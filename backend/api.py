#!/usr/bin/env python3
"""TextileBorder OutlineTool — web API for the Next.js website.

    python api.py                 http://127.0.0.1:8000  (docs at /docs)
    python api.py --port 7860     port used on Hugging Face Spaces

Same pipeline as app.py and cli.py. Checkpoint 1 (and the slow AI step) runs once per
uploaded image; the Session is kept in memory so a settings change only re-runs 2 and 3.

    POST /api/sessions                  upload a photo  -> id + previews
    POST /api/sessions/{id}/update      new settings    -> previews
    POST /api/sessions/{id}/perfect     ?source=sketch|color  -> AI redraw (paid, limited; see README)
    POST /api/sessions/{id}/chat        {message}  -> ask for a change in words (image edits only)
    POST /api/sessions/{id}/layers      {colors, merge, hidden} -> colour layers (free, offline)
    GET  /api/sessions/{id}/download    ?fmt=zip|png|pdf|svg|eps|dxf|tiff|bmp|perfect|layers-svg|layers-zip|layers-psd|perfect-psd
    GET  /api/health
"""
import argparse
import base64
import hmac
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from collections import OrderedDict, deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from sketchclean import CleanSettings, EvenSettings, OutputSettings, Session, Settings
from sketchclean import ai, layers
from sketchclean.export import Page
from sketchclean.imageio import hex_rgb, load_rgb
from sketchclean.lines import line_width
import chat
import perfect

HERE = Path(__file__).resolve().parent
CHAT_MAX_CHARS = 300                              # longest chat message (also checked by the website)
USAGE_LOG = HERE / "outputs" / "openai_usage.jsonl"     # one line per paid OpenAI call (cost tracking)

log = logging.getLogger("textileborder.api")

if not os.environ.get("API_TOKEN"):                # read from the environment or backend/.env (see perfect.py)
    log.warning("API_TOKEN is not set: anyone who can reach this API can use the paid 'Make border perfect'. "
                "Set API_TOKEN outside local development.")

MAX_UPLOAD_MB = 20
MAX_SESSIONS = 20                    # each one holds a few full-size images in memory
SESSION_TTL = 60 * 60                # seconds without use before a session is dropped
ALL_FORMATS = ("png", "tiff", "bmp", "svg", "pdf", "eps", "dxf")
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")

# comma-separated list of website addresses allowed to call the API from a browser
# (default: the local Next.js dev server; set ALLOWED_ORIGINS to the live site address)
ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
           if o.strip()]
if "*" in ORIGINS:
    log.warning("ALLOWED_ORIGINS contains '*': any website can call this API from a browser.")


# ----------------------------------------------------------------- settings

_c, _e, _o = CleanSettings(), EvenSettings(), OutputSettings()


class SettingsIn(BaseModel):
    """Every setting is optional; missing ones use the same defaults as the GUI.
    Out-of-range or unknown values are rejected with HTTP 422 (same limits as cli.py)."""
    output: Literal["bw", "scan"] = _c.output
    method: Literal["ai", "classic"] = _c.method
    keep_detail: bool = _c.keep_detail
    remove_shading: bool = _c.remove_shading
    contrast: float = Field(_c.contrast, ge=-1, le=1)
    sharpness: float = Field(_c.sharpness, ge=0, le=2)
    thickness: float = Field(_c.thickness, ge=-2, le=3)
    even_width: Literal["off", "light", "full", "uniform"] = _e.even_width
    uniform_width: float = Field(_e.uniform_width, ge=0, le=100)
    beautify: float = Field(_e.beautify, ge=0, le=2)
    smooth: float = Field(_e.smooth, ge=0, le=2)
    join_gaps: bool = _e.join_gaps
    color: str = _o.color
    dpi: int = Field(_o.dpi, ge=72, le=1200)
    width_cm: float = Field(_o.width_cm, ge=0, le=300)       # 0 = keep working size

    def to_settings(self) -> Settings:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", self.color):
            raise HTTPException(422, "color must look like #000000")
        return Settings(
            clean=CleanSettings(output=self.output, method=self.method if ai.available() else "classic",
                                keep_detail=self.keep_detail, remove_shading=self.remove_shading,
                                contrast=self.contrast, sharpness=self.sharpness, thickness=self.thickness),
            even=EvenSettings(even_width=self.even_width, uniform_width=self.uniform_width,
                              beautify=self.beautify, smooth=self.smooth, join_gaps=self.join_gaps),
            output=OutputSettings(color=self.color, dpi=self.dpi, width_cm=self.width_cm, formats=ALL_FORMATS))


# ----------------------------------------------------------------- sessions in memory

class Entry:
    def __init__(self, sess: Session, folder: Path, stem: str):
        self.sess, self.folder, self.stem = sess, folder, stem
        self.lock = threading.Lock()         # one change at a time per image
        self.used = time.time()
        self.perfect = None                  # PNG from "Make border perfect"
        self.perfect_calls = 0               # paid image calls used (or running) for this photo
        self.chat_calls = 0                  # chat messages used for this photo
        self.layer_state = {"colors": 0, "merge": []}   # what the user last chose in the Layers tab (used by the downloads)
        self.chat_history = []               # last on-topic turns, so "make it thinner" follows the last change


_sessions: "OrderedDict[str, Entry]" = OrderedDict()
_store_lock = threading.Lock()

_perfect_times: deque = deque()                # start times of paid image calls in the last hour (all sessions)
_chat_times: deque = deque()                   # start times of chat messages in the last hour (all sessions)
_perfect_lock = threading.Lock()


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _reserve(times, env_name, default):
    """Take one slot of a rolling-hour limit. Returns its timestamp, or None if the hour is full."""
    now = time.time()
    with _perfect_lock:
        while times and now - times[0] > 3600:
            times.popleft()
        if len(times) >= _env_int(env_name, default):
            return None
        times.append(now)
        return now


def _release(times, stamp):
    """Give a slot back when the paid call failed."""
    with _perfect_lock:
        try:
            times.remove(stamp)
        except ValueError:
            pass


def _reserve_hourly():
    return _reserve(_perfect_times, "PERFECT_MAX_PER_HOUR", 60)


def _release_hourly(stamp):
    _release(_perfect_times, stamp)


def _log_usage(sid, source, meta):
    """Append one JSON line per successful paid call; a logging problem never breaks the request."""
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "session": sid,
                "kind": meta.get("kind", "image"), "model": meta.get("model"), "quality": meta.get("quality"),
                "size": meta.get("size"), "source": source, "usage": meta.get("usage")}
        with open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:
        log.exception("could not write %s", USAGE_LOG)


def _drop(entry: Entry):
    shutil.rmtree(entry.folder, ignore_errors=True)


def _add(entry: Entry) -> str:
    sid = uuid.uuid4().hex
    with _store_lock:
        now = time.time()
        for k in [k for k, v in _sessions.items() if now - v.used > SESSION_TTL]:
            _drop(_sessions.pop(k))
        while len(_sessions) >= MAX_SESSIONS:
            _drop(_sessions.popitem(last=False)[1])
        _sessions[sid] = entry
    return sid


def _get(sid: str) -> Entry:
    with _store_lock:
        entry = _sessions.get(sid)
        if entry is None:
            raise HTTPException(404, "This picture has expired. Please upload it again.")
        _sessions.move_to_end(sid)
        entry.used = time.time()
    return entry


# ----------------------------------------------------------------- previews

def _data_url(rgb, max_w=1600, fmt=".png"):
    """Shrink for the screen only (files keep full size) and encode for an <img src>."""
    if rgb is None:
        return None
    if rgb.shape[1] > max_w:
        f = max_w / rgb.shape[1]
        rgb = cv2.resize(rgb, (max_w, int(rgb.shape[0] * f)), interpolation=cv2.INTER_AREA)
    params = [cv2.IMWRITE_JPEG_QUALITY, 85] if fmt == ".jpg" else []
    ok, buf = cv2.imencode(fmt, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), params)
    mime = "image/jpeg" if fmt == ".jpg" else "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.tobytes()).decode("ascii")


def _result(sid: str, entry: Entry):
    s = entry.sess
    rep = s.report()
    return {
        "id": sid,
        "name": entry.stem,
        "previews": {
            "scan": _data_url(s.preview_scan(), fmt=".jpg"),
            "clean": _data_url(s.preview_clean()),
            "final": _data_url(s.preview_final()),
            "check": _data_url(s.preview_check()),
        },
        "info": {
            "output": s.settings.clean.output,
            "width": int(s.clean.image.shape[1]),
            "height": int(s.clean.image.shape[0]),
            "lines_from": rep.get("lines_from"),
            "closed_boxes": rep.get("closed_boxes"),
            "gaps_joined": rep.get("gaps_joined"),
            "loose_ends": rep.get("loose_ends"),
            "ai_note": rep.get("ai_note"),
            "seconds": s.timing,
        },
        "formats": ["zip", "png", "tiff", "bmp"] + (["svg", "pdf", "eps", "dxf"] if s.even is not None else []),
        "perfect": _perfect_usage(entry),
        "chat": _chat_usage(entry),
    }


def _perfect_usage(entry: Entry):
    """Paid 'Make border perfect' calls used for this photo and the limit, so the website can show them."""
    return {"used": entry.perfect_calls, "limit": _env_int("PERFECT_MAX_PER_SESSION", 3)}


def _chat_usage(entry: Entry):
    """Chat messages used for this photo and the limit."""
    return {"used": entry.chat_calls, "limit": _env_int("CHAT_MAX_MESSAGES_PER_SESSION", 20)}


def _require_token(authorization):
    """Paid calls need "Authorization: Bearer <API_TOKEN>" when API_TOKEN is set."""
    token = os.environ.get("API_TOKEN")
    if token and not hmac.compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "Not allowed: missing or wrong API token.")


# ----------------------------------------------------------------- app

app = FastAPI(title="TextileBorder OutlineTool API")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])     # the website reads the download's file name


@app.get("/api/health")
def health():
    return {"ok": True, "ai": ai.available(), "ai_status": ai.status(), "perfect": perfect.available(),
            "defaults": asdict(Settings())}


@app.post("/api/sessions")
def create_session(file: UploadFile = File(...), auto_crop: bool = Form(True), settings: str = Form("{}")):
    """Upload a photo: runs checkpoint 1, then 2 and 3 with the given settings."""
    name = Path(file.filename or "sketch.jpg").name
    if Path(name).suffix.lower() not in IMAGE_TYPES:
        raise HTTPException(415, "Please upload a photo (JPG or PNG).")
    try:
        s = SettingsIn.model_validate_json(settings or "{}").to_settings()
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False, include_input=False))

    folder = Path(tempfile.mkdtemp(prefix="sketch_api_"))
    stem = re.sub(r"[^\w-]+", "_", Path(name).stem)[:40] or "sketch"
    src = folder / f"{stem}{Path(name).suffix.lower()}"
    size = 0
    with open(src, "wb") as f:
        while chunk := file.file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_MB << 20:
                shutil.rmtree(folder, ignore_errors=True)
                raise HTTPException(413, f"The photo is too big (more than {MAX_UPLOAD_MB} MB).")
            f.write(chunk)
    try:
        sess = Session(src, auto_crop=auto_crop)
        sess.update(s)
    except Exception:
        log.exception("could not process upload %r", name)       # real reason in the server log only
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, "Could not read this photo. Please upload a JPG or PNG.")
    entry = Entry(sess, folder, stem)
    return _result(_add(entry), entry)


@app.post("/api/sessions/{sid}/update")
def update_session(sid: str, settings: SettingsIn):
    """New settings for an uploaded photo: re-runs checkpoints 2 and 3 only."""
    entry = _get(sid)
    s = settings.to_settings()
    with entry.lock:
        entry.sess.update(s)
        entry.layer_state = {"colors": 0, "merge": []}      # the layers belong to the old lines
        return _result(sid, entry)


def _paid_redraw(sid, entry, source, extra=None, refine=False):
    """One paid image call. refine=False redraws the scanned image; refine=True (chat) starts from the
    last perfect border when there is one. Limits: PERFECT_MAX_PER_SESSION and PERFECT_MAX_PER_HOUR."""
    max_per_session = _env_int("PERFECT_MAX_PER_SESSION", 3)
    # copy what the call needs and reserve this photo's slot, then let go of the lock:
    # the paid call can take a minute and must not block other requests for this photo
    with entry.lock:
        if entry.perfect_calls >= max_per_session:
            raise HTTPException(429, f"Make border perfect can be used {max_per_session} times per photo. "
                                     "Upload the photo again to try more.")
        s = entry.sess
        if refine and entry.perfect is not None and entry.perfect.exists():
            picture = load_rgb(entry.perfect)             # transparent lines are put on white paper again
        else:
            picture = s.preview_scan().copy()     # the scanned image (checkpoint 1)
            if not refine:
                entry.chat_history = []           # a fresh redraw starts a new conversation
        color, dpi = s.settings.output.color, s.settings.output.dpi
        entry.perfect_calls += 1
    stamp = _reserve_hourly()
    if stamp is None:
        with entry.lock:
            entry.perfect_calls -= 1
        raise HTTPException(429, "Make border perfect has been used too often in the last hour. "
                                 "Please try again later.")

    try:
        rgb, meta = perfect.make_perfect(picture, "sketch" if source == "chat" else source, color, extra)  # one prompt for all
    except perfect.PerfectError as e:
        with entry.lock:
            entry.perfect_calls -= 1          # nothing was made, so the slot is given back
        _release_hourly(stamp)
        raise HTTPException(502, str(e))
    _log_usage(sid, source, meta)

    with entry.lock:
        if not entry.folder.exists():          # the photo expired while the call was running
            raise HTTPException(404, "This picture has expired. Please upload it again.")
        path = entry.folder / f"{entry.stem}_perfect.png"
        # the file is black lines on a transparent background (one layer in Photoshop); the preview stays on white
        Image.fromarray(perfect.to_transparent(rgb, color), "RGBA").save(path, dpi=(dpi, dpi))
        entry.perfect = path
        usage = _perfect_usage(entry)
    return rgb, usage


@app.post("/api/sessions/{sid}/perfect")
def make_perfect(sid: str, source: str = "sketch", authorization: Optional[str] = Header(None)):
    """'Make border perfect': an OpenAI image model (gpt-image-2 by default, see OPENAI_IMAGE_MODEL;
    medium quality, see OPENAI_IMAGE_QUALITY) redraws the design as clean line art.
    Both sources send the scanned image (checkpoint 1); source is kept for the usage log.
    Paid: needs API_TOKEN (if set), and is limited per photo and per hour."""
    _require_token(authorization)
    if source not in ("sketch", "color"):
        raise HTTPException(422, "source must be 'sketch' or 'color'")
    entry = _get(sid)
    rgb, usage = _paid_redraw(sid, entry, source)
    return {"image": _data_url(rgb), "perfect": usage}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=CHAT_MAX_CHARS)


@app.post("/api/sessions/{sid}/chat")
def chat_edit(sid: str, body: ChatIn, authorization: Optional[str] = Header(None)):
    """'Chat to perfect': the user asks for a change in words. A cheap text model (chat.py) checks that
    it is a request to improve or edit the border image; anything else gets a fixed refusal and costs
    no image. An allowed edit is applied by the image model to the last perfect border (or the scan).
    Paid: needs API_TOKEN (if set); limited per photo (CHAT_MAX_MESSAGES_PER_SESSION, and the image
    limit above) and per hour (CHAT_MAX_PER_HOUR)."""
    _require_token(authorization)
    message = " ".join(body.message.split())
    if not message:
        raise HTTPException(422, "Please type a message.")
    entry = _get(sid)

    max_messages = _env_int("CHAT_MAX_MESSAGES_PER_SESSION", 20)
    with entry.lock:
        if entry.chat_calls >= max_messages:
            raise HTTPException(429, f"You can send {max_messages} chat messages per photo. "
                                     "Upload the photo again to continue.")
        entry.chat_calls += 1
        history = list(entry.chat_history)
    stamp = _reserve(_chat_times, "CHAT_MAX_PER_HOUR", 300)
    if stamp is None:
        with entry.lock:
            entry.chat_calls -= 1
        raise HTTPException(429, "The chat has been used too often in the last hour. Please try again later.")

    try:
        verdict = chat.classify(message, history)
    except chat.ChatError as e:
        with entry.lock:
            entry.chat_calls -= 1             # nothing was answered, so the slot is given back
        _release(_chat_times, stamp)
        raise HTTPException(502, str(e))
    _log_usage(sid, "chat", {"kind": "chat", "model": verdict["model"], "usage": verdict["usage"]})

    if not verdict["on_topic"]:
        with entry.lock:
            usage, chat_usage = _perfect_usage(entry), _chat_usage(entry)
        return {"reply": chat.REFUSAL, "image": None, "perfect": usage, "chat": chat_usage}

    reply = verdict["reply"] or "Okay."
    image, instruction = None, verdict["edit_instruction"]
    if instruction:
        rgb, _ = _paid_redraw(sid, entry, "chat", extra=instruction, refine=True)
        image = _data_url(rgb)
    with entry.lock:
        entry.chat_history = (entry.chat_history + [{"role": "user", "content": message[:CHAT_MAX_CHARS]},
                                                    {"role": "assistant", "content": reply}])[-6:]
        usage, chat_usage = _perfect_usage(entry), _chat_usage(entry)
    return {"reply": reply, "image": image, "perfect": usage, "chat": chat_usage}


LayerId = Annotated[int, Field(ge=0, le=layers.MAX_COLORS - 1)]


class LayersIn(BaseModel):
    colors: int = Field(0, ge=0, le=layers.MAX_COLORS)                       # 0 = find the number automatically
    merge: list[tuple[LayerId, LayerId]] = Field(default_factory=list, max_length=layers.MAX_COLORS)   # (from, to)
    hidden: list[LayerId] = Field(default_factory=list, max_length=layers.MAX_COLORS)
    show_lines: bool = True


@app.post("/api/sessions/{sid}/layers")
def colour_layers(sid: str, body: LayersIn):
    """Colour layers of the black & white result: the colours found in the photo, and a preview with the
    chosen layers hidden. Free and offline (no AI). The choices are remembered for the layer downloads."""
    entry = _get(sid)
    with entry.lock:
        sess = entry.sess
        try:
            base = sess.layer_base(body.colors)
        except ValueError as e:
            raise HTTPException(400, str(e))
        labels, palette = layers.apply_merge(base, body.merge)
        entry.layer_state = {"colors": body.colors, "merge": list(body.merge)}
        img = layers.composite(labels, palette, set(body.hidden), base.lines,
                               hex_rgb(sess.settings.output.color), body.show_lines)
    return {"image": _data_url(img),
            "palette": [{k: e[k] for k in ("id", "hex", "name", "share")} for e in palette]}


def _download_layers(entry, fmt):
    """layers-svg: one SVG, a group per colour + the lines. layers-zip: a transparent PNG per colour.
    layers-psd: one PSD with a layer per colour and the lines on top."""
    with entry.lock:
        sess = entry.sess
        try:
            base = sess.layer_base(entry.layer_state["colors"])
            work_h, work_w = sess.clean.image.shape
            page = Page(work_w, work_h, sess.settings.output.dpi, sess.settings.output.width_cm)
        except ValueError as e:
            raise HTTPException(422 if "too large" in str(e) else 400, str(e))
        labels, palette = layers.apply_merge(base, entry.layer_state["merge"])
        if not palette:
            raise HTTPException(400, "No colours were found in this photo, so there are no colour layers.")
        out = entry.folder / "layers"
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        line_hex = sess.settings.output.color
        if fmt == "layers-svg":
            path = out / f"{entry.stem}_layers.svg"
            layers.write_layers_svg(path, labels, palette, sess.even.shapes, page, line_hex)
            return FileResponse(path, filename=path.name, media_type="image/svg+xml")
        if fmt == "layers-psd":
            path = out / f"{entry.stem}_layers.psd"
            layers.write_layers_psd(path, labels, palette, base.lines.astype(np.uint8) * 255, hex_rgb(line_hex),
                                    sess.settings.output.dpi / page.scale)
            return FileResponse(path, filename=path.name, media_type="image/vnd.adobe.photoshop")
        path = out / f"{entry.stem}_layers.zip"
        # the PNGs have the working size, so their DPI is scaled to give the chosen physical size
        layers.write_layers_zip(path, labels, palette, base.lines, hex_rgb(line_hex), sess.settings.output.dpi / page.scale)
        return FileResponse(path, filename=path.name, media_type="application/zip")


def _download_perfect_psd(entry):
    """perfect-psd: ONE layered PSD with the AI's perfect border on top of the colour layers of the photo.
    The colours come from the photo (offline); the AI lines only decide the shapes. No extra AI call."""
    with entry.lock:
        if entry.perfect is None or not entry.perfect.exists():
            raise HTTPException(404, "Press Make border perfect first.")
        sess = entry.sess
        try:
            base = sess.layer_base(entry.layer_state["colors"])
            work_h, work_w = sess.clean.image.shape
            page = Page(work_w, work_h, sess.settings.output.dpi, sess.settings.output.width_cm)
        except ValueError as e:
            raise HTTPException(422 if "too large" in str(e) else 400, str(e))
        with Image.open(entry.perfect) as im:
            alpha = np.asarray(im.convert("RGBA"))[..., 3]
        if alpha.shape != (work_h, work_w):
            alpha = cv2.resize(alpha, (work_w, work_h), interpolation=cv2.INTER_CUBIC)
        labels, palette = layers.apply_merge(base, entry.layer_state["merge"])
        ink = alpha > 127
        fitted = layers.refit_to_lines(labels, ink, line_width(ink))
        palette = [e for e in palette if (fitted == e["id"]).any()]      # colours the AI lines still have
        out = entry.folder / "layers"
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        path = out / f"{entry.stem}_perfect_layers.psd"
        layers.write_layers_psd(path, fitted, palette, alpha, hex_rgb(sess.settings.output.color),
                                sess.settings.output.dpi / page.scale, lines_name="Perfect border")
        return FileResponse(path, filename=path.name, media_type="image/vnd.adobe.photoshop")


@app.get("/api/sessions/{sid}/download")
def download(sid: str, fmt: str = "zip"):
    """One file (png, pdf, svg, eps, dxf, tiff, bmp) or everything in one zip."""
    entry = _get(sid)
    fmt = fmt.lower()
    if fmt == "perfect":
        if entry.perfect is None or not entry.perfect.exists():
            raise HTTPException(404, "Press Make border perfect first.")
        return FileResponse(entry.perfect, filename=entry.perfect.name)
    if fmt == "perfect-psd":
        return _download_perfect_psd(entry)
    if fmt in ("layers-svg", "layers-zip", "layers-psd"):
        return _download_layers(entry, fmt)
    if fmt not in ("zip",) + ALL_FORMATS:
        raise HTTPException(422, f"Unknown format: {fmt}")
    with entry.lock:
        out = entry.folder / "files"
        shutil.rmtree(out, ignore_errors=True)
        try:
            files = entry.sess.export(out, entry.stem)
        except ValueError as e:                  # Page: output size over the pixel limit
            raise HTTPException(422, str(e))
        if fmt == "zip":
            bundle = entry.folder / f"{entry.stem}_all_files.zip"
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
                for f in files.values():
                    z.write(f, Path(f).name)
                if entry.perfect is not None and entry.perfect.exists():
                    z.write(entry.perfect, entry.perfect.name)
            return FileResponse(bundle, filename=bundle.name, media_type="application/zip")
        if fmt not in files:
            failed = entry.sess.report().get("failed_formats", {})
            raise HTTPException(400, failed.get(fmt) or f"{fmt.upper()} needs the black & white output.")
        return FileResponse(files[fmt], filename=Path(files[fmt]).name)


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port)
