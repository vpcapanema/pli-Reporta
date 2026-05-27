# Modelo de dados

SQLite no MVP, projetado para migrar para PostgreSQL/PostGIS sem retrabalho.

## `reports`

| coluna | tipo | obs |
|---|---|---|
| id | TEXT (ULID) PK | identificador estável |
| client_id | TEXT | id anônimo do dispositivo |
| category | TEXT | enum |
| magnitude | TEXT | leve/normal/grave |
| description | TEXT | até 500 chars |
| lat | REAL | GPS do navegador |
| lon | REAL | GPS do navegador |
| accuracy_m | REAL | acurácia declarada |
| geometry_geojson | TEXT | linha/polígono opcional, GeoJSON |
| photo_path | TEXT | caminho relativo do arquivo |
| photo_hash | TEXT | sha256 — usado para detectar uploads repetidos |
| exif_json | TEXT | EXIF parseado (sem dados pessoais) |
| captured_at | TEXT (ISO) | enviado pelo cliente |
| received_at | TEXT (ISO) | server-side |
| capture_nonce_valid | INTEGER 0/1 | flag de captura in-app |
| veracity_score | REAL | V |
| veracity_signals_json | TEXT | breakdown auditável |
| relevance_score | REAL | R |
| priority | REAL | V·R |
| status | TEXT | submetido/em_moderacao/validado/publicado/descartado/expirado/resolvido |
| cluster_id | TEXT | FK para `clusters.id` |
| valid_from | TEXT (ISO) | |
| valid_to | TEXT (ISO) | calculado por categoria |
| affected_edges_json | TEXT | lista de osm_way_id após snap |

Índices: `(status, valid_to)`, `(lat, lon)`, `(category, captured_at)`, `(cluster_id)`.

## `clusters`

Agrupa reportes que descrevem o mesmo incidente.

| coluna | tipo |
|---|---|
| id | TEXT (ULID) PK |
| category | TEXT |
| centroid_lat | REAL |
| centroid_lon | REAL |
| first_seen | TEXT (ISO) |
| last_seen | TEXT (ISO) |
| confirmations | INTEGER |
| status | TEXT |

## `users` (opcional, ativado quando login social entrar)

| coluna | tipo |
|---|---|
| id | TEXT PK |
| display_name | TEXT |
| email_hash | TEXT |
| reputation | REAL |
| created_at | TEXT |

## `audit_log`

| coluna | tipo |
|---|---|
| id | INTEGER PK |
| ts | TEXT (ISO) |
| actor | TEXT (sistema/moderador/api-key id) |
| action | TEXT |
| target_type | TEXT |
| target_id | TEXT |
| payload_json | TEXT |

## Migração para PostGIS

- Trocar `lat/lon` por coluna `geometry GEOGRAPHY(Point, 4326)`.
- `geometry_geojson` vira `geometry GEOMETRY` com checagem.
- Índices GiST em `geometry` e `(category, valid_to)` BRIN.
- DBSCAN passa a usar `ST_ClusterDBSCAN`.
