/**
 * Estado da aplicação.
 *
 * Um único objeto de estado, com assinantes notificados a cada mudança. Não há
 * framework: o app tem uma tela só, e a disciplina de "todo mundo lê do store,
 * ninguém guarda cópia" já entrega previsibilidade sem 100 kB de dependência.
 *
 * O histórico guarda snapshots da etiqueta inteira. Uma etiqueta tem dezenas de
 * campos, não milhares -- clonar é barato e elimina toda a classe de bugs de
 * undo baseado em comandos.
 */

const HISTORY_LIMIT = 100;
const AUTOSAVE_KEY = 'criador-etiqueta:rascunho';

/** Etiqueta em branco, no formato que o backend espera. */
export function emptyLabel() {
  return {
    schema_version: 1,
    name: 'Nova etiqueta',
    width_mm: 100,
    height_mm: 50,
    dpi: 203,
    encoding: 'utf-8',
    print_settings: {
      copies: 1,
      darkness: null,
      speed_ips: null,
      home_x_dots: 0,
      home_y_dots: 0,
      invert_all: false,
      pause_between: false,
    },
    elements: [],
  };
}

const clone = (value) => JSON.parse(JSON.stringify(value));

class Store {
  constructor() {
    this.state = {
      label: emptyLabel(),
      catalog: null,
      selection: null,
      zoom: 1,
      options: { grid: true, snap: true, rulers: true, comments: true },
      zpl: { zpl: '', segments: [], issues: [], byte_size: 0, line_count: 0 },
      dirty: false,
    };
    this.past = [];
    this.future = [];
    this.listeners = new Set();
  }

  /** Assina mudanças. Devolve a função para cancelar a assinatura. */
  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /**
   * `reasons` diz o que mudou, para cada painel decidir se precisa redesenhar.
   * Redesenhar tudo a cada tecla digitada travaria o arrasto em etiquetas
   * cheias.
   */
  emit(reasons) {
    const set = new Set(Array.isArray(reasons) ? reasons : [reasons]);
    for (const fn of this.listeners) fn(this.state, set);
  }

  // -- alterações ---------------------------------------------------------

  /**
   * Altera a etiqueta registrando um passo no histórico.
   * @param {(label:object)=>void} mutator
   * @param {{coalesce?:string}} opts  `coalesce` funde alterações seguidas de
   *   mesma chave (digitar em um campo não deve gerar 40 níveis de undo).
   */
  edit(mutator, { coalesce = null, reasons = ['label'] } = {}) {
    const anterior = clone(this.state.label);
    const podeFundir =
      coalesce && this._lastCoalesce === coalesce && this.past.length > 0;

    if (!podeFundir) {
      this.past.push(anterior);
      if (this.past.length > HISTORY_LIMIT) this.past.shift();
    }
    this._lastCoalesce = coalesce;
    this.future.length = 0;

    mutator(this.state.label);
    this.state.dirty = true;
    this.autosave();
    this.emit([...reasons, 'history']);
  }

  /** Muda estado de interface (seleção, zoom, opções) sem tocar no histórico. */
  set(patch, reasons = ['ui']) {
    Object.assign(this.state, patch);
    this.emit(reasons);
  }

  select(id, reasons = ['selection']) {
    if (this.state.selection === id) return;
    this.state.selection = id;
    this.emit(reasons);
  }

  get selected() {
    return this.state.label.elements.find((e) => e.id === this.state.selection) || null;
  }

  /** Substitui a etiqueta inteira (abrir modelo, nova etiqueta, importar). */
  replaceLabel(label, { resetHistory = true } = {}) {
    if (resetHistory) {
      this.past.length = 0;
      this.future.length = 0;
    }
    this.state.label = label;
    this.state.selection = null;
    this.state.dirty = false;
    this._lastCoalesce = null;
    this.autosave();
    this.emit(['label', 'selection', 'history']);
  }


  // -- interações contínuas ------------------------------------------------

  /**
   * Arrastar produz dezenas de atualizações por segundo. Registrar cada uma no
   * histórico faria "desfazer" andar um pixel por vez. Então a interação
   * inteira -- do pointerdown ao pointerup -- vira um único passo:
   * `beginBatch` tira a foto, `live` atualiza sem histórico, `endBatch` fecha.
   */
  beginBatch() {
    this._batch = clone(this.state.label);
  }

  live(mutator, reasons = ['live']) {
    mutator(this.state.label);
    this.emit(reasons);
  }

  endBatch(reasons = ['label']) {
    if (!this._batch) return;
    const antes = JSON.stringify(this._batch);
    const depois = JSON.stringify(this.state.label);
    this._batch = null;
    if (antes === depois) return; // clique sem arrasto não vira passo de undo

    this.past.push(JSON.parse(antes));
    if (this.past.length > HISTORY_LIMIT) this.past.shift();
    this.future.length = 0;
    this._lastCoalesce = null;
    this.state.dirty = true;
    this.autosave();
    this.emit([...reasons, 'history']);
  }

  // -- histórico ----------------------------------------------------------
  undo() {
    if (!this.past.length) return false;
    this.future.push(clone(this.state.label));
    this.state.label = this.past.pop();
    this._lastCoalesce = null;
    this._afterTimeTravel();
    return true;
  }

  redo() {
    if (!this.future.length) return false;
    this.past.push(clone(this.state.label));
    this.state.label = this.future.pop();
    this._lastCoalesce = null;
    this._afterTimeTravel();
    return true;
  }

  _afterTimeTravel() {
    // O elemento selecionado pode ter deixado de existir no estado restaurado.
    if (!this.state.label.elements.some((e) => e.id === this.state.selection)) {
      this.state.selection = null;
    }
    this.autosave();
    this.emit(['label', 'selection', 'history']);
  }

  get canUndo() { return this.past.length > 0; }
  get canRedo() { return this.future.length > 0; }

  // -- rascunho local -----------------------------------------------------

  /** Guarda no navegador para que um F5 acidental não perca o trabalho. */
  autosave() {
    try {
      localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(this.state.label));
    } catch {
      /* cota cheia ou navegação privada: seguir sem autosave é aceitável */
    }
  }

  loadAutosave() {
    try {
      const raw = localStorage.getItem(AUTOSAVE_KEY);
      if (!raw) return null;
      const label = JSON.parse(raw);
      return label && Array.isArray(label.elements) ? label : null;
    } catch {
      return null;
    }
  }
}

export const store = new Store();
export { clone };
