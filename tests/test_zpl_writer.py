"""O gerador de ZPL é o coração do sistema: se ele erra, a etiqueta sai errada
e o prejuízo é físico (ribbon, mídia, tempo de máquina parada). Estes testes
fixam o formato dos comandos que enviamos à impressora.
"""

import pytest

from zpl_core import (
    BarcodeElement,
    BoxElement,
    CircleElement,
    Label,
    LineElement,
    QrCodeElement,
    Rotation,
    Symbology,
    TextElement,
    ZplWriter,
    to_zpl,
)


@pytest.fixture
def etiqueta() -> Label:
    return Label(name="Teste", width_mm=100, height_mm=50, dpi=203)


def linhas_de(label: Label) -> list[str]:
    return ZplWriter(include_comments=False).write(label).lines


# ---------------------------------------------------------------------------
# Estrutura do documento
# ---------------------------------------------------------------------------
def test_documento_abre_e_fecha_corretamente(etiqueta):
    linhas = linhas_de(etiqueta)
    assert linhas[0] == "^XA"
    assert linhas[-1] == "^XZ"


def test_dimensoes_viram_dots(etiqueta):
    # 100 mm a 203 dpi = 799 dots (100 * 203 / 25.4)
    linhas = linhas_de(etiqueta)
    assert "^PW799" in linhas
    assert "^LL400" in linhas


def test_dpi_maior_gera_mais_dots():
    largura_203 = Label(width_mm=100, dpi=203).width_dots
    largura_300 = Label(width_mm=100, dpi=300).width_dots
    assert largura_300 > largura_203 == 799


def test_quantidade_so_aparece_quando_maior_que_um(etiqueta):
    assert not any(l.startswith("^PQ") for l in linhas_de(etiqueta))

    etiqueta.print_settings.copies = 5
    assert "^PQ5,0,0,N" in linhas_de(etiqueta)


def test_parametros_de_impressao_omitidos_quando_nulos(etiqueta):
    """Sem valor definido, a configuração da impressora deve prevalecer."""
    linhas = linhas_de(etiqueta)
    assert not any(l.startswith("^MD") for l in linhas)
    assert not any(l.startswith("^PR") for l in linhas)

    etiqueta.print_settings.darkness = 12
    etiqueta.print_settings.speed_ips = 4
    linhas = linhas_de(etiqueta)
    assert "^MD12" in linhas
    assert "^PR4" in linhas


# ---------------------------------------------------------------------------
# Elementos
# ---------------------------------------------------------------------------
def test_texto_simples(etiqueta):
    etiqueta.add(TextElement(text="ACME", x_mm=5, y_mm=10, height_mm=4))
    assert "^FO40,80^A0N,32,0^FDACME^FS" in linhas_de(etiqueta)


def test_texto_com_bloco_emite_fb(etiqueta):
    etiqueta.add(
        TextElement(text="linha longa", block_width_mm=40, block_max_lines=3, height_mm=3)
    )
    linha = next(l for l in linhas_de(etiqueta) if "^FB" in l)
    assert "^FB320,3," in linha


def test_texto_acentuado_usa_hex_com_fh(etiqueta):
    """Acento cru quebra a impressão; o caminho seguro é ^FH com hexadecimal."""
    etiqueta.add(TextElement(text="Ação"))
    linha = next(l for l in linhas_de(etiqueta) if "^FD" in l)
    assert "^FH\\" in linha
    assert "A_C3_A7_C3_A3o" in linha


def test_caractere_de_controle_e_escapado(etiqueta):
    etiqueta.add(TextElement(text="A^B~C"))
    linha = next(l for l in linhas_de(etiqueta) if "^FD" in l)
    # O ^ e o ~ do conteúdo não podem chegar crus ao parser da impressora.
    assert "^FDA_5EB_7EC^FS" in linha


def test_encoding_define_o_comando_ci(etiqueta):
    assert "^CI28" in linhas_de(etiqueta)
    etiqueta.encoding = "cp850"
    assert "^CI13" in linhas_de(etiqueta)


@pytest.mark.parametrize(
    "simbologia,prefixo",
    [
        (Symbology.CODE128, "^BCN"),
        (Symbology.CODE39, "^B3N"),
        (Symbology.EAN13, "^BEN"),
        (Symbology.EAN8, "^B8N"),
        (Symbology.UPCA, "^BUN"),
        (Symbology.ITF, "^B2N"),
        (Symbology.CODE93, "^BAN"),
    ],
)
def test_cada_simbologia_usa_seu_comando(etiqueta, simbologia, prefixo):
    etiqueta.add(BarcodeElement(symbology=simbologia, data="12345678"))
    linha = next(l for l in linhas_de(etiqueta) if "^BY" in l)
    assert prefixo in linha


def test_barcode_emite_by_antes_do_comando(etiqueta):
    """^BY precisa vir antes: ele configura a largura das barras seguintes."""
    etiqueta.add(BarcodeElement(module_width_dots=3, wide_ratio=2.5, height_mm=10))
    linha = next(l for l in linhas_de(etiqueta) if "^BY" in l)
    assert linha.index("^BY") < linha.index("^BC")
    assert "^BY3,2.5,80" in linha


def test_qrcode_carrega_correcao_no_campo_de_dados(etiqueta):
    etiqueta.add(QrCodeElement(data="ABC", error_correction="H", magnification=6))
    linha = next(l for l in linhas_de(etiqueta) if "^BQ" in l)
    assert "^BQN,2,6,H" in linha
    assert "^FDHA,ABC^FS" in linha


def test_qrcode_limita_ampliacao(etiqueta):
    etiqueta.add(QrCodeElement(magnification=99))
    assert "^BQN,2,10," in next(l for l in linhas_de(etiqueta) if "^BQ" in l)


def test_formas_geram_comandos_graficos(etiqueta):
    etiqueta.add(BoxElement(x_mm=1, y_mm=1, width_mm=10, height_mm=5, thickness_mm=0.5))
    etiqueta.add(CircleElement(diameter_mm=8))
    etiqueta.add(LineElement(width_mm=20, height_mm=0, diagonal=False))

    linhas = linhas_de(etiqueta)
    assert any("^GB" in l for l in linhas)
    assert any("^GC" in l for l in linhas)


def test_linha_diagonal_usa_gd(etiqueta):
    etiqueta.add(LineElement(width_mm=20, height_mm=10, diagonal=True, lean_right=False))
    assert "^GD" in next(l for l in linhas_de(etiqueta) if "^GD" in l)


def test_espessura_nunca_zera(etiqueta):
    """0.01 mm arredondaria para 0 dots e a forma sumiria da impressão."""
    etiqueta.add(BoxElement(thickness_mm=0.01))
    assert ",1,B," in next(l for l in linhas_de(etiqueta) if "^GB" in l)


def test_rotacao_entra_em_todos_os_comandos(etiqueta):
    etiqueta.add(TextElement(text="X", rotation=Rotation.ROTATED))
    etiqueta.add(BarcodeElement(rotation=Rotation.INVERTED))

    linhas = linhas_de(etiqueta)
    assert any("^A0R," in l for l in linhas)
    assert any("^BCI," in l for l in linhas)


def test_elemento_invisivel_nao_entra_no_zpl(etiqueta):
    etiqueta.add(TextElement(text="VISIVEL"))
    etiqueta.add(TextElement(text="OCULTO", visible=False))

    zpl = to_zpl(etiqueta, comments=False)
    assert "VISIVEL" in zpl
    assert "OCULTO" not in zpl


# ---------------------------------------------------------------------------
# Resiliência
# ---------------------------------------------------------------------------
def test_elemento_quebrado_nao_derruba_a_etiqueta(etiqueta):
    """No editor o usuário produz estados inválidos o tempo todo enquanto digita."""
    etiqueta.add(TextElement(text="OK"))
    quebrado = BarcodeElement(data="X")
    quebrado.symbology = "inexistente"  # type: ignore[assignment]
    etiqueta.add(quebrado)
    etiqueta.add(TextElement(text="DEPOIS"))

    zpl = to_zpl(etiqueta, comments=False)
    assert "OK" in zpl and "DEPOIS" in zpl  # o resto continua sendo gerado
    assert "^FXerro em" in zpl               # e o problema fica visível
    assert zpl.endswith("^XZ")


# ---------------------------------------------------------------------------
# Mapa de segmentos (destaque bidirecional no editor)
# ---------------------------------------------------------------------------
def test_cada_elemento_visivel_ganha_um_segmento(etiqueta):
    a = etiqueta.add(TextElement(text="A"))
    b = etiqueta.add(BarcodeElement(data="123"))
    etiqueta.add(TextElement(text="C", visible=False))

    doc = ZplWriter().write(etiqueta)
    assert [s.element_id for s in doc.segments] == [a.id, b.id]


def test_segmento_aponta_para_as_linhas_do_proprio_elemento(etiqueta):
    a = etiqueta.add(TextElement(text="PRIMEIRO"))
    b = etiqueta.add(TextElement(text="SEGUNDO"))

    doc = ZplWriter().write(etiqueta)
    trecho_a = doc.lines[doc.segment_for(a.id).start_line : doc.segment_for(a.id).end_line + 1]
    trecho_b = doc.lines[doc.segment_for(b.id).start_line : doc.segment_for(b.id).end_line + 1]

    assert any("PRIMEIRO" in l for l in trecho_a)
    assert not any("SEGUNDO" in l for l in trecho_a)
    assert any("SEGUNDO" in l for l in trecho_b)


def test_comentarios_podem_ser_desligados(etiqueta):
    etiqueta.add(TextElement(name="Meu campo", text="X"))
    assert "^FXMeu campo^FS" in ZplWriter(include_comments=True).write(etiqueta).lines
    assert "^FXMeu campo^FS" not in ZplWriter(include_comments=False).write(etiqueta).lines


def test_versao_compacta_remove_comentarios_e_quebras(etiqueta):
    etiqueta.add(TextElement(name="Campo", text="X"))
    doc = ZplWriter(include_comments=True).write(etiqueta)

    assert "\n" not in doc.compact()
    assert "^FX" not in doc.compact()
    assert doc.compact().startswith("^XA")


# ---------------------------------------------------------------------------
# Campos variáveis
# ---------------------------------------------------------------------------
def test_placeholders_sao_detectados(etiqueta):
    etiqueta.add(TextElement(text="Produto: {{nome}}"))
    etiqueta.add(BarcodeElement(data="{{sku}}"))
    assert etiqueta.placeholders() == {"nome", "sku"}


def test_merge_substitui_os_valores(etiqueta):
    etiqueta.add(TextElement(text="Olá {{nome}}"))
    zpl = to_zpl(etiqueta, {"nome": "Maria"}, comments=False)
    assert "Ol" in zpl and "Maria" in zpl
    assert "{{nome}}" not in zpl


def test_merge_nao_altera_a_etiqueta_original(etiqueta):
    original = etiqueta.add(TextElement(text="{{campo}}"))
    to_zpl(etiqueta, {"campo": "valor"})
    assert original.text == "{{campo}}"


def test_placeholder_sem_valor_permanece_visivel(etiqueta):
    """Melhor sair "{{sku}}" impresso do que um campo vazio despercebido."""
    etiqueta.add(TextElement(text="{{sku}}"))
    assert "{{sku}}" in to_zpl(etiqueta, {"outro": "x"}, comments=False)
