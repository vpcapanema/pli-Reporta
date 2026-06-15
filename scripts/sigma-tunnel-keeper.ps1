# Mantem o tunel SIGMA ativo enquanto o backend local estiver rodando.
param(
    [int]$ParentPid,
    [int]$LocalPort = 15433,
    [int]$IntervalSeconds = 15
)

$ErrorActionPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

$root = Split-Path -Parent $PSScriptRoot
$tunnelScript = Join-Path $PSScriptRoot "sigma-tunnel.ps1"
$statusFile = Join-Path $root ".sigma-tunnel-keeper.status"

function Test-TcpPortOpen {
    param([string]$TargetHost, [int]$Port, [int]$TimeoutMs = 1200)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($async)
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Write-Status([string]$state, [string]$detail) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')|$state|$detail"
    Set-Content -Path $statusFile -Value $line -Encoding UTF8
}

if (-not $ParentPid -or -not (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue)) {
    exit 0
}

Write-Status "running" "keeper iniciado (parent PID $ParentPid)"

while (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {
    if (-not (Test-TcpPortOpen "127.0.0.1" $LocalPort)) {
        Write-Status "connecting" "abrindo tunel SIGMA..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File $tunnelScript -WaitSeconds 12 -LocalPort $LocalPort | Out-Null
        if (Test-TcpPortOpen "127.0.0.1" $LocalPort) {
            Write-Status "connected" "127.0.0.1:$LocalPort OK"
        } else {
            Write-Status "waiting" "SSH 22 indisponivel na rede atual; nova tentativa em ${IntervalSeconds}s"
        }
    } else {
        Write-Status "connected" "127.0.0.1:$LocalPort OK"
    }
    Start-Sleep -Seconds $IntervalSeconds
}

Write-Status "stopped" "parent encerrado"
Remove-Item $statusFile -Force -ErrorAction SilentlyContinue
