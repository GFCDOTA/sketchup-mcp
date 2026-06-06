# build_furniture_skp.rb — desenha LAYOUT_BOXES (pecas de movel, com z0_in) num
# modelo LIMPO, renderiza top/front/iso enquadrados SO no movel e salva o .skp.
# Pra micro-fixtures de mobiliario parametrico (standalone, sem shell de planta).
# Rodado:  SketchUp.exe <blank_or_any.skp> -RubyStartup build_furniture_skp.rb
# Env: LAYOUT_BOXES, LAYOUT_OUT, RENDER_TOP/FRONT/ISO, LAYOUT_LOG (sinal de done).
require 'json'

def fz_material(model, name, rgb)
  m = model.materials[name]
  return m if m
  m = model.materials.add(name)
  m.color = Sketchup::Color.new(rgb[0], rgb[1], rgb[2])
  m.alpha = 1.0
  m
end

def fz_cam(model, eye, target, up)
  view = model.active_view
  cam = Sketchup::Camera.new(Geom::Point3d.new(*eye), Geom::Point3d.new(*target),
                             Geom::Vector3d.new(*up))
  cam.perspective = false
  view.camera = cam
  view.zoom_extents
end

def fz_png(model, path)
  model.active_view.write_image(filename: path, width: 1400, height: 1100,
                                antialias: true, transparent: false)
end

BEVEL_IN = 0.04 * 39.3700787402   # ~4cm de chanfro/topo inset nas almofadas

# desenha o solido; se bevel>0, faz o TOPO inset (frustum) -> almofada menos cubica
def fz_solid(ents, corners, z0, h, bevel)
  pts = corners.map { |c| Geom::Point3d.new(c[0].to_f, c[1].to_f, z0) }
  face = ents.add_face(pts)
  if bevel <= 0 || h <= bevel * 1.6
    face.pushpull(face.normal.z >= 0 ? h : -h)
    return
  end
  face.pushpull(face.normal.z >= 0 ? (h - bevel) : -(h - bevel))   # corpo ate h-bevel
  topz = z0 + h - bevel
  top = ents.grep(Sketchup::Face).find { |f| f.normal.z.abs > 0.9 && (f.bounds.center.z - topz).abs < 0.3 }
  return unless top
  bb = top.bounds
  x0, y0, x1, y1 = bb.min.x + bevel, bb.min.y + bevel, bb.max.x - bevel, bb.max.y - bevel
  return if x1 <= x0 || y1 <= y0
  ip = [[x0, y0, topz], [x1, y0, topz], [x1, y1, topz], [x0, y1, topz]].map { |p| Geom::Point3d.new(*p) }
  iface = ents.add_face(ip)        # divide o topo
  iface.pushpull(bevel)            # levanta o miolo -> topo inset/chanfrado
end

def fz_run
  boxes = JSON.parse(ENV['LAYOUT_BOXES'] || '[]')
  model = Sketchup.active_model
  model.entities.clear!   # modelo LIMPO (copia descartavel; standalone, sem shell)
  begin; model.definitions.purge_unused; model.materials.purge_unused; rescue StandardError; end
  log = []
  parent = model.active_entities.add_group
  parent.name = 'furniture'
  placed = 0
  boxes.each do |b|
    begin
      h = b['h_in'].to_f
      z0 = (b['z0_in'] || 0).to_f
      g = parent.entities.add_group
      g.name = b['label'] || b['kind']
      bevel = %w[seat_cushion back_cushion].include?(b['kind']) ? BEVEL_IN : 0.0
      fz_solid(g.entities, b['corners'] || [], z0, h, bevel)
      g.material = fz_material(model, "fz_#{b['label']}", b['rgb'] || [120, 120, 120])
      placed += 1
    rescue StandardError => e
      log << "FAIL #{b['label']}: #{e.class}: #{e.message}"
    end
  end
  log << "placed #{placed}/#{boxes.size} pecas"

  bb = parent.bounds
  c = [bb.center.x, bb.center.y, bb.center.z]
  d = bb.diagonal
  if ENV['RENDER_TOP']
    fz_cam(model, [c[0], c[1], c[2] + d * 3], c, [0, 1, 0]); fz_png(model, ENV['RENDER_TOP'])
    log << "top"
  end
  if ENV['RENDER_FRONT']   # frente = -Y: olho em -Y olhando +Y
    fz_cam(model, [c[0], c[1] - d * 3, c[2]], c, [0, 0, 1]); fz_png(model, ENV['RENDER_FRONT'])
    log << "front"
  end
  if ENV['RENDER_ISO']
    fz_cam(model, [c[0] + d * 1.4, c[1] - d * 1.5, c[2] + d * 1.2], c, [0, 0, 1])
    fz_png(model, ENV['RENDER_ISO']); log << "iso"
  end
  model.save(ENV['LAYOUT_OUT']) if ENV['LAYOUT_OUT']
  log << "saved -> #{File.basename(ENV['LAYOUT_OUT'])}" if ENV['LAYOUT_OUT']
  File.write(ENV['LAYOUT_LOG'] || 'furniture_log.txt', log.join("\n"))
end

fz_run
