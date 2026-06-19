# skp_editability_report.rb — PROVA de editabilidade de um .skp mobiliado.
# Lê a hierarquia REAL (não a imagem): geometria solta no root, grupos top-level
# nomeados (Outliner), seleção isolada de cada módulo exigido, shell locked.
# Roda:  SketchUp.exe <furnished.skp> -RubyStartup skp_editability_report.rb
# ENV: KP_REPORT (txt de saída), KP_PNG (close-up cinza opcional), KP_WANT (csv de needles)
require 'json'

def kp_leafcount(e)
  return 0 unless e.respond_to?(:entities)
  e.entities.grep(Sketchup::Group).size + e.entities.grep(Sketchup::ComponentInstance).size +
    e.entities.grep(Sketchup::Face).size
end

def kp_run
  model = Sketchup.active_model
  ents = model.entities
  rep = []

  # 1) ROOT — não pode ter geometria solta
  loose = ents.grep(Sketchup::Face).size + ents.grep(Sketchup::Edge).size
  groups = ents.grep(Sketchup::Group)
  comps  = ents.grep(Sketchup::ComponentInstance)
  rep << "=== 1) ROOT (model.entities) ==="
  rep << "  geometria SOLTA no root (faces+edges): #{loose}   -> #{loose.zero? ? 'PASS (zero)' : 'FAIL'}"
  rep << "  grupos top-level: #{groups.size}  |  componentes top-level: #{comps.size}"
  rep << ""

  # 2) HIERARQUIA NOMEADA (o que o Outliner mostra)
  rows = []
  groups.each { |g| rows << [g.name.to_s, g.locked?, (g.layer.name rescue ''), kp_leafcount(g), g] }
  comps.each  { |c| rows << [(c.name.empty? ? c.definition.name : c.name).to_s, c.locked?, (c.layer.name rescue ''), kp_leafcount(c), c] }
  rep << "=== 2) HIERARQUIA NOMEADA (Outliner) — #{rows.size} nós top-level ==="
  rows.sort_by { |r| [r[2], r[0]] }.each do |nm, lk, tag, lf, _|
    rep << sprintf("  %-32s  locked=%-5s  tag=%-10s  sub=%d", nm, lk, (tag.empty? ? '-' : tag), lf)
  end
  rep << ""

  # 3) GATE — cada módulo exigido = 1 grupo selecionável sozinho (sem parede/piso/outro móvel)
  want = (ENV['KP_WANT'] || 'fridge,sink_module,cooktop_module,countertop,upper_cabinet,base_cabinet,DoorLeaf').split(',')
  labels = {'fridge'=>'fridge','sink_module'=>'sink_module','cooktop_module'=>'cooktop_module',
            'countertop'=>'countertop','upper_cabinet'=>'upper_cabinet_01','base_cabinet'=>'base_cabinet_01','DoorLeaf'=>'door_kitchen'}
  rep << "=== 3) GATE — seleção isolada por módulo ==="
  npass = 0
  want.each do |needle|
    hits = rows.select { |r| r[0].downcase.include?(needle.downcase) }
    lab = labels[needle] || needle
    if hits.empty?
      rep << "  [FAIL] #{lab}: AUSENTE (nenhum grupo casa '#{needle}')"
    else
      # selecionar 1 grupo isoladamente pega só ele (grupo top-level ⇒ clique único = só este nó)
      tot = hits.sum { |h| h[3] }
      rep << "  [PASS] #{lab}: #{hits.size} grupo(s) '#{hits.map { |h| h[0] }.join("', '")}'  (#{tot} sub-peças no total, 0 paredes)"
      npass += 1
    end
  end
  rep << "  -> #{npass}/#{want.size} módulos exigidos presentes e isolados"
  rep << ""

  # 4) SHELL — paredes/piso/portas/janelas em grupos próprios E locked
  shell = rows.select { |r| r[0].match?(/PlanShell|Floor|DoorLeaf|Window|Glazed|Barrier|Passage|Wall/i) }
  locked = shell.count { |r| r[1] }
  rep << "=== 4) SHELL travado ==="
  shell.each { |nm, lk, _, _, _| rep << "  #{nm}: locked=#{lk}#{lk ? '' : '   <-- NAO TRAVADO'}" }
  rep << "  -> shell #{shell.size} grupos | travados #{locked}  #{locked == shell.size && shell.size > 0 ? 'PASS' : 'CHECAR'}"
  rep << ""

  # 5) close-up CINZA da cozinha (sombras on p/ revelar reveals entre módulos; sem V-Ray/textura)
  if ENV['KP_PNG']
    kbb = Geom::BoundingBox.new
    groups.each { |g| kbb.add(g.bounds) if g.name.to_s.include?('COZINHA') }
    if kbb.valid?
      (model.rendering_options['Texture'] = false) rescue nil
      (model.rendering_options['DisplayColorByLayer'] = false) rescue nil
      si = model.shadow_info
      (si['DisplayShadows'] = true) rescue nil
      (si['Light'] = 70) rescue nil
      (si['Dark'] = 50) rescue nil
      c = kbb.center
      w = kbb.max.x - kbb.min.x; d = kbb.max.y - kbb.min.y; ht = kbb.max.z - kbb.min.z
      # As FRENTES da cozinha abrem pro lado livre (-y, onde está o cômodo, sem parede).
      # Câmera CENTRADA em x (NÃO ofsetar -> não atravessa a parede lateral), à frente e
      # um pouco acima, olhando pras frentes. KP_FRONT_SGN=+1 inverte se a parede for -y.
      sgn = (ENV['KP_FRONT_SGN'] || '-1').to_f
      front = [d * 2.6, 64.0].max
      ny = sgn < 0 ? kbb.min.y - front : kbb.max.y + front
      eye = Geom::Point3d.new(c.x, ny, kbb.min.z + ht * 0.70)
      tgt = Geom::Point3d.new(c.x, c.y, kbb.min.z + ht * 0.40)
      cam = Sketchup::Camera.new(eye, tgt, Geom::Vector3d.new(0, 0, 1))
      cam.perspective = true
      cam.fov = 62
      model.active_view.camera = cam
      model.active_view.write_image(filename: ENV['KP_PNG'], width: 1500, height: 1100, antialias: true)
      rep << "=== 5) render cinza -> #{File.basename(ENV['KP_PNG'])} (cozinha bbox #{w.round}x#{d.round}x#{ht.round} in) ==="
    else
      rep << "=== 5) render cinza PULADO — nenhum grupo 'COZINHA' ==="
    end
  end

  File.write(ENV['KP_REPORT'] || 'skp_editability_report.txt', rep.join("\n"))
end

kp_run
