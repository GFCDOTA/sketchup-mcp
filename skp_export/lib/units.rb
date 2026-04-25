# lib/units.rb
# Pixel <-> metre conversion for the skp_export bridge.
#
# IMPORTANT: this file is SketchUp-Ruby-API agnostic and contains no
# Sketchup:: references. It can be required from a vanilla Ruby
# interpreter for unit-testing the conversion math.
#
# DPI assumption: the upstream Python pipeline rasterises the PDF at
# 150 DPI. The user-supplied calibration keeps a coarser working value
# of 0.0066 m/px (effectively a slightly-shrunk plant) so that the
# 74 m^2 apartment ends up at canonical scale in SketchUp. This is the
# same constant that V6.1 used; keep it explicit so it can be tuned.

module SkpExport
  module Units
    DPI = 150.0

    # Working pixel-to-metre scale (V6.1 calibration). Override at runtime
    # via SkpExport::Units.px_to_m_override = <float> if needed.
    DEFAULT_PX_TO_M = 0.0066

    @override = nil

    def self.px_to_m_override=(value)
      @override = value
    end

    def self.px_to_m
      @override || DEFAULT_PX_TO_M
    end

    def self.px_to_m_value(px)
      px.to_f * px_to_m
    end

    # Convert a [x_px, y_px] point into [x_m, y_m] world metres.
    # PDF Y grows downward; SketchUp Y grows upward, so we negate Y.
    def self.point_px_to_m(point_px, y_flip_origin: 0.0)
      x_m = point_px[0].to_f * px_to_m
      y_m = (y_flip_origin - point_px[1].to_f) * px_to_m
      [x_m, y_m]
    end

    # Wall thickness (px) -> wall material category. Below 2.5 px the
    # wall is drywall (V6.1 calibration), otherwise alvenaria.
    DRYWALL_PX_THRESHOLD = 2.5
    ALVENARIA_THICKNESS_M = 0.14
    DRYWALL_THICKNESS_M   = 0.075

    def self.wall_thickness_m(thickness_px)
      return DRYWALL_THICKNESS_M if thickness_px.to_f < DRYWALL_PX_THRESHOLD

      ALVENARIA_THICKNESS_M
    end
  end
end
