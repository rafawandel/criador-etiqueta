/**
 * Painel do ZPL ao vivo.
 *
 * Este painel é o diferencial da ferramenta: o usuário vê o código nascer
 * enquanto monta a etiqueta. Para que ele seja aprendizado e não decoração,
 * a ligação entre desenho e código vai nos dois sentidos --
 *
 *   selecionar um objeto  -> destaca as linhas que ele gerou;
 *   clicar em uma linha   -> seleciona o objeto correspondente.
 *
 * O mapa que liga linha a elemento vem pronto do backend (`ZplDocument.segments`),
 * porque quem sabe qual comando pertence a qual campo é quem escreveu o ZPL.
 */

import { store } from './store.js';

const code = document.getElementById('zpl-code');
const view = document.getElementById('zpl-view');
const tamanho = document.getElementById('zpl-size');
const dots = document.getElementById('zpl-dots');
const listaAvisos = document.getElementById('issues');

const escapar = (texto) =>
  texto.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/**
 * Colorização por tipo de token. Um bloco monocromático de ZPL é ilegível;
 * separar comando, número e conteúdo já resolve 90% da leitura.
 */
function colorir(linha) {
  if (linha.startsWith('^FX')) return `<span class="tok-cmt">${escapar(linha)}</span>`;

  const corte = linha.indexOf('^FD');
  const comandos = corte >= 0 ? linha.slice(0, corte) : linha;
  const dados = corte >= 0 ? linha.slice(corte) : '';

  let html = escapar(comandos)
    .replace(/\^([A-Z@][A-Z0-9@]?)/g, '<span class="tok-cmd">^$1</span>')
    .replace(/(?<![\w-])(\d+(?:\.\d+)?)/g, '<span class="tok-num">$1</span>');

  if (dados) {
    const fim = dados.indexOf('^FS');
    const conteudo = fim >= 0 ? dados.slice(3, fim) : dados.slice(3);
    const rabo = fim >= 0 ? dados.slice(fim) : '';
    html +=
      '<span class="tok-cmd">^FD</span>' +
      `<span class="tok-data">${escapar(conteudo)}</span>` +
      escapar(rabo).replace(/\^([A-Z@][A-Z0-9@]?)/g, '<span class="tok-cmd">^$1</span>');
  }
  return html;
}

let ultimoZpl = '';

export function renderZpl(state, motivos) {
  const { zpl } = state;

  // Rerrenderizar o mesmo texto a cada movimento do mouse é desperdício; só o
  // destaque precisa acompanhar a seleção.
  if (zpl.zpl !== ultimoZpl) {
    ultimoZpl = zpl.zpl;
    const linhas = zpl.zpl ? zpl.zpl.split('\n') : [];
    code.innerHTML = linhas
      .map(
        (linha, i) =>
          `<div class="zpl-line" data-line="${i}">` +
          `<span class="zpl-line__n">${i + 1}</span>` +
          `<span class="zpl-line__t">${colorir(linha)}</span></div>`
      )
      .join('');

    tamanho.textContent = `${zpl.byte_size ?? 0} bytes · ${zpl.line_count ?? 0} linhas`;
    dots.textContent = zpl.width_dots ? `${zpl.width_dots} × ${zpl.height_dots} dots` : '—';
    renderAvisos(zpl.issues || []);
  }

  destacarSelecao(state);
}

function destacarSelecao(state) {
  const segmento = (state.zpl.segments || []).find((s) => s.element_id === state.selection);

  for (const linha of code.querySelectorAll('.zpl-line')) {
    const n = Number(linha.dataset.line);
    const dentro = segmento && n >= segmento.start_line && n <= segmento.end_line;
    linha.classList.toggle('is-highlighted', !!dentro);
  }

  if (segmento) {
    const alvo = code.querySelector(`[data-line="${segmento.start_line}"]`);
    // `nearest` só rola quando a linha está realmente fora de vista -- rolar
    // sempre faria o painel pular a cada clique.
    alvo?.scrollIntoView({ block: 'nearest' });
  }
}

function renderAvisos(avisos) {
  if (!avisos.length) {
    listaAvisos.innerHTML = '';
    return;
  }

  listaAvisos.innerHTML = avisos
    .map(
      (aviso) => `
      <div class="issue issue--${aviso.severity}" ${aviso.element_id ? `data-el="${aviso.element_id}"` : ''}>
        <span class="issue__dot"></span>
        <div class="issue__text">
          <div>${escapar(aviso.message)}</div>
          ${aviso.hint ? `<div class="issue__hint">${escapar(aviso.hint)}</div>` : ''}
        </div>
      </div>`
    )
    .join('');
}

export function initZplView() {
  // Clicar no código seleciona o objeto -- o caminho inverso do destaque.
  code.addEventListener('click', (evento) => {
    const linha = evento.target.closest('.zpl-line');
    if (!linha) return;
    const n = Number(linha.dataset.line);
    const segmento = (store.state.zpl.segments || []).find(
      (s) => n >= s.start_line && n <= s.end_line
    );
    if (segmento) store.select(segmento.element_id);
  });

  // Clicar em um aviso leva ao objeto problemático.
  listaAvisos.addEventListener('click', (evento) => {
    const item = evento.target.closest('[data-el]');
    if (item) store.select(item.dataset.el);
  });
}

/** Copia o ZPL para a área de transferência. */
export async function copiarZpl() {
  const texto = store.state.zpl.zpl || '';
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    // Sem permissão de clipboard (http em host remoto, por exemplo).
    const campo = document.createElement('textarea');
    campo.value = texto;
    document.body.appendChild(campo);
    campo.select();
    const ok = document.execCommand('copy');
    campo.remove();
    return ok;
  }
}
