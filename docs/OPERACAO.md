# Operação

## Moderação humana

Faixa cinza (`0.30 ≤ V < 0.70`) entra na fila `/moderar`. Moderador vê:

- Foto, mapa, EXIF parseado, sinais de veracidade.
- Reportes vizinhos em raio de 200 m / 24 h.
- Botões: `Publicar`, `Descartar (motivo)`, `Pedir mais info` (não usado no MVP).

Cada decisão grava em `audit_log`.

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
