# Lib compartilhada: libera porta do backend (uvicorn + workers orfaos no Windows).
param([int]$Port = 8080)

function Test-DevPortFree([int]$P) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $P)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) {
            try { $listener.Stop() } catch {}
        }
    }
}

function Stop-DevBackendProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) { return }
            if ($cmd -match 'multiprocessing\.spawn|dev_server\.py|uvicorn|backend\.main|pli-Reporta') {
                Write-Host "[pli-reporta] encerrando PID $($_.ProcessId)"
                taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null
            }
        }

    foreach ($procId in @(
            Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique
        )) {
        if ($procId -le 4) { continue }
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        Write-Host "[pli-reporta] encerrando $($proc.ProcessName) PID $procId (porta $Port)"
        taskkill /F /T /PID $procId 2>$null | Out-Null
    }
}

function Clear-DevPort {
    param([int]$P = $Port)

    Write-Host "[pli-reporta] Limpando porta $P..." -ForegroundColor Yellow
    for ($i = 1; $i -le 8; $i++) {
        Stop-DevBackendProcesses
        if (Test-DevPortFree -P $P) {
            Write-Host "[pli-reporta] Porta $P livre." -ForegroundColor Green
            return $true
        }
        Start-Sleep -Milliseconds 600
    }
    Write-Host "[pli-reporta] ERRO: porta $P indisponivel." -ForegroundColor Red
    return $false
}
