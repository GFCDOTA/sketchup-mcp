# skmcp_core.rb — lógica PURA dos jobs su_* (sem a API do SketchUp).
#
# Fica separado para ser testável com `ruby` comum (tests/test_sketchup_ruby_jobs.py):
# seleção de alvo, proteção da arquitetura, câmeras dos presets e a matemática
# de referencial (mundo × local do pai).
# Tudo que toca Sketchup:: mora nos jobs, não aqui.

module SkmcpCore
  module_function

  def protected_name?(name, prefixes)
    n = name.to_s
    prefixes.any? { |p| n.start_with?(p) }
  end

  # info = {'name'=>, 'definition'=>, 'pid'=>}. Componente costuma ter nome de
  # INSTÂNCIA vazio — o nome que o Outliner mostra é o da definição.
  def matches?(info, target)
    if target.key?('persistent_id')
      info['pid'] == target['persistent_id']
    elsif target.key?('name')
      v = target['name']
      info['name'] == v || (info['name'].to_s.empty? && info['definition'] == v)
    else
      needle = target['name_contains'].to_s.downcase
      [info['name'], info['definition']].any? { |s| s.to_s.downcase.include?(needle) }
    end
  end

  # Devolve [infos, erro]. expect 'one' recusa zero ou ambíguo — mexer no
  # objeto errado é pior do que não mexer.
  def select(infos, target)
    hits = infos.select { |i| matches?(i, target) }
    if hits.empty?
      return [[], "nenhuma entidade casa com #{target.reject { |k, _| k == 'expect' }.inspect}"]
    end
    if target.fetch('expect', 'one') == 'one' && hits.size > 1
      names = hits.first(10).map { |h| h['path'] || h['name'] }
      return [[], "#{hits.size} entidades casam (expect=one): #{names.inspect}; " \
                  'use persistent_id ou expect=all']
    end
    [hits, nil]
  end

  # Câmera de um preset sobre um bbox [min xyz, max xyz] (polegadas).
  # Retorna {eye, target, up, perspective}.
  def preset_camera(preset, bmin, bmax)
    c = [0, 1, 2].map { |i| (bmin[i] + bmax[i]) / 2.0 }
    diag = Math.sqrt([0, 1, 2].map { |i| (bmax[i] - bmin[i])**2 }.sum)
    d = diag * 1.6
    case preset
    when 'top'
      { 'eye' => [c[0], c[1], c[2] + diag * 5.0], 'target' => c, 'up' => [0, 1, 0],
        'perspective' => false }
    when 'iso'
      { 'eye' => [c[0] + d * 0.9, c[1] - d * 1.0, c[2] + d * 0.9], 'target' => c,
        'up' => [0, 0, 1], 'perspective' => true }
    when 'front'
      { 'eye' => [c[0], c[1] - d * 1.4, c[2]], 'target' => c, 'up' => [0, 0, 1], 'perspective' => true }
    when 'back'
      { 'eye' => [c[0], c[1] + d * 1.4, c[2]], 'target' => c, 'up' => [0, 0, 1], 'perspective' => true }
    when 'left'
      { 'eye' => [c[0] - d * 1.4, c[1], c[2]], 'target' => c, 'up' => [0, 0, 1], 'perspective' => true }
    when 'right'
      { 'eye' => [c[0] + d * 1.4, c[1], c[2]], 'target' => c, 'up' => [0, 0, 1], 'perspective' => true }
    else
      raise ArgumentError, "preset desconhecido: #{preset.inspect} (top/iso/front/back/left/right)"
    end
  end

  # Altura ortográfica que enquadra o bbox inteiro numa imagem w×h.
  def ortho_height(bmin, bmax, width, height)
    mw = bmax[0] - bmin[0]
    mh = bmax[1] - bmin[1]
    [mh, mw / (width.to_f / height)].max * 1.06
  end

  def safe_filename(name)
    s = name.to_s.gsub(/[^A-Za-z0-9_.-]+/, '_')
    s.empty? ? 'view' : s
  end

  # -- proteção ----------------------------------------------------------------
  # info vem de SkmcpRuntime.walk (+ dedupe): name, definition, locked,
  # ancestors [{label,name,definition,locked}], ancestor_pids, contexts.
  # Devolve o motivo da recusa de uma op guardada (move/rotate/delete/rename),
  # ou nil. Olhar só o nome da INSTÂNCIA deixava passar: mover o pai que contém
  # a parede, casar pela definição, editar dentro de grupo travado ou dentro de
  # componente com várias instâncias (a edição vazaria para todas).
  def guard_violation(info, infos, prefixes)
    if protected_name?(info['name'], prefixes) || protected_name?(info['definition'], prefixes)
      return "#{info['path']} é arquitetura derivada do PDF"
    end
    anc = (info['ancestors'] || []).find do |a|
      protected_name?(a['name'], prefixes) || protected_name?(a['definition'], prefixes)
    end
    return "#{info['path']} está dentro de arquitetura (#{anc['label']})" if anc

    inner = descendants(infos, info['pid']).select do |d|
      protected_name?(d['name'], prefixes) || protected_name?(d['definition'], prefixes)
    end
    unless inner.empty?
      return "#{info['path']} contém arquitetura: #{inner.first(5).map { |d| d['path'] }.inspect}"
    end
    return "#{info['path']} está travado (locked)" if info['locked']

    lk = (info['ancestors'] || []).find { |a| a['locked'] }
    return "#{info['path']} está dentro de um grupo travado (#{lk['label']})" if lk
    if info['contexts'].to_i > 1
      return "#{info['path']} vive numa definição usada em #{info['contexts']} lugares — " \
             'a edição alteraria todos; faça make_unique antes'
    end
    nil
  end

  def descendants(infos, pid)
    infos.select { |i| (i['ancestor_pids'] || []).include?(pid) }
  end

  # O walk visita o conteúdo de um componente uma vez POR INSTÂNCIA, e as
  # entidades dentro da definição têm o mesmo persistent_id em todas. Junta por
  # pid; `contexts` > 1 = a entidade é compartilhada entre instâncias.
  #
  # A ancestralidade é a UNIÃO de todas as visitas: guardar só a 1ª deixava a
  # arquitetura dentro das outras instâncias de um container compartilhado
  # invisível para descendants() — mover a 2ª cópia passava pela guarda.
  def dedupe(infos)
    by = {}
    infos.each do |i|
      cur = by[i['pid']]
      if cur
        cur['contexts'] += 1
        cur['paths'] << i['path']
        cur['ancestor_pids'] = cur['ancestor_pids'] | (i['ancestor_pids'] || [])
        cur['ancestors'] = (cur['ancestors'] + (i['ancestors'] || [])).uniq { |a| a['pid'] }
        cur['locked'] ||= i['locked']
      else
        by[i['pid']] = i.merge('contexts' => 1, 'paths' => [i['path']],
                               'ancestor_pids' => (i['ancestor_pids'] || []).dup,
                               'ancestors' => (i['ancestors'] || []).dup)
      end
    end
    by.values
  end

  # Alvos de move/rotate em que um é ancestral de outro: o filho já anda com o
  # pai, e transformá-lo de novo dobraria o movimento. Devolve os aninhados.
  def nested_hits(hits)
    pids = hits.map { |h| h['pid'] }
    hits.select { |h| (h['ancestor_pids'] || []).any? { |p| pids.include?(p) } }
  end

  # -- referencial -------------------------------------------------------------
  # Matriz 4x4 no layout de Geom::Transformation#to_a: coluna-major,
  # [xaxis(0..2), 0, yaxis(4..6), 0, zaxis(8..10), 0, origem(12..14), w(15)].
  # O SketchUp pode guardar escala uniforme em w (to_a[15] != 1) — normalize.
  IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0].freeze

  def normalize(m)
    w = m[15].to_f
    return m.map(&:to_f) if w == 1.0 || w.zero?
    m.each_with_index.map { |v, i| i == 15 ? 1.0 : v.to_f / w }
  end

  def mat_mul(a, b)
    a = normalize(a)
    b = normalize(b)
    out = Array.new(16, 0.0)
    4.times do |col|
      4.times do |row|
        out[col * 4 + row] = (0..3).sum { |k| a[k * 4 + row] * b[col * 4 + k] }
      end
    end
    out
  end

  def apply_point(m, p)
    m = normalize(m)
    (0..2).map { |r| m[r] * p[0] + m[4 + r] * p[1] + m[8 + r] * p[2] + m[12 + r] }
  end

  def apply_vector(m, v)
    m = normalize(m)
    (0..2).map { |r| m[r] * v[0] + m[4 + r] * v[1] + m[8 + r] * v[2] }
  end

  # Inversa de uma transformação afim (parte linear 3x3 + translação).
  def inverse_affine(m)
    m = normalize(m)
    a = [[m[0], m[4], m[8]], [m[1], m[5], m[9]], [m[2], m[6], m[10]]]
    det = a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) -
          a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0]) +
          a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
    raise ArgumentError, 'transformação singular (escala zero)' if det.abs < 1e-12

    inv = [
      [(a[1][1] * a[2][2] - a[1][2] * a[2][1]), -(a[0][1] * a[2][2] - a[0][2] * a[2][1]), (a[0][1] * a[1][2] - a[0][2] * a[1][1])],
      [-(a[1][0] * a[2][2] - a[1][2] * a[2][0]), (a[0][0] * a[2][2] - a[0][2] * a[2][0]), -(a[0][0] * a[1][2] - a[0][2] * a[1][0])],
      [(a[1][0] * a[2][1] - a[1][1] * a[2][0]), -(a[0][0] * a[2][1] - a[0][1] * a[2][0]), (a[0][0] * a[1][1] - a[0][1] * a[1][0])],
    ].map { |row| row.map { |v| v / det } }
    t = [m[12], m[13], m[14]]
    ti = (0..2).map { |r| -(inv[r][0] * t[0] + inv[r][1] * t[1] + inv[r][2] * t[2]) }
    [inv[0][0], inv[1][0], inv[2][0], 0.0,
     inv[0][1], inv[1][1], inv[2][1], 0.0,
     inv[0][2], inv[1][2], inv[2][2], 0.0,
     ti[0], ti[1], ti[2], 1.0]
  end

  # Mover "by" em eixos do MUNDO: transform! trabalha no referencial do PAI,
  # então o vetor precisa ir para o local do pai (só a parte linear).
  def world_to_local_vector(parent_world, v)
    apply_vector(inverse_affine(parent_world), v)
  end

  # Rotação de `degrees` em torno do Z do MUNDO passando por `center`, como
  # matriz no layout de Geom::Transformation#to_a.
  def rotation_z(center, degrees)
    t = degrees.to_f * Math::PI / 180.0
    c = Math.cos(t)
    s = Math.sin(t)
    cx, cy, = center.map(&:to_f)
    [c, s, 0.0, 0.0, -s, c, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0,
     cx - c * cx + s * cy, cy - s * cx - c * cy, 0.0, 1.0]
  end

  # Transformação a aplicar com transform! (que age no referencial do PAI) para
  # que o efeito no MUNDO seja exatamente `world_mat`: inv(P) · W · P.
  # Conjugar a matriz inteira — e não só levar eixo e centro para o local — é o
  # que mantém o sentido certo sob pai ESPELHADO (Flip Along, det < 0): ali uma
  # rotação de +θ no eixo local vira -θ no mundo.
  def local_transform_for_world(parent_world, world_mat)
    mat_mul(inverse_affine(parent_world), mat_mul(world_mat, parent_world))
  end

  # Eixos ortogonais e de mesmo comprimento: só aí uma rotação em torno do Z do
  # mundo continua sendo rotação depois de levada para o local do pai.
  def uniform_frame?(m, tol = 1e-6)
    m = normalize(m)
    cols = [[m[0], m[1], m[2]], [m[4], m[5], m[6]], [m[8], m[9], m[10]]]
    lens = cols.map { |c| Math.sqrt(c.sum { |x| x * x }) }
    return false if lens.min < tol

    dots = [[0, 1], [0, 2], [1, 2]].map { |i, j| (0..2).sum { |k| cols[i][k] * cols[j][k] } }
    dots.all? { |d| d.abs <= tol * lens.max**2 } && (lens.max - lens.min) <= tol * lens.max
  end

  # bbox de MUNDO a partir do bbox local da definição (8 cantos transformados).
  def world_bbox(bmin, bmax, m)
    corners = [bmin[0], bmax[0]].product([bmin[1], bmax[1]], [bmin[2], bmax[2]])
    pts = corners.map { |c| apply_point(m, c) }
    lo = (0..2).map { |i| pts.map { |p| p[i] }.min }
    hi = (0..2).map { |i| pts.map { |p| p[i] }.max }
    [lo, hi]
  end
end
