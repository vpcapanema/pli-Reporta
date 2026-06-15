# Tunel SSH PostgreSQL SIGMA — 127.0.0.1:15433 -> VM:5433 (padrao sigma-pli).
param(
    [int]$LocalPort = 15433,
    [int]$RemotePort = 5433,
    [string]$VmHost = "56.125.163.194",
    [int]$SshPort = 22,
    [string]$VmUser = "ubuntu",
    [int]$WaitSeconds = 15
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root ".sigma-postgres-tunnel.pid"
$sigmaRoot = Join-Path (Split-Path -Parent $root) "sigma-pli"
$ppk = Join-Path $sigmaRoot "chave_ppk\SRV-SISTEMA-30001480.ppk"
$localSpec = "${LocalPort}:127.0.0.1:${RemotePort}"
$vmTarget = "${VmUser}@${VmHost}"
$logFile = Join-Path $env:TEMP ("pli_reporta_plink_{0}.log" -f $LocalPort)

function Write-Tunnel([string]$msg, [string]$color = "White") {
    Write-Host "[sigma-tunnel] $msg" -ForegroundColor $color
}

function Get-PlinkExe {
    $found = Get-Command plink.exe -ErrorAction SilentlyContinue
    $candidates = @(
        $(if ($found) { $found.Source }),
        "$env:ProgramFiles\PuTTY\plink.exe",
        "${env:ProgramFiles(x86)}\PuTTY\plink.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $candidates) { return $null }
    return $candidates[0]
}

function Test-TcpPortOpen {
    param(
        [string]$TargetHost,
        [int]$Port,
        [int]$TimeoutMs = 1500
    )
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-ExistingTunnelProcess {
    $allPlink = Get-CimInstance Win32_Process -Filter "name = 'plink.exe'" -ErrorAction SilentlyContinue
    if (-not $allPlink) { return $null }
    return $allPlink | Where-Object {
        $_.CommandLine -and $_.CommandLine -match [regex]::Escape("-L $localSpec")
    } | Select-Object -First 1
}

function Stop-ExistingTunnel {
    $existing = Get-ExistingTunnelProcess
    if ($existing) {
        Stop-Process -Id $existing.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $pidFile) {
        $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($oldPid) {
            Stop-Process -Id ([int]$oldPid) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

function Initialize-SshHostKeyCache {
    param(
        [string]$Plink,
        [string]$PpkPath,
        [string]$Target
    )
    if (-not (Test-TcpPortOpen -TargetHost $VmHost -Port $SshPort -TimeoutMs 2500)) {
        return $false
    }

    $probeErr = Join-Path $env:TEMP "pli_reporta_plink_probe_err.txt"
    Remove-Item $probeErr -Force -ErrorAction SilentlyContinue

    $probe = Start-Process -FilePath $Plink -ArgumentList @(
        "-P", "$SshPort", "-i", $PpkPath, $Target, "exit"
    ) -NoNewWindow -Wait -PassThru -RedirectStandardError $probeErr

    if ($probe.ExitCode -eq 0) { return $true }

    $err = Get-Content $probeErr -Raw -ErrorAction SilentlyContinue
    if ($err -and $err -match "host key") {
        Write-Tunnel "Registrando chave SSH da VM (primeira conexao)..." "Yellow"
        $null = "y" | & $Plink -P $SshPort -i $PpkPath $Target "exit" 2>&1
        return $true
    }

    return $false
}

function Read-PlinkLogTail {
    if (-not (Test-Path $logFile)) { return $null }
    $raw = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
    if (-not $raw) { return $null }
    $lines = ($raw -split "`r?`n") | Where-Object { $_.Trim() }
    if ($lines.Count -eq 0) { return $null }
    $take = [Math]::Min(4, $lines.Count)
    return ($lines[(-1 * $take)..-1] -join " | ")
}

# --- Ja ativo? ---
if (Test-TcpPortOpen -TargetHost "127.0.0.1" -Port $LocalPort) {
    $live = Get-ExistingTunnelProcess
    if ($live) {
        Write-Tunnel "Porta $LocalPort ja ativa (PID $($live.ProcessId))." "Green"
    } else {
        Write-Tunnel "Porta $LocalPort ja ativa." "Green"
    }
    exit 0
}

$plink = Get-PlinkExe
if (-not $plink) {
    Write-Tunnel "plink.exe nao encontrado. Instale PuTTY (winget install PuTTY.PuTTY)." "Red"
    exit 1
}
if (-not (Test-Path $ppk)) {
    Write-Tunnel "Chave PPK nao encontrada: $ppk" "Red"
    exit 1
}

Stop-ExistingTunnel
Remove-Item $logFile -Force -ErrorAction SilentlyContinue

if (-not (Initialize-SshHostKeyCache -Plink $plink -PpkPath $ppk -Target $vmTarget)) {
    if (-not (Test-TcpPortOpen -TargetHost $VmHost -Port $SshPort -TimeoutMs 2500)) {
        Write-Tunnel "SSH ${VmHost}:${SshPort} indisponivel na rede atual (porta 22 bloqueada ou filtrada). Tentativa de tunel mesmo assim..." "Yellow"
    }
}

Write-Tunnel "Conectando SSH $VmHost e abrindo 127.0.0.1:${LocalPort} -> VM:${RemotePort} ..." "Cyan"

$proc = Start-Process -FilePath $plink -ArgumentList @(
    "-batch",
    "-P", "$SshPort",
    "-i", $ppk,
    "-log", $logFile,
    "-L", $localSpec,
    $vmTarget,
    "-N"
) -WindowStyle Hidden -PassThru

$proc.Id | Out-File -FilePath $pidFile -Encoding ascii -Force

$deadline = (Get-Date).AddSeconds($WaitSeconds)
$listening = $false
while ((Get-Date) -lt $deadline) {
    if ($proc.HasExited) { break }
    if (Test-TcpPortOpen -TargetHost "127.0.0.1" -Port $LocalPort) {
        $listening = $true
        break
    }
    Start-Sleep -Milliseconds 400
}

if ($listening) {
    Write-Tunnel "Tunel ativo (PID $($proc.Id))." "Green"
    exit 0
}

$diag = @()
if ($proc.HasExited) {
    $code = if ($null -ne $proc.ExitCode) { $proc.ExitCode } else { "?" }
    $diag += "plink encerrou (exit $code)"
}
$logTail = Read-PlinkLogTail
if ($logTail) { $diag += $logTail }

Write-Tunnel "Falha ao abrir tunel." "Red"
if ($diag.Count -gt 0) {
    Write-Tunnel ($diag -join " | ") "Yellow"
}
Write-Tunnel "Verifique se a porta SSH 22 esta liberada para seu IP no Security Group da AWS. O keeper tentara reconectar em background." "Yellow"
Stop-ExistingTunnel
exit 1
