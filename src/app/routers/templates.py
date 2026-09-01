"""Modelos de etiqueta salvos."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.routers.render import parse_label
from app.schemas import SaveTemplateRequest, TemplateSummary
from app.services.template_store import (
    TemplateExists,
    TemplateNotFound,
    TemplateStore,
)
from app.settings import settings
from zpl_core.serialization import label_to_dict

router = APIRouter(prefix="/api/templates", tags=["templates"])
store = TemplateStore(settings.templates_dir)


@router.get("", response_model=list[TemplateSummary])
def list_templates() -> list[dict]:
    return store.list()


@router.get("/{slug}")
def get_template(slug: str) -> dict:
    try:
        return label_to_dict(store.get(slug))
    except TemplateNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("")
def save_template(payload: SaveTemplateRequest) -> dict:
    label = parse_label(payload.label)
    try:
        slug = store.save(label, payload.slug, overwrite=payload.overwrite)
    except TemplateExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"slug": slug, "name": label.name}


@router.delete("/{slug}")
def delete_template(slug: str) -> dict:
    try:
        store.delete(slug)
    except TemplateNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": slug}
