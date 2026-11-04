# Launcher da barra flutuante de agentes (FP-058). ASCII (PowerShell 5.1). Somente observa/controla via Tarefa Agendada existente.
# Nao instala nada, nao mexe na tarefa do listener, nao exige privilegios de administrador.
#   .\run_agent_bar.ps1                 inicia a barra
#   .\run_agent_bar.ps1 -Autostart      cria atalho de inicio no login (PEDE confirmacao; nunca automatico)
#   .\run_agent_bar.ps1 -RemoveAutostart
param([switch]$Autostart, [switch]$RemoveAutostart)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    # worktree sem venv proprio: usa o venv do checkout principal
    $common = (& git -C $repo rev-parse --git-common-dir).Trim()
    $py = Join-Path (Split-Path (Resolve-Path (Join-Path $repo $common)).Path -Parent) ".venv\Scripts\python.exe"
}
if (-not (Test-Path $py)) { Write-Error "venv nao encontrado: rode 'uv sync --locked --extra dev --extra agent-bar' no checkout principal"; exit 2 }
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "AgentBar.lnk"
if ($RemoveAutostart) { if (Test-Path $lnk) { Remove-Item $lnk -Confirm:$false }; Write-Output "autostart removido"; exit 0 }
if ($Autostart) {
    $ans = Read-Host "Criar atalho de inicio no login em $lnk ? (s/N)"
    if ($ans -ne "s") { Write-Output "cancelado"; exit 0 }
    $w = New-Object -ComObject WScript.Shell
    $s = $w.CreateShortcut($lnk)
    $s.TargetPath = "powershell.exe"
    $s.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File `"$PSCommandPath`""
    $s.WorkingDirectory = $repo
    $s.Save()
    Write-Output "atalho criado: $lnk"
    exit 0
}
Set-Location $repo
& $py -m tools.orchestration.agent_bar.app
exit $LASTEXITCODE
