"""zpl_core -- modelo de etiquetas e geracao de ZPL.

Este pacote nao conhece FastAPI, HTTP nem navegador: e Python puro. Isso mantem
a regra de negocio testavel isoladamente e permite reusar o gerador em outro
contexto (script de lote, integracao com ERP, linha de comando) sem carregar a
aplicacao web junto.

    >>> from zpl_core import Label, TextElement, to_zpl
    >>> etiqueta = Label(width_mm=100, height_mm=50)
    >>> _ = etiqueta.add(TextElement(text="ACME", x_mm=5, y_mm=5, height_mm=6))
    >>> print(to_zpl(etiqueta, comments=False))  # doctest: +ELLIPSIS
    ^XA...^XZ
"""

from .elements import (
    ELEMENT_TYPES,
    BarcodeElement,
    BoxElement,
    CircleElement,
    DataMatrixElement,
    Element,
    ImageElement,
    LineElement,
    QrCodeElement,
    RenderContext,
    TextElement,
)
from .enums import Color, Justification, QrErrorCorrection, Rotation, Symbology
from .label import Label, PrintSettings
from .serialization import (
    SerializationError,
    label_from_dict,
    label_from_json,
    label_to_dict,
    label_to_json,
    load_label,
    save_label,
)
from .units import DEFAULT_DPI, SUPPORTED_DPI, Resolution
from .validation import Issue, Severity, validate
from .zpl_writer import ZplDocument, ZplSegment, ZplWriter, to_zpl

__version__ = "0.1.0"

__all__ = [
    "BarcodeElement",
    "BoxElement",
    "CircleElement",
    "Color",
    "DEFAULT_DPI",
    "DataMatrixElement",
    "ELEMENT_TYPES",
    "Element",
    "ImageElement",
    "Issue",
    "Justification",
    "Label",
    "LineElement",
    "PrintSettings",
    "QrCodeElement",
    "QrErrorCorrection",
    "RenderContext",
    "Resolution",
    "Rotation",
    "SUPPORTED_DPI",
    "SerializationError",
    "Severity",
    "Symbology",
    "TextElement",
    "ZplDocument",
    "ZplSegment",
    "ZplWriter",
    "label_from_dict",
    "label_from_json",
    "label_to_dict",
    "label_to_json",
    "load_label",
    "save_label",
    "to_zpl",
    "validate",
]
