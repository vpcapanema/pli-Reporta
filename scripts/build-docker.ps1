# Build e export da imagem Docker para deploy na VM.
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-docker.ps1
#      powershell -File scripts/build-docker.ps1 -Platform linux/arm64

param(
    [ValidateSet('linux/amd64', 'linux/arm64')]
    [string]$Platform = 'linux/arm64',
    [string]$Image = 'pli-reporta-app',
    [string]$Tag = 'latest'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "`n=== PLI Reporta :: build Docker ($Platform) ===" -ForegroundColor Cyan

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'ERRO: Docker Desktop nao esta rodando.' -ForegroundColor Red
    exit 1
}

docker build --platform $Platform -t "${Image}:${Tag}" -t "${Image}:prod" .
if ($LASTEXITCODE -ne 0) { exit 1 }

$arch = if ($Platform -eq 'linux/arm64') { 'arm64' } else { 'amd64' }
$tar = "pli-reporta-app-${arch}.tar"
Write-Host "`nExportando $tar ..." -ForegroundColor Cyan
docker save -o $tar "${Image}:${Tag}"

Write-Host "`nOK" -ForegroundColor Green
Write-Host "  Imagem : ${Image}:${Tag}"
Write-Host "  Tarball: $root\$tar"
Write-Host "`nTransferir para a VM e rodar:"
Write-Host "  scp $tar docker-compose.vm.yml .deploy/nginx-host/pli-reporta .deploy/deploy_vm.sh .env.vm ubuntu@56.125.163.194:/tmp/pli-reporta/"
Write-Host "  ssh ubuntu@56.125.163.194 'cd /tmp/pli-reporta && bash deploy_vm.sh'"
