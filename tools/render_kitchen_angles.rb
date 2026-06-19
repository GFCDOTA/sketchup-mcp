# render_kitchen_angles.rb — ISOLA a cozinha (esconde todo o resto -> zero oclusão) e
# tira N ângulos em CINZA (sem V-Ray/textura) pra validação de FORMA com o GPT.
# Roda: SketchUp.exe <furnished.skp> -RubyStartup render_kitchen_angles.rb
# ENV: KA_DIR (pasta de saída), KA_TAG (prefixo do nome)
require 'json'

def ka_cam(model, eye, tgt, fov, ortho_h = nil)
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

def ka_run
  model = Sketchup.active_model
  ents = model.entities
  # 1) ISOLA: esconde tudo que não é módulo da COZINHA (mata oclusão da parede/sofá)
  kbb = Geom::BoundingBox.new
  ents.grep(Sketchup::Group).each do |g|
    if g.name.to_s.include?('COZINHA')
      g.hidden = false
      kbb.add(g.bounds)
    else
      (g.hidden = true) rescue nil
    end
  end
  return unless kbb.valid?

  (model.rendering_options['Texture'] = false) rescue nil
  (model.rendering_options['DisplayColorByLayer'] = false) rescue nil
  si = model.shadow_info
  (si['DisplayShadows'] = true) rescue nil
  (si['Light'] = 78) rescue nil
  (si['Dark'] = 42) rescue nil

  c = kbb.center
  mnz = kbb.min.z
  w = kbb.max.x - kbb.min.x   # profundidade (x, frentes apontam +x)
  d = kbb.max.y - kbb.min.y   # comprimento da parede (y)
  ht = kbb.max.z - kbb.min.z
  fx = kbb.max.x              # plano das frentes
  dir = ENV['KA_DIR'] || '.'
  tag = ENV['KA_TAG'] || 'cozinha_ang'

  shots = [
    # nome,            eye,                                      target,                         fov, ortho_h
    ['01_hero_3q',  [fx + d * 0.85, c.y - d * 0.45, mnz + ht * 0.52], [c.x, c.y - d * 0.05, mnz + ht * 0.42], 52, nil],
    ['02_elevacao', [fx + d * 1.7,  c.y,            mnz + ht * 0.50], [c.x, c.y,            mnz + ht * 0.50], 40, nil],
    ['03_3q_alt',   [fx + d * 0.85, c.y + d * 0.45, mnz + ht * 0.52], [c.x, c.y + d * 0.05, mnz + ht * 0.42], 52, nil],
    ['04_dollhouse',[fx + d * 0.75, c.y - d * 0.25, kbb.max.z + ht * 0.7], [c.x, c.y, mnz + ht * 0.38], 55, nil],
    ['05_detalhe',  [fx + d * 0.42, c.y + d * 0.18, mnz + ht * 0.56], [c.x, c.y + d * 0.30, mnz + ht * 0.50], 46, nil],
    ['06_plano',    [c.x, c.y, kbb.max.z + [w, d].max * 2.0],        [c.x, c.y, mnz],                  0, [d, w].max * 1.2],
  ]
  log = []
  shots.each do |name, eye, tgt, fov, oh|
    ka_cam(model, eye, tgt, fov, oh)
    path = File.join(dir, "#{tag}_#{name}.png")
    model.active_view.write_image(filename: path, width: 1400, height: 1050, antialias: true)
    log << path
  end
  # restaura visibilidade (não deixa o .skp com tudo escondido)
  ents.grep(Sketchup::Group).each { |g| (g.hidden = false) rescue nil }
  File.write(ENV['KA_LOG'] || File.join(dir, "#{tag}_log.txt"), log.join("\n"))
end

ka_run
