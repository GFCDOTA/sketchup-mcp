# Configura a PROTECAO da branch base para o merge automatico protegido (FP-060 MT-17). EXECUTADO PELO PROPRIETARIO (conta com permissao de admin do repositorio):
# o agente NUNCA altera protecao de branch (e configuracao de seguranca); este script so existe para que o proprietario aplique, de forma repetivel, o que ele decidiu.
# So ASCII. Por padrao e DRY-RUN: imprime o JSON e o comando, nao chama a API. Com -Apply faz o PUT em /branches/<base>/protection.
# Uso:
#   powershell -File tools\orchestration\configure_branch_protection.ps1 -Repo GFCDOTA/sketchup-mcp                 # mostra o que seria aplicado
#   powershell -File tools\orchestration\configure_branch_protection.ps1 -Repo GFCDOTA/sketchup-mcp -Apply          # aplica (gh logado como admin)
#   ... -Branch main -Checks "ci","lint"                                                                            # outro repositorio/branch/checks
# Regras aplicadas: 1 aprovacao independente obrigatoria; aprovacoes de HEADs antigos sao DESCARTADAS quando o codigo muda; conversas resolvidas; os checks obrigatorios
# (strict=false como hoje); enforce_admins=true; sem bypass (nenhuma lista de bypass); sem force push nem delecao.
param(
    [string]$Repo = "GFCDOTA/sketchup-mcp",
    [string]$Branch = "develop",
    [string[]]$Checks = @("uv lock is current", "pytest (py3.11)", "pytest (py3.12)", "deterministic fidelity gates", "mcp server (smoke + stdio handshake)",
                          "qg: backlog, issues and specs", "qg: PR policy", "qg: geometry, program and integration"),
    [switch]$Apply
)
$ErrorActionPreference = "Stop"
$body = [ordered]@{
    required_status_checks = [ordered]@{ strict = $false; contexts = @($Checks) }
    enforce_admins = $true
    required_pull_request_reviews = [ordered]@{
        required_approving_review_count = 1
        dismiss_stale_reviews = $true
        require_code_owner_reviews = $false
    }
    restrictions = $null
    required_conversation_resolution = $true
    allow_force_pushes = $false
    allow_deletions = $false
    block_creations = $false
}
$json = $body | ConvertTo-Json -Depth 6
$path = "repos/$Repo/branches/$Branch/protection"
Write-Output "Protecao a aplicar em $Repo ($Branch):"
Write-Output $json
if (-not $Apply) {
    Write-Output "DRY-RUN: nada foi alterado. Para aplicar: rode de novo com -Apply (com o gh logado como administrador do repositorio)."
    exit 0
}
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) { $gh = "C:\Program Files\GitHub CLI\gh.exe" }
$tmp = New-TemporaryFile
try {
    Set-Content -Path $tmp -Value $json -Encoding ASCII
    & $gh api -X PUT $path --input $tmp | Out-Null
    if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine("falha ao aplicar a protecao (codigo $LASTEXITCODE): confira a permissao de administrador"); exit 1 }
} finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
Write-Output "Protecao aplicada. Conferindo:"
& $gh api $path --jq "{reviews: .required_pull_request_reviews.required_approving_review_count, dismiss_stale: .required_pull_request_reviews.dismiss_stale_reviews, conversations: .required_conversation_resolution.enabled, admins: .enforce_admins.enabled, checks: (.required_status_checks.contexts | length)}"
