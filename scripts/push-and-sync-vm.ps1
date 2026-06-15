# Fluxo completo: laptop -> GitHub -> VM
# Uso: powershell -File scripts/push-and-sync-vm.ps1 [-CommitMessage "descricao"]

param(
    [string]$CommitMessage = '',
    [string]$Branch = 'main',
    [switch]$SkipCommit
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

if (-not $SkipCommit) {
    $status = git status --porcelain
    if ($status) {
        if (-not $CommitMessage) {
            throw 'Ha alteracoes locais. Passe -CommitMessage "..." ou use -SkipCommit se ja commitou.'
        }
        Step '1/4 git add + commit'
        git add -A
        git commit -m $CommitMessage
    } else {
        Write-Host '  (sem alteracoes locais para commitar)' -ForegroundColor DarkGray
    }
} else {
    Step '1/4 Commit ignorado (-SkipCommit)'
}

Step '2/4 git push'
git push origin $Branch
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Step '3/4 sync VM'
& (Join-Path $PSScriptRoot 'sync-vm.ps1') -Branch $Branch
exit $LASTEXITCODE
