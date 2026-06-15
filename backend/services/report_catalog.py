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
        "cor": "#475569",
        "descricao": "Ainda em processamento inicial",
        "visivel_mapa_publico": False,
        "visivel_mapa_gestao": True,
        "export_publico": False,
        "export_gestao": True,
    },
    "em_moderacao": {
        "label": "Precisa da sua análise",
        "cor": "#c2410c",
        "descricao": "O sistema preferiu não decidir sozinho",
        "visivel_mapa_publico": False,
        "visivel_mapa_gestao": True,
        "export_publico": False,
        "export_gestao": True,
    },
    "validado": {
        "label": "Aprovado internamente",
        "cor": "#1d4ed8",
        "descricao": "Validado, aguardando publicação no mapa público",
        "visivel_mapa_publico": False,
        "visivel_mapa_gestao": True,
        "export_publico": False,
        "export_gestao": True,
    },
    "publicado": {
        "label": "Publicado",
        "cor": "#15803d",
        "descricao": "Visível no mapa público",
        "visivel_mapa_publico": True,
        "visivel_mapa_gestao": True,
        "export_publico": True,
        "export_gestao": True,
    },
    "descartado": {
        "label": "Arquivado",
        "cor": "#b91c1c",
        "descricao": "Não será exibido publicamente",
        "visivel_mapa_publico": False,
        "visivel_mapa_gestao": False,
        "export_publico": False,
        "export_gestao": False,
    },
    "registro_municipal": {
        "label": "Registro municipal",
        "cor": "#0369a1",
        "descricao": "Armazenado internamente para relatórios e exportação às prefeituras",
        "visivel_mapa_publico": False,
        "visivel_mapa_gestao": True,
        "export_publico": False,
        "export_gestao": True,
        "camada_gestao": "municipal",
    },
    "expirado": {
        "label": "Expirado",
        "cor": "#334155",
        "descricao": "Perdeu validade temporal",
        "visivel_mapa_publico": False,
        "visivel_mapa_gestao": False,
        "export_publico": False,
        "export_gestao": False,
    },
    "resolvido": {
        "label": "Resolvido",
        "cor": "#7e22ce",
        "descricao": "Encerrado pela autoridade",
        "visivel_mapa_publico": True,
        "visivel_mapa_gestao": True,
        "export_publico": True,
        "export_gestao": True,
    },
}

VISIBILITY_KEYS = (
    "visivel_mapa_publico",
    "visivel_mapa_gestao",
    "export_publico",
    "export_gestao",
)

GLOSSARY = [
    {
        "titulo": "Forma do marcador",
        "itens": [
            "Losango = evento de tráfego",
            "Círculo = manifestação cidadã",
        ],
    },
    {
        "titulo": "Ícone no marcador (eventos de tráfego)",
        "itens": [
            f"{c['label']} → ícone {c['id']}" for c in EVENT_CATEGORIES
        ],
    },
    {
        "titulo": "Sigla no marcador (manifestações)",
        "itens": [f"{c['sigla']} = {c['label']}" for c in MANIF_CATEGORIES],
    },
    {
        "titulo": "Cor do símbolo interno",
        "itens": [f"{m['label']} → cor {m['cor']}" for m in STATUS_META.values()],
    },
]


def catalog_payload() -> dict:
    from .traffic_symbology import traffic_event_symbology_payload

    symbology = traffic_event_symbology_payload()
    return {
        "interaction_types": INTERACTION_TYPES,
        "event_categories": symbology["categories"],
        "manifestation_categories": MANIF_CATEGORIES,
        "statuses": STATUS_META,
        "status_visibility_matrix": status_visibility_matrix(),
        "glossary": GLOSSARY,
        "traffic_symbology": symbology,
    }


def status_visibility_matrix() -> list[dict]:
    """Matriz status → mapas/exportações (ver docs/MATRIZ_STATUS_VISIBILIDADE.md)."""
    rows = []
    for status_id, meta in STATUS_META.items():
        rows.append({
            "status": status_id,
            "label": meta["label"],
            "visivel_mapa_publico": meta.get("visivel_mapa_publico", False),
            "visivel_mapa_gestao": meta.get("visivel_mapa_gestao", False),
            "export_publico": meta.get("export_publico", False),
            "export_gestao": meta.get("export_gestao", False),
            "camada_gestao": meta.get("camada_gestao", "principal"),
        })
    return rows


def visibility_for_status(status: str) -> dict[str, bool]:
    """Flags de visibilidade para um status (sem aplicar valid_to)."""
    meta = STATUS_META.get(status, {})
    return {
        "visivel_mapa_publico": bool(meta.get("visivel_mapa_publico")),
        "visivel_mapa_gestao": bool(meta.get("visivel_mapa_gestao")),
        "export_publico": bool(meta.get("export_publico")),
        "export_gestao": bool(meta.get("export_gestao")),
    }
