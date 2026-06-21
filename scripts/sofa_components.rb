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
      # GPT ciclo12/13: z0 = base_z0 (lounge desce a ~o chao). O braco TAMBEM segue base_z0
      # (ciclo13) -> bottom continuo na frente. Outros estilos: base_z0 == leg_h (no-op).
      SP.rounded_box(ent, x0, lay[:base_front], x1, lay[:d], lay[:base_z0], bt,
                     r: 0.025, mat_obj: mats[:base], name: 'base_recessed')
    end
  end

  # ---- ASSENTO -------------------------------------------------------------
  def build_seat_module(ent, cfg, lay, mats, seam)
    soft = lay[:softness]
    # GPT generalizacao: piso de volume p/ standard nao ler chapado em medium. Gated p/
    # NAO tocar lounge (floor 0.0 = no-op byte-igual nele). 0.058 fica entre medium(0.050)
    # e high(0.070): low/medium sobem, high fica igual (max vence).
    seat_floor = (cfg['profile'] == 'lounge') ? 0.0 : 0.058
    # GPT TOP_FIX (micro-irregularidade controlada): cada almofada herda um jitter seeded
    # pelo PROPRIO indice -> quebra a uniformidade CAD sem des-convergir a forma. default
    # 0.0 = no-op byte-igual (caller so opta via cfg['cushion_jitter']). Cap em 1.0.
    cjit = [[(cfg['cushion_jitter'] || 0.0).to_f, 0.0].max, 1.0].min
    yf = lay[:seat_front]
    yb = lay[:seat_back]
    z0 = lay[:seat_z0]
    z1 = lay[:seat_h]
    breath = 0.006 # folga pequena (almofadas respiram)
    if cfg['seat_style'] == 'bench'
      SP.seat_cushion_primitive(ent, lay[:seat_x0] + breath, yf, lay[:seat_x1] - breath, yb,
                                z0, z1, softness: soft, mat_obj: mats[:fab], min_crown: seat_floor,
                                name: 'seat_bench', seam: seam, seam_mat: mats[:seam],
                                jitter: cjit, seed: 101)
    else # split
      n = [lay[:seats], 1].max
      gap = lay[:gap]
      total = lay[:seat_x1] - lay[:seat_x0]
      cw = (total - gap * (n - 1)) / n
      n.times do |i|
        sx0 = lay[:seat_x0] + i * (cw + gap)
        SP.seat_cushion_primitive(ent, sx0 + breath, yf, sx0 + cw - breath, yb,
                                  z0, z1, softness: soft, mat_obj: mats[:fab], min_crown: seat_floor,
                                  name: "seat_#{i + 1}", seam: seam, seam_mat: mats[:seam],
                                  jitter: cjit, seed: 101 + i)
      end
    end

    # --- CHAISE: fileira frontal de pad estofado (gated family=='chaise') ----
    # GPT (generalizacao): a parte chaise lia como PLATAFORMA/SLAB. Cobre a faixa
    # frontal (chaise_pad_front..seat_front-gap) com ESTOFADO na MESMA linguagem
    # SoftCushion do assento (mesma divisao em X/breath/z0..z1). O tuck-gap em Y gera
    # o sulco -> 2 PROFUNDIDADES de assento, nao 1 almofada gigante chapada. O slab de
    # base recessed fica embaixo como frame (escondido). lounge/outras familias = no-op.
    pf = lay[:chaise_pad_front]
    if cfg['family'] == 'chaise' && pf && pf < yf
      pyb = yf - lay[:gap]
      # seed +200: a fileira chaise frontal NAO espelha a irregularidade do assento
      # de tras (senao a uniformidade volta de outra forma). cjit=0 -> ainda no-op.
      if cfg['seat_style'] == 'bench'
        SP.seat_cushion_primitive(ent, lay[:seat_x0] + breath, pf, lay[:seat_x1] - breath, pyb,
                                  z0, z1, softness: soft, mat_obj: mats[:fab], min_crown: seat_floor,
                                  name: 'seat_chaise_front', seam: seam, seam_mat: mats[:seam],
                                  jitter: cjit, seed: 201)
      else
        n = [lay[:seats], 1].max
        gap = lay[:gap]
        total = lay[:seat_x1] - lay[:seat_x0]
        cw = (total - gap * (n - 1)) / n
        n.times do |i|
          sx0 = lay[:seat_x0] + i * (cw + gap)
          SP.seat_cushion_primitive(ent, sx0 + breath, pf, sx0 + cw - breath, pyb,
                                    z0, z1, softness: soft, mat_obj: mats[:fab], min_crown: seat_floor,
                                    name: "seat_chaise_front_#{i + 1}", seam: seam, seam_mat: mats[:seam],
                                    jitter: cjit, seed: 201 + i)
        end
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
    # GPT generalizacao: piso de VOLUME FRONTAL + tuck pro encosto standard (so quem opta).
    # 0.0 no lounge (no-op). 0.050 sobe o tight (hardcoded 'low'=0.030) e low/medium; high igual.
    back_floor = (cfg['profile'] == 'lounge') ? 0.0 : 0.050
    # GPT TOP_FIX (micro-irregularidade): encostos tambem variam por almofada (seed 301+,
    # separado dos assentos 101+, p/ nao espelhar). default 0.0 = no-op byte-igual.
    bjit = [[(cfg['cushion_jitter'] || 0.0).to_f, 0.0].max, 1.0].min
    yf = lay[:back_front]
    yb = lay[:back_back]
    z0 = lay[:back_z0]
    z1 = lay[:back_top]
    style = cfg['back_style']
    breath = 0.006
    if style == 'tight'
      # encosto firme e continuo (uma peca), crown menor + floor de volume frontal (GPT)
      g = SP.back_cushion_primitive(ent, lay[:seat_x0] + breath, yf, lay[:seat_x1] - breath, yb,
                                    z0, z1, softness: 'low', mat_obj: mats[:back], min_crown: back_floor,
                                    name: 'back_tight', seam: seam, seam_mat: mats[:seam],
                                    jitter: bjit, seed: 301)
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
                                        z0, z1, softness: soft, mat_obj: mats[:back], min_crown: back_floor,
                                        name: "back_#{i + 1}", seam: seam, seam_mat: mats[:seam],
                                        jitter: bjit, seed: 301 + i)
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
    # GPT ciclo13: braco desce ate o MESMO fundo da base (base_z0), nao leg_h -> bottom
    # CONTINUO na frente inteira (sem ressalto/poste nas extremidades; lateral = bloco
    # baixo continuo rente ao chao). base_z0 == leg_h fora de lounge+recessed (no-op).
    # Os pes ficam absorvidos dentro do volume do braco (invisiveis), sem flutuar.
    z0 = lay[:base_z0]
    z1 = lay[:arm_h]
    nm = "arm_#{side}"
    # GPT ciclo10->11 (TOP_FIX braco): profile=lounge -> braco = BLOCO LATERAL BAIXO
    # e LIMPO (ref modern dark), NAO um tubo. Ciclo10 usou crowned_box e rolou DEMAIS:
    # numa peca estreita(x)-e-longa(y) o domo vira meia-cana/poste na frente. Ciclo11
    # corrige -> topo PLANO levemente amaciado (chanfro sutil, sem domo), frente
    # VERTICAL continua (sem poste), arestas verticais com raio limpo. A altura baixa
    # (arm_h=seat_h+0.06) + afinamento (arm_w*0.82) ja convergiram e ficam. Traco de
    # CLASSE; NAO troca arm_style do config, so a primitiva. wide/rolled_soft ja sao
    # macios -> seguem no case normal.
    if cfg['profile'] == 'lounge' && %w[slim track box].include?(style)
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: 0.05, top_round: 0.045, mat_obj: mats[:fab], name: nm)
      return
    end
    # GPT generalizacao: braco STANDARD slim/track/box ganha topo/arestas mais MACIAS
    # (melhor integracao braco<->corpo) SO via r/top_round -> NAO move/baixa/aterra o braco
    # (x/y/z e arm_h intactos = sem postura lounge). lounge slim/track/box ja retornou acima;
    # lounge so chega aqui via wide/rolled_soft, onde std=false -> valores atuais (no-op).
    std = cfg['profile'] != 'lounge'
    case style
    when 'slim'
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: (std ? 0.045 : 0.03), top_round: (std ? 0.05 : 0.03), mat_obj: mats[:fab], name: nm)
    when 'track'
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: (std ? 0.05 : 0.035), top_round: (std ? 0.07 : 0.05), mat_obj: mats[:fab], name: nm)
    when 'box'
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: (std ? 0.03 : 0.02), top_round: (std ? 0.04 : 0.025), mat_obj: mats[:fab], name: nm)
    when 'wide'
      SP.soft_rounded_box(ent, x0, y0, x1, y1, z0, z1, softness: lay[:softness], mat_obj: mats[:fab], name: nm)
    when 'rolled_soft'
      SP.rolled_arm_primitive(ent, x0, y0, x1, y1, z0, z1, softness: lay[:softness], mat_obj: mats[:fab], name: nm)
    else
      SP.rounded_box(ent, x0, y0, x1, y1, z0, z1, r: 0.035, top_round: 0.05, mat_obj: mats[:fab], name: nm)
    end
  end
end
