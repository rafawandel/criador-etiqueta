/**
 * Cliente HTTP.
 *
 * Todo erro do servidor vira uma `ApiError` com a mensagem que o backend
 * escreveu -- as mensagens do FastAPI já são em português e explicam o
 * problema; reescrevê-las aqui só criaria divergência.
 */

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (cause) {
    throw new ApiError('Sem conexão com o servidor. Ele ainda está rodando?', 0, { cause });
  }

  if (!response.ok) {
    let detalhe = `${response.status} ${response.statusText}`;
    try {
      const corpo = await response.json();
      if (corpo?.detail) {
        detalhe = Array.isArray(corpo.detail)
          ? corpo.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
          : corpo.detail;
      }
    } catch {
      /* resposta sem JSON: fica o status mesmo */
    }
    throw new ApiError(detalhe, response.status);
  }
  return response;
}

const json = (url, body, method = 'POST') =>
  request(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const api = {
  catalog: () => request('/api/catalog').then((r) => r.json()),

  health: () => request('/api/health').then((r) => r.json()),

  /** Gera o ZPL da etiqueta. É a chamada do painel ao vivo. */
  zpl: (label, { data = {}, comments = true } = {}) =>
    json('/api/zpl', { label, data, comments }),

  /** URL de preview de código de barras (usada direto no src de um <img>). */
  barcodeUrl: (symbology, data, width, height, showText, barHeightMm) =>
    `/api/preview/barcode?${new URLSearchParams({
      symbology,
      data,
      width: Math.round(width),
      height: Math.round(height),
      show_text: showText ? 'true' : 'false',
      bar_height_mm: barHeightMm,
    })}`,

  qrcodeUrl: (data, size, ecc) =>
    `/api/preview/qrcode?${new URLSearchParams({ data, size: Math.round(size), ecc })}`,

  datamatrixUrl: (data, size) =>
    `/api/preview/datamatrix?${new URLSearchParams({ data, size: Math.round(size) })}`,

  /** Converte a imagem no servidor e devolve um blob URL do bitmap 1-bit. */
  async imagePreview(payload) {
    const response = await request('/api/preview/image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return URL.createObjectURL(await response.blob());
  },

  templates: {
    list: () => request('/api/templates').then((r) => r.json()),
    get: (slug) => request(`/api/templates/${slug}`).then((r) => r.json()),
    save: (label, slug = null) => json('/api/templates', { label, slug, overwrite: true }),
    remove: (slug) => request(`/api/templates/${slug}`, { method: 'DELETE' }).then((r) => r.json()),
  },

  printers: () => request('/api/printers').then((r) => r.json()),

  print: (label, printer, { data = {}, copies = 1 } = {}) =>
    json('/api/print', { label, printer, data, copies }),

  /** Baixa o .zpl deixando o servidor montar o arquivo e o nome. */
  async download(label, comments = true) {
    const response = await request('/api/export/zpl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label, data: {}, comments }),
    });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${label.name || 'etiqueta'}.zpl`;
    link.click();
    URL.revokeObjectURL(url);
  },
};
