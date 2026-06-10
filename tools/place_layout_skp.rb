# place_layout_skp.rb — desenha o layout VENCEDOR como PLACEHOLDERS (boxes
# coloridos extrudados) no shell da planta_74 ja aberto, renderiza before/after.
# Rodado via:  SketchUp.exe <base.skp> -RubyStartup place_layout_skp.rb
# Params via ENV:
#   LAYOUT_BOXES = JSON [{kind,x0,y0,x1,y1 (SU in),h_in,rgb:[r,g,b],label,ambiguous}]
#   LAYOUT_OUT / LAYOUT_BEFORE / LAYOUT_AFTER_TOP / LAYOUT_AFTER_ISO / LAYOUT_LOG
# Placeholders, NAO 3D Warehouse. Felipe 2026-06-04 (gate :8765 opcao A).
require 'json'

def pl_top_camera(model, bbox = nil)
  view = model.active_view
  bbox ||= model.bounds
  center = bbox.center
  eye = Geom::Point3d.new(center.x, center.y, center.z + bbox.diagonal * 5.0)
  cam = Sketchup::Camera.new(eye, center, Geom::Vector3d.new(0, 1, 0))
  cam.perspective = false
  mw = bbox.max.x - bbox.min.x
  mh = bbox.max.y - bbox.min.y
  cam.height = [mh, mw / (1600.0 / 1200.0)].max * 1.06
  view.camera = cam
end

def pl_iso_camera(model, bbox = nil)
  view = model.active_view
  custom = !bbox.nil?
  bbox ||= model.bounds
  center = bbox.center
  diag = bbox.diagonal
  d = diag * 5.0
  eye = Geom::Point3d.new(center.x + d * 0.5, center.y - d * 0.6, center.z + d * 0.7)
  cam = Sketchup::Camera.new(eye, center, Geom::Vector3d.new(0, 0, 1))
  cam.perspective = false
  cam.height = diag * 1.2
  view.camera = cam
  view.zoom_extents unless custom   # custom bbox = enquadra so o comodo, nao o apê
end

def pl_png(model, path)
  model.active_view.write_image(
    filename: path, width: 1600, height: 1200, antialias: true, transparent: false)
end

def pl_material(model, name, rgb)
  m = model.materials[name]
  return m if m
  m = model.materials.add(name)
  m.color = Sketchup::Color.new(rgb[0], rgb[1], rgb[2])
  m.alpha = 1.0
  m
end

def pl_run
  boxes = JSON.parse(ENV['LAYOUT_BOXES'] || '[]')
  model = Sketchup.active_model
  log = []

  # BEFORE: shell puro (sem moveis)
  if ENV['LAYOUT_BEFORE']
    pl_top_camera(model)
    pl_png(model, ENV['LAYOUT_BEFORE'])
    log << "BEFORE render -> #{File.basename(ENV['LAYOUT_BEFORE'])}"
  end

  parent = model.active_entities.add_group
  parent.name = 'Layout_placeholders'
  pents = parent.entities
  placed = 0
  boxes.each do |b|
    begin
      h = b['h_in'].to_f
      z0 = (b['z0_in'] || 0).to_f      # base elevada (ex.: armario aereo flutua sobre a bancada)
      g = pents.add_group
      g.name = b['label'] || b['kind']
      # desenha o POLIGONO real (cantos) na cota z0; almofadas ganham chanfro no topo
      # (Visual Quality Layer: nao parecer cubo/game asset)
      pts = (b['corners'] || []).map { |c| Geom::Point3d.new(c[0].to_f, c[1].to_f, z0) }
      bev = %w[seat_cushion back_cushion arm colchao travesseiro manta].include?(b['kind']) ? (0.04 * 39.3700787402) : 0.0
      face = g.entities.add_face(pts)
      if bev > 0 && h > bev * 1.6
        face.pushpull(face.normal.z >= 0 ? (h - bev) : -(h - bev))
        topz = z0 + h - bev
        top = g.entities.grep(Sketchup::Face).find { |f| f.normal.z.abs > 0.9 && (f.bounds.center.z - topz).abs < 0.3 }
        if top
          bb = top.bounds
          ix0, iy0, ix1, iy1 = bb.min.x + bev, bb.min.y + bev, bb.max.x - bev, bb.max.y - bev
          if ix1 > ix0 && iy1 > iy0
            th = z0 + h
            if b['kind'] == 'arm'   # braco = casca INCLINADA (frustum), sem degrau (GPT)
              bp = [[bb.min.x, bb.min.y, topz], [bb.max.x, bb.min.y, topz], [bb.max.x, bb.max.y, topz], [bb.min.x, bb.max.y, topz]].map { |p| Geom::Point3d.new(*p) }
              tp = [[ix0, iy0, th], [ix1, iy0, th], [ix1, iy1, th], [ix0, iy1, th]].map { |p| Geom::Point3d.new(*p) }
              top.erase!
              4.times { |i| j = (i + 1) % 4; begin; g.entities.add_face(bp[i], bp[j], tp[j], tp[i]); rescue StandardError; end }
              begin; g.entities.add_face(tp); rescue StandardError; end
            else                    # almofada = topo inset levantado (degrau) — GPT aprovou
              ip = [[ix0, iy0, topz], [ix1, iy0, topz], [ix1, iy1, topz], [ix0, iy1, topz]].map { |p| Geom::Point3d.new(*p) }
              g.entities.add_face(ip).pushpull(bev)
            end
          end
        end
      else
        face.pushpull(face.normal.z >= 0 ? h : -h)
      end
      mat = pl_material(model, "ph_#{b['kind']}", b['rgb'] || [120, 120, 120])
      g.material = mat
      placed += 1
      bw = (b['x1'].to_f - b['x0'].to_f).round
      bd = (b['y1'].to_f - b['y0'].to_f).round
      tag = b['ambiguous'] ? ' [TV AMBIGUOUS]' : ''
      log << "  #{b['kind']} bbox #{bw}x#{bd}x#{h.round} in#{tag}"
    rescue StandardError => e
      log << "  FAIL #{b['kind']}: #{e.class}: #{e.message}"
    end
  end
  log << "placed #{placed}/#{boxes.size} placeholders"

  # AFTER: shell + moveis. LAYOUT_ZOOM_GROUP enquadra SO o comodo mobiliado
  # (bounds do grupo de moveis + folga p/ pegar as paredes), nao o apê inteiro.
  zoom_bb = nil
  if ENV['LAYOUT_ZOOM_GROUP'] && placed > 0
    pb = parent.bounds
    zoom_bb = Geom::BoundingBox.new
    pad = 48.0   # ~1.2 m de folga
    zoom_bb.add([pb.min.x - pad, pb.min.y - pad, pb.min.z])
    zoom_bb.add([pb.max.x + pad, pb.max.y + pad, pb.max.z + pad])
  end
  if ENV['LAYOUT_AFTER_TOP']
    pl_top_camera(model, zoom_bb)
    pl_png(model, ENV['LAYOUT_AFTER_TOP'])
    log << "AFTER top -> #{File.basename(ENV['LAYOUT_AFTER_TOP'])}"
  end
  if ENV['LAYOUT_AFTER_ISO']
    pl_iso_camera(model, zoom_bb)
    pl_png(model, ENV['LAYOUT_AFTER_ISO'])
    log << "AFTER iso -> #{File.basename(ENV['LAYOUT_AFTER_ISO'])}"
  end

  if ENV['LAYOUT_OUT']
    model.save(ENV['LAYOUT_OUT'])
    log << "saved -> #{File.basename(ENV['LAYOUT_OUT'])}"
  end

  # LOG por ultimo: e o sinal de "done" pro Python
  File.write(ENV['LAYOUT_LOG'] || 'layout_place_log.txt', log.join("\n"))
end

pl_run
