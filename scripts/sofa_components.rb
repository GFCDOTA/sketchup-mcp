# sofa_components.rb — componentes semanticos: combinam primitivas em PARTES de
# sofa, parametrizados pelo config + layout (calculado pelo gerador). Aqui moram
# as FAMILIAS (arm_style, back_style, seat_style, base_style, leg_style, seam).
#
# Cada componente recebe (ent, cfg, lay, mats). `lay` = hash (symbol keys) em
# METROS com posicoes ja calculadas. Nenhuma medida de "um sofa unico" hardcoded:
# tudo vem do layout.

require_relative 'sofa_primitives'

module SofaComponents
  SP = SofaPrimitives
  module_function

  # ---- COSTURA: policy (subordinada a forma; default OFF) ------------------
  def build_seam_system(cfg)
    case cfg['seam_style']
    when 'simple'        then { enabled: true,  subtle: true }
    when 'piping_subtle' then { enabled: true,  subtle: true }
    else                      { enabled: false, subtle: true }
    end
  end

  # ---- PES -----------------------------------------------------------------
  def build_leg_set(ent, cfg, lay, mats)
    style = cfg['leg_style']
    return if style == 'none' || lay[:leg_h] <= 0.001
    ins = lay[:leg_inset]
    half = lay[:leg_half]
    z0 = 0.0
    z1 = lay[:leg_h]
    w = lay[:w]
    d = lay[:d]
    xs = [ins + half, w - ins - half]
    ys = [ins + half, d - ins - half]
    i = 0
    xs.product(ys).each do |cx, cy|
      i += 1
      nm = "leg_#{i}"
      case style
      when 'tapered_wood' then SP.tapered_leg(ent, cx, cy, half, z0, z1, taper: 0.35, mat_obj: mats[:leg], name: nm)
      when 'block'        then SP.block_leg(ent, cx, cy, half, z0, z1, mat_obj: mats[:leg], name: nm)
      when 'metal_stub'   then SP.cylinder_or_tube_subtle(ent, cx, cy, half * 0.6, z0, z1, mat_obj: mats[:leg], name: nm)
      else                     SP.tapered_leg(ent, cx, cy, half, z0, z1, mat_obj: mats[:leg], name: nm)
      end
    end
  end

  # ---- BASE / PLINTO -------------------------------------------------------
  def build_base_module(ent, cfg, lay, mats)
    style = cfg['base_style']
    x0 = lay[:seat_x0]
    x1 = lay[:seat_x1]
    bt = lay[:base_top]
    case style
    when 'plinth'
      # plinto recuado ate o chao (kick), sem pernas; recuo em todos os lados
      ins = 0.05
      SP.rounded_box(ent, x0 + ins, lay[:base_front] + ins, x1 - ins, lay[:d] - ins,
                     0.0, bt, r: 0.02, mat_obj: mats[:base], name: 'base_plinth')
    when 'exposed_legs'
      # rail fino sobre as pernas (deixa as pernas protagonistas)
      SP.rounded_box(ent, x0, lay[:base_front], x1, lay[:d], lay[:leg_h], bt,
                     r: 0.02, mat_obj: mats[:base], name: 'base_rail')
    else # recessed
      SP.rounded_box(ent, x0, lay[:base_front], x1, lay[:d], lay[:leg_h], bt,
                     r: 0.025, mat_obj: mats[:base], name: 'base_recessed')
    end
  end

  # ---- ASSENTO -------------------------------------------------------------
  def build_seat_module(ent, cfg, lay, mats, seam)
    soft = lay[:softness]
    yf = lay[:seat_front]
    yb = lay[:seat_back]
    z0 = lay[:seat_z0]
    z1 = lay[:seat_h]
    breath = 0.006 # folga pequena (almofadas respiram)
    if cfg['seat_style'] == 'bench'
      SP.seat_cushion_primitive(ent, lay[:seat_x0] + breath, yf, lay[:seat_x1] - breath, yb,
                                z0, z1, softness: soft, mat_obj: mats[:fab],
                                name: 'seat_bench', seam: seam, seam_mat: mats[:seam])
    else # split
      n = [lay[:seats], 1].max
      gap = lay[:gap]
      total = lay[:seat_x1] - lay[:seat_x0]
      cw = (total - gap * (n - 1)) / n
      n.times do |i|
        sx0 = lay[:seat_x0] + i * (cw + gap)
        SP.seat_cushion_primitive(ent, sx0 + breath, yf, sx0 + cw - breath, yb,
                                  z0, z1, softness: soft, mat_obj: mats[:fab],
                                  name: "seat_#{i + 1}", seam: seam, seam_mat: mats[:seam])
      end
    end
  end

  # ---- ENCOSTO (com rake aplicado no grupo) --------------------------------
  def _rake!(g, lay)
    return unless g
    deg = lay[:rake_deg] || 9.0
    pivot = Geom::Point3d.new(0, lay[:back_front] * SP::M, lay[:back_z0] * SP::M)
    t = Geom::Transformation.rotation(pivot, Geom::Vector3d.new(1, 0, 0), -deg * Math::PI / 180.0)
    g.transform!(t)
  end

  def build_back_module(ent, cfg, lay, mats, seam)
    soft = lay[:softness]
    yf = lay[:back_front]
    yb = lay[:back_back]
    z0 = lay[:back_z0]
    z1 = lay[:back_top]
    style = cfg['back_style']
    breath = 0.006
    if style == 'tight'
      # encosto firme e continuo (uma peca), crown menor
      g = SP.back_cushion_primitive(ent, lay[:seat_x0] + breath, yf, lay[:seat_x1] - breath, yb,
                                    z0, z1, softness: 'low', mat_obj: mats[:back],
                                    name: 'back_tight', seam: seam, seam_mat: mats[:seam])
      _rake!(g, lay)
    else
      n = [lay[:seats], 1].max
      gap = lay[:gap]
      total = lay[:seat_x1] - lay[:seat_x0]
      cw = (total - gap * (n - 1)) / n
      n.times do |i|
        bx0 = lay[:seat_x0] + i * (cw + gap)
        g = if style == 'pillow'
              SP.pillow_primitive(ent, bx0 + breath, yf, bx0 + cw - breath, yb,
                                  z0, z1, softness: 'high', mat_obj: mats[:back], name: "back_pillow_#{i + 1}")
            else # cushion
              SP.back_cushion_primitive(ent, bx0 + breath, yf, bx0 + cw - breath, yb,
                                        z0, z1, softness: soft, mat_obj: mats[:back],
                                        name: "back_#{i + 1}", seam: seam, seam_mat: mats[:seam])
            end
        _rake!(g, lay)
      end
    end
  end

  # ---- BRACOS --------------------------------------------------------------
  def build_arm_module(ent, cfg, lay, side, mats)
    style = cfg['arm_style']
    return if style == 'none' || lay[:arm_w] <= 0.001
    aw = lay[:arm_w]
    x0, x1 = side == :left ? [0.0, aw] : [lay[:w] - aw, lay[:w]]
    y0 = 0.0
    y1 = lay[:d]
    z0 = lay[:leg_h]
    z1 = lay[:arm_h]
    nm = "arm_#{side}"
    # GPT ciclo10 (TOP_FIX braco): profile=lounge -> braco com TOPO ROLADO CONTINUO
    # (crowned_box, sem tampa plana / sem anel-chanfro). Traco de CLASSE; NAO troca
    # arm_style do config, so a PRIMITIVA de render. slim/track/box (hoje rounded_box
    # de topo plano) passam a rolar; wide/rolled_soft ja tem topo continuo -> ficam
    # no case normal (zero regressao).
    if cfg['profile'] == 'lounge' && %w[slim track box].include?(style)
      SP.rolled_arm_primitive(ent, x0, y0, x1, y1, z0, z1, softness: lay[:softness], mat_obj: mats[:fab], name: nm)
      return
    end
    case style
    when 'slim'
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: 0.03, top_round: 0.03, mat_obj: mats[:fab], name: nm)
    when 'track'
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: 0.035, top_round: 0.05, mat_obj: mats[:fab], name: nm)
    when 'box'
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: 0.02, top_round: 0.025, mat_obj: mats[:fab], name: nm)
    when 'wide'
      SP.soft_rounded_box(ent, x0, y0, x1, y1, z0, z1, softness: lay[:softness], mat_obj: mats[:fab], name: nm)
    when 'rolled_soft'
      SP.rolled_arm_primitive(ent, x0, y0, x1, y1, z0, z1, softness: lay[:softness], mat_obj: mats[:fab], name: nm)
    else
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: 0.035, top_round: 0.05, mat_obj: mats[:fab], name: nm)
    end
  end
end
