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
