"""Validacao da etiqueta.

Regra de ouro: **nunca bloquear o usuario**. A validacao devolve uma lista de
achados e o editor decide como mostra-los (badge no elemento, lista lateral).
Uma etiqueta com problemas continua gerando ZPL -- quem decide se vale imprimir
e a pessoa, nao o sistema.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .elements import BarcodeElement, Element, QrCodeElement, TextElement
from .enums import Symbology
from .label import PLACEHOLDER_RE, Label


class Severity(StrEnum):
    ERROR = "error"      # nao vai imprimir como o usuario espera
    WARNING = "warning"  # vai imprimir, mas provavelmente nao e o desejado
    INFO = "info"        # observacao util


@dataclass(slots=True, frozen=True)
class Issue:
    severity: Severity
    message: str
    element_id: str | None = None
    hint: str | None = None


# Comprimentos exigidos por simbologia (sem contar o digito verificador
# calculado pela impressora).
_FIXED_LENGTHS: dict[Symbology, tuple[int, ...]] = {
    Symbology.EAN13: (12, 13),
    Symbology.EAN8: (7, 8),
    Symbology.UPCA: (11, 12),
}

_CODE39_CHARSET = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-. $/+%")

#: Abaixo disso a barra estreita fica menor que a resolucao util da cabeca.
_MIN_MODULE_DOTS = 2
#: Fontes menores que isso ficam ilegiveis em 203 dpi.
_MIN_TEXT_HEIGHT_MM = 1.6


def validate(label: Label) -> list[Issue]:
    """Roda todas as checagens e devolve os achados ordenados por gravidade."""
    issues: list[Issue] = []

    if label.width_mm <= 0 or label.height_mm <= 0:
        issues.append(Issue(Severity.ERROR, "Dimensoes da etiqueta devem ser maiores que zero."))
    if not label.elements:
        issues.append(Issue(Severity.INFO, "A etiqueta esta vazia. Arraste um objeto da paleta."))

    for element in label.elements:
        issues.extend(_check_bounds(element, label))
        issues.extend(_check_element(element, label))

    placeholders = label.placeholders()
    if placeholders:
        nomes = ", ".join(sorted(placeholders))
        issues.append(
            Issue(
                Severity.INFO,
                f"Campos variaveis nesta etiqueta: {nomes}.",
                hint="Preencha os valores na hora de imprimir ou envie um lote de dados.",
            )
        )

    order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return sorted(issues, key=lambda i: order[i.severity])


# ---------------------------------------------------------------------------
def _check_bounds(element: Element, label: Label) -> list[Issue]:
    if not element.visible:
        return []

    x1, y1, x2, y2 = element.bounds_mm(label.resolution)
    name = element.display_name()

    if x1 < 0 or y1 < 0:
        return [
            Issue(
                Severity.ERROR,
                f'"{name}" esta fora da etiqueta (posicao negativa).',
                element.id,
                hint="A origem do ZPL e o canto superior esquerdo.",
            )
        ]

    # Tolerancia de 0.5 mm: as estimativas de largura de texto e codigo de
    # barras sao aproximadas, entao margem exata geraria falso positivo.
    if x2 > label.width_mm + 0.5 or y2 > label.height_mm + 0.5:
        return [
            Issue(
                Severity.WARNING,
                f'"{name}" pode ultrapassar a borda da etiqueta.',
                element.id,
                hint=f"Area util: {label.width_mm:g} x {label.height_mm:g} mm.",
            )
        ]
    return []


def _check_element(element: Element, label: Label) -> list[Issue]:
    match element:
        case BarcodeElement():
            return _check_barcode(element, label)
        case TextElement():
            return _check_text(element)
        case QrCodeElement():
            return _check_qrcode(element)
        case _:
            return []


def _check_barcode(el: BarcodeElement, label: Label) -> list[Issue]:
    issues: list[Issue] = []
    name = el.display_name()
    # Placeholders nao podem ser validados como conteudo final.
    is_template = bool(PLACEHOLDER_RE.search(el.data))

    if not el.data.strip():
        issues.append(Issue(Severity.ERROR, f'"{name}" esta sem dados.', el.id))
        return issues

    if not is_template:
        expected = _FIXED_LENGTHS.get(el.symbology)
        digits = el.data.strip()

        if expected is not None:
            if not digits.isdigit():
                issues.append(
                    Issue(Severity.ERROR, f'"{name}" ({el.symbology}) aceita apenas digitos.', el.id)
                )
            elif len(digits) not in expected:
                esperado = " ou ".join(str(n) for n in expected)
                issues.append(
                    Issue(
                        Severity.ERROR,
                        f'"{name}" ({el.symbology}) precisa de {esperado} digitos, tem {len(digits)}.',
                        el.id,
                    )
                )
        elif el.symbology is Symbology.ITF and len(digits) % 2 != 0:
            issues.append(
                Issue(
                    Severity.ERROR,
                    f'"{name}" (ITF) exige quantidade par de digitos.',
                    el.id,
                    hint="Complete com um zero a esquerda.",
                )
            )
        elif el.symbology is Symbology.CODE39:
            invalidos = sorted(set(el.data.upper()) - _CODE39_CHARSET)
            if invalidos:
                issues.append(
                    Issue(
                        Severity.ERROR,
                        f'"{name}" (Code 39) nao aceita: {" ".join(invalidos)}.',
                        el.id,
                        hint="Code 128 aceita o conjunto completo ASCII.",
                    )
                )

    if el.module_width_dots < _MIN_MODULE_DOTS:
        issues.append(
            Issue(
                Severity.WARNING,
                f'"{name}" tem barras muito finas para leitura confiavel.',
                el.id,
                hint=f"Use largura de modulo >= {_MIN_MODULE_DOTS} dots.",
            )
        )

    if el.height_mm < 5:
        issues.append(
            Issue(Severity.WARNING, f'"{name}" esta muito baixo; leitores podem falhar.', el.id)
        )

    return issues


def _check_text(el: TextElement) -> list[Issue]:
    issues: list[Issue] = []
    name = el.display_name()

    if not el.text.strip():
        issues.append(Issue(Severity.WARNING, f'"{name}" esta sem conteudo.', el.id))
    if el.height_mm < _MIN_TEXT_HEIGHT_MM:
        issues.append(
            Issue(
                Severity.WARNING,
                f'"{name}" tem fonte muito pequena ({el.height_mm:g} mm).',
                el.id,
                hint=f"Abaixo de {_MIN_TEXT_HEIGHT_MM} mm a impressao fica ilegivel.",
            )
        )
    if el.block_width_mm > 0 and el.block_max_lines < 1:
        issues.append(Issue(Severity.ERROR, f'"{name}": bloco precisa de ao menos 1 linha.', el.id))
    return issues


def _check_qrcode(el: QrCodeElement) -> list[Issue]:
    issues: list[Issue] = []
    name = el.display_name()

    if not el.data.strip():
        issues.append(Issue(Severity.ERROR, f'"{name}" esta sem dados.', el.id))
    if el.magnification < 3:
        issues.append(
            Issue(
                Severity.WARNING,
                f'"{name}" tem modulos pequenos demais para leitura por celular.',
                el.id,
                hint="Ampliacao 4 ou maior costuma funcionar bem em 203 dpi.",
            )
        )
    if len(el.data) > 300:
        issues.append(
            Issue(
                Severity.WARNING,
                f'"{name}" tem muitos dados; o codigo fica denso.',
                el.id,
                hint="Considere gravar so uma URL curta ou um identificador.",
            )
        )
    return issues
