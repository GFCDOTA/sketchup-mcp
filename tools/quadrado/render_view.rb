require 'sketchup.rb'

model = Sketchup.active_model
view = model.active_view

bb = model.bounds
center = bb.center
diag = bb.diagonal

eye = Geom::Point3d.new(center.x + diag * 0.7, center.y - diag * 0.9, center.z + diag * 0.6)
target = center
up = Geom::Vector3d.new(0, 0, 1)

cam = Sketchup::Camera.new(eye, target, up)
cam.perspective = true
cam.fov = 35
view.camera = cam
view.zoom_extents

out_png = ENV['SKP_OUT']
options = {
  :filename    => out_png,
  :width       => 1600,
  :height      => 1200,
  :antialias   => true,
  :compression => 0.95,
  :transparent => false,
}
model.active_view.write_image(options)

done = out_png + '.done'
File.write(done, "ok\n")
