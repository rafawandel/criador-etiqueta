"""Enumeracoes do dominio ZPL.

Os valores das enums sao exatamente os caracteres que o ZPL espera, para que a
geracao do codigo seja uma substituicao direta e nao uma tabela de traducao.
"""

from __future__ import annotations

from enum import StrEnum


class Rotation(StrEnum):
    """Orientacao do campo. O valor e o caractere aceito pelo ZPL."""

    NORMAL = "N"        # 0 graus
    ROTATED = "R"       # 90 graus horario
    INVERTED = "I"      # 180 graus
    BOTTOM_UP = "B"     # 270 graus

    @property
    def degrees(self) -> int:
        return {"N": 0, "R": 90, "I": 180, "B": 270}[self.value]

    @classmethod
    def from_degrees(cls, degrees: int) -> "Rotation":
        return {0: cls.NORMAL, 90: cls.ROTATED, 180: cls.INVERTED, 270: cls.BOTTOM_UP}[
            degrees % 360
        ]


class Justification(StrEnum):
    """Alinhamento dentro de um bloco de texto (^FB)."""

    LEFT = "L"
    CENTER = "C"
    RIGHT = "R"
    JUSTIFIED = "J"


class Color(StrEnum):
    """Cor do traco em elementos graficos."""

    BLACK = "B"
    WHITE = "W"


class Symbology(StrEnum):
    """Simbologias de codigo de barras 1D suportadas."""

    CODE128 = "code128"
    CODE39 = "code39"
    EAN13 = "ean13"
    EAN8 = "ean8"
    UPCA = "upca"
    ITF = "itf"
    CODE93 = "code93"


class QrErrorCorrection(StrEnum):
    """Nivel de correcao de erro do QR Code (letra usada no ^FD)."""

    LOW = "L"        # ~7%
    MEDIUM = "M"     # ~15%
    QUARTILE = "Q"   # ~25%
    HIGH = "H"       # ~30%


class TextAnchor(StrEnum):
    """De onde o ^FO mede a posicao do campo.

    ZPL ancora no canto superior esquerdo por padrao (^FW / ^FO). Manter isso
    explicito no modelo evita surpresas quando o usuario alinha elementos.
    """

    TOP_LEFT = "top-left"
    BASELINE = "baseline"
