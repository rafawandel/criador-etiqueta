"""A validação existe para pegar o erro antes do ribbon. Ela nunca bloqueia --
apenas avisa --, então cada teste confere a mensagem certa na gravidade certa.
"""

import pytest

from zpl_core import (
    BarcodeElement,
    Label,
    QrCodeElement,
    Severity,
    Symbology,
    TextElement,
    validate,
)


def graves(label: Label) -> list[str]:
    return [i.message for i in validate(label) if i.severity is Severity.ERROR]


def avisos(label: Label) -> list[str]:
    return [i.message for i in validate(label) if i.severity is Severity.WARNING]


# ---------------------------------------------------------------------------
# Simbologias com regra de conteúdo
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("digitos", ["123", "78912345678901234"])
def test_ean13_com_quantidade_errada_de_digitos(digitos):
    label = Label()
    label.add(BarcodeElement(symbology=Symbology.EAN13, data=digitos))
    assert any("12 ou 13 digitos" in m for m in graves(label))


def test_ean13_valido_nao_reclama():
    label = Label()
    label.add(BarcodeElement(symbology=Symbology.EAN13, data="789123456789", height_mm=12))
    assert not graves(label)


def test_ean13_com_letras():
    label = Label()
    label.add(BarcodeElement(symbology=Symbology.EAN13, data="78912345678A"))
    assert any("apenas digitos" in m for m in graves(label))


def test_code39_rejeita_caractere_fora_do_conjunto():
    label = Label()
    label.add(BarcodeElement(symbology=Symbology.CODE39, data="ABC@123"))
    mensagens = graves(label)
    assert any("Code 39" in m and "@" in m for m in mensagens)


def test_code39_aceita_o_proprio_conjunto():
    label = Label()
    label.add(BarcodeElement(symbology=Symbology.CODE39, data="ABC-123 $/+%", height_mm=12))
    assert not graves(label)


def test_itf_exige_quantidade_par():
    label = Label()
    label.add(BarcodeElement(symbology=Symbology.ITF, data="12345"))
    assert any("par de digitos" in m for m in graves(label))


def test_barcode_sem_dados():
    label = Label()
    label.add(BarcodeElement(data="   "))
    assert any("sem dados" in m for m in graves(label))


def test_placeholder_nao_e_validado_como_conteudo_final():
    """Um campo variável só ganha valor na impressão -- cobrar formato agora
    encheria a tela de erro falso enquanto o usuário monta o modelo."""
    label = Label()
    label.add(BarcodeElement(symbology=Symbology.EAN13, data="{{ean}}", height_mm=12))
    assert not graves(label)


# ---------------------------------------------------------------------------
# Legibilidade
# ---------------------------------------------------------------------------
def test_barra_estreita_demais_vira_aviso():
    label = Label()
    label.add(BarcodeElement(data="12345678", module_width_dots=1, height_mm=12))
    assert any("barras muito finas" in m for m in avisos(label))


def test_codigo_baixo_demais_vira_aviso():
    label = Label()
    label.add(BarcodeElement(data="12345678", height_mm=3))
    assert any("muito baixo" in m for m in avisos(label))


def test_fonte_minuscula_vira_aviso():
    label = Label()
    label.add(TextElement(text="X", height_mm=1.0))
    assert any("fonte muito pequena" in m for m in avisos(label))


def test_qrcode_com_modulo_pequeno_vira_aviso():
    label = Label()
    label.add(QrCodeElement(data="https://x", magnification=2))
    assert any("pequenos demais" in m for m in avisos(label))


# ---------------------------------------------------------------------------
# Posição
# ---------------------------------------------------------------------------
def test_posicao_negativa_e_erro():
    label = Label(width_mm=100, height_mm=50)
    label.add(TextElement(text="X", x_mm=-5, y_mm=2, height_mm=4))
    assert any("fora da etiqueta" in m for m in graves(label))


def test_elemento_alem_da_borda_vira_aviso():
    label = Label(width_mm=50, height_mm=30)
    label.add(TextElement(text="Um texto bem comprido para estourar", x_mm=45, height_mm=6))
    assert any("ultrapassar a borda" in m for m in avisos(label))


def test_elemento_dentro_da_etiqueta_nao_reclama():
    label = Label(width_mm=100, height_mm=50)
    label.add(TextElement(text="curto", x_mm=5, y_mm=5, height_mm=4))
    assert not graves(label) and not avisos(label)


def test_elemento_oculto_nao_e_cobrado_por_posicao():
    label = Label(width_mm=50, height_mm=30)
    label.add(TextElement(text="X", x_mm=-10, visible=False))
    assert not graves(label)


def test_borda_considera_a_resolucao():
    """O mesmo código ocupa menos milímetros em 300 dpi; o aviso precisa seguir."""
    elemento = dict(symbology=Symbology.CODE128, data="ABCDEFGHIJ", x_mm=40, height_mm=12)

    estreita = Label(width_mm=70, height_mm=40, dpi=203)
    estreita.add(BarcodeElement(**elemento))
    larga = Label(width_mm=70, height_mm=40, dpi=300)
    larga.add(BarcodeElement(**elemento))

    assert any("ultrapassar a borda" in m for m in avisos(estreita))
    assert not avisos(larga)


# ---------------------------------------------------------------------------
# Informativos
# ---------------------------------------------------------------------------
def test_etiqueta_vazia_recebe_orientacao():
    mensagens = [i.message for i in validate(Label())]
    assert any("esta vazia" in m for m in mensagens)


def test_campos_variaveis_sao_listados():
    label = Label()
    label.add(TextElement(text="{{sku}} — {{lote}}"))
    informativos = [i for i in validate(label) if i.severity is Severity.INFO]
    assert any("lote, sku" in i.message for i in informativos)


def test_erros_vem_antes_dos_avisos():
    label = Label()
    label.add(BarcodeElement(symbology=Symbology.EAN13, data="1", module_width_dots=1))
    gravidades = [i.severity for i in validate(label)]
    assert gravidades == sorted(gravidades, key=lambda s: ["error", "warning", "info"].index(s))
