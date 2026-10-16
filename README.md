# TextileBorder OutlineTool — Prototype v0.5 (AI + beautify)

Turns a phone photo or scan of a sketch into a **clean scanner-quality image** or **clean
black & white line art** (with vector files) for Wilcom EmbroideryStudio, CorelDRAW,
Illustrator, Inkscape or textile CAD. The main line finder is an AI model (ONNX).

## Install and run

```bash
pip install -r requirements.txt
python app.py                 # GUI in your browser (http://127.0.0.1:7860)
python cli.py sketch.jpg      # command line, files go to ./outputs
python tests/smoke_test.py    # checks every sample runs and writes every file
```

The AI model is in `models/` (`manga_line_extraction_int8.onnx`, 44 MB). If the model or
`onnxruntime` is missing, the tool says so and uses the classic method instead.

**Faster model (recommended for daily use):** the full-precision model is about 2× faster on
most CPUs but is 172 MB, so it is not in the zip. Make it once (needs PyTorch only for this step):

```bash
git clone https://github.com/ljsabc/MangaLineExtraction_PyTorch mle
# download erika.pth from that repo's Releases page into this folder
pip install torch onnx
python tools/export_onnx.py --repo mle --weights erika.pth --out models/manga_line_extraction.onnx
```
The tool uses the full-precision model automatically when it is in `models/`.
With an NVIDIA GPU, `pip install onnxruntime-gpu` instead of `onnxruntime` (under a second per image).

## How it works

```
photo ─► 1 SCAN ──────────► 2 CLEAN ─────────────────────────► 3 EVEN OUT ──────► files
         page, grain,       AI lines (+ hatching/dots back)     gaps, even width,
         light, levels      contrast, thickness                 smooth / straighten
         (automatic)        or Scanner look (grayscale)
```

### Checkpoint 1 — Scan (automatic)
Find and flatten the page (only when 4 straight edges are found) → remove grain → enlarge to a
2400 px working size → even out the light (divide by the paper's own brightness) → auto levels.
The AI **needs** this step: on a raw photo with shadows it finds almost nothing.

### Checkpoint 2 — Clean: the AI line finder (`sketchclean/ai.py`)
Model: **MangaLineExtraction** (MIT licence, github.com/ljsabc/MangaLineExtraction_PyTorch),
exported to ONNX. It outputs clean, even structural lines without blobs or smudges.

1. **Stroke-width normalisation.** The model was trained on strokes about 4 px wide. The tool
   measures this sketch's stroke width and resizes so its strokes land at 4 px (capped at
   1400 px for speed). Wider strokes get treated as "tone" and erased; this step prevents that.
2. **Overlapping tiles** (512 px, 64 px blended overlap): bounded memory and time for any size, no seams.
3. **Hysteresis threshold** on the line probability: certain lines are kept, faint parts are kept
   only where they continue a certain line. Contrast moves both thresholds.
4. **Keep hatching, dots and fine detail** (on by default). The model was trained to erase tone,
   so it removes hatching. The tool finds hatched regions (where the classic finder sees much
   more ink than the AI over a few line widths) and uses the classic result inside them; isolated
   dots the AI dropped are added back. Everywhere else the AI's clean lines are used.
5. Line thickness is then applied to the final lines.

The AI runs **once per image** (10–40 s on an ordinary CPU, faster with the full-precision model,
under 1 s on a GPU). After that, every setting change reuses it and takes a few seconds.

| Control | What it does |
|---|---|
| Line finder | **AI** (default) or **Classic** (Wolf binarization + fine-stroke detector) |
| Keep hatching, dots and fine detail | Adds back what the AI treats as tone |
| Remove shading | Keeps thin lines, drops wide soft tone |
| Contrast | + darker lines / more faint lines kept, − softer / fewer |
| Line thickness | + bolder, − thinner |
| Sharpness | Crisper edges, scanner output only |

### Checkpoint 3 — Even out (B&W)

| Control | What it does |
|---|---|
| Line width | **Same width everywhere** (default): overdrawn, pressed-hard and dark-shaded parts are trimmed back to one pen width, thin parts filled up to it where there is room · Light: trims only the worst spots · Per line: each line steady at its own width · Off |
| Pen width | For "Same width everywhere": 0 = automatic (a normal, light stroke of this sketch — measured at the 30th percentile, so heavy parts cannot inflate it), or a width in photo pixels |
| Beautify lines | For "Same width everywhere" (default 1): each line is redrawn on its own smoothed centre path (hand shake removed, ends and junctions pinned so nothing moves apart), with one round pen; a line that stops just short of another (within ~3 pen widths, pointing at it) is continued until it touches. Dots keep their own shape; inside dense hatching nothing is joined. 0 = off |
| Smooth and straighten | 0 follows the pencil · 1 balanced · 2 very smooth |
| Join small breaks | Bridges a gap where two line ends face each other, as thick as that line |

## Outputs

| File | Use |
|---|---|
| `.eps` | **Wilcom EmbroideryStudio** (Import Graphic), CorelDRAW, Illustrator |
| `.dxf` | **Wilcom** (Import Graphic → choose **Millimeters**), CAD. AutoCAD R12, in mm. Layers: `OUTLINE` (edges of every line shape) and `CENTERLINE` (middle of every line — useful for run-stitch outlines) |
| `.svg` `.pdf` | Vector: `line-art` layer + `fill-boxes` layer (one white shape per closed box) |
| `.bmp` `.png` `.tif` | Bitmaps for auto-digitizing / textile CAD (PNG has transparent paper; black lines are 1-bit) |
| `_scan.png/.tif/.bmp` | Scanner-look output (grayscale) |
| `_report.json` | Settings, timings, AI model used, closed boxes, gaps joined |

Wilcom's own `.EMB` and stitch formats (DST, PES …) are made by Wilcom itself when it
digitizes the artwork; they cannot be written by an outside tool.

## Project structure

```
app.py                    GUI: upload → Scan → Clean → Final, live preview, download
cli.py                    command line, batches (--method ai|classic, --no-detail, ...)
models/                   ONNX model(s)
sketchclean/
  config.py               every setting, default and range in one place
  imageio.py              load (applies phone rotation), save PNG / TIFF / BMP with DPI
  scan.py                 Checkpoint 1
  ai.py                   AI line finder: model loading, stroke-width scaling, tiling
  clean.py                Checkpoint 2: AI + detail merge, classic finder, controls
  even.py                 Checkpoint 3
  beautify.py             professional redraw: smoothed centre paths, one pen, short ends continued
  lines.py                centre lines, width, loose ends, gap bridges, centre-line paths
  vectorize.py            B&W → smooth vector shapes, and back to pixels
  export.py               SVG / PDF / EPS / DXF / PNG / TIFF / BMP writers
  pipeline.py             Session: runs the checkpoints, caches the scan and the AI result
tools/
  export_onnx.py          make the full-precision ONNX model from the original weights
  compare_binarization.py research: 9 binarization algorithms side by side (needs doxapy)
  make_samples.py         generates the synthetic test sketches
tests/smoke_test.py       every sample × 4 settings, all formats
samples/                  test images
```

## Known limits

- The AI removes hatching by design; "Keep hatching" restores it from the classic finder, so
  very faint hatching in a soft photo is still slightly irregular. A sharper photo or a scanner helps most.
- Mirror / repeat border helpers from v0.2 are not in this version yet.
- Model licence: the code and repository are MIT. Before selling the product, confirm with the
  author that the trained weights may be used commercially.
