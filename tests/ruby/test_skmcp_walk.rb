# Composição REAL: SkmcpRuntime.walk -> SkmcpCore.dedupe -> guard_violation /
# referencial, com classes falsas no lugar da API do SketchUp. Os testes do core
# usam infos montadas à mão; este prova que as peças se encaixam.
# Rodado por tests/test_sketchup_ruby_jobs.py.
require 'minitest/autorun'

module Sketchup
  class FakeEntity
    attr_reader :name, :definition, :persistent_id, :transformation

    def initialize(pid, name, definition, matrix = nil, locked: false)
      @persistent_id = pid
      @name = name
      @definition = definition
      @transformation = FakeTransform.new(matrix || [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0])
      @locked = locked
    end

    def locked?
      @locked
    end
  end

  class Group < FakeEntity; end
  class ComponentInstance < FakeEntity; end
end

FakeTransform = Struct.new(:to_a)
FakeDefinition = Struct.new(:name, :entities)

module UI
  def self.start_timer(*) end
end

require_relative '../../tools/sketchup/ruby/skmcp_runtime'

class TestSkmcpWalk < Minitest::Test
  PREFIXES = %w[PlanShell_ Window_].freeze

  def guard(infos, pid)
    info = infos.find { |i| i['pid'] == pid }
    SkmcpCore.guard_violation(info, infos, PREFIXES)
  end

  def infos_of(roots)
    SkmcpCore.dedupe(SkmcpRuntime.walk(roots).map(&:last))
  end

  # O cenário do cético: Sala ⊃ C1(Modulo); C2(Modulo) na raiz; Modulo ⊃ parede.
  def test_toda_instancia_de_container_com_arquitetura_e_recusada
    wall = Sketchup::Group.new(100, 'PlanShell_piece_1', FakeDefinition.new('Group#1', []))
    modulo = FakeDefinition.new('Modulo', [wall])
    c1 = Sketchup::ComponentInstance.new(11, '', modulo)
    c2 = Sketchup::ComponentInstance.new(12, '', modulo)
    sala = Sketchup::Group.new(5, 'Sala', FakeDefinition.new('Group#5', [c1]))
    infos = infos_of([sala, c2])
    [5, 11, 12].each { |pid| assert_match(/contém arquitetura|definição usada/, guard(infos, pid).to_s, "pid #{pid}") }
  end

  def test_copias_de_grupo_que_compartilham_definicao
    wall = Sketchup::Group.new(100, 'PlanShell_piece_1', FakeDefinition.new('Group#1', []))
    bloco = FakeDefinition.new('Bloco', [wall])
    infos = infos_of([Sketchup::Group.new(21, 'Bloco', bloco), Sketchup::Group.new(22, 'Bloco', bloco)])
    assert guard(infos, 21) && guard(infos, 22)
  end

  def test_parent_world_e_world_compoem_na_ordem_certa
    rot90 = [0.0, 1.0, 0, 0, -1.0, 0.0, 0, 0, 0, 0, 1.0, 0, 100.0, 50.0, 0, 1.0]
    leg = Sketchup::Group.new(2, 'perna', FakeDefinition.new('Group#2', []),
                              [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 10.0, 0, 0, 1.0])
    sofa = Sketchup::Group.new(1, 'Sofa', FakeDefinition.new('Group#1', [leg]), rot90)
    by = SkmcpRuntime.walk([sofa]).to_h { |_, i| [i['pid'], i] }
    assert_equal SkmcpCore.normalize(rot90), by[2]['parent_world']
    # origem da perna no mundo: girar (10,0,0) por 90° e somar (100,50,0) = (100,60,0)
    origin = SkmcpCore.apply_point(by[2]['world'], [0.0, 0.0, 0.0])
    [100.0, 60.0, 0.0].zip(origin).each { |e, g| assert_in_delta e, g, 1e-9 }
    # mover +X do mundo dentro do sofá girado = -Y no local do pai
    local = SkmcpCore.world_to_local_vector(by[2]['parent_world'], [1.0, 0, 0])
    [0.0, -1.0, 0.0].zip(local).each { |e, g| assert_in_delta e, g, 1e-9 }
  end

  def test_ancestral_travado_chega_ate_o_filho
    braco = Sketchup::Group.new(2, 'braco', FakeDefinition.new('Group#2', []))
    sofa = Sketchup::Group.new(1, 'Sofa', FakeDefinition.new('Group#1', [braco]), nil, locked: true)
    assert_match(/travado/, guard(infos_of([sofa]), 2).to_s)
  end
end
