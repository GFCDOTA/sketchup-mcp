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

def pl_material(model, name, rgb, tex_path = nil, tile = 40)
  m = model.materials[name]
  return m if m
  m = model.materials.add(name)
  m.color = Sketchup::Color.new(rgb[0], rgb[1], rgb[2])
  m.alpha = 1.0
  # A CORRECAO DO BUG (FP-036): o path HUMANO/interativo tambem aplica textura por kind, nao so
  # o V-Ray. Sem png (ou arquivo ausente) -> cor chapada = comportamento anterior (fallback seguro).
  if tex_path && File.exist?(tex_path)
    begin
      m.texture = tex_path
      m.texture.size = [tile, tile] if m.texture   # tamanho fisico do tile em polegadas
    rescue StandardError
      # textura falhou -> fica so na cor solida (nao aborta a peca)
    end
  end
  m
end

def pl_run
  boxes = JSON.parse(ENV['LAYOUT_BOXES'] || '[]')
  model = Sketchup.active_model
  log = []

  # FP-036: mapa de textura por KIND (de style_spec.texture_map_for), injetado pelo Python.
  # kind = FONTE UNICA -> cada ph_<kind> recebe SO a textura do seu kind (nunca a 1a peca em tudo).
  tex_map = (JSON.parse(ENV['LAYOUT_TEX_MAP'] || '{}') rescue {})    # kind -> png
  tile_map = (JSON.parse(ENV['LAYOUT_TILE_MAP'] || '{}') rescue {})  # kind -> tile_in (de tile_map_for)
  tex_dir = ENV['LAYOUT_TEX_DIR']
  tex_logged = {}    # dedup do log por kind (inclui MISS)
  tex_applied = {}   # so os kinds que REALMENTE receberam textura (File.exist? true)

  # BEFORE: shell puro (sem moveis)
  if ENV['LAYOUT_BEFORE']
    pl_top_camera(model)
    pl_png(model, ENV['LAYOUT_BEFORE'])
    log << "BEFORE render -> #{File.basename(ENV['LAYOUT_BEFORE'])}"
  end

  ents = model.active_entities
  # EDITABILIDADE (Felipe 2026-06-18): cada MOVEL = um GRUPO TOP-LEVEL nomeado, pra
  # clique UNICO selecionar SO aquele movel (nao o apê todo). Organizacao por COMODO
  # via TAG/Layer (Outliner mostra; nao aninha a selecao). Nada de mega-grupo 'Mobilia'.
  mod_groups = {}
  furn_bb = Geom::BoundingBox.new
  placed = 0
  boxes.each do |b|
    begin
      h = b['h_in'].to_f
      z0 = (b['z0_in'] || 0).to_f      # base elevada (ex.: armario aereo flutua sobre a bancada)
      room = (b['room'] || 'Apto').to_s
      mod  = (b['module'] || b['kind'] || 'Movel').to_s
      mkey = "#{room}|#{mod}"
      tag = (model.layers[room] || model.layers.add(room))
      mg = mod_groups[mkey]
      if mg.nil?
        mg = ents.add_group            # MOVEL = grupo top-level (selecionavel sozinho)
        mg.name = "#{room} · #{mod}"
        mg.layer = tag
        mod_groups[mkey] = mg
      end
      g = mg.entities.add_group        # a peca, DENTRO do movel
      g.name = b['label'] || b['kind']
      # PERFIL: peca com face 3D no mundo + vetor de extrusao (place_sofa_boxes) ->
      # desenha as CURVAS reais (coroamento/arredondado) em vez de caixa. Padrao p/
      # QUALQUER peca com profile (sofa hoje; qualquer movel refinado no futuro).
      if (pw_face = b['profile_world'])
        ppts = pw_face.map { |c| Geom::Point3d.new(c[0].to_f, c[1].to_f, c[2].to_f) }
        pface = g.entities.add_face(ppts)
        if pface
          ev = b['extrude_vec'] || [0, 0, 0]
          pvec = Geom::Vector3d.new(ev[0].to_f, ev[1].to_f, ev[2].to_f)
          d = pvec.dot(pface.normal)
          pface.pushpull(d.abs < 1e-6 ? pvec.length : d)
        end
        # suaviza as arestas do perfil: sem isto as facetas do coroamento viram
        # 'ranhuras' e o sofa parece faceteado/rugoso, nao curvo liso (regra do harness).
        g.entities.grep(Sketchup::Edge).each do |e|
          if e.faces.length == 2 && e.faces[0].normal.angle_between(e.faces[1].normal) < 0.45
            e.soft = true
            e.smooth = true
          end
        end
      else
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
      end   # fecha o if (pw_face = b['profile_world'])
      kind = b['kind']
      # FP-037: prefere o material JA RESOLVIDO por (familia,kind) no Python (mat_name/tex_png/
      # tile_in) — assim rack.base=madeira e sofa.base=grafite viram materiais SEPARADOS. Sem os
      # campos (ex. slice sem attach) cai no fallback FP-036 por kind (tex_map[kind]).
      mat_name = b['mat_name'] || "ph_#{kind}"
      png = b.key?('tex_png') ? b['tex_png'] : tex_map[kind]
      tile = (b['tile_in'] || tile_map[kind] || 40).to_f
      tex_path = (png && tex_dir) ? File.join(tex_dir, png) : nil
      if png && tex_dir && !tex_logged[mat_name]                 # log por material (invariante auditavel)
        tex_logged[mat_name] = true
        if File.exist?(tex_path)
          tex_applied[mat_name] = true                           # so conta o que de fato texturizou
          log << "  tex #{mat_name} <- #{png} (tile #{tile.round})"
        else
          log << "  tex MISS #{mat_name}: #{png} ausente -> cor chapada"
        end
      end
      mat = pl_material(model, mat_name, b['rgb'] || [120, 120, 120], tex_path, tile)
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
  log << "texturas aplicadas: #{tex_applied.size} kind(s) via LAYOUT_TEX_MAP"
  log << "MOVEIS (comodo | movel): #{mod_groups.keys.sort.join(' ; ')}"
  mod_groups.each_value { |mg| (furn_bb.add(mg.bounds) rescue nil) }
  # TRAVA o shell (paredes/piso/portas/janelas) — mover/editar movel NAO atrapalha a base
  nlock = 0
  ents.grep(Sketchup::Group).each do |gp|
    nm = gp.name.to_s
    if %w[PlanShell Floor_Group DoorLeaf Window GlazedBalcony SoftBarrier PassageMarker].any? { |p| nm.start_with?(p) }
      (gp.locked = true; nlock += 1) rescue nil
    end
  end
  log << "shell travado: #{nlock} grupos (paredes/piso/portas)"

  # AFTER: shell + moveis. LAYOUT_ZOOM_GROUP enquadra SO o comodo mobiliado
  # (bounds do grupo de moveis + folga p/ pegar as paredes), nao o apê inteiro.
  zoom_bb = nil
  if ENV['LAYOUT_ZOOM_GROUP'] && placed > 0
    pb = furn_bb
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
