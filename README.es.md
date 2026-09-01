# Creador de Etiquetas ZPL

[Português](README.md) · [English](README.en.md) · **Español**

Editor visual de etiquetas para impresoras Zebra. Arrastras los objetos al
lienzo, escribes el contenido y el código ZPL aparece listo al lado —
actualizado en cada cambio.

```
┌──────────────┬────────────────────────────┬──────────────┬──────────────────┐
│  PALETA      │         ETIQUETA           │  PROPIEDADES │   ZPL EN VIVO    │
│  CAPAS       │  (arrastra, redimensiona)  │              │  (bidireccional) │
└──────────────┴────────────────────────────┴──────────────┴──────────────────┘
```

> **Nota sobre el idioma:** la interfaz de la aplicación está en **portugués de
> Brasil**, al igual que la documentación dentro del código. Solo este README
> está traducido. Localizar la interfaz implicaría extraer todos los textos de
> `web/js/` y `src/app/catalog.py` — conviene saberlo antes de implantarlo en un
> equipo que no hable portugués.

## Cómo ejecutarlo

El proyecto usa [uv](https://docs.astral.sh/uv/). Si aún no lo tienes:

```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"    # Windows
curl -LsSf https://astral.sh/uv/install.sh | sh               # Linux/macOS
```

Después:

```bash
uv sync                  # crea el .venv e instala las versiones exactas del lock
uv run python run.py     # levanta el editor
```

El navegador abre en `http://127.0.0.1:8000`. No hay paso de compilación: el
frontend son módulos ES nativos, servidos directamente.

## Qué puedes poner en la etiqueta

| Objeto | Comando ZPL | Observaciones |
|---|---|---|
| Texto | `^A` + `^FD` | fuentes internas, rotación, bloque con salto de línea (`^FB`), inversión (`^FR`) |
| Código de barras | `^BC` `^B3` `^BA` `^BE` `^B8` `^BU` `^B2` | Code 128/39/93, EAN-13/8, UPC-A, ITF |
| Código QR | `^BQ` | 4 niveles de corrección de errores |
| DataMatrix | `^BX` | ECC 200 |
| Rectángulo | `^GB` | marco o área sólida, esquinas redondeadas |
| Línea | `^GB` / `^GD` | horizontal, vertical y diagonal |
| Círculo | `^GC` | |
| Imagen | `^GFA` | logotipo convertido a 1 bit, con umbral o tramado |

Los acentos se resuelven con `^CI28` (UTF-8) y escape hexadecimal vía `^FH`, que
es el camino que funciona en planta — incluso en impresoras antiguas, cambiando
la codificación en la pestaña **Etiqueta**.

## Campos variables

Escribe `{{sku}}` en cualquier texto o código de barras. El campo se convierte en
una variable: el editor lista las variables encontradas y pide los valores al
imprimir. La misma plantilla sirve para un lote completo.

```python
from zpl_core import load_label, to_zpl

plantilla = load_label("templates_store/etiqueta-produto.json")
for fila in productos:
    enviar(to_zpl(plantilla, {"sku": fila.sku, "lote": fila.lote}))
```

## Atajos de teclado

| | |
|---|---|
| `Ctrl+Z` / `Ctrl+Y` | deshacer / rehacer |
| `Ctrl+D` | duplicar objeto |
| `Delete` | eliminar objeto |
| `Flechas` | mover 0,5 mm (`Shift` = 5 mm) |
| `Ctrl+S` | guardar plantilla |
| `Ctrl` + rueda | zoom |
| `Alt` al arrastrar | desactiva el imán |
| `Esc` | quitar la selección |

## Impresión

Tres caminos, del más simple al más integrado:

1. **Descargar el `.zpl`** y enviarlo como prefieras — siempre disponible;
2. **Copiar** el código y pegarlo donde haga falta;
3. **Imprimir directo**, por TCP en el puerto 9100 o por una cola de Windows.

La impresión directa viene **desactivada**. Para habilitarla:

```bash
# .env  (ver .env.example)
ETIQUETA_ALLOW_PRINTING=1
ETIQUETA_PRINTERS=Expedicion=192.168.0.50:9100;Produccion=192.168.0.51
```

Para la cola de Windows, instala el extra: `uv sync --extra windows-print`. Sin
él solo queda disponible el envío por IP — y el mensaje de error lo indica.

## Cómo está organizado el proyecto

> Para la arquitectura completa — capas, contratos, decisiones registradas y el
> paso a paso para añadir un comando ZPL nuevo — consulta
> **[DESIGN.md](DESIGN.md)** (escrito en portugués).

```
src/
├── zpl_core/            Python puro. No conoce HTTP ni navegador.
│   ├── units.py         mm <-> dots. El único lugar que sabe qué es el DPI.
│   ├── enums.py         rotación, color, simbología (valores = letras del ZPL)
│   ├── elements.py      una dataclass por objeto; cada una sabe emitir ZPL
│   ├── label.py         la etiqueta: medio, impresión, campos variables
│   ├── zpl_writer.py    modelo -> ZPL + mapa línea→elemento
│   ├── escaping.py      ^FH / ^CI, acentos y caracteres de control
│   ├── validation.py    avisos que evitan desperdiciar material
│   ├── serialization.py JSON <-> Label
│   ├── barcodes.py      PNG de vista previa (no es lo que se imprime)
│   ├── images.py        imagen -> mapa de bits de 1 bit -> ^GFA
│   └── printing.py      TCP 9100, cola de Windows, archivo
│
├── app/                 Capa web delgada sobre zpl_core.
│   ├── catalog.py       describe los objetos PARA LA INTERFAZ
│   ├── routers/         render, templates, printing
│   └── main.py          FastAPI
│
web/                     Editor. Sin compilación, sin framework.
├── store.js             estado + historial de deshacer
├── geometry.js          tamaños e imán (refleja el cálculo de Python)
├── canvas.js            dibujo y todas las interacciones del ratón
├── inspector.js         panel de propiedades generado por el catálogo
├── panels.js            paleta y capas
└── zplview.js           panel de ZPL con resaltado bidireccional
```

### Tres decisiones que vale la pena explicar

**El ZPL se genera solo en Python.** El panel en vivo hace una llamada (con
retardo de 120 ms) en lugar de armar el código en el navegador. En red local la
latencia es imperceptible y, a cambio, existe una única implementación del ZPL —
la misma que alimenta la exportación, la impresión y los scripts por lotes. Dos
implementaciones divergirían, y la divergencia aparecería en la impresora.

**La interfaz la genera el catálogo.** El panel de propiedades y la paleta no
tienen formularios escritos a mano. Se construyen a partir de `app/catalog.py`,
que describe etiqueta, unidad, rango de valores y cómo redimensiona cada objeto.
Dar soporte a un comando ZPL nuevo consiste en: crear la dataclass en
`elements.py`, registrarla en `ELEMENT_TYPES` y describirla en el catálogo. No
cambia ni una línea de JavaScript.

**El código y el dibujo se señalan mutuamente.** Junto con el ZPL, el generador
devuelve el mapa de qué elemento produjo qué líneas. Seleccionar un objeto
resalta el fragmento correspondiente; hacer clic en una línea selecciona el
objeto. Eso convierte el panel de código en una herramienta de aprendizaje en
lugar de un bloque de texto opaco.

## Limitaciones conocidas

- **La vista previa es una aproximación, no una simulación.** El navegador dibuja
  el texto y las formas; los códigos de barras vienen de bibliotecas Python. La
  fidelidad basta para maquetar, pero solo la impresora conoce la métrica exacta
  de las fuentes internas de Zebra. Imprime una unidad antes de dar por buena una
  plantilla.
- **DataMatrix aparece como marcador.** El `^BX` generado es correcto e imprime
  con normalidad; lo que falta es un codificador DataMatrix en Python puro para
  dibujar la vista previa. Se señala como aproximado en pantalla para no engañar
  a nadie.
- **La rotación en la vista previa** gira alrededor del origen del campo. Es el
  comportamiento de `^FO` en la mayoría de los casos, pero los campos rotados
  merecen una impresión de prueba antes de pasar a producción.

## Pruebas

```bash
uv run pytest
```

94 pruebas que cubren la generación de ZPL, el escape de acentos, la
serialización, la validación y el contrato HTTP. Algunas existen específicamente
para fijar acoplamientos que se romperían en silencio — por ejemplo, que todo
campo descrito en el catálogo exista de verdad en la dataclass correspondiente.

## Licencia

[MIT](LICENSE). Usa, modifica y redistribuye libremente, incluso con fines
comerciales — basta con mantener el aviso de copyright.

Las dependencias también son permisivas: FastAPI, Pydantic y python-barcode bajo
MIT; Uvicorn, Starlette y qrcode bajo BSD-3-Clause; Pillow bajo MIT-CMU. Ninguna
impone restricciones sobre lo que hagas con este proyecto.
