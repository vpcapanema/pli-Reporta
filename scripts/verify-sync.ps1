# Compara versoes: laptop | GitHub | VM
# Uso: powershell -File scripts/verify-sync.ps1

param(
    [string]$VmHost = '56.125.163.194',
    [string]$VmUser = 'ubuntu',
    [string]$Branch = 'main',
    [string]$AppDir = '/opt/pli-reporta'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'sync-lib.ps1')

$state = Get-SyncState -VmHost $VmHost -VmUser $VmUser -Branch $Branch -AppDir $AppDir
Write-SyncStatus $state

$runtimeOk = Test-RuntimeManifest -BaseUrl 'http://pli-reporta.56-125-163-194.sslip.io' -Label 'VM'
$pageOk = Test-ApiPublicaPage -BaseUrl 'http://pli-reporta.56-125-163-194.sslip.io' -Label 'VM'
$runtimeOk = $runtimeOk -and $pageOk

if ($state.IsSynced -and $runtimeOk) {
    Write-Host -ForegroundColor Green '  SINCRONIZADO - git alinhado e container testado'
    exit 0
}

if ($state.IsSynced -and -not $runtimeOk) {
    Write-Host -ForegroundColor Yellow '  GIT OK mas CONTAINER DESATUALIZADO - rode a task "Sincronizar ambientes"'
    exit 1
}

if ($state.Local -ne $state.GitHub) {
    $pushMsg = '  DESALINHADO - rode: git push origin ' + $Branch
    Write-Host -ForegroundColor Yellow $pushMsg
}
if ($state.GitHub -ne $state.Vm) {
    $syncMsg = '  DESALINHADO - rode: powershell -File scripts/sync-vm.ps1'
    Write-Host -ForegroundColor Yellow $syncMsg
}
exit 1
