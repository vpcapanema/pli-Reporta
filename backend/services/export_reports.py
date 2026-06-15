"""Exportação analítica de camadas públicas (CSV, PDF, shapefile)."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

import shapefile
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from ..models import Report
from .layer_feed import active_public_reports_stmt
from .pipeline import report_to_feature
from .report_catalog import EVENT_CATEGORIES, MANIF_CATEGORIES, STATUS_META
from .road_context import ROAD_CONTEXT_POPUP_FIELDS, road_context_popup_rows

WGS84_PRJ = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'

INTERACTION_LABELS = {
    "evento_trafego": "Evento de tráfego",
    "manifestacao": "Manifestação cidadã",
}

# Cabeçalhos CSV (ordem fixa)
_BASE_COLUMNS: list[tuple[str, str]] = [
    ("id", "ID"),
    ("interaction_type", "Tipo de interação"),
    ("category", "Categoria"),
    ("status", "Status"),
    ("magnitude", "Magnitude"),
    ("description", "Descrição"),
    ("lat", "Latitude"),
    ("lon", "Longitude"),
    ("veracity", "Veracidade (V)"),
    ("relevance", "Relevância (R)"),
    ("priority", "Prioridade (P)"),
    ("road_scope", "Escopo viário"),
    ("road_label", "Referência rodoviária"),
    ("cluster_id", "Cluster"),
    ("valid_from", "Válido desde"),
    ("valid_to", "Válido até"),
    ("captured_at", "Capturado em"),
    ("received_at", "Recebido em"),
    ("photo_url", "URL da foto"),
]

_ROAD_COLUMN_LABELS = [label for key, label in ROAD_CONTEXT_POPUP_FIELDS if not key.startswith("_")]


def _categories_for(interaction_type: str) -> list[dict[str, str]]:
    if interaction_type == "evento_trafego":
        return EVENT_CATEGORIES
    if interaction_type == "manifestacao":
        return MANIF_CATEGORIES
    return []


def validate_layer(interaction_type: str, category_id: str) -> dict[str, str]:
    cats = {c["id"]: c for c in _categories_for(interaction_type)}
    hit = cats.get(category_id)
    if not hit:
        raise ValueError(f"Categoria inválida: {category_id}")
    return hit


def layer_features(db: Session, interaction_type: str, category_id: str) -> list[dict[str, Any]]:
    validate_layer(interaction_type, category_id)
    stmt = active_public_reports_stmt(interaction_type=interaction_type)
    stmt = stmt.where(Report.category == category_id)
    rows = db.execute(stmt).scalars().all()
    return [report_to_feature(r) for r in rows]


def layer_label_for(interaction_type: str, category_id: str) -> str:
    cat = validate_layer(interaction_type, category_id)
    group = "eventos" if interaction_type == "evento_trafego" else "manifestações"
    return f"{cat['label']} ({group})"


def parse_layer_refs(
    layers: list[dict[str, str]],
) -> list[tuple[str, str, dict[str, str]]]:
    """Valida e deduplica seleção de camadas."""
    if not layers:
        raise ValueError("Selecione ao menos uma camada.")
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, dict[str, str]]] = []
    for item in layers:
        itype = (item.get("interaction_type") or "").strip().lower()
        cat_id = (item.get("category_id") or "").strip().lower()
        if itype not in ("evento_trafego", "manifestacao"):
            raise ValueError(f"Tipo de interação inválido: {itype}")
        key = (itype, cat_id)
        if key in seen:
            continue
        seen.add(key)
        out.append((itype, cat_id, validate_layer(itype, cat_id)))
    if not out:
        raise ValueError("Selecione ao menos uma camada.")
    return out


def batch_layer_data(
    db: Session,
    layer_refs: list[tuple[str, str, dict[str, str]]],
) -> list[dict[str, Any]]:
    """Pacotes por camada: metadados + features."""
    packs: list[dict[str, Any]] = []
    for itype, cat_id, cat in layer_refs:
        features = layer_features(db, itype, cat_id)
        packs.append({
            "interaction_type": itype,
            "category_id": cat_id,
            "category_label": cat["label"],
            "layer_label": layer_label_for(itype, cat_id),
            "features": features,
        })
    return packs


def _category_label(category_id: str, interaction_type: str) -> str:
    for c in _categories_for(interaction_type):
        if c["id"] == category_id:
            return c["label"]
    return category_id


def _status_label(status: str | None) -> str:
    if not status:
        return ""
    return STATUS_META.get(status, {}).get("label") or status


def flatten_feature(
    feature: dict[str, Any],
    *,
    interaction_type: str,
) -> dict[str, str]:
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or [None, None]
    lon, lat = (coords[0], coords[1]) if len(coords) >= 2 else (None, None)

    row: dict[str, str] = {
        "ID": str(props.get("id") or ""),
        "Tipo de interação": INTERACTION_LABELS.get(props.get("interaction_type") or interaction_type, ""),
        "Categoria": _category_label(str(props.get("category") or ""), interaction_type),
        "Status": _status_label(props.get("status")),
        "Magnitude": str(props.get("magnitude") or ""),
        "Descrição": str(props.get("description") or ""),
        "Latitude": f"{lat:.6f}" if lat is not None else "",
        "Longitude": f"{lon:.6f}" if lon is not None else "",
        "Veracidade (V)": str(props.get("veracity") if props.get("veracity") is not None else ""),
        "Relevância (R)": str(props.get("relevance") if props.get("relevance") is not None else ""),
        "Prioridade (P)": str(props.get("priority") if props.get("priority") is not None else ""),
        "Escopo viário": str(props.get("road_scope") or ""),
        "Referência rodoviária": str(props.get("road_label") or ""),
        "Cluster": str(props.get("cluster_id") or ""),
        "Válido desde": str(props.get("valid_from") or ""),
        "Válido até": str(props.get("valid_to") or ""),
        "Capturado em": str(props.get("captured_at") or ""),
        "Recebido em": str(props.get("received_at") or ""),
        "URL da foto": str(props.get("photo_url") or ""),
    }

    ctx = props.get("road_context")
    if isinstance(ctx, str):
        try:
            ctx = json.loads(ctx)
        except (ValueError, TypeError):
            ctx = None
    if isinstance(ctx, dict):
        for label, value in road_context_popup_rows(ctx):
            row[label] = value
    return row


def csv_headers(_interaction_type: str) -> list[str]:
    base = [label for _, label in _BASE_COLUMNS]
    return base + _ROAD_COLUMN_LABELS


def features_to_csv(features: list[dict[str, Any]], *, interaction_type: str) -> bytes:
    headers = csv_headers(interaction_type)
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for feat in features:
        writer.writerow(flatten_feature(feat, interaction_type=interaction_type))
    return buf.getvalue().encode("utf-8")


def batch_to_csv(packs: list[dict[str, Any]]) -> bytes:
    """CSV único com coluna Camada quando há várias seleções."""
    headers = ["Camada"] + csv_headers("evento_trafego")
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for pack in packs:
        itype = pack["interaction_type"]
        label = pack["layer_label"]
        for feat in pack["features"]:
            row = flatten_feature(feat, interaction_type=itype)
            row["Camada"] = label
            writer.writerow(row)
    return buf.getvalue().encode("utf-8")


def _shp_field_defs(headers: list[str]) -> list[tuple[str, str, int, int]]:
    """DBF limita nomes a 10 caracteres — usa índice numérico mapeado no CSV."""
    defs: list[tuple[str, str, int, int]] = []
    for i, h in enumerate(headers):
        name = f"F{i:02d}"
        size = min(254, max(32, len(h) + 16))
        defs.append((name, "C", size, 0))
    return defs


def features_to_shapefile_zip(
    features: list[dict[str, Any]],
    *,
    interaction_type: str,
    layer_label: str,
) -> bytes:
    headers = csv_headers(interaction_type)
    field_defs = _shp_field_defs(headers)

    shp_io = io.BytesIO()
    shx_io = io.BytesIO()
    dbf_io = io.BytesIO()

    with shapefile.Writer(shp=shp_io, shx=shx_io, dbf=dbf_io) as w:
        w.shapeType = shapefile.POINT
        for fd in field_defs:
            w.field(*fd)
        for feat in features:
            row = flatten_feature(feat, interaction_type=interaction_type)
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or [0, 0]
            w.point(float(coords[0]), float(coords[1]))
            w.record(*[row.get(h, "")[:254] for h in headers])

    base = layer_label.replace(" ", "_").lower()[:32] or "camada"
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base}.shp", shp_io.getvalue())
        zf.writestr(f"{base}.shx", shx_io.getvalue())
        zf.writestr(f"{base}.dbf", dbf_io.getvalue())
        zf.writestr(f"{base}.prj", WGS84_PRJ)
        zf.writestr(
            f"{base}_campos.csv",
            "campo_shp,rotulo\n" + "\n".join(f"F{i:02d},{h}" for i, h in enumerate(headers)),
        )
    return zip_buf.getvalue()


def batch_to_shapefile_zip(packs: list[dict[str, Any]]) -> bytes:
    """ZIP com um shapefile por camada selecionada."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pack in packs:
            itype = pack["interaction_type"]
            cat_id = pack["category_id"]
            layer_label = pack["layer_label"]
            blob = features_to_shapefile_zip(
                pack["features"],
                interaction_type=itype,
                layer_label=layer_label,
            )
            inner = zipfile.ZipFile(io.BytesIO(blob))
            folder = f"{itype}__{cat_id}"
            for name in inner.namelist():
                zf.writestr(f"{folder}/{name}", inner.read(name))
    return zip_buf.getvalue()


def _pdf_escape(text: str) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def features_to_pdf(
    features: list[dict[str, Any]],
    *,
    interaction_type: str,
    layer_label: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"PLI Reporta — {layer_label}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=14,
        textColor=colors.HexColor("#003b5a"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#003b5a"),
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )

    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    story: list[Any] = [
        Paragraph("PLI Reporta — Parecer técnico analítico", title_style),
        Paragraph(
            f"<b>Camada:</b> {_pdf_escape(layer_label)} · <b>Registros:</b> {len(features)} · <b>Gerado em:</b> {generated}",
            body_style,
        ),
        Spacer(1, 0.4 * cm),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2fa854")),
        Spacer(1, 0.3 * cm),
    ]

    if not features:
        story.append(Paragraph("Nenhum registro publicado nesta camada.", body_style))
    else:
        for i, feat in enumerate(features, start=1):
            row = flatten_feature(feat, interaction_type=interaction_type)
            story.append(Paragraph(f"Registro {i} — {row.get('ID', '')}", section_style))
            for key, val in row.items():
                if not val:
                    continue
                story.append(
                    Paragraph(
                        f"<b>{_pdf_escape(key)}:</b> {_pdf_escape(val)}",
                        body_style,
                    )
                )
            if i < len(features):
                story.append(Spacer(1, 0.25 * cm))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
                story.append(Spacer(1, 0.25 * cm))

    doc.build(story)
    return buf.getvalue()


def batch_to_pdf(packs: list[dict[str, Any]]) -> bytes:
    """PDF com seção por camada selecionada."""
    buf = io.BytesIO()
    total = sum(len(p["features"]) for p in packs)
    titles = ", ".join(p["category_label"] for p in packs[:4])
    if len(packs) > 4:
        titles += f" (+{len(packs) - 4})"
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="PLI Reporta — Exportação",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=14,
        textColor=colors.HexColor("#003b5a"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#003b5a"),
        spaceBefore=10,
        spaceAfter=4,
    )
    layer_style = ParagraphStyle(
        "Layer",
        parent=styles["Heading3"],
        fontSize=10,
        textColor=colors.HexColor("#116593"),
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )

    generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    story: list[Any] = [
        Paragraph("PLI Reporta — Parecer técnico analítico", title_style),
        Paragraph(
            f"<b>Camadas:</b> {_pdf_escape(titles)} · <b>Total de registros:</b> {total} · "
            f"<b>Gerado em:</b> {generated}",
            body_style,
        ),
        Spacer(1, 0.4 * cm),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2fa854")),
        Spacer(1, 0.3 * cm),
    ]

    if total == 0:
        story.append(Paragraph("Nenhum registro publicado nas camadas selecionadas.", body_style))
    else:
        for pack in packs:
            features = pack["features"]
            story.append(
                Paragraph(
                    f"{_pdf_escape(pack['layer_label'])} — {len(features)} registro(s)",
                    layer_style,
                )
            )
            if not features:
                story.append(Paragraph("Nenhum registro publicado nesta camada.", body_style))
                continue
            for i, feat in enumerate(features, start=1):
                row = flatten_feature(feat, interaction_type=pack["interaction_type"])
                story.append(Paragraph(f"Registro {i} — {row.get('ID', '')}", section_style))
                for key, val in row.items():
                    if not val:
                        continue
                    story.append(
                        Paragraph(
                            f"<b>{_pdf_escape(key)}:</b> {_pdf_escape(val)}",
                            body_style,
                        )
                    )
                if i < len(features):
                    story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
    return buf.getvalue()
