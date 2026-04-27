# dump_wall_coords.rb
# Abre o .skp gerado e despeja: bounds globais + 5 walls samples (start/end coords)
# Usa via: SketchUp.exe -RubyStartup dump_wall_coords.rb <template.skp>

SKP_PATH = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/generated_from_consensus.skp"
LOG_FILE = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/wall_coords_dump.log"

def dlog(m)
  File.open(LOG_FILE, "a") { |f| f.puts "[#{Time.now}] #{m}" }
end

File.write(LOG_FILE, "")
dlog("START dump_wall_coords")

begin
  Sketchup.open_file(SKP_PATH)
  model = Sketchup.active_model
  dlog("model.bounds: min=#{model.bounds.min.inspect} max=#{model.bounds.max.inspect}")
  dlog("min in inches: (#{model.bounds.min.x.to_f}, #{model.bounds.min.y.to_f}, #{model.bounds.min.z.to_f})")
  dlog("max in inches: (#{model.bounds.max.x.to_f}, #{model.bounds.max.y.to_f}, #{model.bounds.max.z.to_f})")
  dlog("diagonal in inches: #{model.bounds.diagonal.to_f}")
  dlog("diagonal in m: #{model.bounds.diagonal.to_m}")

  # Sanity check: 1.m -> ?
  one_m = 1.m
  dlog("1.m = #{one_m.to_f} (deveria ser ~39.37 se .m -> inches)")
  dlog("1.m.to_m = #{1.m.to_m rescue 'N/A'}")

  # Iterar grupos Wall_*
  walls = model.entities.grep(Sketchup::Group).select { |g| g.name =~ /^Wall_/ }
  dlog("count walls: #{walls.size}")

  walls.first(5).each do |w|
    bb = w.bounds
    dlog("  #{w.name}: min=(#{bb.min.x.to_f.round(3)}, #{bb.min.y.to_f.round(3)}, #{bb.min.z.to_f.round(3)}) " \
         "max=(#{bb.max.x.to_f.round(3)}, #{bb.max.y.to_f.round(3)}, #{bb.max.z.to_f.round(3)}) " \
         "(inches)")
    dlog("    width=#{(bb.max.x.to_f - bb.min.x.to_f).round(3)} in " \
         "depth=#{(bb.max.y.to_f - bb.min.y.to_f).round(3)} in " \
         "height=#{(bb.max.z.to_f - bb.min.z.to_f).round(3)} in")
  end

  # Primeira face de uma wall -> coords reais dos vertices
  if walls.first
    g_ents = walls.first.entities
    face = g_ents.grep(Sketchup::Face).first
    if face
      dlog("first wall first face vertices (inches):")
      face.vertices.each_with_index do |v, i|
        p = v.position
        dlog("  v#{i}: (#{p.x.to_f.round(4)}, #{p.y.to_f.round(4)}, #{p.z.to_f.round(4)})")
      end
    end
  end

rescue => e
  dlog("ERR: #{e.class}: #{e.message}")
  dlog(e.backtrace.first(10).join("\n"))
ensure
  UI.start_timer(2.0, false) { Sketchup.send_action("fileQuit:") rescue nil }
end
