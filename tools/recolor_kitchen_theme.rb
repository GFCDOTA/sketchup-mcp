# recolor_kitchen_theme.rb — BAKEIA um TEMA (cor + textura) nos materiais ph_kc_* do .skp
# carregado e SALVA num novo arquivo. NAO rebuilda geometria, NAO move nada — so troca a pele
# dos materiais da cozinha. Cores levemente levantadas vs o V-Ray (shading flat do SketchUp nao
# tem reflexo -> preto puro vira borrao; charcoal le melhor). ENV: KITCHEN_THEME, THEME_OUT,
# VRAY_TEX_DIR, RECOLOR_LOG.
begin
  m = Sketchup.active_model
  theme = ENV['KITCHEN_THEME'] || 'black_wood_gold'
  tex = ENV['VRAY_TEX_DIR']
  cols = {}
  texs = {}

  if theme == 'black_wood_gold'
    blk = [44, 44, 48]                                   # charcoal (le no flat shading)
    %w[corpo porta gaveta corpo_sup porta_sup filler cuba].each { |k| cols["ph_kc_#{k}"] = blk }
    cols['ph_kc_geladeira']  = [62, 65, 72]              # inox dark
    cols['ph_kc_torneira']   = [26, 26, 30]
    cols['ph_kc_boca']       = [26, 26, 30]
    cols['ph_kc_vidro']      = [20, 20, 24]
    cols['ph_kc_soculo']     = [40, 41, 45]
    cols['ph_kc_puxador']    = [160, 128, 74]            # bronze
    cols['ph_kc_led']        = [255, 242, 214]
    cols['ph_kc_tampo']      = [58, 52, 48]              # pedra escura
    cols['ph_kc_backsplash'] = [64, 55, 47]
    cols['ph_kc_niche_wood'] = [120, 72, 42]            # madeira quente
    cols['ph_kc_board']      = [120, 72, 42]
    texs['ph_kc_backsplash'] = 'stone_gold.png'         # pedra com veio dourado
    texs['ph_kc_niche_wood'] = 'wood_medium.png'
    texs['ph_kc_board']      = 'wood_medium.png'
    texs['ph_kc_tampo']      = 'stone_gold.png'
  elsif theme == 'hotel_boutique'
    taupe = [150, 138, 122]
    %w[corpo porta gaveta corpo_sup porta_sup filler].each { |k| cols["ph_kc_#{k}"] = taupe }
    cols['ph_kc_geladeira'] = [180, 160, 120]; cols['ph_kc_puxador'] = [170, 140, 95]
    cols['ph_kc_torneira'] = [150, 120, 80]; cols['ph_kc_cuba'] = [150, 120, 80]
    cols['ph_kc_soculo'] = [70, 64, 58]; cols['ph_kc_led'] = [255, 244, 222]
    cols['ph_kc_tampo'] = [222, 219, 212]; cols['ph_kc_backsplash'] = [222, 219, 212]
    cols['ph_kc_niche_wood'] = [150, 116, 78]
    texs['ph_kc_tampo'] = 'stone_counter.png'; texs['ph_kc_backsplash'] = 'stone_counter.png'
    texs['ph_kc_niche_wood'] = 'wood_medium.png'
  end

  n = 0
  m.materials.each do |mat|
    nm = mat.name.to_s
    next unless cols.key?(nm)
    r, g, b = cols[nm]
    mat.color = Sketchup::Color.new(r, g, b)
    if texs.key?(nm) && tex
      p = File.join(tex, texs[nm])
      begin
        mat.texture = p if File.exist?(p)
      rescue StandardError
      end
    end
    n += 1
  end

  out = ENV['THEME_OUT']
  ok = m.save(out)
  File.write(ENV['RECOLOR_LOG'], "OK theme=#{theme} recolored=#{n} saved=#{ok} -> #{out}")
rescue StandardError => e
  File.write(ENV['RECOLOR_LOG'] || File.join(ENV['TEMP'] || '.', 'recolor_err.txt'), "ERR #{e.message}")
end
