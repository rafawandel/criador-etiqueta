"""O JSON da etiqueta é o formato de arquivo do usuário. Ele precisa sobreviver
a idas e voltas sem perder nada e falhar de forma explicável quando vier torto.
"""

import json

import pytest

from zpl_core import (
    BarcodeElement,
    BoxElement,
    ImageElement,
    Label,
    QrCodeElement,
    SerializationError,
    Symbology,
    TextElement,
    label_from_dict,
    label_from_json,
    label_to_dict,
    label_to_json,
    load_label,
    save_label,
    to_zpl,
)
from zpl_core.elements import ELEMENT_TYPES


@pytest.fixture
def etiqueta_completa() -> Label:
    label = Label(name="Completa", width_mm=80, height_mm=40, dpi=300)
    label.print_settings.copies = 3
    label.print_settings.darkness = 10
    label.add(TextElement(name="T", text="Olá ação", x_mm=2, y_mm=3, height_mm=5))
    label.add(BarcodeElement(symbology=Symbology.CODE39, data="ABC", wide_ratio=2.5))
    label.add(QrCodeElement(data="https://x", magnification=7))
    label.add(BoxElement(width_mm=10, height_mm=4, rounding=3))
    return label


def test_ida_e_volta_preserva_o_zpl(etiqueta_completa):
    """O teste que importa: a etiqueta recarregada imprime igual à original."""
    copia = label_from_json(label_to_json(etiqueta_completa))
    assert to_zpl(copia) == to_zpl(etiqueta_completa)


def test_ida_e_volta_preserva_os_campos(etiqueta_completa):
    copia = label_from_dict(label_to_dict(etiqueta_completa))

    assert copia.name == etiqueta_completa.name
    assert copia.dpi == 300
    assert copia.print_settings.copies == 3
    assert copia.print_settings.darkness == 10
    assert [e.id for e in copia.elements] == [e.id for e in etiqueta_completa.elements]


def test_enums_voltam_como_enums(etiqueta_completa):
    copia = label_from_dict(label_to_dict(etiqueta_completa))
    barcode = next(e for e in copia.elements if isinstance(e, BarcodeElement))
    assert barcode.symbology is Symbology.CODE39


def test_json_e_legivel_por_humanos(etiqueta_completa):
    """O arquivo é versionado em Git pelo time; precisa ser diffável."""
    bruto = label_to_json(etiqueta_completa)
    assert "\n" in bruto
    assert "Olá" in bruto  # sem escapar acentos
    assert json.loads(bruto)["schema_version"] == 1


def test_todos_os_tipos_sobrevivem_a_ida_e_volta():
    """Guarda contra um tipo novo entrar no modelo e quebrar a persistência."""
    label = Label()
    for cls in ELEMENT_TYPES.values():
        label.add(cls())

    copia = label_from_dict(label_to_dict(label))
    assert [type(e) for e in copia.elements] == [type(e) for e in label.elements]


def test_campos_desconhecidos_sao_ignorados():
    """Um arquivo gravado por versão futura com campo extra ainda abre."""
    label = label_from_dict(
        {"elements": [{"type": "text", "text": "X", "campo_do_futuro": 42}]}
    )
    assert label.elements[0].text == "X"


def test_tipo_desconhecido_da_erro_explicativo():
    with pytest.raises(SerializationError) as erro:
        label_from_dict({"elements": [{"type": "holograma"}]})

    assert "holograma" in str(erro.value)
    assert "text" in str(erro.value)  # lista os tipos suportados


def test_schema_futuro_e_recusado():
    with pytest.raises(SerializationError, match="versao mais nova"):
        label_from_dict({"schema_version": 99, "elements": []})


def test_json_invalido_da_erro_de_serializacao():
    with pytest.raises(SerializationError, match="JSON invalido"):
        label_from_json("{isso nao e json")


def test_etiqueta_minima_usa_padroes():
    label = label_from_dict({})
    assert label.width_mm == 100 and label.height_mm == 50 and label.dpi == 203


def test_gravar_e_ler_arquivo(tmp_path, etiqueta_completa):
    destino = save_label(etiqueta_completa, tmp_path / "sub" / "etiqueta.json")
    assert destino.exists()
    assert to_zpl(load_label(destino)) == to_zpl(etiqueta_completa)


def test_imagem_nao_perde_o_conteudo():
    minima = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    label = Label()
    label.add(ImageElement(source=minima, width_mm=10, height_mm=10))
    copia = label_from_dict(label_to_dict(label))
    assert copia.elements[0].source == minima
