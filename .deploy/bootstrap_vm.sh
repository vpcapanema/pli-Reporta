#!/bin/bash
# =============================================================================
# Bootstrap PLI Reporta na VM AWS (rodar UMA VEZ)
#
# Cria /opt/pli-reporta como clone git + nginx + container isolado.
# Nao toca sigma-pli, pli-hazardtrack nem outros stacks.
#
# Uso na VM (apos liberar SSH):
#   git clone https://github.com/vpcapanema/pli-Reporta.git /tmp/pli-reporta-setup
#   cd /tmp/pli-reporta-setup && bash .deploy/bootstrap_vm.sh
# =============================================================================
set -euo pipefail

APP_DIR="/opt/pli-reporta"
REPO_URL="https://github.com/vpcapanema/pli-Reporta.git"
EXPECTED_REPO_FRAGMENT="vpcapanema/pli-Reporta"
BRANCH="main"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
ok()   { printf "    \033[1;32m[ok]\033[0m %s\n" "$1"; }
warn() { printf "    \033[1;33m[!!]\033[0m %s\n" "$1"; }
die()  { printf "    \033[1;31m[X]\033[0m %s\n" "$1"; exit 1; }

[[ "$APP_DIR" == "/opt/pli-reporta" ]] || die "APP_DIR fora do esperado"

case "$APP_DIR" in
    *sigma*|*hazard*|*fad*|*sra*|/home/ubuntu/*)
        die "PATH suspeito: $APP_DIR"
        ;;
esac

step "checando pre-requisitos"
command -v docker >/dev/null || die "docker nao instalado"
command -v git >/dev/null || die "git nao instalado"
docker compose version >/dev/null 2>&1 || die "docker compose v2 ausente"
docker network inspect sigma-backend-network >/dev/null 2>&1 || {
    die "rede sigma-backend-network ausente (sigma_pli_db precisa estar no ar)"
}
ok "docker e rede postgres OK"

if [[ -d "$APP_DIR/.git" ]]; then
    warn "$APP_DIR ja e um clone git — use update_vm.sh para atualizar"
    exec bash "$APP_DIR/.deploy/update_vm.sh"
fi

SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_KEEP=$(mktemp -d)
[[ -f "$APP_DIR/.env.vm" ]] && cp "$APP_DIR/.env.vm" "$TMP_KEEP/" || true

if [[ -d "$APP_DIR" ]]; then
    step "preservando .env.vm existente"
    [[ -f "$APP_DIR/.env.vm" ]] && cp "$APP_DIR/.env.vm" "$TMP_KEEP/"
    if docker compose -f "$APP_DIR/docker-compose.vm.yml" ps --quiet 2>/dev/null | grep -q .; then
        docker compose -f "$APP_DIR/docker-compose.vm.yml" down || true
    fi
    sudo rm -rf "$APP_DIR"
fi

step "instalando clone em $APP_DIR"
if [[ -d "$SETUP_DIR/.git" && "$(git -C "$SETUP_DIR" remote get-url origin 2>/dev/null || true)" == *"$EXPECTED_REPO_FRAGMENT"* ]]; then
    sudo mkdir -p "$(dirname "$APP_DIR")"
    sudo cp -a "$SETUP_DIR" "$APP_DIR"
    sudo chown -R "$USER:$USER" "$APP_DIR"
    ok "copiado de $SETUP_DIR"
else
    sudo git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
    sudo chown -R "$USER:$USER" "$APP_DIR"
    ok "clonado de $REPO_URL"
fi

cd "$APP_DIR"
REMOTE_NOW=$(git remote get-url origin 2>/dev/null || echo "")
[[ "$REMOTE_NOW" == *"$EXPECTED_REPO_FRAGMENT"* ]] || die "repo errado apos install: $REMOTE_NOW"

if [[ -f "$TMP_KEEP/.env.vm" ]]; then
    cp "$TMP_KEEP/.env.vm" "$APP_DIR/.env.vm"
    chmod 600 "$APP_DIR/.env.vm"
    ok ".env.vm restaurado"
elif [[ ! -f "$APP_DIR/.env.vm" ]]; then
    cp "$APP_DIR/.env.vm.example" "$APP_DIR/.env.vm"
    chmod 600 "$APP_DIR/.env.vm"
    warn "criado .env.vm a partir do example — preencha PLI_DB_PASSWORD e SECRET_KEY"
fi

step "nginx"
NGINX_SRC="$APP_DIR/.deploy/nginx-host/pli-reporta"
sudo cp "$NGINX_SRC" /etc/nginx/sites-available/pli-reporta
sudo ln -sf /etc/nginx/sites-available/pli-reporta /etc/nginx/sites-enabled/pli-reporta
sudo nginx -t
sudo systemctl reload nginx
ok "nginx configurado"

step "build e subida do container"
docker compose -f docker-compose.vm.yml build
docker compose -f docker-compose.vm.yml up -d
ok "container no ar"

exec bash "$APP_DIR/.deploy/update_vm.sh"
