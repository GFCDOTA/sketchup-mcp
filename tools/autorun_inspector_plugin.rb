# Auto-fire inspector on SU startup. Heavy logging to disk so we can
# see what step (if any) is failing.
ctrl = File.join(File.dirname(__FILE__), 'autorun_inspector_control.txt')
errp = File.join(File.dirname(__FILE__), 'autorun_inspector_error.txt')
logp = File.join(File.dirname(__FILE__), 'autorun_inspector_log.txt')

def lg(p, m)
  File.open(p, 'a') { |f| f.puts("[#{Time.now.strftime('%H:%M:%S')}] #{m}") } rescue nil
end

File.delete(logp) rescue nil
lg(logp, "plugin file evaluated; ctrl exist? #{File.exist?(ctrl)}")

if File.exist?(ctrl)
  begin
    cfg = File.read(ctrl).strip.split("\n").map(&:strip)
    lg(logp, "control file lines=#{cfg.length}: #{cfg.inspect}")
    if cfg.length >= 3
      ENV['INSPECT_SKP']    = cfg[0]
      ENV['INSPECT_REPORT'] = cfg[1]
      script                = cfg[2]
      lg(logp, "envs set; scheduling timer")
      UI.start_timer(5.0, false) do
        lg(logp, "timer fired; active_model=#{(Sketchup.active_model rescue 'nil').inspect}")
        begin
          load script
          lg(logp, "load returned ok")
        rescue Exception => e
          msg = "load #{script} failed: #{e.class}: #{e.message}\n#{e.backtrace.first(30).join("\n")}"
          File.write(errp, msg)
          lg(logp, "load raised: #{e.class}: #{e.message}")
        end
      end
      lg(logp, "timer scheduled (5.0s)")
    else
      File.write(errp, "control file has #{cfg.length} lines, need >=3")
      lg(logp, "control file too short")
    end
  rescue => e
    File.write(errp, "bootstrap: #{e.class}: #{e.message}")
    lg(logp, "bootstrap raised: #{e.class}: #{e.message}")
  end
else
  lg(logp, "no control file")
end
