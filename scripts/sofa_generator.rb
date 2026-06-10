# sofa_generator.rb — gerador parametrico da CLASSE sofa.
# Carrega config -> valida contra schema (clamp+warn ou FAIL explicito) ->
# calcula layout -> monta modulos -> materiais -> cameras -> SKP + renders +
# validation.json (gates objetivos; ASSET/SOFTNESS/CAIXOTAO ficam PENDENTE p/
# review visual externo — o gerador NUNCA autojulga isso).

require 'json'
require 'fileutils'
require_relative 'sofa_primitives'
require_relative 'sofa_components'

module SofaGenerator
  SP = SofaPrimitives
  SC = SofaComponents
  module_function

  # ---- validacao + defaults ------------------------------------------------
  def validate(cfg, schema)
    warnings = []
    errors = []
    schema['enums'].each do |k, allowed|
      errors << "enum invalido #{k}=#{cfg[k]}" if !cfg[k].nil? && !allowed.include?(cfg[k])
    end
    schema['defaults'].each { |k, v| cfg[k] = v if cfg[k].nil? }
    if cfg['arm_width_m'].nil?
      cfg['arm_width_m'] = schema['arm_width_by_style_m'][cfg['arm_style']] || 0.22
    end
    cfg['arm_width_m'] = 0.0 if cfg['arm_style'] == 'none'
    cfg['leg_style'] = 'none' if cfg['base_style'] == 'plinth'
    cfg['leg_height_m'] = 0.0 if cfg['leg_style'] == 'none'
    cfg['leg_height_m'] ||= schema['defaults']['leg_height_m']

    schema['ranges_m'].each do |k, lohi|
      next if cfg[k].nil?
      lo, hi = lohi
      if cfg[k] < lo
        warnings << "#{k}=#{cfg[k]}<#{lo} (clamp)"; cfg[k] = lo
      elsif cfg[k] > hi
        warnings << "#{k}=#{cfg[k]}>#{hi} (clamp)"; cfg[k] = hi
      end
    end
    %w[id family seat_count overall_width_m overall_depth_m overall_height_m].each do |k|
      errors << "faltando #{k}" if cfg[k].nil?
    end

    pr = schema['proportion_rules']
    if cfg['arm_style'] != 'none'
      maxw = cfg['overall_width_m'] * pr['arm_width_max_frac_of_width']
      if cfg['arm_width_m'] > maxw
        warnings << "arm_width #{cfg['arm_width_m']}>#{maxw.round(2)} (clamp proporcao)"
        cfg['arm_width_m'] = maxw
      end
      seats = [cfg['seat_count'], 1].max
      clear = (cfg['overall_width_m'] - 2 * cfg['arm_width_m']) / seats
      if clear < pr['min_seat_clear_width_per_seat_m']
        cfg['arm_width_m'] = [(cfg['overall_width_m'] - pr['min_seat_clear_width_per_seat_m'] * seats) / 2.0, 0.08].max
        warnings << "arm_width reduzido p/ garantir assento util (clear<#{pr['min_seat_clear_width_per_seat_m']})"
      end
    end
    well = cfg['arm_height_m'].to_f - cfg['seat_height_m'].to_f
    warnings << "well braco-assento #{well.round(2)}m>#{pr['seat_top_below_arm_top_max_m']} (assento pode ler fundo)" if well > pr['seat_top_below_arm_top_max_m']
    cfg['seat_cushion_thickness_m'] = [cfg['seat_cushion_thickness_m'], pr['seat_cushion_thickness_min_m']].max
    cfg['back_thickness_m'] = [cfg['back_thickness_m'], pr['back_thickness_min_m']].max

    [errors, warnings]
  end

  # ---- layout (metros) -----------------------------------------------------
  def compute_layout(cfg)
    w = cfg['overall_width_m'].to_f
    d = cfg['overall_depth_m'].to_f
    h = cfg['overall_height_m'].to_f
    seat_h = cfg['seat_height_m'].to_f
    cush_t = cfg['seat_cushion_thickness_m'].to_f
    back_t = cfg['back_thickness_m'].to_f
    arm_w = cfg['arm_width_m'].to_f
    arm_h = cfg['arm_height_m'].to_f
    leg_h = cfg['leg_height_m'].to_f
    seat_d = cfg['seat_depth_m'].to_f
    rake = cfg['back_rake_deg'].to_f
    # GPT ciclo1 (TOP_FIX perfil): lounge = silhueta mais baixa/profunda/reclinada.
    # Traco de CLASSE (qualquer caso profile=lounge herda), nao ajuste de 1 exemplar.
    if cfg['profile'] == 'lounge'
      arm_h = [arm_h, seat_h + 0.06].min   # GPT ciclo10: braco lounge BAIXO -> topo ~6cm acima do assento (rente, nao parede)
      arm_w = [arm_w * 0.82, 0.10].max if arm_w > 0.001  # GPT ciclo10: braco lounge mais FINO de frente (~18%, relacional); no-arm preservado
      rake = [rake, 13.0].max              # mais recline
      leg_h = [leg_h, 0.02].min            # GPT ciclo9/12: pes baixos (reveal 4->2cm no side); .min preservado (cfg menor vence)
    end
    base_top = seat_h - cush_t
    seat_back = d - back_t
    seat_front = [seat_back - seat_d, arm_w * 0.0 + 0.10].max
    base_rec = cfg['base_style'] == 'plinth' ? 0.04 : 0.06
    # GPT ciclo12: base lounge recua ~2cm ATRAS da frente do assento -> mata o degrau/ledge
    # frontal e tuca a faixa sob o balanco da almofada (leitura monolitica). Relacional a
    # seat_front (qualquer lounge herda); max(...,base_rec) protege sofa raso de inverter.
    base_front_eff = cfg['profile'] == 'lounge' ? [seat_front - 0.02, base_rec].max : base_rec
    {
      w: w, d: d, h: h, seats: [cfg['seat_count'].to_i, 1].max, gap: 0.018,
      leg_h: leg_h,
      leg_inset: (cfg['profile'] == 'lounge' ? [cfg['leg_inset_m'].to_f, 0.085].max : cfg['leg_inset_m'].to_f),
      leg_half: (cfg['profile'] == 'lounge' ? 0.030 : 0.045),  # lounge: pes menores e recuados (GPT ciclo9)
      base_top: base_top, base_front: base_front_eff,
      base_z0: ((cfg['profile'] == 'lounge' && cfg['base_style'] == 'recessed') ? [leg_h - 0.014, 0.006].max : leg_h),  # GPT ciclo12: lounge recessed -> base desce a ~o chao (SO recessed; plinth/exposed_legs intactos)
      seat_h: seat_h, seat_z0: base_top, seat_front: seat_front, seat_back: seat_back,
      arm_w: arm_w, arm_h: arm_h,
      back_z0: seat_h - 0.08, back_top: h, back_front: seat_back - 0.03, back_back: d,
      seat_x0: arm_w, seat_x1: w - arm_w,
      rake_deg: rake,
      softness: cfg['softness_level']
    }
  end

  # ---- materiais -----------------------------------------------------------
  # Paletas de tecido (aprendido dos refs 3DW: o ESCURO texturizado e metade do
  # "parece real" — o linho claro chapado era um gap). material_style escolhe.
  PALETTES = {
    'light_linen'   => { fab: [210, 200, 185], base: [150, 142, 128], back: [196, 187, 172], seam: [150, 142, 128] },
    'mid_gray'      => { fab: [120, 122, 126], base: [86, 88, 92],    back: [110, 112, 116], seam: [96, 98, 102] },
    'dark_charcoal' => { fab: [58, 60, 64],    base: [38, 40, 42],    back: [70, 72, 76],    seam: [46, 48, 52] }
  }.freeze

  def build_materials(model, cfg)
    ms = cfg['material_style'] || 'light_linen'
    pal = PALETTES[ms] || PALETTES['light_linen']
    leg_rgb = case cfg['leg_style']
              when 'block' then [70, 70, 72]
              when 'metal_stub' then [120, 122, 128]
              else [96, 66, 44]
              end
    {
      fab:  SP.mat(model, "fab_#{ms}",  pal[:fab]),
      base: SP.mat(model, "base_#{ms}", pal[:base]),
      back: SP.mat(model, "back_#{ms}", pal[:back]),
      seam: SP.mat(model, "seam_#{ms}", pal[:seam]),
      leg:  SP.mat(model, 'sofa_leg', leg_rgb)
    }
  end

  # ---- montagem ------------------------------------------------------------
  def assemble(model, cfg, lay)
    mats = build_materials(model, cfg)
    seam = SC.build_seam_system(cfg)[:enabled]
    root = model.active_entities.add_group
    root.name = "Sofa_#{cfg['id']}"
    e = root.entities
    SC.build_leg_set(e, cfg, lay, mats)
    SC.build_base_module(e, cfg, lay, mats)
    SC.build_seat_module(e, cfg, lay, mats, seam)
    SC.build_back_module(e, cfg, lay, mats, seam)
    SC.build_arm_module(e, cfg, lay, :left, mats)
    SC.build_arm_module(e, cfg, lay, :right, mats)
    root
  end

  # ---- cameras (enquadramento DETERMINISTICO — nao corta, nao over-zoom) ---
  ASPECT = 1600.0 / 1200.0

  def _shoot(view, eye, target, up, persp, ph, pw, dir, name)
    cam = Sketchup::Camera.new(eye, target, up)
    cam.perspective = persp
    unless persp
      cam.height = [ph, pw / ASPECT].max * 1.16  # margem: nao cortar pes/bracos
    end
    view.camera = cam
    view.zoom_extents if persp
    view.write_image(filename: File.join(dir, name), width: 1600, height: 1200,
                     antialias: true, transparent: false)
  end

  def render_views(model, dir)
    FileUtils.mkdir_p(dir)
    view = model.active_view
    bb = model.bounds
    c = bb.center
    dg = bb.diagonal
    ex = bb.max.x - bb.min.x
    ey = bb.max.y - bb.min.y
    ez = bb.max.z - bb.min.z
    up = Geom::Vector3d.new(0, 0, 1)
    _shoot(view, Geom::Point3d.new(c.x, bb.min.y - dg, c.z), c, up, false, ez, ex, dir, 'front.png')
    _shoot(view, Geom::Point3d.new(bb.max.x + dg, c.y, c.z), c, up, false, ez, ey, dir, 'side.png')
    _shoot(view, Geom::Point3d.new(c.x, c.y, bb.max.z + dg * 2), c, Geom::Vector3d.new(0, 1, 0), false, ey, ex, dir, 'top.png')
    _shoot(view, Geom::Point3d.new(bb.max.x + dg * 0.85, bb.min.y - dg * 0.95, c.z + dg * 0.65), c, up, true, ez, ex, dir, 'three_quarter.png')
  end

  # ---- gerar UM caso (limpa modelo, monta, renderiza, salva, valida) -------
  def generate(cfg, schema, out_dir)
    SP::LOG.clear
    model = Sketchup.active_model
    model.entities.clear!
    errors, warnings = validate(cfg, schema)
    FileUtils.mkdir_p(out_dir)
    if !errors.empty?
      vj = { id: cfg['id'], status: 'FAIL', errors: errors, warnings: warnings }
      File.write(File.join(out_dir, 'validation.json'), JSON.pretty_generate(vj))
      return vj
    end
    lay = compute_layout(cfg)
    root = assemble(model, cfg, lay)
    render_views(model, out_dir)
    skp = File.join(out_dir, "#{cfg['id']}.skp")
    model.save(skp)
    bb = root.bounds
    bbox_m = [((bb.max.x - bb.min.x) / SP::M).round(3),
              ((bb.max.y - bb.min.y) / SP::M).round(3),
              ((bb.max.z - bb.min.z) / SP::M).round(3)]
    parts = root.entities.grep(Sketchup::Group).map(&:name)
    vj = {
      id: cfg['id'], status: 'OK', family: cfg['family'],
      bbox_m: bbox_m, n_parts: parts.size, parts: parts,
      warnings: warnings, errors: [],
      gates_objetivos: {
        'PIPELINE_PASS' => true, 'SCHEMA_PASS' => true,
        'COMPONENTS_PASS' => (parts.size >= 4),
        'PROPORTION_PASS' => warnings.none? { |x| x.include?('clamp proporcao') },
        'BLOCKOUT_PASS' => 'PENDING_VISUAL',
        'ASSET_PASS' => 'PENDING_VISUAL', 'SOFTNESS_PASS' => 'PENDING_VISUAL',
        'CAIXOTAO_FAIL' => 'PENDING_VISUAL', 'DETAIL_RESTRAINT_PASS' => 'PENDING_VISUAL'
      },
      primitives_log: SP::LOG.dup,
      renders: %w[front.png side.png top.png three_quarter.png],
      skp: skp
    }
    File.write(File.join(out_dir, 'validation.json'), JSON.pretty_generate(vj))
    vj
  end

  def load_schema(path)
    JSON.parse(File.read(path))
  end
end
