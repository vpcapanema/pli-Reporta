#!/bin/bash
# =============================================================================
# Deploy do PLI Reporta na VM AWS — script idempotente (padrao PLI-HazardTrack)
#
# Pressupoe arquivos em /tmp/pli-reporta/:
#   - pli-reporta-app-arm64.tar   (ou amd64, conforme a VM)
#   - docker-compose.vm.yml
#   - pli-reporta                 (config nginx do host)
#   - .env.vm                     (PLI_DB_PASSWORD, SECRET_KEY; opcional)
#
# Uso na VM:
#   cd /tmp/pli-reporta
#   bash deploy_vm.sh
# =============================================================================
set -euo pipefail

APP_DIR="/opt/pli-reporta"
NGINX_AVAILABLE="/etc/nginx/sites-available/pli-reporta"
NGINX_ENABLED="/etc/nginx/sites-enabled/pli-reporta"
SRC_DIR="$(pwd)"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
ok()   { printf "    \033[1;32m[ok]\033[0m %s\n" "$1"; }
warn() { printf "    \033[1;33m[!!]\033[0m %s\n" "$1"; }

step "checando pre-requisitos"
command -v docker >/dev/null || { echo "docker nao instalado"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose v2 nao disponivel"; exit 1; }
docker network inspect sigma-backend-network >/dev/null 2>&1 || {
    echo "rede sigma-backend-network nao encontrada (sigma_pli_db precisa estar no ar)"
    exit 1
}
[[ -f "$SRC_DIR/docker-compose.vm.yml" ]] || { echo "compose nao encontrado"; exit 1; }
[[ -f "$SRC_DIR/pli-reporta" ]] || { echo "config nginx nao encontrada"; exit 1; }

TAR=""
for candidate in pli-reporta-app-arm64.tar pli-reporta-app-amd64.tar pli-reporta-app.tar; do
    if [[ -f "$SRC_DIR/$candidate" ]]; then
        TAR="$candidate"
        break
    fi
done
if [[ -n "$TAR" ]]; then
    step "carregando imagem $TAR"
    docker load -i "$SRC_DIR/$TAR"
    ok "imagem pli-reporta-app:latest disponivel"
else
    warn "sem tarball — compose fara build local (mais lento)"
fi

step "instalando stack em $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo cp "$SRC_DIR/docker-compose.vm.yml" "$APP_DIR/docker-compose.vm.yml"
if [[ -f "$SRC_DIR/.env.vm" ]]; then
    sudo cp "$SRC_DIR/.env.vm" "$APP_DIR/.env.vm"
    sudo chmod 600 "$APP_DIR/.env.vm"
    ok ".env.vm instalado"
else
    warn "sem .env.vm — defina PLI_DB_PASSWORD e SECRET_KEY antes de subir"
fi
sudo chown -R "$USER:$USER" "$APP_DIR"

step "instalando virtual host no Nginx do host"
if [[ -f "$NGINX_AVAILABLE" ]]; then
    sudo cp "$NGINX_AVAILABLE" "${NGINX_AVAILABLE}.bak.$(date +%Y%m%d%H%M%S)"
fi
sudo cp "$SRC_DIR/pli-reporta" "$NGINX_AVAILABLE"
sudo ln -sf "$NGINX_AVAILABLE" "$NGINX_ENABLED"
sudo nginx -t
sudo systemctl reload nginx
ok "nginx recarregado (sigma-pli intocado)"

step "subindo container"
cd "$APP_DIR"
docker compose -f docker-compose.vm.yml up -d
ok "container subindo"

step "aguardando healthcheck (max 90s)"
for _ in {1..18}; do
    sleep 5
    if curl -fsS http://127.0.0.1:8090/healthz >/dev/null 2>&1; then
        ok "app respondendo em 127.0.0.1:8090"
        break
    fi
    printf "."
done
echo

step "testando via Nginx"
curl -s -o /dev/null -w "  status=%{http_code} time=%{time_total}s\n" \
    -H "Host: pli-reporta.56-125-163-194.sslip.io" \
    http://127.0.0.1/healthz || true

step "PRONTO"
echo "  URL publica:  http://pli-reporta.56-125-163-194.sslip.io"
echo "  Logs:         docker compose -f $APP_DIR/docker-compose.vm.yml logs -f --tail=200"
