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

  def mat(model, name, rgb)
    m = model.materials[name]
    return m if m
    m = model.materials.add(name)
    m.color = Sketchup::Color.new(rgb[0], rgb[1], rgb[2])
    m.alpha = 1.0
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

  # Almofada de ASSENTO: corpo coroado (volume), frente macia, espessura plausivel.
  # seam: se true, costura sutil no ombro superior externo.
  def seat_cushion_primitive(ents, x0, y0, x1, y1, z0, z1,
                             softness: 'medium', mat_obj: nil, name: nil,
                             seam: false, seam_mat: nil)
    sp = soft_params(softness)
    g = crowned_box(ents, x0, y0, x1, y1, z0, z1,
                    r: sp[:r] * 1.3, crown: sp[:crown], seg: 8,
                    mat_obj: mat_obj, name: name)
    if seam
      zsh = (z1 - sp[:crown] * 0.5) * M  # no ombro da coroa
      perim = rounded_rect_pts(x0 * M, y0 * M, x1 * M, y1 * M, zsh, sp[:r] * 1.3 * M, 8)
      # costura FILHA do grupo da almofada (acompanha rake/transform — fix v1)
      thin_seam_line(g.entities, perim, radius_m: 0.0045, mat_obj: seam_mat, name: "#{name}_seam")
    end
    g
  end

  # Almofada de ENCOSTO: espessura minima garantida, coroada, topo arredondado.
  # O rake e aplicado pelo COMPONENTE (rotaciona o grupo) — aqui sai vertical.
  def back_cushion_primitive(ents, x0, y0, x1, y1, z0, z1,
                             softness: 'medium', mat_obj: nil, name: nil,
                             seam: false, seam_mat: nil)
    sp = soft_params(softness)
    g = crowned_box(ents, x0, y0, x1, y1, z0, z1,
                    r: sp[:r] * 1.2, crown: sp[:crown] * 0.9, seg: 8,
                    mat_obj: mat_obj, name: name)
    if seam
      zsh = (z1 - sp[:crown] * 0.5) * M
      perim = rounded_rect_pts(x0 * M, y0 * M, x1 * M, y1 * M, zsh, sp[:r] * 1.2 * M, 8)
      # costura FILHA do grupo (acompanha o rake aplicado pelo componente — fix v1)
      thin_seam_line(g.entities, perim, radius_m: 0.0045, mat_obj: seam_mat, name: "#{name}_seam")
    end
    g
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
