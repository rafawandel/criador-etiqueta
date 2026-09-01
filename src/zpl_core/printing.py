"""Envio do ZPL para a impressora.

Tres caminhos, do mais comum ao mais especifico:

* **rede** -- socket TCP na porta 9100 (raw). E como praticamente toda Zebra de
  chao de fabrica recebe trabalho;
* **arquivo** -- grava um ``.zpl`` para conferencia ou envio manual;
* **spooler do Windows** -- fila local ja instalada, exige pywin32.

Nenhum caminho tenta interpretar a resposta da impressora: ZPL raw e uma via de
mao unica. O que garantimos e um erro claro quando o envio nao acontece.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PORT = 9100
DEFAULT_TIMEOUT = 5.0


class PrintError(RuntimeError):
    """Nao foi possivel entregar o trabalho a impressora."""


@dataclass(slots=True, frozen=True)
class NetworkPrinter:
    """Uma Zebra alcancavel por IP."""

    name: str
    host: str
    port: int = DEFAULT_PORT
    timeout: float = DEFAULT_TIMEOUT

    def describe(self) -> str:
        return f"{self.name} ({self.host}:{self.port})"


def send_to_network(zpl: str, printer: NetworkPrinter, encoding: str = "utf-8") -> int:
    """Envia o ZPL por TCP raw. Devolve os bytes escritos."""
    payload = zpl.encode(encoding, errors="replace")
    try:
        with socket.create_connection((printer.host, printer.port), printer.timeout) as sock:
            sock.sendall(payload)
        return len(payload)
    except TimeoutError as exc:
        raise PrintError(
            f"{printer.describe()} nao respondeu em {printer.timeout:g}s. "
            "Verifique se a impressora esta ligada e na mesma rede."
        ) from exc
    except OSError as exc:
        raise PrintError(f"Falha ao conectar em {printer.describe()}: {exc}") from exc


def send_to_windows_spooler(zpl: str, printer_name: str, encoding: str = "utf-8") -> int:
    """Envia por uma fila do Windows ja instalada (driver generico / raw)."""
    try:
        import win32print  # type: ignore[import-not-found]
    except ImportError as exc:
        raise PrintError(
            "Impressao pelo spooler exige pywin32. Instale com "
            "'uv sync --extra windows-print', ou use o envio por IP."
        ) from exc

    payload = zpl.encode(encoding, errors="replace")
    handle = win32print.OpenPrinter(printer_name)
    try:
        job = win32print.StartDocPrinter(handle, 1, ("Etiqueta ZPL", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, payload)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
        return len(payload)
    except Exception as exc:  # noqa: BLE001
        raise PrintError(f"Falha ao imprimir em '{printer_name}': {exc}") from exc
    finally:
        win32print.ClosePrinter(handle)


def list_windows_printers() -> list[str]:
    """Filas locais disponiveis; lista vazia se pywin32 nao estiver instalado."""
    try:
        import win32print  # type: ignore[import-not-found]
    except ImportError:
        return []
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p[2] for p in win32print.EnumPrinters(flags)]


def save_to_file(zpl: str, path: str | Path, encoding: str = "utf-8") -> Path:
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(zpl, encoding=encoding)
    return destino


def probe(host: str, port: int = DEFAULT_PORT, timeout: float = 2.0) -> bool:
    """Testa se a porta raw esta aceitando conexao, sem enviar nada."""
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False
