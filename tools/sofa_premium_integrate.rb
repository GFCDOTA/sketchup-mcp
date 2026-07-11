# sofa_premium_integrate.rb — FP-SOFA-PREMIUM item 4: substitui o modulo Sofa
# da planta mobiliada pelo sofa premium (mesma gramatica aprovada alt_001-006,
# re-emitida parametricamente na largura do slot da planta — LP-SOFA-001:
# footprint vem da planta). Abre a copia do furnished, apaga o grupo do modulo
# antigo, constroi o premium no mesmo centro/rotacao, salva e renderiza.
#
# Env: SOFA_INT_JSON (parts em m), SOFA_INT_PLACEMENT (center_in+theta),
#      SOFA_INT_OUT (.skp), SOFA_INT_PNG (prefixo), SOFA_INT_LOG, SOFA_INT_ALT006.
require "json"

M_TO_IN = 39.3700787402
ALT006_R_M = 0.025

def log_line(msg)
  path = ENV["SOFA_INT_LOG"]
  return unless path
  File.open(path, "a") { |f| f.puts("#{Time.now.strftime('%H:%M:%S')} #{msg}") }
end

def pts3(arr)
  arr.map { |x, y, z| Geom::Point3d.new(x * M_TO_IN, y * M_TO_IN, z * M_TO_IN) }
end

def build_part(ents, part)
  g = ents.add_group
  g.name = part["label"]
  ge = g.entities
  if (prof = part["profile_xz"])
    y0 = part["y0"]
    face = ge.add_face(pts3(prof.map { |x, z| [x, y0, z] }))
    return g if face.nil?
    depth = (part["y1"] - part["y0"]) * M_TO_IN
    face.pushpull(face.normal.y > 0 ? depth : -depth)
  elsif (prof = part["profile_yz"])
    x0 = part["x0"]
    face = ge.add_face(pts3(prof.map { |y, z| [x0, y, z] }))
    return g if face.nil?
    depth = (part["x1"] - part["x0"]) * M_TO_IN
    face.pushpull(face.normal.x > 0 ? depth : -depth)
  else
    x0, y0, x1, y1 = part.values_at("x0", "y0", "x1", "y1")
    z0, z1 = part["z0"], part["z1"]
    face = ge.add_face(pts3([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]]))
    return g if face.nil?
    h = (z1 - z0) * M_TO_IN
    face.pushpull(face.normal.z > 0 ? h : -h)
    g.transform!(Geom::Transformation.translation(Geom::Vector3d.new(0, 0, z0 * M_TO_IN))) if z0.abs > 1e-9
  end
  # cor do tecido/pecas (a planta e' colorida — usa o rgb da part)
  if (rgb = part["rgb"])
    mat = Sketchup.active_model.materials.add("sofa_premium_#{part['label']}")
    mat.color = Sketchup::Color.new(*rgb)
    g.entities.grep(Sketchup::Face).each { |f| f.material = mat; f.back_material = mat }
  end
  g
end

def rounded_front_plan_cutter(ents, part, r_m)
  x0, y0, x1, y1 = part.values_at("x0", "y0", "x1", "y1")
  z0, z1 = part["z0"], part["z1"]
  r = [r_m, (x1 - x0) / 2.0 - 1e-4, (y1 - y0) / 2.0 - 1e-4].min
  pts = []
  seg = 6
  pts << [x0, y1]
  pts << [x0, y0 + r]
  seg.times do |i|
    a = Math::PI + (Math::PI / 2.0) * (i + 1) / seg
    pts << [x0 + r + r * Math.cos(a), y0 + r + r * Math.sin(a)]
  end
  pts << [x1 - r, y0]
  seg.times do |i|
    a = 1.5 * Math::PI + (Math::PI / 2.0) * (i + 1) / seg
    pts << [x1 - r + r * Math.cos(a), y0 + r + r * Math.sin(a)]
  end
  pts << [x1, y1]
  g = ents.add_group
  face = g.entities.add_face(pts3(pts.map { |x, y| [x, y, z0 - 0.01] }))
  return nil if face.nil?
  h = (z1 - z0 + 0.02) * M_TO_IN
  face.pushpull(face.normal.z > 0 ? h : -h)
  g
end

def render_cam(model, eye, target, png, w, h, fov = 55.0)
  dir = eye.vector_to(target)
  up = dir.parallel?(Geom::Vector3d.new(0, 0, 1)) ? Geom::Vector3d.new(0, 1, 0) : Geom::Vector3d.new(0, 0, 1)
  cam = Sketchup::Camera.new(eye, target, up)
  cam.perspective = true
  cam.fov = fov
  model.active_view.camera = cam
  model.active_view.write_image(filename: png, width: w, height: h,
                                antialias: true, transparent: false)
end

begin
  model = Sketchup.active_model
  placement = JSON.parse(File.read(ENV["SOFA_INT_PLACEMENT"]))
  cx_in, cy_in = placement["center_in"]
  theta = placement["theta_deg"] * Math::PI / 180.0

  # 1. apaga o modulo Sofa antigo (grupo "SALA ... · Sofa" do place_layout)
  victims = model.entities.grep(Sketchup::Group).select { |g| g.name.to_s =~ /·\s*Sofa\s*\z/ }
  log_line("modulos Sofa encontrados: #{victims.length} (#{victims.map(&:name).join(' | ')})")
  model.start_operation("sofa_premium_integrate", true)
  victims.each(&:erase!)

  # 2. constroi o premium num wrapper local e transforma pro lugar
  parts = JSON.parse(File.read(ENV["SOFA_INT_JSON"]))
  wrap = model.entities.add_group
  wrap.name = "SALA DE JANTAR | SALA DE ESTAR · Sofa (premium)"
  arm_groups = {}
  parts.each do |part|
    g = build_part(wrap.entities, part)
    arm_groups[part["label"]] = { "g" => g, "part" => part } if part["kind"] == "arm"
  end
  if ENV["SOFA_INT_ALT006"] == "1"
    arm_groups.each_value do |h|
      cutter = rounded_front_plan_cutter(wrap.entities, h["part"], ALT006_R_M)
      next if cutter.nil?
      begin
        res = h["g"].intersect(cutter)
        if res
          res.name = h["part"]["label"]
        else
          cutter.erase!
        end
      rescue => e
        cutter.erase! rescue nil
        log_line("alt006 exception #{e.message}")
      end
    end
    wrap.entities.grep(Sketchup::Group).each do |g|
      g.entities.grep(Sketchup::Edge).each do |e|
        e.soft = e.smooth = true if e.faces.length == 2 &&
                                    e.faces[0].normal.angle_between(e.faces[1].normal) < 0.45
      end
    end
  end
  # centraliza a origem local e leva pro centro/rotacao do slot
  w_in = parts.map { |p| p["x1"] }.max * M_TO_IN
  d_in = parts.map { |p| p["y1"] }.max * M_TO_IN
  t = Geom::Transformation.translation(Geom::Vector3d.new(cx_in, cy_in, 0)) *
      Geom::Transformation.rotation(Geom::Point3d.new(0, 0, 0), Geom::Vector3d.new(0, 0, 1), theta) *
      Geom::Transformation.translation(Geom::Vector3d.new(-w_in / 2.0, -d_in / 2.0, 0))
  wrap.transform!(t)
  model.commit_operation
  log_line("premium colocado em (#{cx_in.round(1)}, #{cy_in.round(1)}) theta=#{placement['theta_deg']}")

  out = ENV["SOFA_INT_OUT"]
  model.save(out)
  log_line("skp salvo #{out}")

  prefix = ENV["SOFA_INT_PNG"]
  cin = Geom::Point3d.new(cx_in, cy_in, 0)
  # top zenital da sala
  render_cam(model, Geom::Point3d.new(cx_in, cy_in, 500), Geom::Point3d.new(cx_in, cy_in + 0.001, 0),
             "#{prefix}_sala_top.png", 1400, 1000, 40.0)
  # eye-level via auto_camera (sightline limpa computada, 0 oclusores)
  if (ec = placement["eyelevel"])
    eye = Geom::Point3d.new(*ec["eye"])
    tgt = Geom::Point3d.new(*ec["target"])
    render_cam(model, eye, tgt, "#{prefix}_sala_eyelevel.png", 1400, 1000,
               ec["fov"] || 60.0)
  end
  # iso 3/4 da sala (acima do pe-direito, olhando pra baixo)
  eye2 = Geom::Point3d.new(cx_in + 150, cy_in + 100, 4.4 * M_TO_IN)
  render_cam(model, eye2, Geom::Point3d.new(cx_in, cy_in, 0.4 * M_TO_IN),
             "#{prefix}_sala_iso.png", 1400, 1000, 45.0)
  log_line("DONE")
rescue => e
  log_line("FATAL #{e.class}: #{e.message}\n#{e.backtrace.first(5).join("\n")}")
end
