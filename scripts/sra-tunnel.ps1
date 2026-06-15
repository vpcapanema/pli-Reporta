# Tunel SSH para o PostgreSQL SRA na VM (container sra-postgres, localhost-only).
# Mapeia 127.0.0.1:15434 (local) -> VM:5434. Idempotente.
param(
    [int]$LocalPort = 15434,
    [int]$RemotePort = 5434,
    [string]$VmHost = "56.125.163.194",
    [int]$SshPort = 22,
    [string]$VmUser = "ubuntu",
    [int]$WaitSeconds = 15
)

$ErrorActionPreference = "Stop"

function Test-Port([string]$TargetHost, [int]$Port, [int]$TimeoutMs = 1500) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($async)
        return $client.Connected
    } catch { return $false } finally { $client.Dispose() }
}

if (Test-Port "127.0.0.1" $LocalPort) {
    Write-Host "[sra-tunnel] Porta $LocalPort ja ativa." -ForegroundColor Green
    exit 0
}

$plink = (Get-Command plink.exe -ErrorAction SilentlyContinue).Source
foreach ($cand in @("$env:ProgramFiles\PuTTY\plink.exe", "${env:ProgramFiles(x86)}\PuTTY\plink.exe")) {
    if (-not $plink -and (Test-Path $cand)) { $plink = $cand }
}
if (-not $plink) {
    Write-Host "[sra-tunnel] plink.exe nao encontrado. Instale: winget install PuTTY.PuTTY" -ForegroundColor Red
    exit 1
}

$ppk = $null
foreach ($cand in @(
    "D:\REPOSITORIOS\sigma-pli\chave_ppk\SRV-SISTEMA-30001480.ppk",
    "D:\REPOSITORIOS\PLI-HazardTrack\SRV-SISTEMA-30001480.ppk"
)) { if (-not $ppk -and (Test-Path $cand)) { $ppk = $cand } }
if (-not $ppk) {
    Write-Host "[sra-tunnel] Chave PPK nao encontrada." -ForegroundColor Red
    exit 1
}

if (-not (Test-Port $VmHost $SshPort 4000)) {
    Write-Host "[sra-tunnel] SSH ${VmHost}:${SshPort} inacessivel." -ForegroundColor Yellow
    exit 1
}

try { "y`n" | & $plink -ssh -P $SshPort -i $ppk "$VmUser@$VmHost" "exit" 2>&1 | Out-Null } catch { }

$localSpec = "${LocalPort}:127.0.0.1:${RemotePort}"
Write-Host "[sra-tunnel] Abrindo 127.0.0.1:${LocalPort} -> VM:${RemotePort} ..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $plink -ArgumentList @(
    "-ssh", "-batch", "-P", "$SshPort", "-i", $ppk, "-L", $localSpec, "$VmUser@$VmHost", "-N"
) -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    if (Test-Port "127.0.0.1" $LocalPort) {
        Write-Host "[sra-tunnel] Tunel ativo (PID $($proc.Id))." -ForegroundColor Green
        exit 0
    }
    Start-Sleep -Milliseconds 400
}

Write-Host "[sra-tunnel] Falha ao abrir o tunel." -ForegroundColor Red
exit 1
