# screenshot_camera.rb — tira um PNG do modelo ABERTO com camera custom (inches).
# Env: SC_EYE "x,y,z" ; SC_TARGET "x,y,z" ; SC_OUT ; SC_LOG ; SC_FOV (opcional)
def sc_run
  model = Sketchup.active_model
  eye = ENV['SC_EYE'].split(',').map(&:to_f)
  tgt = ENV['SC_TARGET'].split(',').map(&:to_f)
  cam = Sketchup::Camera.new(Geom::Point3d.new(*eye), Geom::Point3d.new(*tgt),
                             Geom::Vector3d.new(0, 0, 1))
  cam.perspective = true
  cam.fov = (ENV['SC_FOV'] || '57').to_f
  model.active_view.camera = cam
  (model.rendering_options['Texture'] = true) rescue nil
  model.active_view.write_image(filename: ENV['SC_OUT'], width: 1100, height: 1375,
                                antialias: true)
  File.write(ENV['SC_LOG'] || 'sc_log.txt', "ok #{ENV['SC_OUT']}")
end
sc_run
