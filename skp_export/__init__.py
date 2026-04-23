"""skp_export — Python-side bridge to the Ruby SketchUp exporter.

The Python code here validates `observed_model.json`, locates a SketchUp
installation, and invokes SketchUp's Ruby interpreter to produce the
final ``.skp`` file via the ``.rb`` scripts in this package.
"""

__version__ = "0.1.0"
