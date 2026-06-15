"""Exportação pública de camadas por categoria."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_session
from ..services.export_reports import (
    batch_layer_data,
    batch_to_csv,
    batch_to_pdf,
    batch_to_shapefile_zip,
    features_to_csv,
    features_to_pdf,
    features_to_shapefile_zip,
    layer_features,
    layer_label_for,
    parse_layer_refs,
    validate_layer,
)

router = APIRouter()


class ExportLayerRef(BaseModel):
    interaction_type: str
    category_id: str


class ExportBatchBody(BaseModel):
    format: str = Field(pattern="^(csv|pdf|zip)$")
    layers: list[ExportLayerRef]


def _filename(base: str, ext: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)
    return f"pli-reporta_{safe}.{ext}"


def _batch_slug(packs: list[dict]) -> str:
    if len(packs) == 1:
        p = packs[0]
        return f"{p['interaction_type']}_{p['category_id']}"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"export_{len(packs)}_camadas_{ts}"


def _export_response(*, content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/batch")
def export_batch(
    body: ExportBatchBody,
    db: Session = Depends(get_session),
) -> Response:
    try:
        refs = parse_layer_refs(
            [
                {
                    "interaction_type": layer.interaction_type,
                    "category_id": layer.category_id,
                }
                for layer in body.layers
            ]
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    packs = batch_layer_data(db, refs)
    slug = _batch_slug(packs)

    if body.format == "csv":
        content = (
            batch_to_csv(packs)
            if len(packs) > 1
            else features_to_csv(packs[0]["features"], interaction_type=packs[0]["interaction_type"])
        )
        return _export_response(
            content=content,
            media_type="text/csv; charset=utf-8",
            filename=_filename(slug, "csv"),
        )
    if body.format == "pdf":
        content = (
            batch_to_pdf(packs)
            if len(packs) > 1
            else features_to_pdf(
                packs[0]["features"],
                interaction_type=packs[0]["interaction_type"],
                layer_label=packs[0]["layer_label"],
            )
        )
        return _export_response(
            content=content,
            media_type="application/pdf",
            filename=_filename(slug, "pdf"),
        )
    content = (
        batch_to_shapefile_zip(packs)
        if len(packs) > 1
        else features_to_shapefile_zip(
            packs[0]["features"],
            interaction_type=packs[0]["interaction_type"],
            layer_label=packs[0]["layer_label"],
        )
    )
    return _export_response(
        content=content,
        media_type="application/zip",
        filename=_filename(slug, "zip"),
    )


@router.get("/export/layer/{interaction_type}/{category_id}")
def export_layer(
    interaction_type: str,
    category_id: str,
    export_format: str = Query(..., alias="format", pattern="^(csv|pdf|zip)$"),
    db: Session = Depends(get_session),
) -> Response:
    itype = interaction_type.strip().lower()
    if itype not in ("evento_trafego", "manifestacao"):
        raise HTTPException(400, detail="interaction_type inválido.")

    try:
        cat = validate_layer(itype, category_id.strip().lower())
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    features = layer_features(db, itype, category_id.strip().lower())
    layer_label = layer_label_for(itype, cat["id"])
    slug = f"{itype}_{category_id}"

    if export_format == "csv":
        content = features_to_csv(features, interaction_type=itype)
        return _export_response(
            content=content,
            media_type="text/csv; charset=utf-8",
            filename=_filename(slug, "csv"),
        )
    if export_format == "pdf":
        content = features_to_pdf(
            features,
            interaction_type=itype,
            layer_label=layer_label,
        )
        return _export_response(
            content=content,
            media_type="application/pdf",
            filename=_filename(slug, "pdf"),
        )
    content = features_to_shapefile_zip(
        features,
        interaction_type=itype,
        layer_label=layer_label,
    )
    return _export_response(
        content=content,
        media_type="application/zip",
        filename=_filename(slug, "zip"),
    )
