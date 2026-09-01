/**
 * Paleta de objetos e lista de camadas.
 *
 * Ambas são geradas a partir do catálogo do backend -- nenhuma lista de tipos
 * escrita à mão em JavaScript.
 */

import { store } from './store.js';
import { addElement } from './canvas.js';

const paleta = document.getElementById('palette');
const camadas = document.getElementById('layers');
const contador = document.getElementById('layer-count');

let onChange = () => {};

export function initPanels({ onChange: cb } = {}) {
  onChange = cb || (() => {});

  camadas.addEventListener('click', (evento) => {
    const item = evento.target.closest('.layer');
    if (!item) return;
    const id = item.dataset.id;
    const acao = evento.target.closest('[data-action]')?.dataset.action;

    if (!acao) {
      store.select(id);
      return;
    }

    // Olho e cadeado alteram o modelo, então entram no histórico.
    store.edit((label) => {
      const el = label.elements.find((e) => e.id === id);
      if (!el) return;
      if (acao === 'visibility') el.visible = !el.visible;
      if (acao === 'lock') el.locked = !el.locked;
    });
    onChange();
  });
}

// ---------------------------------------------------------------------------
// Paleta
// ---------------------------------------------------------------------------
export function renderPalette(catalog) {
  paleta.innerHTML = '';

  for (const categoria of catalog.categories) {
    const titulo = document.createElement('div');
    titulo.className = 'palette__group';
    titulo.textContent = categoria;
    paleta.appendChild(titulo);

    for (const entrada of catalog.elements.filter((e) => e.category === categoria)) {
      paleta.appendChild(itemDaPaleta(entrada));
    }
  }
}

function itemDaPaleta(entrada) {
  const item = document.createElement('button');
  item.className = 'palette__item';
  item.type = 'button';
  item.draggable = true;
  item.title = `${entrada.description}\nZPL: ${entrada.zpl}`;
  item.innerHTML =
    `<span class="palette__icon">${entrada.icon}</span>` +
    `<span class="palette__label">${entrada.label}</span>`;

  // Arrastar posiciona onde o usuário soltar; clicar insere em um ponto livre.
  item.addEventListener('dragstart', (evento) => {
    evento.dataTransfer.setData('application/x-zpl-element', entrada.type);
    evento.dataTransfer.effectAllowed = 'copy';
    item.classList.add('is-dragging');
  });
  item.addEventListener('dragend', () => item.classList.remove('is-dragging'));
  item.addEventListener('click', () => addElement(entrada.type));

  return item;
}

// ---------------------------------------------------------------------------
// Camadas
// ---------------------------------------------------------------------------
export function renderLayers(state) {
  const { label, selection } = state;
  contador.textContent = String(label.elements.length);

  if (!label.elements.length) {
    camadas.innerHTML = '<li class="empty">Nenhum objeto ainda.</li>';
    return;
  }

  const icones = Object.fromEntries(
    (state.catalog?.elements || []).map((e) => [e.type, e.icon])
  );

  // Lista de trás para frente: o que imprime por cima aparece no topo, como o
  // usuário enxerga a etiqueta.
  camadas.innerHTML = [...label.elements]
    .reverse()
    .map((el) => {
      const rotulo = el.name || resumoDe(el);
      return `
      <li class="layer ${el.id === selection ? 'is-selected' : ''} ${el.visible ? '' : 'is-hidden'}"
          data-id="${el.id}">
        <span class="layer__icon">${icones[el.type] || '?'}</span>
        <span class="layer__name" title="${escapar(rotulo)}">${escapar(rotulo)}</span>
        <button class="layer__btn ${el.locked ? 'is-on' : ''}" data-action="lock"
                title="${el.locked ? 'Destravar' : 'Travar posição'}">${el.locked ? '🔒' : '🔓'}</button>
        <button class="layer__btn" data-action="visibility"
                title="${el.visible ? 'Ocultar' : 'Mostrar'}">${el.visible ? '👁' : '🚫'}</button>
      </li>`;
    })
    .join('');
}

/** Sem nome definido, mostramos o conteúdo -- é como a pessoa reconhece o campo. */
function resumoDe(el) {
  const texto = el.text ?? el.data ?? '';
  if (texto) return texto.length > 28 ? `${texto.slice(0, 27)}…` : texto;
  return el.type;
}

const escapar = (texto) =>
  String(texto).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
