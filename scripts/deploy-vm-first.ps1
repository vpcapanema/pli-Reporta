# Primeiro deploy na VM.
# -BuildOnVm (padrao): build ARM64 nativo na VM a partir do GitHub
# -SendTarball: build no laptop + envia .tar (lento no Windows)

param(
    [string]$VmHost = '56.125.163.194',
    [string]$VmUser = 'ubuntu',
    [int]$SshPort = 22,
    [switch]$SendTarball,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

function Get-CredFile {
    $parent = Split-Path -Parent $root
    Get-ChildItem -LiteralPath $parent -Recurse -Filter 'CREDENCIAIS_VALIDADAS.txt' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match 'DOCUMENTA' } |
        Select-Object -First 1 -ExpandProperty FullName
}

function Get-PlinkTools {
    $plink = @(
        (Get-Command plink.exe -ErrorAction SilentlyContinue).Source,
        "$env:ProgramFiles\PuTTY\plink.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    $pscp = @(
        (Get-Command pscp.exe -ErrorAction SilentlyContinue).Source,
        "$env:ProgramFiles\PuTTY\pscp.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $plink -or -not $pscp) { throw 'PuTTY plink/pscp nao encontrado' }
    @{ Plink = $plink; Pscp = $pscp }
}

function Get-Ppk {
    @(
        'D:\REPOSITORIOS\sigma-pli\chave_ppk\SRV-SISTEMA-30001480.ppk',
        'D:\REPOSITORIOS\PLI-HazardTrack\SRV-SISTEMA-30001480.ppk'
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

$cred = Get-CredFile
$text = Get-Content -LiteralPath $cred -Raw
if ($text -notmatch 'pli_user / (\S+)') { throw 'Senha pli_user nao encontrada' }
$pliPass = $Matches[1]
$secret = (python -c "import secrets; print(secrets.token_urlsafe(48))").Trim()

$tools = Get-PlinkTools
$ppk = Get-Ppk
$target = "${VmUser}@${VmHost}"
$plinkArgs = @('-batch', '-P', "$SshPort", '-i', $ppk)
$pscpArgs = @('-batch', '-P', "$SshPort", '-i', $ppk)

if ($SendTarball) {
    Step 'Modo tarball: build ARM64 local'
    $tar = Join-Path $root 'pli-reporta-app-arm64.tar'
    if (-not $SkipBuild -or -not (Test-Path $tar)) {
        & (Join-Path $PSScriptRoot 'build-docker.ps1') -Platform linux/arm64
        if ($LASTEXITCODE -ne 0) { exit 1 }
    } else {
        Write-Host "  Pulando build - usando $tar" -ForegroundColor Yellow
    }
    $staging = Join-Path $env:TEMP 'pli-reporta-deploy'
    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
    New-Item -ItemType Directory -Path $staging | Out-Null
    Copy-Item (Join-Path $root 'pli-reporta-app-arm64.tar') $staging
    Copy-Item (Join-Path $root 'docker-compose.vm.yml') $staging
    Copy-Item (Join-Path $root '.deploy\deploy_vm.sh') $staging
    Copy-Item (Join-Path $root '.deploy\nginx-host\pli-reporta') (Join-Path $staging 'pli-reporta')
    $envContent = @"
PLI_DB_PASSWORD=$pliPass
SECRET_KEY=$secret
PUBLIC_BASE_URL=http://pli-reporta.56-125-163-194.sslip.io
SIGMA_API_BASE_URL=http://host.docker.internal
"@
    Set-Content -Path (Join-Path $staging '.env.vm') -Value $envContent -Encoding UTF8
    & $tools.Plink @plinkArgs $target 'mkdir -p /tmp/pli-reporta'
    & $tools.Pscp @pscpArgs -r "$staging\*" "${target}:/tmp/pli-reporta/"
    & $tools.Plink @plinkArgs $target "sed -i 's/\r$//' /tmp/pli-reporta/deploy_vm.sh"
    & $tools.Plink @plinkArgs $target 'cd /tmp/pli-reporta && chmod +x deploy_vm.sh && bash deploy_vm.sh'
} else {
    Step 'Modo nativo: build ARM64 na VM a partir do GitHub'
    & $tools.Pscp @pscpArgs (Join-Path $root '.deploy\deploy_vm_native.sh') "${target}:/tmp/deploy_vm_native.sh"
    & $tools.Plink @plinkArgs $target "sed -i 's/\r$//' /tmp/deploy_vm_native.sh"
    $envCmd = "export PLI_DB_PASSWORD='$pliPass'; export SECRET_KEY='$secret'; bash /tmp/deploy_vm_native.sh"
    & $tools.Plink @plinkArgs $target $envCmd
}
if ($LASTEXITCODE -ne 0) { exit 1 }

Step 'Verificando sincronizacao'
git fetch origin main 2>&1 | Out-Null
$local = (git rev-parse HEAD).Trim()
$vmSha = (& $tools.Plink @plinkArgs $target 'git -C /opt/pli-reporta rev-parse HEAD 2>/dev/null').Trim()
Write-Host "  Laptop/GitHub: $local" -ForegroundColor Cyan
Write-Host "  VM:            $vmSha" -ForegroundColor Cyan
if ($local -eq $vmSha) {
    Write-Host "  ALINHADO" -ForegroundColor Green
} else {
    Write-Host "  VM pode estar 1 commit atras - rode sync-vm.ps1" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "URL: http://pli-reporta.56-125-163-194.sslip.io" -ForegroundColor Green
