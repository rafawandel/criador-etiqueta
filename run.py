#!/usr/bin/env python
"""Sobe o editor de etiquetas.

    uv run python run.py                    # http://127.0.0.1:8000
    uv run python run.py --port 9000
    uv run python run.py --host 0.0.0.0     # libera para a rede local

Insere `src/` no path na mao, entao tambem roda com o interpretador do venv
diretamente -- util em maquina de producao onde so existe o .venv ja preparado.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from threading import Timer

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))


def main() -> int:
    parser = argparse.ArgumentParser(description="Editor visual de etiquetas ZPL")
    parser.add_argument("--host", default=None, help="endereco de escuta (padrao: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="porta (padrao: 8000)")
    parser.add_argument("--reload", action="store_true", help="recarrega ao editar o codigo")
    parser.add_argument("--no-browser", action="store_true", help="nao abre o navegador")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Dependencias faltando. Rode:\n\n    uv sync\n")
        return 1

    from app.settings import settings

    host = args.host or settings.host
    port = args.port or settings.port
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}/"

    print(f"\n  Criador de Etiquetas ZPL")
    print(f"  Editor:        {url}")
    print(f"  API (docs):    {url}docs")
    print(f"  Modelos em:    {settings.templates_dir}")
    print(f"  Impressao:     {'habilitada' if settings.allow_printing else 'desabilitada'}")
    print("\n  Ctrl+C para encerrar.\n")

    if not args.no_browser:
        Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run("app.main:app", host=host, port=port, reload=args.reload, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
