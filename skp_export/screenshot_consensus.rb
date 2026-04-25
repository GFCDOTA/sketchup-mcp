# screenshot_consensus.rb
# Carrega generated_from_consensus.skp e exporta topview + iso PNG.
# Usa via: SketchUp.exe -RubyStartup screenshot_consensus.rb <template.skp>

SKP_PATH    = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/generated_from_consensus.skp"
PNG_TOPVIEW = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/skp_topview_v62.png"
PNG_ISO     = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/skp_iso_v62.png"
LOG_FILE    = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/screenshot_run.log"

def slog(m)
  File.open(LOG_FILE, "a") { |f| f.puts "[#{Time.now}] #{m}" }
  warn(m) rescue nil
end

File.write(LOG_FILE, "")
slog("START screenshot")

begin
  ok = Sketchup.open_file(SKP_PATH)
  slog("open_file returned: #{ok.inspect}")
  model = Sketchup.active_model
  view  = model.active_view

  # Top view (camera straight down on XY plane)
  bbox = model.bounds
  cx = bbox.center.x
  cy = bbox.center.y
  cz = bbox.center.z
  diag = bbox.diagonal
  slog("model bounds center=(#{cx.to_f}, #{cy.to_f}, #{cz.to_f}) diag=#{diag.to_f}")

  view.camera = Sketchup::Camera.new(
    Geom::Point3d.new(cx, cy, cz + diag),
    Geom::Point3d.new(cx, cy, cz),
    Geom::Vector3d.new(0, 1, 0)
  )
  view.zoom_extents
  view.write_image(filename: PNG_TOPVIEW, width: 1600, height: 1200, antialias: true)
  slog("topview saved: #{PNG_TOPVIEW}")

  # Iso view (NE corner looking down at apartment)
  view.camera = Sketchup::Camera.new(
    Geom::Point3d.new(cx + diag * 0.7, cy - diag * 0.7, cz + diag * 0.6),
    Geom::Point3d.new(cx, cy, cz),
    Geom::Vector3d.new(0, 0, 1)
  )
  view.zoom_extents
  view.write_image(filename: PNG_ISO, width: 1600, height: 1200, antialias: true)
  slog("iso saved: #{PNG_ISO}")
rescue => e
  slog("ERR: #{e.class}: #{e.message}")
  slog(e.backtrace.first(15).join("\n"))
ensure
  UI.start_timer(2.0, false) do
    begin
      Sketchup.send_action("fileQuit:")
    rescue => qe
      slog("fileQuit error: #{qe.message}")
    end
  end
end
