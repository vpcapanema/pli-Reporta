# Campos das camadas (PostGIS + GeoJSON)

Documento de referência para o pacote de atributos de **cada feature** nas camadas
de pontos e polígonos. O mesmo `id` e o **mesmo conjunto de campos** aparecem em:

- `reports.geom_point` / `reports.geom_polygon` (PostgreSQL + PostGIS)
- `data/camadas-do-sistema/pontos/*.geojson` (geometria `Point`)
- `data/camadas-do-sistema/poligonos/*.geojson` (geometria `Polygon`, buffer 10 m)

Implementação: `backend/services/layer_schema.py` e `backend/services/road_context.py`.

---

## Fluxo de persistência

```
(lat, lon) → validações + snap DER
  → PostGIS: geom_point + atributos completos
  → resposta ao usuário
  → GeoJSON pontos/
  → buffer 10 m → PostGIS: geom_polygon + mesmos atributos
  → GeoJSON poligonos/
```

---

## Campos do sistema

| Rótulo amigável (exportado) | Chave interna | Tipo / origem | Valor amigável |
|---|---|---|---|
| ID | `id` | ULID | Identificador estável do reporte |
| Tipo de interação | `interaction_type` | enum | `evento_trafego` / `manifestacao` → rótulo no feed |
| Categoria (código) | `category` | enum | ex.: `buraco`, `elogio` |
| Categoria | `category_label` | catálogo | ex.: Buraco, Elogio |
| Sigla da categoria | `category_sigla` | catálogo | ex.: BU, EL |
| Magnitude | `magnitude` | enum | leve / normal / grave |
| Descrição | `description` | texto | até 500 caracteres |
| Status | `status` | enum | submetido, em_moderacao, publicado, … |
| Visível no mapa público | `visivel_mapa_publico` | bool | matriz de status + `valid_to` |
| Visível no mapa gestão | `visivel_mapa_gestao` | bool | matriz de status + `valid_to` |
| Exportação pública | `export_publico` | bool | matriz de status |
| Exportação gestão | `export_gestao` | bool | matriz de status |
| Bloqueante | `blocking` | bool | categoria + prioridade |
| Cluster | `cluster_id` | ULID | agrupamento espacial |
| Veracidade (V) | `veracity` | float 0–1 | 3 casas decimais |
| Relevância (R) | `relevance` | float 0–1 | 3 casas decimais |
| Prioridade (P) | `priority` | float | V × R |
| Válido desde | `valid_from` | ISO 8601 | início da vigência |
| Válido até | `valid_to` | ISO 8601 | expiração calculada |
| Capturado em | `captured_at` | ISO 8601 | relógio do dispositivo |
| Recebido em | `received_at` | ISO 8601 | servidor |
| URL da foto | `photo_url` | URL | endpoint público da mídia |
| Acurácia GPS (m) | `accuracy_m` | float | precisão declarada |
| Nonce de captura válido | `capture_nonce_valid` | 0/1 | anti-fraude in-app |
| Trechos afetados | `affected_edges` | lista | osm:way após snap |

---

## Campos da malha DER (snap)

Obtidos no snap com a malha viária estadual. **Não incluem** `jurisdicao` nem
`perimetro_urbano` (usados só na classificação interna federal/estadual).

| Rótulo amigável (exportado) | Chave interna (snap) | Valor amigável |
|---|---|---|
| Classificação viária | `scope_label` | Rodovia federal / Rodovia estadual / Via municipal |
| Rodovia | `rodovia` + `denominacao` | Linha combinada, ex.: `SP 330 — Anhanguera` |
| Tipo rodoviário | `tipo_rodoviario` | Title case |
| Município | `municipio` | Title case |
| Tipo de pista | `tipo_pista` | DUP → Duplicada, ASF → Asfaltada, … |
| Administrador da via | `administra` | DER → DER-SP, DNIT → DNIT, … |
| Coordenadoria Regional Geral DER | `cod_regional` | código regional |
| Sede da coordenadoria | `sede_regional` | Title case |
| Residência de conserva DER | `residencia` | código/texto original |
| Sede da residência de conserva | `sede_residencia` | Title case |
| Distância snap utilizada | `snap_dist_m` | metros com vírgula, ex.: `12,4 m` |

Formatação de valores: `backend/services/road_context.py` → `format_road_context_value()`.

---

## Ordem completa dos campos exportados

1. Os 25 campos do **sistema** (tabela acima)
2. Os 11 campos **DER** (tabela acima)

Total: **36 atributos** por feature (`FULL_LAYER_FIELD_LABELS` em `layer_schema.py`).

Manifestações sem snap DER recebem os campos DER vazios ou apenas município /
classificação viária municipal, conforme o contexto.

---

## Geometrias

| Destino | Coluna / pasta | Geometria | Derivação |
|---|---|---|---|
| PostGIS ponto | `geom_point` | `POINT` SRID 4326 | `(lon, lat)` do reporte |
| PostGIS polígono | `geom_polygon` | `POLYGON` SRID 4326 | Buffer **10 m** no ponto |
| GeoJSON pontos | `pontos/` | `Point` | Mesmas coordenadas |
| GeoJSON polígonos | `poligonos/` | `Polygon` | Mesmo buffer 10 m |

---

## Campos excluídos (não exportados)

| Campo shapefile | Motivo |
|---|---|
| `jurisdicao` | Classificação interna federal/estadual no snap |
| `perimetro_urbano` | Apoio à regra de via urbana IBGE |
| `scope` (código) | Substituído por `scope_label` amigável |

---

## Referências

- Matriz de visibilidade: [MATRIZ_STATUS_VISIBILIDADE.md](MATRIZ_STATUS_VISIBILIDADE.md)
- Arquitetura das camadas: [ARQUITETURA_CAMADAS.md](ARQUITETURA_CAMADAS.md)
- Modelo relacional: [DATA_MODEL.md](DATA_MODEL.md)
