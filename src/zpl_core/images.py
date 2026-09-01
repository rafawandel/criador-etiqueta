"""Conversao de imagens para o campo grafico do ZPL (^GF).

Uma Zebra so imprime preto e branco: cada dot esta ligado ou desligado. O ^GFA
recebe o bitmap 1-bit em hexadecimal, linha a linha, com as linhas completadas
ate fechar um byte.

A escolha entre limiar simples e dithering muda muito o resultado: logotipos
chapados ficam melhores com limiar; fotos, com dithering.
"""

from __future__ import annotations

import base64
import binascii
import io

#: Data URLs maiores que isso viram ZPL grande demais para a memoria da
#: impressora. Barrar cedo da um erro claro em vez de um travamento.
MAX_SOURCE_BYTES = 6 * 1024 * 1024


class ImageConversionError(ValueError):
    """A imagem nao pode ser convertida para bitmap."""


def decode_data_url(source: str) -> bytes:
    """Extrai os bytes de um data URL (ou de base64 puro)."""
    if not source:
        raise ImageConversionError("Nenhuma imagem informada.")
    payload = source.split(",", 1)[1] if source.startswith("data:") else source
    try:
        raw = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ImageConversionError(f"Imagem em base64 invalida: {exc}") from exc
    if len(raw) > MAX_SOURCE_BYTES:
        raise ImageConversionError("Imagem grande demais (limite de 6 MB).")
    return raw


def image_to_bitmap(
    source: str,
    *,
    width_dots: int,
    height_dots: int,
    threshold: int = 128,
    dither: bool = False,
    invert: bool = False,
):
    """Abre a imagem e devolve um objeto PIL 1-bit no tamanho pedido."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise ImageConversionError("Pillow nao esta instalado.") from exc

    width_dots, height_dots = max(1, width_dots), max(1, height_dots)
    try:
        img = Image.open(io.BytesIO(decode_data_url(source)))
    except OSError as exc:
        raise ImageConversionError(f"Formato de imagem nao reconhecido: {exc}") from exc

    # Achatar transparencia sobre branco: o alfa viraria preto solido no ZPL.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fundo = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(fundo, img)

    img = img.convert("L").resize((width_dots, height_dots), Image.LANCZOS)

    if dither:
        bitmap = img.convert("1")  # Floyd-Steinberg, padrao do Pillow
    else:
        limiar = max(0, min(255, threshold))
        bitmap = img.point(lambda p: 255 if p > limiar else 0, mode="1")

    if invert:
        from PIL import ImageOps

        bitmap = ImageOps.invert(bitmap.convert("L")).convert("1")
    return bitmap


def bitmap_to_graphic_field(bitmap) -> str:
    """Bitmap 1-bit -> comando ``^GFA`` completo."""
    width, height = bitmap.size
    bytes_per_row = (width + 7) // 8
    total_bytes = bytes_per_row * height

    # No ZPL, bit 1 = dot impresso (preto). No modo "1" do Pillow, 0 = preto.
    pixels = bitmap.load()
    linhas: list[str] = []
    for y in range(height):
        atual = bytearray(bytes_per_row)
        for x in range(width):
            if pixels[x, y] == 0:
                atual[x // 8] |= 0x80 >> (x % 8)
        linhas.append(atual.hex().upper())

    return f"^GFA,{total_bytes},{total_bytes},{bytes_per_row},{''.join(linhas)}"


def image_to_graphic_field(
    source: str,
    *,
    width_dots: int,
    height_dots: int,
    threshold: int = 128,
    dither: bool = False,
    invert: bool = False,
) -> str:
    """Atalho: data URL -> comando ``^GFA``."""
    bitmap = image_to_bitmap(
        source,
        width_dots=width_dots,
        height_dots=height_dots,
        threshold=threshold,
        dither=dither,
        invert=invert,
    )
    return bitmap_to_graphic_field(bitmap)


def bitmap_to_png(bitmap) -> bytes:
    """Bitmap 1-bit -> PNG, para o editor mostrar exatamente o que sera impresso."""
    buffer = io.BytesIO()
    bitmap.convert("L").save(buffer, format="PNG")
    return buffer.getvalue()
