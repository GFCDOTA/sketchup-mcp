## Boot fired by SketchUp -RubyStartup. Logs each phase to disk.

LOG = 'E:/Claude/sketchup-mcp/runs/vector/_boot.log'

def lg(s)
  File.open(LOG, 'a') { |f| f.puts("[#{Time.now.strftime('%H:%M:%S')}] #{s}") } rescue nil
end

# Wipe log up front
File.delete(LOG) rescue nil
lg("boot.rb start; ruby=#{RUBY_VERSION}")

ENV['CONSENSUS_JSON'] = 'E:/Claude/sketchup-mcp/runs/vector/consensus_model.json'
ENV['SKP_OUT']        = 'E:/Claude/sketchup-mcp/runs/vector/planta_74.skp'

begin
  lg("UI defined? #{defined?(UI)}; Sketchup defined? #{defined?(Sketchup)}")
  if defined?(UI) && UI.respond_to?(:start_timer)
    UI.start_timer(3.0, false) do
      lg("timer fired; active_model=#{Sketchup.active_model rescue 'nil'}")
      begin
        load 'E:/Claude/sketchup-mcp/tools/consume_consensus.rb'
        lg("consume_consensus.rb load complete")
      rescue => e
        lg("consume err: #{e.class}: #{e.message}")
        e.backtrace.first(8).each { |l| lg("  #{l}") }
      end
    end
    lg("timer scheduled")
  else
    lg("UI/start_timer not available at boot")
  end
rescue => e
  lg("bootstrap err: #{e.class}: #{e.message}")
end
