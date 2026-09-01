"""Configuracao da aplicacao, lida de variaveis de ambiente.

Nada de segredo aqui -- e uma ferramenta interna -- mas centralizar caminhos e
limites evita constante espalhada pelo codigo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from zpl_core.printing import DEFAULT_PORT, NetworkPrinter

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    valor = os.getenv(name)
    return default if valor is None else valor.strip().lower() in {"1", "true", "sim", "yes"}


def _printers_from_env() -> list[NetworkPrinter]:
    """Le ``ETIQUETA_PRINTERS`` no formato ``Nome=host:porta;Nome2=host2``."""
    raw = os.getenv("ETIQUETA_PRINTERS", "").strip()
    if not raw:
        return []

    printers: list[NetworkPrinter] = []
    for pedaco in raw.split(";"):
        if "=" not in pedaco:
            continue
        nome, endereco = pedaco.split("=", 1)
        host, _, porta = endereco.strip().partition(":")
        if not host:
            continue
        printers.append(
            NetworkPrinter(
                name=nome.strip() or host,
                host=host,
                port=int(porta) if porta.isdigit() else DEFAULT_PORT,
            )
        )
    return printers


@dataclass(slots=True)
class Settings:
    templates_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("ETIQUETA_TEMPLATES_DIR", PROJECT_ROOT / "templates_store")
        )
    )
    web_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "web")
    host: str = field(default_factory=lambda: os.getenv("ETIQUETA_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("ETIQUETA_PORT", "8000")))

    #: Impressao direta desligada por padrao: ligar e uma decisao consciente de
    #: quem instala, porque envia bytes para um equipamento fisico da rede.
    allow_printing: bool = field(
        default_factory=lambda: _env_bool("ETIQUETA_ALLOW_PRINTING", False)
    )
    printers: list[NetworkPrinter] = field(default_factory=_printers_from_env)

    def __post_init__(self) -> None:
        self.templates_dir = Path(self.templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
