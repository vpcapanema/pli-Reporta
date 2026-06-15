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

if ($state.IsSynced) {
    Write-Host -ForegroundColor Green '  SINCRONIZADO - os tres ambientes no mesmo commit'
    exit 0
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
