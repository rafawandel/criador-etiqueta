# DESIGN — Criador de Etiquetas ZPL

Documento de arquitetura. Descreve **como** o sistema é construído e **por quê**
cada decisão foi tomada. O `README.md` é para quem vai *usar*; este é para quem
vai *mexer*.

> **Manutenção:** este arquivo acompanha o código. Toda mudança que altere
> camadas, contratos, formato de dados ou uma decisão registrada abaixo deve
> atualizar a seção correspondente **no mesmo commit**. Um DESIGN.md
> desatualizado é pior que nenhum: ele mente com autoridade.

---

## 1. O problema

Etiquetas Zebra são descritas em ZPL — uma linguagem de comandos em texto, densa
e posicional, com coordenadas em *dots* que dependem da resolução da cabeça de
impressão. Escrever ZPL à mão é viável para uma etiqueta; é insustentável para
um catálogo de modelos mantido por gente de produção.

O sistema resolve isso com um editor visual onde o usuário arrasta objetos e vê
o ZPL nascer ao lado, em tempo real. O código gerado é o produto final: pode ser
copiado, baixado ou enviado direto à impressora.

### Requisitos que moldaram o desenho

| Requisito | Consequência arquitetural |
|---|---|
| "qualquer objeto que o ZPL aceita" | Catálogo de tipos dirigido por metadados (§8) |
| ZPL atualizado em tempo real | Geração no servidor com debounce; fonte única (§7, ADR-1) |
| Uso em chão de fábrica | Zero build no cliente; erro nunca derruba a tela (§10) |
| Reuso em lote / integração com ERP | Núcleo Python isolado de HTTP (§4) |

---

## 2. Princípios

1. **Uma só implementação do ZPL.** Ela vive em `zpl_core` e alimenta editor,
   exportação, impressão e scripts. Nunca há uma segunda versão "só para a tela".
2. **O núcleo não conhece o mundo.** `zpl_core` não importa FastAPI, não sabe o
   que é uma requisição e não lê variável de ambiente.
3. **Metadados no lugar de código repetido.** Um objeto novo é descrito uma vez;
   paleta, formulário e redimensionamento se ajustam sozinhos.
4. **Nunca bloquear o usuário.** A validação avisa, não impede. Um elemento
   inválido vira comentário de erro no ZPL e o resto continua sendo gerado.
5. **Sem dependência que não pague o próprio peso.** O frontend não tem
   framework nem build step. A ferramenta precisa subir numa máquina de produção
   com `uv run` e mais nada.

---

## 3. Estilo arquitetural

O sistema usa **duas** arquiteturas, uma de cada lado da rede — porque os dois
lados resolvem problemas diferentes. Nomeá-las corretamente evita a discussão
recorrente de "mas isso é MVC?" (§3.4).

### 3.1 Backend — camadas com dependência unidirecional

É o princípio de *ports & adapters* (arquitetura hexagonal) aplicado sem a
cerimônia: **as dependências apontam para dentro, nunca para fora.**

```
        entrada                    adaptadores                  domínio
   ┌──────────────┐          ┌────────────────────┐      ┌─────────────────┐
   │  navegador   │ ──HTTP─> │     src/app/       │ ───> │  src/zpl_core/  │
   │  script      │ ───────────────────────────────────> │                 │
   │  ERP         │          │  routers, catálogo │      │  regras de ZPL  │
   └──────────────┘          │  persistência      │      └─────────────────┘
                             └────────────────────┘         não importa
                                                            nada de fora
```

O núcleo não sabe que existe HTTP, nem navegador, nem variável de ambiente. Por
isso um script de lote consome `zpl_core` diretamente, sem subir servidor — a
segunda seta no diagrama.

**A regra é verificável, não apenas declarada:**

```bash
grep -rn "from app\|import app" src/zpl_core/    # tem de sair vazio
```

Vale como checagem de arquitetura em CI: no dia em que alguém importar `app`
dentro do núcleo, o comando acusa e a reutilização em script quebra em seguida.

### 3.2 Frontend — fluxo unidirecional com observador

O editor não tem controllers. Tem um estado único que **notifica**, e painéis que
**reagem**:

```
  interação ──> store (única fonte de verdade) ──┬──> canvas
                        │                        ├──> inspetor
                   emite "motivos"               ├──> camadas
                        │                        └──> painel de ZPL
                        └──> debounce ──> API ──> volta como novo estado
```

É a família Flux/MVVM, não MVC. A propriedade que interessa: **nenhum painel
conhece outro painel.** Adicionar um painel novo é assinar o store; remover um é
apagar o arquivo. Não há um mediador central que precise ser editado nos dois
casos.

### 3.3 Padrões táticos e onde eles aparecem

Só os que realmente estão em uso — rotular de mais é tão ruim quanto não
documentar:

| Padrão | Onde | O que ele compra |
|---|---|---|
| Modelo de domínio rico | `zpl_core/elements.py` | Cada elemento sabe virar ZPL; o writer não tem `if` por tipo |
| Registro de tipos | `ELEMENT_TYPES` | Serialização e catálogo descobrem tipos novos sozinhos |
| Interface dirigida por esquema | `app/catalog.py` → `inspector.js` | Formulário não escrito à mão (ADR-2) |
| Observador / publicar-assinar | `web/js/store.js` | Painéis desacoplados entre si |
| Instantâneo (memento) | Histórico do store | Desfazer sem escrever operação inversa para cada ação |
| Agrupamento de interação | `beginBatch` / `endBatch` | Um arrasto inteiro vira um passo de desfazer |
| Repositório | `TemplateStore` | Trocar arquivo por banco toca uma classe só |
| Objeto de transferência | `app/schemas.py` | Pydantic só na borda HTTP (ADR-6) |
| Degradação suave | `_safe_element_zpl`, `_placeholder_png` | Dado inválido não apaga a tela nem interrompe o ZPL |

**Deliberadamente ausentes:** injeção de dependência formal, interfaces abstratas
(*ports*) e uma camada de casos de uso. Existe um domínio e um cliente; abstrair
agora seria custo de indireção sem nenhum segundo implementador para justificá-lo.
Se um dia surgir um segundo adaptador de entrada — uma CLI, uma fila —, o lugar
de introduzi-los já está isolado.

### 3.4 O que este projeto não é

#### Não é MVC

A pergunta aparece porque `routers/` *parece* uma camada de controllers. A
analogia quebra em dois pontos:

| MVC | Aqui | |
|---|---|---|
| **Model** | `zpl_core/` | ✅ Encaixa — e é um modelo *rico*, com as regras de negócio dentro |
| **Controller** | `app/routers/` | ⚠️ Recebem entrada e chamam o domínio, mas **não escolhem uma view**: devolvem JSON. São adaptadores HTTP |
| **View (servidor)** | — | ❌ **Não existe.** Nenhum motor de template no projeto |
| **View (cliente)** | `canvas.js`, `inspector.js`, `zplview.js`, `panels.js` | ⚠️ Views que tratam a própria entrada — no MVC isso seria papel do controller |
| **Controller (cliente)** | `main.js` | ❌ Não medeia nada; é apenas o ponto que liga os fios |

As duas razões de fundo:

1. **Não há renderização no servidor.** MVC nasceu para aplicações em que o
   servidor monta a tela. Aqui o servidor devolve dados (`{"zpl": "^XA…",
   "segments": […]}`) e quem monta a tela é o navegador. Chamar isso de "view"
   confundiria mais do que esclareceria.
2. **Não há interação entre painéis para mediar.** Um controller ganha valor
   quando existe coordenação ("ao salvar, atualize a lista e feche o modal").
   Neste editor todos os painéis leem do store; uma camada de controllers
   adicionaria indireção sem eliminar acoplamento nenhum, porque não há
   acoplamento entre painéis para eliminar.

O que MVC busca de mais importante — **regra de negócio isolada da apresentação**
— está presente, e veio pela separação em camadas. É por isso que os testes de
domínio rodam sem servidor e sem navegador.

#### Também não é

- **Clean Architecture completa** — faltam de propósito os *ports* abstratos e a
  camada de casos de uso (§3.3).
- **Microserviços** — é um processo só. Um editor de etiquetas interno não tem
  eixo de escala nem fronteira de equipe que justifique a rede no meio.
- **SPA com framework** — é uma página com módulos ES nativos (ADR-4).

---

## 4. Camadas

O §3.1 explicou a *regra* (dependências apontam para dentro). Esta seção mostra
a *forma concreta*: o que cada camada contém e em que arquivo procurar.

```
┌───────────────────────────────────────────────────────────────────────┐
│  web/            Editor no navegador. Módulos ES nativos, sem build.  │
│                  Conhece a API HTTP. Não sabe nada de ZPL.            │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  JSON sobre HTTP
┌──────────────────────────────┴────────────────────────────────────────┐
│  src/app/        Camada web fina. Traduz HTTP <-> zpl_core.           │
│                  Contém o catálogo (metadados de interface),          │
│                  configuração e persistência.                          │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  chamadas Python diretas
┌──────────────────────────────┴────────────────────────────────────────┐
│  src/zpl_core/   Domínio. Python puro, testável isoladamente,         │
│                  reutilizável em script de lote ou integração.        │
└───────────────────────────────────────────────────────────────────────┘
```

`app` também nunca importa de `web`: o servidor não conhece a estrutura da tela,
só o contrato JSON do §10.

### Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `zpl_core/units.py` | mm ↔ dots. **Único** lugar que sabe o que é DPI. |
| `zpl_core/enums.py` | Rotação, cor, simbologia. Valores = letras do ZPL. |
| `zpl_core/elements.py` | Um dataclass por objeto; cada um sabe virar ZPL e estimar seu tamanho. |
| `zpl_core/label.py` | A etiqueta: mídia, parâmetros de impressão, campos variáveis. |
| `zpl_core/zpl_writer.py` | Modelo → `ZplDocument` (texto + mapa linha→elemento). |
| `zpl_core/escaping.py` | `^FH`/`^CI`: acentos e caracteres de controle. |
| `zpl_core/validation.py` | Avisos que evitam desperdício de mídia. |
| `zpl_core/serialization.py` | JSON ↔ `Label`, com coerção de tipos genérica. |
| `zpl_core/barcodes.py` | PNGs de *preview*. Não é o que imprime. |
| `zpl_core/images.py` | Imagem → bitmap 1 bit → `^GFA`. |
| `zpl_core/printing.py` | TCP 9100, spooler do Windows, arquivo. |
| `app/catalog.py` | Descreve os objetos **para a interface**. |
| `app/schemas.py` | Contratos HTTP (Pydantic) — envelopes, não o modelo. |
| `app/routers/render.py` | `POST /api/zpl`, exportação, previews. |
| `app/routers/templates.py` | CRUD de modelos salvos. |
| `app/routers/printing.py` | Envio à impressora. Único router com efeito físico. |
| `app/services/template_store.py` | Persistência em arquivos JSON. |
| `app/settings.py` | Configuração por variável de ambiente. |

---

## 5. Fluxo principal

Toda edição percorre o mesmo caminho, em uma direção:

```
  interação do usuário
         │
         ▼
    store.js  ────────────────┐  (estado + histórico de desfazer)
         │                    │
         │ notifica com       │
         │ "motivos"          │
         ▼                    ▼
   painéis redesenham    debounce 120 ms
   (canvas, inspetor,         │
    camadas)                  ▼
                        POST /api/zpl
                              │
                              ▼
                    ZplWriter (Python)
                              │
                              ▼
                  { zpl, segments, issues }
                              │
                              ▼
                   painel de ZPL + avisos
```

Nenhum painel conversa com outro painel. Todos leem do `store` e reagem a
*motivos* (`label`, `live`, `selection`, `ui`, `zpl`, `history`), o que permite
redesenhar só o necessário — é isso que mantém o arrasto fluido numa etiqueta
cheia.

### Motivos de notificação

| Motivo | Emitido quando | Quem reage |
|---|---|---|
| `label` | edição registrada no histórico | canvas, inspetor, camadas, ZPL |
| `live` | arrasto/resize em andamento (sem histórico) | canvas, inspetor, camadas, ZPL |
| `selection` | mudou o objeto selecionado | canvas, inspetor, camadas, ZPL |
| `ui` | zoom, grade, réguas | canvas |
| `zpl` | chegou resposta do servidor | painel de ZPL |
| `history` | pilha de desfazer mudou | botões da barra |

---

## 6. Modelo de domínio

```
Label
├── name, width_mm, height_mm, dpi, encoding
├── print_settings: PrintSettings
│     └── copies, darkness, speed_ips, home_x/y_dots, invert_all, pause_between
└── elements: list[Element]        ← a ordem é a ordem de impressão
      │
      └── Element (base)
            ├── id, name, x_mm, y_mm, rotation, visible, locked
            ├── to_zpl(ctx) -> list[str]
            └── size_mm(resolution) -> (largura, altura)
```

**Tudo em milímetros.** O modelo nunca guarda dots. A conversão acontece só na
hora de gerar o ZPL, em `RenderContext.dots()`. Trocar o DPI de uma etiqueta
pronta reposiciona tudo corretamente, sem tocar em nenhum elemento.

### Elementos suportados

| Tipo | Comando ZPL | Redimensiona alterando |
|---|---|---|
| `text` | `^A` + `^FD` (+ `^FB`, `^FR`) | `block_width_mm` / `height_mm` |
| `barcode` | `^BY` + `^BC`/`^B3`/`^BA`/`^BE`/`^B8`/`^BU`/`^B2` | `height_mm` |
| `qrcode` | `^BQ` | `magnification` (passo inteiro) |
| `datamatrix` | `^BX` | `module_size_dots` (passo inteiro) |
| `box` | `^GB` | `width_mm` / `height_mm` |
| `line` | `^GB` (reta) ou `^GD` (diagonal) | `width_mm` / `height_mm` |
| `circle` | `^GC` | `diameter_mm` |
| `image` | `^GFA` | `width_mm` / `height_mm` |

Os campos de enum são `StrEnum` e são **interpolados diretamente**, sem `.value`.
Isso faz `TextElement(rotation="R")` gerar exatamente o mesmo ZPL que
`TextElement(rotation=Rotation.ROTATED)` — importante para quem monta etiquetas
em script, sem passar pela serialização.

### Campos variáveis

Qualquer texto ou dado de código de barras aceita `{{nome}}`. `Label.merged(data)`
devolve uma **cópia** com os valores substituídos; a etiqueta original nunca é
mutada. Placeholder sem valor correspondente permanece visível no resultado — é
melhor imprimir `{{sku}}` e alguém notar do que imprimir um campo vazio que
passa despercebido.

---

## 7. Geração de ZPL

`ZplWriter.write(label, data)` devolve um `ZplDocument`, não uma string:

```python
@dataclass
class ZplDocument:
    lines: list[str]
    segments: list[ZplSegment]   # element_id -> (start_line, end_line)
```

O mapa de segmentos é o que permite o **destaque bidirecional** no editor:
selecionar um objeto ilumina as linhas que ele gerou, e clicar numa linha
seleciona o objeto. Quem sabe qual comando pertence a qual campo é quem escreveu
o ZPL — por isso o mapa nasce aqui, e não de uma tentativa de reparsear o texto
no navegador.

### Estrutura do documento gerado

```
^XA                    abertura
^CI28                  codificação (do encoding da etiqueta)
^PW799 ^LL400 ^LH0,0   largura, altura, origem
[^MD ^PR ^POI]         só quando definidos explicitamente
  ^FXNome do campo^FS  comentário opcional
  ^FO40,80^A0N,48,0^FD...^FS
  ...
[^PQn,0,0,N]           só quando cópias > 1
^XZ                    fechamento
```

Parâmetros de impressão omitidos (`darkness`, `speed_ips` em `None`) **não geram
comando**, deixando prevalecer o que está gravado na impressora — que costuma
ser o ajuste correto para aquela mídia.

### Escape de conteúdo (`escaping.py`)

`^`, `~` e `_` quebram o parser da impressora; acentos são um problema clássico.
A estratégia: detectar se o texto precisa de tratamento e, só nesse caso, emitir
`^FH\` e converter os bytes para hexadecimal (`Ação` → `A_C3_A7_C3_A3o`). Textos
ASCII simples ficam legíveis no painel, que é o caso comum.

### Resiliência

`_safe_element_zpl` envolve cada elemento. Um objeto que estoure vira
`^FXerro em <nome>: <motivo>^FS` e o restante da etiqueta continua sendo gerado.
No editor o usuário produz estados inválidos o tempo todo enquanto digita — a
tela não pode ficar em branco por causa disso.

---

## 8. O catálogo: interface dirigida por metadados

**Esta é a decisão central do projeto.** O editor não tem um formulário escrito
para cada tipo de objeto. Ele pede `GET /api/catalog` ao iniciar e monta a
paleta e o painel de propriedades a partir da resposta.

```jsonc
{
  "elements": [{
    "type": "barcode",
    "label": "Codigo de barras",
    "icon": "|||",
    "category": "Codigos",
    "description": "...",          // vira o texto de ajuda no painel
    "zpl": "^BC / ^B3 / ^BE ...",  // mostrado ao usuário: ensina o comando
    "resize": { "width": null, "height": "height_mm",
                "uniform": null, "integer": false },
    "fields": [                    // cada um vira um widget
      { "name": "data", "label": "Dados", "widget": "text", "group": "Conteudo" },
      { "name": "height_mm", "label": "Altura das barras", "widget": "number",
        "unit": "mm", "min": 2, "max": 150, "step": 0.5, "group": "Aparencia" }
    ],
    "defaults": { /* elemento recém-criado, serializado */ }
  }],
  "common_fields": [ /* name, x_mm, y_mm, rotation */ ],
  "supported_dpi": [152, 203, 300, 600],
  "categories": ["Conteudo", "Codigos", "Formas"]
}
```

Widgets suportados: `text`, `textarea`, `number`, `select`, `switch`, `image`.

O catálogo vive em `app/catalog.py`, e **não** em `zpl_core`, porque rótulo,
ícone e faixa de valores são decisões de interface, não de domínio. Uma segunda
interface (um app desktop, digamos) traria o próprio catálogo sem duplicar o
modelo.

Dois testes protegem esse acoplamento, que quebraria em silêncio:
`test_campos_do_catalogo_existem_no_modelo` e
`test_regras_de_redimensionamento_apontam_para_campos_reais`.

---

## 9. Frontend

Módulos ES nativos, carregados direto pelo navegador. Sem bundler, sem
transpilação, sem `node_modules`.

| Módulo | Responsabilidade |
|---|---|
| `store.js` | Estado único, assinantes, histórico, rascunho em `localStorage` |
| `api.js` | Cliente HTTP; erros do servidor viram `ApiError` legível |
| `geometry.js` | Tamanhos e ímã. **Espelha** o cálculo do Python |
| `canvas.js` | Desenho dos elementos e todas as interações de mouse |
| `inspector.js` | Painel de propriedades gerado pelo catálogo |
| `panels.js` | Paleta e lista de camadas |
| `zplview.js` | Painel de ZPL: colorização e destaque bidirecional |
| `main.js` | Costura tudo: atalhos, zoom, diálogos, debounce |

### Elementos são DOM, não `<canvas>`

Com nós do DOM posicionados em absoluto ganhamos de graça hit-testing, cursores,
foco por teclado e — o que mais importa — **texto renderizado pelo navegador**,
muito mais fiel a uma fonte escalável do que qualquer desenho que faríamos à mão.
Códigos de barras e QR chegam como `<img>` gerados em Python.

### Histórico

Arrastar produz dezenas de atualizações por segundo; registrar cada uma faria
"desfazer" andar um pixel por vez. Por isso há dois caminhos:

- `store.edit(fn, {coalesce})` — edição discreta. `coalesce` funde alterações
  consecutivas no mesmo campo (digitar não gera 40 níveis de undo).
- `beginBatch()` / `live(fn)` / `endBatch()` — a interação inteira, do
  `pointerdown` ao `pointerup`, vira **um** passo. Um clique sem arrasto não
  entra no histórico, porque `endBatch` compara os estados antes de gravar.

O histórico guarda snapshots da etiqueta inteira (limite de 100). Uma etiqueta
tem dezenas de campos, não milhares: clonar é barato e elimina toda a classe de
bugs de undo baseado em comandos.

### Geometria espelhada — acoplamento consciente

`geometry.js::naturalSizeMm` e `barcodeModules` repetem as fórmulas de
`elements.py::size_mm` e `barcode_modules`. É duplicação deliberada: o canvas
precisa do tamanho a cada quadro do arrasto, e uma ida ao servidor por quadro
seria inviável.

**Se você mudar uma das fórmulas, mude a outra.** Os dois arquivos carregam
comentário apontando um para o outro. Se elas divergirem, a caixa desenhada na
tela e o aviso de "passou da borda" passam a discordar.

### Ímã e guias

`snapPosition` ajusta a posição arrastada para as referências mais próximas
dentro de 0,8 mm, nesta ordem: bordas e centro da etiqueta; bordas e centros dos
outros elementos. Sem referência por perto, cai na grade de 1 mm. Devolve também
as linhas-guia a desenhar — mostrar *por que* o objeto colou é o que faz o ímã
parecer inteligente em vez de teimoso. `Alt` desliga durante o arrasto.

---

## 10. Contrato HTTP

| Método | Rota | Para quê |
|---|---|---|
| `GET` | `/api/catalog` | Descreve os objetos; monta a interface inteira |
| `GET` | `/api/health` | Versão e se a impressão está habilitada |
| `POST` | `/api/zpl` | **A chamada do painel ao vivo**: ZPL + segmentos + avisos |
| `POST` | `/api/export/zpl` | Mesmo ZPL como arquivo `.zpl` para download |
| `GET` | `/api/preview/barcode` | PNG de código linear (cacheável) |
| `GET` | `/api/preview/qrcode` | PNG de QR |
| `GET` | `/api/preview/datamatrix` | Marcador de DataMatrix (§17) |
| `POST` | `/api/preview/image` | Imagem convertida para o bitmap 1 bit real |
| `GET` `POST` | `/api/templates` | Listar / salvar modelos |
| `GET` `DELETE` | `/api/templates/{slug}` | Abrir / excluir |
| `GET` | `/api/printers` | Impressoras configuradas + filas do Windows |
| `POST` | `/api/print` | Enviar à impressora (desabilitado por padrão) |

A etiqueta trafega como **dicionário livre**, validado por
`zpl_core.serialization`, que já é a autoridade sobre o formato. Pydantic cuida
só do que é genuinamente HTTP: envelopes, opções de render, parâmetros de
impressão. Espelhar o modelo inteiro em Pydantic criaria duas fontes da verdade
— e a garantia de que uma ficaria para trás.

**Códigos de erro:** `422` para etiqueta malformada (com a mensagem explicativa
da serialização), `404` para modelo/impressora inexistente, `403` para impressão
desabilitada, `502` para falha ao falar com a impressora.

Os previews **nunca** retornam erro por dado inválido: devolvem um PNG marcador.
Enquanto o usuário digita, o dado é inválido quase o tempo todo.

---

## 11. Validação

`validate(label) -> list[Issue]`, ordenada por gravidade:

| Gravidade | Significado |
|---|---|
| `error` | Não vai imprimir como o usuário espera |
| `warning` | Vai imprimir, mas provavelmente não é o desejado |
| `info` | Observação útil (campos variáveis detectados, etiqueta vazia) |

Cobre: comprimento e alfabeto por simbologia (EAN/UPC/ITF/Code 39), dados
vazios, barras finas demais para leitura, código baixo demais, fonte ilegível,
QR com módulo pequeno, e posição fora da etiqueta.

Dois cuidados que evitam falso positivo:

- **Placeholders não são validados como conteúdo final.** `{{ean}}` num EAN-13
  não é erro — o valor chega na impressão.
- **Tolerância de 0,5 mm na borda**, porque as larguras de texto e código são
  estimativas.

A validação **nunca impede** a geração. Quem decide se vale imprimir é a pessoa.

---

## 12. Persistência

Modelos são arquivos JSON em `templates_store/`, um por etiqueta. Arquivo em
disco em vez de banco por escolha: o time versiona no Git, copia para outra
máquina e abre num editor de texto quando precisa.

- `schema_version` no arquivo permite migrar formatos antigos; um arquivo de
  versão **mais nova** é recusado com mensagem clara.
- `slugify()` neutraliza o nome (`../../etc/passwd` → `etc-passwd`) e
  `TemplateStore._path` confere que o caminho resolvido continua dentro da pasta.
- Um arquivo corrompido não impede listar os outros.
- A desserialização é genérica: lê as anotações de tipo das dataclasses e
  converte. Adicionar um campo a um elemento **não** exige tocar em
  `serialization.py`. Campos desconhecidos são ignorados.

No navegador, o rascunho atual vai para `localStorage` a cada alteração, para
que um F5 acidental não perca o trabalho.

---

## 13. Impressão

Três caminhos, em `zpl_core/printing.py`:

1. **TCP 9100** (raw) — como praticamente toda Zebra de chão de fábrica recebe;
2. **Spooler do Windows** — exige `pywin32`; ausente, a mensagem de erro diz isso
   e aponta o envio por IP;
3. **Arquivo** — grava `.zpl` para conferência ou envio manual.

ZPL raw é via de mão única: não interpretamos resposta da impressora. O que
garantimos é erro claro quando o envio não acontece (timeout com o endereço,
conexão recusada).

**A impressão direta vem desligada** (`ETIQUETA_ALLOW_PRINTING=0`). É o único
ponto do sistema com efeito no mundo físico; habilitar deve ser decisão
consciente de quem instala. O router aceita apenas impressoras previamente
configuradas ou um endereço explícito digitado pelo usuário.

---

## 14. Testes

`uv run pytest` — 94 testes, sem rede e sem impressora.

| Arquivo | Cobre |
|---|---|
| `test_zpl_writer.py` | Formato exato dos comandos, escape, segmentos, resiliência |
| `test_serialization.py` | Ida e volta preserva o ZPL; erros explicáveis |
| `test_validation.py` | Cada regra, na gravidade certa |
| `test_api.py` | Contrato HTTP e a integridade do catálogo |

Alguns testes existem especificamente para travar acoplamentos que quebrariam em
silêncio:

- todo campo descrito no catálogo existe na dataclass correspondente;
- toda regra de redimensionamento aponta para um campo real;
- os `defaults` de todo tipo do catálogo geram ZPL válido — ou seja, arrastar
  qualquer objeto da paleta funciona na hora;
- todo tipo registrado sobrevive à ida e volta pelo JSON.

A interface foi verificada em Chrome headless via Playwright (arrasto,
redimensionamento, ZPL ao vivo, destaque bidirecional, desfazer, salvar/abrir).
Esses roteiros são exploratórios e ficam fora da suíte automatizada — eles
dependem de servidor e navegador reais.

---

## 15. Como estender

### Adicionar um objeto ZPL novo

1. **`zpl_core/elements.py`** — crie o dataclass:
   ```python
   @dataclass(slots=True, kw_only=True)
   class EllipseElement(Element):
       type: ClassVar[str] = "ellipse"
       width_mm: float = 20.0
       height_mm: float = 10.0
       thickness_mm: float = 0.4

       def to_zpl(self, ctx: RenderContext) -> list[str]:
           t = max(1, ctx.dots(self.thickness_mm))
           return [f"{self._origin(ctx)}^GE{ctx.dots(self.width_mm)},"
                   f"{ctx.dots(self.height_mm)},{t},{self.color}^FS"]

       def size_mm(self, resolution=None) -> tuple[float, float]:
           return (self.width_mm, self.height_mm)
   ```
2. Registre em `ELEMENT_TYPES` (fim do arquivo).
3. **`app/catalog.py`** — descreva `label`, `icon`, `category`, `zpl`,
   `resize` e `fields`.
4. **`web/js/geometry.js`** — só se o tamanho não for `width_mm`/`height_mm`.
5. **`web/js/canvas.js`** — só se precisar de desenho próprio; formas simples já
   caem no caminho genérico.
6. Teste e **atualize a tabela do §6 deste documento**.

Os passos 4 e 5 costumam ser desnecessários. Nenhum outro arquivo muda.

### Adicionar uma validação

Uma função `_check_*` em `validation.py` e uma linha em `_check_element`.

### Adicionar um widget de propriedade

Uma entrada no objeto `construir` em `inspector.js` e um helper em
`catalog.py`. Documente o widget no §8.

---

## 16. Decisões registradas

### ADR-1 — O ZPL é gerado só em Python

**Contexto.** O painel ao vivo precisa atualizar a cada tecla.
**Alternativa rejeitada.** Gerar o ZPL em JavaScript para latência zero.
**Decisão.** Gerar no servidor, com debounce de 120 ms.
**Porquê.** Em rede local a latência é imperceptível, e em troca existe **uma**
implementação do ZPL — a mesma que alimenta exportação, impressão e scripts de
lote. Duas implementações divergiriam, e a divergência apareceria na impressora,
que é o lugar mais caro de descobrir um bug.

### ADR-2 — Interface dirigida pelo catálogo

**Contexto.** O requisito é suportar "qualquer objeto que o ZPL aceita".
**Alternativa rejeitada.** Um componente de formulário por tipo, em JavaScript.
**Decisão.** Metadados em Python descrevem cada objeto; a interface se monta.
**Porquê.** Suportar um comando novo passa a custar uma dataclass e uma entrada
de catálogo, sem tocar em JavaScript. O custo é indireção — mitigado pelos
testes de integridade do §14.

### ADR-3 — Elementos como DOM, não `<canvas>`

**Alternativa rejeitada.** Pintar tudo num `<canvas>` com hit-testing manual.
**Porquê.** Texto renderizado pelo navegador é muito mais fiel a uma fonte
escalável, e ganhamos cursores, foco e acessibilidade sem escrever nada. O custo
— menos controle sobre o desenho — não pesa numa etiqueta com dezenas de
elementos.

### ADR-4 — Frontend sem build

**Alternativa rejeitada.** React/Vue com bundler.
**Porquê.** A ferramenta precisa subir em máquina de produção com um comando. Um
pipeline de build seria mais infraestrutura que o app inteiro. A tela é única e
o estado é pequeno; um store de 200 linhas resolve.

### ADR-5 — Modelo em milímetros, nunca em dots

**Porquê.** Dots dependem do DPI. Guardar em mm permite trocar a impressora de
203 para 300 dpi e ter a etiqueta reposicionada corretamente, sem migração de
dados. A conversão fica confinada a `units.py`.

### ADR-6 — Etiqueta trafega como dicionário, não como modelo Pydantic

**Porquê.** `zpl_core.serialization` já é a autoridade sobre o formato.
Espelhar o modelo em Pydantic criaria duas definições do mesmo esquema, e uma
delas ficaria desatualizada.

### ADR-7 — `uv` como gerenciador de ambiente

**Alternativa rejeitada.** `pip` + `requirements.txt`.
**Decisão.** `pyproject.toml` + `uv.lock`, com `uv sync` e `uv run`.
**Porquê.** O lock fixa as versões exatas para todos os ambientes — a suíte que
passa aqui passa na máquina de produção. `uv run` dispensa ativar venv, o que
elimina toda uma categoria de "funciona na minha máquina". Os arquivos
`requirements*.txt` foram removidos para não haver duas listas de dependências
divergindo.

### ADR-8 — Camadas em vez de MVC

**Alternativa rejeitada.** Organizar o backend como Model / View / Controller.
**Porquê.** Não há renderização no servidor: os routers devolvem JSON e nunca
escolhem uma view, então o "V" seria um rótulo vazio. E no cliente não existe
coordenação entre painéis para um controller mediar. O detalhamento, com a
tabela de correspondência, está em §3.4.

---

## 17. Limites conhecidos

- **O preview é aproximação, não simulação.** Texto e formas são desenhados pelo
  navegador; códigos vêm de bibliotecas Python. A métrica exata das fontes
  internas da Zebra só a impressora conhece. Para homologar um modelo, imprima
  uma unidade.
- **DataMatrix aparece como marcador.** O `^BX` gerado está correto e imprime;
  falta um encoder DataMatrix puro-Python para desenhar o preview. Sinalizado
  como aproximado na tela, para não enganar.
- **Code 93 não tem preview local** (`python-barcode` não o implementa). O ZPL
  está correto; a tela mostra um marcador com as proporções.
- **Rotação no preview** gira em torno da origem do campo. É o comportamento do
  `^FO` na maioria dos casos, mas campos rotacionados merecem impressão de teste.
- **Seleção é de um objeto por vez.** Não há seleção múltipla nem agrupamento.
- **Sem multiusuário.** `TemplateStore` não trata escrita concorrente; dois
  navegadores salvando o mesmo slug, o último vence.

---

## 18. Ambiente e ferramentas

Gerenciados por **[uv](https://docs.astral.sh/uv/)**.

```bash
uv sync              # cria .venv e instala exatamente o que está no lock
uv run python run.py # sobe o editor (não precisa ativar venv)
uv run pytest        # testes
uv add <pacote>      # adiciona dependência e atualiza o lock
uv lock --upgrade    # atualiza as versões dentro das faixas do pyproject
```

- `pyproject.toml` declara as dependências e as faixas aceitas.
- `uv.lock` fixa as versões exatas e **é versionado no Git**.
- O grupo `dev` (`[dependency-groups]`) traz pytest, httpx e playwright; entra
  automaticamente no `uv sync` e fica de fora de uma instalação de produção
  (`uv sync --no-dev`).

**Configuração** por variável de ambiente ou `.env` (veja `.env.example`):
`ETIQUETA_HOST`, `ETIQUETA_PORT`, `ETIQUETA_TEMPLATES_DIR`,
`ETIQUETA_ALLOW_PRINTING`, `ETIQUETA_PRINTERS`.

Python 3.11+ (usa `StrEnum`, `match` e `X | None` em anotações resolvidas em
tempo de execução).

### 18.1 Conjunto de documentos

| Arquivo | Público | Idioma |
|---|---|---|
| `README.md` / `.en.md` / `.es.md` | Quem vai **usar** a ferramenta | pt-BR / en / es |
| `DESIGN.md` (este) | Quem vai **mexer** no código | pt-BR |
| `.env.example` | Quem vai **instalar** | pt-BR |

Os três READMEs cobrem o mesmo conteúdo e precisam ser atualizados juntos —
um README traduzido desatualizado engana exatamente o leitor que menos consegue
conferir no código. O `DESIGN.md` fica só em português por decisão de custo: ele
muda com frequência e o público é o time que mantém o projeto.

**A interface da aplicação está em português apenas.** Os READMEs traduzidos
dizem isso de forma explícita. Internacionalizar a interface exigiria extrair os
textos de `web/js/` e de `app/catalog.py` (que carrega os rótulos dos campos) —
o catálogo já é o ponto natural para isso, porque concentra quase toda a
terminologia visível.

### 18.2 Licença

MIT (`LICENSE`), declarada também em `pyproject.toml` (`license = "MIT"`). Todas
as dependências de produção são permissivas — MIT, BSD-3-Clause e MIT-CMU —,
então nada é herdado que restrinja o uso.

Em exemplos e testes, domínios seguem a RFC 2606 (`example.com`), reservada para
documentação: nenhum exemplo aponta para um domínio real de terceiros.
