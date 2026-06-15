# Arquitetura de camadas (GeoJSON)

## Ideia central

O banco (`reports`) continua sendo a **fonte de verdade** transacional (PostgreSQL + PostGIS).  
As camadas em `data/camadas-do-sistema/` são uma **projeção materializada**: um espelho em GeoJSON, atualizado quando um reporte é **aceito** pelo sistema.

Cada reporte aceito gera **dois registros** (mesmo `id`, mesmos atributos):

| Pasta | Geometria | Uso |
|---|---|---|
| `pontos/` | `Point` (coordenada do reporte) | **Servido nos mapas** (público e gestão) |
| `poligonos/` | `Polygon` ou `MultiPolygon` (área de impacto) | Análise, exportação, roteador — **não** desenhado nos mapas atuais |

## Estrutura de arquivos

```
data/camadas-do-sistema/
├── README.md
├── pontos/
│   ├── evento_trafego__buraco.geojson
│   ├── evento_trafego__alagamento.geojson
│   ├── …
│   └── manifestacao__reclamacao.geojson
└── poligonos/
    ├── evento_trafego__buraco.geojson
    └── …
```

Um arquivo GeoJSON por **camada lógica** = par `(interaction_type, category_id)`.

## Ciclo de vida

```
Reporte submetido
    → pipeline (veracidade, relevância, política)
    → status aceito (publicado, validado internamente, etc.)
    → layer_store.upsert_report(report)
         ├─ pontos/{camada}.geojson   (Feature Point)
         └─ poligonos/{camada}.geojson (Feature Polygon)
```

Atualizações posteriores (moderador altera status, expiração, resolução, manutenção) **re-escrevem ou removem** a feature nos dois arquivos.

## Atributos das features

Todas as features (ponto **e** polígono) carregam o **mesmo pacote de 36 atributos**
com rótulos e valores amigáveis: campos do sistema + campos DER do snap.

Lista completa, tipos e formatação: **[CAMPOS_CAMADAS.md](CAMPOS_CAMADAS.md)**.

Campos principais para **controle de visibilidade nos mapas** (matriz completa: [MATRIZ_STATUS_VISIBILIDADE.md](MATRIZ_STATUS_VISIBILIDADE.md)):

| Atributo | Função |
|---|---|
| `status` | Estado do reporte (`publicado`, `resolvido`, `em_moderacao`, …) |
| `visivel_mapa_publico` | `true` → entra no feed do mapa público |
| `visivel_mapa_gestao` | `true` → entra no feed do mapa de gestão |
| `valid_to` | ISO; feature expirada some dos feeds mesmo com flags `true` |

### Regras de visibilidade (mapa público)

Servir features de `pontos/` onde:

- `visivel_mapa_publico == true`
- `valid_to` é nulo ou futuro

Valores típicos hoje: `status` em `publicado` ou `resolvido`.

### Regras de visibilidade (mapa gestão)

Servir features de `pontos/` onde:

- `visivel_mapa_gestao == true`
- `valid_to` é nulo ou futuro

Inclui reportes em análise, validados internamente, publicados e resolvidos — conforme política.

## O que os mapas consomem

| Mapa | Fonte | Filtro |
|---|---|---|
| Público (`/mapa`) | `GET /api/layers/pontos/{interaction_type}.geojson` | `visivel_mapa_publico` |
| Gestão (`/gestao`) | `GET /api/moderation/layers/pontos/{interaction_type}.geojson` | `visivel_mapa_gestao` |

Endpoints atuais (`/incidents.geojson`, `/moderation/reports.geojson`) serão **substituídos** por leitura desses arquivos (ou mantidos como alias temporário).

## Polígonos

Geometria derivada do ponto do reporte:

1. Buffer fixo de **10 m** em torno de `geom_point` (padrão do sistema)
2. `geometry_geojson` do reporte, se enviado como polígono/multipolígono (exceção futura)

Mesmos atributos do ponto; ver [CAMPOS_CAMADAS.md](CAMPOS_CAMADAS.md).

## Próximos passos de implementação

1. `layer_store.py` — ler/escrever GeoJSON com lock de arquivo
2. Hook em `ingest_report` e `decide` (moderação) + manutenção (expirar/resolver)
3. Novos endpoints de feed a partir de `pontos/`
4. Frontends (`viewer.js`, `gestao-dashboard.js`) apontando para os novos feeds
5. Script de **backfill** a partir do banco para popular camadas existentes
