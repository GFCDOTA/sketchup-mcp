# screenshot_consensus.rb
# Carrega generated_from_consensus.skp e exporta:
#   - skp_topview_v62.png   — TRUE top-down ortográfica (parallel projection)
#   - skp_iso_v62.png       — vista isométrica padrão
#   - bounds_dump.txt       — bounds de cada Wall_*, Room_*, Door_* (debug outlier)
# Usa via: SketchUp.exe -RubyStartup screenshot_consensus.rb <template.skp>

SKP_PATH    = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/generated_from_consensus.skp"
PNG_TOPVIEW = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/skp_topview_v62.png"
PNG_ISO     = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/skp_iso_v62.png"
BOUNDS_DUMP = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/bounds_dump.txt"
LOG_FILE    = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/screenshot_run.log"

def slog(m)
  File.open(LOG_FILE, "a") { |f| f.puts "[#{Time.now}] #{m}" }
  warn(m) rescue nil
end

File.write(LOG_FILE, "")
File.write(BOUNDS_DUMP, "")
slog("START screenshot")

begin
  ok = Sketchup.open_file(SKP_PATH)
  slog("open_file returned: #{ok.inspect}")
  model = Sketchup.active_model
  view  = model.active_view

  bbox = model.bounds
  cx = bbox.center.x
  cy = bbox.center.y
  cz = bbox.center.z
  diag = bbox.diagonal
  slog("model bounds (inches): center=(#{cx.to_f.round(2)}, #{cy.to_f.round(2)}, #{cz.to_f.round(2)}) diag=#{diag.to_f.round(2)}")
  slog("model bounds (m):      center=(#{cx.to_m.round(2)}, #{cy.to_m.round(2)}, #{cz.to_m.round(2)}) diag=#{diag.to_m.round(2)}")
  slog("model bounds (m):      min=(#{bbox.min.x.to_m.round(2)}, #{bbox.min.y.to_m.round(2)}, #{bbox.min.z.to_m.round(2)})  max=(#{bbox.max.x.to_m.round(2)}, #{bbox.max.y.to_m.round(2)}, #{bbox.max.z.to_m.round(2)})")

  # ============================================================
  # BOUNDS DUMP — encontra outliers entre walls/rooms/doors
  # ============================================================
  File.open(BOUNDS_DUMP, "w") do |f|
    f.puts "model.bounds (m): min=(#{bbox.min.x.to_m.round(3)}, #{bbox.min.y.to_m.round(3)}, #{bbox.min.z.to_m.round(3)})  max=(#{bbox.max.x.to_m.round(3)}, #{bbox.max.y.to_m.round(3)}, #{bbox.max.z.to_m.round(3)})"
    f.puts "=" * 80

    walls = model.entities.grep(Sketchup::Group).select { |g| g.name =~ /^Wall_/ }
    rooms = model.entities.grep(Sketchup::Group).select { |g| g.name =~ /^Room_/ }
    doors_inst = model.entities.grep(Sketchup::ComponentInstance).select { |i| i.name =~ /^Door_/ }
    doors_grp  = model.entities.grep(Sketchup::Group).select { |g| g.name =~ /^Door_/ }
    f.puts "groups counts: walls=#{walls.size} rooms=#{rooms.size} door_instances=#{doors_inst.size} door_groups=#{doors_grp.size}"
    f.puts ""

    f.puts "=== WALLS (top-5 by y_max) ==="
    walls_sorted = walls.sort_by { |w| -w.bounds.max.y.to_f }
    walls_sorted.first(5).each do |w|
      bb = w.bounds
      f.puts "  #{w.name}  y[#{bb.min.y.to_m.round(2)}..#{bb.max.y.to_m.round(2)}] x[#{bb.min.x.to_m.round(2)}..#{bb.max.x.to_m.round(2)}]"
    end
    f.puts ""
    f.puts "=== WALLS (top-5 by y_min — most negative) ==="
    walls_sorted_min = walls.sort_by { |w| w.bounds.min.y.to_f }
    walls_sorted_min.first(5).each do |w|
      bb = w.bounds
      f.puts "  #{w.name}  y[#{bb.min.y.to_m.round(2)}..#{bb.max.y.to_m.round(2)}] x[#{bb.min.x.to_m.round(2)}..#{bb.max.x.to_m.round(2)}]"
    end
    f.puts ""

    f.puts "=== ROOMS (top-5 by y_max) ==="
    rooms_sorted = rooms.sort_by { |r| -r.bounds.max.y.to_f }
    rooms_sorted.first(5).each do |r|
      bb = r.bounds
      f.puts "  #{r.name}  y[#{bb.min.y.to_m.round(2)}..#{bb.max.y.to_m.round(2)}] x[#{bb.min.x.to_m.round(2)}..#{bb.max.x.to_m.round(2)}]"
    end
    f.puts ""

    f.puts "=== DOORS (all, instances + groups) ==="
    (doors_inst + doors_grp).each do |d|
      bb = d.bounds
      f.puts "  #{d.name}  y[#{bb.min.y.to_m.round(2)}..#{bb.max.y.to_m.round(2)}] x[#{bb.min.x.to_m.round(2)}..#{bb.max.x.to_m.round(2)}] z[#{bb.min.z.to_m.round(2)}..#{bb.max.z.to_m.round(2)}]"
    end
  end
  slog("bounds dump saved: #{BOUNDS_DUMP}")

  # ============================================================
  # TOP VIEW — TRUE ortho parallel projection
  # ============================================================
  # eye direto acima do center, target = center, up = +Y, perspective = false (parallel)
  eye_z = cz + diag * 1.5
  view.camera = Sketchup::Camera.new(
    Geom::Point3d.new(cx, cy, eye_z),
    Geom::Point3d.new(cx, cy, cz),
    Geom::Vector3d.new(0, 1, 0),
    false  # perspective = false -> PARALLEL PROJECTION (true ortho)
  )
  view.camera.perspective = false  # double safety
  view.zoom_extents
  view.write_image(filename: PNG_TOPVIEW, width: 1600, height: 1200, antialias: true)
  slog("TOP saved: #{PNG_TOPVIEW}  perspective=#{view.camera.perspective?}")

  # ============================================================
  # ISO VIEW — perspective desligada também pra forma menos distorcida
  # ============================================================
  iso_dist = diag * 1.2
  view.camera = Sketchup::Camera.new(
    Geom::Point3d.new(cx + iso_dist * 0.7, cy - iso_dist * 0.7, cz + iso_dist * 0.6),
    Geom::Point3d.new(cx, cy, cz),
    Geom::Vector3d.new(0, 0, 1),
    false  # parallel projection no iso tambem (axonometric)
  )
  view.zoom_extents
  view.write_image(filename: PNG_ISO, width: 1600, height: 1200, antialias: true)
  slog("ISO saved: #{PNG_ISO}")

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
