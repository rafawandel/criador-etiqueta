"""A etiqueta: configuracao de midia, parametros de impressao e elementos."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any

from .elements import Element, RenderContext
from .units import DEFAULT_DPI, Resolution

#: Placeholders de campo variavel, no formato {{sku}}.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")

#: Atributos textuais em que a substituicao de placeholders acontece.
_MERGEABLE_FIELDS = ("text", "data")


@dataclass(slots=True)
class PrintSettings:
    """Parametros que afetam a impressao, nao o desenho.

    Todos sao opcionais: quando ``None``, a configuracao gravada na impressora
    prevalece -- que costuma ser o comportamento desejado em producao.
    """

    copies: int = 1
    darkness: int | None = None      # ^MD  -30 a 30
    speed_ips: int | None = None     # ^PR  polegadas por segundo
    home_x_dots: int = 0             # ^LH  deslocamento global
    home_y_dots: int = 0
    invert_all: bool = False         # ^POI (imprime a etiqueta de cabeca)
    pause_between: bool = False      # ^PQ com pausa


@dataclass(slots=True)
class Label:
    """Uma etiqueta completa."""

    name: str = "Nova etiqueta"
    width_mm: float = 100.0
    height_mm: float = 50.0
    dpi: int = DEFAULT_DPI
    encoding: str = "utf-8"
    elements: list[Element] = field(default_factory=list)
    print_settings: PrintSettings = field(default_factory=PrintSettings)

    # -- derivados ---------------------------------------------------------
    @property
    def resolution(self) -> Resolution:
        return Resolution(self.dpi)

    @property
    def width_dots(self) -> int:
        return self.resolution.mm_to_dots(self.width_mm)

    @property
    def height_dots(self) -> int:
        return self.resolution.mm_to_dots(self.height_mm)

    def render_context(self) -> RenderContext:
        return RenderContext(resolution=self.resolution, encoding=self.encoding)

    # -- manipulacao -------------------------------------------------------
    def add(self, element: Element) -> Element:
        self.elements.append(element)
        return element

    def find(self, element_id: str) -> Element | None:
        return next((e for e in self.elements if e.id == element_id), None)

    def remove(self, element_id: str) -> bool:
        before = len(self.elements)
        self.elements = [e for e in self.elements if e.id != element_id]
        return len(self.elements) != before

    def visible_elements(self) -> list[Element]:
        return [e for e in self.elements if e.visible]

    # -- campos variaveis --------------------------------------------------
    def placeholders(self) -> set[str]:
        """Nomes de todos os campos variaveis usados na etiqueta."""
        found: set[str] = set()
        for element in self.elements:
            for attr in _MERGEABLE_FIELDS:
                value = getattr(element, attr, None)
                if isinstance(value, str):
                    found.update(PLACEHOLDER_RE.findall(value))
        return found

    def merged(self, data: dict[str, Any]) -> "Label":
        """Copia da etiqueta com os placeholders substituidos por ``data``.

        Placeholders sem valor correspondente ficam como estao, para que o
        problema apareca na etiqueta em vez de virar um campo silenciosamente
        vazio.
        """
        if not data:
            return self

        def substitute(text: str) -> str:
            return PLACEHOLDER_RE.sub(
                lambda m: str(data.get(m.group(1), m.group(0))), text
            )

        new_elements: list[Element] = []
        for element in self.elements:
            changes = {
                attr: substitute(getattr(element, attr))
                for attr in _MERGEABLE_FIELDS
                if isinstance(getattr(element, attr, None), str)
            }
            new_elements.append(replace(element, **changes) if changes else element)

        return replace(self, elements=new_elements)
