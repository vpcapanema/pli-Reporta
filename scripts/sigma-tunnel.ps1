# Tunel SSH PostgreSQL: 127.0.0.1:15433 -> VM:5433
param(
    [int]$LocalPort = 15433,
    [int]$RemotePort = 5433,
    [string]$VmHost = '56.125.163.194',
    [int]$SshPort = 22,
    [string]$VmUser = 'ubuntu',
    [int]$WaitSeconds = 12
)

$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $PSScriptRoot
$localSpec = "${LocalPort}:127.0.0.1:${RemotePort}"
$vmTarget = "${VmUser}@${VmHost}"

function Test-Tcp([string]$HostName, [int]$P, [int]$Ms = 1500) {
    $c = [System.Net.Sockets.TcpClient]::new()
    try {
        $a = $c.BeginConnect($HostName, $P, $null, $null)
        if (-not $a.AsyncWaitHandle.WaitOne($Ms, $false)) { return $false }
        $c.EndConnect($a)
        return $true
    } catch { return $false } finally { $c.Dispose() }
}

function Get-Plink {
    @(
        (Get-Command plink.exe -ErrorAction SilentlyContinue).Source,
        "$env:ProgramFiles\PuTTY\plink.exe",
        "${env:ProgramFiles(x86)}\PuTTY\plink.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

function Get-Ppk {
    $sigmaRoot = Join-Path (Split-Path -Parent $root) 'sigma-pli'
    @(
        (Join-Path $sigmaRoot 'chave_ppk\SRV-SISTEMA-30001480.ppk'),
        'D:\REPOSITORIOS\PLI-HazardTrack\SRV-SISTEMA-30001480.ppk'
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

function Stop-Tunnel {
    Get-CimInstance Win32_Process -Filter "Name='plink.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match [regex]::Escape("-L $localSpec") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

if (Test-Tcp '127.0.0.1' $LocalPort) {
    Write-Host "[sigma-tunnel] Porta $LocalPort ja ativa." -ForegroundColor Green
    exit 0
}

$plink = Get-Plink
$ppk = Get-Ppk
if (-not $plink) {
    Write-Host '[sigma-tunnel] plink.exe nao encontrado (winget install PuTTY.PuTTY).' -ForegroundColor Red
    exit 1
}
if (-not $ppk) {
    Write-Host '[sigma-tunnel] Chave PPK nao encontrada.' -ForegroundColor Red
    exit 1
}

Stop-Tunnel
if (-not (Test-Tcp $VmHost $SshPort 3000)) {
    Write-Host "[sigma-tunnel] SSH ${VmHost}:${SshPort} inacessivel." -ForegroundColor Yellow
    exit 1
}

try { 'y' | & $plink -P $SshPort -i $ppk $vmTarget 'exit' 2>&1 | Out-Null } catch {}

Write-Host "[sigma-tunnel] Abrindo 127.0.0.1:${LocalPort} -> VM:${RemotePort} ..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $plink -ArgumentList @(
    '-batch', '-P', "$SshPort", '-i', $ppk, '-L', $localSpec, $vmTarget, '-N'
) -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    if (Test-Tcp '127.0.0.1' $LocalPort) {
        Write-Host "[sigma-tunnel] Tunel ativo (PID $($proc.Id))." -ForegroundColor Green
        exit 0
    }
    Start-Sleep -Milliseconds 350
}

Write-Host '[sigma-tunnel] Falha ao abrir tunel.' -ForegroundColor Red
Stop-Tunnel
exit 1
