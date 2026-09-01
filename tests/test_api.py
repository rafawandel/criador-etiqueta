"""Contrato HTTP entre o editor e o backend.

O editor é o único cliente hoje, mas ele depende de detalhes precisos destas
respostas (o mapa de segmentos, a lista de avisos, o formato do catálogo).
Quebrar qualquer um deles quebra a tela sem erro visível no Python.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.template_store import TemplateStore, slugify


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(app)


@pytest.fixture
def etiqueta() -> dict:
    return {
        "name": "Etiqueta de teste",
        "width_mm": 100,
        "height_mm": 50,
        "dpi": 203,
        "elements": [
            {"type": "text", "id": "t1", "text": "ACME", "x_mm": 5, "y_mm": 5, "height_mm": 6},
            {"type": "barcode", "id": "b1", "symbology": "code128", "data": "ABC123",
             "x_mm": 5, "y_mm": 20, "height_mm": 12},
        ],
    }


# ---------------------------------------------------------------------------
# Catálogo -- é o que constrói a interface inteira
# ---------------------------------------------------------------------------
def test_catalogo_descreve_todos_os_tipos(cliente):
    from zpl_core.elements import ELEMENT_TYPES

    catalogo = cliente.get("/api/catalog").json()
    tipos = {e["type"] for e in catalogo["elements"]}
    assert tipos == set(ELEMENT_TYPES)


def test_cada_tipo_traz_o_que_a_interface_precisa(cliente):
    for entrada in cliente.get("/api/catalog").json()["elements"]:
        assert entrada["label"] and entrada["icon"] and entrada["category"]
        assert entrada["fields"], f"{entrada['type']} sem campos editáveis"
        assert "defaults" in entrada, f"{entrada['type']} sem valores padrão"
        assert "resize" in entrada, f"{entrada['type']} sem regra de redimensionamento"


def test_defaults_do_catalogo_geram_zpl_valido(cliente):
    """Arrastar qualquer objeto da paleta tem que produzir ZPL na hora."""
    catalogo = cliente.get("/api/catalog").json()
    elementos = [
        {**e["defaults"], "id": f"e{i}"} for i, e in enumerate(catalogo["elements"])
    ]
    resposta = cliente.post("/api/zpl", json={"label": {"elements": elementos}})

    assert resposta.status_code == 200
    assert resposta.json()["zpl"].startswith("^XA")


def test_campos_do_catalogo_existem_no_modelo(cliente):
    """Um campo descrito na interface que não existe na dataclass viraria uma
    edição silenciosamente ignorada."""
    catalogo = cliente.get("/api/catalog").json()
    for entrada in catalogo["elements"]:
        conhecidos = set(entrada["defaults"])
        for campo in entrada["fields"] + catalogo["common_fields"]:
            assert campo["name"] in conhecidos, f"{entrada['type']}.{campo['name']}"


def test_regras_de_redimensionamento_apontam_para_campos_reais(cliente):
    for entrada in cliente.get("/api/catalog").json()["elements"]:
        for chave in ("width", "height", "uniform"):
            campo = entrada["resize"].get(chave)
            if campo:
                assert campo in entrada["defaults"], f"{entrada['type']}.{campo}"


# ---------------------------------------------------------------------------
# Geração de ZPL
# ---------------------------------------------------------------------------
def test_zpl_traz_codigo_segmentos_e_medidas(cliente, etiqueta):
    corpo = cliente.post("/api/zpl", json={"label": etiqueta}).json()

    assert corpo["zpl"].startswith("^XA") and corpo["zpl"].endswith("^XZ")
    assert corpo["width_dots"] == 799
    assert corpo["byte_size"] > 0
    assert {s["element_id"] for s in corpo["segments"]} == {"t1", "b1"}


def test_segmentos_apontam_para_linhas_existentes(cliente, etiqueta):
    corpo = cliente.post("/api/zpl", json={"label": etiqueta}).json()
    linhas = corpo["zpl"].split("\n")

    for segmento in corpo["segments"]:
        assert 0 <= segmento["start_line"] <= segmento["end_line"] < len(linhas)


def test_comentarios_podem_ser_desligados(cliente, etiqueta):
    com = cliente.post("/api/zpl", json={"label": etiqueta, "comments": True}).json()
    sem = cliente.post("/api/zpl", json={"label": etiqueta, "comments": False}).json()

    assert "^FX" in com["zpl"]
    assert "^FX" not in sem["zpl"]


def test_campos_variaveis_sao_devolvidos_e_substituidos(cliente, etiqueta):
    etiqueta["elements"][0]["text"] = "Olá {{cliente}}"

    corpo = cliente.post("/api/zpl", json={"label": etiqueta}).json()
    assert corpo["placeholders"] == ["cliente"]

    preenchido = cliente.post(
        "/api/zpl", json={"label": etiqueta, "data": {"cliente": "Maria"}}
    ).json()
    assert "Maria" in preenchido["zpl"]


def test_avisos_referenciam_o_elemento(cliente, etiqueta):
    etiqueta["elements"][1] = {**etiqueta["elements"][1], "symbology": "ean13", "data": "1"}
    avisos = cliente.post("/api/zpl", json={"label": etiqueta}).json()["issues"]

    erro = next(i for i in avisos if i["severity"] == "error")
    assert erro["element_id"] == "b1"


def test_etiqueta_invalida_responde_422_com_explicacao(cliente):
    resposta = cliente.post("/api/zpl", json={"label": {"elements": [{"type": "xyz"}]}})
    assert resposta.status_code == 422
    assert "xyz" in resposta.json()["detail"]


def test_export_serve_arquivo_com_o_nome_da_etiqueta(cliente, etiqueta):
    resposta = cliente.post("/api/export/zpl", json={"label": etiqueta})
    assert 'filename="Etiqueta de teste.zpl"' in resposta.headers["content-disposition"]
    assert resposta.text.startswith("^XA")


# ---------------------------------------------------------------------------
# Previews
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "rota,parametros",
    [
        ("/api/preview/barcode", {"symbology": "code128", "data": "ABC123"}),
        ("/api/preview/barcode", {"symbology": "ean13", "data": "7891234567895"}),
        ("/api/preview/qrcode", {"data": "https://example.com"}),
        ("/api/preview/datamatrix", {"data": "XYZ"}),
    ],
)
def test_preview_devolve_png(cliente, rota, parametros):
    resposta = cliente.get(rota, params=parametros)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "image/png"
    assert resposta.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_com_dado_invalido_ainda_devolve_imagem(cliente):
    """Enquanto o usuário digita, o dado é inválido quase o tempo todo. O
    preview precisa mostrar algo em vez de estourar."""
    resposta = cliente.get("/api/preview/barcode", params={"symbology": "ean13", "data": "AB"})
    assert resposta.status_code == 200
    assert resposta.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_de_imagem_devolve_bitmap(cliente):
    minima = (
        "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    resposta = cliente.post(
        "/api/preview/image",
        json={"source": minima, "width_mm": 10, "height_mm": 10, "dpi": 203},
    )
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "image/png"


def test_imagem_corrompida_responde_422(cliente):
    resposta = cliente.post(
        "/api/preview/image",
        json={"source": "data:image/png;base64,naoehimagem", "width_mm": 10, "height_mm": 10},
    )
    assert resposta.status_code == 422


# ---------------------------------------------------------------------------
# Impressão
# ---------------------------------------------------------------------------
def test_impressao_desligada_por_padrao_explica_o_motivo(cliente, etiqueta):
    resposta = cliente.post(
        "/api/print", json={"label": etiqueta, "printer": "192.168.0.1:9100"}
    )
    assert resposta.status_code == 403
    assert "ETIQUETA_ALLOW_PRINTING" in resposta.json()["detail"]


def test_saude_reporta_o_estado_da_impressao(cliente):
    corpo = cliente.get("/api/health").json()
    assert corpo["status"] == "ok"
    assert corpo["printing_enabled"] is False


# ---------------------------------------------------------------------------
# Modelos salvos
# ---------------------------------------------------------------------------
def test_ciclo_de_vida_do_modelo(tmp_path, etiqueta):
    from zpl_core.serialization import label_from_dict

    store = TemplateStore(tmp_path)
    assert store.list() == []

    slug = store.save(label_from_dict(etiqueta))
    assert slug == "etiqueta-de-teste"

    resumo = store.list()[0]
    assert resumo["name"] == "Etiqueta de teste"
    assert resumo["element_count"] == 2

    assert store.get(slug).name == "Etiqueta de teste"

    store.delete(slug)
    assert store.list() == []


def test_arquivo_corrompido_nao_impede_listar_os_outros(tmp_path, etiqueta):
    from zpl_core.serialization import label_from_dict

    store = TemplateStore(tmp_path)
    store.save(label_from_dict(etiqueta))
    (tmp_path / "quebrado.json").write_text("{ isso nao e json", encoding="utf-8")

    assert len(store.list()) == 1


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Etiqueta Ação 2024", "etiqueta-acao-2024"),
        ("../../etc/passwd", "etc-passwd"),
        ("   ", "etiqueta"),
    ],
)
def test_slug_neutraliza_nomes_perigosos(entrada, esperado):
    assert slugify(entrada) == esperado


def test_caminho_nao_escapa_da_pasta(tmp_path):
    """Um slug com travessia de diretório não pode gravar fora da pasta."""
    store = TemplateStore(tmp_path)
    caminho = store._path("../../fora")
    assert caminho.parent == tmp_path.resolve()
