# PLI Reporta — iniciar, reiniciar ou limpar porta do backend.
# Uso: powershell -File scripts/backend-dev.ps1 [-Action Start|Restart|KillPort] [-Port 8080]
param(
    [ValidateSet('Start', 'Restart', 'KillPort')][string]$Action = 'Start',
    [int]$Port = 8080
)

$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
if ($Host.Name -eq 'ConsoleHost') { chcp 65001 > $null }

$root = Split-Path -Parent $PSScriptRoot
$python = & (Join-Path $root 'scripts\lib\resolve-python.ps1') -Root $root
if (-not $python) { exit 1 }

function Write-Step([string]$n, [string]$msg) {
    Write-Host ''
    Write-Host "=== [$n] $msg ===" -ForegroundColor Cyan
}

function Test-EnvPattern([string]$pattern) {
    $envFile = Join-Path $root '.env'
    if (-not (Test-Path $envFile)) { return $false }
    return $null -ne (Select-String -Path $envFile -Pattern $pattern -ErrorAction SilentlyContinue)
}

function Test-NeedsPostgresTunnel { Test-EnvPattern '^\s*DATABASE_URL=.*15433' }
function Test-UsesPostgres { Test-EnvPattern '^\s*DATABASE_URL=postgresql' }

function Test-PortBindable([int]$P) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $P)
        $listener.ExclusiveAddressUse = $true
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) { try { $listener.Stop() } catch {} }
    }
}

function Get-PortListenerPids([int]$P) {
    $fromNetstat = @(
        netstat -ano -p tcp 2>$null |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -match "^TCP\s+(127\.0\.0\.1|\[::1\]|0\.0\.0\.0|\[::\]):$P\s+.*LISTENING\s+\d+\s*$" } |
            ForEach-Object { if ($_ -match 'LISTENING\s+(\d+)\s*$') { [int]$matches[1] } }
    )
    $fromCmdlet = @(
        Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
    @($fromNetstat + $fromCmdlet) | Where-Object { $_ -gt 4 } | Sort-Object -Unique
}

function Stop-ProjectPythonWorkers {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^python(\.exe|w\.exe)?$' -and
            $_.CommandLine -match 'dev_server\.py|uvicorn|backend\.main'
        } |
        ForEach-Object {
            Write-Host "[pli-reporta] Encerrando worker Python PID $($_.ProcessId)"
            taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null
        }
}

function Stop-LivePortOwners([int]$P) {
    foreach ($procId in (Get-PortListenerPids -Port $P)) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        Write-Host "[pli-reporta] Encerrando $($proc.ProcessName) PID $procId (porta $P)"
        taskkill /F /T /PID $procId 2>$null | Out-Null
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

function Clear-BackendPort([int]$P) {
    Write-Host "[pli-reporta] Limpando porta $P..." -ForegroundColor Yellow
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        Stop-ProjectPythonWorkers
        Stop-LivePortOwners -P $P
        if (Test-PortBindable -P $P) {
            Write-Host "[pli-reporta] Porta $P disponivel para bind (tentativa $attempt)." -ForegroundColor Green
            return $true
        }
        $live = @()
        foreach ($procId in (Get-PortListenerPids -Port $P)) {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) { $live += "$procId ($($proc.ProcessName))" }
        }
        if ($live.Count -gt 0) {
            Write-Host "[pli-reporta] Tentativa $attempt - ainda ocupada: $($live -join ', ')"
        } else {
            Write-Host "[pli-reporta] Tentativa $attempt - bind bloqueado (socket fantasma? aguardando...)"
        }
        Start-Sleep -Milliseconds 900
    }
    Write-Host "[pli-reporta] ERRO: nao foi possivel reservar a porta $P." -ForegroundColor Red
    Write-Host '[pli-reporta] Feche outros terminais do backend ou reinicie o VS Code.' -ForegroundColor Red
    return $false
}

function Start-BrowserWhenReady([int]$P) {
    $url = "http://localhost:$P/"
    Write-Host "[pli-reporta] Aguardando /healthz para abrir $url no navegador padrao..." -ForegroundColor Yellow
    Start-Job -ScriptBlock {
        param($port, $homeUrl)
        for ($i = 0; $i -lt 120; $i++) {
            try {
                $req = [System.Net.WebRequest]::Create("http://127.0.0.1:$port/healthz")
                $req.Timeout = 2000
                $req.Method = 'GET'
                $resp = $req.GetResponse()
                $code = [int]$resp.StatusCode
                $resp.Close()
                if ($code -ge 200 -and $code -lt 500) {
                    Start-Process $homeUrl
                    return
                }
            } catch {
                Start-Sleep -Milliseconds 500
            }
        }
    } -ArgumentList $P, $url | Out-Null
}

if ($Action -eq 'KillPort') {
    if (-not (Clear-BackendPort -P $Port)) { exit 1 }
    exit 0
}

$label = if ($Action -eq 'Restart') { 'Reiniciando' } else { 'Iniciando' }

Write-Step '1/4' "Matando e limpando processos na porta $Port"
if (-not (Clear-BackendPort -P $Port)) { exit 1 }

Write-Step '2/4' 'Preparando ambiente (tunel DB se necessario)'
if (Test-NeedsPostgresTunnel) {
    Write-Host '[pli-reporta] DATABASE_URL usa porta 15433; tentando tunel SSH...' -ForegroundColor Yellow
    $tunnelScript = Join-Path $root 'scripts\sigma-tunnel.ps1'
    if (Test-Path $tunnelScript) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $tunnelScript
        if ($LASTEXITCODE -ne 0) {
            Write-Host '[pli-reporta] AVISO: tunel SSH indisponivel; banco remoto pode falhar.' -ForegroundColor Yellow
        }
    }
} else {
    Write-Host '[pli-reporta] Login moderador via SIGMA_API_BASE_URL (sem tunel SSH)' -ForegroundColor Green
}

if (Test-UsesPostgres) {
    Write-Host '[pli-reporta] Liberando conexoes ociosas no PostgreSQL...' -ForegroundColor Yellow
    Set-Location $root
    $env:PYTHONPATH = $root
    & $python scripts/release_db_connections.py
}

Write-Step '3/4' "Confirmando porta $Port livre antes do backend"
if (-not (Clear-BackendPort -P $Port)) { exit 1 }

Write-Step '4/4' "$label backend em http://localhost:$Port/"
Set-Location $root
$env:PYTHONPATH = $root
if ($Action -in 'Start', 'Restart') { Start-BrowserWhenReady -P $Port }
& $python scripts/dev_server.py $Port
