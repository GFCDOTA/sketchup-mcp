# Log do launcher em UTF-8 (sem BOM), dot-sourced por run_event_bridge.ps1 (Issue #589). So ASCII (PS 5.1 le .ps1 sem BOM como ANSI).
# Motivo: `Tee-Object -Append` do Windows PowerShell 5.1 grava UTF-16 e misturava com linhas UTF-8 antigas no mesmo arquivo.
#   Initialize-BridgeLog -Path <log> [-MaxBytes 5242880]
#     - arquivo legado (contem byte NUL = UTF-16/misto) e PRESERVADO como <log>.legacy-utf16-<aaaammddHHmmss> (nunca apagado nem convertido);
#     - arquivo UTF-8 acima de MaxBytes e rotacionado para <log>.1 (substitui o .1 anterior).
#   Write-BridgeLog -Path <log> -Line <texto>   anexa UMA linha em UTF-8 sem BOM, terminada em LF.
$script:BridgeUtf8 = New-Object System.Text.UTF8Encoding($false)

function Initialize-BridgeLog {
    param([Parameter(Mandatory = $true)][string]$Path, [long]$MaxBytes = 5242880)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $len = (Get-Item -LiteralPath $Path).Length
    if ($len -eq 0) { return }
    $legacy = $false
    if ($len -le 52428800) { $legacy = ([IO.File]::ReadAllBytes($Path) -contains 0) }
    if ($legacy) {
        $stamp = Get-Date -Format "yyyyMMddHHmmss"
        Move-Item -LiteralPath $Path -Destination ($Path + ".legacy-utf16-" + $stamp)
        return
    }
    if ($len -gt $MaxBytes) { Move-Item -Force -LiteralPath $Path -Destination ($Path + ".1") }
}

function Write-BridgeLog {
    param([Parameter(Mandatory = $true)][string]$Path, [AllowEmptyString()][string]$Line = "")
    [IO.File]::AppendAllText($Path, $Line + "`n", $script:BridgeUtf8)
}
