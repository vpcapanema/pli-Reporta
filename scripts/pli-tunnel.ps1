# Garante o túnel SSH para o PostgreSQL do PLI Reporta (VM container sigma_pli_db).
# Mapeia 127.0.0.1:15433 (local) -> VM:5433. Idempotente: sai 0 se já estiver no ar.
param(
    [int]$LocalPort = 15433,
    [int]$RemotePort = 5433,
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

# Já ativo?
if (Test-Port "127.0.0.1" $LocalPort) {
    Write-Host "[pli-tunnel] Porta $LocalPort já ativa." -ForegroundColor Green
    exit 0
}

# Localiza plink
$plink = (Get-Command plink.exe -ErrorAction SilentlyContinue).Source
foreach ($cand in @("$env:ProgramFiles\PuTTY\plink.exe", "${env:ProgramFiles(x86)}\PuTTY\plink.exe")) {
    if (-not $plink -and (Test-Path $cand)) { $plink = $cand }
}
if (-not $plink) {
    Write-Host "[pli-tunnel] plink.exe não encontrado. Instale: winget install PuTTY.PuTTY" -ForegroundColor Red
    exit 1
}

# Localiza a chave PPK
$ppk = $null
foreach ($cand in @(
    "D:\REPOSITORIOS\sigma-pli\chave_ppk\SRV-SISTEMA-30001480.ppk",
    "D:\REPOSITORIOS\PLI-HazardTrack\SRV-SISTEMA-30001480.ppk"
)) { if (-not $ppk -and (Test-Path $cand)) { $ppk = $cand } }
if (-not $ppk) {
    Write-Host "[pli-tunnel] Chave PPK não encontrada." -ForegroundColor Red
    exit 1
}

if (-not (Test-Port $VmHost $SshPort 4000)) {
    Write-Host "[pli-tunnel] SSH ${VmHost}:${SshPort} inacessível. Libere seu IP (rede Claro) na porta 22 do Security Group AWS." -ForegroundColor Yellow
    exit 1
}

# Aceita o host key na primeira conexão (best-effort, não-batch).
try { "y`n" | & $plink -ssh -P $SshPort -i $ppk "$VmUser@$VmHost" "exit" 2>&1 | Out-Null } catch { }

$localSpec = "${LocalPort}:127.0.0.1:${RemotePort}"
Write-Host "[pli-tunnel] Abrindo 127.0.0.1:${LocalPort} -> VM:${RemotePort} ..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $plink -ArgumentList @(
    "-ssh", "-batch", "-P", "$SshPort", "-i", $ppk, "-L", $localSpec, "$VmUser@$VmHost", "-N"
) -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    if (Test-Port "127.0.0.1" $LocalPort) {
        Write-Host "[pli-tunnel] Túnel ativo (PID $($proc.Id))." -ForegroundColor Green
        exit 0
    }
    Start-Sleep -Milliseconds 400
}

Write-Host "[pli-tunnel] Falha ao abrir o túnel." -ForegroundColor Red
exit 1
