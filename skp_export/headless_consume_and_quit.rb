# headless_consume_and_quit.rb
# Loaded via SketchUp CLI: SketchUp.exe -RubyStartup <this_file>
# (flag support varies by SU version; fallback: load manually from Ruby console).
#
# Builds the model from consensus_model.json, saves to the target .skp,
# then quits. Designed for one-shot dashboard slot fill.

CONSENSUS_JSON = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json"
OUTPUT_SKP     = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/generated_from_consensus.skp"
CONSUMER_RB    = "E:/Claude/sketchup-mcp/skp_export/consume_consensus.rb"
DOOR_LIB       = "E:/Claude/sketchup-mcp/skp_export/components/Door Interior.skp"
LOG_FILE       = "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/headless_run.log"

def hlog(msg)
  File.open(LOG_FILE, "a") { |f| f.puts "[#{Time.now}] #{msg}" }
  warn(msg) rescue nil
end

File.write(LOG_FILE, "")  # truncate at start
hlog("START headless_consume_and_quit")
hlog("RUBY_VERSION=#{RUBY_VERSION}  Sketchup.version=#{Sketchup.version rescue 'N/A'}")

begin
  hlog("loading #{CONSUMER_RB}")
  load CONSUMER_RB
  hlog("CONSUMER_RB loaded")
  model = Sketchup.active_model
  hlog("active_model: #{model.inspect}")
  hlog("calling Consume.from_consensus")
  # door_lib forcado pra "" pra usar fallback procedural (rectangle simples)
  # — Door Interior.skp do SU sampler tem axis convention X=width Y=HEIGHT
  # Z=thickness (nao Y=thickness como assume_upright esperava). Resultado:
  # doors saiam com y span 7.46m (height multiplicado por scale_y errado).
  # TBD V6.3: detectar smallest axis = thickness automatically em
  # place_real_component, OU re-modelar Door Interior com eixos certos.
  effective_door_lib = ENV["CONSUME_DOOR_LIB"]
  if effective_door_lib.nil?
    effective_door_lib = ""  # default: forca fallback procedural
    hlog("door_lib defaulted to '' (procedural fallback) — set CONSUME_DOOR_LIB env to override")
  end
  result = Consume.from_consensus(CONSENSUS_JSON, model, door_lib: effective_door_lib)
  hlog("from_consensus returned: #{result.inspect}")
  # Sanity check: model.bounds em metros — deve casar com walls_world_range
  # logado por compute_origin (caso contrario, transform inconsistente).
  bb = model.bounds
  hlog("model.bounds (m): min=(#{bb.min.x.to_m.round(3)}, #{bb.min.y.to_m.round(3)}, #{bb.min.z.to_m.round(3)}) " \
       "max=(#{bb.max.x.to_m.round(3)}, #{bb.max.y.to_m.round(3)}, #{bb.max.z.to_m.round(3)})")
  hlog("model.bounds diag (m): #{bb.diagonal.to_m.round(3)}")
  hlog("saving to #{OUTPUT_SKP}")
  ok = model.save(OUTPUT_SKP)
  hlog("save returned: #{ok.inspect}")
rescue => e
  hlog("ERROR: #{e.class}: #{e.message}")
  hlog(e.backtrace.first(15).join("\n"))
ensure
  hlog("scheduling fileQuit in 2s")
  UI.start_timer(2.0, false) do
    begin
      hlog("invoking fileQuit:")
      Sketchup.send_action("fileQuit:")
    rescue => qe
      hlog("fileQuit error: #{qe.message}")
    end
  end
end
