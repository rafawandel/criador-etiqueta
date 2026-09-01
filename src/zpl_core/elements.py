"""Modelo de dados dos objetos que podem ser colocados na etiqueta.

Cada elemento e uma dataclass simples (dados) que sabe duas coisas:

* ``to_zpl(ctx)``  -> as linhas de ZPL que ele gera;
* ``size_mm()``    -> o espaco que ele ocupa, usado pela validacao e pelo
  editor para desenhar a caixa de selecao.

Elementos novos entram registrando-se em ``ELEMENT_TYPES`` no fim do arquivo --
o resto da aplicacao (API, editor, validacao) passa a suporta-los sem alteracao.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import ClassVar

from .enums import Color, Justification, QrErrorCorrection, Rotation, Symbology
from .escaping import field_data, sanitize_comment
from .units import Resolution

# Os campos de enum sao StrEnum, entao interpolamos o valor direto ("^A0N,...")
# em vez de acessar `.value`. Assim um elemento montado com string crua
# (TextElement(rotation="R")) gera o mesmo ZPL de um montado com o enum -- o que
# importa para quem usa o zpl_core em script, sem passar pela serializacao.

# Largura media de um caractere na fonte escalavel ^A0, como fracao da altura.
# Usada apenas para estimar a caixa do texto -- o render real e feito no editor.
_AVG_CHAR_RATIO = 0.58


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass(slots=True)
class RenderContext:
    """Tudo que um elemento precisa saber do mundo externo para virar ZPL."""

    resolution: Resolution = field(default_factory=Resolution)
    encoding: str = "utf-8"

    def dots(self, mm: float) -> int:
        return self.resolution.mm_to_dots(mm)


@dataclass(slots=True, kw_only=True)
class Element:
    """Base de todos os objetos da etiqueta."""

    type: ClassVar[str] = "abstract"

    id: str = field(default_factory=_new_id)
    name: str = ""
    x_mm: float = 0.0
    y_mm: float = 0.0
    rotation: Rotation = Rotation.NORMAL
    visible: bool = True
    locked: bool = False

    # -- API que as subclasses implementam ---------------------------------
    def to_zpl(self, ctx: RenderContext) -> list[str]:
        raise NotImplementedError

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        """Largura e altura ocupadas, ja considerando a rotacao.

        ``resolution`` importa nos elementos cujo tamanho e definido em dots
        (codigos de barras, QR, DataMatrix): o mesmo modulo ocupa metade do
        espaco em uma cabeca de 300 dpi.
        """
        raise NotImplementedError

    # -- helpers compartilhados --------------------------------------------
    def bounds_mm(self, resolution: Resolution | None = None) -> tuple[float, float, float, float]:
        w, h = self.size_mm(resolution)
        return (self.x_mm, self.y_mm, self.x_mm + w, self.y_mm + h)

    def display_name(self) -> str:
        return self.name or self.type.replace("_", " ").title()

    def _origin(self, ctx: RenderContext) -> str:
        return f"^FO{ctx.dots(self.x_mm)},{ctx.dots(self.y_mm)}"

    def _swap_for_rotation(self, w: float, h: float) -> tuple[float, float]:
        rotated = self.rotation in (Rotation.ROTATED, Rotation.BOTTOM_UP)
        return (h, w) if rotated else (w, h)


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
@dataclass(slots=True, kw_only=True)
class TextElement(Element):
    """Texto usando fonte interna da impressora (^A)."""

    type: ClassVar[str] = "text"

    text: str = "Texto"
    font: str = "0"              # 0 = escalavel; A-Z = fontes bitmap fixas
    height_mm: float = 4.0
    width_mm: float = 0.0        # 0 = proporcional a altura
    reverse: bool = False        # ^FR -> imprime invertido sobre area preta

    # Bloco de texto (^FB): quando block_width_mm > 0 o texto quebra linha.
    block_width_mm: float = 0.0
    block_max_lines: int = 1
    block_line_spacing_mm: float = 0.0
    justification: Justification = Justification.LEFT

    def to_zpl(self, ctx: RenderContext) -> list[str]:
        height = ctx.dots(self.height_mm)
        width = ctx.dots(self.width_mm) if self.width_mm > 0 else 0
        parts = [self._origin(ctx), f"^A{self.font}{self.rotation},{height},{width}"]

        if self.block_width_mm > 0:
            parts.append(
                f"^FB{ctx.dots(self.block_width_mm)},{max(1, self.block_max_lines)},"
                f"{ctx.dots(self.block_line_spacing_mm)},{self.justification},0"
            )
        if self.reverse:
            parts.append("^FR")

        parts.append(field_data(self.text, ctx.encoding))
        parts.append("^FS")
        return ["".join(parts)]

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        char_w = self.width_mm if self.width_mm > 0 else self.height_mm * _AVG_CHAR_RATIO
        if self.block_width_mm > 0:
            lines = max(1, self.block_max_lines)
            w = self.block_width_mm
            h = self.height_mm * lines + self.block_line_spacing_mm * (lines - 1)
        else:
            w = max(char_w * len(self.text), char_w)
            h = self.height_mm
        return self._swap_for_rotation(w, h)


# ---------------------------------------------------------------------------
# Codigos de barras 1D
# ---------------------------------------------------------------------------

#: Simbologia -> comando ZPL correspondente.
_BARCODE_COMMANDS: dict[Symbology, str] = {
    Symbology.CODE128: "^BC",
    Symbology.CODE39: "^B3",
    Symbology.CODE93: "^BA",
    Symbology.EAN13: "^BE",
    Symbology.EAN8: "^B8",
    Symbology.UPCA: "^BU",
    Symbology.ITF: "^B2",
}


def barcode_modules(symbology: Symbology, data: str, wide_ratio: float = 3.0) -> int:
    """Quantos modulos estreitos o codigo ocupa na horizontal.

    Cada simbologia tem uma estrutura propria -- EAN tem largura fixa, Code 128
    gasta 11 modulos por caractere, Code 39 gasta mais porque alterna barras
    largas e estreitas. Estimar isso direito e o que permite ao editor
    responder a pergunta que mais importa: "esse codigo cabe na etiqueta?".

    Inclui as zonas de silencio, que sao parte da area que precisa ficar livre
    para o leitor enxergar o codigo.
    """
    n = max(1, len(data))
    silencio = 20  # 10 modulos de cada lado

    match symbology:
        case Symbology.EAN13 | Symbology.UPCA:
            return 95 + 18   # largura fixa + zonas de silencio da norma
        case Symbology.EAN8:
            return 67 + 14
        case Symbology.CODE128:
            # start + dados + verificador + stop
            return 11 * (n + 2) + 13 + silencio
        case Symbology.CODE93:
            return 9 * (n + 4) + 1 + silencio
        case Symbology.CODE39:
            # 9 elementos por caractere, 3 deles largos, mais o espaco entre
            # caracteres; start e stop (*) entram na conta.
            por_char = 6 + 3 * wide_ratio + 1
            return int(por_char * (n + 2)) + silencio
        case Symbology.ITF:
            # Digitos sao codificados aos pares: 5 elementos por digito, 2 largos.
            por_digito = 3 + 2 * wide_ratio
            return int(por_digito * n) + 9 + silencio
        case _:
            return 11 * n + 35 + silencio


@dataclass(slots=True, kw_only=True)
class BarcodeElement(Element):
    """Codigo de barras linear."""

    type: ClassVar[str] = "barcode"

    symbology: Symbology = Symbology.CODE128
    data: str = "123456789012"
    height_mm: float = 12.0
    module_width_dots: int = 2       # ^BY: largura da barra estreita
    wide_ratio: float = 3.0          # ^BY: relacao larga/estreita (2.0 a 3.0)
    show_text: bool = True           # linha de interpretacao
    text_above: bool = False
    check_digit: bool = False

    def to_zpl(self, ctx: RenderContext) -> list[str]:
        height = ctx.dots(self.height_mm)
        f = "Y" if self.show_text else "N"
        g = "Y" if self.text_above else "N"
        e = "Y" if self.check_digit else "N"
        rot = f"{self.rotation}"
        cmd = _BARCODE_COMMANDS[self.symbology]

        match self.symbology:
            case Symbology.CODE128:
                # ^BCo,h,f,g,e,m -- modo A deixa a impressora escolher o subset
                barcode = f"{cmd}{rot},{height},{f},{g},{e},A"
            case Symbology.CODE39:
                barcode = f"{cmd}{rot},{e},{height},{f},{g}"
            case Symbology.CODE93 | Symbology.UPCA | Symbology.ITF:
                barcode = f"{cmd}{rot},{height},{f},{g},{e}"
            case _:  # EAN13 / EAN8 -- digito verificador e sempre calculado
                barcode = f"{cmd}{rot},{height},{f},{g}"

        return [
            f"{self._origin(ctx)}^BY{self.module_width_dots},{self.wide_ratio:g},{height}"
            f"{barcode}{field_data(self.data, ctx.encoding)}^FS"
        ]

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        dots_per_mm = (resolution or Resolution()).dots_per_mm
        module_mm = self.module_width_dots / dots_per_mm
        modules = barcode_modules(self.symbology, self.data, self.wide_ratio)
        w = max(modules * module_mm, 10.0)
        # A linha de interpretacao ocupa ~3.5 mm na fonte que a Zebra usa.
        h = self.height_mm + (3.5 if self.show_text else 0.0)
        return self._swap_for_rotation(w, h)


# ---------------------------------------------------------------------------
# Codigos 2D
# ---------------------------------------------------------------------------
@dataclass(slots=True, kw_only=True)
class QrCodeElement(Element):
    """QR Code (^BQ)."""

    type: ClassVar[str] = "qrcode"

    data: str = "https://example.com"
    magnification: int = 4           # 1 a 10 -- tamanho do modulo em dots
    error_correction: QrErrorCorrection = QrErrorCorrection.MEDIUM
    model: int = 2

    def to_zpl(self, ctx: RenderContext) -> list[str]:
        mag = max(1, min(10, self.magnification))
        # No ^BQ o ^FD carrega "<correcao><modo>,<dados>"; A = automatico.
        payload = field_data(f"{self.error_correction}A,{self.data}", ctx.encoding)
        return [
            f"{self._origin(ctx)}^BQ{self.rotation},{self.model},{mag},"
            f"{self.error_correction}{payload}^FS"
        ]

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        # Versao aproximada do QR a partir do volume de dados.
        modules = 21 + 4 * min(10, max(0, (len(self.data) - 10) // 14))
        side = modules * self.magnification / (resolution or Resolution()).dots_per_mm
        return (side, side)


@dataclass(slots=True, kw_only=True)
class DataMatrixElement(Element):
    """DataMatrix (^BX)."""

    type: ClassVar[str] = "datamatrix"

    data: str = "DATAMATRIX"
    module_size_dots: int = 6
    quality: int = 200               # 200 = ECC200, o unico usado hoje

    def to_zpl(self, ctx: RenderContext) -> list[str]:
        return [
            f"{self._origin(ctx)}^BX{self.rotation},{self.module_size_dots},"
            f"{self.quality}{field_data(self.data, ctx.encoding)}^FS"
        ]

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        modules = 10 + 2 * min(12, len(self.data) // 3)
        side = modules * self.module_size_dots / (resolution or Resolution()).dots_per_mm
        return (side, side)


# ---------------------------------------------------------------------------
# Graficos
# ---------------------------------------------------------------------------
@dataclass(slots=True, kw_only=True)
class BoxElement(Element):
    """Retangulo ou area preenchida (^GB)."""

    type: ClassVar[str] = "box"

    width_mm: float = 30.0
    height_mm: float = 15.0
    thickness_mm: float = 0.4
    color: Color = Color.BLACK
    rounding: int = 0                # 0 (reto) a 8 (bem arredondado)

    def to_zpl(self, ctx: RenderContext) -> list[str]:
        t = max(1, ctx.dots(self.thickness_mm))
        return [
            f"{self._origin(ctx)}^GB{ctx.dots(self.width_mm)},{ctx.dots(self.height_mm)},"
            f"{t},{self.color},{max(0, min(8, self.rounding))}^FS"
        ]

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        return (self.width_mm, self.height_mm)


@dataclass(slots=True, kw_only=True)
class LineElement(Element):
    """Linha horizontal, vertical ou diagonal.

    Horizontais e verticais viram um ^GB degenerado (mais previsivel na
    impressora); diagonais usam ^GD.
    """

    type: ClassVar[str] = "line"

    width_mm: float = 40.0
    height_mm: float = 0.0
    thickness_mm: float = 0.4
    color: Color = Color.BLACK
    diagonal: bool = False
    lean_right: bool = True          # ^GD: orientacao R ou L

    def to_zpl(self, ctx: RenderContext) -> list[str]:
        t = max(1, ctx.dots(self.thickness_mm))
        w, h = ctx.dots(self.width_mm), ctx.dots(self.height_mm)
        if self.diagonal:
            orient = "R" if self.lean_right else "L"
            return [f"{self._origin(ctx)}^GD{w},{h},{t},{self.color},{orient}^FS"]
        return [f"{self._origin(ctx)}^GB{w},{h},{t},{self.color},0^FS"]

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        return (
            max(self.width_mm, self.thickness_mm),
            max(self.height_mm, self.thickness_mm),
        )


@dataclass(slots=True, kw_only=True)
class CircleElement(Element):
    """Circulo (^GC)."""

    type: ClassVar[str] = "circle"

    diameter_mm: float = 15.0
    thickness_mm: float = 0.4
    color: Color = Color.BLACK

    def to_zpl(self, ctx: RenderContext) -> list[str]:
        t = max(1, ctx.dots(self.thickness_mm))
        return [
            f"{self._origin(ctx)}^GC{ctx.dots(self.diameter_mm)},{t},{self.color}^FS"
        ]

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        return (self.diameter_mm, self.diameter_mm)


@dataclass(slots=True, kw_only=True)
class ImageElement(Element):
    """Imagem monocromatica embutida no ZPL (^GFA).

    ``source`` guarda um data URL (``data:image/png;base64,...``). A conversao
    para bitmap 1-bit acontece na hora de gerar o ZPL, em ``images.py``.
    """

    type: ClassVar[str] = "image"

    source: str = ""
    width_mm: float = 20.0
    height_mm: float = 20.0
    threshold: int = 128
    dither: bool = False
    invert: bool = False

    def to_zpl(self, ctx: RenderContext) -> list[str]:
        if not self.source:
            return [f"^FXimagem vazia: {sanitize_comment(self.display_name())}^FS"]
        from .images import image_to_graphic_field  # import tardio: Pillow e opcional

        gf = image_to_graphic_field(
            self.source,
            width_dots=ctx.dots(self.width_mm),
            height_dots=ctx.dots(self.height_mm),
            threshold=self.threshold,
            dither=self.dither,
            invert=self.invert,
        )
        return [f"{self._origin(ctx)}{gf}^FS"]

    def size_mm(self, resolution: Resolution | None = None) -> tuple[float, float]:
        return (self.width_mm, self.height_mm)


#: Registro central de tipos. Adicionar um elemento novo = adicionar uma linha.
ELEMENT_TYPES: dict[str, type[Element]] = {
    cls.type: cls
    for cls in (
        TextElement,
        BarcodeElement,
        QrCodeElement,
        DataMatrixElement,
        BoxElement,
        LineElement,
        CircleElement,
        ImageElement,
    )
}
