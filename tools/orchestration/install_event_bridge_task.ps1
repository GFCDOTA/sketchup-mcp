# Registra (ou remove) a tarefa do Agendador de Tarefas do Windows que mantem o event_bridge/executor rodando (Issue #589).
# So ASCII (Windows PowerShell 5.1 le .ps1 sem BOM como ANSI).
# Uso (PowerShell normal, SEM admin: a tarefa e do proprio usuario e so roda com a sessao dele ativa):
#   powershell -File tools\orchestration\install_event_bridge_task.ps1                 # registra em MODO DRY-RUN (so ingere a fila)
#   powershell -File tools\orchestration\install_event_bridge_task.ps1 -Execute        # registra COM execucao do Claude (so apos aprovacao)
#   powershell -File tools\orchestration\install_event_bridge_task.ps1 -Remove         # remove a tarefa
# Nada e iniciado aqui: use `Start-ScheduledTask -TaskName "sketchup-mcp event bridge"` ou faca logoff/logon.
param([switch]$Execute, [switch]$Remove, [string]$TaskName = "sketchup-mcp event bridge", [int]$IntervalSeconds = 120)
$ErrorActionPreference = "Stop"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "tarefa '$TaskName' removida"
    exit 0
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$launcher = Join-Path $repo "tools\orchestration\run_event_bridge.ps1"
if (-not (Test-Path $launcher)) { [Console]::Error.WriteLine("launcher ausente: $launcher"); exit 2 }
$argLine = "-NoProfile -ExecutionPolicy RemoteSigned -File `"$launcher`" -IntervalSeconds $IntervalSeconds"
if ($Execute) { $argLine += " -Execute" }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argLine -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$mode = if ($Execute) { "COM execucao do Claude (-Execute)" } else { "dry-run (sem -Execute)" }
Write-Output "tarefa '$TaskName' registrada: $mode; inicia no logon de $env:USERNAME; 1 instancia; reinicia ate 3x a cada 5 min"
