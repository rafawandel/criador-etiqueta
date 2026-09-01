"""Render de codigos de barras para o *preview* do editor.

Isto NAO gera o codigo impresso -- quem imprime e a impressora, a partir do ZPL.
Aqui produzimos apenas a imagem que o usuario ve na tela enquanto monta a
etiqueta, para que ele avalie tamanho e proporcao antes de gastar ribbon.

Toda falha vira uma imagem de aviso legivel em vez de uma excecao: no editor,
um dado incompleto e o estado normal enquanto a pessoa digita.
"""

from __future__ import annotations

import io
from functools import lru_cache

from .enums import Symbology

#: Simbologias do nosso dominio -> nomes usados pela biblioteca python-barcode.
_PYBARCODE_NAMES: dict[Symbology, str] = {
    Symbology.CODE128: "code128",
    Symbology.CODE39: "code39",
    Symbology.EAN13: "ean13",
    Symbology.EAN8: "ean8",
    Symbology.UPCA: "upca",
    Symbology.ITF: "itf",
}

#: Simbologias que o ZPL imprime mas para as quais nao temos render local.
#: O preview mostra um marcador com as proporcoes corretas.
_PREVIEW_UNSUPPORTED = {Symbology.CODE93}


@lru_cache(maxsize=512)
def render_barcode_png(
    symbology: str,
    data: str,
    *,
    width_px: int = 400,
    height_px: int = 120,
    show_text: bool = True,
    bar_height_mm: float = 10.0,
) -> bytes:
    """PNG de um codigo de barras 1D. Resultado e cacheado por parametros.

    ``bar_height_mm`` e a altura das *barras*, sem a linha de interpretacao.
    Ela define a proporcao entre barras e numeros na imagem gerada -- sem isso
    o texto sairia sempre do mesmo tamanho e um codigo alto ficaria com os
    numeros minusculos (e um baixo, com numeros gigantes).
    """
    try:
        symbol = Symbology(symbology)
    except ValueError:
        return _placeholder_png(width_px, height_px, f"simbologia {symbology}?")

    if symbol in _PREVIEW_UNSUPPORTED or not data.strip():
        rotulo = data.strip() or "sem dados"
        return _placeholder_png(width_px, height_px, rotulo)

    try:
        import barcode
        from barcode.writer import ImageWriter

        cls = barcode.get_barcode_class(_PYBARCODE_NAMES[symbol])
        # python-barcode calcula o digito verificador de EAN/UPC, entao
        # entregamos os digitos sem ele.
        payload = _trim_check_digit(symbol, data.strip())
        writer_options = {
            "module_width": 0.2,
            "module_height": max(2.0, bar_height_mm),
            "quiet_zone": 1.0,
            "write_text": show_text,
            "font_size": 8,          # ~2.8 mm, proximo da fonte que a Zebra usa
            "text_distance": 1.0,
            "dpi": 300,
        }
        buffer = io.BytesIO()
        cls(payload, writer=ImageWriter()).write(buffer, writer_options)
        return _fit(buffer.getvalue(), width_px, height_px)
    except Exception as exc:  # noqa: BLE001 - preview nunca derruba o editor
        # A mensagem da biblioteca vem em ingles; ela vai para o subtitulo, como
        # detalhe tecnico. O rotulo principal fica no idioma da interface -- e a
        # explicacao completa, em portugues, ja aparece no painel de avisos.
        return _placeholder_png(
            width_px, height_px, "dados invalidos", subtitle=_short(exc)
        )


@lru_cache(maxsize=512)
def render_qrcode_png(data: str, *, size_px: int = 200, error_correction: str = "M") -> bytes:
    """PNG de um QR Code."""
    if not data:
        return _placeholder_png(size_px, size_px, "sem dados")
    try:
        import qrcode
        from qrcode.constants import (
            ERROR_CORRECT_H,
            ERROR_CORRECT_L,
            ERROR_CORRECT_M,
            ERROR_CORRECT_Q,
        )

        levels = {
            "L": ERROR_CORRECT_L,
            "M": ERROR_CORRECT_M,
            "Q": ERROR_CORRECT_Q,
            "H": ERROR_CORRECT_H,
        }
        qr = qrcode.QRCode(
            error_correction=levels.get(error_correction.upper(), ERROR_CORRECT_M),
            box_size=10,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)
        buffer = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
        return _fit(buffer.getvalue(), size_px, size_px)
    except Exception as exc:  # noqa: BLE001
        return _placeholder_png(size_px, size_px, _short(exc))


@lru_cache(maxsize=256)
def render_datamatrix_png(data: str, *, size_px: int = 200) -> bytes:
    """Marcador de DataMatrix.

    Nao ha encoder DataMatrix puro-Python confiavel sem dependencia nativa. O
    ZPL gerado esta correto e imprime na Zebra; aqui mostramos apenas a area
    ocupada, sinalizada como aproximada para nao enganar o usuario.
    """
    return _placeholder_png(size_px, size_px, "DataMatrix", subtitle="preview aproximado")


# ---------------------------------------------------------------------------
def _trim_check_digit(symbol: Symbology, data: str) -> str:
    """Remove o digito verificador quando a biblioteca vai recalcula-lo."""
    tamanhos = {Symbology.EAN13: 13, Symbology.EAN8: 8, Symbology.UPCA: 12}
    completo = tamanhos.get(symbol)
    if completo and len(data) == completo:
        return data[:-1]
    return data


def _fit(png: bytes, width: int, height: int) -> bytes:
    """Reescala mantendo as barras nitidas (sem suavizacao)."""
    from PIL import Image

    with Image.open(io.BytesIO(png)) as img:
        resized = img.convert("L").resize((max(1, width), max(1, height)), Image.NEAREST)
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG")
        return buffer.getvalue()


def _placeholder_png(width: int, height: int, message: str, subtitle: str = "") -> bytes:
    """Retangulo tracejado com a mensagem -- ocupa o mesmo espaco do codigo."""
    from PIL import Image, ImageDraw

    width, height = max(24, width), max(24, height)
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width - 1, height - 1], outline=120)

    # Hachura diagonal leve, para o placeholder nao ser confundido com o codigo.
    for x in range(-height, width, 10):
        draw.line([(x, height), (x + height, 0)], fill=225)

    texto = message if len(message) <= 28 else message[:27] + "…"
    draw.text((6, height // 2 - 10), texto, fill=60)
    if subtitle:
        draw.text((6, height // 2 + 2), subtitle, fill=140)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _short(exc: Exception) -> str:
    texto = str(exc).strip() or exc.__class__.__name__
    return texto.splitlines()[0][:60]
