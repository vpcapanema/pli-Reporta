#!/bin/bash
# Build nativo ARM64 na VM + deploy inicial (primeira instalacao).
# Chamado pelo laptop via: scripts/deploy-vm-first.ps1 -BuildOnVm
set -euo pipefail

APP_DIR="/opt/pli-reporta"
BUILD_DIR="/tmp/pli-reporta-build"
REPO="https://github.com/vpcapanema/pli-Reporta.git"
NGINX_DST="/etc/nginx/sites-available/pli-reporta"
PUBLIC_HOST="pli-reporta.56-125-163-194.sslip.io"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
ok()   { printf "    \033[1;32m[ok]\033[0m %s\n" "$1"; }
die()  { printf "    \033[1;31m[X]\033[0m %s\n" "$1"; exit 1; }

[[ -n "${PLI_DB_PASSWORD:-}" ]] || die "PLI_DB_PASSWORD nao definida"
[[ -n "${SECRET_KEY:-}" ]] || die "SECRET_KEY nao definida"

step "pre-requisitos"
command -v docker >/dev/null || die "docker ausente"
command -v git >/dev/null || die "git ausente"
docker network inspect sigma-backend-network >/dev/null 2>&1 || die "rede sigma-backend-network ausente"
ok "docker e postgres OK"

step "clone GitHub (main)"
rm -rf "$BUILD_DIR"
git clone --depth 1 --branch main "$REPO" "$BUILD_DIR"
ok "clone em $BUILD_DIR"

step "configurando .env.vm"
cat > "$BUILD_DIR/.env.vm" <<EOF
PLI_DB_PASSWORD=$PLI_DB_PASSWORD
SECRET_KEY=$SECRET_KEY
PUBLIC_BASE_URL=http://$PUBLIC_HOST
SIGMA_API_BASE_URL=http://host.docker.internal
EOF
chmod 600 "$BUILD_DIR/.env.vm"
ok ".env.vm criado"

step "build imagem (ARM64 nativo)"
cd "$BUILD_DIR"
docker compose -f docker-compose.vm.yml build
ok "imagem pli-reporta-app:latest"

step "instalando em $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo rm -rf "$APP_DIR"/*
sudo cp -a "$BUILD_DIR"/. "$APP_DIR"/
sudo chown -R "$USER:$USER" "$APP_DIR"
chmod 600 "$APP_DIR/.env.vm"
chmod +x "$APP_DIR/.deploy/"*.sh
ok "arquivos em $APP_DIR"

step "nginx"
sudo cp "$APP_DIR/.deploy/nginx-host/pli-reporta" "$NGINX_DST"
sudo ln -sf "$NGINX_DST" /etc/nginx/sites-enabled/pli-reporta
sudo nginx -t
sudo systemctl reload nginx
ok "nginx configurado"

step "subindo container"
cd "$APP_DIR"
docker compose --env-file .env.vm -f docker-compose.vm.yml up -d --force-recreate
ok "container no ar"

step "healthcheck"
for _ in {1..18}; do
    sleep 5
    if curl -fsS http://127.0.0.1:8090/healthz >/dev/null 2>&1; then
        ok "healthz OK"
        break
    fi
done
curl -s -o /dev/null -w "  publico status=%{http_code}\n" \
    -H "Host: $PUBLIC_HOST" http://127.0.0.1/healthz || true

SHA=$(git -C "$APP_DIR" rev-parse HEAD)
echo "$SHA" > "$APP_DIR/.deploy/last_deploy_sha"
step "DEPLOY CONCLUIDO"
echo "  commit: $SHA"
echo "  url:    http://$PUBLIC_HOST"
