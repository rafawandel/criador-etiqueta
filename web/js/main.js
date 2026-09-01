/**
 * Ponto de entrada: liga estado, painéis e atalhos.
 *
 * O fluxo é sempre o mesmo, em uma direção só:
 *
 *   interação -> store -> assinantes redesenham -> (debounce) -> API gera ZPL
 *
 * Nenhum painel fala com outro painel. Isso mantém previsível o que redesenha
 * quando, que é o que evita travamento durante o arrasto.
 */

import { api, ApiError } from './api.js';
import { store, emptyLabel } from './store.js';
import { PX_PER_MM, clamp, sizeMm } from './geometry.js';
import { NUDGE_MM, addElement, initCanvas, posicionarReguas, render } from './canvas.js';
import {
  duplicar,
  initInspector,
  remover,
  renderInspector,
  renderLabelSettings,
} from './inspector.js';
import { initPanels, renderLayers, renderPalette } from './panels.js';
import { copiarZpl, initZplView, renderZpl } from './zplview.js';

const $ = (sel) => document.querySelector(sel);

/** Espera entre a última alteração e o pedido de ZPL ao servidor. */
const DEBOUNCE_ZPL_MS = 120;

// ---------------------------------------------------------------------------
// Avisos flutuantes
// ---------------------------------------------------------------------------
function toast(mensagem, tipo = '') {
  const alvo = document.getElementById('toasts');
  const balao = document.createElement('div');
  balao.className = `toast ${tipo ? `toast--${tipo}` : ''}`;
  balao.textContent = mensagem;
  alvo.appendChild(balao);
  setTimeout(() => balao.remove(), tipo === 'error' ? 6000 : 2600);
}

const aviseErro = (erro) =>
  toast(erro instanceof ApiError ? erro.message : String(erro?.message || erro), 'error');

// ---------------------------------------------------------------------------
// Geração de ZPL (debounced)
// ---------------------------------------------------------------------------
let timerZpl = null;
let requisicaoAtual = 0;

function agendarZpl() {
  clearTimeout(timerZpl);
  timerZpl = setTimeout(gerarZpl, DEBOUNCE_ZPL_MS);
}

async function gerarZpl() {
  const meu = ++requisicaoAtual;
  try {
    const resultado = await api.zpl(store.state.label, {
      comments: store.state.options.comments,
    });
    // Respostas fora de ordem sobrescreveriam um resultado mais novo.
    if (meu !== requisicaoAtual) return;
    store.set({ zpl: resultado }, ['zpl']);
  } catch (erro) {
    if (meu === requisicaoAtual) aviseErro(erro);
  }
}

// ---------------------------------------------------------------------------
// Assinatura central
// ---------------------------------------------------------------------------
function conectarPaineis() {
  store.subscribe((state, motivos) => {
    const mexeuNaEtiqueta = motivos.has('label') || motivos.has('live');

    if (mexeuNaEtiqueta || motivos.has('selection') || motivos.has('ui') || motivos.has('zpl')) {
      render(state);
    }
    if (mexeuNaEtiqueta || motivos.has('selection')) {
      renderInspector(state, motivos);
      renderLayers(state);
    }
    if (motivos.has('zpl') || motivos.has('selection')) {
      renderZpl(state, motivos);
    }
    if (motivos.has('history')) {
      $('#btn-undo').disabled = !store.canUndo;
      $('#btn-redo').disabled = !store.canRedo;
    }
    if (mexeuNaEtiqueta) {
      agendarZpl();
      atualizarBarraSuperior(state);
    }
    atualizarStatus(state);
  });
}

function atualizarBarraSuperior(state) {
  const { label } = state;
  if (document.activeElement !== $('#label-name')) $('#label-name').value = label.name;
  if (document.activeElement !== $('#label-width')) $('#label-width').value = label.width_mm;
  if (document.activeElement !== $('#label-height')) $('#label-height').value = label.height_mm;
  $('#label-dpi').value = label.dpi;
}

function atualizarStatus(state) {
  const el = state.label.elements.find((e) => e.id === state.selection);
  $('#status-selection').textContent = el
    ? `${el.name || el.type} · ${el.x_mm} , ${el.y_mm} mm`
    : 'Nenhum objeto selecionado';
  $('#status-size').textContent =
    `${state.label.width_mm} × ${state.label.height_mm} mm @ ${state.label.dpi} dpi`;
}

// ---------------------------------------------------------------------------
// Barra superior
// ---------------------------------------------------------------------------
function ligarBarraSuperior(catalog) {
  const dpi = $('#label-dpi');
  dpi.innerHTML = catalog.supported_dpi
    .map((v) => `<option value="${v}">${v} dpi</option>`)
    .join('');

  $('#label-name').addEventListener('input', (e) => {
    store.edit((l) => (l.name = e.target.value), { coalesce: 'label:name', reasons: ['label'] });
  });

  const dimensao = (seletor, campo) =>
    $(seletor).addEventListener('change', (e) => {
      const valor = clamp(parseFloat(e.target.value) || 1, 1, 500);
      e.target.value = valor;
      store.edit((l) => (l[campo] = valor));
    });

  dimensao('#label-width', 'width_mm');
  dimensao('#label-height', 'height_mm');

  dpi.addEventListener('change', (e) => {
    store.edit((l) => (l.dpi = parseInt(e.target.value, 10)));
  });

  $('#btn-undo').addEventListener('click', () => store.undo());
  $('#btn-redo').addEventListener('click', () => store.redo());
  $('#btn-new').addEventListener('click', novaEtiqueta);
  $('#btn-open').addEventListener('click', abrirDialogoModelos);
  $('#btn-save').addEventListener('click', salvarModelo);
  $('#btn-export').addEventListener('click', () =>
    api.download(store.state.label, store.state.options.comments).catch(aviseErro)
  );
  $('#btn-print').addEventListener('click', abrirDialogoImpressao);

  $('#btn-copy').addEventListener('click', async () => {
    toast((await copiarZpl()) ? 'ZPL copiado.' : 'Não foi possível copiar.', 'ok');
  });

  $('#opt-comments').addEventListener('change', (e) => {
    store.state.options.comments = e.target.checked;
    gerarZpl();
  });
}

// ---------------------------------------------------------------------------
// Barra do palco: zoom, grade, alinhamento
// ---------------------------------------------------------------------------
const ZOOMS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8];

function aplicarZoom(zoom) {
  store.set({ zoom: clamp(zoom, 0.1, 12) }, ['ui']);
  $('#zoom-level').textContent = `${Math.round(store.state.zoom * 100)}%`;
  requestAnimationFrame(posicionarReguas);
}

function zoomVizinho(direcao) {
  const atual = store.state.zoom;
  const lista = direcao > 0 ? ZOOMS : [...ZOOMS].reverse();
  const proximo = lista.find((z) => (direcao > 0 ? z > atual + 0.001 : z < atual - 0.001));
  aplicarZoom(proximo ?? atual);
}

function ajustarNaJanela() {
  const area = document.getElementById('scroll').getBoundingClientRect();
  const { width_mm, height_mm } = store.state.label;
  const folga = 64;
  const zoom = Math.min(
    (area.width - folga) / (width_mm * PX_PER_MM),
    (area.height - folga) / (height_mm * PX_PER_MM)
  );
  aplicarZoom(zoom);
}

function ligarBarraDoPalco() {
  $('#zoom-in').addEventListener('click', () => zoomVizinho(+1));
  $('#zoom-out').addEventListener('click', () => zoomVizinho(-1));
  $('#zoom-fit').addEventListener('click', ajustarNaJanela);

  for (const [id, chave] of [['#opt-grid', 'grid'], ['#opt-snap', 'snap'], ['#opt-rulers', 'rulers']]) {
    $(id).addEventListener('change', (e) => {
      store.state.options[chave] = e.target.checked;
      store.set({}, ['ui']);
    });
  }

  const alinhar = (fn) => () => {
    const id = store.state.selection;
    if (!id) return toast('Selecione um objeto primeiro.');
    store.edit((label) => {
      const el = label.elements.find((e) => e.id === id);
      if (el) fn(el, label);
    });
  };

  // O alinhamento usa a caixa estimada do elemento -- a mesma que o canvas
  // desenha, então o resultado bate com o que se vê.
  $('#align-left').addEventListener('click', alinhar((el) => (el.x_mm = 0)));
  $('#align-vcenter').addEventListener('click', alinhar((el, label) => {
    el.y_mm = arredondar((label.height_mm - medir(el, label).h) / 2);
  }));
  $('#align-hcenter').addEventListener('click', alinhar((el, label) => {
    el.x_mm = arredondar((label.width_mm - medir(el, label).w) / 2);
  }));
  $('#align-right').addEventListener('click', alinhar((el, label) => {
    el.x_mm = arredondar(label.width_mm - medir(el, label).w);
  }));

  // Ctrl + roda amplia em torno do cursor, como em qualquer editor gráfico.
  document.getElementById('scroll').addEventListener(
    'wheel',
    (evento) => {
      if (!evento.ctrlKey) return;
      evento.preventDefault();
      zoomVizinho(evento.deltaY < 0 ? +1 : -1);
    },
    { passive: false }
  );
}

const medir = (el, label) => sizeMm(el, label.dpi);
const arredondar = (v) => Math.round(Math.max(0, v) * 100) / 100;

// ---------------------------------------------------------------------------
// Abas do painel de propriedades
// ---------------------------------------------------------------------------
function ligarAbas() {
  for (const aba of document.querySelectorAll('.tab')) {
    aba.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((t) => t.classList.remove('is-active'));
      aba.classList.add('is-active');
      $('#tab-props').classList.toggle('is-hidden', aba.dataset.tab !== 'props');
      $('#tab-label').classList.toggle('is-hidden', aba.dataset.tab !== 'label');
      if (aba.dataset.tab === 'label') renderLabelSettings(store.state);
    });
  }
}

// ---------------------------------------------------------------------------
// Teclado
// ---------------------------------------------------------------------------
function ligarTeclado() {
  document.addEventListener('keydown', (evento) => {
    const digitando = /^(INPUT|TEXTAREA|SELECT)$/.test(evento.target.tagName);

    if (evento.key === 'Escape') {
      evento.target.blur?.();
      store.select(null);
      return;
    }
    if (digitando) return;

    const ctrl = evento.ctrlKey || evento.metaKey;
    const id = store.state.selection;

    if (ctrl && evento.key.toLowerCase() === 'z') {
      evento.preventDefault();
      evento.shiftKey ? store.redo() : store.undo();
      return;
    }
    if (ctrl && evento.key.toLowerCase() === 'y') {
      evento.preventDefault();
      store.redo();
      return;
    }
    if (ctrl && evento.key.toLowerCase() === 'd' && id) {
      evento.preventDefault();
      duplicar(id);
      return;
    }
    if (ctrl && evento.key.toLowerCase() === 's') {
      evento.preventDefault();
      salvarModelo();
      return;
    }
    if ((evento.key === 'Delete' || evento.key === 'Backspace') && id) {
      evento.preventDefault();
      remover(id);
      return;
    }

    // Setas empurram o objeto. Shift usa passo grosso, para atravessar a
    // etiqueta sem 40 toques.
    const direcoes = {
      ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
    };
    if (direcoes[evento.key] && id) {
      evento.preventDefault();
      const [dx, dy] = direcoes[evento.key];
      const passo = evento.shiftKey ? NUDGE_MM * 10 : NUDGE_MM;
      store.edit(
        (label) => {
          const el = label.elements.find((e) => e.id === id);
          if (!el || el.locked) return;
          el.x_mm = arredondar(el.x_mm + dx * passo);
          el.y_mm = arredondar(el.y_mm + dy * passo);
        },
        { coalesce: `nudge:${id}` }
      );
    }
  });
}

// ---------------------------------------------------------------------------
// Modelos salvos
// ---------------------------------------------------------------------------
function novaEtiqueta() {
  if (store.state.dirty && !confirm('Descartar as alterações não salvas?')) return;
  store.replaceLabel(emptyLabel());
  gerarZpl();
  toast('Etiqueta em branco criada.');
}

async function salvarModelo() {
  try {
    const { slug } = await api.templates.save(store.state.label);
    store.state.dirty = false;
    toast(`Modelo salvo como "${slug}".`, 'ok');
  } catch (erro) {
    aviseErro(erro);
  }
}

async function abrirDialogoModelos() {
  const dialogo = $('#dialog-open');
  const lista = $('#template-list');
  lista.innerHTML = '<li class="empty">Carregando…</li>';
  dialogo.showModal();

  try {
    const modelos = await api.templates.list();
    lista.innerHTML = modelos.length
      ? modelos
          .map(
            (m) => `
        <li data-slug="${m.slug}">
          <div class="template-list__name">
            <div>${m.name}</div>
            <div class="template-list__meta">
              ${m.width_mm} × ${m.height_mm} mm · ${m.dpi} dpi · ${m.element_count} objeto(s)
            </div>
          </div>
          <button class="btn btn--danger" data-remove="${m.slug}">Excluir</button>
        </li>`
          )
          .join('')
      : '<li class="empty">Nenhum modelo salvo ainda.</li>';
  } catch (erro) {
    lista.innerHTML = '<li class="empty">Não foi possível listar os modelos.</li>';
    aviseErro(erro);
  }

  lista.onclick = async (evento) => {
    const excluir = evento.target.closest('[data-remove]');
    if (excluir) {
      if (!confirm(`Excluir o modelo "${excluir.dataset.remove}"?`)) return;
      try {
        await api.templates.remove(excluir.dataset.remove);
        excluir.closest('li').remove();
        toast('Modelo excluído.');
      } catch (erro) {
        aviseErro(erro);
      }
      return;
    }

    const item = evento.target.closest('[data-slug]');
    if (!item) return;
    try {
      store.replaceLabel(await api.templates.get(item.dataset.slug));
      gerarZpl();
      dialogo.close();
      ajustarNaJanela();
      toast('Modelo aberto.');
    } catch (erro) {
      aviseErro(erro);
    }
  };
}

// ---------------------------------------------------------------------------
// Impressão
// ---------------------------------------------------------------------------
async function abrirDialogoImpressao() {
  const dialogo = $('#dialog-print');
  const form = $('#print-form');
  const placeholders = store.state.zpl.placeholders || [];

  form.innerHTML = '<p class="field__help">Carregando impressoras…</p>';
  dialogo.showModal();

  let impressoras = [];
  try {
    impressoras = await api.printers();
  } catch (erro) {
    aviseErro(erro);
  }

  form.innerHTML = `
    <div class="field">
      <label class="field__label" for="pr-printer">Impressora</label>
      ${
        impressoras.length
          ? `<select id="pr-printer">${impressoras
              .map((p) => `<option value="${p.name}">${p.name}${p.address ? ` — ${p.address}` : ''}</option>`)
              .join('')}</select>`
          : `<input id="pr-printer" type="text" placeholder="192.168.0.50:9100">
             <p class="field__help">Nenhuma impressora configurada. Informe o IP e a porta da Zebra.</p>`
      }
    </div>
    <div class="field">
      <label class="field__label" for="pr-copies">Quantidade</label>
      <input id="pr-copies" type="number" min="1" max="999" value="1">
    </div>
    ${
      placeholders.length
        ? `<div class="group"><div class="group__title">Campos variáveis</div><div class="group__body">${placeholders
            .map(
              (nome) => `
          <div class="field">
            <label class="field__label" for="pr-var-${nome}">${nome}</label>
            <input id="pr-var-${nome}" data-var="${nome}" type="text" placeholder="valor de ${nome}">
          </div>`
            )
            .join('')}</div></div>`
        : ''
    }`;

  $('#btn-print-confirm').onclick = async () => {
    const impressora = $('#pr-printer')?.value?.trim();
    if (!impressora) return toast('Informe a impressora.', 'error');

    const dados = {};
    for (const campo of form.querySelectorAll('[data-var]')) dados[campo.dataset.var] = campo.value;

    try {
      const resposta = await api.print(store.state.label, impressora, {
        data: dados,
        copies: parseInt($('#pr-copies').value, 10) || 1,
      });
      dialogo.close();
      toast(resposta.message, 'ok');
    } catch (erro) {
      aviseErro(erro);
    }
  };
}

function ligarDialogos() {
  for (const botao of document.querySelectorAll('[data-close]')) {
    botao.addEventListener('click', () => botao.closest('dialog').close());
  }
}

// ---------------------------------------------------------------------------
// Etiqueta de exemplo, para a tela não abrir vazia na primeira visita
// ---------------------------------------------------------------------------
function etiquetaExemplo() {
  const label = emptyLabel();
  label.name = 'Exemplo — produto';
  label.elements = [
    { type: 'box', id: 'ex000001', name: 'Moldura', x_mm: 2, y_mm: 2, rotation: 'N', visible: true,
      locked: false, width_mm: 96, height_mm: 46, thickness_mm: 0.4, color: 'B', rounding: 2 },
    { type: 'text', id: 'ex000002', name: 'Empresa', x_mm: 6, y_mm: 5, rotation: 'N', visible: true,
      locked: false, text: 'ACME INDUSTRIAL', font: '0', height_mm: 6, width_mm: 0, reverse: false,
      block_width_mm: 0, block_max_lines: 1, block_line_spacing_mm: 0, justification: 'L' },
    { type: 'line', id: 'ex000003', name: 'Divisória', x_mm: 6, y_mm: 13, rotation: 'N', visible: true,
      locked: false, width_mm: 88, height_mm: 0, thickness_mm: 0.3, color: 'B', diagonal: false,
      lean_right: true },
    { type: 'text', id: 'ex000004', name: 'Produto', x_mm: 6, y_mm: 16, rotation: 'N', visible: true,
      locked: false, text: 'Produto: {{produto}}', font: '0', height_mm: 3.5, width_mm: 0,
      reverse: false, block_width_mm: 0, block_max_lines: 1, block_line_spacing_mm: 0, justification: 'L' },
    { type: 'barcode', id: 'ex000005', name: 'EAN', x_mm: 6, y_mm: 22, rotation: 'N', visible: true,
      locked: false, symbology: 'ean13', data: '7891234567895', height_mm: 14,
      module_width_dots: 2, wide_ratio: 3, show_text: true, text_above: false, check_digit: false },
    { type: 'qrcode', id: 'ex000006', name: 'Rastreio', x_mm: 74, y_mm: 20, rotation: 'N',
      visible: true, locked: false, data: 'https://example.com/lote/{{lote}}', magnification: 4,
      error_correction: 'M', model: 2 },
  ];
  return label;
}

// ---------------------------------------------------------------------------
// Inicialização
// ---------------------------------------------------------------------------
async function iniciar() {
  try {
    const catalog = await api.catalog();
    store.state.catalog = catalog;

    renderPalette(catalog);
    ligarBarraSuperior(catalog);
  } catch (erro) {
    aviseErro(erro);
    return;
  }

  initCanvas({ onChange: agendarZpl });
  initInspector({ onChange: agendarZpl });
  initPanels({ onChange: agendarZpl });
  initZplView();
  ligarBarraDoPalco();
  ligarAbas();
  ligarTeclado();
  ligarDialogos();
  conectarPaineis();

  const rascunho = store.loadAutosave();
  store.replaceLabel(rascunho || etiquetaExemplo());

  ajustarNaJanela();
  await gerarZpl();

  window.addEventListener('resize', posicionarReguas);
  window.addEventListener('beforeunload', (evento) => {
    if (!store.state.dirty) return;
    evento.preventDefault();
    evento.returnValue = '';
  });
}

iniciar();
