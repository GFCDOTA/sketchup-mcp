# validate.rb
# Post-build sanity check for the .skp produced by main.rb.
#
# Not a replacement for a full integration test — just quick checks:
#
#   - output file exists and is > 10 KB
#   - Sketchup.active_model has at least 10 entities
#   - entity class counts are reported for debugging
#
# Invoked automatically by main.rb after a successful build. Exits with
# a non-zero status if the basic checks fail so the Python side sees
# the failure through the subprocess exit code.

module SkpExport
  module Validate
    MIN_FILE_SIZE_BYTES = 10_000
    MIN_ENTITY_COUNT    = 10

    def self.run(run_dir:, output_name: "plant.skp")
      output_path = File.join(run_dir, output_name)

      ok = true
      unless File.exist?(output_path)
        warn("[skp_export.validate] ERROR: output file missing: #{output_path}")
        ok = false
      else
        size = File.size(output_path)
        if size < MIN_FILE_SIZE_BYTES
          warn("[skp_export.validate] ERROR: output file too small (#{size} B): #{output_path}")
          ok = false
        else
          warn("[skp_export.validate] OK file size=#{size}B path=#{output_path}")
        end
      end

      if defined?(Sketchup) && Sketchup.active_model
        ents = Sketchup.active_model.entities
        count = ents.count
        classes = count_entity_classes(ents)
        warn("[skp_export.validate] entities=#{count} classes=#{classes.inspect}")
        if count < MIN_ENTITY_COUNT
          warn("[skp_export.validate] ERROR: too few entities (#{count} < #{MIN_ENTITY_COUNT})")
          ok = false
        end
      end

      exit(1) unless ok
      true
    end

    def self.count_entity_classes(entities)
      counts = Hash.new(0)
      entities.each do |ent|
        counts[ent.class.name] += 1
      end
      counts
    end
  end
end
