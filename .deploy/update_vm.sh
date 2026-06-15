#!/bin/bash
# =============================================================================
# Atualizar PLI Reporta na VM AWS (sincroniza com GitHub)
#
# Fluxo recomendado:
#   (laptop)  git commit && git push
#   (laptop)  powershell -File scripts/sync-vm.ps1
#   — ou na VM diretamente:
#   (vm)      bash /opt/pli-reporta/.deploy/update_vm.sh
#
# O script:
#   1. git pull --ff-only (mantem .env.vm intocado)
#   2. rebuilda imagem so se arquivos de runtime mudaram (cache Docker)
#   3. recria container quando a imagem mudou
#   4. recarrega Nginx se a config mudou
#   5. valida /healthz publico
#
# Reverter:
#   cd /opt/pli-reporta
#   git log --oneline -5
#   git reset --hard <sha-anterior>
#   bash .deploy/update_vm.sh
# =============================================================================
set -euo pipefail

APP_DIR="/opt/pli-reporta"
COMPOSE_FILE="$APP_DIR/docker-compose.vm.yml"
NGINX_SRC="$APP_DIR/.deploy/nginx-host/pli-reporta"
NGINX_DST="/etc/nginx/sites-available/pli-reporta"
EXPECTED_REPO_FRAGMENT="vpcapanema/pli-Reporta"
PUBLIC_HOST="pli-reporta.56-125-163-194.sslip.io"
DEPLOY_MARKER="$APP_DIR/.deploy/last_deploy_sha"

# Arquivos que exigem rebuild da imagem Docker
REBUILD_PATTERNS=(
    'Dockerfile'
    '.dockerignore'
    'requirements.txt'
    'backend/'
    'frontend/'
    'scripts/'
    'migrations/'
    'alembic.ini'
    'data/camadas-do-sistema/'
    'docker-compose.vm.yml'
)

step() { printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
ok()   { printf "    \033[1;32m[ok]\033[0m %s\n" "$1"; }
warn() { printf "    \033[1;33m[!!]\033[0m %s\n" "$1"; }
die()  { printf "    \033[1;31m[X]\033[0m %s\n" "$1"; exit 1; }

needs_rebuild() {
    local changed_file="$1"
    local pattern
    for pattern in "${REBUILD_PATTERNS[@]}"; do
        if [[ "$changed_file" == "$pattern"* ]] || [[ "$changed_file" == "$pattern" ]]; then
            return 0
        fi
    done
    return 1
}

runtime_matches_git() {
    local sha="$1"
    if [[ ! -f "$DEPLOY_MARKER" ]]; then
        return 1
    fi
    local marker
    marker=$(tr -d '[:space:]' < "$DEPLOY_MARKER")
    [[ "$marker" == "$sha" ]] || return 1
    curl -fsS http://127.0.0.1:8090/healthz >/dev/null 2>&1 || return 1
    curl -fsS http://127.0.0.1:8090/api/public/ 2>/dev/null | grep -q '"simbologia"' || return 1
    return 0
}

[[ "$APP_DIR" == "/opt/pli-reporta" ]] || die "APP_DIR fora do esperado: $APP_DIR"
[[ -d "$APP_DIR/.git" ]] || die "$APP_DIR nao e clone git (rode bootstrap_vm.sh primeiro)"

cd "$APP_DIR"

ACTUAL_REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$ACTUAL_REMOTE" != *"$EXPECTED_REPO_FRAGMENT"* ]]; then
    die "remote inesperado: '$ACTUAL_REMOTE' (esperava '$EXPECTED_REPO_FRAGMENT')"
fi
ok "repo verificado: $ACTUAL_REMOTE"

if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "descartando alteracoes locais para alinhar com GitHub (.env.vm preservado)"
    git reset --hard HEAD
fi

step "git pull (branch: $(git branch --show-current))"
OLD_SHA=$(git rev-parse HEAD)
git fetch --quiet origin
git pull --ff-only
NEW_SHA=$(git rev-parse HEAD)

CHANGED_FILES=()
if [[ "$OLD_SHA" != "$NEW_SHA" ]]; then
    mapfile -t CHANGED_FILES < <(git diff --name-only "$OLD_SHA" "$NEW_SHA")
    ok "atualizado: ${OLD_SHA:0:7} -> ${NEW_SHA:0:7} ($((${#CHANGED_FILES[@]})) arquivo(s))"
else
    warn "ja no commit ${NEW_SHA:0:7} — verificando runtime mesmo assim"
fi

DO_REBUILD=0
DO_NGINX=0
DEPLOYED_SHA=""
if [[ -f "$DEPLOY_MARKER" ]]; then
    DEPLOYED_SHA=$(tr -d '[:space:]' < "$DEPLOY_MARKER")
fi

if [[ ${#CHANGED_FILES[@]} -eq 0 ]]; then
        if [[ "$OLD_SHA" == "$NEW_SHA" ]]; then
        if runtime_matches_git "$NEW_SHA"; then
            ok "git e runtime alinhados ($NEW_SHA)"
            exit 0
        fi
        if [[ -n "$DEPLOYED_SHA" && "$DEPLOYED_SHA" != "$NEW_SHA" ]]; then
            warn "git em ${NEW_SHA:0:7} mas runtime em ${DEPLOYED_SHA:0:7} — rebuild necessario"
            mapfile -t CHANGED_FILES < <(git diff --name-only "$DEPLOYED_SHA" "$NEW_SHA" 2>/dev/null || true)
        else
            warn "marcador de deploy ausente — rebuild de seguranca"
        fi
        DO_REBUILD=1
    else
        DO_REBUILD=1
    fi
else
    for f in "${CHANGED_FILES[@]}"; do
        if needs_rebuild "$f"; then DO_REBUILD=1; fi
        if [[ "$f" == .deploy/nginx-host/* ]]; then DO_NGINX=1; fi
    done
fi

if [[ $DO_REBUILD -eq 0 && -n "$DEPLOYED_SHA" && "$DEPLOYED_SHA" != "$NEW_SHA" ]]; then
    warn "commit mudou mas nenhum arquivo de runtime listado — rebuild forcado"
    DO_REBUILD=1
fi

if [[ $DO_REBUILD -eq 0 && -z "$DEPLOYED_SHA" ]]; then
    warn "sem marcador de deploy — rebuild forcado"
    DO_REBUILD=1
fi

if [[ $DO_REBUILD -eq 0 && $DO_NGINX -eq 0 ]]; then
    ok "somente docs/testes alterados — runtime inalterado ($NEW_SHA)"
    echo "$NEW_SHA" > "$DEPLOY_MARKER"
    exit 0
fi

if [[ $DO_NGINX -eq 1 || ! -f "$NGINX_DST" ]]; then
    step "atualizando Nginx do host"
    if [[ -f "$NGINX_SRC" ]]; then
        if ! sudo cmp -s "$NGINX_SRC" "$NGINX_DST" 2>/dev/null; then
            sudo cp "$NGINX_DST" "${NGINX_DST}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
            sudo cp "$NGINX_SRC" "$NGINX_DST"
            sudo ln -sf "$NGINX_DST" /etc/nginx/sites-enabled/pli-reporta
            sudo nginx -t
            sudo systemctl reload nginx
            ok "nginx reconfigurado"
        else
            ok "nginx inalterado"
        fi
    fi
fi

if [[ $DO_REBUILD -eq 1 ]]; then
    step "rebuild da imagem (somente layers alterados — cache Docker)"
    docker compose -f "$COMPOSE_FILE" build
    ok "imagem atualizada"

    step "recriando container"
    docker compose --env-file "$APP_DIR/.env.vm" -f "$COMPOSE_FILE" up -d --force-recreate
    ok "container recriado"
else
    ok "imagem inalterada — container nao recriado"
fi

step "aguardando /healthz (max 90s)"
for _ in {1..18}; do
    sleep 5
    if curl -fsS http://127.0.0.1:8090/healthz >/dev/null 2>&1; then
        ok "app em 127.0.0.1:8090"
        break
    fi
    printf "."
done
echo

step "teste publico via Nginx"
curl -s -o /dev/null -w "  status=%{http_code} time=%{time_total}s\n" \
    -H "Host: $PUBLIC_HOST" \
    http://127.0.0.1/healthz || true

step "teste do manifesto (/api/public/)"
if ! curl -fsS http://127.0.0.1:8090/api/public/ 2>/dev/null | grep -q '"simbologia"'; then
    die "manifesto sem simbologia apos deploy — container desatualizado"
fi
ok "manifesto com simbologia"

echo "$NEW_SHA" > "$DEPLOY_MARKER"

step "SINCRONIZACAO CONCLUIDA"
echo "  commit VM:    $NEW_SHA"
echo "  url:          http://$PUBLIC_HOST"
echo "  logs:         docker compose -f $COMPOSE_FILE logs -f --tail=200"
