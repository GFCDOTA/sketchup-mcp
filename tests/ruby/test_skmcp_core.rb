# Testa a lógica PURA dos jobs su_* (skmcp_core.rb) com ruby comum, sem SketchUp.
# Rodado por tests/test_sketchup_ruby_jobs.py.
require 'minitest/autorun'
require_relative '../../tools/sketchup/ruby/skmcp_core'

class TestSkmcpCore < Minitest::Test
  INFOS = [
    { 'name' => 'Cama_Suite01', 'definition' => 'Group#1', 'pid' => 10, 'path' => 'Cama_Suite01' },
    { 'name' => '', 'definition' => 'Cadeira', 'pid' => 11, 'path' => 'Cadeira' },
    { 'name' => '', 'definition' => 'Cadeira', 'pid' => 12, 'path' => 'Cadeira' },
    { 'name' => 'PlanShell_Group', 'definition' => 'Group#9', 'pid' => 13, 'path' => 'PlanShell_Group' },
  ].freeze

  def test_nome_exato_casa_instancia
    hits, err = SkmcpCore.select(INFOS, { 'name' => 'Cama_Suite01' })
    assert_nil err
    assert_equal [10], hits.map { |h| h['pid'] }
  end

  def test_componente_sem_nome_casa_pela_definicao
    hits, err = SkmcpCore.select(INFOS, { 'name' => 'Cadeira', 'expect' => 'all' })
    assert_nil err
    assert_equal [11, 12], hits.map { |h| h['pid'] }
  end

  def test_ambiguo_com_expect_one_e_recusado
    hits, err = SkmcpCore.select(INFOS, { 'name' => 'Cadeira' })
    assert_empty hits
    assert_match(/2 entidades/, err)
  end

  def test_nada_casa_e_erro
    _, err = SkmcpCore.select(INFOS, { 'name_contains' => 'sofa' })
    assert_match(/nenhuma entidade/, err)
  end

  def test_persistent_id_e_inequivoco
    hits, err = SkmcpCore.select(INFOS, { 'persistent_id' => 12 })
    assert_nil err
    assert_equal [12], hits.map { |h| h['pid'] }
  end

  def test_name_contains_ignora_caixa
    hits, = SkmcpCore.select(INFOS, { 'name_contains' => 'CAMA' })
    assert_equal [10], hits.map { |h| h['pid'] }
  end

  def test_protegido_por_prefixo
    assert SkmcpCore.protected_name?('PlanShell_Group', %w[PlanShell_ Floor_])
    refute SkmcpCore.protected_name?('Cama', %w[PlanShell_ Floor_])
  end

  def test_presets_miram_o_centro_e_top_e_ortografico
    bmin = [0.0, 0.0, 0.0]
    bmax = [100.0, 50.0, 10.0]
    top = SkmcpCore.preset_camera('top', bmin, bmax)
    assert_equal [50.0, 25.0, 5.0], top['target']
    refute top['perspective']
    assert top['eye'][2] > 10.0
    %w[iso front back left right].each do |p|
      c = SkmcpCore.preset_camera(p, bmin, bmax)
      assert c['perspective'], p
      refute_equal c['eye'], c['target'], p
    end
    assert_raises(ArgumentError) { SkmcpCore.preset_camera('diagonal', bmin, bmax) }
  end

  def test_altura_ortografica_enquadra_o_lado_maior
    h = SkmcpCore.ortho_height([0, 0, 0], [400.0, 100.0, 0], 1600, 1200)
    assert_in_delta 300.0 * 1.06, h, 1e-6
  end

  def test_nome_de_arquivo_seguro
    assert_equal 'sala_3_4', SkmcpCore.safe_filename('sala 3/4')
    assert_equal 'view', SkmcpCore.safe_filename('')
  end
end

# Proteção: cada brecha achada na revisão do PR #249 tem um caso aqui.
class TestSkmcpGuard < Minitest::Test
  PREFIXES = %w[PlanShell_ Window_ Floor_].freeze

  def node(pid, name, definition: "Group##{pid}", ancestors: [], locked: false, contexts: 1)
    { 'pid' => pid, 'name' => name, 'definition' => definition, 'path' => name,
      'locked' => locked, 'contexts' => contexts, 'ancestors' => ancestors,
      'ancestor_pids' => ancestors.map { |a| a['pid'] } }
  end

  def anc(pid, name, definition: "Group##{pid}", locked: false)
    { 'pid' => pid, 'label' => name, 'name' => name, 'definition' => definition, 'locked' => locked }
  end

  def violation(info, infos = [info])
    SkmcpCore.guard_violation(info, infos, PREFIXES)
  end

  def test_movel_comum_passa
    assert_nil violation(node(1, 'Sofa'))
  end

  def test_nome_proprio_protegido
    assert_match(/arquitetura/, violation(node(1, 'PlanShell_Group')))
  end

  def test_protegido_pelo_nome_da_definicao
    # instância sem nome: o Outliner mostra a definição — e a proteção também tem que olhar
    assert_match(/arquitetura/, violation(node(1, '', definition: 'Window_Group_w1')))
  end

  def test_dentro_de_arquitetura
    child = node(2, 'peca', ancestors: [anc(1, 'PlanShell_Group')])
    assert_match(/dentro de arquitetura/, violation(child))
  end

  def test_pai_que_contem_arquitetura
    parent = node(1, 'Pavimento')
    wall = node(2, 'PlanShell_Group', ancestors: [anc(1, 'Pavimento')])
    assert_match(/contém arquitetura/, violation(parent, [parent, wall]))
  end

  def test_travado
    assert_match(/locked/, violation(node(1, 'Sofa', locked: true)))
  end

  def test_dentro_de_grupo_travado
    child = node(2, 'braco', ancestors: [anc(1, 'Sofa', locked: true)])
    assert_match(/travado/, violation(child))
  end

  def test_definicao_compartilhada
    assert_match(/make_unique/, violation(node(1, 'perna', contexts: 4)))
  end

  def test_dedupe_une_a_ancestralidade_de_todas_as_visitas
    # mesma parede vista por 2 caminhos: a união é o que deixa descendants()
    # achar a arquitetura dentro de QUALQUER instância do container
    a = { 'pid' => 100, 'path' => 'Sala/Modulo/PlanShell_piece_1', 'ancestor_pids' => [5, 11],
          'ancestors' => [{ 'pid' => 5 }, { 'pid' => 11 }], 'locked' => false }
    b = { 'pid' => 100, 'path' => 'Modulo/PlanShell_piece_1', 'ancestor_pids' => [12],
          'ancestors' => [{ 'pid' => 12, 'locked' => true }], 'locked' => true }
    out = SkmcpCore.dedupe([a, b]).first
    assert_equal [5, 11, 12], out['ancestor_pids']
    assert_equal [5, 11, 12], out['ancestors'].map { |x| x['pid'] }
    assert out['locked']
  end

  def test_alvos_aninhados_sao_detectados
    pai = { 'pid' => 1, 'path' => 'Sofa', 'ancestor_pids' => [] }
    filho = { 'pid' => 2, 'path' => 'Sofa/braco', 'ancestor_pids' => [1] }
    outro = { 'pid' => 3, 'path' => 'Mesa', 'ancestor_pids' => [] }
    assert_equal [2], SkmcpCore.nested_hits([pai, filho, outro]).map { |h| h['pid'] }
    assert_empty SkmcpCore.nested_hits([pai, outro])
  end

  def test_dedupe_junta_mesma_entidade_em_varias_instancias
    a = { 'pid' => 9, 'name' => 'perna', 'path' => 'Cadeira/perna' }
    b = { 'pid' => 9, 'name' => 'perna', 'path' => 'Cadeira#2/perna' }
    out = SkmcpCore.dedupe([a, b])
    assert_equal 1, out.size
    assert_equal 2, out.first['contexts']
    assert_equal ['Cadeira/perna', 'Cadeira#2/perna'], out.first['paths']
  end
end

# Referencial: transform!/bounds aninhados trabalham no eixo LOCAL do pai.
class TestSkmcpFrame < Minitest::Test
  # layout de Geom::Transformation#to_a (coluna-major, origem em 12..14)
  def rot_z90(origin = [0.0, 0.0, 0.0])
    [0.0, 1.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, *origin, 1.0]
  end

  def assert_vec(exp, got, tol = 1e-9)
    exp.zip(got).each { |e, g| assert_in_delta e, g, tol }
  end

  def test_identidade
    m = SkmcpCore.mat_mul(SkmcpCore::IDENTITY, rot_z90([5.0, 0, 0]))
    assert_vec rot_z90([5.0, 0, 0]), m
  end

  def test_w_diferente_de_1_e_normalizado
    # SketchUp guarda escala uniforme 2x como w = 0.5
    m = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 0.5]
    assert_vec [2.0, 2.0, 2.0], SkmcpCore.apply_point(m, [1.0, 1.0, 1.0])
  end

  def test_inversa_desfaz
    m = rot_z90([10.0, 20.0, 3.0])
    p = [1.5, -2.0, 7.0]
    back = SkmcpCore.apply_point(SkmcpCore.inverse_affine(m), SkmcpCore.apply_point(m, p))
    assert_vec p, back
  end

  def test_mover_em_x_do_mundo_dentro_de_pai_girado_90
    # o caso real: o sofá integrado vive num wrapper girado theta=90.
    # Andar +X no mundo = andar -Y no local do pai. Um move "cru" andaria em +Y.
    local = SkmcpCore.world_to_local_vector(rot_z90([100.0, 50.0, 0.0]), [1.0, 0.0, 0.0])
    assert_vec [0.0, -1.0, 0.0], local
  end

  def test_translacao_do_pai_nao_afeta_vetor
    local = SkmcpCore.world_to_local_vector([1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 9, 9, 9, 1.0], [0, 0, 1.0])
    assert_vec [0.0, 0.0, 1.0], local
  end

  def test_bbox_de_mundo_de_caixa_girada
    lo, hi = SkmcpCore.world_bbox([0.0, 0.0, 0.0], [2.0, 1.0, 1.0], rot_z90)
    assert_vec [-1.0, 0.0, 0.0], lo
    assert_vec [0.0, 2.0, 1.0], hi
  end

  def test_escala_nao_uniforme_bloqueia_rotacao
    assert SkmcpCore.uniform_frame?(rot_z90)
    refute SkmcpCore.uniform_frame?([2.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0])
  end

  def test_rotacao_de_mundo_exata_sob_pai_espelhado
    # Flip Along no wrapper (det < 0): levar só eixo+centro para o local
    # inverteria o sentido. A conjugação inteira mantém o efeito no MUNDO.
    flip = [-1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 30.0, 0, 0, 1.0]
    r_world = SkmcpCore.rotation_z([10.0, 5.0, 0.0], 90)
    t_local = SkmcpCore.local_transform_for_world(flip, r_world)
    p_local = [3.0, 2.0, 1.0]
    via_local = SkmcpCore.apply_point(SkmcpCore.mat_mul(flip, t_local), p_local)
    direto = SkmcpCore.apply_point(r_world, SkmcpCore.apply_point(flip, p_local))
    assert_vec direto, via_local
  end

  def test_rotacao_z_gira_no_sentido_anti_horario
    assert_vec [0.0, 1.0, 0.0], SkmcpCore.apply_point(SkmcpCore.rotation_z([0, 0, 0], 90), [1.0, 0, 0])
    assert_vec [10.0, 1.0, 0.0], SkmcpCore.apply_point(SkmcpCore.rotation_z([10.0, 0, 0], 90), [11.0, 0, 0])
  end

  def test_singular_recusa
    assert_raises(ArgumentError) { SkmcpCore.inverse_affine(Array.new(15, 0.0) + [1.0]) }
  end
end
