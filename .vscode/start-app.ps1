# PLI Reporta - inicia tudo: mata porta 8080, sobe uvicorn e abre o navegador.
$ErrorActionPreference = 'SilentlyContinue'

$port = 8080
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'venv\Scripts\python.exe'

# 1) Matar qualquer processo escutando na porta
$conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($conns) {
    $conns | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Write-Host "[pli-reporta] Matando PID $_ na porta $port"
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "[pli-reporta] Porta $port livre."
}

# 2) Disparar watcher em background que abre o navegador quando o backend responder
Start-Job -ScriptBlock {
    param($p)
    for ($i = 0; $i -lt 120; $i++) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $client.Connect('localhost', $p)
            $client.Close()
            Start-Process "http://localhost:$p/"
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
} -ArgumentList $port | Out-Null

# 3) Subir o backend em primeiro plano (mantem o terminal da task vivo)
Write-Host "[pli-reporta] Subindo uvicorn em http://localhost:$port/ ..."
Set-Location $root
& $python -m uvicorn backend.main:app --reload --port $port
