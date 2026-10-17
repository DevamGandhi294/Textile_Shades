#!/usr/bin/env python3
"""TextileBorder OutlineTool — GUI.

    python app.py            opens http://127.0.0.1:7860 in your browser
    python app.py --share    also gives a temporary public link (e.g. to use a phone camera)

Flow: upload → 1 Scan (automatic) → 2 Clean → 3 Even out → Download.
Checkpoint 1 runs once per image and is kept; moving a slider only re-runs 2 and 3.
"""
import argparse
import re
import tempfile
import zipfile
from pathlib import Path

import cv2
import gradio as gr

# Older Gradio 4.x crashes on page load with newer pydantic
# ("argument of type 'bool' is not iterable"). Harmless on new Gradio.
try:
    import gradio_client.utils as _gcu
    _orig = _gcu._json_schema_to_python_type

    def _safe(schema, defs=None):
        return "Any" if isinstance(schema, bool) else _orig(schema, defs)

    _gcu._json_schema_to_python_type = _safe
except (ImportError, AttributeError):
    pass

from sketchclean import CleanSettings, EvenSettings, OutputSettings, Session, Settings
from sketchclean import ai
from sketchclean.config import RANGES

HERE = Path(__file__).parent
SAMPLES = sorted(str(p) for p in (HERE / "samples").glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
ALL_FORMATS = ["png", "tiff", "bmp", "svg", "pdf", "eps", "dxf"]


def screen(img, max_w=1600):
    """Shrink for display only; files keep full size."""
    if img is None or img.shape[1] <= max_w:
        return img
    f = max_w / img.shape[1]
    return cv2.resize(img, (max_w, int(img.shape[0] * f)), interpolation=cv2.INTER_AREA)


def to_hex(c):
    if not c:
        return "#000000"
    if c.startswith("#"):
        return c[:7]
    nums = [float(n) for n in re.findall(r"[\d.]+", c)[:3]]
    return "#" + "".join(f"{int(round(n)):02x}" for n in nums)


def make_settings(output, method, detail, shading, contrast, sharpness, thickness, even_width, pen, beauty, smooth, join,
                  color,
                  width_cm, dpi, formats):
    return Settings(
        clean=CleanSettings(output=output, method=method, keep_detail=detail, remove_shading=shading,
                            contrast=float(contrast),
                            sharpness=float(sharpness), thickness=float(thickness)),
        even=EvenSettings(even_width=even_width, uniform_width=float(pen), beautify=float(beauty),
                          smooth=float(smooth), join_gaps=join),
        output=OutputSettings(color=to_hex(color), dpi=int(dpi), width_cm=float(width_cm or 0),
                              formats=tuple(formats) or tuple(ALL_FORMATS)))


def status_text(sess):
    t = sess.timing
    secs = " · ".join(f"{k} {v:.1f} s" for k, v in t.items())
    h, w = sess.clean.image.shape
    if sess.even is None:
        return f"**Scanner output** · {w} × {h} px · {secs}"
    e = sess.even
    src = sess.report().get("lines_from", "classic")
    ai_txt = (f"AI lines ({sess.ai_info['seconds']:.0f} s, {sess.ai_info['device'].replace('ExecutionProvider', '')})"
              if src == "ai" else "classic lines")
    if sess.settings.clean.method == "ai" and sess.ai_error:
        ai_txt += f" — {sess.ai_error}"
    ends = ("all lines closed" if not e.loose_ends else
            f"{len(e.loose_ends)} loose line ends (red in **Check boxes**; normal for fold lines and embroidery)")
    return (f"**Black & white** · {ai_txt} · {w} × {h} px · {e.n_areas} closed boxes · {len(e.bridges)} gaps joined · "
            f"{ends}  \n{secs}")


def views(sess):
    check = sess.preview_check()
    return (screen(sess.preview_scan()), screen(sess.preview_clean()), screen(sess.preview_final()),
            screen(check) if check is not None else None, status_text(sess))


def run_all(path, auto_crop, *controls):
    if not path:
        return (None, None, None, None, None, "Upload a photo or scan of a sketch to start.")
    sess = Session(path, auto_crop=auto_crop)
    sess.update(make_settings(*controls))
    return (sess, *views(sess))


def rerun(sess, *controls):
    if sess is None:
        return (None, None, None, None, None, "Upload a photo or scan of a sketch to start.")
    sess.update(make_settings(*controls))
    return (sess, *views(sess))


def download(sess, *controls):
    if sess is None:
        raise gr.Error("Upload a sketch first.")
    sess.update(make_settings(*controls))
    out = Path(tempfile.mkdtemp(prefix="sketch_"))
    stem = re.sub(r"[^\w-]+", "_", Path(sess.path).stem)[:40] or "sketch"
    files = sess.export(out, stem)
    bundle = out / f"{stem}_all_files.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files.values():
            z.write(f, Path(f).name)
    keep = [str(bundle)] + [str(f) for k, f in files.items() if k != "report"]
    failed = sess.report().get("failed_formats")
    note = f"Could not create: {failed}" if failed else f"{len(keep) - 1} files ready."
    return keep, note


def build_ui():
    c0, e0, o0 = CleanSettings(), EvenSettings(), OutputSettings()
    with gr.Blocks(title="TextileBorder OutlineTool") as demo:
        sess = gr.State(None)
        gr.Markdown("# TextileBorder OutlineTool\nUpload a photo or scan of a sketch. "
                    "It becomes a clean scan automatically; adjust only if needed, then download.")
        with gr.Row():
            with gr.Column(scale=1, min_width=340):
                inp = gr.Image(label="Sketch photo or scan", type="filepath",
                               sources=["upload", "webcam", "clipboard"], height=280)
                output = gr.Radio([("Black & white lines", "bw"), ("Scanner look (grayscale)", "scan")],
                                  value=c0.output, label="Output",
                                  info="B&W: clean lines for colour fill and vector files. "
                                       "Scanner: keeps pencil shading and fine hatching.")

                method = gr.Radio([("AI lines (recommended)", "ai"), ("Classic", "classic")],
                                  value=c0.method if ai.available() else "classic", label="Line finder (B&W)",
                                  info="AI: clean, even lines without blobs. First run on a new image takes "
                                       "10-30 s on CPU; after that, settings update quickly. " + ai.status())
                detail = gr.Checkbox(value=c0.keep_detail, label="Keep hatching, dots and fine detail (AI)",
                                     info="The AI removes hatching as 'tone'; this adds it back from the classic finder.")

                with gr.Accordion("2 · Clean the lines", open=True):
                    shading = gr.Checkbox(value=c0.remove_shading, label="Remove shading and smudges",
                                          info="Keeps thin lines, drops soft pencil shading and leftover shadow.")
                    contrast = gr.Slider(*RANGES["contrast"][:2], value=c0.contrast, step=RANGES["contrast"][2],
                                         label="Contrast", info="+ darker lines and whiter paper · − softer")
                    thickness = gr.Slider(*RANGES["thickness"][:2], value=c0.thickness, step=RANGES["thickness"][2],
                                          label="Line thickness", info="+ bolder · − thinner")
                    sharpness = gr.Slider(*RANGES["sharpness"][:2], value=c0.sharpness, step=RANGES["sharpness"][2],
                                          label="Sharpness (scanner output)", info="Crisper edges in the scanner look.")

                with gr.Accordion("3 · Even out the lines (B&W)", open=True):
                    even_width = gr.Radio([("Same width everywhere", "uniform"), ("Light", "light"),
                                           ("Per line", "full"), ("Off", "off")],
                                          value=e0.even_width, label="Line width",
                                          info="Same width everywhere: overdrawn, pressed-hard and dark-shaded "
                                               "parts are cut back to one pen width. Light: only trims the worst "
                                               "spots. Per line: each line steady at its own width.")
                    pen = gr.Slider(0, 6, value=e0.uniform_width, step=0.25,
                                    label="Pen width (Same width everywhere)",
                                    info="0 = automatic (a normal stroke of this sketch). "
                                         "Or set it in pixels of your photo.")
                    beauty = gr.Slider(0, 2, value=e0.beautify, step=0.1, label="Beautify lines (Same width everywhere)",
                                       info="Redraws every line like a professional: removes hand shake from curves "
                                            "and continues lines that stop just short of another line so they touch. "
                                            "0 off · 1 normal · 2 extra smooth.")
                    smooth = gr.Slider(*RANGES["smooth"][:2], value=e0.smooth, step=RANGES["smooth"][2],
                                       label="Smooth and straighten",
                                       info="0 follows the pencil · 1 balanced · 2 very smooth, straighter lines")
                    join = gr.Checkbox(value=e0.join_gaps, label="Join small breaks in lines",
                                       info="Bridges a gap where two line ends face each other.")

                with gr.Accordion("Download settings", open=False):
                    color = gr.ColorPicker(value=o0.color, label="Line colour (B&W)")
                    width_cm = gr.Number(value=0, minimum=0, label="Width in cm (0 = automatic)")
                    dpi = gr.Dropdown([150, 200, 300, 600], value=o0.dpi, label="DPI")
                    formats = gr.CheckboxGroup(ALL_FORMATS, value=ALL_FORMATS, label="Formats",
                                               info="Wilcom E4: EPS or DXF (choose Millimeters) for vectors, "
                                                    "BMP/PNG for auto-digitizing. Vectors need the B&W output.")
                    auto_crop = gr.Checkbox(value=True, label="Auto-crop the paper in photos",
                                            info="Turn off if part of the drawing gets cut.")

                btn = gr.Button("Download files", variant="primary", size="lg")
                files = gr.File(label="Files", file_count="multiple")
                note = gr.Markdown()
                if SAMPLES:
                    gr.Examples(SAMPLES, inputs=inp, label="Try a sample")

            with gr.Column(scale=2):
                status = gr.Markdown("Upload a photo or scan of a sketch to start.")
                with gr.Tabs():
                    with gr.Tab("1 · Scan"):
                        v_scan = gr.Image(label="Checkpoint 1: scanner look (automatic)", type="numpy")
                    with gr.Tab("2 · Clean"):
                        v_clean = gr.Image(label="Checkpoint 2: cleaned", type="numpy")
                    with gr.Tab("3 · Final"):
                        v_final = gr.Image(label="Checkpoint 3: final", type="numpy")
                    with gr.Tab("Check boxes"):
                        gr.Markdown("Each closed box has its own colour. **Green** = gaps joined. "
                                    "**Red circle** = loose line end (colour fill could leak there).")
                        v_check = gr.Image(label="Check", type="numpy")

        controls = [output, method, detail, shading, contrast, sharpness, thickness, even_width, pen, beauty, smooth, join,
                    color, width_cm, dpi, formats]
        outs = [sess, v_scan, v_clean, v_final, v_check, status]

        inp.change(run_all, [inp, auto_crop] + controls, outs)
        auto_crop.change(run_all, [inp, auto_crop] + controls, outs)
        for s in (contrast, sharpness, thickness, pen, beauty, smooth):
            s.release(rerun, [sess] + controls, outs)
        for c in (output, method, detail, shading, even_width, join, color):
            c.change(rerun, [sess] + controls, outs)
        btn.click(download, [sess] + controls, [files, note], api_name="download")
    return demo


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--share", action="store_true", help="create a temporary public link")
    ap.add_argument("--port", type=int, default=7860)
    a = ap.parse_args()
    build_ui().launch(server_port=a.port, share=a.share, inbrowser=True)
