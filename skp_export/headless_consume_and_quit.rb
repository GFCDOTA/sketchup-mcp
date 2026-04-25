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

begin
  load CONSUMER_RB
  model = Sketchup.active_model
  # door_lib explicitly passed; consume_consensus also has a DEFAULT_DOOR_LIB
  # fallback to the same path if File.exist? checks pass.
  Consume.from_consensus(CONSENSUS_JSON, model, door_lib: DOOR_LIB)
  model.save(OUTPUT_SKP)
  warn("[headless] saved #{OUTPUT_SKP}")
rescue => e
  warn("[headless] ERROR: #{e.class}: #{e.message}")
  warn(e.backtrace.first(8).join("\n"))
ensure
  # Defer quit so SU can flush the save buffer.
  UI.start_timer(2.0, false) { Sketchup.send_action("fileQuit:") }
end
