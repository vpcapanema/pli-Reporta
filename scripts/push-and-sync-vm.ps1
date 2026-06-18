# Fluxo completo: laptop -> GitHub -> VM
# Uso: powershell -File scripts/push-and-sync-vm.ps1 [-CommitMessage "descricao"]
# Recomendado: task "PLI Reporta: Publicar e atualizar VM" ou scripts/commit-push-deploy-vm.ps1

param(
    [string]$CommitMessage = '',
    [string]$Branch = 'main',
    [switch]$SkipCommit,
    [switch]$SkipOpenBrowser
)

$ErrorActionPreference = 'Stop'
$deployScript = Join-Path $PSScriptRoot 'commit-push-deploy-vm.ps1'
if (-not (Test-Path $deployScript)) {
    throw 'Script commit-push-deploy-vm.ps1 nao encontrado.'
}

$deployArgs = @('-ExecutionPolicy', 'Bypass', '-File', $deployScript, '-Branch', $Branch)
if ($CommitMessage) { $deployArgs += @('-CommitMessage', $CommitMessage) }
if ($SkipOpenBrowser) { $deployArgs += '-SkipOpenBrowser' }
if ($SkipCommit) {
    Write-Host 'AVISO: -SkipCommit ignorado — use commit-push-deploy-vm.ps1 apenas quando nao houver alteracoes locais.' -ForegroundColor Yellow
}

& powershell @deployArgs
exit $LASTEXITCODE
