# test/sketchup_stub.rb
# Minimal stand-in for the SketchUp Ruby API so the pure-math parts
# of skp_export can be unit-tested under a vanilla Ruby interpreter
# (no SketchUp required).
#
# Only the constants and helpers that our `Coords`/`Units`/
# `BuildFloors` modules actually touch are stubbed. If tests ever
# need richer behaviour, extend this file — do NOT monkey-patch
# inside individual tests.

module Geom
  # SketchUp's Point3d is a struct-like object with x/y/z accessors
  # and an initialiser that takes lengths in inches. For scalar unit
  # tests we only need to hold the three numbers and return them.
  Point3d = Struct.new(:x, :y, :z) unless const_defined?(:Point3d)
  Vector3d = Struct.new(:x, :y, :z) unless const_defined?(:Vector3d)
end

# Numeric#m — inches-per-metre length conversion idiom used by
# SketchUp. Under real SketchUp `1.m` returns the number of inches in
# one metre (~39.37). For unit tests we just need the identity behaviour
# since we compare in metres only; we model `.m` as a no-op so the
# math stays readable.
unless Numeric.instance_methods.include?(:m)
  class Numeric
    def m
      self
    end
  end
end
