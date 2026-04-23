# test/test_coords.rb
# Unit tests for SkpExport::Coords. Pure Ruby — run outside SketchUp.
#
# Run with:
#   ruby skp_export/test/test_coords.rb
#
# If Ruby is not installed on the host (SketchUp's bundled Ruby is
# not on PATH), these tests are documentation only. The equivalent
# behaviour is cross-checked on the Python side by
# `tests/test_skp_export_f9.py`.

$LOAD_PATH.unshift(File.expand_path("..", __dir__))

require_relative "sketchup_stub"
require "minitest/autorun"

require "lib/coords"
require "lib/units"

class TestCoords < Minitest::Test
  # Default V6.1 calibration: 0.0066 m/px.
  def setup
    SkpExport::Units.px_to_m_override = nil
  end

  def test_px_per_metre_matches_calibration
    # 1 / 0.0066 m/px ≈ 151.515 px/m
    assert_in_delta 151.515, SkpExport::Coords.px_per_metre, 0.01
  end

  def test_length_px_to_m_basic
    # 100 px * 0.0066 m/px = 0.66 m
    assert_in_delta 0.66, SkpExport::Coords.length_px_to_m(100), 1e-6
    assert_in_delta 0.0, SkpExport::Coords.length_px_to_m(0), 1e-9
    # Negative values allowed (e.g. deltas).
    assert_in_delta(-0.132, SkpExport::Coords.length_px_to_m(-20), 1e-6)
  end

  def test_point_px_to_m_no_flip
    # origin_y_px = 0 means Y is just negated
    x_m, y_m = SkpExport::Coords.point_px_to_m([100, 50], origin_y_px: 0.0)
    assert_in_delta 0.66, x_m, 1e-6
    assert_in_delta(-0.33, y_m, 1e-6)
  end

  def test_point_px_to_m_with_y_flip_origin
    # origin_y_px = 200: Y is flipped so a point near the top of the
    # raster (small y) ends up near the top of the SketchUp world
    # (large +y).
    x_m, y_m = SkpExport::Coords.point_px_to_m([100, 50], origin_y_px: 200.0)
    assert_in_delta 0.66, x_m, 1e-6
    # (200 - 50) px * 0.0066 m/px = 0.99 m
    assert_in_delta 0.99, y_m, 1e-6
  end

  def test_point_px_to_m_y_flip_roundtrip
    # Flipping twice should return (approximately) the original Y in
    # pixels. We simulate a roundtrip with origin=300.
    origin = 300.0
    y_px_in = 120.0
    _x, y_m = SkpExport::Coords.point_px_to_m([0, y_px_in], origin_y_px: origin)
    # Reverse: y_m = (origin - y_px) * px_to_m => y_px = origin - y_m / px_to_m
    y_px_out = origin - y_m / SkpExport::Units.px_to_m
    assert_in_delta y_px_in, y_px_out, 1e-6
  end

  def test_world_point_fallback_returns_struct
    # Under the stub, Geom::Point3d is a Struct with x/y/z.
    pt = SkpExport::Coords.world_point(1.5, 2.5, 3.5)
    # `.m` is identity under the stub (Numeric#m returns self).
    assert_in_delta 1.5, pt.x, 1e-6
    assert_in_delta 2.5, pt.y, 1e-6
    assert_in_delta 3.5, pt.z, 1e-6
  end

  def test_wall_thickness_m_drywall_below_threshold
    # Below 2.5 px -> drywall (0.075 m)
    assert_in_delta 0.075, SkpExport::Coords.wall_thickness_m(2.4), 1e-6
    assert_in_delta 0.075, SkpExport::Coords.wall_thickness_m(0.1), 1e-6
  end

  def test_wall_thickness_m_alvenaria_at_threshold
    # Exactly 2.5 px or above -> alvenaria (0.14 m)
    assert_in_delta 0.14, SkpExport::Coords.wall_thickness_m(2.5), 1e-6
    assert_in_delta 0.14, SkpExport::Coords.wall_thickness_m(3.8), 1e-6
  end

  def test_px_to_m_override_changes_scale
    # Crank override to 0.01 m/px (≈1:100 plan).
    SkpExport::Units.px_to_m_override = 0.01
    assert_in_delta 1.0, SkpExport::Coords.length_px_to_m(100), 1e-9
  ensure
    SkpExport::Units.px_to_m_override = nil
  end
end
