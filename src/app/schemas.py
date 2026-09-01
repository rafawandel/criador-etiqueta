"""Contratos HTTP (Pydantic).

A etiqueta em si trafega como dicionario livre e e validada por
``zpl_core.serialization``, que ja e a autoridade sobre o formato. Duplicar o
modelo em Pydantic criaria duas fontes da verdade -- e a garantia de que uma
delas ficaria desatualizada.

Pydantic cuida do que e genuinamente de HTTP: envelopes, opcoes de render e
parametros de impressao.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LabelPayload(BaseModel):
    """Envelope de uma requisicao que carrega uma etiqueta."""

    label: dict[str, Any] = Field(description="Etiqueta serializada (schema do zpl_core).")
    data: dict[str, str] = Field(
        default_factory=dict,
        description="Valores dos campos variaveis {{campo}}.",
    )
    comments: bool = Field(default=True, description="Emitir comentarios ^FX no ZPL.")


class ZplSegmentOut(BaseModel):
    element_id: str
    start_line: int
    end_line: int


class IssueOut(BaseModel):
    severity: str
    message: str
    element_id: str | None = None
    hint: str | None = None


class ZplResponse(BaseModel):
    """Resposta do endpoint que alimenta o painel de ZPL ao vivo."""

    zpl: str
    compact: str
    line_count: int
    byte_size: int
    segments: list[ZplSegmentOut]
    issues: list[IssueOut]
    width_dots: int
    height_dots: int
    placeholders: list[str]


class TemplateSummary(BaseModel):
    slug: str
    name: str
    width_mm: float
    height_mm: float
    dpi: int
    element_count: int
    updated_at: str


class SaveTemplateRequest(BaseModel):
    label: dict[str, Any]
    slug: str | None = Field(
        default=None,
        description="Identificador do arquivo. Gerado a partir do nome quando ausente.",
    )
    overwrite: bool = True


class PrintRequest(BaseModel):
    label: dict[str, Any]
    data: dict[str, str] = Field(default_factory=dict)
    printer: str = Field(description="Nome configurado, ou host[:porta].")
    copies: int = Field(default=1, ge=1, le=999)


class PrintResponse(BaseModel):
    ok: bool
    printer: str
    bytes_sent: int
    message: str


class PrinterOut(BaseModel):
    name: str
    kind: str
    address: str | None = None


class ImagePreviewRequest(BaseModel):
    """Converte uma imagem para o bitmap 1-bit que a impressora vai receber."""

    source: str = Field(description="Data URL da imagem.")
    width_mm: float = Field(gt=0, le=500)
    height_mm: float = Field(gt=0, le=500)
    dpi: int = Field(default=203, gt=0, le=1200)
    threshold: int = Field(default=128, ge=0, le=255)
    dither: bool = False
    invert: bool = False
