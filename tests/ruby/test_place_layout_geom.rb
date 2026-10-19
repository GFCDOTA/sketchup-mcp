# Testa a geometria PURA do place_layout_skp.rb (place_layout_geom.rb) com ruby comum.
# Rodado por tests/test_place_layout_geom.py.
#
# Regressão do L2 de 2026-10-19: peça macia girada 30° ganhava topo inset calculado
# do AABB e vazava da pegada. O inset precisa ficar DENTRO do polígono da peça.
require 'minitest/autorun'
require_relative '../../tools/sketchup/furnish/place_layout_geom'

class TestPlaceLayoutGeom < Minitest::Test
  G = PlaceLayoutGeom

  def rect(cx, cy, w, d, deg)
    t = deg * Math::PI / 180.0
    c = Math.cos(t)
    s = Math.sin(t)
    [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]].map do |x, y|
      [cx + x * c - y * s, cy + x * s + y * c]
    end
  end

  # ponto dentro de polígono convexo CCW (todas as arestas à esquerda)
  def inside?(ring, p, tol = 1e-6)
    n = ring.length
    (0...n).all? do |i|
      a = ring[i]
      b = ring[(i + 1) % n]
      (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -tol
    end
  end

  def dist_to_edges(ring, p)
    n = ring.length
    (0...n).map do |i|
      a = ring[i]
      b = ring[(i + 1) % n]
      ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])).abs / Math.hypot(b[0] - a[0], b[1] - a[1])
    end.min
  end

  def test_retangulo_alinhado_da_o_mesmo_inset_do_aabb_de_antes
    out = G.inset_convex([[0, 0], [10, 0], [10, 4], [0, 4]], 1.0)
    assert_equal [[1.0, 1.0], [9.0, 1.0], [9.0, 3.0], [1.0, 3.0]].sort, out.map { |p| p.map { |v| v.round(9) } }.sort
  end

  def test_peca_girada_30_graus_fica_dentro_da_pegada
    ring = G.ccw(rect(100, 50, 24, 10, 30))
    out = G.inset_convex(ring, 1.5)
    refute_nil out
    out.each do |p|
      assert inside?(ring, p), "vértice #{p.inspect} fora da pegada girada"
      assert_in_delta 1.5, dist_to_edges(ring, p), 1e-6
    end
  end

  def test_qualquer_angulo_mantem_area_do_retangulo_inset
    [0, 12, 30, 45, 78, 90, 137, 210].each do |deg|
      out = G.inset_convex(rect(0, 0, 20, 8, deg), 1.0)
      assert_in_delta 18.0 * 6.0, G.signed_area(out), 1e-6, "ângulo #{deg}"
    end
  end

  def test_ordem_horaria_vira_anti_horaria
    cw = [[0, 0], [0, 4], [10, 4], [10, 0]]
    assert_operator G.signed_area(G.ccw(cw)), :>, 0
    assert_operator G.signed_area(G.inset_convex(cw, 1.0)), :>, 0
  end

  def test_inset_que_consome_a_peca_devolve_nil
    assert_nil G.inset_convex([[0, 0], [2, 0], [2, 2], [0, 2]], 1.5)
  end

  def test_poligono_nao_convexo_devolve_nil
    l_shape = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]
    assert_nil G.inset_convex(l_shape, 0.2)
  end

  def test_vertice_repetido_devolve_nil
    assert_nil G.inset_convex([[0, 0], [0, 0], [4, 0], [4, 4]], 0.5)
  end
end
