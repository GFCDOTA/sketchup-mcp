# skmcp_core.rb — lógica PURA dos jobs su_* (sem a API do SketchUp).
#
# Fica separado para ser testável com `ruby` comum (tests/test_sketchup_ruby_core.py):
# seleção de alvo, regra de arquitetura protegida e câmeras dos presets de vista.
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
end
