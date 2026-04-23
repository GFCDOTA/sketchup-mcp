# test/test_units.rb
# Unit tests for SkpExport::Units. Pure Ruby — run outside SketchUp.
#
# Run with:
#   ruby skp_export/test/test_units.rb
#
# If Ruby is not installed on the host, these tests are documentation
# only. The equivalent thickness classification behaviour is
# cross-checked on the Python side by `tests/test_skp_export_f9.py`
# (see `test_dry_run_p12_thickness_breakdown`).

$LOAD_PATH.unshift(File.expand_path("..", __dir__))

require_relative "sketchup_stub"
require "minitest/autorun"

require "lib/units"

class TestUnits < Minitest::Test
  def setup
    SkpExport::Units.px_to_m_override = nil
  end

  def test_px_to_m_default
    assert_in_delta 0.0066, SkpExport::Units.px_to_m, 1e-9
  end

  def test_px_to_m_value_scalar
    assert_in_delta 0.066, SkpExport::Units.px_to_m_value(10), 1e-9
    assert_in_delta 0.0, SkpExport::Units.px_to_m_value(0), 1e-9
  end

  def test_point_px_to_m_backcompat
    # Legacy kwarg name `y_flip_origin:` still honoured (so callers
    # that haven't migrated to Coords keep working).
    x, y = SkpExport::Units.point_px_to_m([100, 50], y_flip_origin: 200)
    assert_in_delta 0.66, x, 1e-6
    assert_in_delta 0.99, y, 1e-6
  end

  def test_thickness_classifier_drywall_below_threshold
    assert_in_delta 0.075, SkpExport::Units.wall_thickness_m(2.4), 1e-6
    assert_in_delta 0.075, SkpExport::Units.wall_thickness_m(1.0), 1e-6
  end

  def test_thickness_classifier_alvenaria_at_threshold
    assert_in_delta 0.14, SkpExport::Units.wall_thickness_m(2.5), 1e-6
    assert_in_delta 0.14, SkpExport::Units.wall_thickness_m(5.0), 1e-6
  end

  def test_thickness_boundary_exactly_at_threshold
    # The classifier uses strict `<` so exactly 2.5 is alvenaria.
    got = SkpExport::Units.wall_thickness_m(2.5)
    assert_equal SkpExport::Units::ALVENARIA_THICKNESS_M, got
  end

  def test_thickness_boundary_just_below_threshold
    # Anything < 2.5 is drywall.
    got = SkpExport::Units.wall_thickness_m(2.4999999)
    assert_equal SkpExport::Units::DRYWALL_THICKNESS_M, got
  end

  def test_classify_wall_thicknesses_mixed_list
    walls = [
      { "thickness" => 1.0 },
      { "thickness" => 2.4 },
      { "thickness" => 2.5 },
      { "thickness" => 3.8 },
      { "thickness" => 5.0 },
    ]
    counts = SkpExport::Units.classify_wall_thicknesses(walls)
    assert_equal 2, counts[:drywall]
    assert_equal 3, counts[:alvenaria]
  end

  def test_classify_wall_thicknesses_accepts_bare_numbers
    counts = SkpExport::Units.classify_wall_thicknesses([1.0, 2.6, 2.5, 0.5])
    assert_equal 2, counts[:drywall]
    assert_equal 2, counts[:alvenaria]
  end

  def test_classify_wall_thicknesses_empty_list
    counts = SkpExport::Units.classify_wall_thicknesses([])
    assert_equal 0, counts[:drywall]
    assert_equal 0, counts[:alvenaria]
  end

  def test_classify_wall_thicknesses_nil_input
    counts = SkpExport::Units.classify_wall_thicknesses(nil)
    assert_equal 0, counts[:drywall]
    assert_equal 0, counts[:alvenaria]
  end
end
