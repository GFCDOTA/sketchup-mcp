# sofa_primitives.rb — primitivas reutilizaveis da CLASSE sofa (low/mid-poly SketchUp).
#
# NAO sao hardcoded para um sofa especifico: cada primitiva toma dimensoes em
# METROS, material, nome de grupo e softness, e registra bbox no LOG.
# Anti-"rounded box": almofadas tem CROWN (cupula de 2 tiers) + bordas suaves,
# nao so um chanfro. Suavizacao SO nas arestas curvas (90deg reais ficam vivos).
#
# Unidade interna do SU = POLEGADAS. M converte metros->polegadas.
# Convencao: X=largura, Y=profundidade (frente=min Y), Z=altura.

module SofaPrimitives
  M = 39.3700787402
  LOG = []  # cada primitiva empurra {name, w_m, d_m, h_m} (gerador despeja no validation.json)

  # softness_level -> raio de borda + crown (espelha softness_map do schema)
  SOFT = {
    'low'    => { r: 0.020, crown: 0.030 },
    'medium' => { r: 0.035, crown: 0.050 },
    'high'   => { r: 0.050, crown: 0.070 }
  }.freeze

  module_function

  def soft_params(level)
    SOFT[level.to_s] || SOFT['medium']
  end

  # Hash deterministico seed->float em [0,1). NAO usa rand global (reproduzivel:
  # mesma planta = mesmo .skp). k = sub-canal (bulge/sag/... cada um independente).
  # LCG simples (Numerical Recipes) — barato, sem estado, sem srand.
  def _jrand(seed, k)
    h = (seed.to_i * 2654435761 + (k.to_i + 1) * 40503) & 0xFFFFFFFF
    h = (h * 1664525 + 1013904223) & 0xFFFFFFFF
    h / 4294967296.0
  end

  # Fator de jitter SIMETRICO em [1-amp, 1+amp], seeded por (seed,k). amp<=1.
  def _jfac(seed, k, amp)
    1.0 + (_jrand(seed, k) * 2.0 - 1.0) * amp
  end

  # Offset de jitter SIMETRICO em [-amp, +amp] (p/ tilt/tuck que partem de 0).
  def _joff(seed, k, amp)
    (_jrand(seed, k) * 2.0 - 1.0) * amp
  end

  def mat(model, name, rgb)
    m = model.materials[name]
    return m if m
    m = model.materials.add(name)
    m.color = Sketchup::Color.new(rgb[0], rgb[1], rgb[2])
    m.alpha = 1.0
    m
  end

  # Material de TECIDO com textura procedural tileavel (track de material/GPT):
  # aplica o albedo em UV de escala REAL (tile_m, ex 0.30m) -> mata o RGB chapado.
  # rgb = cor base (fallback/tint se a textura faltar). tex_path = albedo PNG.
  # Robusto: se a textura faltar/falhar, cai pra cor solida (nao quebra o build).
  def mat_fabric(model, name, rgb, tex_path, tile_m)
    m = model.materials[name]
    return m if m
    m = model.materials.add(name)
    m.color = Sketchup::Color.new(rgb[0], rgb[1], rgb[2])
    m.alpha = 1.0
    if tex_path && File.exist?(tex_path)
      begin
        m.texture = tex_path
        m.texture.size = tile_m * M  # UV world-scale: textura ocupa tile_m no modelo
      rescue StandardError => e
        LOG << "tex_fail #{name}: #{e.class}: #{e.message}"
      end
    else
      LOG << "tex_missing #{name}: #{tex_path}"
    end
    m
  end

  # ---- helpers de baixo nivel (em POLEGADAS) -------------------------------

  # Perimetro de retangulo ARREDONDADO. r,seg controlam o canto. CCW.
  def rounded_rect_pts(x0, y0, x1, y1, z, r, seg = 6)
    r = [r, (x1 - x0) / 2.0 - 0.001, (y1 - y0) / 2.0 - 0.001].min
    if r <= 0.001
      return [Geom::Point3d.new(x0, y0, z), Geom::Point3d.new(x1, y0, z),
              Geom::Point3d.new(x1, y1, z), Geom::Point3d.new(x0, y1, z)]
    end
    corners = [[x1 - r, y0 + r, 270.0], [x1 - r, y1 - r, 0.0],
               [x0 + r, y1 - r, 90.0], [x0 + r, y0 + r, 180.0]]
    pts = []
    corners.each do |cx, cy, a0|
      (0..seg).each do |i|
        a = (a0 + 90.0 * i / seg) * Math::PI / 180.0
        pts << Geom::Point3d.new(cx + r * Math.cos(a), cy + r * Math.sin(a), z)
      end
    end
    pts
  end

  # Suaviza SO as arestas curvas (faces quase coplanares). 90deg reais ficam vivos.
  def soften_curved_edges(group)
    group.entities.grep(Sketchup::Edge).each do |e|
      fs = e.faces
      next unless fs.size == 2
      begin
        ang = fs[0].normal.angle_between(fs[1].normal)
      rescue StandardError
        next
      end
      if ang > 0.02 && ang < 1.05  # ~1deg..60deg = curva/crown
        e.soft = true
        e.smooth = true
      end
    end
  end

  def _extrude_up(face, h_in)
    face.pushpull(face.normal.z >= 0 ? h_in : -h_in)
  end

  def _top_face(group, ztop_in)
    group.entities.grep(Sketchup::Face).find do |f|
      f.normal.z.abs > 0.9 && (f.bounds.center.z - ztop_in).abs < 0.5
    end
  end

  def _log(name, group)
    bb = group.bounds
    LOG << { name: name || 'unnamed',
             w_m: ((bb.max.x - bb.min.x) / M).round(3),
             d_m: ((bb.max.y - bb.min.y) / M).round(3),
             h_m: ((bb.max.z - bb.min.z) / M).round(3) }
    group
  end

  # ---- GEOMETRIA BASE ------------------------------------------------------

  # Caixa com cantos verticais arredondados + (opcional) borda do topo arredondada.
  def rounded_box(ents, x0, y0, x1, y1, z0, z1,
                  r: 0.035, top_round: 0.0, seg: 6, mat_obj: nil, name: nil, soften: true)
    x0i, y0i, x1i, y1i, z0i, z1i, ri, tr =
      [x0, y0, x1, y1, z0, z1, r, top_round].map { |v| v * M }
    g = ents.add_group
    g.name = name if name
    h = z1i - z0i
    tr = [tr, h / 2.0 - 0.05].min
    tr = 0.0 if tr < 0.0
    base_h = h - tr
    f = g.entities.add_face(rounded_rect_pts(x0i, y0i, x1i, y1i, z0i, ri, seg))
    return _log(name, g) if f.nil?
    _extrude_up(f, base_h)
    if tr > 0.05  # borda do topo: anel inset levantado (chanfro arredondado)
      zt = z0i + base_h
      tf = _top_face(g, zt)
      if tf
        ip = rounded_rect_pts(x0i + tr, y0i + tr, x1i - tr, y1i - tr, zt, [ri, tr].max, seg)
        inner = g.entities.add_face(ip)
        _extrude_up(inner, tr) if inner
      end
    end
    g.material = mat_obj if mat_obj
    soften_curved_edges(g) if soften
    _log(name, g)
  end

  # rounded_box com borda do topo generosa (partes macias: bracos rolled, etc.)
  def soft_rounded_box(ents, x0, y0, x1, y1, z0, z1,
                       softness: 'medium', seg: 7, mat_obj: nil, name: nil)
    sp = soft_params(softness)
    rounded_box(ents, x0, y0, x1, y1, z0, z1,
                r: sp[:r] * 1.2, top_round: sp[:crown] * 0.9, seg: seg,
                mat_obj: mat_obj, name: name)
  end

  # Caixa COROADA: corpo arredondado + cupula de 2 tiers no topo (volume de almofada).
  def crowned_box(ents, x0, y0, x1, y1, z0, z1,
                  r: 0.045, crown: 0.05, seg: 7, mat_obj: nil, name: nil)
    x0i, y0i, x1i, y1i, z0i, z1i, ri, cr =
      [x0, y0, x1, y1, z0, z1, r, crown].map { |v| v * M }
    g = ents.add_group
    g.name = name if name
    h = z1i - z0i
    cr = [cr, h * 0.45, (x1i - x0i) * 0.22, (y1i - y0i) * 0.22].min
    cr = 0.0 if cr < 0.0
    body_h = h - cr
    f = g.entities.add_face(rounded_rect_pts(x0i, y0i, x1i, y1i, z0i, ri, seg))
    return _log(name, g) if f.nil?
    _extrude_up(f, body_h)
    if cr > 0.04
      # TOPO ROLADO (pillow) — aprendido dos refs 3DW (KIVIK/modern dark): a borda
      # do topo "rola" pra dentro num quarto-de-circulo (dome CONTINUO), nunca
      # degrau/tampa. Apaga a tampa plana e lofta aneis (triangulos = planares).
      zt = z0i + body_h
      tf = _top_face(g, zt)
      tf.erase! if tf
      nseg = 4
      rings = (0..nseg).map do |t|
        a = (t.to_f / nseg) * (Math::PI / 2.0)
        inset = cr * (1.0 - Math.cos(a))
        z = zt + cr * Math.sin(a)
        rounded_rect_pts(x0i + inset, y0i + inset, x1i - inset, y1i - inset, z, [ri * 0.85, 0.05].max, seg)
      end
      (0...nseg).each do |t|
        aa = rings[t]
        bb = rings[t + 1]
        n = [aa.size, bb.size].min
        (0...n).each do |i|
          j = (i + 1) % n
          begin
            g.entities.add_face(aa[i], aa[j], bb[j])
            g.entities.add_face(aa[i], bb[j], bb[i])
          rescue StandardError
            nil
          end
        end
      end
      begin
        g.entities.add_face(rings[nseg])
      rescue StandardError
        nil
      end
    end
    g.material = mat_obj if mat_obj
    soften_curved_edges(g)
    _log(name, g)
  end

  # Pe afilado (frustum): topo (junto a base) mais largo, ponta estreita.
  def tapered_leg(ents, cx, cy, half, z0, z1, taper: 0.35, mat_obj: nil, name: nil)
    cxi, cyi, hwi, z0i, z1i = [cx, cy, half, z0, z1].map { |v| v * M }
    tw = hwi
    bw = hwi * (1.0 - taper)
    g = ents.add_group
    g.name = name if name
    top = [[cxi - tw, cyi - tw, z1i], [cxi + tw, cyi - tw, z1i],
           [cxi + tw, cyi + tw, z1i], [cxi - tw, cyi + tw, z1i]].map { |p| Geom::Point3d.new(*p) }
    bot = [[cxi - bw, cyi - bw, z0i], [cxi + bw, cyi - bw, z0i],
           [cxi + bw, cyi + bw, z0i], [cxi - bw, cyi + bw, z0i]].map { |p| Geom::Point3d.new(*p) }
    begin
      g.entities.add_face(top)
      4.times { |i| j = (i + 1) % 4; g.entities.add_face(top[i], top[j], bot[j], bot[i]) }
      g.entities.add_face(bot)
    rescue StandardError
      nil
    end
    g.material = mat_obj if mat_obj
    _log(name, g)
  end

  # Pe bloco (rounded box pequeno, quina levemente suave).
  def block_leg(ents, cx, cy, half, z0, z1, mat_obj: nil, name: nil)
    rounded_box(ents, cx - half, cy - half, cx + half, cy + half, z0, z1,
                r: 0.006, top_round: 0.0, seg: 3, mat_obj: mat_obj, name: name)
  end

  # Pe/tubo cilindrico sutil (metal stub / pe redondo). seg baixo = low-poly.
  def cylinder_or_tube_subtle(ents, cx, cy, radius, z0, z1, seg: 12, mat_obj: nil, name: nil)
    cxi, cyi, rad, z0i, z1i = [cx, cy, radius, z0, z1].map { |v| v * M }
    g = ents.add_group
    g.name = name if name
    begin
      circ = g.entities.add_circle(Geom::Point3d.new(cxi, cyi, z0i),
                                   Geom::Vector3d.new(0, 0, 1), rad, seg)
      f = g.entities.add_face(circ)
      _extrude_up(f, z1i - z0i) if f
      g.entities.grep(Sketchup::Edge).each { |e| e.soft = true; e.smooth = true if e.line[1].z.abs < 0.01 || true }
    rescue StandardError
      nil
    end
    g.material = mat_obj if mat_obj
    _log(name, g)
  end

  # Linha de costura SUTIL: tubo fino via followme ao longo de um perimetro.
  # Subordinado a forma: raio pequeno, guard-railed (se falhar, degrada).
  # perimeter_pts em POLEGADAS. radius_m em METROS (sutil: 0.004-0.006).
  def thin_seam_line(ents, perimeter_pts, radius_m: 0.005, seg: 6, mat_obj: nil, name: nil)
    return nil if perimeter_pts.nil? || perimeter_pts.size < 4
    g = ents.add_group
    g.name = name if name
    begin
      path = []
      n = perimeter_pts.size
      (0...n).each do |i|
        a = perimeter_pts[i]
        b = perimeter_pts[(i + 1) % n]
        next if a.distance(b) < 0.02
        e = g.entities.add_line(a, b)
        path << e if e
      end
      return _log(name, g) if path.size < 3
      dir = (perimeter_pts[1] - perimeter_pts[0])
      dir.normalize!
      circ = g.entities.add_circle(perimeter_pts[0], dir, radius_m * M, seg)
      cf = g.entities.add_face(circ)
      cf.followme(path) if cf
      g.material = mat_obj if mat_obj
    rescue StandardError
      nil
    end
    _log(name, g)
  end

  # ---- ESTOFADO (diferente de caixa arredondada) --------------------------

  # SoftCushionPrimitive — almofada DEFORMADA por costura+peso (nao rounded box).
  # Topo = malha nu x nv (GPT: <=6x4) deformada: bulge central + edge_compression +
  # sag frontal + corner_pinch + seam_tuck (a costura AFUNDA a malha na borda).
  # Faces TRIANGULADAS (evita non-planar). soften so no estofado (topo/laterais),
  # nunca nas arestas estruturais. Tudo em metros; converte p/ polegadas.
  # Aprendido do gate GPT (ref 3DW): "parar de gerar caixa, gerar almofada comprimida".
  def soft_cushion_primitive(ents, x0, y0, x1, y1, z0, z1,
                             softness: 'medium', bulge: nil, sag_front: nil,
                             seam_depth: nil, edge_comp: nil, corner_pinch: nil,
                             nu: 6, nv: 4, mat_obj: nil, name: nil,
                             seam: false, seam_mat: nil,
                             jitter: 0.0, seed: 0)
    sp = soft_params(softness)
    bulge      = (bulge      || sp[:crown] * 1.0)
    sag_front  = (sag_front  || bulge * 0.45)
    seam_depth = (seam_depth || bulge * 0.40)
    edge_comp  = (edge_comp  || bulge * 0.45)
    corner_pinch = (corner_pinch || bulge * 0.30)
    # MICRO-IRREGULARIDADE CONTROLADA (GPT TOP_FIX): cada almofada herda um jitter
    # seeded dos PROPRIOS params (sem ruido no loop). jitter=0.0 -> jf==1 / offsets==0
    # -> byte-identico ao caller atual (no-op de CLASSE). Amplitudes pequenas (a forma
    # convergida bulge/tuck/sag/silhueta fica; isto so quebra a uniformidade CAD).
    jit = [[jitter.to_f, 0.0].max, 1.0].min
    # +-amp por sub-canal (k distinto). ~+-9..12% nos volumes; tilt/tuck menores.
    bulge        *= _jfac(seed, 0, jit * 0.10)   # +-10% do dome central
    sag_front    *= _jfac(seed, 1, jit * 0.12)   # +-12% da queda frontal
    seam_depth   *= _jfac(seed, 2, jit * 0.12)   # +-12% do tuck/divisoria
    corner_pinch *= _jfac(seed, 3, jit * 0.12)   # +-12% do beliscao de canto
    # edge_comp NAO jittered: e a "frente reta/uniforme" aprovada no ciclo8 -> intacta.
    tilt = _joff(seed, 4, jit * 0.08)            # assimetria E<->D do dome: +-8%
    tuck_lo = _jfac(seed, 5, jit * 0.10)         # tuck borda esquerda (u~0)  +-10%
    tuck_hi = _jfac(seed, 6, jit * 0.10)         # tuck borda direita  (u~1)  +-10%
    g = ents.add_group
    g.name = name if name
    th = z1 - z0
    maxdef = th * 0.5
    top = Array.new(nu + 1) { Array.new(nv + 1) }
    (0..nu).each do |i|
      u = i.to_f / nu
      (0..nv).each do |j|
        v = j.to_f / nv
        x = x0 + (x1 - x0) * u
        y = y0 + (y1 - y0) * v
        # tilt: inclina LEVEMENTE o dome p/ um lado (assimetria E<->D), amplitude (2u-1).
        du = (1.0 - (2.0 * u - 1.0)**2) * (1.0 + tilt * (2.0 * u - 1.0)) # dome (1 centro, 0 borda)
        dv = 1.0 - (2.0 * v - 1.0)**2
        eu = (2.0 * u - 1.0)**2           # borda (0 centro, 1 borda)
        ev = (2.0 * v - 1.0)**2
        ring = [u, 1.0 - u, v, 1.0 - v].min          # dist a borda mais proxima
        seam_t = ring < 0.16 ? (1.0 - ring / 0.16) : 0.0  # tuck raso na borda
        # tuck por borda: esquerda (u<0.5) vs direita (u>=0.5) com fatores diferentes
        # -> divisoes/encontros deixam de ser identicos. v=0.5 => fator 1 (continuo).
        edge_fac = u < 0.5 ? tuck_lo : tuck_hi
        dz = bulge * du * dv \
             - edge_comp * (eu + ev) * 0.5 \
             - seam_depth * seam_t * edge_fac \
             - corner_pinch * (eu * ev) \
             - sag_front * ((1.0 - v)**2) * 0.6        # frente (v=0) cai
        dz = [[dz, maxdef].min, -maxdef].max
        top[i][j] = Geom::Point3d.new(x * M, y * M, (z1 + dz) * M)
      end
    end
    # topo triangulado
    (0...nu).each do |i|
      (0...nv).each do |j|
        a = top[i][j]; b = top[i + 1][j]; c = top[i + 1][j + 1]; d = top[i][j + 1]
        begin; g.entities.add_face(a, b, c); rescue StandardError; end
        begin; g.entities.add_face(a, c, d); rescue StandardError; end
      end
    end
    # perimetro -> laterais ate z0 + fundo
    z0i = z0 * M
    perim = []
    (0...nu).each { |i| perim << top[i][0] }
    (0...nv).each { |j| perim << top[nu][j] }
    nu.downto(1).each { |i| perim << top[i][nv] }
    nv.downto(1).each { |j| perim << top[0][j] }
    n = perim.size
    (0...n).each do |k|
      a = perim[k]; b = perim[(k + 1) % n]
      ab = Geom::Point3d.new(a.x, a.y, z0i)
      bb = Geom::Point3d.new(b.x, b.y, z0i)
      begin; g.entities.add_face(a, b, bb); rescue StandardError; end
      begin; g.entities.add_face(a, bb, ab); rescue StandardError; end
    end
    begin; g.entities.add_face(perim.map { |p| Geom::Point3d.new(p.x, p.y, z0i) }); rescue StandardError; end
    g.material = mat_obj if mat_obj
    # soften/smooth TODO o estofado (topo+lados) como superficie continua; SO as arestas
    # do fundo (z0) ficam vivas. Mata o serrilhado/facetado do mesh deformado.
    # (GPT: "soften/smooth normals obrigatorio"; aqui = superficie macia, sem patamar.)
    g.entities.grep(Sketchup::Edge).each do |e|
      next if e.start.position.z <= z0i + 0.05 && e.end.position.z <= z0i + 0.05
      begin
        e.soft = true
        e.smooth = true
      rescue StandardError
        nil
      end
    end
    if seam
      # piping fino SEPARADO no ombro (perimetro), guard-railed
      zsh = (z1 - bulge * 0.5) * M
      pr = rounded_rect_pts(x0 * M, y0 * M, x1 * M, y1 * M, zsh, 0.03 * M, 6)
      thin_seam_line(g.entities, pr, radius_m: 0.004, mat_obj: seam_mat, name: "#{name}_seam")
    end
    _log(name, g)
  end

  # Almofada TUFTED (capitone): grid de botoes/sulcos + PUFFS estofados entre eles, alem
  # do bulge geral. Para sectional/tradicional (NAO o lounge liso). low/mid-poly.
  # tuft_grid=[gx,gy] = numero de PUFFS (diamantes) em X,Y. tuft_bulge=altura do puff,
  # tuft_depth=fundura do botao/sulco. O tufting e GEOMETRIA (depressoes reais), nao linha
  # desenhada. Reaproveita jitter seeded (organic) + piping geometrico opcional (bead fino).
  def tufted_cushion_primitive(ents, x0, y0, x1, y1, z0, z1,
                               softness: 'medium', tuft_grid: [3, 2],
                               tuft_bulge: 0.035, tuft_depth: 0.018, sag_front: nil,
                               corner_pinch: nil, base_bulge: nil,
                               piping: false, piping_radius: 0.012,
                               jitter: 0.0, seed: 0, mat_obj: nil, seam_mat: nil, name: nil)
    sp = soft_params(softness)
    gx = [tuft_grid[0].to_i, 1].max
    gy = [tuft_grid[1].to_i, 1].max
    base_bulge   = (base_bulge   || sp[:crown] * 0.55)   # cupula geral suave (o tuft da o resto)
    sag_front    = (sag_front    || base_bulge * 0.35)
    corner_pinch = (corner_pinch || base_bulge * 0.30)
    # organic/micro-irregularidade: jitter seeded por almofada (default 0 = no-op byte-igual)
    jit = [[jitter.to_f, 0.0].max, 1.0].min
    base_bulge *= _jfac(seed, 0, jit * 0.10)
    tb = tuft_bulge * _jfac(seed, 1, jit * 0.10)
    td = tuft_depth * _jfac(seed, 2, jit * 0.10)
    tilt = _joff(seed, 3, jit * 0.06)
    g = ents.add_group
    g.name = name if name
    th = z1 - z0
    maxdef = th * 0.5
    nu = [gx * 6, 14].max
    nv = [gy * 6, 10].max
    top = Array.new(nu + 1) { Array.new(nv + 1) }
    (0..nu).each do |i|
      u = i.to_f / nu
      (0..nv).each do |j|
        v = j.to_f / nv
        x = x0 + (x1 - x0) * u
        y = y0 + (y1 - y0) * v
        du = (1.0 - (2.0 * u - 1.0)**2) * (1.0 + tilt * (2.0 * u - 1.0))
        dv = 1.0 - (2.0 * v - 1.0)**2
        eu = (2.0 * u - 1.0)**2
        ev = (2.0 * v - 1.0)**2
        # padrao tufted: puff (centro das celulas) sobe; sulcos (linhas do grid) descem;
        # botoes (cantos do grid) descem MAIS. Falloff na borda (rim p/ piping, nao tufta ali).
        pu = Math.sin(Math::PI * gx * u).abs
        pv = Math.sin(Math::PI * gy * v).abs
        puff = pu * pv
        btn  = (1.0 - pu) * (1.0 - pv)
        ring = [u, 1.0 - u, v, 1.0 - v].min
        ef = [ring / 0.13, 1.0].min
        tuft = (tb * puff - td * (1.0 - puff) - td * 0.7 * btn) * ef
        dz = base_bulge * du * dv \
             + tuft \
             - corner_pinch * (eu * ev) \
             - sag_front * ((1.0 - v)**2) * 0.6
        dz = [[dz, maxdef].min, -maxdef].max
        top[i][j] = Geom::Point3d.new(x * M, y * M, (z1 + dz) * M)
      end
    end
    (0...nu).each do |i|
      (0...nv).each do |j|
        a = top[i][j]; b = top[i + 1][j]; c = top[i + 1][j + 1]; d = top[i][j + 1]
        begin; g.entities.add_face(a, b, c); rescue StandardError; end
        begin; g.entities.add_face(a, c, d); rescue StandardError; end
      end
    end
    z0i = z0 * M
    perim = []
    (0...nu).each { |i| perim << top[i][0] }
    (0...nv).each { |j| perim << top[nu][j] }
    nu.downto(1).each { |i| perim << top[i][nv] }
    nv.downto(1).each { |j| perim << top[0][j] }
    np = perim.size
    (0...np).each do |k|
      a = perim[k]; b = perim[(k + 1) % np]
      ab = Geom::Point3d.new(a.x, a.y, z0i)
      bb = Geom::Point3d.new(b.x, b.y, z0i)
      begin; g.entities.add_face(a, b, bb); rescue StandardError; end
      begin; g.entities.add_face(a, bb, ab); rescue StandardError; end
    end
    begin; g.entities.add_face(perim.map { |p| Geom::Point3d.new(p.x, p.y, z0i) }); rescue StandardError; end
    g.material = mat_obj if mat_obj
    g.entities.grep(Sketchup::Edge).each do |e|
      next if e.start.position.z <= z0i + 0.05 && e.end.position.z <= z0i + 0.05
      begin
        e.soft = true
        e.smooth = true
      rescue StandardError
        nil
      end
    end
    if piping
      zsh = (z1 - base_bulge * 0.35) * M
      pr = rounded_rect_pts(x0 * M, y0 * M, x1 * M, y1 * M, zsh, 0.025 * M, 6)
      thin_seam_line(g.entities, pr, radius_m: piping_radius, mat_obj: seam_mat || mat_obj, name: "#{name}_piping")
    end
    _log(name, g)
  end

  # Almofada de ASSENTO: SoftCushion (deformada), nao rounded box. family='tight'
  # (KIVIK-ish) usa menos bulge / mais bloco; senao mais bulge/macio (lounge).
  def seat_cushion_primitive(ents, x0, y0, x1, y1, z0, z1,
                             softness: 'medium', mat_obj: nil, name: nil,
                             seam: false, seam_mat: nil, family: nil, min_crown: 0.0,
                             jitter: 0.0, seed: 0)
    sp = soft_params(softness)
    blk = (family == 'tight')
    # GPT generalizacao: piso de volume (so quem opta passa min_crown>0; default 0 = no-op
    # byte-igual). Standard usa floor p/ nao ler chapado em medium; lounge passa 0.
    cr = [sp[:crown], min_crown].max
    # GPT ciclo4: menos "barriga" -> bulge MENOR + compressao mais UNIFORME (edge_comp
    # maior), frente mais reta (sag menor), tuck mais sutil (seam menor), topo menos arqueado.
    # GPT ciclo8: frente mais RETA/menos arqueada -> bulge e sag menores ainda +
    # compressao frontal mais controlada/uniforme (edge_comp maior).
    soft_cushion_primitive(ents, x0, y0, x1, y1, z0, z1,
                           softness: softness,
                           bulge: cr * (blk ? 0.34 : 0.45),
                           sag_front: cr * 0.14,
                           seam_depth: cr * (blk ? 0.14 : 0.20),
                           edge_comp: cr * 0.62,
                           corner_pinch: cr * 0.18,
                           nu: 6, nv: 4, mat_obj: mat_obj, name: name,
                           seam: seam, seam_mat: seam_mat,
                           jitter: jitter, seed: seed)
  end

  # Almofada de ENCOSTO estofada (NAO placa): deforma a FACE FRONTAL (-Y, lado do
  # sentado) -> bulge no meio (volume) + BASE comprimida contra o assento (tuck) +
  # topo recuado/soft. y0=frente (encosta no assento), y1=fundo (plano, estrutural).
  # O rake e aplicado pelo COMPONENTE (rotacao do grupo) — preservado.
  # GPT (perfil/encosto): "menos placa, mais volume, base comprimida, topo soft".
  def back_cushion_primitive(ents, x0, y0, x1, y1, z0, z1,
                             softness: 'medium', mat_obj: nil, name: nil,
                             seam: false, seam_mat: nil, min_crown: 0.0,
                             jitter: 0.0, seed: 0)
    sp = soft_params(softness)
    cr = [sp[:crown], min_crown].max  # GPT generalizacao: piso de volume frontal (default 0 = no-op)
    depth = (y1 - y0)
    bulge = cr * 1.1        # protrusao max (meio) pro sentado
    base_comp = cr * 0.85   # base recua/comprime contra o assento (w~0)
    top_back = depth * 0.8          # topo: frente recua ate ~o fundo -> borda fina ARREDONDADA (GPT)
    # MICRO-IRREGULARIDADE (GPT, back_variance<seat_variance): jitter seeded por almofada
    # de ENCOSTO, amplitudes MENORES que o assento (encosto varia menos). jitter=0 -> no-op.
    jit = [[jitter.to_f, 0.0].max, 1.0].min
    bulge     *= _jfac(seed, 0, jit * 0.08)   # +-8% do volume frontal
    base_comp *= _jfac(seed, 1, jit * 0.10)   # +-10% do tuck na base
    btilt = _joff(seed, 2, jit * 0.06)        # assimetria E<->D do hump +-6%
    g = ents.add_group
    g.name = name if name
    nu = 6
    nw = 10                         # silhueta lateral LISA (GPT: curva continua, nao facetada)
    yb = y1 * M                     # face de tras (plana, estrutural)
    front = Array.new(nu + 1) { Array.new(nw + 1) }
    (0..nu).each do |i|
      u = i.to_f / nu
      (0..nw).each do |k|
        w = k.to_f / nw
        x = x0 + (x1 - x0) * u
        z = z0 + (z1 - z0) * w
        du = (1.0 - (2.0 * u - 1.0)**2) * (1.0 + btilt * (2.0 * u - 1.0))  # tilt: assimetria E<->D
        hump = Math.sin(Math::PI * w)   # corcova SUAVE (0 nas pontas, pico no meio) -> silhueta continua
        # frente: bulge suave (meio) ; base tuck (w~0) ; topo recua/arredonda (w~1)
        yf = y0 - (bulge * du * hump) \
                + (base_comp * ((1.0 - w)**2)) \
                + (top_back * (w**2.4))  # curva suave que fecha o topo (sem canto)
        yf = [yf, y0 - depth * 0.85].max
        yf = [yf, y1 - 0.005].min
        front[i][k] = Geom::Point3d.new(x * M, yf * M, z * M)
      end
    end
    (0...nu).each do |i|
      (0...nw).each do |k|
        a = front[i][k]; b = front[i + 1][k]; c = front[i + 1][k + 1]; d = front[i][k + 1]
        begin; g.entities.add_face(a, b, c); rescue StandardError; end
        begin; g.entities.add_face(a, c, d); rescue StandardError; end
      end
    end
    perim = []
    (0...nu).each { |i| perim << front[i][0] }
    (0...nw).each { |k| perim << front[nu][k] }
    nu.downto(1).each { |i| perim << front[i][nw] }
    nw.downto(1).each { |k| perim << front[0][k] }
    n = perim.size
    (0...n).each do |idx|
      a = perim[idx]; b = perim[(idx + 1) % n]
      ab = Geom::Point3d.new(a.x, yb, a.z)
      bb = Geom::Point3d.new(b.x, yb, b.z)
      begin; g.entities.add_face(a, b, bb); rescue StandardError; end
      begin; g.entities.add_face(a, bb, ab); rescue StandardError; end
    end
    begin; g.entities.add_face(perim.map { |p| Geom::Point3d.new(p.x, yb, p.z) }); rescue StandardError; end
    g.material = mat_obj if mat_obj
    g.entities.grep(Sketchup::Edge).each do |e|
      next if (e.start.position.y - yb).abs < 0.05 && (e.end.position.y - yb).abs < 0.05
      begin
        e.soft = true
        e.smooth = true
      rescue StandardError
        nil
      end
    end
    _log(name, g)
  end

  # Pillow (pillow back / almofada solta): mais plump e mais arredondada.
  def pillow_primitive(ents, x0, y0, x1, y1, z0, z1,
                       softness: 'high', mat_obj: nil, name: nil)
    sp = soft_params(softness)
    crowned_box(ents, x0, y0, x1, y1, z0, z1,
                r: sp[:r] * 1.6, crown: sp[:crown] * 1.2, seg: 9,
                mat_obj: mat_obj, name: name)
  end

  # Braco ROLLED/soft: corpo macio com topo bem arredondado (roll).
  def rolled_arm_primitive(ents, x0, y0, x1, y1, z0, z1,
                           softness: 'medium', mat_obj: nil, name: nil)
    sp = soft_params(softness)
    w = [(x1 - x0), (y1 - y0)].min
    crowned_box(ents, x0, y0, x1, y1, z0, z1,
                r: [sp[:r] * 1.4, w / 2.6].min, crown: [w / 2.4, (z1 - z0) * 0.4].min,
                seg: 9, mat_obj: mat_obj, name: name)
  end
end
