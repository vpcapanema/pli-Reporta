# API

Base: `/api/v1`

## Públicos (sem auth)

### `POST /reports`
Cria um reporte. `multipart/form-data`.

Campos:

| nome | tipo | obrigatório | descrição |
|---|---|---|---|
| `photo` | file (jpeg/png/webp) | sim | foto do incidente |
| `lat` | float | sim | latitude do navegador |
| `lon` | float | sim | longitude do navegador |
| `accuracy_m` | float | não | acurácia GPS em metros |
| `category` | enum | sim | ver METODOLOGIA §4.1 |
| `magnitude` | enum `leve|normal|grave` | não | default `normal` |
| `description` | string | não | até 500 chars |
| `captured_at` | ISO 8601 | sim | momento da captura no cliente |
| `capture_nonce` | string | não | token de captura in-app |
| `client_id` | uuid | não | id anônimo persistente do dispositivo |
| `geometry` | json `{type, coordinates}` | não | linha/polígono opcional |

Resposta `201`:

```json
{
  "id": "01HX...",
  "status": "validado|em_moderacao|descartado",
  "veracity_score": 0.83,
  "relevance_score": 0.71,
  "priority": 0.59,
  "explanation": ["geo do navegador 1.0", "snap à via 1.0", "..."]
}
```

### `GET /capture-nonce`
Devolve um nonce assinado para a próxima captura in-app. TTL configurável.

### `GET /incidents.geojson?bbox=&since=&category=`
Feed primário consumido pelo roteador. Cada feature carrega:

```json
{
  "type": "Feature",
  "geometry": {"type": "Point", "coordinates": [lon, lat]},
  "properties": {
    "id": "01HX...",
    "category": "alagamento",
    "severity": "grave",
    "veracity": 0.83,
    "relevance": 0.91,
    "priority": 0.75,
    "affected_edges": ["osm:way:12345"],
    "blocking": false,
    "valid_from": "2026-05-27T12:00:00Z",
    "valid_to": "2026-05-28T00:00:00Z",
    "confirmations": 3
  }
}
```

Cache-Control: `max-age = min(valid_to - now, 60)`.

### `GET /reports/{id}`
Estado público do reporte (sem dados pessoais).

## Operacionais (com chave)

Header: `X-API-Key: <chave>`.

- `GET /moderation/queue` — lista a faixa cinza pendente.
- `POST /moderation/{id}/decide` — `{decision: "publicar|descartar", note}`.
- `POST /reports/{id}/resolve` — autoridade marca como resolvido.
