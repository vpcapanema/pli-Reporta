# Operação

## Moderação humana

Faixa cinza (`0.30 ≤ V < 0.70`) entra na fila de moderação em `/acesso`. Gestor vê:

- Foto, mapa, EXIF parseado, sinais de veracidade.
- Reportes vizinhos em raio de 200 m / 24 h.
- Botões: `Publicar`, `Descartar (motivo)`, `Pedir mais info` (não usado no MVP).

Cada decisão grava em `audit_log`.

## Migrações de banco (Alembic)

O schema é versionado com Alembic. A URL do banco vem de `settings.database_url`
(env/.env) — não há URL fixa no `alembic.ini`.

### Banco próprio do PLI Reporta no PostgreSQL da VM

O PLI Reporta grava seus dados em um banco **dedicado** (`pli_reporta`), no mesmo
PostgreSQL da VM que hospeda o SIGMA — mas isolado dele (usuário e banco próprios).
O SIGMA continua sendo usado apenas para autenticação de gestores (via API HTTP).

> O PostgreSQL da VM escuta em `127.0.0.1:5433` (não é público). Ele só é
> alcançável **de dentro da VM** ou via **túnel SSH** a partir de um IP liberado
> na porta 22 do Security Group da AWS.

#### Rota A — direto na VM (recomendado p/ deploy em container)

Conectado na VM por SSH, use o superusuário local (peer auth, sem senha):

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE pli_user LOGIN PASSWORD 'troque-esta-senha';
CREATE DATABASE pli_reporta OWNER pli_user ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE pli_reporta TO pli_user;
SQL
```

O container do PLI Reporta aponta o `DATABASE_URL` para o Postgres do host
(ex.: `host.docker.internal:5433` ou o IP do bridge docker / `--network=host` com
`127.0.0.1:5433`) e o `db_migrate.py` cria o schema no start:

```
DATABASE_URL=postgresql+psycopg://pli_user:<senha>@127.0.0.1:5433/pli_reporta
```

#### Rota B — da sua máquina, via túnel SSH (precisa de admin do PG)

```powershell
# 0) libere seu IP público atual na porta 22 do Security Group (AWS)
# 1) abre o túnel SSH (porta local 15433 -> VM:5433)
powershell -ExecutionPolicy Bypass -File scripts/sigma-tunnel.ps1

# 2) cria banco + usuário dedicados (idempotente)
$env:PGADMIN_HOST="127.0.0.1"; $env:PGADMIN_PORT="15433"
$env:PGADMIN_USER="postgres"; $env:PGADMIN_PASSWORD="<senha-admin>"
$env:PLI_DB_PASSWORD="<senha-do-pli_user>"
python scripts/provision_pli_db.py

# 3) aponta a app para o banco e aplica as migrações
$env:DATABASE_URL="postgresql+psycopg://pli_user:<senha>@127.0.0.1:15433/pli_reporta"
python scripts/db_migrate.py
```

### Comandos Alembic

| Cenário | Comando |
|---|---|
| Aplicar migrações pendentes | `python -m alembic upgrade head` |
| Criar nova migração (autogerada) | `python -m alembic revision --autogenerate -m "descrição"` |
| Ver versão atual | `python -m alembic current` |
| Reverter última | `python -m alembic downgrade -1` |
| Deploy (idempotente/seguro) | `python scripts/db_migrate.py` |

Notas:
- **SQLite (dev/test):** `init_db()` cria as tabelas via metadata; o Alembic é
  opcional, mas `scripts/db_migrate.py` adota o schema existente com `stamp head`.
- **Postgres (produção):** o schema é gerido **exclusivamente** pelo Alembic.
  O `startCommand` do Render roda `scripts/db_migrate.py` antes do uvicorn.
- Após criar/editar modelos em `backend/models.py`, gere a migração com
  `--autogenerate` e **revise** o arquivo em `migrations/versions/` antes de commitar.

## Tarefas periódicas (cron / APScheduler)

| Tarefa | Frequência | Função |
|---|---|---|
| `expire_old` | a cada 10 min | move reportes com `valid_to < now` para `expirado` |
| `recompute_clusters` | a cada 5 min | atualiza `R_confirmacao` em clusters ativos |
| `recompute_reputation` | diária | recalcula `users.reputation` com janela de 30 dias |
| `coverage_report` | semanal | gera relatório de cobertura por município |

## Backups

- SQLite: cópia atomic com `VACUUM INTO` para `backups/pli_reporta_YYYYMMDD.db` diariamente.
- Mídia: `rsync` ou `aws s3 sync` para storage offsite.

## Métricas mínimas

Endpoint `/healthz` retorna:

```json
{
  "status": "ok",
  "db": "ok",
  "storage": "ok",
  "queue_size": 12,
  "active_incidents": 87
}
```

## Chaves operacionais

- `MODERATOR_API_KEY` — habilita endpoints `/moderation/*`.
- `RESOLVER_API_KEY` — autoridade marca incidentes como resolvidos.

Gerar com `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Deploy Docker na VM (container isolado)

Mesmo padrao do **PLI-HazardTrack**: container proprio, porta local dedicada e URL
publica via Nginx do host (sem alterar o sigma-pli).

| Item | Valor |
|------|-------|
| Container | `pli_reporta_app` |
| Rede propria | `pli_reporta_net` |
| Porta host (loopback) | `127.0.0.1:8090` |
| URL publica | `http://pli-reporta.56-125-163-194.sslip.io` |
| Postgres | `sigma_pli_db:5432` via rede `sigma-backend-network` |
| Banco | `pli_reporta` / usuario `pli_user` |

### Build local (Windows)

```powershell
powershell -File scripts/build-docker.ps1          # gera pli-reporta-app-arm64.tar
powershell -File scripts/docker-test.ps1           # testa container isolado em :8081
```

### Deploy na VM

```bash
# Na sua maquina: copiar tarball + compose + nginx + .env.vm
scp pli-reporta-app-arm64.tar docker-compose.vm.yml \
    .deploy/nginx-host/pli-reporta .deploy/deploy_vm.sh .env.vm \
    ubuntu@56.125.163.194:/tmp/pli-reporta/

# Na VM
cd /tmp/pli-reporta && bash deploy_vm.sh
```

Rollback (nao mexe no sigma-pli):

```bash
docker compose -f /opt/pli-reporta/docker-compose.vm.yml down
sudo rm /etc/nginx/sites-enabled/pli-reporta
sudo systemctl reload nginx
```

## Sincronizacao laptop → GitHub → VM

GitHub e a fonte da verdade. A VM mantem um clone em `/opt/pli-reporta`
e atualiza **somente o que mudou** (git diff + cache Docker).

| Ambiente | Papel |
|----------|-------|
| Laptop | desenvolvimento + `git push` |
| GitHub | repositorio central (`main`) |
| VM | clone em `/opt/pli-reporta` + container Docker |

### Fluxo habitual (apos cada alteracao)

```powershell
# 1) commit + push + atualiza VM
powershell -File scripts/push-and-sync-vm.ps1 -CommitMessage "sua mensagem"

# ou, se ja commitou e fez push:
powershell -File scripts/sync-vm.ps1
```

Na VM, `update_vm.sh` automaticamente:

1. `git pull --ff-only` (preserva `.env.vm`)
2. Rebuild da imagem **so** se mudou `Dockerfile`, `backend/`, `frontend/`, etc.
3. Recria container somente quando a imagem mudou
4. Recarrega Nginx somente se mudou `.deploy/nginx-host/pli-reporta`
5. Pula rebuild se so mudaram docs/testes

### Conferir se os tres estao alinhados

```powershell
powershell -File scripts/verify-sync.ps1
```

Mostra o SHA do laptop, GitHub e VM. Os tres devem ser iguais.

### Primeira instalacao na VM (uma vez)

```bash
git clone https://github.com/vpcapanema/pli-Reporta.git /tmp/pli-reporta-setup
cd /tmp/pli-reporta-setup
cp .env.vm.example .env.vm   # preencher PLI_DB_PASSWORD e SECRET_KEY
bash .deploy/bootstrap_vm.sh
```

### Reverter versao na VM

```bash
cd /opt/pli-reporta
git log --oneline -5
git reset --hard <sha-anterior>
bash .deploy/update_vm.sh
```
