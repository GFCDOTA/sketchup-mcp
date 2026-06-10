# sofa_primitives.rb — primitivas reutilizaveis de estofado low/mid-poly p/ SketchUp.
#
# Implementa o contrato de docs/SOFA_SKILL.md. Anti-caixote por design:
#   - cantos VERTICAIS arredondados (rounded-rect extrudado), nao 90deg vivo;
#   - topo das almofadas COROADO (volume), nao chapado;
#   - pes em frustum (afilados), nao perna de mesa;
#   - piping/costura via followme (guard-railed);
#   - suavizacao (soft+smooth) SO nas arestas curvas, nunca nos 90deg reais.
#
# Unidade da API publica: METROS. Converte p/ polegadas (unidade interna do SU).
# Convencao: X=largura, Y=profundidade (frente=min Y), Z=altura.
# Cada primitiva desenha num `ents` (normalmente grupo nomeado) e devolve o grupo.

module SofaPrimitives
  M = 39.3700787402  # metros -> polegadas (unidade interna do SketchUp)

  module_function

  # ---- helpers -------------------------------------------------------------

  def mat(model, name, rgb)
    m = model.materials[name]
    return m if m
    m = model.materials.add(name)
    m.color = Sketchup::Color.new(rgb[0], rgb[1], rgb[2])
    m.alpha = 1.0
    m
  end

  # Perimetro de retangulo ARREDONDADO (em polegadas). Devolve Array<Point3d> no z dado.
  # r = raio do canto; seg = segmentos por canto (low-poly: 4-6). CCW.
  def rounded_rect_pts(x0, y0, x1, y1, z, r, seg = 5)
    r = [r, (x1 - x0) / 2.0 - 0.001, (y1 - y0) / 2.0 - 0.001].min
    if r <= 0.001
      return [Geom::Point3d.new(x0, y0, z), Geom::Point3d.new(x1, y0, z),
              Geom::Point3d.new(x1, y1, z), Geom::Point3d.new(x0, y1, z)]
    end
    # centro de cada canto + angulo inicial (graus), no sentido CCW
    corners = [[x1 - r, y0 + r, 270.0],   # baixo-direita
               [x1 - r, y1 - r,   0.0],   # cima-direita
               [x0 + r, y1 - r,  90.0],   # cima-esquerda
               [x0 + r, y0 + r, 180.0]]   # baixo-esquerda
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
        ang = fs[0].normal.angle_between(fs[1].normal)  # radianos
      rescue StandardError
        next
      end
      if ang > 0.02 && ang < 1.0   # ~1deg..57deg = segmento de curva/coroa
        e.soft = true
        e.smooth = true
      end
    end
  end

  def _extrude_up(face, h_in)
    # extruda p/ CIMA independente da orientacao da normal (idioma do place_layout)
    face.pushpull(face.normal.z >= 0 ? h_in : -h_in)
  end

  def _top_face(group, ztop_in)
    group.entities.grep(Sketchup::Face).find do |f|
      f.normal.z.abs > 0.9 && (f.bounds.center.z - ztop_in).abs < 0.4
    end
  end

  # ---- primitivas ----------------------------------------------------------

  # Caixa com cantos verticais arredondados + topo macio opcional (top_bevel = coroa/chanfro).
  def rounded_box(ents, x0, y0, x1, y1, z0, z1,
                  r: 0.04, top_bevel: 0.0, seg: 5, mat_obj: nil, name: nil)
    x0i, y0i, x1i, y1i, z0i, z1i, ri, tbi =
      [x0, y0, x1, y1, z0, z1, r, top_bevel].map { |v| v * M }
    g = ents.add_group
    g.name = name if name
    h = z1i - z0i
    tb = [tbi, h / 2.0 - 0.05].min
    tb = 0.0 if tb < 0.0
    base_h = h - tb

    base_pts = rounded_rect_pts(x0i, y0i, x1i, y1i, z0i, ri, seg)
    face = g.entities.add_face(base_pts)
    return g if face.nil?
    _extrude_up(face, base_h)

    # coroa/chanfro: face do topo recebe um nucleo INSET levantado (rounded) -> macio
    if tb > 0.05
      ztop = z0i + base_h
      tf = _top_face(g, ztop)
      if tf
        ip = rounded_rect_pts(x0i + tb, y0i + tb, x1i - tb, y1i - tb, ztop,
                              [ri, tb].max, seg)
        inner = g.entities.add_face(ip)
        _extrude_up(inner, tb) if inner
      end
    end

    g.material = mat_obj if mat_obj
    soften_curved_edges(g)
    g
  end

  # Almofada de assento: rounded_box COROADO (volume) + piping opcional na borda do topo.
  def seat_cushion(ents, x0, y0, x1, y1, z0, z1,
                   r: 0.045, crown: 0.05, seg: 5, mat_obj: nil, piping_mat: nil, name: nil)
    g = rounded_box(ents, x0, y0, x1, y1, z0, z1,
                    r: r, top_bevel: crown, seg: seg, mat_obj: mat_obj, name: name)
    if piping_mat
      # vivo na borda superior externa (no nivel do ombro da coroa)
      zsh = (z1 - crown) * M
      perim = rounded_rect_pts(x0 * M, y0 * M, x1 * M, y1 * M, zsh, r * M, seg)
      piping(ents, perim, 0.008, mat_obj: piping_mat)
    end
    g
  end

  # Almofada de encosto: mesma familia (o build aplica o rake via rotacao do grupo).
  def back_cushion(ents, x0, y0, x1, y1, z0, z1,
                   r: 0.045, crown: 0.045, seg: 5, mat_obj: nil, piping_mat: nil, name: nil)
    g = rounded_box(ents, x0, y0, x1, y1, z0, z1,
                    r: r, top_bevel: crown, seg: seg, mat_obj: mat_obj, name: name)
    if piping_mat
      zsh = (z1 - crown) * M
      perim = rounded_rect_pts(x0 * M, y0 * M, x1 * M, y1 * M, zsh, r * M, seg)
      piping(ents, perim, 0.008, mat_obj: piping_mat)
    end
    g
  end

  # Braco LARGO com topo bem arredondado (track/rolled arm).
  def armrest(ents, x0, y0, x1, y1, z0, z1, r: 0.06, seg: 6, mat_obj: nil, name: nil)
    # topo arredondado generoso: top_bevel ~ metade da largura do braco (limitado)
    w = [(x1 - x0), (y1 - y0)].min
    rounded_box(ents, x0, y0, x1, y1, z0, z1,
                r: [r, w / 2.5].min, top_bevel: [w / 3.0, (z1 - z0) / 2.0].min,
                seg: seg, mat_obj: mat_obj, name: name)
  end

  # Pe CURTO afilado (frustum): topo (junto a base) mais largo, ponta mais estreita.
  def leg(ents, cx, cy, half, z0, z1, taper: 0.35, seg: 4, mat_obj: nil, name: nil)
    cxi, cyi, hi, z0i, z1i = [cx, cy, half, z0, z1].map { |v| v * M }
    tb = hi               # meia-largura no topo (encosta na base)
    bb = hi * (1.0 - taper) # meia-largura na ponta (afilado)
    g = ents.add_group
    g.name = name if name
    top = [[cxi - tb, cyi - tb, z1i], [cxi + tb, cyi - tb, z1i],
           [cxi + tb, cyi + tb, z1i], [cxi - tb, cyi + tb, z1i]].map { |p| Geom::Point3d.new(*p) }
    bot = [[cxi - bb, cyi - bb, z0i], [cxi + bb, cyi - bb, z0i],
           [cxi + bb, cyi + bb, z0i], [cxi - bb, cyi + bb, z0i]].map { |p| Geom::Point3d.new(*p) }
    begin
      g.entities.add_face(top)
      4.times do |i|
        j = (i + 1) % 4
        g.entities.add_face(top[i], top[j], bot[j], bot[i])
      end
      g.entities.add_face(bot)
    rescue StandardError
      nil
    end
    g.material = mat_obj if mat_obj
    g
  end

  # Vivo/piping: followme de um circulo fino ao longo do perimetro (guard-railed).
  # perimeter_pts em POLEGADAS. radius em METROS.
  def piping(ents, perimeter_pts, radius_m, mat_obj: nil)
    return nil if perimeter_pts.nil? || perimeter_pts.size < 4
    g = ents.add_group
    begin
      path = []
      n = perimeter_pts.size
      (0...n).each do |i|
        a = perimeter_pts[i]
        b = perimeter_pts[(i + 1) % n]
        next if a.distance(b) < 0.01
        e = g.entities.add_line(a, b)
        path << e if e
      end
      return g if path.size < 3
      p0 = perimeter_pts[0]
      p1 = perimeter_pts[1]
      dir = p1 - p0
      dir.normalize!
      circ = g.entities.add_circle(p0, dir, radius_m * M, 8)
      cface = g.entities.add_face(circ)
      cface.followme(path) if cface
      g.material = mat_obj if mat_obj
    rescue StandardError
      # piping e prioridade 4: se falhar, degrada (sofa continua valido)
    end
    g
  end
end
