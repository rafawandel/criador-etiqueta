"""Catalogo de elementos: a ponte entre o modelo Python e a interface.

O editor **nao** tem a lista de campos escrita em JavaScript. Ele pede este
catalogo ao iniciar e monta a paleta e o painel de propriedades a partir dele.

A consequencia pratica: para suportar um objeto ZPL novo basta (1) criar a
dataclass em ``zpl_core.elements`` e (2) descreve-la aqui. Nenhuma linha de
JavaScript precisa mudar -- que e exatamente o requisito de "qualquer objeto
que o ZPL aceita".

Este modulo vive na camada de aplicacao, e nao em ``zpl_core``, porque rotulo,
icone e faixa de valores sao decisoes de interface, nao de dominio.
"""

from __future__ import annotations

from typing import Any

from zpl_core.elements import ELEMENT_TYPES
from zpl_core.enums import Color, Justification, QrErrorCorrection, Rotation, Symbology
from zpl_core.serialization import element_to_dict
from zpl_core.units import SUPPORTED_DPI


def _opts(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"value": v, "label": label} for v, label in pairs]


ROTATION_OPTIONS = _opts(
    [
        (Rotation.NORMAL, "0 graus"),
        (Rotation.ROTATED, "90 graus"),
        (Rotation.INVERTED, "180 graus"),
        (Rotation.BOTTOM_UP, "270 graus"),
    ]
)

SYMBOLOGY_OPTIONS = _opts(
    [
        (Symbology.CODE128, "Code 128 (uso geral)"),
        (Symbology.CODE39, "Code 39"),
        (Symbology.CODE93, "Code 93"),
        (Symbology.EAN13, "EAN-13 (varejo)"),
        (Symbology.EAN8, "EAN-8"),
        (Symbology.UPCA, "UPC-A"),
        (Symbology.ITF, "ITF (caixa/pallet)"),
    ]
)

COLOR_OPTIONS = _opts([(Color.BLACK, "Preto"), (Color.WHITE, "Branco")])

JUSTIFICATION_OPTIONS = _opts(
    [
        (Justification.LEFT, "Esquerda"),
        (Justification.CENTER, "Centro"),
        (Justification.RIGHT, "Direita"),
        (Justification.JUSTIFIED, "Justificado"),
    ]
)

ECC_OPTIONS = _opts(
    [
        (QrErrorCorrection.LOW, "Baixa (7%) - mais dados"),
        (QrErrorCorrection.MEDIUM, "Media (15%)"),
        (QrErrorCorrection.QUARTILE, "Alta (25%)"),
        (QrErrorCorrection.HIGH, "Maxima (30%) - resiste a sujeira"),
    ]
)

FONT_OPTIONS = _opts(
    [
        ("0", "Escalavel (padrao)"),
        ("A", "A - 9x5 fixa"),
        ("B", "B - 11x7 fixa"),
        ("D", "D - 18x10 fixa"),
        ("E", "E - OCR-B"),
        ("F", "F - 26x13 fixa"),
        ("G", "G - 60x40 fixa"),
        ("H", "H - OCR-A"),
    ]
)


def _num(
    name: str,
    label: str,
    *,
    unit: str = "mm",
    min: float = 0,
    max: float = 500,
    step: float = 0.5,
    group: str = "Geral",
    help: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "widget": "number",
        "unit": unit,
        "min": min,
        "max": max,
        "step": step,
        "group": group,
        "help": help,
    }


def _select(name: str, label: str, options: list[dict[str, str]], *, group: str = "Geral",
            help: str = "") -> dict[str, Any]:
    return {"name": name, "label": label, "widget": "select", "options": options,
            "group": group, "help": help}


def _switch(name: str, label: str, *, group: str = "Geral", help: str = "") -> dict[str, Any]:
    return {"name": name, "label": label, "widget": "switch", "group": group, "help": help}


def _text(name: str, label: str, *, widget: str = "text", group: str = "Conteudo",
          help: str = "") -> dict[str, Any]:
    return {"name": name, "label": label, "widget": widget, "group": group, "help": help}


def _resize(
    *,
    width: str | None = None,
    height: str | None = None,
    uniform: str | None = None,
    integer: bool = False,
) -> dict[str, Any]:
    """Descreve o que as alcas de redimensionamento alteram.

    ``width``/``height`` apontam para campos em mm; ``uniform`` para um campo
    que escala nos dois eixos (diametro, ampliacao). ``integer`` marca campos
    que so aceitam passos inteiros -- caso do modulo de QR e DataMatrix, em que
    valores fracionarios nao existem na impressora.
    """
    return {"width": width, "height": height, "uniform": uniform, "integer": integer}


#: Campos que todo elemento tem. Renderizados no topo do painel.
COMMON_FIELDS: list[dict[str, Any]] = [
    _text("name", "Nome do campo", group="Identificacao",
          help="So para voce se localizar; vira comentario ^FX no ZPL."),
    _num("x_mm", "X", group="Posicao", step=0.5, help="Distancia da borda esquerda."),
    _num("y_mm", "Y", group="Posicao", step=0.5, help="Distancia da borda superior."),
    _select("rotation", "Rotacao", ROTATION_OPTIONS, group="Posicao"),
]


#: Definicao de cada tipo: como aparece na paleta e o que da para editar.
ELEMENT_CATALOG: list[dict[str, Any]] = [
    {
        "type": "text",
        "resize": _resize(width="block_width_mm", height="height_mm"),
        "label": "Texto",
        "icon": "T",
        "category": "Conteudo",
        "description": "Texto com fonte da impressora. Aceita campos variaveis {{campo}}.",
        "zpl": "^A / ^FD",
        "fields": [
            _text("text", "Texto", widget="textarea",
                  help="Use {{nome}} para criar um campo variavel preenchido na impressao."),
            _select("font", "Fonte", FONT_OPTIONS, group="Aparencia"),
            _num("height_mm", "Altura da fonte", min=0.5, max=100, step=0.5, group="Aparencia"),
            _num("width_mm", "Largura do caractere", min=0, max=100, step=0.5, group="Aparencia",
                 help="0 = proporcional a altura."),
            _switch("reverse", "Inverter (branco no preto)", group="Aparencia"),
            _num("block_width_mm", "Largura do bloco", min=0, max=300, group="Quebra de linha",
                 help="Maior que 0 ativa a quebra automatica (^FB)."),
            _num("block_max_lines", "Maximo de linhas", unit="", min=1, max=20, step=1,
                 group="Quebra de linha"),
            _num("block_line_spacing_mm", "Espaco entre linhas", min=0, max=50,
                 group="Quebra de linha"),
            _select("justification", "Alinhamento", JUSTIFICATION_OPTIONS,
                    group="Quebra de linha"),
        ],
    },
    {
        "type": "barcode",
        "resize": _resize(height="height_mm"),
        "label": "Codigo de barras",
        "icon": "|||",
        "category": "Codigos",
        "description": "Codigo linear. A impressora desenha as barras a partir dos dados.",
        "zpl": "^BC / ^B3 / ^BE ...",
        "fields": [
            _text("data", "Dados"),
            _select("symbology", "Simbologia", SYMBOLOGY_OPTIONS, group="Conteudo",
                    help="Code 128 aceita letras e numeros; EAN/UPC so digitos."),
            _num("height_mm", "Altura das barras", min=2, max=150, group="Aparencia"),
            _num("module_width_dots", "Largura da barra estreita", unit="dots", min=1, max=10,
                 step=1, group="Aparencia",
                 help="Abaixo de 2 dots a leitura fica instavel."),
            _num("wide_ratio", "Relacao larga/estreita", unit="x", min=2, max=3, step=0.1,
                 group="Aparencia"),
            _switch("show_text", "Mostrar numeros", group="Aparencia"),
            _switch("text_above", "Numeros acima das barras", group="Aparencia"),
            _switch("check_digit", "Digito verificador", group="Aparencia"),
        ],
    },
    {
        "type": "qrcode",
        "resize": _resize(uniform="magnification", integer=True),
        "label": "QR Code",
        "icon": "QR",
        "category": "Codigos",
        "description": "Codigo 2D. Bom para URLs e identificadores lidos por celular.",
        "zpl": "^BQ",
        "fields": [
            _text("data", "Dados", widget="textarea"),
            _num("magnification", "Ampliacao", unit="x", min=1, max=10, step=1,
                 group="Aparencia", help="Tamanho de cada modulo em dots."),
            _select("error_correction", "Correcao de erro", ECC_OPTIONS, group="Aparencia"),
        ],
    },
    {
        "type": "datamatrix",
        "resize": _resize(uniform="module_size_dots", integer=True),
        "label": "DataMatrix",
        "icon": "DM",
        "category": "Codigos",
        "description": "Codigo 2D compacto, comum em peca pequena e area medica.",
        "zpl": "^BX",
        "fields": [
            _text("data", "Dados", widget="textarea"),
            _num("module_size_dots", "Tamanho do modulo", unit="dots", min=2, max=20, step=1,
                 group="Aparencia"),
        ],
    },
    {
        "type": "box",
        "resize": _resize(width="width_mm", height="height_mm"),
        "label": "Retangulo",
        "icon": "[]",
        "category": "Formas",
        "description": "Moldura ou area preenchida. Espessura grande vira bloco solido.",
        "zpl": "^GB",
        "fields": [
            _num("width_mm", "Largura", min=0.1, max=500, group="Tamanho"),
            _num("height_mm", "Altura", min=0.1, max=500, group="Tamanho"),
            _num("thickness_mm", "Espessura da linha", min=0.1, max=100, step=0.1,
                 group="Aparencia"),
            _select("color", "Cor", COLOR_OPTIONS, group="Aparencia"),
            _num("rounding", "Arredondamento", unit="", min=0, max=8, step=1, group="Aparencia"),
        ],
    },
    {
        "type": "line",
        "resize": _resize(width="width_mm", height="height_mm"),
        "label": "Linha",
        "icon": "/",
        "category": "Formas",
        "description": "Divisoria horizontal, vertical ou diagonal.",
        "zpl": "^GB / ^GD",
        "fields": [
            _num("width_mm", "Comprimento horizontal", min=0, max=500, group="Tamanho"),
            _num("height_mm", "Comprimento vertical", min=0, max=500, group="Tamanho",
                 help="Deixe 0 para linha horizontal."),
            _num("thickness_mm", "Espessura", min=0.1, max=50, step=0.1, group="Aparencia"),
            _select("color", "Cor", COLOR_OPTIONS, group="Aparencia"),
            _switch("diagonal", "Diagonal", group="Aparencia"),
            _switch("lean_right", "Inclinar para a direita", group="Aparencia"),
        ],
    },
    {
        "type": "circle",
        "resize": _resize(uniform="diameter_mm"),
        "label": "Circulo",
        "icon": "O",
        "category": "Formas",
        "description": "Circulo vazado ou preenchido.",
        "zpl": "^GC",
        "fields": [
            _num("diameter_mm", "Diametro", min=0.5, max=500, group="Tamanho"),
            _num("thickness_mm", "Espessura", min=0.1, max=100, step=0.1, group="Aparencia"),
            _select("color", "Cor", COLOR_OPTIONS, group="Aparencia"),
        ],
    },
    {
        "type": "image",
        "resize": _resize(width="width_mm", height="height_mm"),
        "label": "Imagem",
        "icon": "IMG",
        "category": "Conteudo",
        "description": "Logotipo convertido para preto e branco e embutido no ZPL.",
        "zpl": "^GFA",
        "fields": [
            _text("source", "Arquivo", widget="image"),
            _num("width_mm", "Largura", min=1, max=500, group="Tamanho"),
            _num("height_mm", "Altura", min=1, max=500, group="Tamanho"),
            _num("threshold", "Limiar preto/branco", unit="", min=0, max=255, step=1,
                 group="Conversao", help="Menor = mais preto."),
            _switch("dither", "Dithering", group="Conversao",
                    help="Ligue para fotos, desligue para logotipos chapados."),
            _switch("invert", "Inverter", group="Conversao"),
        ],
    },
]


def build_catalog() -> dict[str, Any]:
    """Payload completo consumido pelo editor na inicializacao."""
    tipos = []
    for entry in ELEMENT_CATALOG:
        cls = ELEMENT_TYPES[entry["type"]]
        tipos.append({**entry, "defaults": element_to_dict(cls())})

    return {
        "elements": tipos,
        "common_fields": COMMON_FIELDS,
        "supported_dpi": list(SUPPORTED_DPI),
        "categories": list(dict.fromkeys(e["category"] for e in ELEMENT_CATALOG)),
    }
