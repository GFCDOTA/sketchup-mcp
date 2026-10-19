# render_sala_eyelevel.rb — renderiza a SALA em CINZA (sem V-Ray/textura) em escala HUMANA
# (eye-level) p/ validar FORMA/proporcao/ancoragem/circulacao ANTES de aplicar estetica.
# NAO isola (paredes ficam visiveis -> da pra ver o rack ancorado). Acha os moveis pelo nome
# e posiciona as cameras no eixo sofa<->rack e na zona de jantar.
# ENV: KA_DIR (saida), KA_TAG (prefixo), KA_LOG.
require 'json'

def sl_cam(model, eye, tgt, fov, ortho_h = nil)
  cam = Sketchup::Camera.new(Geom::Point3d.new(*eye), Geom::Point3d.new(*tgt),
                             Geom::Vector3d.new(0, 0, 1))
  if ortho_h
    cam.perspective = false
    cam.height = ortho_h
  else
    cam.perspective = true
    cam.fov = fov
  end
  model.active_view.camera = cam
end

def sl_run
  model = Sketchup.active_model
  ents = model.entities
  centers = {}
  sala_bb = Geom::BoundingBox.new
  ents.grep(Sketchup::Group).each do |g|
    nm = g.name.to_s
    sala_bb.add(g.bounds) if nm.include?('SALA')
    [['Sofa', 'Sofa'], ['Rack', 'Rack'], ['Mesa de jantar', 'jantar'],
     ['Mesa de centro', 'centro']].each do |key, sub|
      centers[key] = g.bounds.center if nm.include?(sub) && nm.include?('SALA') && !centers[key]
    end
  end
  return unless sala_bb.valid?

  (model.rendering_options['Texture'] = false) rescue nil
  (model.rendering_options['DisplayColorByLayer'] = false) rescue nil
  si = model.shadow_info
  (si['DisplayShadows'] = true) rescue nil
  (si['Light'] = 80) rescue nil
  (si['Dark'] = 45) rescue nil

  c = sala_bb.center
  mnz = sala_bb.min.z
  bigd = [sala_bb.max.x - sala_bb.min.x, sala_bb.max.y - sala_bb.min.y].max
  sofa = centers['Sofa'] || c
  rack = centers['Rack'] || c
  din = centers['Mesa de jantar'] || c
  eyeh = mnz + 58.0      # ~1.47m

  ax = rack.x - sofa.x
  ay = rack.y - sofa.y
  al = Math.sqrt(ax * ax + ay * ay)
  al = 1.0 if al < 1e-6
  ax /= al
  ay /= al

  dir = ENV['KA_DIR'] || '.'
  tag = ENV['KA_TAG'] || 'sala_eye'
  shots = [
    # sofa -> TV: acima/atras do sofa olhando o rack (over-the-sofa)
    ['01_sofa_to_tv', [sofa.x - ax * 14, sofa.y - ay * 14, mnz + 64], [rack.x, rack.y, mnz + 22], 62, nil],
    # TV -> sofa: NA FRENTE do rack (lado do room), olhando p/ o sofa (-eixo). NAO entrar na parede.
    ['02_tv_to_sofa', [rack.x - ax * 10, rack.y - ay * 10, mnz + 60], [sofa.x, sofa.y, mnz + 24], 64, nil],
    # jantar 3/4: olhando a mesa + cadeiras
    ['03_jantar', [din.x - 52, din.y - 52, eyeh], [din.x, din.y, mnz + 16], 58, nil],
    # dollhouse: BEM acima das paredes (clear) + offset diagonal pequeno, olhando p/ baixo no centro
    ['04_dollhouse', [c.x - bigd * 0.28, c.y - bigd * 0.28, sala_bb.max.z + bigd * 1.05], [c.x, c.y, mnz], 46, nil],
    # plano (top ortho) — integracao sala/jantar/aberturas
    ['05_plano', [c.x, c.y, sala_bb.max.z + bigd * 2.0], [c.x, c.y, mnz], 0, bigd * 1.15],
  ]
  log = []
  shots.each do |name, eye, tgt, fov, oh|
    sl_cam(model, eye, tgt, fov, oh)
    path = File.join(dir, "#{tag}_#{name}.png")
    model.active_view.write_image(filename: path, width: 1240, height: 930, antialias: true)
    log << path
  end
  File.write(ENV['KA_LOG'] || File.join(dir, "#{tag}_log.txt"),
             "centers=#{centers.keys.join(',')}\n" + log.join("\n"))
end

sl_run
