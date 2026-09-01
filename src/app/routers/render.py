"""Geracao de ZPL e imagens de preview.

O painel "ZPL ao vivo" do editor bate em ``POST /api/zpl`` a cada alteracao
(com debounce no cliente). O ZPL e gerado em Python -- nunca em JavaScript --
para que o codigo mostrado na tela seja *exatamente* o que sera impresso.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse

from app.schemas import ImagePreviewRequest, LabelPayload, ZplResponse
from zpl_core.barcodes import render_barcode_png, render_datamatrix_png, render_qrcode_png
from zpl_core.images import ImageConversionError, bitmap_to_png, image_to_bitmap
from zpl_core.label import Label
from zpl_core.serialization import SerializationError, label_from_dict
from zpl_core.units import Resolution
from zpl_core.validation import validate
from zpl_core.zpl_writer import ZplWriter

router = APIRouter(prefix="/api", tags=["render"])

#: Cache do navegador para os previews. Os parametros ficam na URL, entao a
#: mesma imagem nunca precisa ser gerada duas vezes.
_CACHE_HEADERS = {"Cache-Control": "public, max-age=86400"}


def parse_label(payload: dict) -> Label:
    """Converte o dicionario recebido em ``Label``, com erro amigavel."""
    try:
        return label_from_dict(payload)
    except SerializationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/zpl", response_model=ZplResponse)
def generate_zpl(payload: LabelPayload) -> ZplResponse:
    """Modelo -> ZPL + mapa de segmentos + achados da validacao."""
    label = parse_label(payload.label)
    documento = ZplWriter(include_comments=payload.comments).write(label, payload.data)
    compacto = documento.compact()

    return ZplResponse(
        zpl=documento.text,
        compact=compacto,
        line_count=len(documento.lines),
        byte_size=len(compacto.encode(label.encoding, errors="replace")),
        segments=[asdict(s) for s in documento.segments],
        issues=[asdict(i) for i in validate(label)],
        width_dots=label.width_dots,
        height_dots=label.height_dots,
        placeholders=sorted(label.placeholders()),
    )


@router.post("/export/zpl", response_class=PlainTextResponse)
def export_zpl(payload: LabelPayload) -> PlainTextResponse:
    """Mesmo ZPL, servido como arquivo ``.zpl`` para download."""
    label = parse_label(payload.label)
    documento = ZplWriter(include_comments=payload.comments).write(label, payload.data)
    nome = (label.name or "etiqueta").replace('"', "")
    return PlainTextResponse(
        documento.text,
        headers={"Content-Disposition": f'attachment; filename="{nome}.zpl"'},
    )


# ---------------------------------------------------------------------------
# Previews
# ---------------------------------------------------------------------------
@router.get("/preview/barcode")
def preview_barcode(
    symbology: str = Query(...),
    data: str = Query(""),
    width: int = Query(400, ge=8, le=4000),
    height: int = Query(120, ge=8, le=2000),
    show_text: bool = Query(True),
    bar_height_mm: float = Query(10.0, gt=0, le=300),
) -> Response:
    png = render_barcode_png(
        symbology,
        data,
        width_px=width,
        height_px=height,
        show_text=show_text,
        bar_height_mm=bar_height_mm,
    )
    return Response(png, media_type="image/png", headers=_CACHE_HEADERS)


@router.get("/preview/qrcode")
def preview_qrcode(
    data: str = Query(""),
    size: int = Query(200, ge=16, le=2000),
    ecc: str = Query("M"),
) -> Response:
    png = render_qrcode_png(data, size_px=size, error_correction=ecc)
    return Response(png, media_type="image/png", headers=_CACHE_HEADERS)


@router.get("/preview/datamatrix")
def preview_datamatrix(
    data: str = Query(""),
    size: int = Query(200, ge=16, le=2000),
) -> Response:
    png = render_datamatrix_png(data, size_px=size)
    return Response(png, media_type="image/png", headers=_CACHE_HEADERS)


@router.post("/preview/image")
def preview_image(payload: ImagePreviewRequest) -> Response:
    """Devolve a imagem ja convertida para 1 bit.

    Mostrar o resultado real da conversao (e nao a imagem original) evita a
    frustracao classica de ver um logotipo bonito na tela e um borrao na
    etiqueta.
    """
    resolution = Resolution(payload.dpi)
    try:
        bitmap = image_to_bitmap(
            payload.source,
            width_dots=resolution.mm_to_dots(payload.width_mm),
            height_dots=resolution.mm_to_dots(payload.height_mm),
            threshold=payload.threshold,
            dither=payload.dither,
            invert=payload.invert,
        )
    except ImageConversionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return Response(bitmap_to_png(bitmap), media_type="image/png")
