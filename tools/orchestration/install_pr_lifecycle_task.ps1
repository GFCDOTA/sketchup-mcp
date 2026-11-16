# Registra (ou remove) a tarefa do Agendador de Tarefas que mantem o ciclo padrao de PR rodando e o RETOMA apos reinicio do computador (FP-060 MT-17).
# So ASCII. Tarefa do PROPRIO usuario (sem admin): inicia no logon, 1 instancia, reinicia ate 3x a cada 5 min se cair.
# Uso:
#   powershell -File tools\orchestration\install_pr_lifecycle_task.ps1             # registra em MODO PLANO (-Execute ausente: nada e escrito)
#   powershell -File tools\orchestration\install_pr_lifecycle_task.ps1 -Execute    # registra COM execucao (so apos autorizacao do proprietario)
#   powershell -File tools\orchestration\install_pr_lifecycle_task.ps1 -Execute -AutoMerge -Workers 3   # + merge protegido e ate 3 revisoes em paralelo
#   powershell -File tools\orchestration\install_pr_lifecycle_task.ps1 -Remove
# Nada e iniciado aqui: use Start-ScheduledTask -TaskName "sketchup-mcp pr lifecycle" ou faca logoff/logon.
param([switch]$Execute, [switch]$Remove, [string]$TaskName = "sketchup-mcp pr lifecycle", [int]$IntervalSeconds = 30, [int]$Workers = 3, [switch]$AutoMerge)
$ErrorActionPreference = "Stop"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "tarefa '$TaskName' removida"
    exit 0
}
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$launcher = Join-Path $repo "tools\orchestration\run_pr_lifecycle.ps1"
if (-not (Test-Path $launcher)) { [Console]::Error.WriteLine("launcher ausente: $launcher"); exit 2 }
$argLine = "-NoProfile -ExecutionPolicy RemoteSigned -File `"$launcher`" -IntervalSeconds $IntervalSeconds -Workers $Workers"
if ($Execute) { $argLine += " -Execute" }
if ($AutoMerge) { $argLine += " -AutoMerge" }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argLine -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$mode = if ($Execute) { "COM execucao (-Execute)" } else { "plano (sem -Execute)" }
Write-Output "tarefa '$TaskName' registrada: $mode; inicia no logon de $env:USERNAME; 1 instancia; reinicia ate 3x a cada 5 min"
