# PLI Reporta

PWA colaborativa de reportes viários georreferenciados, mobile-first, com pipeline de
veracidade e relevância para alimentar serviços de roteamento e alertas como camada
operacional de **incidentes verificados**.

Aplicação independente. Pode ser publicada em qualquer host com Python 3.10+ e um disco
para mídia. Para integração com o roteador OSRM/PLI, expõe um endpoint GeoJSON estável.

## Documentação

- [Metodologia conceitual e hierarquização de rotas](./METODOLOGIA.md) — leia primeiro.
- [API de integração com o roteador](./docs/API.md)
- [Modelo de dados](./docs/DATA_MODEL.md)
- [Operação e moderação](./docs/OPERACAO.md)

## Quickstart (dev)

```bash
python -m venv venv
venv\Scripts\activate           # Windows
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn backend.main:app --reload --port 8080
```

Abra:

- `http://localhost:8080/`            — PWA de reporte (mobile-first)
- `http://localhost:8080/mapa`        — visualizador público
- `http://localhost:8080/acesso`        — acesso restrito (login gestor / moderação)
- `http://localhost:8080/docs`        — OpenAPI / Swagger
- `http://localhost:8080/api/v1/incidents.geojson` — feed para o roteador

## Estrutura

```
pli_reporta/
├── METODOLOGIA.md          documento conceitual (veracidade, relevância, hierarquização)
├── backend/                FastAPI + SQLite + Pillow
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── routes/             endpoints HTTP
│   ├── services/           lógica de domínio (scores, exif, snap, dedup)
│   └── storage/photos/     mídia gerada
├── frontend/               PWA vanilla + MapLibre GL
│   ├── index.html          tela de captura
│   ├── viewer.html         mapa público
│   ├── acesso.html         login e painel de moderação
│   ├── manifest.webmanifest
│   ├── sw.js               service worker (offline + background sync)
│   └── js/                 módulos
├── data/                   dados auxiliares (roads.geojson opcional para snap)
├── tests/
├── requirements.txt
├── render.yaml
└── .env.example
```

## Identidade visual

Paleta institucional PLI usada nos templates:

| Token CSS | Hex | Uso |
|---|---|---|
| `--pli-verde` | `#3ec26e` | verde PLI, ações primárias |
| `--pli-verde-dark` | `#2fa854` | hover/foco em ações primárias |
| `--pli-verde-soft` | `#E5F6EC` | seleções e badges |
| `--pli-primary` | `#003b5a` | azul profundo, topbar, fundo escuro |
| `--pli-secondary` | `#1c3d59` | azul-marinho PLI, textos fortes |
| `--pli-accent` | `#116593` | azul médio PLI, links e secundários |
| `--bg` | `#F5F7FA` | fundo |
| `--surface` | `#FFFFFF` | cartões |
| `--border` | `#D7DEE6` | linhas |

Sem emojis em qualquer artefato visual; categorias usam marcadores tipográficos
(BU, AL, AC, BL, OB, LE, SI, OU). Para ajustes finos basta sobrescrever os tokens em
`frontend/styles.css`.

## Acesso restrito

A rota `/acesso` (link **Acesso Restrito** no menu) concentra login de gestores e moderação.
A rota legada `/moderar` redireciona para `/acesso`.

Autenticação via SIGMA-PLI (`SIGMA_API_BASE_URL`) ou credenciais locais de dev (`MODERATOR_USERNAME` / `MODERATOR_PASSWORD`).

| Tema | Escolha | Por quê |
|---|---|---|
| Anônimo | Permitido, com reputação 0 | Reduz atrito; evidência mostra que login obriga afasta contribuintes |
| Captura | `getUserMedia` + fallback `<input capture>` | Foto na página, não da galeria, é o sinal mais forte de autenticidade |
| Geometria | Ponto sempre; linha/polígono para usuários verificados | Reduz erro de iniciante e abuso |
| Veracidade | Score 0..1 com gates (descarta / modera / publica) | Auditável, ajustável, explica decisão ao usuário |
| Relevância | Categoria × confirmações × persistência × afetação viária | Separa "o que é real" de "o que importa para a rota" |
| Persistência | SQLite no MVP, com camada SQLAlchemy pronta para PostGIS | Simples no início, sem retrabalho depois |

Detalhes formais e fórmulas em [METODOLOGIA.md](./METODOLOGIA.md).

## Licença

A definir pelo PLI-SP. O código é entregue sem cláusula restritiva por padrão.
