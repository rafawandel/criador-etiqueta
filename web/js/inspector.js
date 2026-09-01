/**
 * Painel de propriedades.
 *
 * Não há um formulário escrito para cada tipo de elemento: o painel é montado a
 * partir do catálogo que o backend envia. Um campo novo na dataclass Python,
 * descrito em `app/catalog.py`, aparece aqui automaticamente com o rótulo, a
 * unidade e os limites certos.
 *
 * O formulário é reconstruído quando muda a *seleção*, não a cada tecla. Se
 * fosse recriado a todo evento, o cursor pularia para o fim do campo enquanto o
 * usuário digita -- um dos defeitos mais irritantes em editores como este.
 */

import { store } from './store.js';

const container = document.getElementById('inspector');
const labelContainer = document.getElementById('label-settings');

let idRenderizado = null;
let onChange = () => {};

export function initInspector({ onChange: cb } = {}) {
  onChange = cb || (() => {});
}

// ---------------------------------------------------------------------------
// Propriedades do elemento selecionado
// ---------------------------------------------------------------------------
export function renderInspector(state, motivos) {
  const el = state.label.elements.find((e) => e.id === state.selection);

  if (!el) {
    idRenderizado = null;
    container.innerHTML = '<p class="empty">Selecione um objeto para editar suas propriedades.</p>';
    return;
  }

  // Trocou a seleção -> remonta. Continuou o mesmo -> só sincroniza os valores,
  // preservando foco e posição do cursor.
  if (el.id !== idRenderizado) {
    idRenderizado = el.id;
    montarFormulario(state, el);
  } else if (motivos.has('live') || motivos.has('label')) {
    sincronizarValores(el);
  }
}

function montarFormulario(state, el) {
  const entrada = state.catalog.elements.find((e) => e.type === el.type);
  const campos = [...state.catalog.common_fields, ...(entrada?.fields || [])];

  container.innerHTML = '';
  container.appendChild(cabecalho(entrada, el));

  for (const [grupo, doGrupo] of agrupar(campos)) {
    container.appendChild(blocoGrupo(grupo, doGrupo, el));
  }

  container.appendChild(acoes(el));
}

function cabecalho(entrada, el) {
  const div = document.createElement('div');
  div.className = 'group';
  div.innerHTML = `
    <div class="group__title">${entrada?.label || el.type}</div>
    <div class="group__body">
      <p class="field__help">${entrada?.description || ''}</p>
      <p class="field__help"><strong>Comando ZPL:</strong> <code>${entrada?.zpl || '—'}</code></p>
    </div>`;
  return div;
}

function agrupar(campos) {
  const mapa = new Map();
  for (const campo of campos) {
    const grupo = campo.group || 'Geral';
    if (!mapa.has(grupo)) mapa.set(grupo, []);
    mapa.get(grupo).push(campo);
  }
  return mapa;
}

function blocoGrupo(titulo, campos, el) {
  const bloco = document.createElement('div');
  bloco.className = 'group';

  const cabeca = document.createElement('div');
  cabeca.className = 'group__title';
  cabeca.textContent = titulo;

  const corpo = document.createElement('div');
  // X/Y lado a lado: são lidos como um par, não como dois campos soltos.
  const doisPorLinha = campos.length > 1 && campos.every((c) => c.widget === 'number');
  corpo.className = doisPorLinha ? 'group__body cols-2' : 'group__body';

  for (const campo of campos) corpo.appendChild(criarCampo(campo, el));

  bloco.append(cabeca, corpo);
  return bloco;
}

// ---------------------------------------------------------------------------
// Widgets
// ---------------------------------------------------------------------------
function criarCampo(campo, el) {
  const wrapper = document.createElement('div');
  wrapper.className = campo.widget === 'switch' ? 'field field--inline' : 'field';

  const rotulo = document.createElement('label');
  rotulo.className = 'field__label';
  rotulo.textContent = campo.label;
  rotulo.htmlFor = `f-${campo.name}`;
  wrapper.appendChild(rotulo);

  const entrada = construir[campo.widget] ? construir[campo.widget](campo, el) : construir.text(campo, el);
  wrapper.appendChild(entrada);

  if (campo.help) {
    const ajuda = document.createElement('p');
    ajuda.className = 'field__help';
    ajuda.textContent = campo.help;
    wrapper.appendChild(ajuda);
  }
  return wrapper;
}

const construir = {
  text(campo, el) {
    const input = document.createElement('input');
    input.type = 'text';
    input.id = `f-${campo.name}`;
    input.dataset.field = campo.name;
    input.value = el[campo.name] ?? '';
    input.addEventListener('input', () => aplicar(campo.name, input.value, campo));
    return input;
  },

  textarea(campo, el) {
    const area = document.createElement('textarea');
    area.id = `f-${campo.name}`;
    area.dataset.field = campo.name;
    area.rows = 3;
    area.value = el[campo.name] ?? '';
    area.addEventListener('input', () => aplicar(campo.name, area.value, campo));
    return area;
  },

  number(campo, el) {
    const caixa = document.createElement('div');
    caixa.className = campo.unit ? 'field__unit' : '';

    const input = document.createElement('input');
    input.type = 'number';
    input.id = `f-${campo.name}`;
    input.dataset.field = campo.name;
    input.min = campo.min;
    input.max = campo.max;
    input.step = campo.step;
    input.value = el[campo.name] ?? 0;

    input.addEventListener('input', () => {
      const bruto = parseFloat(input.value);
      if (Number.isNaN(bruto)) return; // campo vazio no meio da digitação
      const limitado = Math.min(campo.max, Math.max(campo.min, bruto));
      aplicar(campo.name, limitado, campo);
    });
    // Só corrige o texto ao sair do campo, para não brigar com quem digita.
    input.addEventListener('blur', () => {
      const atual = store.selected?.[campo.name];
      if (atual !== undefined) input.value = atual;
    });

    caixa.appendChild(input);
    if (campo.unit) {
      const unidade = document.createElement('span');
      unidade.textContent = campo.unit;
      caixa.appendChild(unidade);
    }
    return campo.unit ? caixa : input;
  },

  select(campo, el) {
    const select = document.createElement('select');
    select.id = `f-${campo.name}`;
    select.dataset.field = campo.name;
    for (const opcao of campo.options) {
      const item = document.createElement('option');
      item.value = opcao.value;
      item.textContent = opcao.label;
      select.appendChild(item);
    }
    select.value = el[campo.name] ?? campo.options[0]?.value;
    select.addEventListener('change', () => aplicar(campo.name, select.value, campo));
    return select;
  },

  switch(campo, el) {
    const caixa = document.createElement('span');
    caixa.className = 'switch';

    const input = document.createElement('input');
    input.type = 'checkbox';
    input.id = `f-${campo.name}`;
    input.dataset.field = campo.name;
    input.checked = !!el[campo.name];
    input.addEventListener('change', () => aplicar(campo.name, input.checked, campo));

    const trilho = document.createElement('span');
    trilho.className = 'switch__track';

    caixa.append(input, trilho);
    return caixa;
  },

  /** Seletor de imagem: lê o arquivo como data URL, que é o que o modelo guarda. */
  image(campo, el) {
    const zona = document.createElement('div');
    zona.className = 'dropzone';
    zona.dataset.field = campo.name;

    const arquivo = document.createElement('input');
    arquivo.type = 'file';
    arquivo.accept = 'image/*';
    arquivo.hidden = true;

    const pintar = () => {
      const valor = store.selected?.[campo.name];
      zona.innerHTML = valor
        ? `<img src="${valor}" alt="" /><div>Clique para trocar</div>`
        : '<div>Clique para escolher uma imagem<br>PNG, JPG ou BMP</div>';
      zona.appendChild(arquivo);
    };

    arquivo.addEventListener('change', () => {
      const escolhido = arquivo.files?.[0];
      if (!escolhido) return;
      const leitor = new FileReader();
      leitor.onload = () => {
        aplicar(campo.name, leitor.result, campo, { coalesce: false });
        pintar();
      };
      leitor.readAsDataURL(escolhido);
    });

    zona.addEventListener('click', () => arquivo.click());
    pintar();
    return zona;
  },
};

/** Grava o valor no elemento selecionado. */
function aplicar(nome, valor, campo, { coalesce = true } = {}) {
  const id = store.state.selection;
  if (!id) return;

  store.edit(
    (label) => {
      const alvo = label.elements.find((e) => e.id === id);
      if (alvo) alvo[nome] = valor;
    },
    // Digitação contínua no mesmo campo vira um único passo de "desfazer".
    { coalesce: coalesce ? `${id}:${nome}` : null }
  );
  onChange();
}

/** Atualiza os valores exibidos sem recriar os campos (preserva o foco). */
function sincronizarValores(el) {
  for (const input of container.querySelectorAll('[data-field]')) {
    const nome = input.dataset.field;
    if (document.activeElement === input) continue;
    if (input.type === 'checkbox') input.checked = !!el[nome];
    else if (input.tagName === 'DIV') continue; // dropzone se repinta sozinha
    else input.value = el[nome] ?? '';
  }
}

// ---------------------------------------------------------------------------
// Ações do elemento
// ---------------------------------------------------------------------------
function acoes(el) {
  const bloco = document.createElement('div');
  bloco.className = 'inspector__actions';

  const botao = (texto, titulo, classe, aoClicar) => {
    const b = document.createElement('button');
    b.className = `btn ${classe}`;
    b.textContent = texto;
    b.title = titulo;
    b.addEventListener('click', aoClicar);
    return b;
  };

  bloco.append(
    botao('Duplicar', 'Ctrl+D', '', () => duplicar(el.id)),
    botao('▲', 'Trazer para frente', 'btn--icon', () => reordenar(el.id, +1)),
    botao('▼', 'Enviar para trás', 'btn--icon', () => reordenar(el.id, -1)),
    botao('Excluir', 'Delete', 'btn--danger', () => remover(el.id))
  );
  return bloco;
}

export function duplicar(id) {
  const original = store.state.label.elements.find((e) => e.id === id);
  if (!original) return;

  const copia = { ...structuredClone(original), id: novoId() };
  copia.x_mm = Math.round((copia.x_mm + 2) * 100) / 100;
  copia.y_mm = Math.round((copia.y_mm + 2) * 100) / 100;
  if (copia.name) copia.name = `${copia.name} (cópia)`;

  store.edit((label) => label.elements.push(copia));
  store.select(copia.id);
  onChange();
}

export function remover(id) {
  store.edit((label) => {
    label.elements = label.elements.filter((e) => e.id !== id);
  });
  store.select(null);
  onChange();
}

/** Move na pilha de impressão: o último elemento da lista imprime por cima. */
export function reordenar(id, direcao) {
  store.edit((label) => {
    const i = label.elements.findIndex((e) => e.id === id);
    const j = i + direcao;
    if (i < 0 || j < 0 || j >= label.elements.length) return;
    [label.elements[i], label.elements[j]] = [label.elements[j], label.elements[i]];
  });
  onChange();
}

function novoId() {
  return (crypto.randomUUID?.() || Math.random().toString(16).slice(2)).replace(/-/g, '').slice(0, 8);
}

// ---------------------------------------------------------------------------
// Aba "Etiqueta": configurações da mídia e da impressão
// ---------------------------------------------------------------------------
export function renderLabelSettings(state) {
  const { label } = state;
  const ajustes = label.print_settings;

  labelContainer.innerHTML = `
    <div class="group">
      <div class="group__title">Impressão</div>
      <div class="group__body">
        <div class="field">
          <label class="field__label" for="ps-copies">Cópias por etiqueta</label>
          <input id="ps-copies" type="number" min="1" max="999" value="${ajustes.copies ?? 1}">
        </div>
        <div class="field">
          <label class="field__label" for="ps-darkness">Escurecimento (^MD)</label>
          <input id="ps-darkness" type="number" min="-30" max="30" placeholder="usar o da impressora"
                 value="${ajustes.darkness ?? ''}">
          <p class="field__help">Vazio mantém o ajuste gravado na impressora. Aumente se as barras saírem falhadas.</p>
        </div>
        <div class="field">
          <label class="field__label" for="ps-speed">Velocidade (^PR)</label>
          <input id="ps-speed" type="number" min="1" max="14" placeholder="usar o da impressora"
                 value="${ajustes.speed_ips ?? ''}">
          <p class="field__help">Polegadas por segundo. Mais devagar imprime com mais definição.</p>
        </div>
        <div class="field field--inline">
          <span class="field__label">Imprimir de cabeça para baixo (^POI)</span>
          <span class="switch">
            <input id="ps-invert" type="checkbox" ${ajustes.invert_all ? 'checked' : ''}>
            <span class="switch__track"></span>
          </span>
        </div>
      </div>
    </div>

    <div class="group">
      <div class="group__title">Codificação</div>
      <div class="group__body">
        <div class="field">
          <label class="field__label" for="lb-encoding">Conjunto de caracteres</label>
          <select id="lb-encoding">
            <option value="utf-8">UTF-8 (^CI28) — recomendado</option>
            <option value="cp850">CP850 (^CI13)</option>
            <option value="cp1252">CP1252 (^CI27)</option>
            <option value="ascii">ASCII (^CI0)</option>
          </select>
          <p class="field__help">Impressoras antigas podem não aceitar UTF-8. Se os acentos saírem errados, teste CP850.</p>
        </div>
      </div>
    </div>`;

  labelContainer.querySelector('#lb-encoding').value = label.encoding;

  const ligar = (id, aplicarValor) => {
    const campo = labelContainer.querySelector(id);
    campo.addEventListener('change', () => {
      store.edit((l) => aplicarValor(l, campo));
      onChange();
    });
  };

  ligar('#ps-copies', (l, c) => (l.print_settings.copies = Math.max(1, parseInt(c.value, 10) || 1)));
  ligar('#ps-darkness', (l, c) => (l.print_settings.darkness = c.value === '' ? null : parseInt(c.value, 10)));
  ligar('#ps-speed', (l, c) => (l.print_settings.speed_ips = c.value === '' ? null : parseInt(c.value, 10)));
  ligar('#ps-invert', (l, c) => (l.print_settings.invert_all = c.checked));
  ligar('#lb-encoding', (l, c) => (l.encoding = c.value));
}
