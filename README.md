# Criador de Etiquetas ZPL

**Português** · [English](README.en.md) · [Español](README.es.md)

Editor visual de etiquetas para impressoras Zebra. Você arrasta os objetos na
tela, digita o conteúdo, e o código ZPL aparece pronto ao lado — atualizado a
cada alteração.

```
┌──────────────┬────────────────────────────┬──────────────┬──────────────────┐
│  PALETA      │        ETIQUETA            │ PROPRIEDADES │   ZPL AO VIVO    │
│  CAMADAS     │   (arrasta, redimensiona)  │              │  (bidirecional)  │
└──────────────┴────────────────────────────┴──────────────┴──────────────────┘
```

## Rodando

O projeto usa [uv](https://docs.astral.sh/uv/). Se ainda não tiver:

```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"    # Windows
curl -LsSf https://astral.sh/uv/install.sh | sh               # Linux/macOS
```

Depois:

```bash
uv sync                  # cria o .venv e instala as versões exatas do lock
uv run python run.py     # sobe o editor
```

O navegador abre em `http://127.0.0.1:8000`. Não há passo de build: o frontend
é JavaScript de módulo nativo, servido direto.

## O que dá para colocar na etiqueta

| Objeto | Comando ZPL | Observação |
|---|---|---|
| Texto | `^A` + `^FD` | fontes internas, rotação, bloco com quebra (`^FB`), inversão (`^FR`) |
| Código de barras | `^BC` `^B3` `^BA` `^BE` `^B8` `^BU` `^B2` | Code 128/39/93, EAN-13/8, UPC-A, ITF |
| QR Code | `^BQ` | 4 níveis de correção de erro |
| DataMatrix | `^BX` | ECC 200 |
| Retângulo | `^GB` | moldura ou área sólida, cantos arredondados |
| Linha | `^GB` / `^GD` | horizontal, vertical e diagonal |
| Círculo | `^GC` | |
| Imagem | `^GFA` | logotipo convertido para 1 bit, com limiar ou dithering |

Acentos são resolvidos com `^CI28` (UTF-8) e escape hexadecimal via `^FH`, que
é o caminho que funciona em campo — inclusive nas impressoras mais antigas,
trocando a codificação na aba **Etiqueta**.

## Campos variáveis

Escreva `{{sku}}` em qualquer texto ou código de barras. O campo vira uma
variável: o editor lista as variáveis encontradas e pede os valores na hora de
imprimir. O mesmo modelo serve para um lote inteiro.

```python
from zpl_core import load_label, to_zpl

modelo = load_label("templates_store/etiqueta-produto.json")
for linha in produtos:
    enviar(to_zpl(modelo, {"sku": linha.sku, "lote": linha.lote}))
```

## Atalhos

| | |
|---|---|
| `Ctrl+Z` / `Ctrl+Y` | desfazer / refazer |
| `Ctrl+D` | duplicar objeto |
| `Delete` | excluir objeto |
| `Setas` | mover 0,5 mm (`Shift` = 5 mm) |
| `Ctrl+S` | salvar modelo |
| `Ctrl` + roda | zoom |
| `Alt` durante o arrasto | desliga o ímã |
| `Esc` | limpar seleção |

## Imprimindo

Três caminhos, do mais simples ao mais integrado:

1. **Baixar `.zpl`** e enviar como preferir — sempre disponível;
2. **Copiar** o código e colar onde for preciso;
3. **Imprimir direto**, por TCP na porta 9100 ou por uma fila do Windows.

A impressão direta vem **desligada**. Para habilitar:

```bash
# .env  (veja .env.example)
ETIQUETA_ALLOW_PRINTING=1
ETIQUETA_PRINTERS=Expedicao=192.168.0.50:9100;Producao=192.168.0.51
```

Para a fila do Windows, instale o extra: `uv sync --extra windows-print`. Sem
ele, só o envio por IP fica disponível — e a mensagem de erro diz isso.

## Como o projeto está organizado

> Para a arquitetura completa — camadas, contratos, decisões registradas e o
> passo a passo para adicionar um comando ZPL novo — veja **[DESIGN.md](DESIGN.md)**.

```
src/
├── zpl_core/            Python puro. Não conhece HTTP nem navegador.
│   ├── units.py         mm <-> dots. Único lugar que sabe o que é DPI.
│   ├── enums.py         rotação, cor, simbologia (valores = letras do ZPL)
│   ├── elements.py      um dataclass por objeto; cada um sabe virar ZPL
│   ├── label.py         a etiqueta: mídia, impressão, campos variáveis
│   ├── zpl_writer.py    modelo -> ZPL + mapa linha→elemento
│   ├── escaping.py      ^FH / ^CI, acentos e caracteres de controle
│   ├── validation.py    avisos que evitam desperdício de mídia
│   ├── serialization.py JSON <-> Label
│   ├── barcodes.py      PNGs de preview (não é o que imprime)
│   ├── images.py        imagem -> bitmap 1 bit -> ^GFA
│   └── printing.py      TCP 9100, spooler do Windows, arquivo
│
├── app/                 Camada web fina sobre o zpl_core.
│   ├── catalog.py       descreve os objetos PARA A INTERFACE
│   ├── routers/         render, templates, printing
│   └── main.py          FastAPI
│
web/                     Editor. Sem build, sem framework.
├── store.js             estado + histórico de desfazer
├── geometry.js          tamanhos e ímã (espelha o cálculo do Python)
├── canvas.js            desenho e todas as interações de mouse
├── inspector.js         painel de propriedades gerado pelo catálogo
├── panels.js            paleta e camadas
└── zplview.js           painel de ZPL com destaque bidirecional
```

### Três decisões que valem explicar

**O ZPL é gerado só em Python.** O painel ao vivo faz uma chamada (com debounce
de 120 ms) em vez de montar o código no navegador. Em rede local a latência é
imperceptível, e em troca existe uma única implementação do ZPL — a que também
alimenta a exportação, a impressão e os scripts de lote. Duas implementações
divergiriam, e a divergência apareceria na impressora.

**A interface é gerada pelo catálogo.** O painel de propriedades e a paleta não
têm formulários escritos à mão. Eles são construídos a partir de
`app/catalog.py`, que descreve rótulo, unidade, faixa de valores e como cada
objeto redimensiona. Suportar um comando ZPL novo é: criar a dataclass em
`elements.py`, registrá-la em `ELEMENT_TYPES` e descrevê-la no catálogo.
Nenhuma linha de JavaScript muda.

**O código e o desenho apontam um para o outro.** O gerador devolve, junto com
o ZPL, o mapa de qual elemento produziu quais linhas. Selecionar um objeto
destaca o trecho correspondente; clicar em uma linha seleciona o objeto. É o
que transforma o painel de código em ferramenta de aprendizado em vez de um
bloco de texto opaco.

## Limites conhecidos

- **O preview é aproximação, não simulação.** Texto e formas são desenhados
  pelo navegador; códigos de barras vêm de bibliotecas Python. A fidelidade é
  boa para diagramar, mas a métrica exata das fontes internas da Zebra só a
  impressora conhece. Para conferência final, imprima uma unidade.
- **DataMatrix aparece como marcador.** O `^BX` gerado está correto e imprime
  normalmente; o que falta é um encoder DataMatrix puro-Python para desenhar o
  preview. Ele é sinalizado como aproximado na tela para não enganar ninguém.
- **Rotação no preview** gira em torno da origem do campo. É o comportamento do
  `^FO` na maioria dos casos, mas campos rotacionados merecem uma impressão de
  teste antes de virar produção.

## Testes

```bash
uv run pytest
```

94 testes cobrindo geração de ZPL, escape de acentos, serialização, validação e
o contrato HTTP. Alguns deles existem para travar acoplamentos que quebrariam
em silêncio — por exemplo, que todo campo descrito no catálogo exista de fato na
dataclass correspondente.

## Licença

[MIT](LICENSE). Use, modifique e redistribua à vontade, inclusive
comercialmente — basta manter o aviso de copyright.

As dependências também são permissivas: FastAPI, Pydantic e python-barcode sob
MIT; Uvicorn, Starlette e qrcode sob BSD-3-Clause; Pillow sob MIT-CMU. Nenhuma
impõe restrição ao que você fizer com este projeto.
