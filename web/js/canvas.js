/**
 * Canvas da etiqueta: desenho dos elementos e todas as interações de mouse.
 *
 * Decisão central: os elementos são nós do DOM posicionados em absoluto, não um
 * `<canvas>` pintado à mão. Com DOM ganhamos de graça hit-testing, cursor,
 * acessibilidade e -- o que mais importa aqui -- texto renderizado pelo próprio
 * navegador, que é bem mais fiel a uma fonte escalável do que qualquer
 * aproximação que desenharíamos.
 *
 * Códigos de barras e QR vêm como <img> gerados no servidor, em Python: o
 * desenho de barras é território de biblioteca testada, não de código novo.
 */

import { api } from './api.js';
import { store } from './store.js';
import { PX_PER_MM, boundsMm, clamp, round2, sizeMm, snapPosition } from './geometry.js';

const sheet = document.getElementById('sheet');
const layer = document.getElementById('elements');
const guidesLayer = document.getElementById('guides');
const gridLayer = document.getElementById('sheet-grid');
const scroll = document.getElementById('scroll');
const viewport = document.getElementById('viewport');
const rulerTop = document.getElementById('ruler-top');
const rulerLeft = document.getElementById('ruler-left');

/** Passo da grade e do ímã, em mm. */
const GRID_MM = 1;
/** Passo fino ao mover com as setas do teclado. */
export const NUDGE_MM = 0.5;

/** Nós já criados, por id de elemento -- evita recriar <img> a cada quadro. */
const nodes = new Map();

let scale = PX_PER_MM;
let onCommit = () => {};

// ---------------------------------------------------------------------------
// Desenho
// ---------------------------------------------------------------------------

export function initCanvas({ onChange } = {}) {
  onCommit = onChange || (() => {});
  installDragAndDrop();
  installPointerHandlers();
  installCursorTracking();
}

export function setScale(zoom) {
  scale = PX_PER_MM * zoom;
}

export function render(state) {
  const { label, options } = state;
  scale = PX_PER_MM * state.zoom;

  sheet.style.width = `${label.width_mm * scale}px`;
  sheet.style.height = `${label.height_mm * scale}px`;

  renderGrid(label, options.grid);
  renderRulers(label, options.rulers);

  const vivos = new Set();
  label.elements.forEach((el, indice) => {
    vivos.add(el.id);
    let node = nodes.get(el.id);
    if (!node) {
      node = criarNo(el);
      nodes.set(el.id, node);
      layer.appendChild(node);
    }
    atualizarNo(node, el, label, state, indice);
  });

  for (const [id, node] of nodes) {
    if (!vivos.has(id)) {
      node.remove();
      nodes.delete(id);
    }
  }
}

function criarNo(el) {
  const node = document.createElement('div');
  node.className = 'el';
  node.dataset.id = el.id;
  node.dataset.type = el.type;
  return node;
}

function atualizarNo(node, el, label, state, indice) {
  const { w, h } = sizeMm(el, label.dpi);
  const selecionado = state.selection === el.id;

  node.style.left = `${el.x_mm * scale}px`;
  node.style.top = `${el.y_mm * scale}px`;
  node.style.zIndex = String(indice + 1);
  node.classList.toggle('is-selected', selecionado);
  node.classList.toggle('is-invisible', !el.visible);
  node.classList.toggle('is-locked', !!el.locked);
  node.classList.toggle('has-error', temErro(state, el.id));

  // O tamanho da caixa vem da estimativa, exceto no texto solto, em que a
  // medida real do navegador é mais honesta do que qualquer fórmula.
  const soltoTexto = el.type === 'text' && !(el.block_width_mm > 0);
  node.style.width = soltoTexto ? 'auto' : `${w * scale}px`;
  node.style.height = soltoTexto ? 'auto' : `${h * scale}px`;

  node.style.transform = rotacaoCss(el);
  desenharConteudo(node, el, label, w, h);
  desenharAlcas(node, el, state, selecionado);
}

/** ZPL gira o campo em torno da própria origem (^FO); o CSS faz o mesmo. */
function rotacaoCss(el) {
  const graus = { N: 0, R: 90, I: 180, B: 270 }[el.rotation] || 0;
  return graus ? `rotate(${graus}deg)` : '';
}

function temErro(state, id) {
  return (state.zpl.issues || []).some((i) => i.element_id === id && i.severity === 'error');
}

function desenharConteudo(node, el, label, w, h) {
  switch (el.type) {
    case 'text':      return desenharTexto(node, el);
    case 'barcode':   return desenharImagem(node, el, api.barcodeUrl(
                        el.symbology, el.data, w * scale, h * scale, el.show_text, el.height_mm));
    case 'qrcode':    return desenharImagem(node, el, api.qrcodeUrl(
                        el.data, Math.max(w, h) * scale, el.error_correction));
    case 'datamatrix':return desenharImagem(node, el, api.datamatrixUrl(
                        el.data, Math.max(w, h) * scale));
    case 'box':       return desenharCaixa(node, el, label);
    case 'line':      return desenharLinha(node, el, label);
    case 'circle':    return desenharCirculo(node, el, label);
    case 'image':     return desenharImagemLocal(node, el, label);
    default:          return desenharDesconhecido(node, el);
  }
}

function conteudo(node, tag, className) {
  let filho = node.firstElementChild;
  if (!filho || filho.tagName.toLowerCase() !== tag || filho.className !== className) {
    node.textContent = '';
    filho = document.createElement(tag);
    filho.className = className;
    node.appendChild(filho);
  }
  return filho;
}

// -- texto ------------------------------------------------------------------

/* Fonte 0 do ZPL é uma sans-serif estreita; as demais são bitmap de largura
   fixa. Aproximar a família certa evita que o usuário posicione tudo na tela e
   descubra na impressão que o texto ocupa outro espaço. */
const FONTE_ESCALAVEL = '"Arial Narrow", "Liberation Sans Narrow", Arial, sans-serif';
const FONTE_FIXA = 'Consolas, "DejaVu Sans Mono", monospace';

function desenharTexto(node, el) {
  const bloco = el.block_width_mm > 0;
  const span = conteudo(node, 'div', bloco ? 'el__text el__text--block' : 'el__text');

  span.textContent = el.text || ' ';
  span.style.fontFamily = el.font === '0' ? FONTE_ESCALAVEL : FONTE_FIXA;
  span.style.fontSize = `${el.height_mm * scale}px`;
  span.style.textAlign = { L: 'left', C: 'center', R: 'right', J: 'justify' }[el.justification] || 'left';

  // width_mm > 0 no ZPL força a largura do caractere; no navegador o
  // equivalente honesto é esticar horizontalmente.
  const esticar = el.width_mm > 0 ? el.width_mm / (el.height_mm * 0.58) : 1;
  span.style.transform = esticar !== 1 ? `scaleX(${esticar})` : '';

  if (bloco) {
    span.style.width = `${el.block_width_mm * scale}px`;
    span.style.lineHeight = `${(el.height_mm + (el.block_line_spacing_mm || 0)) * scale}px`;
  } else {
    span.style.width = '';
    span.style.lineHeight = '1';
  }

  span.style.background = el.reverse ? '#000' : '';
  span.style.color = el.reverse ? '#fff' : '';
}

// -- imagens vindas do servidor ---------------------------------------------
function desenharImagem(node, el, url) {
  const img = conteudo(node, 'img', 'el__img');
  if (img.dataset.src !== url) {
    img.dataset.src = url;
    img.src = url;
    img.alt = '';
    img.draggable = false;
  }
}

// -- formas -----------------------------------------------------------------
function desenharCaixa(node, el, label) {
  const div = conteudo(node, 'div', 'el__shape');
  const espessura = el.thickness_mm * scale;
  const preenchido = el.thickness_mm * 2 >= Math.min(el.width_mm, el.height_mm);
  const cor = el.color === 'W' ? '#fff' : '#111';

  Object.assign(div.style, {
    width: '100%',
    height: '100%',
    boxSizing: 'border-box',
    border: preenchido ? 'none' : `${Math.max(1, espessura)}px solid ${cor}`,
    background: preenchido ? cor : 'transparent',
    borderRadius: el.rounding ? `${(el.rounding / 8) * 50}%` : '0',
  });
}

function desenharLinha(node, el, label) {
  const div = conteudo(node, 'div', 'el__shape');
  const cor = el.color === 'W' ? '#fff' : '#111';

  if (el.diagonal) {
    // Uma diagonal é um SVG; borda CSS não faz isso de forma honesta.
    div.innerHTML = '';
    const w = Math.max(el.width_mm, 0.1) * scale;
    const h = Math.max(el.height_mm, 0.1) * scale;
    const p = el.lean_right ? `0,${h} ${w},0` : `0,0 ${w},${h}`;
    div.innerHTML =
      `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">` +
      `<polyline points="${p}" stroke="${cor}" stroke-width="${Math.max(1, el.thickness_mm * scale)}" fill="none"/></svg>`;
    Object.assign(div.style, { width: '100%', height: '100%', background: 'transparent', border: 'none' });
  } else {
    div.innerHTML = '';
    Object.assign(div.style, { width: '100%', height: '100%', background: cor, border: 'none' });
  }
}

function desenharCirculo(node, el) {
  const div = conteudo(node, 'div', 'el__shape');
  const espessura = Math.max(1, el.thickness_mm * scale);
  const preenchido = el.thickness_mm * 2 >= el.diameter_mm;
  const cor = el.color === 'W' ? '#fff' : '#111';

  Object.assign(div.style, {
    width: '100%',
    height: '100%',
    boxSizing: 'border-box',
    borderRadius: '50%',
    border: preenchido ? 'none' : `${espessura}px solid ${cor}`,
    background: preenchido ? cor : 'transparent',
  });
}

// -- imagem do usuário ------------------------------------------------------

/* O preview mostra o bitmap 1-bit convertido pelo servidor, e não o arquivo
   original: é o que a impressora vai receber. A conversão é assíncrona, então
   guardamos uma assinatura para não repetir a chamada a cada quadro. */
function desenharImagemLocal(node, el, label) {
  if (!el.source) {
    const vazio = conteudo(node, 'div', 'el__placeholder');
    vazio.textContent = 'Clique para escolher a imagem';
    return;
  }

  const img = conteudo(node, 'img', 'el__img');
  const assinatura = [el.source.length, el.width_mm, el.height_mm, el.threshold,
                      el.dither, el.invert, label.dpi].join('|');

  if (img.dataset.sig === assinatura) return;
  img.dataset.sig = assinatura;

  api
    .imagePreview({
      source: el.source,
      width_mm: el.width_mm,
      height_mm: el.height_mm,
      dpi: label.dpi,
      threshold: el.threshold,
      dither: el.dither,
      invert: el.invert,
    })
    .then((url) => {
      if (img.dataset.sig !== assinatura) return URL.revokeObjectURL(url);
      if (img.dataset.blob) URL.revokeObjectURL(img.dataset.blob);
      img.dataset.blob = url;
      img.src = url;
    })
    .catch(() => {
      img.removeAttribute('src');
      img.dataset.sig = '';
    });
}

function desenharDesconhecido(node, el) {
  const div = conteudo(node, 'div', 'el__placeholder');
  div.textContent = el.type;
}

// ---------------------------------------------------------------------------
// Alças de redimensionamento
// ---------------------------------------------------------------------------

/** Quais alças fazem sentido, dado o que o catálogo diz que dá para mudar. */
function direcoes(spec) {
  if (!spec) return [];
  if (spec.uniform) return ['nw', 'ne', 'se', 'sw'];
  const podeW = !!spec.width;
  const podeH = !!spec.height;
  if (podeW && podeH) return ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
  if (podeH) return ['n', 's'];
  if (podeW) return ['e', 'w'];
  return [];
}

function desenharAlcas(node, el, state, selecionado) {
  node.querySelectorAll('.handle').forEach((h) => h.remove());
  if (!selecionado || el.locked) return;

  const spec = specDe(state, el.type);
  for (const dir of direcoes(spec)) {
    const alca = document.createElement('div');
    alca.className = 'handle';
    alca.dataset.dir = dir;
    node.appendChild(alca);
  }
}

function specDe(state, tipo) {
  return state.catalog?.elements.find((e) => e.type === tipo)?.resize || null;
}

// ---------------------------------------------------------------------------
// Grade, réguas e guias
// ---------------------------------------------------------------------------
function renderGrid(label, ligada) {
  if (!ligada) {
    gridLayer.style.background = 'none';
    return;
  }
  const passo = GRID_MM * scale;
  const forte = 10 * scale; // linha destacada a cada centímetro
  gridLayer.style.background = `
    repeating-linear-gradient(to right,  #0000000d 0 1px, transparent 1px ${passo}px),
    repeating-linear-gradient(to bottom, #0000000d 0 1px, transparent 1px ${passo}px),
    repeating-linear-gradient(to right,  #00000022 0 1px, transparent 1px ${forte}px),
    repeating-linear-gradient(to bottom, #00000022 0 1px, transparent 1px ${forte}px)`;
}

function renderRulers(label, ligadas) {
  viewport.classList.toggle('no-rulers', !ligadas);
  if (!ligadas) return;

  // Espaço entre números cresce com o zoom para as marcas nunca se colarem.
  const passo = scale > 6 ? 5 : scale > 3 ? 10 : 20;
  rulerTop.innerHTML = marcas(label.width_mm, passo, 'h');
  rulerLeft.innerHTML = marcas(label.height_mm, passo, 'v');
  posicionarReguas();
}

function marcas(totalMm, passo, eixo) {
  const partes = [];
  for (let mm = 0; mm <= totalMm; mm += passo) {
    const px = mm * scale;
    const lado = eixo === 'h' ? 'left' : 'top';
    partes.push(`<span class="ruler__tick" style="${lado}:${px}px;${eixo === 'h' ? 'height:6px' : 'width:6px'}"></span>`);
    partes.push(`<span class="ruler__label" style="${lado}:${px}px">${mm}</span>`);
  }
  return partes.join('');
}

/** As réguas acompanham a rolagem e a posição da folha dentro do palco. */
export function posicionarReguas() {
  const caixaFolha = sheet.getBoundingClientRect();
  const caixaScroll = scroll.getBoundingClientRect();
  const dx = caixaFolha.left - caixaScroll.left;
  const dy = caixaFolha.top - caixaScroll.top;
  rulerTop.style.transform = `translateX(${dx}px)`;
  rulerLeft.style.transform = `translateY(${dy}px)`;
}

function mostrarGuias(guias) {
  guidesLayer.innerHTML = guias
    .map((g) =>
      g.axis === 'v'
        ? `<div class="guide guide--v" style="left:${g.at * scale}px"></div>`
        : `<div class="guide guide--h" style="top:${g.at * scale}px"></div>`
    )
    .join('');
}

const limparGuias = () => (guidesLayer.innerHTML = '');

// ---------------------------------------------------------------------------
// Interação: mover e redimensionar
// ---------------------------------------------------------------------------
function pontoEmMm(evento) {
  const caixa = sheet.getBoundingClientRect();
  return {
    x: (evento.clientX - caixa.left) / scale,
    y: (evento.clientY - caixa.top) / scale,
  };
}

function installPointerHandlers() {
  sheet.addEventListener('pointerdown', (evento) => {
    const alca = evento.target.closest('.handle');
    const node = evento.target.closest('.el');

    if (!node) {
      store.select(null);
      return;
    }

    const el = store.state.label.elements.find((e) => e.id === node.dataset.id);
    if (!el) return;

    store.select(el.id);
    if (el.locked) return;

    evento.preventDefault();
    sheet.setPointerCapture(evento.pointerId);
    store.beginBatch();

    const inicio = pontoEmMm(evento);
    const contexto = {
      el,
      inicio,
      origem: { x: el.x_mm, y: el.y_mm },
      caixa: boundsMm(el, store.state.label.dpi),
      valores: { ...el },
      dir: alca?.dataset.dir || null,
      spec: specDe(store.state, el.type),
    };

    const mover = (e) => (contexto.dir ? redimensionar(e, contexto) : arrastar(e, contexto));
    const soltar = (e) => {
      sheet.releasePointerCapture(e.pointerId);
      sheet.removeEventListener('pointermove', mover);
      sheet.removeEventListener('pointerup', soltar);
      limparGuias();
      store.endBatch();
      onCommit();
    };

    sheet.addEventListener('pointermove', mover);
    sheet.addEventListener('pointerup', soltar);
  });
}

function arrastar(evento, ctx) {
  const atual = pontoEmMm(evento);
  const label = store.state.label;
  let x = ctx.origem.x + (atual.x - ctx.inicio.x);
  let y = ctx.origem.y + (atual.y - ctx.inicio.y);

  // Alt desliga o ímã: às vezes o usuário precisa de um valor fora da grade.
  const comIma = store.state.options.snap && !evento.altKey;
  if (comIma) {
    const outros = label.elements
      .filter((e) => e.id !== ctx.el.id && e.visible)
      .map((e) => boundsMm(e, label.dpi));
    const { w, h } = sizeMm(ctx.el, label.dpi);
    const ajuste = snapPosition({ x, y, w, h }, label, outros, GRID_MM);
    x = ajuste.x;
    y = ajuste.y;
    mostrarGuias(ajuste.guides);
  } else {
    limparGuias();
  }

  store.live((l) => {
    const alvo = l.elements.find((e) => e.id === ctx.el.id);
    alvo.x_mm = round2(x);
    alvo.y_mm = round2(y);
  }, ['live']);
}

function redimensionar(evento, ctx) {
  const atual = pontoEmMm(evento);
  const dx = atual.x - ctx.inicio.x;
  const dy = atual.y - ctx.inicio.y;
  const { dir, spec, caixa } = ctx;

  const oeste = dir.includes('w');
  const norte = dir.includes('n');
  const novaW = Math.max(0.5, caixa.w + (oeste ? -dx : dir.includes('e') || spec.uniform ? dx : 0));
  const novaH = Math.max(0.5, caixa.h + (norte ? -dy : dir.includes('s') || spec.uniform ? dy : 0));

  store.live((l) => {
    const alvo = l.elements.find((e) => e.id === ctx.el.id);

    if (spec.uniform) {
      // Campos em dots (ampliação do QR, módulo do DataMatrix) escalam em
      // proporção e são arredondados: valor fracionário não existe na cabeça.
      const fator = Math.max(novaW / caixa.w, novaH / caixa.h);
      const bruto = ctx.valores[spec.uniform] * fator;
      alvo[spec.uniform] = spec.integer ? Math.max(1, Math.round(bruto)) : round2(Math.max(0.5, bruto));
    } else {
      if (spec.width) alvo[spec.width] = round2(novaW);
      if (spec.height) alvo[spec.height] = round2(novaH);
    }

    // Arrastar pela borda superior/esquerda move a origem junto.
    if (oeste) alvo.x_mm = round2(ctx.origem.x + (caixa.w - novaW));
    if (norte) alvo.y_mm = round2(ctx.origem.y + (caixa.h - novaH));
  }, ['live']);
}

// ---------------------------------------------------------------------------
// Soltar um objeto vindo da paleta
// ---------------------------------------------------------------------------
function installDragAndDrop() {
  const permitir = (e) => {
    if (!e.dataTransfer.types.includes('application/x-zpl-element')) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    sheet.classList.add('is-dragover');
  };

  sheet.addEventListener('dragover', permitir);
  sheet.addEventListener('dragenter', permitir);
  sheet.addEventListener('dragleave', (e) => {
    if (!sheet.contains(e.relatedTarget)) sheet.classList.remove('is-dragover');
  });

  sheet.addEventListener('drop', (evento) => {
    evento.preventDefault();
    sheet.classList.remove('is-dragover');
    const tipo = evento.dataTransfer.getData('application/x-zpl-element');
    if (!tipo) return;
    const ponto = pontoEmMm(evento);
    addElement(tipo, ponto);
  });
}

/**
 * Insere um elemento novo. Sem posição, cai em um ponto livre perto do canto --
 * empilhar tudo em 0,0 é o comportamento que mais irrita em editores assim.
 */
export function addElement(tipo, ponto = null) {
  const state = store.state;
  const entrada = state.catalog.elements.find((e) => e.type === tipo);
  if (!entrada) return null;

  const novo = { ...structuredClone(entrada.defaults), id: novoId() };
  const label = state.label;

  if (ponto) {
    const { w, h } = sizeMm(novo, label.dpi);
    novo.x_mm = round2(clamp(ponto.x - w / 2, 0, Math.max(0, label.width_mm - w)));
    novo.y_mm = round2(clamp(ponto.y - h / 2, 0, Math.max(0, label.height_mm - h)));
  } else {
    const passo = 3 * (label.elements.length % 8);
    novo.x_mm = round2(clamp(4 + passo, 0, label.width_mm - 5));
    novo.y_mm = round2(clamp(4 + passo, 0, label.height_mm - 5));
  }

  store.edit((l) => l.elements.push(novo), { reasons: ['label'] });
  store.select(novo.id);
  onCommit();
  return novo;
}

function novoId() {
  return (crypto.randomUUID?.() || Math.random().toString(16).slice(2)).replace(/-/g, '').slice(0, 8);
}

// ---------------------------------------------------------------------------
// Posição do cursor na barra de status
// ---------------------------------------------------------------------------
function installCursorTracking() {
  const status = document.getElementById('status-cursor');
  const cursorTop = document.createElement('span');
  const cursorLeft = document.createElement('span');
  cursorTop.className = 'ruler__cursor';
  cursorLeft.className = 'ruler__cursor';
  rulerTop.appendChild(cursorTop);
  rulerLeft.appendChild(cursorLeft);

  sheet.addEventListener('pointermove', (evento) => {
    const { x, y } = pontoEmMm(evento);
    status.textContent = `${x.toFixed(1)} , ${y.toFixed(1)} mm`;
    cursorTop.style.left = `${x * scale}px`;
    cursorLeft.style.top = `${y * scale}px`;
  });

  sheet.addEventListener('pointerleave', () => {
    status.textContent = '—';
  });

  scroll.addEventListener('scroll', posicionarReguas, { passive: true });
}
