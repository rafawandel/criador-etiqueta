/**
 * Geometria dos elementos no canvas.
 *
 * As fórmulas de tamanho espelham `zpl_core/elements.py::size_mm`. São
 * estimativas -- quem desenha de verdade é a impressora --, mas precisam bater
 * com as do backend, senão o aviso de "passou da borda" apareceria em
 * situações diferentes das que o usuário vê na tela.
 */

/** Milímetro real na tela a 100% de zoom (1 pol = 96 px CSS). */
export const PX_PER_MM = 96 / 25.4;

/** Proporção largura/altura de caractere na fonte escalável ^A0. */
const AVG_CHAR_RATIO = 0.58;

export const dotsPerMm = (dpi) => dpi / 25.4;

/**
 * Módulos estreitos que o código ocupa na horizontal.
 * Espelha `zpl_core/elements.py::barcode_modules` -- as duas contas precisam
 * dar o mesmo número, senão a caixa desenhada e o aviso de "passou da borda"
 * discordariam.
 */
export function barcodeModules(symbology, data, wideRatio = 3) {
  const n = Math.max(1, (data || '').length);
  const silencio = 20;

  switch (symbology) {
    case 'ean13':
    case 'upca':
      return 95 + 18;
    case 'ean8':
      return 67 + 14;
    case 'code128':
      return 11 * (n + 2) + 13 + silencio;
    case 'code93':
      return 9 * (n + 4) + 1 + silencio;
    case 'code39':
      return Math.trunc((6 + 3 * wideRatio + 1) * (n + 2)) + silencio;
    case 'itf':
      return Math.trunc((3 + 2 * wideRatio) * n) + 9 + silencio;
    default:
      return 11 * n + 35 + silencio;
  }
}

/** Tamanho ocupado pelo elemento, em mm, antes da rotação. */
export function naturalSizeMm(el, dpi = 203) {
  const dpmm = dotsPerMm(dpi);

  switch (el.type) {
    case 'text': {
      const charW = el.width_mm > 0 ? el.width_mm : el.height_mm * AVG_CHAR_RATIO;
      if (el.block_width_mm > 0) {
        const linhas = Math.max(1, el.block_max_lines);
        return {
          w: el.block_width_mm,
          h: el.height_mm * linhas + (el.block_line_spacing_mm || 0) * (linhas - 1),
        };
      }
      return { w: Math.max(charW * (el.text || '').length, charW), h: el.height_mm };
    }
    case 'barcode': {
      const moduloMm = el.module_width_dots / dpmm;
      const modulos = barcodeModules(el.symbology, el.data, el.wide_ratio);
      return {
        w: Math.max(modulos * moduloMm, 10),
        h: el.height_mm + (el.show_text ? 3.5 : 0),
      };
    }
    case 'qrcode': {
      const modulos = 21 + 4 * Math.min(10, Math.max(0, Math.floor(((el.data || '').length - 10) / 14)));
      const lado = (modulos * el.magnification) / dpmm;
      return { w: lado, h: lado };
    }
    case 'datamatrix': {
      const modulos = 10 + 2 * Math.min(12, Math.floor((el.data || '').length / 3));
      const lado = (modulos * el.module_size_dots) / dpmm;
      return { w: lado, h: lado };
    }
    case 'circle':
      return { w: el.diameter_mm, h: el.diameter_mm };
    case 'line':
      return {
        w: Math.max(el.width_mm, el.thickness_mm),
        h: Math.max(el.height_mm, el.thickness_mm),
      };
    default: // box, image
      return { w: el.width_mm ?? 10, h: el.height_mm ?? 10 };
  }
}

const ROTATED = new Set(['R', 'B']);

/** Tamanho já considerando a rotação -- é a caixa que o usuário vê e arrasta. */
export function sizeMm(el, dpi = 203) {
  const { w, h } = naturalSizeMm(el, dpi);
  return ROTATED.has(el.rotation) ? { w: h, h: w } : { w, h };
}

export function boundsMm(el, dpi = 203) {
  const { w, h } = sizeMm(el, dpi);
  return { x1: el.x_mm, y1: el.y_mm, x2: el.x_mm + w, y2: el.y_mm + h, w, h };
}

// ---------------------------------------------------------------------------
// Ímã (snapping)
// ---------------------------------------------------------------------------

/** Distância, em mm, dentro da qual o elemento "cola" em uma referência. */
const SNAP_TOLERANCE_MM = 0.8;

/**
 * Ajusta uma posição arrastada para as referências mais próximas.
 *
 * Duas famílias de referência, na ordem em que o usuário espera:
 * 1. bordas e centro da etiqueta (alinhar ao papel);
 * 2. bordas e centros dos outros elementos (alinhar entre campos).
 *
 * Devolve a posição corrigida e as linhas-guia a desenhar -- mostrar *por que*
 * o objeto colou é o que faz o ímã parecer inteligente em vez de teimoso.
 */
export function snapPosition({ x, y, w, h }, label, others, gridMm) {
  const guias = [];
  let sx = x;
  let sy = y;

  const alvosX = [0, label.width_mm / 2 - w / 2, label.width_mm - w];
  const alvosY = [0, label.height_mm / 2 - h / 2, label.height_mm - h];
  const linhasX = [0, label.width_mm / 2, label.width_mm];
  const linhasY = [0, label.height_mm / 2, label.height_mm];

  for (const outro of others) {
    alvosX.push(outro.x1, outro.x2, outro.x1 - w, outro.x2 - w, outro.x1 + outro.w / 2 - w / 2);
    linhasX.push(outro.x1, outro.x2, outro.x1, outro.x2, outro.x1 + outro.w / 2);
    alvosY.push(outro.y1, outro.y2, outro.y1 - h, outro.y2 - h, outro.y1 + outro.h / 2 - h / 2);
    linhasY.push(outro.y1, outro.y2, outro.y1, outro.y2, outro.y1 + outro.h / 2);
  }

  let melhorX = SNAP_TOLERANCE_MM;
  let melhorY = SNAP_TOLERANCE_MM;
  let guiaX = null;
  let guiaY = null;

  alvosX.forEach((alvo, i) => {
    const d = Math.abs(x - alvo);
    if (d < melhorX) { melhorX = d; sx = alvo; guiaX = linhasX[i]; }
  });
  alvosY.forEach((alvo, i) => {
    const d = Math.abs(y - alvo);
    if (d < melhorY) { melhorY = d; sy = alvo; guiaY = linhasY[i]; }
  });

  // Sem referência por perto, cai na grade -- assim o arrasto livre ainda
  // produz valores redondos.
  if (guiaX === null && gridMm > 0) sx = Math.round(x / gridMm) * gridMm;
  if (guiaY === null && gridMm > 0) sy = Math.round(y / gridMm) * gridMm;

  if (guiaX !== null) guias.push({ axis: 'v', at: guiaX });
  if (guiaY !== null) guias.push({ axis: 'h', at: guiaY });

  return { x: sx, y: sy, guides: guias };
}

export const round2 = (v) => Math.round(v * 100) / 100;
export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
