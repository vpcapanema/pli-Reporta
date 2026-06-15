"""Catálogo de categorias, status e legenda para a UI de gestão."""
from __future__ import annotations

EVENT_CATEGORIES = [
    {"id": "buraco", "sigla": "BU", "label": "Buraco"},
    {"id": "alagamento", "sigla": "AL", "label": "Alagamento"},
    {"id": "acidente", "sigla": "AC", "label": "Acidente"},
    {"id": "incendio", "sigla": "IN", "label": "Incêndio"},
    {"id": "animal_na_pista", "sigla": "AN", "label": "Animal na pista"},
    {"id": "objeto_na_pista", "sigla": "OP", "label": "Objeto na pista"},
    {"id": "queda_arvore", "sigla": "AR", "label": "Queda de árvore"},
    {"id": "veiculo_quebrado", "sigla": "VQ", "label": "Veículo quebrado"},
    {"id": "bloqueio_total", "sigla": "BL", "label": "Bloqueio total"},
    {"id": "obra_grande", "sigla": "OB", "label": "Obra"},
    {"id": "lentidao_corredor", "sigla": "LE", "label": "Lentidão"},
    {"id": "sinalizacao_quebrada", "sigla": "SI", "label": "Sinalização"},
    {"id": "outro", "sigla": "OU", "label": "Outro"},
]

MANIF_CATEGORIES = [
    {"id": "elogio", "sigla": "EL", "label": "Elogio"},
    {"id": "sugestao", "sigla": "SG", "label": "Sugestão"},
    {"id": "reclamacao", "sigla": "RC", "label": "Reclamação"},
]

INTERACTION_TYPES = [
    {
        "id": "evento_trafego",
        "label": "Evento de tráfego",
        "shape": "diamond",
        "descricao": "Marcador em forma de losango",
    },
    {
        "id": "manifestacao",
        "label": "Manifestação cidadã",
        "shape": "circle",
        "descricao": "Marcador circular",
    },
]

STATUS_META = {
    "submetido": {
        "label": "Recém-chegado",
        "cor": "#94a3b8",
        "descricao": "Ainda em processamento inicial",
    },
    "em_moderacao": {
        "label": "Precisa da sua análise",
        "cor": "#f59e0b",
        "descricao": "O sistema preferiu não decidir sozinho",
    },
    "validado": {
        "label": "Aprovado internamente",
        "cor": "#3b82f6",
        "descricao": "Validado, aguardando publicação no mapa público",
    },
    "publicado": {
        "label": "Publicado",
        "cor": "#22c55e",
        "descricao": "Visível no mapa público",
    },
    "descartado": {
        "label": "Arquivado",
        "cor": "#ef4444",
        "descricao": "Não será exibido publicamente",
    },
    "expirado": {
        "label": "Expirado",
        "cor": "#64748b",
        "descricao": "Perdeu validade temporal",
    },
    "resolvido": {
        "label": "Resolvido",
        "cor": "#a855f7",
        "descricao": "Encerrado pela autoridade",
    },
}

GLOSSARY = [
    {
        "titulo": "Forma do marcador",
        "itens": [
            "Losango = evento de tráfego",
            "Círculo = manifestação cidadã",
        ],
    },
    {
        "titulo": "Sigla no marcador",
        "itens": [f"{c['sigla']} = {c['label']}" for c in EVENT_CATEGORIES + MANIF_CATEGORIES],
    },
    {
        "titulo": "Cor da borda",
        "itens": [f"{m['label']} → cor {m['cor']}" for m in STATUS_META.values()],
    },
]


def catalog_payload() -> dict:
    return {
        "interaction_types": INTERACTION_TYPES,
        "event_categories": EVENT_CATEGORIES,
        "manifestation_categories": MANIF_CATEGORIES,
        "statuses": STATUS_META,
        "glossary": GLOSSARY,
    }
