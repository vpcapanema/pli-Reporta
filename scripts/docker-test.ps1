# Build e teste local — container isolado (padrao VM, sem network_mode: host).
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/docker-test.ps1
param(
    [int]$HostPort = 8081,
    [string]$DbHost = '56.125.163.194',
    [int]$DbPort = 5433
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

function Get-PlidbUrl {
    $parent = Split-Path -Parent $root
    $credFile = Get-ChildItem -LiteralPath $parent -Recurse -Filter 'CREDENCIAIS_VALIDADAS.txt' -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match 'DOCUMENTA' } |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $credFile) { throw 'CREDENCIAIS_VALIDADAS.txt nao encontrada em DOCUMENTACAO_IA' }
    $text = Get-Content -LiteralPath $credFile -Raw
    if ($text -match 'postgresql\+psycopg://pli_user:[^@\s]+@[^\s]+/pli_reporta') {
        return $Matches[0] -replace '@56\.125\.163\.194:5433', "@${DbHost}:${DbPort}"
    }
    throw 'DATABASE_URL pli_reporta nao encontrada'
}

function Wait-Health([string]$Url, [int]$Seconds = 90) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { return $r.Content }
        } catch {}
        Start-Sleep -Seconds 2
    }
    throw "Timeout aguardando $Url"
}

Step '1/4 Build imagem isolada'
docker build -t pli-reporta-app:local .
if ($LASTEXITCODE -ne 0) { exit 1 }

$dbUrl = Get-PlidbUrl
$container = 'pli-reporta-test'
$network = 'pli_reporta_test_net'
docker rm -f $container 2>$null | Out-Null
docker network rm $network 2>$null | Out-Null
docker network create $network | Out-Null

Step '2/4 Container isolado (127.0.0.1:PORT -> 8090 interno)'
docker run -d --name $container --network $network `
    -p "127.0.0.1:${HostPort}:8090" `
    -e "APP_ENV=production" `
    -e "PORT=8090" `
    -e "DATABASE_URL=$dbUrl" `
    -e "SIGMA_API_BASE_URL=http://56.125.163.194" `
    -e "PUBLIC_BASE_URL=http://localhost:$HostPort" `
    -e "PHOTO_STORAGE_DIR=/app/backend/storage/photos" `
    -e "SECRET_KEY=docker-local-test-secret" `
    pli-reporta-app:local | Out-Null
if ($LASTEXITCODE -ne 0) { exit 1 }

try {
    Step '3/4 Healthcheck'
    $healthUrl = "http://127.0.0.1:$HostPort/healthz"
    $body = Wait-Health $healthUrl
    Write-Host $body -ForegroundColor Green
    if ($body -notmatch '"db"\s*:\s*"ok"') { throw 'healthz sem db ok' }

    Step '4/4 POST manifestacao'
    $py = @'
import sys
from datetime import datetime, timezone
from io import BytesIO
import httpx
from PIL import Image

base = "http://127.0.0.1:HOSTPORT"
buf = BytesIO()
Image.new("RGB", (32, 32), (180, 180, 180)).save(buf, format="JPEG")
jpeg = buf.getvalue()
with httpx.Client(base_url=base, timeout=30.0) as c:
    nonce = c.get("/api/capture-nonce").json()["nonce"]
    files = {"photo": ("t.jpg", jpeg, "image/jpeg")}
    data = {
        "lat": "-23.55", "lon": "-46.63", "category": "sugestao",
        "interaction_type": "manifestacao",
        "description": "Smoke test Docker isolado - manifestacao de validacao.",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "capture_nonce": nonce, "client_id": "docker-smoke",
    }
    r = c.post("/api/reports", files=files, data=data)
    print("status", r.status_code)
    print(r.text[:300])
    sys.exit(0 if r.status_code == 201 else 1)
'@
    $py = $py -replace 'HOSTPORT', "$HostPort"
    $py | & python -
    if ($LASTEXITCODE -ne 0) { throw 'POST /api/reports falhou' }

    Write-Host ""
    Write-Host "OK - container isolado validado em http://localhost:$HostPort/" -ForegroundColor Green
    Write-Host "Na VM a URL publica sera: http://pli-reporta.56-125-163-194.sslip.io" -ForegroundColor Green
}
finally {
    Write-Host ""
    Write-Host "Limpando container de teste..." -ForegroundColor Yellow
    docker rm -f $container 2>$null | Out-Null
    docker network rm $network 2>$null | Out-Null
}
