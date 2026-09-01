"""Persistencia de modelos de etiqueta em arquivos JSON.

Arquivo em disco em vez de banco por escolha: o time de producao consegue
versionar, copiar para outra maquina e abrir o modelo em um editor de texto.
Se um dia virar multiusuario com historico, esta classe e o unico ponto a
substituir -- o resto da aplicacao so conhece a interface.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from zpl_core.label import Label
from zpl_core.serialization import SerializationError, load_label, save_label

_SLUG_INVALIDO = re.compile(r"[^a-z0-9]+")


class TemplateNotFound(LookupError):
    pass


class TemplateExists(FileExistsError):
    pass


def slugify(nome: str) -> str:
    """Nome legivel -> identificador seguro para nome de arquivo."""
    normalizado = unicodedata.normalize("NFKD", nome)
    ascii_only = normalizado.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_INVALIDO.sub("-", ascii_only).strip("-")
    return slug[:60] or "etiqueta"


class TemplateStore:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    # -- caminhos ----------------------------------------------------------
    def _path(self, slug: str) -> Path:
        seguro = slugify(slug)
        if not seguro:
            raise TemplateNotFound("Identificador vazio.")
        # Resolver e conferir o pai barra qualquer tentativa de escapar da pasta.
        caminho = (self.directory / f"{seguro}.json").resolve()
        if caminho.parent != self.directory.resolve():
            raise TemplateNotFound(f"Caminho invalido: {slug!r}")
        return caminho

    # -- leitura -----------------------------------------------------------
    def list(self) -> list[dict]:
        resumos: list[dict] = []
        for arquivo in sorted(self.directory.glob("*.json")):
            try:
                label = load_label(arquivo)
            except (SerializationError, OSError):
                continue  # arquivo corrompido nao impede listar os outros
            resumos.append(
                {
                    "slug": arquivo.stem,
                    "name": label.name,
                    "width_mm": label.width_mm,
                    "height_mm": label.height_mm,
                    "dpi": label.dpi,
                    "element_count": len(label.elements),
                    "updated_at": datetime.fromtimestamp(
                        arquivo.stat().st_mtime, tz=timezone.utc
                    ).isoformat(timespec="seconds"),
                }
            )
        return sorted(resumos, key=lambda r: r["updated_at"], reverse=True)

    def get(self, slug: str) -> Label:
        caminho = self._path(slug)
        if not caminho.exists():
            raise TemplateNotFound(f"Modelo '{slug}' nao encontrado.")
        return load_label(caminho)

    # -- escrita -----------------------------------------------------------
    def save(self, label: Label, slug: str | None = None, *, overwrite: bool = True) -> str:
        destino = self._path(slug or label.name)
        if destino.exists() and not overwrite:
            raise TemplateExists(f"Modelo '{destino.stem}' ja existe.")
        save_label(label, destino)
        return destino.stem

    def delete(self, slug: str) -> None:
        caminho = self._path(slug)
        if not caminho.exists():
            raise TemplateNotFound(f"Modelo '{slug}' nao encontrado.")
        caminho.unlink()
