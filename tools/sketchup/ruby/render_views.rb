# render_views.rb — PNGs do .skp ABERTO por preset ou câmera explícita. Não salva o modelo.
#
# Params:
#   views: [{name, preset: top|iso|front|back|left|right}
#           | {name, eye_m:[x,y,z], target_m:[x,y,z], fov?, perspective?}]
#   width, height, hide_contains: [substring de nome de grupo a esconder]
#   focus_contains: substring — enquadra só o bbox desses grupos (ex. um cômodo)
require_relative 'skmcp_runtime'

def skmcp_pt(v)
  Geom::Point3d.new(v[0].to_f.m, v[1].to_f.m, v[2].to_f.m)
end

SkmcpRuntime.run('render_views') do |params, model|
  out_dir = params.fetch('out_dir')
  width = (params['width'] || 1600).to_i
  height = (params['height'] || 1200).to_i
  view = model.active_view
  (model.rendering_options['Texture'] = true) rescue nil
  # grupo aberto no .skp: o resto do modelo sairia esmaecido na imagem
  SkmcpRuntime.close_edit_context(model)

  hide = (params['hide_contains'] || []).map(&:downcase)
  hidden = []
  unless hide.empty?
    model.entities.each do |e|
      next unless e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
      label = (e.name.to_s.empty? ? e.definition.name : e.name).to_s.downcase
      next unless hide.any? { |h| label.include?(h) } && !e.hidden?
      e.hidden = true
      hidden << label
    end
  end

  bb = model.bounds
  if params['focus_contains'] && !params['focus_contains'].empty?
    needle = params['focus_contains'].downcase
    fb = Geom::BoundingBox.new
    model.entities.each do |e|
      next unless e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
      label = (e.name.to_s.empty? ? e.definition.name : e.name).to_s.downcase
      fb.add(e.bounds) if label.include?(needle)
    end
    raise "focus_contains=#{needle.inspect} não casou com nenhum grupo" if fb.empty?
    bb = fb
  end
  bmin = [bb.min.x, bb.min.y, bb.min.z].map(&:to_f)
  bmax = [bb.max.x, bb.max.y, bb.max.z].map(&:to_f)

  rendered = (params['views'] || [{ 'name' => 'top', 'preset' => 'top' },
                                  { 'name' => 'iso', 'preset' => 'iso' }]).map do |v|
    name = SkmcpCore.safe_filename(v['name'] || v['preset'])
    file = File.join(out_dir, "#{name}.png")
    begin
      if v['preset']
        c = SkmcpCore.preset_camera(v['preset'], bmin, bmax)
        cam = Sketchup::Camera.new(Geom::Point3d.new(*c['eye']), Geom::Point3d.new(*c['target']),
                                   Geom::Vector3d.new(*c['up']))
        cam.perspective = c['perspective']
        cam.height = SkmcpCore.ortho_height(bmin, bmax, width, height) unless c['perspective']
      else
        cam = Sketchup::Camera.new(skmcp_pt(v['eye_m']), skmcp_pt(v['target_m']), Geom::Vector3d.new(0, 0, 1))
        cam.perspective = v.fetch('perspective', true)
      end
      cam.fov = v['fov'].to_f if v['fov'] && cam.perspective?
      view.camera = cam
      ok = view.write_image(filename: file, width: width, height: height, antialias: true)
      { 'name' => name, 'path' => file, 'ok' => ok && File.exist?(file) }
    rescue StandardError => e
      { 'name' => name, 'path' => file, 'ok' => false, 'error' => "#{e.class}: #{e.message}" }
    end
  end

  { 'views' => rendered, 'hidden' => hidden, 'width' => width, 'height' => height,
    'all_ok' => rendered.all? { |r| r['ok'] }, 'model_saved' => false }
end
