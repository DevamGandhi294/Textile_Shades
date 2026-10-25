---
title: TextileBorder OutlineTool API
emoji: 🧵
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# TextileBorder OutlineTool — Prototype v0.5 (AI + beautify)

Turns a phone photo or scan of a sketch into a **clean scanner-quality image** or **clean
black & white line art** (with vector files) for Wilcom EmbroideryStudio, CorelDRAW,
Illustrator, Inkscape or textile CAD. The main line finder is an AI model (ONNX).

## Install and run

```bash
pip install -r requirements.txt
python app.py                 # GUI in your browser (http://127.0.0.1:7860)
python api.py                 # web API for the Next.js site in ../frontend (http://127.0.0.1:8000/docs)
python cli.py sketch.jpg      # command line, files go to ./outputs
python tests/smoke_test.py    # checks every sample runs and writes every file
python tests/api_test.py      # checks the web API (limits, errors, Make border perfect; no network)
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

## Colour layers (free, offline)

For a coloured sketch the website's **Layers** tab splits the design into one layer per colour, the way a
designer works in Photoshop or textile CAD: every area of the same colour is one layer, so one change
recolours all of them. No AI and no cost (`sketchclean/layers.py`):

1. **Colour scan** (`scan.color_scan`): the photo keeps its colour. The paper's light is measured on paper
   pixels only (so coloured areas never count as shadow), per colour channel; dividing by it evens out the
   light and removes the lamp's colour cast.
2. **Palette:** the colours of the design (k-means in Lab); colours that look alike are merged and crumbs are
   dropped. The user can also choose the number of colours (2 to 12), merge two colours, or hide a layer.
3. **Layers:** every closed box (from the final lines) takes the colour most of its pixels have, so shapes are
   crisp and follow the lines; colour is extended under the lines so no gap shows if the lines are hidden.
   Greys and white are not colours: white areas belong to no layer.
4. **Downloads:** `layers-psd` = ONE Photoshop file: a white "Background", a layer per colour ("01 Pink", ...)
   and the lines on top (soft edges kept, DPI stored); `layers-svg` = one SVG with a group per colour
   (Inkscape layers, top-level groups for Illustrator and CorelDRAW) and a "Lines" group on top;
   `layers-zip` = one transparent PNG per colour, one for the lines and a composite, all the same size.

A photo only gets colour layers if it really has colour: tinted paper, shadows and pencil sketches give no
layers (colours need a Lab chroma of about 20+, and some strong colour must be present). Very pale
pastels on their own are not detected. A small colour that is clearly different from the others (a flower
centre) is kept; the muddy blend on the edge between two colours is not.

The layers need the Black & white output. They are not in the normal ZIP.
Try it with `samples/07_color_border.jpg` (made by `tools/make_colour_sample.py`).

**The AI's perfect border as a layered PSD (`perfect-psd`, no extra AI call):** after "Make border perfect"
the website offers one PSD with the AI's lines on top ("Perfect border") over the colour layers of the photo.
The AI redraws the lines a few pixels off the photo, so each closed box of the AI lines takes the colour
layer most of its area has in the photo (`layers.refit_to_lines`, a vote over the whole box), and the colour
is extended under the lines. If the photo has no colour, the PSD is the white background and the
"Perfect border" layer. It uses the number of colours and merges last chosen in the Layers tab.

**Not verified yet:** how the layers show in the real software (Illustrator, CorelDRAW, Photoshop, Wilcom).
Test the SVG and the PNG layers there before relying on them.

## AI layers (optional, paid: one image call per layer)

The **AI layers** tab turns the uploaded photo into one layered PSD where the AI does all the work
(`layer_pipeline.py`; nothing local looks at the picture). The user first chooses the machine or design type:
**Embroidery**, **Digital Print** or **CAD**; it is part of every prompt.

1. **Check my design** (`POST /ai-analyse`, one cheap call to a small vision model, `OPENAI_ANALYSIS_MODEL`,
   default `gpt-4.1-mini`). It answers in JSON: `image_type` (line / color), `is_complete`, `is_symmetric`,
   `mirror` and the `layers` (name + description) to make. The layers depend on the machine: Embroidery splits by
   thread colour and stitch type, Print by colour (ink), CAD one layer per motif. For a symmetric design only the
   left half is described and drawn. The user sees the plan and **how many image calls it needs before anything
   is paid**.
2. **Model routing** (`pick_model`): a complete design uses `MODEL_COMPLETE` (default `gpt-image-2.5-flare`),
   an incomplete one `MODEL_INCOMPLETE` (default `gpt-image-1-mini`). Change them in `.env`.
3. **One image call per layer** (`POST /ai-layers`, a few at a time): that layer only, as clean, fully closed borders
   on a transparent background; a colour design gets area-wise border colours, a line design one dark colour
   (`#1a1a1a`). Models that cannot draw on transparency (anything but `gpt-image-1*`) are asked for pure white,
   which Python turns into transparency.
4. **Export** (`ai-layers-psd`): one PSD with psd-tools, a white Background, the original photo as a hidden layer and
   one named layer for each AI layer, bottom to top. A mirrored design is flipped horizontally to make the other half.

Limits: at most `AI_LAYERS_MAX_LAYERS` layers (6) per design, `AI_LAYERS_MAX_RUNS_PER_SESSION` (2) runs per photo, every
image call counts in `PERFECT_MAX_PER_HOUR`, and the design check counts as a chat message. If one layer fails, the others
are kept and the unpaid slots are given back. Every call is logged in `outputs/openai_usage.jsonl`
(`source: ai-analyse` and `ai-layer`, with the prompt). **Each layer is a separate AI redraw, so the layers can differ by a
few pixels from each other.** A real vector-shape PSD cannot be written by the library: the PSD has pixel layers.

## Make border perfect (optional, paid)

The website's **Make border perfect** button sends the picture to an OpenAI image model, which
redraws the same design as clean line art with smooth curves (`perfect.py`). "Sketch" sends the
original uploaded photo, "Coloured design" sends the scanned image. The answer is turned into
crisp black lines on white, 2400 px on the long side.

Settings go in `backend/.env` (copy `.env.example`; never commit `.env`):

| Variable | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | — | needed; without it the button is hidden |
| `OPENAI_IMAGE_MODEL` | `gpt-image-2` | image model |
| `OPENAI_IMAGE_QUALITY` | `medium` | `low` for cheap previews; `high` costs about 4× medium |
| `OPENAI_INPUT_FIDELITY` | `low` | gpt-image-1 models only |
| `OPENAI_CHAT_MODEL` | `gpt-4.1-mini` | text model that checks chat messages |
| `CHAT_MAX_MESSAGES_PER_SESSION` | 20 | chat messages per uploaded photo (then HTTP 429) |
| `CHAT_MAX_PER_HOUR` | 300 | chat messages for the whole server in a rolling hour (then HTTP 429) |
| `API_TOKEN` | not set | if set, the call needs `Authorization: Bearer <token>` (a warning is logged when unset) |
| `PERFECT_MAX_PER_SESSION` | 3 | paid calls per uploaded photo (then HTTP 429) |
| `PERFECT_MAX_PER_HOUR` | 60 | paid calls for the whole server in a rolling hour (then HTTP 429) |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | websites allowed to call the API |

### Chat to improve it

Instead of the one-click button, the user can open a chat and ask for a change in words ("make the lines
thinner", "close the small gaps"). A very cheap text model (`chat.py`, `gpt-4.1-mini` by default) first
checks the message: only requests to improve or edit the border image are allowed. Anything else (general
questions, other topics, questions about the model or its prompts) gets a fixed refusal from the server
and no image is made. An allowed edit is sent to the image model together with the default prompt; it
starts from the last perfect border (or the scan) and counts towards `PERFECT_MAX_PER_SESSION`.
Messages are limited to 300 characters, `CHAT_MAX_MESSAGES_PER_SESSION` per photo and
`CHAT_MAX_PER_HOUR` for the whole server. Chat calls are logged in the same usage file (`kind: chat`).

Every successful call adds one line to `outputs/openai_usage.jsonl` (time, session, model,
quality, size, source and OpenAI's token usage) for cost tracking. Calls are never retried
automatically, because every call is paid.

The AI result is a PNG (or the layered PSD above): it is not vectorised, so it is not in the SVG / PDF / EPS / DXF
files. The download is black lines (in the chosen line colour) on a **transparent** background, so it opens
in Photoshop as one layer for the colour layers to go under. It is included in the ZIP download.

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
  layers.py               colour layers: palette, layer per colour, layered SVG and PNG ZIP
  pipeline.py             Session: runs the checkpoints, caches the scan and the AI result
tools/
  export_onnx.py          make the full-precision ONNX model from the original weights
  compare_binarization.py research: 9 binarization algorithms side by side (needs doxapy)
  make_samples.py         generates the synthetic test sketches
  make_colour_sample.py   a synthetic hand-coloured border (samples/07_color_border.jpg)
tests/smoke_test.py       every sample × 6 settings, all formats
tests/api_test.py         web API: setting limits, errors, Make border perfect (no network)
samples/                  test images
```

## Known limits

- The AI removes hatching by design; "Keep hatching" restores it from the classic finder, so
  very faint hatching in a soft photo is still slightly irregular. A sharper photo or a scanner helps most.
- Mirror / repeat border helpers from v0.2 are not in this version yet.
- Model licence: the code and repository are MIT. Before selling the product, confirm with the
  author that the trained weights may be used commercially.
