# Sincroniza a VM: git pull, rebuild do container, acompanhamento e testes.
# Uso: powershell -File scripts/sync-vm.ps1
#
# Pre-requisito: git push origin main (ou use ensure-sync.ps1)

param(
    [string]$VmHost = '56.125.163.194',
    [string]$VmUser = 'ubuntu',
    [string]$Branch = 'main',
    [string]$AppDir = '/opt/pli-reporta',
    [string]$VmBaseUrl = 'https://pli-reporta.56-125-163-194.sslip.io',
    [string]$VmHealthUrl = 'https://pli-reporta.56-125-163-194.sslip.io/healthz'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
. (Join-Path $PSScriptRoot 'sync-lib.ps1')

function Step([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

Step '1/5 Verificando alinhamento local <-> GitHub'
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

Step '2/5 VM — git pull e rebuild do container (update_vm.sh)'
# git reset antes do update_vm: evita falha se o script local na VM estiver quebrado/desatualizado
$pullCmd = "cd '$AppDir' && git fetch origin $Branch && git reset --hard origin/$Branch"
Invoke-VmRemote -VmHost $VmHost -VmUser $VmUser -Command $pullCmd
$updateCmd = "cd '$AppDir' && bash '$AppDir/.deploy/update_vm.sh'"
Invoke-VmRemote -VmHost $VmHost -VmUser $VmUser -Command $updateCmd

Step '3/5 Acompanhando subida do container'
$runtimeOk = Test-VmRuntime -BaseUrl $VmBaseUrl -HealthUrl $VmHealthUrl -Label 'VM' -MaxAttempts 15 -DelaySeconds 5
if (-not $runtimeOk) {
    throw 'Container na VM respondeu, mas os testes de runtime falharam.'
}

Step '4/5 Conferindo commit na VM'
$vmSha = (Invoke-VmRemote -VmHost $VmHost -VmUser $VmUser -Command "git -C $AppDir rev-parse HEAD 2>/dev/null || cat $AppDir/.deploy/last_deploy_sha").Trim()
$deploySha = (Invoke-VmRemote -VmHost $VmHost -VmUser $VmUser -Command "tr -d '[:space:]' < $AppDir/.deploy/last_deploy_sha 2>/dev/null || echo MISSING").Trim()
if ($vmSha -eq $local) {
    Write-Host "  OK  git na VM: $vmSha" -ForegroundColor Green
} else {
    Write-Host "  AVISO  git VM=$vmSha  GitHub=$local" -ForegroundColor Yellow
}
if ($deploySha -eq $local) {
    Write-Host "  OK  marcador de deploy: $deploySha" -ForegroundColor Green
} else {
    Write-Host "  AVISO  marcador deploy=$deploySha  GitHub=$local" -ForegroundColor Yellow
}

Step '5/5 Resumo'
Write-Host "  URL publica: $VmBaseUrl/api-publica" -ForegroundColor Green
Write-Host "  Manifesto:   $VmBaseUrl/api/public/" -ForegroundColor DarkGray
