"""Conversao Label <-> dicionario/JSON.

A serializacao e generica: le as anotacoes de tipo das dataclasses e converte
os valores. Assim, adicionar um campo novo a um elemento nao exige tocar aqui.

O JSON gravado carrega ``schema_version`` para que arquivos antigos possam ser
migrados quando o formato evoluir.
"""

from __future__ import annotations

import json
import types
import typing
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from . import elements as elements_module
from .elements import ELEMENT_TYPES, Element
from .label import Label, PrintSettings

SCHEMA_VERSION = 1


class SerializationError(ValueError):
    """Dados de entrada nao descrevem uma etiqueta valida."""


# ---------------------------------------------------------------------------
# Serializar
# ---------------------------------------------------------------------------
def _value_to_json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _value_to_json(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [_value_to_json(v) for v in value]
    return value


def element_to_dict(element: Element) -> dict[str, Any]:
    data = {f.name: _value_to_json(getattr(element, f.name)) for f in fields(element)}
    data["type"] = element.type  # ClassVar, entao nao vem de fields()
    return data


def label_to_dict(label: Label) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": label.name,
        "width_mm": label.width_mm,
        "height_mm": label.height_mm,
        "dpi": label.dpi,
        "encoding": label.encoding,
        "print_settings": _value_to_json(label.print_settings),
        "elements": [element_to_dict(e) for e in label.elements],
    }


def label_to_json(label: Label, *, indent: int = 2) -> str:
    return json.dumps(label_to_dict(label), indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Desserializar
# ---------------------------------------------------------------------------
def _coerce(value: Any, hint: Any) -> Any:
    """Converte um valor cru de JSON para o tipo anotado no dataclass."""
    if hint is Any or value is None:
        return value

    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        if len(args) == 1:
            return _coerce(value, args[0])
        return value
    if origin in (list, tuple):
        (inner,) = typing.get_args(hint) or (Any,)
        return [_coerce(v, inner) for v in value]

    if isinstance(hint, type):
        if issubclass(hint, Enum):
            return hint(value)
        if hint is bool:
            return bool(value)
        if hint is int:
            return int(value)
        if hint is float:
            return float(value)
        if hint is str:
            return str(value)
    return value


def _build(cls: type, data: dict[str, Any]) -> Any:
    """Instancia uma dataclass a partir de um dict, ignorando chaves extras."""
    hints = typing.get_type_hints(cls, vars(elements_module))
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name in data:
            kwargs[f.name] = _coerce(data[f.name], hints.get(f.name, Any))
    return cls(**kwargs)


def element_from_dict(data: dict[str, Any]) -> Element:
    kind = data.get("type")
    cls = ELEMENT_TYPES.get(kind)
    if cls is None:
        conhecidos = ", ".join(sorted(ELEMENT_TYPES))
        raise SerializationError(
            f"Tipo de elemento desconhecido: {kind!r}. Suportados: {conhecidos}."
        )
    try:
        return _build(cls, data)
    except SerializationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SerializationError(f"Elemento {kind!r} invalido: {exc}") from exc


def label_from_dict(data: dict[str, Any]) -> Label:
    if not isinstance(data, dict):
        raise SerializationError("A etiqueta deve ser um objeto JSON.")

    version = data.get("schema_version", SCHEMA_VERSION)
    if version > SCHEMA_VERSION:
        raise SerializationError(
            f"Arquivo gravado por uma versao mais nova (schema {version}). Atualize o aplicativo."
        )

    label = Label(
        name=str(data.get("name", "Nova etiqueta")),
        width_mm=float(data.get("width_mm", 100.0)),
        height_mm=float(data.get("height_mm", 50.0)),
        dpi=int(data.get("dpi", 203)),
        encoding=str(data.get("encoding", "utf-8")),
        elements=[element_from_dict(e) for e in data.get("elements", [])],
    )
    if isinstance(data.get("print_settings"), dict):
        label.print_settings = _build(PrintSettings, data["print_settings"])
    return label


def label_from_json(raw: str) -> Label:
    try:
        return label_from_dict(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise SerializationError(f"JSON invalido: {exc}") from exc


# ---------------------------------------------------------------------------
# Arquivos
# ---------------------------------------------------------------------------
def save_label(label: Label, path: str | Path) -> Path:
    destino = Path(path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(label_to_json(label), encoding="utf-8")
    return destino


def load_label(path: str | Path) -> Label:
    return label_from_json(Path(path).read_text(encoding="utf-8"))
