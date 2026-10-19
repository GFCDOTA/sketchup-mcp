# material_review.rb — FP-038: renderiza PROOFS de material por AMBIENTE num .skp ja mobiliado.
# Para cada camera: isola o comodo (esconde grupos de OUTROS comodos + oclusores pedidos, tipo o
# vidro da sacada que lava o sofa), frameia a mobilia VISIVEL e renderiza. NAO salva o .skp (so
# renderiza; restaura a visibilidade entre cameras). Rodado:
#   SketchUp.exe <furnished_copy.skp> -RubyStartup material_review.rb
# ENV: MR_CAMERAS (JSON [{name,match,out,mode,hide:[prefixos]}]), MR_LOG (sinal done), MR_DEFER (s).
require 'json'

# grupos do SHELL (paredes/piso/portas/janelas/vidro) — distinto dos moveis ("#{room} · #{module}").
MR_SHELL_PREFIXES = %w[PlanShell Floor_Group DoorLeaf Window GlazedBalcony
                       SoftBarrier PassageMarker].freeze

def mr_set_visibility(groups, match, exclude)
  # PROOF DE MATERIAL, nao de arquitetura: esconde TODO o shell (parede/piso/vidro) -> sem oclusao
  # de parede lavando o movel. Mostra so os moveis do comodo-alvo (nome contem `match`), menos os
  # modulos em `exclude` (movel alto/distante que encolhe o alvo). Devolve os grupos VISIVEIS.
  m = match.to_s.upcase
  ex = (exclude || []).map { |e| e.to_s.upcase }
  shown = []
  groups.each do |g|
    nm = g.name.to_s
    if MR_SHELL_PREFIXES.any? { |p| nm.start_with?(p) }
      g.hidden = true
    else
      keep = nm.upcase.include?(m) && ex.none? { |e| nm.upcase.include?(e) }
      g.hidden = !keep
      shown << g if keep
    end
  end
  shown
end

def mr_camera(view, shown, mode)
  # angulo iso (ou mais fechado no closeup) + zoom SO nos moveis visiveis (ignora o shell) => o
  # material preenche o frame sem depender da granularidade do piso.
  bb = Geom::BoundingBox.new
  shown.each { |g| (bb.add(g.bounds) rescue nil) }
  return unless bb.valid?
  c = bb.center
  d = bb.diagonal
  close = (mode.to_s == 'closeup')
  eye = Geom::Point3d.new(c.x + d * (close ? 0.30 : 0.60),
                          c.y - d * (close ? 0.35 : 0.70),
                          c.z + d * (close ? 0.28 : 0.55))
  cam = Sketchup::Camera.new(eye, c, Geom::Vector3d.new(0, 0, 1))
  cam.perspective = true
  cam.fov = close ? 42.0 : 52.0
  view.camera = cam
  (view.zoom(shown) rescue nil)   # enquadra os moveis visiveis mantendo a direcao da camera
end

def mr_run
  model = Sketchup.active_model
  view = model.active_view
  log = []
  cams = (JSON.parse(ENV['MR_CAMERAS'] || '[]') rescue [])
  groups = model.entities.grep(Sketchup::Group)
  cams.each do |cam|
    begin
      shown = mr_set_visibility(groups, cam['match'], cam['exclude'] || [])
      mr_camera(view, shown, cam['mode'])
      out = cam['out']
      view.write_image(filename: out, width: 1600, height: 1200,
                       antialias: true, transparent: false)
      log << "#{cam['name']}: #{shown.size} moveis visiveis -> #{File.basename(out.to_s)}"
    rescue StandardError => e
      log << "#{cam['name']} FAIL: #{e.class}: #{e.message}"
    ensure
      groups.each { |g| (g.hidden = false) rescue nil }   # restaura p/ a proxima camera
    end
  end
  log << "DONE #{cams.size} cameras (skp NAO salvo)"
  File.write(ENV['MR_LOG'] || 'mr_log.txt', log.join("\n"))
end

UI.start_timer((ENV['MR_DEFER'] || '8').to_f, false) { mr_run }
