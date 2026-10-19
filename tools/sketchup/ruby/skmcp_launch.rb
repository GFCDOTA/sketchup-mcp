# skmcp_launch.rb — carrega UM script Ruby neste SketchUp, depois que a janela existe.
#
# Substitui o mecanismo de `autorun_control.txt` + plugin `autorun_consume.rb` no Plugins GLOBAL do usuário:
# um control file esquecido (ou um build em andamento) era executado por QUALQUER SketchUp aberto depois —
# inclusive o do Felipe dando duplo clique num .skp (2026-05-20: apagou e salvou por cima do arquivo aberto).
# Com `SketchUp.exe <modelo.skp> -RubyStartup skmcp_launch.rb` o script vale para AQUELE processo e mais nenhum.
#
# Env (definido pelo Python no processo filho):
#   SKMCP_LAUNCH_SCRIPT  caminho do script a carregar (obrigatório)
#   SKMCP_LAUNCH_DEFER   segundos até a view estar pronta (default 2.0; write_image antes disso sai vazio)
#   SKMCP_LAUNCH_ERROR   arquivo onde registrar falha do `load` (opcional)
# O script carregado lê o próprio env (ex.: CONSENSUS_JSON, SKP_OUT) e salva/escreve seu sinal de pronto.
UI.start_timer((ENV['SKMCP_LAUNCH_DEFER'] || '2.0').to_f, false) do
  begin
    script = ENV['SKMCP_LAUNCH_SCRIPT'].to_s
    raise 'SKMCP_LAUNCH_SCRIPT não definido' if script.empty?
    raise "script não encontrado: #{script}" unless File.exist?(script)

    load script
  rescue Exception => e # rubocop:disable Lint/RescueException — ScriptError também vira registro
    err = ENV['SKMCP_LAUNCH_ERROR'].to_s
    unless err.empty?
      File.write(err, "load #{ENV['SKMCP_LAUNCH_SCRIPT']} falhou: #{e.class}: #{e.message}\n#{(e.backtrace || []).first(20).join("\n")}\n")
    end
  end
end
