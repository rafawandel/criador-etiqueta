"""Traducao do modelo para ZPL -- a unica fonte da verdade do codigo gerado.

O writer devolve um ``ZplDocument`` em vez de uma string solta porque o editor
precisa saber **qual trecho do ZPL veio de qual elemento**. E isso que permite
destacar o codigo correspondente quando o usuario seleciona um objeto no canvas
(e vice-versa), transformando o painel de ZPL em uma ferramenta de aprendizado
em vez de um bloco de texto opaco.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .elements import Element
from .escaping import sanitize_comment
from .label import Label

#: Encoding do ZPL -> parametro do comando ^CI.
_CI_BY_ENCODING = {"utf-8": 28, "cp850": 13, "cp1252": 27, "ascii": 0}


@dataclass(slots=True, frozen=True)
class ZplSegment:
    """De que elemento veio um trecho do documento (linhas 0-indexadas)."""

    element_id: str
    start_line: int
    end_line: int


@dataclass(slots=True)
class ZplDocument:
    """ZPL gerado + o mapa que liga cada linha ao elemento de origem."""

    lines: list[str] = field(default_factory=list)
    segments: list[ZplSegment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def compact(self) -> str:
        """Versao sem quebras de linha, para enviar a impressora."""
        return "".join(line for line in self.lines if not line.startswith("^FX"))

    def segment_for(self, element_id: str) -> ZplSegment | None:
        return next((s for s in self.segments if s.element_id == element_id), None)

    def __str__(self) -> str:  # pragma: no cover - conveniencia
        return self.text


class ZplWriter:
    """Converte uma ``Label`` em ``ZplDocument``.

    Parameters
    ----------
    include_comments:
        Emite ``^FX`` com o nome de cada elemento. Otimo enquanto o usuario esta
        aprendendo, ruido puro em producao -- por isso e opcional.
    """

    def __init__(self, *, include_comments: bool = True) -> None:
        self.include_comments = include_comments

    def write(self, label: Label, data: dict[str, Any] | None = None) -> ZplDocument:
        source = label.merged(data) if data else label
        ctx = source.render_context()
        doc = ZplDocument()

        doc.lines.extend(self._header(source))

        for element in source.visible_elements():
            start = len(doc.lines)
            if self.include_comments:
                doc.lines.append(f"^FX{sanitize_comment(element.display_name())}^FS")
            doc.lines.extend(self._safe_element_zpl(element, ctx))
            doc.segments.append(ZplSegment(element.id, start, len(doc.lines) - 1))

        doc.lines.extend(self._footer(source))
        return doc

    # -- partes do documento ----------------------------------------------
    def _header(self, label: Label) -> list[str]:
        settings = label.print_settings
        lines = ["^XA"]

        ci = _CI_BY_ENCODING.get(label.encoding.lower())
        if ci is not None:
            lines.append(f"^CI{ci}")

        lines.append(f"^PW{label.width_dots}")
        lines.append(f"^LL{label.height_dots}")
        lines.append(f"^LH{settings.home_x_dots},{settings.home_y_dots}")

        if settings.darkness is not None:
            lines.append(f"^MD{settings.darkness}")
        if settings.speed_ips is not None:
            lines.append(f"^PR{settings.speed_ips}")
        if settings.invert_all:
            lines.append("^POI")

        return lines

    def _footer(self, label: Label) -> list[str]:
        copies = max(1, label.print_settings.copies)
        lines: list[str] = []
        if copies > 1:
            pause = "Y" if label.print_settings.pause_between else "N"
            lines.append(f"^PQ{copies},0,0,{pause}")
        lines.append("^XZ")
        return lines

    def _safe_element_zpl(self, element: Element, ctx) -> list[str]:
        """Um elemento quebrado nao pode derrubar a etiqueta inteira.

        No editor o usuario digita valores invalidos o tempo todo (um dado que
        ainda nao cabe na simbologia, uma imagem meio carregada). Preferimos
        marcar o problema no proprio ZPL e seguir gerando o resto.
        """
        try:
            return element.to_zpl(ctx)
        except Exception as exc:  # noqa: BLE001 - resiliencia deliberada
            return [f"^FXerro em {sanitize_comment(element.display_name())}: "
                    f"{sanitize_comment(str(exc))}^FS"]


def to_zpl(label: Label, data: dict[str, Any] | None = None, *, comments: bool = True) -> str:
    """Atalho para quem so quer a string."""
    return ZplWriter(include_comments=comments).write(label, data).text
