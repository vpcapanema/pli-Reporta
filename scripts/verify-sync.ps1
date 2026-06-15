# Compara versoes: laptop | GitHub | VM
# Uso: powershell -File scripts/verify-sync.ps1

param(
    [string]$VmHost = '56.125.163.194',
    [string]$VmUser = 'ubuntu',
    [string]$Branch = 'main',
    [string]$AppDir = '/opt/pli-reporta'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

git fetch origin $Branch 2>&1 | Out-Null

$local  = (git rev-parse HEAD).Trim()
$github = (git rev-parse "origin/$Branch").Trim()
$vmRaw  = ssh "${VmUser}@${VmHost}" @"
if [ -d '$AppDir/.git' ]; then git -C '$AppDir' rev-parse HEAD;
elif [ -f '$AppDir/.deploy/last_deploy_sha' ]; then cat '$AppDir/.deploy/last_deploy_sha';
else echo MISSING; fi
"@.Trim()
$vm = ($vmRaw -split "`n")[-1].Trim()

function Short([string]$sha) { if ($sha.Length -ge 7) { $sha.Substring(0, 7) } else { $sha } }

Write-Host ""
Write-Host "  Laptop : $(Short $local)  $local"
Write-Host "  GitHub : $(Short $github)  $github"
Write-Host "  VM     : $(Short $vm)  $vm"
Write-Host ""

if ($local -eq $github -and $github -eq $vm) {
    Write-Host "  SINCRONIZADO — os tres ambientes no mesmo commit" -ForegroundColor Green
    exit 0
}
if ($local -ne $github) {
    Write-Host "  DESALINHADO — rode: git push origin $Branch" -ForegroundColor Yellow
}
if ($github -ne $vm) {
    Write-Host "  DESALINHADO — rode: powershell -File scripts/sync-vm.ps1" -ForegroundColor Yellow
}
exit 1
