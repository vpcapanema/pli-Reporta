#!/bin/bash
# Habilita HTTPS na VM (Let's Encrypt) — necessário para GPS e câmera no navegador.
set -euo pipefail

PUBLIC_HOST="pli-reporta.56-125-163-194.sslip.io"
APP_DIR="/opt/pli-reporta"
NGINX_SRC_HTTP="$APP_DIR/.deploy/nginx-host/pli-reporta"
NGINX_SRC_HTTPS="$APP_DIR/.deploy/nginx-host/pli-reporta-https"
NGINX_DST="/etc/nginx/sites-available/pli-reporta"
EMAIL="${CERTBOT_EMAIL:-admin@${PUBLIC_HOST}}"

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
ok()   { printf "    \033[1;32m[ok]\033[0m %s\n" "$1"; }
die()  { printf "    \033[1;31m[X]\033[0m %s\n" "$1"; exit 1; }

[[ -d "$APP_DIR" ]] || die "Clone em $APP_DIR nao encontrado"
[[ -f "$NGINX_SRC_HTTP" ]] || die "Config HTTP ausente em $NGINX_SRC_HTTP"

step "preparando webroot ACME"
sudo mkdir -p /var/www/certbot
sudo chown -R www-data:www-data /var/www/certbot 2>/dev/null || sudo chmod 755 /var/www/certbot

step "instalando certbot (se necessario)"
if ! command -v certbot >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo apt-get install -y certbot
fi

step "publicando nginx HTTP com desafio ACME"
sudo cp "$NGINX_SRC_HTTP" "$NGINX_DST"
sudo ln -sf "$NGINX_DST" /etc/nginx/sites-enabled/pli-reporta
sudo nginx -t
sudo systemctl reload nginx

step "emitindo certificado TLS para $PUBLIC_HOST"
sudo certbot certonly --webroot \
    -w /var/www/certbot \
    -d "$PUBLIC_HOST" \
    --non-interactive --agree-tos -m "$EMAIL" \
    --deploy-hook "systemctl reload nginx"

[[ -f "/etc/letsencrypt/live/$PUBLIC_HOST/fullchain.pem" ]] \
    || die "Certificado nao encontrado apos certbot"

step "ativando virtual host HTTPS"
[[ -f "$NGINX_SRC_HTTPS" ]] || die "Config HTTPS ausente"
sudo cp "$NGINX_SRC_HTTPS" "$NGINX_DST"
sudo nginx -t
sudo systemctl reload nginx

ok "HTTPS ativo: https://$PUBLIC_HOST/"
ok "GPS e camera do navegador passam a funcionar (contexto seguro)"
