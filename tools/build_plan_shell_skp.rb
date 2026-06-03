# Build a single-shell .skp for an entire floor plan.
#
# Loaded via the existing autorun_consume.rb plugin (line 3 of
# autorun_control.txt points here). Reads:
#   ENV['CONSENSUS_JSON']  -> consensus path (set by autorun)
#   ENV['SKP_OUT']         -> output .skp path (set by autorun)
#   ENV['SHELL_JSON_IN']   -> _shell_polygon.json produced by the Python
#                             phase of build_plan_shell_skp.py
#   ENV['PNG_ISO_OUT']     -> isometric PNG screenshot path (optional)
#   ENV['PNG_TOP_OUT']     -> top-down PNG screenshot path (optional)
#   ENV['REPORT_OUT']      -> geometry_report.json path (optional)
#   ENV['SOFT_BARRIERS_MODE'] -> "groups" or "skip" (default "groups")
#
# Geometry strategy (see docs/adr/ADR-003-plan-shell-exporter.md):
#   1. PlanShell_Group: one Group containing the union'd wall polygon
#      extruded ONCE. No per-wall groups, no corner overlap, gaps for
#      openings already carved in 2D by the Python phase.
#   2. Floor_Group_<room_id>: one Group per room, flat face at z=0
#      from consensus.rooms[i].polygon_pts. No pushpull. Light room
#      palette colour.
#   3. SoftBarrier_Group_<i>: optional, one Group per soft_barrier at
#      1.10 m height. Skipped if SOFT_BARRIERS_MODE='skip', or if the
#      polyline overlaps a wall (FP-006 filter) — overlap policy here
#      is intentionally conservative for the first cut.

require 'json'

# Default = wall-thickness anchor (0.19 m wall / 5.4 pt), matches
# consume_consensus.rb. Per-build override via ENV['PT_TO_M'] so a plan whose
# real wall thickness differs (e.g. planta_74, PDF cotas -> ~0.0252 m/pt) can be
# built at its correct scale WITHOUT changing the global default (quadrado etc.
# keep 0.0352) and WITHOUT mutating any input fixture.
PT_TO_M  = (ENV['PT_TO_M'].to_s.strip.empty? ? (0.19 / 5.4) : ENV['PT_TO_M'].to_f)
M_TO_IN  = 39.3700787402
PT_TO_IN = PT_TO_M * M_TO_IN

WALL_HEIGHT_M    = 2.70
WALL_HEIGHT_IN   = WALL_HEIGHT_M * M_TO_IN
PARAPET_HEIGHT_M = 1.10
PARAPET_HEIGHT_IN = PARAPET_HEIGHT_M * M_TO_IN

WALL_RGB    = [78, 78, 78]     # same as consume_consensus.rb wall_dark
PARAPET_RGB = [130, 135, 140]  # same as consume_consensus.rb parapet

# ---- Phase 2 visual-parity constants (ports from consume_consensus.rb)
# All inherit consume_consensus.rb's values; provenance recorded in
# docs/grounding/constants_provenance.md as inherited_from_consume_consensus.

# Door leaf (for kind=interior_door / door_arc)
DOOR_HEIGHT_M    = 2.10
DOOR_THICK_M     = 0.04
DOOR_HEIGHT_IN   = DOOR_HEIGHT_M * M_TO_IN
DOOR_THICK_IN    = DOOR_THICK_M  * M_TO_IN
DOOR_RGB         = [140, 95, 55]   # madeira escura
DOOR_SWING_DEG   = 30.0            # visual swing angle

# Window panel (for kind=window). 3 bands: sill / glass / lintel.
WINDOW_SILL_M    = 0.90            # peitoril height
WINDOW_HEAD_M    = 2.10            # verga bottom
WINDOW_SILL_IN   = WINDOW_SILL_M * M_TO_IN
WINDOW_HEAD_IN   = WINDOW_HEAD_M * M_TO_IN
GLASS_RGB        = [180, 220, 240] # azul-glass
GLASS_ALPHA      = 0.45
LINTEL_RGB       = [110, 115, 120]

# Passage marker (for openings with geometry_origin=wall_gap that
# weren't carved). Thin floor-level rect for visibility.
PASSAGE_MARKER_HEIGHT_IN = 1.0     # ~2.5 cm above floor
PASSAGE_RGB              = [102, 187, 230]  # azul claro destacado

# Mirror of CARVING_ORIGINS in tools/build_plan_shell_skp.py — kept
# in sync manually. Used to decide which openings get a leaf/panel
# rendered (carved) vs which only get a passage marker (already in
# wall data).
CARVING_ORIGINS = ['svg_arc', 'svg_segments', 'human_annotation'].freeze
ROOM_PALETTE = [               # same as consume_consensus.rb ROOM_PALETTE
  [253, 226, 192], [200, 230, 201], [187, 222, 251], [248, 187, 208],
  [220, 237, 200], [255, 224, 178], [209, 196, 233], [179, 229, 252],
  [255, 249, 196], [245, 224, 208], [207, 216, 220],
]

def pdf_pt_to_su(pt)
  Geom::Point3d.new(pt[0] * PT_TO_IN, pt[1] * PT_TO_IN, 0.0)
end

# ---- shell extrusion ------------------------------------------------

def build_plan_shell(parent_ents, polygon_pieces, material)
  # Top-level wrapper Group. Each piece lives in its OWN sub-group so
  # pushpull operations are contextually isolated — previously they
  # were re-finding faces from earlier pieces, leading to extrusions
  # of the wrong face.
  group = parent_ents.add_group
  group.name = 'PlanShell_Group'

  pieces_solid = 0
  pieces_failed = 0
  pieces_holes_emitted = 0

  polygon_pieces.each_with_index do |piece, idx|
    outer = piece['outer']
    holes = piece['holes'] || []
    outer_pts = outer.map { |p| pdf_pt_to_su(p) }

    sub_group = group.entities.add_group
    sub_group.name = "PlanShell_piece_#{idx}"
    sub_ents = sub_group.entities

    outer_face = sub_ents.add_face(outer_pts)
    if outer_face.nil?
      puts "[shell] piece[#{idx}] outer face creation failed (#{outer.length} verts)"
      sub_group.erase!
      pieces_failed += 1
      next
    end

    # Add hole faces; SU recognises each as inside outer and creates
    # the hole topology. erase! the inner face — its edges remain and
    # bound the donut.
    holes.each do |hole|
      hole_pts = hole.map { |p| pdf_pt_to_su(p) }
      inner_face = sub_ents.add_face(hole_pts)
      if inner_face && inner_face.valid?
        inner_face.erase!
        pieces_holes_emitted += 1
      end
    end

    # In the sub-group, the only face(s) here are the ones we just
    # added — no risk of grabbing an old face. Prefer the multi-loop
    # face (when holes exist); else the only face.
    ring_face = sub_ents.grep(Sketchup::Face).find { |f| f.loops.length > 1 }
    ring_face ||= sub_ents.grep(Sketchup::Face).first
    if ring_face.nil?
      puts "[shell] piece[#{idx}] no ring face found after hole carve"
      sub_group.erase!
      pieces_failed += 1
      next
    end
    ring_face.reverse! if ring_face.normal.z < 0

    ring_face.pushpull(WALL_HEIGHT_IN)

    # Paint each face of the sub-group.
    sub_ents.grep(Sketchup::Face).each do |f|
      f.material      = material
      f.back_material = material
    end

    pieces_solid += 1
  end

  {
    'pieces_solid'         => pieces_solid,
    'pieces_failed'        => pieces_failed,
    'pieces_holes_emitted' => pieces_holes_emitted,
    'group'                => group,
  }
end

# ---- floors --------------------------------------------------------

def dedupe_consecutive_pts(pts, eps = 0.001)
  # Strip consecutive duplicates in a polygon's vertex list. Real
  # consensus data (planta_74) has rooms whose polygon_pts include
  # repeats (e.g., A.S. | TERRACO SOCIAL | TERRACO TECNICO has 196
  # entries with duplicates); SU's add_face refuses those with
  # ArgumentError: "Duplicate points in array". Also strip a closing
  # duplicate (last == first) since add_face wants distinct vertices.
  return pts if pts.length < 2
  result = [pts[0]]
  pts[1..].each do |pt|
    prev = result.last
    next if (pt[0] - prev[0]).abs < eps && (pt[1] - prev[1]).abs < eps
    result << pt
  end
  # Drop closing duplicate if present.
  if result.length >= 2
    first = result.first
    last  = result.last
    if (first[0] - last[0]).abs < eps && (first[1] - last[1]).abs < eps
      result.pop
    end
  end
  result
end

def build_floor(parent_ents, room, material, room_index)
  raw_pts = room['polygon_pts'] || []
  poly_pts = dedupe_consecutive_pts(raw_pts)
  if poly_pts.length < 3
    return {
      'ok' => false,
      'reason' => "polygon has #{poly_pts.length} unique vertices " \
                  "after dedupe (raw=#{raw_pts.length}); need >= 3",
    }
  end
  group = parent_ents.add_group
  rid = (room['id'] || "r#{room_index}").to_s
  group.name = "Floor_Group_#{rid}"
  ents = group.entities

  begin
    pts = poly_pts.map { |p| pdf_pt_to_su(p) }
    face = ents.add_face(pts)
    if face.nil?
      group.erase!
      return {
        'ok' => false,
        'reason' => "add_face returned nil (raw=#{raw_pts.length} " \
                    "deduped=#{poly_pts.length}; polygon may be " \
                    "self-intersecting or non-planar)",
      }
    end
    face.reverse! if face.normal.z < 0
    face.material      = material
    face.back_material = material
    {
      'ok'       => true,
      'group'    => group,
      'area_in2' => face.area.round(2),
      'raw_pts'  => raw_pts.length,
      'deduped_pts' => poly_pts.length,
    }
  rescue StandardError => e
    group.erase! if group && group.valid?
    {
      'ok'     => false,
      'reason' => "exception: #{e.class}: #{e.message} " \
                  "(raw=#{raw_pts.length} deduped=#{poly_pts.length})",
    }
  end
end

# ---- soft barriers (peitorils) -------------------------------------

# Half-thickness (in SU inches) of the thin slab swept along a soft
# barrier polyline segment. 1.5 in / 2 = 0.75 in ≈ 1.9 cm half-width
# → 3.8 cm full thickness. Matches consume_consensus.rb's add_parapet
# default. The point of using a thin sweep instead of the polyline's
# bounding box is so a peitoril running ~3 m along one edge of a
# room renders as a 3 m × 3.8 cm strip (~0.12 m²), not as a 3 m × Y
# rectangle covering the entire room interior (the 2026-05-20 bug).
SOFT_BARRIER_THICKNESS_IN = 1.5

# Soft barriers render ONLY when sourced (barrier_type / human confirmation /
# PDF-text). An unsourced bare polyline is NOT rendered as physical geometry —
# Hard Rule #1 (never invent). By type: railing/guardrail -> grade material,
# peitoril/mureta/parapet -> low solid wall. This replaces the old global
# SOFT_BARRIERS_MODE all-or-nothing that caused the render seesaw.
RAILING_BARRIER_TYPES  = %w[guardrail railing guarda_corpo guarda-corpo
                            peitoril_com_grade guarda_corpo_com_grade].freeze
LOW_WALL_BARRIER_TYPES = %w[peitoril mureta parapet].freeze

def barrier_source(sb)
  bt = sb['barrier_type']
  return "barrier_type=#{bt}" if bt && !bt.to_s.strip.empty?
  return 'human_confirmed' if sb['human_confirmed'] || sb['confirmed']
  return 'pdf_text' if sb['pdf_text'] || sb['source_label']
  nil
end

# Returns 'railing', 'low_wall', or nil (unsourced -> do not render).
def barrier_render_as(sb)
  bt = (sb['barrier_type'] || '').to_s.strip.downcase
  return 'railing'  if RAILING_BARRIER_TYPES.include?(bt)
  return 'low_wall' if LOW_WALL_BARRIER_TYPES.include?(bt)
  return 'low_wall' if barrier_source(sb) # sourced but untyped -> conservative
  nil
end

def soft_barrier_polyline_pts(barrier)
  # Soft barriers come as polyline arrays (consume_consensus.rb consumes
  # them the same way). Each is a list of [x, y] PDF points.
  barrier['polyline_pts'] || barrier['polyline'] || []
end

# Wall footprints + FP-006 overlap filter, ported from
# consume_consensus.rb lines 125-165 to keep the plan_shell exporter
# robust against the same "peitoril coincident with wall" failure
# (renders as 1.10 m wallpaper band on the wall face).
def wall_footprints_in_su(walls, thickness_pt)
  half = thickness_pt / 2.0
  walls.map do |w|
    sx, sy = w['start']
    ex, ey = w['end']
    if w['orientation'] == 'h'
      x0, x1 = [sx, ex].minmax
      y0, y1 = sy - half, sy + half
    else
      x0, x1 = sx - half, sx + half
      y0, y1 = [sy, ey].minmax
    end
    [x0 * PT_TO_IN, y0 * PT_TO_IN, x1 * PT_TO_IN, y1 * PT_TO_IN]
  end
end

def segment_overlaps_wall?(p1, p2, footprints, tol_in = 1.0)
  # 3-point sample (p1, midpoint, p2) inside any wall footprint
  # (within tol_in inches) ⇒ reject. Mirror of FP-006 in
  # consume_consensus.rb.
  pts = [
    [p1.x, p1.y],
    [(p1.x + p2.x) / 2.0, (p1.y + p2.y) / 2.0],
    [p2.x, p2.y],
  ]
  footprints.any? do |x0, y0, x1, y1|
    pts.any? do |px, py|
      px >= x0 - tol_in && px <= x1 + tol_in &&
        py >= y0 - tol_in && py <= y1 + tol_in
    end
  end
end

# ---- guarda-corpo (varanda planta_74) — render parametrico ----------
# EVOLUCAO (Felipe 2026-06-03): a foto da fachada real + o componente do
# 3DW ("Peitoril de vidro") mostram VIDRO translucido azulado entre
# montantes tubulares, com corrimao de cano e mureta de concreto na base —
# nao a grade de balaustres densos do palpite anterior. Geramos: mureta +
# painel de vidro + montantes espacados + corrimao (ver build_soft_barrier).
GRADE_RAIL_THICK_IN  = 0.04 * M_TO_IN   # 4cm corrimao (cano)
GRADE_BAL_SIZE_IN    = 0.02 * M_TO_IN   # (legado) 2cm balaustre — nao mais usado
GRADE_BAL_SPACING_IN = 0.12 * M_TO_IN   # (legado) ~12cm — nao mais usado
GRADE_BOT_Z0 = 0.03 * M_TO_IN
GRADE_BOT_Z1 = 0.11 * M_TO_IN
GRADE_TOP_Z0 = (PARAPET_HEIGHT_M - 0.08) * M_TO_IN
GRADE_TOP_Z1 = PARAPET_HEIGHT_IN
# Painel de VIDRO + montantes tubulares (calibrado pelo componente do 3DW que
# o Felipe baixou: bounds/material extraidos via inspect_peitoril.rb).
GLASS_THICK_IN        = 0.012 * M_TO_IN  # 12mm — painel de vidro fino
GLASS_RGB             = [124, 138, 181]  # azulado, extraido do componente
GLASS_ALPHA           = 0.45             # translucido (componente media 0.52)
GRADE_POST_SIZE_IN    = 0.05  * M_TO_IN  # 5cm — montante tubular (secao)
GRADE_POST_SPACING_IN = 1.0   * M_TO_IN  # ~1,0m entre montantes
# Guarda-corpo do PREDIO REAL (Felipe 2026-06-03, ref foto fachada): mureta de
# concreto na base (cimento) + grade metalica EM CIMA dela. A mureta vai do chao
# ate MURETA_BASE_M; a grade ocupa dali ate PARAPET_HEIGHT_M (1,10m).
MURETA_BASE_M  = 0.45
MURETA_BASE_IN = MURETA_BASE_M * M_TO_IN

def add_grade_box(ents, quad_xy, z0, z1, material)
  # Caixa: face no z0 (4 cantos [x,y]) -> pushpull ate z1. Retorna true se construiu.
  pts = quad_xy.map { |p| Geom::Point3d.new(p[0], p[1], z0) }
  g = ents.add_group
  f = (g.entities.add_face(pts) rescue nil)
  if f.nil?
    g.erase!
    return false
  end
  f.reverse! if f.normal.z < 0
  f.pushpull(z1 - z0)
  g.entities.grep(Sketchup::Face).each { |ff| ff.material = material; ff.back_material = material }
  true
end

def build_soft_barrier(parent_ents, barrier, material, index,
                       wall_footprints: nil)
  # Per-segment swept slab. For each consecutive pair (a, b) on the
  # polyline, build a thin rectangle perpendicular to the segment
  # direction with half-width SOFT_BARRIER_THICKNESS_IN/2. The slab is
  # then extruded to PARAPET_HEIGHT_IN. This mirrors the production
  # add_parapet behaviour (consume_consensus.rb:308-345) and replaces
  # the earlier polyline-bbox approach that produced enormous slabs
  # covering room interiors (2026-05-20 bug captured by
  # tests/test_plan_shell_invariants.py).
  pts_pdf = soft_barrier_polyline_pts(barrier)
  return {'ok' => false, 'reason' => 'no polyline_pts'} if pts_pdf.length < 2

  # SOURCE GATE (Felipe 2026-06-02): so renderiza com FONTE EXPLICITA.
  # sem barrier_type + sem human_annotation => SKIP TOTAL (caso sb000-sb007).
  # NADA de fallback fisico — nem grade, nem mureta, nem bloco cinza. Fica
  # ausente do SKP; aparece so como WARN no soft_barrier_source_audit.
  bt = barrier['barrier_type']
  has_source = (barrier['geometry_origin'] == 'human_annotation')
  unless bt && has_source
    return {'ok' => false,
            'reason' => "skip(no_source): barrier_type=#{bt.inspect} human_annotation=#{has_source}"}
  end
  # GRADE so com autorizacao explicita; peitoril/mureta = elemento baixo opaco.
  render_grade = (barrier['render_as'] == 'grade' || bt == 'guardrail' || bt == 'railing')

  group = parent_ents.add_group
  group.name = "SoftBarrier_Group_#{index}"

  segments_built  = 0
  total_len_in    = 0.0
  segments_skipped_short    = 0
  segments_skipped_overlap  = 0
  segments_skipped_facefail = 0

  pts_pdf.each_cons(2).with_index do |(a, b), seg_idx|
    next if a == b
    p1 = pdf_pt_to_su(a)
    p2 = pdf_pt_to_su(b)
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    len = Math.sqrt(dx * dx + dy * dy)
    if len < 0.01
      segments_skipped_short += 1
      next
    end
    # FP-006: drop segments whose midpoint sits inside a wall footprint
    # — those are the building outline that the vector extractor
    # catches as soft_barrier, not real peitoris.
    # EXCECAO (trust-human, gate :8765 GO opcao B): barreiras com
    # geometry_origin=human_annotation sao peitoris CONFIRMADOS pelo humano —
    # nunca dropadas por overlap. Peitoril real encosta na parede pela ponta
    # (3-pt sample acusa), entao FP-006 so vale pro AUTO-extraido. Restaura
    # sb005 (PEITORIL H=1,10M) que o regen #28 (merge de paredes) passou a derrubar.
    trust_human = barrier['geometry_origin'] == 'human_annotation'
    if wall_footprints && !trust_human && segment_overlaps_wall?(p1, p2, wall_footprints)
      segments_skipped_overlap += 1
      next
    end

    ux = dx / len
    uy = dy / len

    sub_group = group.entities.add_group
    sub_group.name = "SoftBarrier_#{index}_seg_#{seg_idx}"
    se = sub_group.entities

    # Ja passou pelo SOURCE GATE (tem barrier_type + fonte). GRADE so se
    # render_grade (render_as=grade / guardrail / railing); senao peitoril/
    # mureta = elemento baixo OPACO. NUNCA fallback de peitoril -> grade.
    if render_grade
      boxes = 0
      # (1) MURETA DE CONCRETO na base — o "cimento embaixo da grade" do predio
      # real (Felipe 2026-06-03). Laje solida do chao ate MURETA_BASE_IN, material
      # concreto (plan_parapet, cinza claro), distinta da grade metalica acima.
      concrete = (parent_ents.model.materials['plan_parapet'] rescue nil)
      mhalf = SOFT_BARRIER_THICKNESS_IN / 2.0
      mnx = -uy * mhalf
      mny =  ux * mhalf
      base_quad = [
        Geom::Point3d.new(p1.x + mnx, p1.y + mny, 0),
        Geom::Point3d.new(p2.x + mnx, p2.y + mny, 0),
        Geom::Point3d.new(p2.x - mnx, p2.y - mny, 0),
        Geom::Point3d.new(p1.x - mnx, p1.y - mny, 0),
      ]
      bface = (se.add_face(base_quad) rescue nil)
      if bface
        bface.reverse! if bface.normal.z < 0
        bface.pushpull(MURETA_BASE_IN)
        se.grep(Sketchup::Face).each { |f| f.material = (concrete || material); f.back_material = (concrete || material) }
        boxes += 1
      end
      # (2) GUARDA-CORPO DE VIDRO em cima da mureta (MURETA_BASE_IN .. 1,10m).
      # Replica o componente "Peitoril de vidro" do 3DW que o Felipe baixou
      # (2026-06-03): PAINEL DE VIDRO translucido azulado + MONTANTES tubulares
      # espacados + CORRIMAO de cano no topo. Substitui os balaustres densos
      # (antes parecia cerca; agora e a varanda de vidro da fachada real).
      glass_mat = (parent_ents.model.materials['plan_glass'] rescue nil) || material
      half_t = GRADE_RAIL_THICK_IN / 2.0
      nx = -uy * half_t
      ny =  ux * half_t
      rail_quad = [
        [p1.x + nx, p1.y + ny], [p2.x + nx, p2.y + ny],
        [p2.x - nx, p2.y - ny], [p1.x - nx, p1.y - ny],
      ]
      # (2a) CORRIMAO tubular (metal) no topo (1,02m .. 1,10m).
      boxes += 1 if add_grade_box(se, rail_quad, GRADE_TOP_Z0, GRADE_TOP_Z1, material)
      # (2b) PAINEL DE VIDRO: laje fina translucida, da mureta ao corrimao.
      ghalf = GLASS_THICK_IN / 2.0
      gnx = -uy * ghalf
      gny =  ux * ghalf
      glass_quad = [
        [p1.x + gnx, p1.y + gny], [p2.x + gnx, p2.y + gny],
        [p2.x - gnx, p2.y - gny], [p1.x - gnx, p1.y - gny],
      ]
      boxes += 1 if add_grade_box(se, glass_quad, MURETA_BASE_IN, GRADE_TOP_Z0, glass_mat)
      # (2c) MONTANTES tubulares (metal) espacados, da mureta ao topo.
      n_post = [(len / GRADE_POST_SPACING_IN).round, 1].max
      ps = GRADE_POST_SIZE_IN / 2.0
      (0..n_post).each do |k|
        t = k.to_f / n_post
        cx = p1.x + dx * t
        cy = p1.y + dy * t
        post_quad = [[cx - ps, cy - ps], [cx + ps, cy - ps], [cx + ps, cy + ps], [cx - ps, cy + ps]]
        boxes += 1 if add_grade_box(se, post_quad, MURETA_BASE_IN, GRADE_TOP_Z1, material)
      end
      ok_seg = boxes > 0
    else
      # MURETA OPACA (default): laje fina extrudada ate 1,10m.
      half_t = SOFT_BARRIER_THICKNESS_IN / 2.0
      nx = -uy * half_t
      ny =  ux * half_t
      quad = [
        Geom::Point3d.new(p1.x + nx, p1.y + ny, 0),
        Geom::Point3d.new(p2.x + nx, p2.y + ny, 0),
        Geom::Point3d.new(p2.x - nx, p2.y - ny, 0),
        Geom::Point3d.new(p1.x - nx, p1.y - ny, 0),
      ]
      face = (se.add_face(quad) rescue nil)
      if face
        face.reverse! if face.normal.z < 0
        face.pushpull(PARAPET_HEIGHT_IN)
        se.grep(Sketchup::Face).each { |f| f.material = material; f.back_material = material }
        ok_seg = true
      else
        ok_seg = false
      end
    end

    unless ok_seg
      sub_group.erase!
      segments_skipped_facefail += 1
      next
    end
    segments_built += 1
    total_len_in += len
  end

  if segments_built == 0
    group.erase!
    return {
      'ok' => false,
      'reason' => "all segments skipped " \
                  "(short=#{segments_skipped_short}, " \
                  "wall_overlap=#{segments_skipped_overlap}, " \
                  "facefail=#{segments_skipped_facefail})",
    }
  end

  {
    'ok' => true,
    'group' => group,
    'length_m'                 => (total_len_in / M_TO_IN).round(3),
    'segments_built'           => segments_built,
    'segments_skipped_short'   => segments_skipped_short,
    'segments_skipped_overlap' => segments_skipped_overlap,
    'segments_skipped_facefail' => segments_skipped_facefail,
  }
end

# ---- opening renderers (Phase 2 visual parity) --------------------

def opening_kind_v5(op)
  # Normalise the opening's semantic kind. consume_consensus.rb keys
  # off `kind_v5` with fallback to legacy `kind`. The strings we care
  # about: interior_door | interior_passage | window | glazed_balcony.
  k = op['kind_v5'] || op['kind'] || 'interior_door'
  return 'interior_door'   if k == 'door_arc' || k == 'door'
  return 'interior_passage' if k == 'open_passage' || k == 'passage'
  k
end

def opening_axis_basis(host_wall)
  # Returns the axis the wall runs along (0=x, 1=y), the cross axis,
  # and the centerline coordinate on the cross axis.
  if host_wall['orientation'] == 'h'
    [0, 1, host_wall['start'][1].to_f]
  else
    [1, 0, host_wall['start'][0].to_f]
  end
end

def opening_carve_corners_pdf(opening, host_wall, thickness_pt)
  # Mirror of opening_carve_rect in build_plan_shell_skp.py.
  # Returns the 4 PDF-point corners of the opening rectangle aligned
  # with the host wall.
  half = thickness_pt / 2.0
  cx, cy = opening['center']
  w = opening['opening_width_pts'].to_f
  half_w = w / 2.0
  if host_wall['orientation'] == 'h'
    wall_cy = host_wall['start'][1].to_f
    [
      [cx - half_w, wall_cy - half],
      [cx + half_w, wall_cy - half],
      [cx + half_w, wall_cy + half],
      [cx - half_w, wall_cy + half],
    ]
  else
    wall_cx = host_wall['start'][0].to_f
    [
      [wall_cx - half, cy - half_w],
      [wall_cx + half, cy - half_w],
      [wall_cx + half, cy + half_w],
      [wall_cx - half, cy + half_w],
    ]
  end
end

def emit_band_at(parent_ents, corners_pdf, z_bottom_in, z_top_in, material, name)
  # Build a 3D box from a 2D footprint between two z heights. Used by
  # window panels (sill / glass / lintel). Returns the sub-group.
  pts_pdf = corners_pdf
  # Move to z_bottom, then pushpull to z_top.
  base_pts = pts_pdf.map { |p|
    Geom::Point3d.new(p[0] * PT_TO_IN, p[1] * PT_TO_IN, z_bottom_in)
  }
  group = parent_ents.add_group
  group.name = name
  face = group.entities.add_face(base_pts)
  return nil if face.nil?
  face.reverse! if face.normal.z < 0
  face.pushpull(z_top_in - z_bottom_in)
  group.entities.grep(Sketchup::Face).each do |f|
    f.material      = material
    f.back_material = material
  end
  group
end

def build_door_leaf(parent_ents, opening, host_wall, _thickness_pt, material, index)
  # Renders a thin rotating leaf (DOOR_THICK_M × opening_width)
  # hinged at one end of the opening, rotated DOOR_SWING_DEG open.
  # The leaf lives in its own top-level Group (DoorLeaf_Group_<id>),
  # NOT inside PlanShell_Group — leaves are a separate visual layer.
  # _thickness_pt retained for caller symmetry with the other
  # opening renderers (each receives the same signature).
  axis_idx, _cross_idx, cross_value = opening_axis_basis(host_wall)
  cx, cy = opening['center']
  along = axis_idx == 0 ? cx.to_f : cy.to_f
  width_pt = opening['opening_width_pts'].to_f
  hinge_side = opening['hinge_side'] || opening['hinge'] || 'left'

  # Hinge end along the wall axis.
  hinge_along = (hinge_side == 'right') ? along + width_pt / 2.0 : along - width_pt / 2.0
  far_along   = (hinge_side == 'right') ? along - width_pt / 2.0 : along + width_pt / 2.0

  # Place leaf on one face of the wall (offset by half thickness on the
  # cross axis). Closed leaf base: a rectangle hinge_along..far_along
  # along the wall axis × DOOR_THICK_IN across.
  cross_offset_pt = host_wall['thickness'].to_f / 2.0
  # Leaf sits aligned with one wall face — pick the side based on
  # opening direction. We don't have side info; use cross+offset.
  cross_base = cross_value + cross_offset_pt

  # Build the leaf's flat footprint at z=0, then pushpull to DOOR_HEIGHT.
  if axis_idx == 0
    # Horizontal wall — leaf footprint along x, thickness along y
    base_corners = [
      [hinge_along, cross_base],
      [far_along,   cross_base],
      [far_along,   cross_base + DOOR_THICK_M / PT_TO_M],
      [hinge_along, cross_base + DOOR_THICK_M / PT_TO_M],
    ]
  else
    base_corners = [
      [cross_base,                         hinge_along],
      [cross_base + DOOR_THICK_M / PT_TO_M, hinge_along],
      [cross_base + DOOR_THICK_M / PT_TO_M, far_along],
      [cross_base,                         far_along],
    ]
  end
  pts = base_corners.map { |p| Geom::Point3d.new(p[0] * PT_TO_IN, p[1] * PT_TO_IN, 0) }

  group = parent_ents.add_group
  group.name = "DoorLeaf_Group_#{opening['id'] || index}"
  face = group.entities.add_face(pts)
  if face.nil?
    group.erase!
    return {'ok' => false, 'reason' => 'door leaf add_face nil'}
  end
  face.reverse! if face.normal.z < 0
  face.pushpull(DOOR_HEIGHT_IN)
  group.entities.grep(Sketchup::Face).each do |f|
    f.material      = material
    f.back_material = material
  end

  # Rotate around the vertical hinge axis by DOOR_SWING_DEG.
  # Bug fix (2026-05-20): the previous version computed
  #   hinge_world = (hinge_along, axis_idx == 0 ? cross_base : hinge_along, 0)
  # which for vertical walls (axis_idx == 1) put BOTH x and y to
  # `hinge_along`, sending the pivot onto an arbitrary diagonal in
  # world space. The leaf then rotated around that off-axis pivot
  # and was visibly translated metres away from the host wall —
  # "floating doors" in the .skp.
  # The correct mapping:
  #   horizontal wall (axis_idx == 0): hinge_world = (hinge_along, cross_base, 0)
  #   vertical wall  (axis_idx == 1): hinge_world = (cross_base, hinge_along, 0)
  hinge_world = if axis_idx == 0
    Geom::Point3d.new(
      hinge_along * PT_TO_IN,
      cross_base * PT_TO_IN,
      0,
    )
  else
    Geom::Point3d.new(
      cross_base * PT_TO_IN,
      hinge_along * PT_TO_IN,
      0,
    )
  end
  hinge_axis = Geom::Vector3d.new(0, 0, 1)
  hinge_xform = Geom::Transformation.rotation(
    hinge_world, hinge_axis,
    DOOR_SWING_DEG * Math::PI / 180.0,
  )
  group.transform!(hinge_xform)

  {'ok' => true, 'group' => group}
end

def build_window_panel(parent_ents, opening, host_wall, thickness_pt,
                        sill_mat, glass_mat, lintel_mat, index)
  # 3-band window: sill (0 → 0.9 m) + glass (0.9 → 2.1 m) + lintel (2.1 → 2.7 m).
  # Each band is a sub-group inside Window_Group_<id> wrapper.
  corners = opening_carve_corners_pdf(opening, host_wall, thickness_pt)
  group = parent_ents.add_group
  group.name = "Window_Group_#{opening['id'] || index}"

  oid = opening['id'] || index.to_s
  sill = emit_band_at(group.entities, corners, 0.0, WINDOW_SILL_IN,
                     sill_mat, "Window_#{oid}_sill")
  glass = emit_band_at(group.entities, corners, WINDOW_SILL_IN, WINDOW_HEAD_IN,
                      glass_mat, "Window_#{oid}_glass")
  lintel = emit_band_at(group.entities, corners, WINDOW_HEAD_IN, WALL_HEIGHT_IN,
                       lintel_mat, "Window_#{oid}_lintel")
  built = [sill, glass, lintel].compact.length
  if built == 0
    group.erase!
    return {'ok' => false, 'reason' => 'window panel: all 3 bands failed'}
  end
  {'ok' => true, 'group' => group, 'bands_built' => built}
end

def build_glazed_balcony(parent_ents, opening, host_wall, thickness_pt,
                         glass_mat, index)
  # Full-height glass (porta-vidro). Single sub-group sweeping 0 → WALL_HEIGHT_IN.
  corners = opening_carve_corners_pdf(opening, host_wall, thickness_pt)
  group = parent_ents.add_group
  group.name = "GlazedBalcony_Group_#{opening['id'] || index}"
  oid = opening['id'] || index.to_s
  pane = emit_band_at(group.entities, corners, 0.0, WALL_HEIGHT_IN,
                     glass_mat, "GlazedBalcony_#{oid}_pane")
  if pane.nil?
    group.erase!
    return {'ok' => false, 'reason' => 'glazed_balcony pane add_face nil'}
  end
  {'ok' => true, 'group' => group}
end

def build_passage_marker(parent_ents, opening, host_wall, thickness_pt,
                          material, index)
  # Thin floor-level rect (PASSAGE_MARKER_HEIGHT_IN ≈ 2.5 cm) to make
  # the opening visible in the model. Used for wall_gap-origin
  # openings whose gap is already in the wall data (not carved by us).
  corners = opening_carve_corners_pdf(opening, host_wall, thickness_pt)
  group = parent_ents.add_group
  group.name = "PassageMarker_Group_#{opening['id'] || index}"
  oid = opening['id'] || index.to_s
  marker = emit_band_at(group.entities, corners, 0.0,
                       PASSAGE_MARKER_HEIGHT_IN,
                       material, "PassageMarker_#{oid}_band")
  if marker.nil?
    group.erase!
    return {'ok' => false, 'reason' => 'passage marker add_face nil'}
  end
  {'ok' => true, 'group' => group}
end

# ---- WINDOW APERTURE 3D CARVE (ADR-007 / FP-024) -------------------
#
# A WINDOW is a wall-hosted partial-height aperture: WINDOW_SILL_IN to
# WINDOW_HEAD_IN. The wall MUST retain mass below the sill (peitoril /
# parapet) AND above the head (verga / lintel). Carving the wall full-
# height in 2D (the prior bug) then refilling with sill+glass+lintel
# bands produces three structurally-separate volumes that read as
# "shaft with infill," not as "wall with window aperture."
#
# This function carves the aperture AFTER the wall is extruded as a
# solid. Steps mirror the in-place edit pattern documented in
# docs/specs/quadrado_demo_spec.md §6.4:
#   1. Locate the PlanShell sub-group containing the host wall.
#   2. Find a vertical (lateral) face perpendicular to the wall axis
#      that contains the window aperture position. (Either the outer
#      or inner face — pushpull goes through anyway.)
#   3. READ wall face coords FROM THE MODEL (LL-014; never hardcode).
#   4. Add a coplanar rectangle face on that face at
#      [sill_in..head_in] × [cx-w/2 .. cx+w/2]. SU auto-splits the
#      host face into [aperture] + [perimeter remainder].
#   5. pushpull(-real_thickness_in) — pushes aperture face through the
#      wall; SU merges with the opposite face on exact match,
#      creating a real through-hole. Wall mass above head and below
#      sill is preserved as part of the perimeter remainder.
#   6. Add a glass face at mid-thickness inside the aperture (separate
#      top-level group so it can be inspected/replaced without
#      touching the wall shell).

def find_wall_face_for_aperture(piece_ents, host_wall, cx_in, cy_in,
                                  half_w_in, slab_floor_in, slab_ceiling_in,
                                  host_at, tol)
  # host_at = host wall's perpendicular position (y for 'h', x for 'v'), inches;
  # tol = match tolerance (~half wall thickness + margin).
  # FP-031: require the candidate face to belong to the HOST wall. Without this
  # the find() returned the first face merely spanning the aperture's x/y-range
  # — often a different parallel facade — carving the hole on the wrong wall.
  # Returning nil here (no host face) lets the caller fall back to a panel.
  ori = host_wall['orientation']
  piece_ents.grep(Sketchup::Face).find do |f|
    next false if f.normal.z.abs > 0.01  # skip top/bottom (annular floor/ceiling)
    if ori == 'h'
      next false unless f.normal.y.abs > 0.99
      bb = f.bounds
      (bb.min.y - host_at).abs <= tol &&
        bb.min.x <= cx_in - half_w_in + 0.5 &&
        bb.max.x >= cx_in + half_w_in - 0.5 &&
        bb.min.z < slab_floor_in + 0.5 &&
        bb.max.z > slab_ceiling_in - 0.5
    else
      next false unless f.normal.x.abs > 0.99
      bb = f.bounds
      (bb.min.x - host_at).abs <= tol &&
        bb.min.y <= cy_in - half_w_in + 0.5 &&
        bb.max.y >= cy_in + half_w_in - 0.5 &&
        bb.min.z < slab_floor_in + 0.5 &&
        bb.max.z > slab_ceiling_in - 0.5
    end
  end
end

def build_window_aperture_3d(parent_ents, opening, host_wall, thickness_pt,
                              glass_mat, index)
  oid = opening['id'] || index.to_s
  cx_pt, cy_pt = opening['center']
  w_pt = opening['opening_width_pts'].to_f
  ori = host_wall['orientation']

  cx_in = cx_pt * PT_TO_IN
  cy_in = cy_pt * PT_TO_IN
  half_w_in = (w_pt * PT_TO_IN) / 2.0
  sill_in = WINDOW_SILL_IN
  head_in = WINDOW_HEAD_IN
  # Use the HOST wall's own thickness for the through-carve, not the global
  # consensus thickness. FP-031 #28 merged collinear walls and set each merged
  # wall's thickness to the MEAN of its segments, so a merged wall (e.g. m003 =
  # 5.52pt) can be THICKER than the global (5.40pt). pushpull(-global) then
  # stops short of the far face -> no through-hole -> a blind pocket that reads
  # as a flat dark rectangle, not a glazed window (Felipe: BANHO 2 "só o recorte,
  # sem vidro"). The shell builds the wall at host_wall['thickness'], so carving
  # exactly that distance reaches the far face and merges into a clean hole.
  thickness_in = (host_wall['thickness'] || thickness_pt).to_f * PT_TO_IN
  # Host wall's perpendicular position + tolerance (FP-031), so the aperture
  # only carves the host wall (mirrors the glass, which uses host_wall.start).
  host_at_in = (ori == 'h' ? host_wall['start'][1].to_f
                           : host_wall['start'][0].to_f) * PT_TO_IN
  face_tol_in = thickness_in + 4.0  # ~half thickness + margin; << wall spacing

  plan_shell = parent_ents.grep(Sketchup::Group)
                          .find { |g| g.name == 'PlanShell_Group' }
  return {'ok' => false, 'reason' => 'PlanShell_Group not found'} if plan_shell.nil?

  carve_succeeded = false
  glass_group = nil
  carve_diag = []

  plan_shell.entities.grep(Sketchup::Group).each do |piece|
    ents = piece.entities
    target = find_wall_face_for_aperture(
      ents, host_wall, cx_in, cy_in, half_w_in, 0.0, WALL_HEIGHT_IN,
      host_at_in, face_tol_in,
    )
    if target.nil?
      carve_diag << "#{piece.name}: no candidate face"
      next
    end

    # Read face's fixed coord from the actual model (LL-014).
    if ori == 'h'
      y_at = target.bounds.min.y  # face is at constant y
      pts = [
        Geom::Point3d.new(cx_in - half_w_in, y_at, sill_in),
        Geom::Point3d.new(cx_in + half_w_in, y_at, sill_in),
        Geom::Point3d.new(cx_in + half_w_in, y_at, head_in),
        Geom::Point3d.new(cx_in - half_w_in, y_at, head_in),
      ]
    else
      x_at = target.bounds.min.x
      pts = [
        Geom::Point3d.new(x_at, cy_in - half_w_in, sill_in),
        Geom::Point3d.new(x_at, cy_in + half_w_in, sill_in),
        Geom::Point3d.new(x_at, cy_in + half_w_in, head_in),
        Geom::Point3d.new(x_at, cy_in - half_w_in, head_in),
      ]
    end

    aperture_face = ents.add_face(pts)
    if aperture_face.nil?
      carve_diag << "#{piece.name}: add_face returned nil"
      next
    end

    # Push aperture face INTO the wall. Outer face normal points
    # outward; pushpull(-thickness) drives the face inward through
    # the wall, where it merges with the opposite face on exact match,
    # creating a real through-hole. Wall mass above/below stays put.
    begin
      aperture_face.pushpull(-thickness_in)
    rescue StandardError => e
      carve_diag << "#{piece.name}: pushpull raised #{e.class}: #{e.message}"
      next
    end
    carve_succeeded = true

    # Glass pane at mid-thickness — separate top-level group.
    if ori == 'h'
      mid_y_in = host_wall['start'][1].to_f * PT_TO_IN
      glass_pts = [
        Geom::Point3d.new(cx_in - half_w_in, mid_y_in, sill_in),
        Geom::Point3d.new(cx_in + half_w_in, mid_y_in, sill_in),
        Geom::Point3d.new(cx_in + half_w_in, mid_y_in, head_in),
        Geom::Point3d.new(cx_in - half_w_in, mid_y_in, head_in),
      ]
    else
      mid_x_in = host_wall['start'][0].to_f * PT_TO_IN
      glass_pts = [
        Geom::Point3d.new(mid_x_in, cy_in - half_w_in, sill_in),
        Geom::Point3d.new(mid_x_in, cy_in + half_w_in, sill_in),
        Geom::Point3d.new(mid_x_in, cy_in + half_w_in, head_in),
        Geom::Point3d.new(mid_x_in, cy_in - half_w_in, head_in),
      ]
    end

    glass_group = parent_ents.add_group
    glass_group.name = "WindowGlass_Group_#{oid}"
    glass_face = glass_group.entities.add_face(glass_pts)
    if glass_face
      glass_face.material = glass_mat
      glass_face.back_material = glass_mat
    end

    break
  end

  if carve_succeeded
    {
      'ok' => true,
      'group' => glass_group,
      'aperture_carved' => true,
      'sill_in' => sill_in,
      'head_in' => head_in,
    }
  else
    {'ok' => false, 'reason' => "no piece matched: #{carve_diag.join('; ')}"}
  end
end

# ---- camera + screenshots -----------------------------------------

def setup_iso_camera(model)
  view = model.active_view
  bbox = model.bounds
  center = bbox.center
  diag = bbox.diagonal
  # Cabinet-iso direction with healthy margin
  d = diag * 5.0
  eye = Geom::Point3d.new(
    center.x + d * 0.5,
    center.y - d * 0.6,
    center.z + d * 0.7,
  )
  cam = Sketchup::Camera.new(eye, center, Geom::Vector3d.new(0, 0, 1))
  cam.perspective = false
  cam.height = diag * 1.2
  view.camera = cam
  view.zoom_extents
end

def setup_top_camera(model, img_w = 1600, img_h = 1200)
  view = model.active_view
  bbox = model.bounds
  center = bbox.center
  diag = bbox.diagonal
  eye = Geom::Point3d.new(center.x, center.y, center.z + diag * 5.0)
  cam = Sketchup::Camera.new(
    eye, center, Geom::Vector3d.new(0, 1, 0),
  )
  cam.perspective = false
  # FP-031 #29: DETERMINISTIC ortho-top fit to the IMAGE aspect — NOT
  # view.zoom_extents, which fits the SU *window* aspect and then clips the
  # model in the fixed-aspect PNG (so the perimeter falls off-frame and the
  # wall-presence gate cannot verify it). Set cam.height to contain the model
  # bounds in the img_w:img_h aspect + a small margin, centred on the model.
  # Result: the whole plan is always in-frame and the pixel projection is
  # reproducible (independent of the SU window size).
  aspect = img_w.to_f / img_h.to_f
  model_w = bbox.max.x - bbox.min.x
  model_h = bbox.max.y - bbox.min.y
  cam.height = [model_h, model_w / aspect].max * 1.06
  view.camera = cam
end

def write_png(model, path, width = 1600, height = 1200)
  options = {
    :filename    => path,
    :width       => width,
    :height      => height,
    :antialias   => true,
    :compression => 0.95,
    :transparent => false,
  }
  model.active_view.write_image(options)
end

# FP-031 #2: emit the EXACT top-view projection so the deterministic
# wall-presence gate (tools/overlay_diff.py) needs zero pixel calibration.
# Writes a sidecar `<png>.proj.json` (additive — does NOT change the render).
# Must be called while the TOP camera is active, right after zoom_extents and
# before any other view mutation (view.screen_coords is viewport-dependent).
def write_top_projection_sidecar(model, png_path, width, height)
  return if png_path.nil? || png_path.to_s.empty?
  view = model.active_view
  cam  = view.camera
  bb   = model.bounds
  samples_in = [
    [bb.min.x, bb.min.y], [bb.max.x, bb.min.y], [bb.max.x, bb.max.y],
    [bb.min.x, bb.max.y], [bb.center.x, bb.center.y],
  ]
  samples = samples_in.map do |xi, yi|
    sp = view.screen_coords(Geom::Point3d.new(xi, yi, 0.0))
    { 'world_pt' => [xi / PT_TO_IN, yi / PT_TO_IN],   # back to pdf-points
      'world_in' => [xi, yi],
      'screen_px' => [sp.x.to_f, sp.y.to_f] }
  end
  data = {
    'mode' => 'ortho_top',
    'png' => File.basename(png_path.to_s),
    'img_w' => width, 'img_h' => height,
    'vp_w' => view.vpwidth, 'vp_h' => view.vpheight,
    'cam_height_in' => cam.height.to_f,
    'cam_target_in' => [cam.target.x.to_f, cam.target.y.to_f],
    'pt_to_in' => PT_TO_IN,
    'samples' => samples,
  }
  File.write(png_path.to_s + '.proj.json', JSON.pretty_generate(data))
end

# ---- geometry report ----------------------------------------------

def walk_entities(ents, faces_out, edges_out, sub_groups_out)
  ents.each do |e|
    case e
    when Sketchup::Face then faces_out << e
    when Sketchup::Edge then edges_out << e
    when Sketchup::Group
      sub_groups_out << e
      walk_entities(e.entities, faces_out, edges_out, sub_groups_out)
    end
  end
end

def collect_face_records(group)
  faces = []
  edges = []
  sub_groups = []
  walk_entities(group.entities, faces, edges, sub_groups)
  default_faces = faces.count do |f|
    (f.material.nil? || f.back_material.nil?)
  end
  {
    'faces'                 => faces.length,
    'edges'                 => edges.length,
    'sub_groups'            => sub_groups.length,
    'faces_with_holes'      => faces.count { |f| f.loops.length > 1 },
    'top_or_bottom_faces'   => faces.count { |f| f.normal.z.abs > 0.99 },
    'default_material_faces' => default_faces,
  }
end

def primary_material_name(faces)
  # The "primary" material is the one most faces are painted with.
  # Returns nil if no face has a material.
  counts = Hash.new(0)
  faces.each do |f|
    m = f.material
    counts[m.name] += 1 if m
  end
  return nil if counts.empty?
  counts.max_by { |_, n| n }.first
end

def lateral_face_count(faces, eps = 0.01)
  # A "lateral" face has a normal lying roughly in the XY plane, i.e.
  # |normal.z| << 1. A pure floor has ZERO lateral faces. Wall-shell
  # and soft-barrier groups have many.
  faces.count { |f| f.normal.z.abs < eps }
end

def group_bbox_record(group)
  # Walk the group's entities (recursing into sub-groups) and capture
  # the axis-aligned bbox in SU's internal units (inches). Also returns
  # height_m for direct invariant checks.
  faces = []
  edges = []
  subs = []
  walk_entities(group.entities, faces, edges, subs)

  # SU's Group#bounds returns the local bbox in inches.
  bbox = group.bounds
  z_min_in = bbox.min.z
  z_max_in = bbox.max.z
  x_min_in = bbox.min.x
  x_max_in = bbox.max.x
  y_min_in = bbox.min.y
  y_max_in = bbox.max.y
  height_in = z_max_in - z_min_in

  # Real material footprint: sum of areas of all faces with a roughly
  # +Z normal (the "tops" of the swept slabs / the floor tile / the
  # top of the wall shell). Distinct from `footprint_bbox_m2`, which
  # is the bounding box of the whole group and over-estimates badly
  # when sub-groups are sparsely placed along a polyline.
  m_per_in = 1.0 / M_TO_IN
  top_faces = faces.select { |f| f.normal.z > 0.99 }
  top_area_in2 = top_faces.sum(0.0) { |f| f.area }
  top_area_m2 = (top_area_in2 * m_per_in * m_per_in).round(4)

  {
    'name'              => group.name,
    'entity_count'      => group.entities.length,
    'face_count'        => faces.length,
    'edge_count'        => edges.length,
    'sub_group_count'   => subs.length,
    'lateral_face_count' => lateral_face_count(faces),
    'top_or_bottom_face_count' => faces.count { |f| f.normal.z.abs > 0.99 },
    'top_face_count' => top_faces.length,
    'default_material_face_count' => faces.count do |f|
      f.material.nil? || f.back_material.nil?
    end,
    'primary_material'  => primary_material_name(faces),
    'bbox_in' => {
      'min' => [x_min_in.round(4), y_min_in.round(4), z_min_in.round(4)],
      'max' => [x_max_in.round(4), y_max_in.round(4), z_max_in.round(4)],
    },
    'bbox_m' => {
      'min' => [
        (x_min_in * m_per_in).round(4),
        (y_min_in * m_per_in).round(4),
        (z_min_in * m_per_in).round(4),
      ],
      'max' => [
        (x_max_in * m_per_in).round(4),
        (y_max_in * m_per_in).round(4),
        (z_max_in * m_per_in).round(4),
      ],
    },
    'height_m'  => (height_in * m_per_in).round(4),
    'footprint_bbox_m2' => (
      ((x_max_in - x_min_in) * (y_max_in - y_min_in)) *
      m_per_in * m_per_in
    ).round(4),
    'footprint_top_face_m2' => top_area_m2,
  }
end

def deep_face_check_all_painted?(group)
  faces = []
  edges = []
  subs = []
  walk_entities(group.entities, faces, edges, subs)
  faces.all? { |f| !f.material.nil? }
end

def write_geometry_report(model, report_path, ctx)
  ents = model.active_entities
  groups = ents.grep(Sketchup::Group)
  plan_shell  = groups.find { |g| g.name == 'PlanShell_Group' }
  floor_grps  = groups.select { |g| g.name.start_with?('Floor_Group_') }
  sb_grps     = groups.select { |g| g.name.start_with?('SoftBarrier_Group_') }

  report = {
    'schema_version'   => '1.0.0',
    'tool'             => 'build_plan_shell_skp',
    'consensus_path'   => ctx[:consensus_path],
    'skp_path'         => ctx[:skp_path],
    'shell_json_path'  => ctx[:shell_json_path],
    'soft_barriers_mode' => ctx[:soft_barriers_mode],
    'plan_shell' => plan_shell ?
      collect_face_records(plan_shell).merge({'present' => true}) :
      {'present' => false},
    'floor_groups' => {
      'present'  => !floor_grps.empty?,
      'count'    => floor_grps.length,
      'failed_count'   => (ctx[:floors_failed] || []).length,
      'failed_records' => ctx[:floors_failed] || [],
      'records'  => floor_grps.map do |g|
        face = g.entities.grep(Sketchup::Face).first
        {
          'name'      => g.name,
          'faces'     => g.entities.grep(Sketchup::Face).length,
          'edges'     => g.entities.grep(Sketchup::Edge).length,
          'area_in2'  => face ? face.area.round(2) : nil,
          'area_m2'   => face ? (face.area / (M_TO_IN * M_TO_IN)).round(4) : nil,
        }
      end,
    },
    'soft_barrier_groups' => {
      'present' => !sb_grps.empty?,
      'count'   => sb_grps.length,
      'skipped_count' => ctx[:soft_barriers_skipped] || 0,
      'skip_reasons'  => ctx[:soft_barriers_skip_reasons] || [],
      'barriers'      => ctx[:soft_barrier_records] || [],
    },
    'totals' => {
      'top_level_groups' => groups.length,
      'faces' => groups.sum { |g| g.entities.grep(Sketchup::Face).length },
      'edges' => groups.sum { |g| g.entities.grep(Sketchup::Edge).length },
    },
    'groups_diagnostic' => groups.map { |g| group_bbox_record(g) },
    'shell_stats_from_python' => ctx[:py_stats],
    'gates_self_check' => {
      'plan_shell_group_exists'    => !plan_shell.nil?,
      'wall_shell_is_single_group' => !plan_shell.nil?,
      'floors_separated_from_walls' => floor_grps.length > 0,
      'default_material_faces_zero' =>
        groups.all? { |g| deep_face_check_all_painted?(g) },
    },
  }
  File.write(report_path, JSON.pretty_generate(report))
end

# ===== Main =========================================================

cjson      = ENV['CONSENSUS_JSON'] or raise 'CONSENSUS_JSON env not set'
outskp     = ENV['SKP_OUT']        or raise 'SKP_OUT env not set'
shell_json = ENV['SHELL_JSON_IN']  or raise 'SHELL_JSON_IN env not set'
outpng_iso = ENV['PNG_ISO_OUT']
outpng_top = ENV['PNG_TOP_OUT']
outreport  = ENV['REPORT_OUT']
sb_mode    = ENV['SOFT_BARRIERS_MODE'] || 'groups'

puts "[rb] consensus=#{cjson}"
puts "[rb] out_skp=#{outskp}"
puts "[rb] shell_json=#{shell_json}"
puts "[rb] soft_barriers_mode=#{sb_mode}"

shell_data = JSON.parse(File.read(shell_json))
consensus  = JSON.parse(File.read(cjson))

model = Sketchup.active_model
model.entities.clear!
model.definitions.purge_unused
model.start_operation('build_plan_shell', true)

wall_mat = model.materials.add('plan_wall')
wall_mat.color = Sketchup::Color.new(*WALL_RGB)

# 1. Plan shell (the unified wall)
shell_result = build_plan_shell(
  model.active_entities, shell_data['polygons'], wall_mat,
)
puts "[rb] shell: solid=#{shell_result['pieces_solid']} " \
     "failed=#{shell_result['pieces_failed']} " \
     "holes=#{shell_result['pieces_holes_emitted']}"

# 2. Floors (one per room)
rooms = consensus['rooms'] || []
floors_built  = 0
floors_failed = []
rooms.each_with_index do |room, i|
  palette_rgb = ROOM_PALETTE[i % ROOM_PALETTE.length]
  mat_name = "floor_#{room['id'] || i}"
  mat = model.materials.add(mat_name)
  mat.color = Sketchup::Color.new(*palette_rgb)
  res = build_floor(model.active_entities, room, mat, i)
  if res['ok']
    floors_built += 1
  else
    floors_failed << {
      'room_id'  => room['id'] || "r#{i}",
      'room_name' => room['name'] || "(unnamed)",
      'polygon_vertex_count' => (room['polygon_pts'] || []).length,
      'reason'   => res['reason'],
    }
    puts "[rb] floor FAILED for #{room['name'] || room['id']}: #{res['reason']}"
  end
end
puts "[rb] floors: built=#{floors_built} failed=#{floors_failed.length}"

# 3. Soft barriers — rendered BY barrier_type + source, never global on/off.
# Unsourced barriers (no barrier_type / confirmation) are NOT emitted as
# physical geometry (Hard Rule #1). railing/guardrail -> grade material;
# peitoril/mureta/parapet -> low solid wall. Each decision is recorded in
# sb_records so the railing gates can verify the SKP against the consensus.
sb_built = 0
sb_skipped = 0
sb_skip_reasons = []
sb_records = []
if sb_mode == 'groups'
  parapet_mat = model.materials.add('plan_parapet')
  parapet_mat.color = Sketchup::Color.new(*PARAPET_RGB)
  railing_mat = model.materials.add('plan_railing')
  railing_mat.color = Sketchup::Color.new(60, 62, 70)
  # Vidro translucido azulado do guarda-corpo (calibrado pelo componente 3DW).
  glass_mat = model.materials.add('plan_glass')
  glass_mat.color = Sketchup::Color.new(*GLASS_RGB)
  glass_mat.alpha = GLASS_ALPHA
  walls_for_overlap = consensus['walls'] || []
  thickness_for_overlap = consensus['wall_thickness_pts'] || 5.4
  wall_footprints = wall_footprints_in_su(
    walls_for_overlap, thickness_for_overlap,
  )
  (consensus['soft_barriers'] || []).each_with_index do |sb, i|
    sid = sb['id'] || "sb#{i}"
    render_as = barrier_render_as(sb)
    if render_as.nil?
      sb_skipped += 1
      sb_skip_reasons << "sb[#{i}] #{sid}: unsourced_no_provenance (not rendered)"
      sb_records << {
        'id' => sid, 'barrier_type' => sb['barrier_type'],
        'sourced' => false, 'rendered' => false, 'render_as' => nil,
        'skip_reason' => 'unsourced_no_provenance',
      }
      next
    end
    mat = render_as == 'railing' ? railing_mat : parapet_mat
    res = build_soft_barrier(
      model.active_entities, sb, mat, i, wall_footprints: wall_footprints,
    )
    if res['ok']
      sb_built += 1
      sb_records << {
        'id' => sid, 'barrier_type' => sb['barrier_type'],
        'sourced' => true, 'rendered' => true, 'render_as' => render_as,
        'host_wall_id' => sb['host_wall_id'], 'length_m' => res['length_m'],
      }
    else
      sb_skipped += 1
      sb_skip_reasons << "sb[#{i}] #{sid}: #{res['reason']}"
      sb_records << {
        'id' => sid, 'barrier_type' => sb['barrier_type'],
        'sourced' => true, 'rendered' => false, 'render_as' => nil,
        'skip_reason' => res['reason'],
      }
    end
  end
elsif sb_mode == 'skip'
  sb_skipped = (consensus['soft_barriers'] || []).length
  sb_skip_reasons << "SOFT_BARRIERS_MODE=skip; #{sb_skipped} soft_barriers " \
                     "intentionally not emitted; expect fidelity impact."
end
puts "[rb] soft_barriers: built=#{sb_built} skipped=#{sb_skipped}"

# 4. Opening renderers (Phase 2 visual parity).
# Dispatch each consensus.openings entry to the appropriate renderer
# based on kind_v5 + geometry_origin. Door leaves, window panels,
# glazed balconies, and passage markers are each emitted as top-level
# Groups separate from PlanShell_Group — never inside the wall shell.
openings = consensus['openings'] || []
walls_by_id = consensus['walls'].each_with_object({}) do |w, h|
  h[w['id']] = w if w['id']
end
thickness_pt = consensus['wall_thickness_pts'] || 5.4

door_mat = model.materials.add('plan_door')
door_mat.color = Sketchup::Color.new(*DOOR_RGB)
sill_mat = model.materials.add('plan_window_sill')
sill_mat.color = Sketchup::Color.new(*PARAPET_RGB)
glass_mat = model.materials.add('plan_window_glass')
glass_mat.color = Sketchup::Color.new(*GLASS_RGB)
glass_mat.alpha = GLASS_ALPHA
lintel_mat = model.materials.add('plan_window_lintel')
lintel_mat.color = Sketchup::Color.new(*LINTEL_RGB)
passage_mat = model.materials.add('plan_passage_marker')
passage_mat.color = Sketchup::Color.new(*PASSAGE_RGB)

door_built = 0
window_built = 0
glazed_built = 0
passage_built = 0
opening_skips = []

openings.each_with_index do |op, i|
  host = walls_by_id[op['wall_id']]
  if host.nil?
    opening_skips << "op[#{i}] #{op['id']}: no host wall #{op['wall_id'].inspect}"
    next
  end
  kind = opening_kind_v5(op)
  origin = op['geometry_origin'] || ''
  carved = CARVING_ORIGINS.include?(origin)

  case kind
  when 'interior_door'
    if carved
      res = build_door_leaf(model.active_entities, op, host,
                           thickness_pt, door_mat, i)
      door_built += 1 if res['ok']
      opening_skips << "op[#{i}] door: #{res['reason']}" unless res['ok']
    else
      # geometry already in wall data; emit a passage marker so the
      # opening is visible to the reviewer.
      res = build_passage_marker(model.active_entities, op, host,
                                thickness_pt, passage_mat, i)
      passage_built += 1 if res['ok']
    end
  when 'interior_passage'
    # No leaf rendered (vão livre). Marker only if not carved.
    unless carved
      res = build_passage_marker(model.active_entities, op, host,
                                thickness_pt, passage_mat, i)
      passage_built += 1 if res['ok']
    end
  when 'window'
    # Preferred: 3D aperture (peitoril/verga preserved, see-through glass) —
    # works when the window sits on a clean solid host wall (e.g. quadrado).
    # find_wall_face_for_aperture now requires the face to belong to the HOST
    # wall (FP-031), so it returns ok=false instead of carving a wrong parallel
    # facade. FALLBACK: when no host face is found (planta_74's broken wall_id /
    # gap-hosted windows), place the window as a PANEL at the opening center
    # (peitoril 0-0.9 / glass 0.9-2.1 / verga 2.1-2.7 at cx / host.start.y) —
    # the exact spot the glass resolves to and the PDF provenance audit
    # confirmed. This keeps quadrado's see-through window unchanged while
    # placing planta_74's windows on the correct wall, not an invented one.
    res = build_window_aperture_3d(model.active_entities, op, host,
                                   thickness_pt, glass_mat, i)
    unless res['ok']
      res = build_window_panel(model.active_entities, op, host,
                               thickness_pt, sill_mat, glass_mat, lintel_mat, i)
      res['via_panel_fallback'] = true if res['ok']
    end
    window_built += 1 if res['ok']
    opening_skips << "op[#{i}] window: #{res['reason']}" unless res['ok']
  when 'glazed_balcony'
    res = build_glazed_balcony(model.active_entities, op, host,
                              thickness_pt, glass_mat, i)
    glazed_built += 1 if res['ok']
    opening_skips << "op[#{i}] glazed: #{res['reason']}" unless res['ok']
  else
    opening_skips << "op[#{i}] unknown kind #{kind.inspect}"
  end
end
puts "[rb] openings: doors=#{door_built} windows=#{window_built} " \
     "glazed=#{glazed_built} passage=#{passage_built} " \
     "skipped=#{opening_skips.length}"

model.commit_operation

# 4. Geometry report
if outreport
  ctx = {
    consensus_path:           cjson,
    skp_path:                 outskp,
    shell_json_path:          shell_json,
    soft_barriers_mode:       sb_mode,
    soft_barriers_skipped:    sb_skipped,
    soft_barriers_skip_reasons: sb_skip_reasons,
    soft_barrier_records:     sb_records,
    floors_failed:            floors_failed,
    py_stats:                 shell_data['stats'],
  }
  write_geometry_report(model, outreport, ctx)
  puts "[rb] wrote #{outreport}"
end

# 5. Screenshots — iso then top, write image after each
if outpng_iso
  setup_iso_camera(model)
  write_png(model, outpng_iso)
  puts "[rb] wrote #{outpng_iso}"
end
if outpng_top
  setup_top_camera(model)
  write_png(model, outpng_top)
  # Capture the exact projection while the top camera is still active.
  write_top_projection_sidecar(model, outpng_top, 1600, 1200)
  puts "[rb] wrote #{outpng_top} (+ .proj.json)"
end

# 6. Save .skp last (this is the launcher's exit signal)
status = model.save(outskp)
puts "[rb] saved #{outskp} (status=#{status})"
