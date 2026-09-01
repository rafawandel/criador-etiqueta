"""Conversao entre unidades do mundo real (mm) e o mundo da impressora (dots).

Toda a aplicacao trabalha internamente em milimetros. O ZPL trabalha em dots.
A conversao acontece em um unico lugar -- aqui -- para que mudar o DPI da
impressora nao exija tocar em nenhuma outra parte do codigo.
"""

from __future__ import annotations

from dataclasses import dataclass

MM_PER_INCH = 25.4

#: DPIs de cabeca de impressao suportados pelas Zebra mais comuns.
SUPPORTED_DPI: tuple[int, ...] = (152, 203, 300, 600)
DEFAULT_DPI = 203


@dataclass(frozen=True, slots=True)
class Resolution:
    """Resolucao da cabeca de impressao."""

    dpi: int = DEFAULT_DPI

    def __post_init__(self) -> None:
        if self.dpi <= 0:
            raise ValueError("dpi deve ser positivo")

    @property
    def dots_per_mm(self) -> float:
        return self.dpi / MM_PER_INCH

    def mm_to_dots(self, mm: float) -> int:
        """Milimetros -> dots, arredondado para o dot mais proximo."""
        return int(round(mm * self.dots_per_mm))

    def dots_to_mm(self, dots: float) -> float:
        return dots / self.dots_per_mm

    def describe(self) -> str:
        return f"{self.dpi} dpi ({self.dots_per_mm:.2f} dots/mm)"


def mm_to_dots(mm: float, dpi: int = DEFAULT_DPI) -> int:
    return Resolution(dpi).mm_to_dots(mm)


def dots_to_mm(dots: float, dpi: int = DEFAULT_DPI) -> float:
    return Resolution(dpi).dots_to_mm(dots)
