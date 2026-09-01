"""Escape de dados de campo (^FD).

Tres caracteres tem significado especial para o parser ZPL e nao podem entrar
crus no ^FD: o prefixo de comando (^), o prefixo de controle (~) e o delimitador
(,) em alguns contextos. Acentos tambem sao um problema classico: mesmo com
^CI28 (UTF-8) o caminho seguro e mandar os bytes em hexadecimal usando ^FH.

A estrategia aqui: so ativamos ^FH quando realmente necessario, mantendo o ZPL
legivel para o usuario na maior parte dos casos.
"""

from __future__ import annotations

#: Caractere de escape hexadecimal declarado pelo ^FH.
HEX_INDICATOR = "_"

#: Caracteres que quebram o parser se enviados crus.
_UNSAFE = frozenset("^~" + HEX_INDICATOR)


def needs_hex_escape(text: str) -> bool:
    """True se o texto contem algo que precisa do modo ^FH."""
    return any(ch in _UNSAFE or ord(ch) > 126 or ord(ch) < 32 for ch in text)


def encode_field_data(text: str, encoding: str = "utf-8") -> tuple[str, bool]:
    r"""Prepara um texto para ir dentro de um ^FD.

    Retorna ``(payload, usa_fh)``. Quando ``usa_fh`` e True o chamador deve
    emitir ``^FH\`` imediatamente antes do ``^FD``.
    """
    if not needs_hex_escape(text):
        return text, False

    out: list[str] = []
    for byte in text.encode(encoding):
        char = chr(byte)
        if 32 <= byte <= 126 and char not in _UNSAFE:
            out.append(char)
        else:
            out.append(f"{HEX_INDICATOR}{byte:02X}")
    return "".join(out), True


def field_data(text: str, encoding: str = "utf-8") -> str:
    """Monta o par ``^FH^FD`` completo (sem o ``^FS`` final)."""
    payload, use_fh = encode_field_data(text, encoding)
    prefix = "^FH\\" if use_fh else ""
    return f"{prefix}^FD{payload}"


def sanitize_comment(text: str) -> str:
    """Deixa um texto seguro para virar comentario ^FX."""
    return "".join(ch for ch in text if ch not in _UNSAFE and ch != "\n")[:60]
