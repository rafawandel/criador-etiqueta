"""Aplicacao FastAPI: serve a API e o editor.

A camada web e deliberadamente fina. Ela traduz HTTP para chamadas de
``zpl_core`` e devolve o resultado -- nenhuma regra de ZPL vive aqui.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import build_catalog
from app.routers import printing, render, templates
from app.settings import settings
from zpl_core import __version__

app = FastAPI(
    title="Criador de Etiquetas ZPL",
    version=__version__,
    description=(
        "Editor visual de etiquetas para impressoras Zebra. O ZPL e gerado em "
        "Python a partir de um modelo unico, exibido em tempo real no editor."
    ),
)

app.include_router(render.router)
app.include_router(templates.router)
app.include_router(printing.router)


@app.get("/api/catalog", tags=["catalog"])
def catalog() -> dict:
    """Descreve os elementos disponiveis; o editor monta a UI a partir daqui."""
    return build_catalog()


@app.get("/api/health", tags=["catalog"])
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "printing_enabled": settings.allow_printing,
        "printers_configured": len(settings.printers),
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.web_dir / "index.html")


# Montado por ultimo para nao capturar as rotas de API.
app.mount("/", StaticFiles(directory=settings.web_dir), name="web")


def run() -> None:  # pragma: no cover - ponto de entrada
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=bool(__debug__),
    )
