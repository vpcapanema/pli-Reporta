# Sincroniza a VM com o commit ja publicado no GitHub.
# Uso: powershell -File scripts/sync-vm.ps1
#
# Pre-requisito: git push origin main (use push-and-sync-vm.ps1 para fazer os dois)

param(
    [string]$VmHost = '56.125.163.194',
    [string]$VmUser = 'ubuntu',
    [string]$Branch = 'main',
    [string]$AppDir = '/opt/pli-reporta'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
. (Join-Path $PSScriptRoot 'vm-remote.ps1')

function Step([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

Step '1/3 Verificando alinhamento local <-> GitHub'
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
git fetch origin $Branch 2>&1 | Out-Null
$ErrorActionPreference = $prevEap
$local = (git rev-parse HEAD).Trim()
$remote = (git rev-parse "origin/$Branch" 2>$null).Trim()
if (-not $remote) { throw "Branch origin/$Branch nao encontrada no remoto" }
if ($local -ne $remote) {
    throw @"
Local ($($local.Substring(0,7))) difere do GitHub ($($remote.Substring(0,7))).
Rode: git push origin $Branch
"@
}
Write-Host "  OK  laptop e GitHub em $local" -ForegroundColor Green

Step '2/3 Atualizando VM'
$updateCmd = "cd '$AppDir' && git fetch origin '$Branch' && git reset --hard 'origin/$Branch' && chmod +x .deploy/*.sh 2>/dev/null || true && bash '$AppDir/.deploy/update_vm.sh'"
Invoke-VmRemote -VmHost $VmHost -VmUser $VmUser -Command $updateCmd

Step '3/3 Conferindo versao na VM'
$vmSha = (Invoke-VmRemote -VmHost $VmHost -VmUser $VmUser -Command "git -C $AppDir rev-parse HEAD 2>/dev/null || cat $AppDir/.deploy/last_deploy_sha").Trim()
if ($vmSha -eq $local) {
    Write-Host "  OK  VM alinhada com GitHub ($vmSha)" -ForegroundColor Green
} else {
    Write-Host "  AVISO  VM=$vmSha  GitHub=$local" -ForegroundColor Yellow
}
Write-Host "`nURL: http://pli-reporta.56-125-163-194.sslip.io" -ForegroundColor Green
