# furnish_plan.rb — insere componentes de mobilia (.skp do 3D Warehouse) num
# modelo de planta ja pronto e salva variantes (planta_74_vN.skp) + renders.
# Rodado via:  SketchUp.exe <base.skp> -RubyStartup furnish_plan.rb
# Params via ENV FURNISH_JOBS = JSON [{component,out,cx,cy,rot,scale,name}, ...]
#   cx,cy = posicao do CENTRO do movel no plano, em SU inches (chao em z=0).
# Felipe 2026-06-04: gerar plantas mobiliadas com sofas diferentes pra escolher.
require 'json'

def fp_setup_iso_camera(model)
  view = model.active_view
  bbox = model.bounds
  center = bbox.center
  diag = bbox.diagonal
  d = diag * 5.0
  eye = Geom::Point3d.new(center.x + d * 0.5, center.y - d * 0.6, center.z + d * 0.7)
  cam = Sketchup::Camera.new(eye, center, Geom::Vector3d.new(0, 0, 1))
  cam.perspective = false
  cam.height = diag * 1.2
  view.camera = cam
  view.zoom_extents
end

def fp_setup_top_camera(model)
  view = model.active_view
  bbox = model.bounds
  center = bbox.center
  diag = bbox.diagonal
  eye = Geom::Point3d.new(center.x, center.y, center.z + diag * 5.0)
  cam = Sketchup::Camera.new(eye, center, Geom::Vector3d.new(0, 1, 0))
  cam.perspective = false
  mw = bbox.max.x - bbox.min.x
  mh = bbox.max.y - bbox.min.y
  cam.height = [mh, mw / (1600.0 / 1200.0)].max * 1.06
  view.camera = cam
end

def fp_write_png(model, path)
  model.active_view.write_image(
    filename: path, width: 1600, height: 1200, antialias: true, transparent: false,
  )
end

def fp_run
  jobs = JSON.parse(ENV['FURNISH_JOBS'] || '[]')
  model = Sketchup.active_model
  log = []
  placements = []
  jobs.each do |job|
    out = job['out']
    begin
      defn = model.definitions.load(job['component'])
      bb = defn.bounds
      cx = job['cx'].to_f
      cy = job['cy'].to_f
      rot = (job['rot'] || 0).to_f
      scale = (job['scale'] || 1.0).to_f
      # AUTO-ESCALA: varios componentes do 3DW vem em escala errada (miniatura
      # ou gigante). Normaliza pela ALTURA (Z) -> alvo ~0.80 m (altura tipica de
      # sofa) quando fora de [0.55, 1.25] m. Felipe 2026-06-04: validar escala.
      hz_m = bb.depth.to_f / 39.37
      autoscaled = false
      if scale == 1.0 && (hz_m < 0.55 || hz_m > 1.25)
        scale = (0.80 * 39.37) / bb.depth.to_f
        autoscaled = true
      end
      # centro XY do movel -> (cx,cy); base Z -> 0 (chao); depois escala+gira
      to_origin = Geom::Transformation.translation(
        Geom::Vector3d.new(-bb.center.x, -bb.center.y, -bb.min.z))
      place  = Geom::Transformation.translation(Geom::Point3d.new(cx, cy, 0.0))
      rotate = Geom::Transformation.rotation(
        Geom::Point3d.new(0, 0, 0), Geom::Vector3d.new(0, 0, 1), rot.degrees)
      scaler = Geom::Transformation.scaling(scale)
      trans = place * rotate * scaler * to_origin
      inst = model.active_entities.add_instance(defn, trans)
      inst.name = job['name'] || 'furniture'

      model.save(out)
      iso = out.sub(/\.skp\z/i, '_iso.png')
      top = out.sub(/\.skp\z/i, '_top.png')
      fp_setup_iso_camera(model); fp_write_png(model, iso)
      fp_setup_top_camera(model); fp_write_png(model, top)

      # dimensoes FINAIS (ja escaladas), em metros
      fw = (bb.width.to_f  * scale / 39.37).round(3)
      fd = (bb.height.to_f * scale / 39.37).round(3)
      fh = (bb.depth.to_f  * scale / 39.37).round(3)
      tag = autoscaled ? " AUTO-SCALE x#{scale.round(2)} (orig alt #{hz_m.round(2)}m)" : ""
      log << "OK #{out} | #{defn.name} | final #{fw}x#{fd}x#{fh} m#{tag}"
      placements << {
        'out' => File.basename(out), 'name' => (job['name'] || 'furniture'),
        'w_m' => fw, 'd_m' => fd, 'h_m' => fh,
        'cx_in' => cx, 'cy_in' => cy, 'scale' => scale.round(3),
        'autoscaled' => autoscaled,
      }
      inst.erase!
      model.definitions.purge_unused
    rescue StandardError => e
      log << "FAIL #{out}: #{e.class}: #{e.message}"
    end
  end
  File.write(ENV['FURNISH_LOG'] || 'furnish_log.txt', log.join("\n"))
  if ENV['FURNISH_PLACEMENTS']
    File.write(ENV['FURNISH_PLACEMENTS'], JSON.generate(placements))
  end
end

fp_run
