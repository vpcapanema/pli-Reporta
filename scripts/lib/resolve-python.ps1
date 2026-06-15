# Resolve o interpretador Python do projeto (.venv ou venv) e sincroniza requirements.
param(
    [Parameter(Mandatory)][string]$Root
)

$python = @(
    (Join-Path $Root '.venv\Scripts\python.exe'),
    (Join-Path $Root 'venv\Scripts\python.exe')
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $python) {
    Write-Host '[pli-reporta] ERRO: nenhum venv encontrado (.venv ou venv).' -ForegroundColor Red
    Write-Host '[pli-reporta] Rode: python -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt' -ForegroundColor Red
    exit 1
}

$req = Join-Path $Root 'requirements.txt'
Write-Host "[pli-reporta] Python: $python" -ForegroundColor DarkGray
Write-Host '[pli-reporta] Sincronizando dependencias (requirements.txt)...' -ForegroundColor Yellow
& $python -m pip install -r $req -q
if ($LASTEXITCODE -ne 0) {
    Write-Host '[pli-reporta] AVISO: pip install falhou; o backend pode falhar ao subir.' -ForegroundColor Yellow
}

return $python
