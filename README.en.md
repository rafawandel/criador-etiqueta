# ZPL Label Designer

[Português](README.md) · **English** · [Español](README.es.md)

Visual label editor for Zebra printers. You drag objects onto the canvas, type
the content, and the ZPL code appears ready beside it — updated on every change.

```
┌──────────────┬────────────────────────────┬──────────────┬──────────────────┐
│  PALETTE     │          LABEL             │  PROPERTIES  │    LIVE ZPL      │
│  LAYERS      │     (drag, resize)         │              │  (two-way link)  │
└──────────────┴────────────────────────────┴──────────────┴──────────────────┘
```

> **Note on language:** the application's interface is in **Brazilian
> Portuguese**, and so is the inline documentation in the code. Only this README
> is translated. Localizing the UI would mean extracting every string in
> `web/js/` and `src/app/catalog.py` — worth knowing before you deploy this to a
> non-Portuguese-speaking team.

## Running it

The project uses [uv](https://docs.astral.sh/uv/). If you don't have it yet:

```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"    # Windows
curl -LsSf https://astral.sh/uv/install.sh | sh               # Linux/macOS
```

Then:

```bash
uv sync                  # creates .venv and installs the exact locked versions
uv run python run.py     # starts the editor
```

Your browser opens at `http://127.0.0.1:8000`. There is no build step: the
frontend is native ES modules, served directly.

## What you can put on a label

| Object | ZPL command | Notes |
|---|---|---|
| Text | `^A` + `^FD` | internal fonts, rotation, word-wrapped blocks (`^FB`), reverse (`^FR`) |
| Barcode | `^BC` `^B3` `^BA` `^BE` `^B8` `^BU` `^B2` | Code 128/39/93, EAN-13/8, UPC-A, ITF |
| QR Code | `^BQ` | 4 error-correction levels |
| DataMatrix | `^BX` | ECC 200 |
| Rectangle | `^GB` | outline or solid fill, rounded corners |
| Line | `^GB` / `^GD` | horizontal, vertical and diagonal |
| Circle | `^GC` | |
| Image | `^GFA` | logo converted to 1-bit, via threshold or dithering |

Accented characters are handled with `^CI28` (UTF-8) plus hexadecimal escaping
through `^FH` — the approach that actually works in the field, including on
older printers, by switching the encoding in the **Etiqueta** (Label) tab.

## Variable fields

Write `{{sku}}` in any text or barcode. The field becomes a variable: the editor
lists every variable it finds and asks for the values at print time. The same
template then serves an entire batch.

```python
from zpl_core import load_label, to_zpl

template = load_label("templates_store/etiqueta-produto.json")
for row in products:
    send(to_zpl(template, {"sku": row.sku, "lote": row.batch}))
```

## Keyboard shortcuts

| | |
|---|---|
| `Ctrl+Z` / `Ctrl+Y` | undo / redo |
| `Ctrl+D` | duplicate object |
| `Delete` | remove object |
| `Arrow keys` | nudge 0.5 mm (`Shift` = 5 mm) |
| `Ctrl+S` | save template |
| `Ctrl` + wheel | zoom |
| `Alt` while dragging | disable snapping |
| `Esc` | clear selection |

## Printing

Three paths, from the simplest to the most integrated:

1. **Download the `.zpl`** and send it however you like — always available;
2. **Copy** the code and paste it wherever you need;
3. **Print directly**, over TCP port 9100 or through a Windows print queue.

Direct printing ships **disabled**. To enable it:

```bash
# .env  (see .env.example)
ETIQUETA_ALLOW_PRINTING=1
ETIQUETA_PRINTERS=Shipping=192.168.0.50:9100;Production=192.168.0.51
```

For the Windows queue, install the extra: `uv sync --extra windows-print`.
Without it only IP delivery is available — and the error message says so.

## How the project is laid out

> For the full architecture — layers, contracts, recorded decisions and the
> step-by-step guide to adding a new ZPL command — see **[DESIGN.md](DESIGN.md)**
> (written in Portuguese).

```
src/
├── zpl_core/            Pure Python. Knows nothing about HTTP or browsers.
│   ├── units.py         mm <-> dots. The only place that knows what DPI is.
│   ├── enums.py         rotation, color, symbology (values = ZPL letters)
│   ├── elements.py      one dataclass per object; each knows how to emit ZPL
│   ├── label.py         the label: media, print settings, variable fields
│   ├── zpl_writer.py    model -> ZPL + line→element map
│   ├── escaping.py      ^FH / ^CI, accents and control characters
│   ├── validation.py    warnings that prevent wasted media
│   ├── serialization.py JSON <-> Label
│   ├── barcodes.py      preview PNGs (not what gets printed)
│   ├── images.py        image -> 1-bit bitmap -> ^GFA
│   └── printing.py      TCP 9100, Windows spooler, file
│
├── app/                 Thin web layer over zpl_core.
│   ├── catalog.py       describes the objects FOR THE INTERFACE
│   ├── routers/         render, templates, printing
│   └── main.py          FastAPI
│
web/                     Editor. No build, no framework.
├── store.js             state + undo history
├── geometry.js          sizes and snapping (mirrors the Python calculation)
├── canvas.js            rendering and every mouse interaction
├── inspector.js         property panel generated from the catalog
├── panels.js            palette and layers
└── zplview.js           ZPL panel with two-way highlighting
```

### Three decisions worth explaining

**ZPL is generated in Python only.** The live panel makes a request (debounced
at 120 ms) instead of assembling the code in the browser. On a local network the
latency is imperceptible, and in exchange there is a single ZPL implementation —
the same one that feeds export, printing and batch scripts. Two implementations
would drift apart, and the drift would show up on the printer.

**The interface is generated from the catalog.** The property panel and the
palette have no hand-written forms. They are built from `app/catalog.py`, which
describes label, unit, value range and how each object resizes. Supporting a new
ZPL command means: create the dataclass in `elements.py`, register it in
`ELEMENT_TYPES`, describe it in the catalog. Not one line of JavaScript changes.

**The code and the drawing point at each other.** Along with the ZPL, the
generator returns a map of which element produced which lines. Selecting an
object highlights the matching snippet; clicking a line selects the object. That
is what turns the code panel into a learning tool instead of an opaque block of
text.

## Known limitations

- **The preview is an approximation, not a simulation.** Text and shapes are
  drawn by the browser; barcodes come from Python libraries. Fidelity is good
  enough for laying things out, but only the printer knows the exact metrics of
  Zebra's internal fonts. Print one unit before signing off on a template.
- **DataMatrix shows as a placeholder.** The generated `^BX` is correct and
  prints normally; what is missing is a pure-Python DataMatrix encoder to draw
  the preview. It is flagged as approximate on screen so nobody is misled.
- **Rotation in the preview** pivots around the field origin. That matches `^FO`
  behaviour in most cases, but rotated fields deserve a test print before going
  to production.

## Tests

```bash
uv run pytest
```

94 tests covering ZPL generation, accent escaping, serialization, validation and
the HTTP contract. Some exist specifically to lock down couplings that would
break silently — for example, that every field described in the catalog actually
exists on the corresponding dataclass.

## License

[MIT](LICENSE). Use, modify and redistribute freely, including commercially —
just keep the copyright notice.

The dependencies are permissive too: FastAPI, Pydantic and python-barcode under
MIT; Uvicorn, Starlette and qrcode under BSD-3-Clause; Pillow under MIT-CMU.
None of them restricts what you do with this project.
