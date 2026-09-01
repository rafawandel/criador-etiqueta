"""Envio para a impressora.

Este e o unico router com efeito no mundo fisico, entao vem desligado por
padrao (``ETIQUETA_ALLOW_PRINTING=1`` para habilitar) e so aceita impressoras
previamente configuradas ou um endereco explicito informado pelo usuario.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException

from app.routers.render import parse_label
from app.schemas import PrinterOut, PrintRequest, PrintResponse
from app.settings import settings
from zpl_core.printing import (
    DEFAULT_PORT,
    NetworkPrinter,
    PrintError,
    list_windows_printers,
    send_to_network,
    send_to_windows_spooler,
)
from zpl_core.zpl_writer import ZplWriter

router = APIRouter(prefix="/api", tags=["printing"])


def _resolve(nome: str) -> tuple[str, NetworkPrinter | None]:
    """Nome informado -> impressora de rede configurada, fila local ou host:porta."""
    for printer in settings.printers:
        if printer.name == nome:
            return ("network", printer)

    if nome in list_windows_printers():
        return ("spooler", None)

    if ":" in nome or "." in nome:
        host, _, porta = nome.partition(":")
        return (
            "network",
            NetworkPrinter(
                name=nome, host=host, port=int(porta) if porta.isdigit() else DEFAULT_PORT
            ),
        )

    raise HTTPException(status_code=404, detail=f"Impressora '{nome}' nao encontrada.")


@router.get("/printers", response_model=list[PrinterOut])
def list_printers() -> list[dict]:
    disponiveis = [
        {"name": p.name, "kind": "network", "address": f"{p.host}:{p.port}"}
        for p in settings.printers
    ]
    disponiveis += [
        {"name": nome, "kind": "spooler", "address": None} for nome in list_windows_printers()
    ]
    return disponiveis


@router.post("/print", response_model=PrintResponse)
def print_label(payload: PrintRequest) -> PrintResponse:
    if not settings.allow_printing:
        raise HTTPException(
            status_code=403,
            detail=(
                "Impressao direta desabilitada. Defina ETIQUETA_ALLOW_PRINTING=1 para "
                "liberar, ou baixe o .zpl e envie manualmente."
            ),
        )

    label = parse_label(payload.label)
    if payload.copies > 1:
        label.print_settings = replace(label.print_settings, copies=payload.copies)

    # A impressora quer ZPL compacto e sem comentarios.
    zpl = ZplWriter(include_comments=False).write(label, payload.data).compact()
    kind, printer = _resolve(payload.printer)

    try:
        if kind == "network" and printer is not None:
            enviados = send_to_network(zpl, printer, label.encoding)
            destino = printer.describe()
        else:
            enviados = send_to_windows_spooler(zpl, payload.printer, label.encoding)
            destino = payload.printer
    except PrintError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PrintResponse(
        ok=True,
        printer=destino,
        bytes_sent=enviados,
        message=f"{payload.copies} etiqueta(s) enviada(s) para {destino}.",
    )
