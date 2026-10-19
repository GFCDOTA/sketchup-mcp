# place_layout_geom.rb — geometria PURA do place_layout_skp.rb (sem a API do SketchUp),
# testável com `ruby` comum (tests/ruby/test_place_layout_geom.rb).
#
# Por que existe: o chanfro das peças macias (almofada/braço/colchão…) era montado
# a partir de `Face#bounds` — caixa ALINHADA AOS EIXOS. Com a peça girada fora de
# múltiplos de 90° (place_sofa_boxes aceita qualquer ângulo), o topo inset saía do
# AABB, não da pegada: placas horizontais vazando da peça (L2 2026-10-19, raytest).
# Aqui o inset é do PRÓPRIO polígono da peça; para retângulo alinhado o resultado é
# o mesmo retângulo de antes.
module PlaceLayoutGeom
  module_function

  def signed_area(ring)
    n = ring.length
    (0...n).sum { |i| ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1] } / 2.0
  end

  # Anel [[x,y],...] em ordem anti-horária (normal +Z), sem fechar.
  def ccw(ring)
    signed_area(ring) < 0 ? ring.reverse : ring
  end

  # Inset de um polígono CONVEXO por `d`: cada aresta anda `d` para dentro e o
  # vértice novo é a interseção das duas arestas deslocadas vizinhas. Devolve o
  # anel CCW na mesma ordem dos vértices de `ccw(ring)`, ou nil se `d` consome o
  # polígono (área não positiva, orientação invertida ou arestas paralelas).
  def convex?(ring)
    n = ring.length
    return false if n < 3

    crosses = (0...n).map do |i|
      a = ring[i]
      b = ring[(i + 1) % n]
      c = ring[(i + 2) % n]
      (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
    end
    crosses.all? { |x| x > -1e-9 } || crosses.all? { |x| x < 1e-9 }
  end

  def inset_convex(ring, d)
    pts = ccw(ring.map { |p| [p[0].to_f, p[1].to_f] })
    n = pts.length
    return nil if n < 3 || !convex?(pts)

    lines = (0...n).map do |i|
      a = pts[i]
      b = pts[(i + 1) % n]
      dx = b[0] - a[0]
      dy = b[1] - a[1]
      len = Math.hypot(dx, dy)
      return nil if len < 1e-9

      nx = -dy / len # normal à ESQUERDA = para dentro num anel CCW
      ny = dx / len
      [[a[0] + nx * d, a[1] + ny * d], [dx, dy]]
    end
    out = (0...n).map do |i|
      p1, v1 = lines[(i - 1) % n]
      p2, v2 = lines[i]
      den = v1[0] * v2[1] - v1[1] * v2[0]
      return nil if den.abs < 1e-12

      t = ((p2[0] - p1[0]) * v2[1] - (p2[1] - p1[1]) * v2[0]) / den
      [p1[0] + v1[0] * t, p1[1] + v1[1] * t]
    end
    signed_area(out) > 1e-9 ? out : nil
  end
end
