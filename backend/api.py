#!/usr/bin/env python3
"""TextileBorder OutlineTool — web API for the Next.js website.

    python api.py                 http://127.0.0.1:8000  (docs at /docs)
    python api.py --port 7860     port used on Hugging Face Spaces

Same pipeline as app.py and cli.py. Checkpoint 1 (and the slow AI step) runs once per
uploaded image; the Session is kept in memory so a settings change only re-runs 2 and 3.

    POST /api/sessions                  upload a photo  -> id + previews
    POST /api/sessions/{id}/update      new settings    -> previews
    GET  /api/sessions/{id}/download    ?fmt=zip|png|pdf|svg|eps|dxf|tiff|bmp
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
from typing import Literal, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, Field, ValidationError

from sketchclean import CleanSettings, EvenSettings, OutputSettings, Session, Settings
from sketchclean import ai
import perfect

HERE = Path(__file__).resolve().parent
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

# comma-separated list of website addresses allowed to call the API ("*" = any)
ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]


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
        self.perfect_calls = 0               # paid calls used (or running) for this photo


_sessions: "OrderedDict[str, Entry]" = OrderedDict()
_store_lock = threading.Lock()

_perfect_times: deque = deque()                # start times of paid calls in the last hour (all sessions)
_perfect_lock = threading.Lock()


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _reserve_hourly():
    """Take one slot of PERFECT_MAX_PER_HOUR (rolling hour). Returns its timestamp, or None if full."""
    now = time.time()
    with _perfect_lock:
        while _perfect_times and now - _perfect_times[0] > 3600:
            _perfect_times.popleft()
        if len(_perfect_times) >= _env_int("PERFECT_MAX_PER_HOUR", 60):
            return None
        _perfect_times.append(now)
        return now


def _release_hourly(stamp):
    """Give a slot back when the paid call failed."""
    with _perfect_lock:
        try:
            _perfect_times.remove(stamp)
        except ValueError:
            pass


def _log_usage(sid, source, meta):
    """Append one JSON line per successful paid call; a logging problem never breaks the request."""
    try:
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "session": sid,
                "model": meta.get("model"), "quality": meta.get("quality"), "size": meta.get("size"),
                "source": source, "usage": meta.get("usage")}
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
    }


# ----------------------------------------------------------------- app

app = FastAPI(title="TextileBorder OutlineTool API")
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])


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
        return _result(sid, entry)


@app.post("/api/sessions/{sid}/perfect")
def make_perfect(sid: str, source: str = "sketch", authorization: Optional[str] = Header(None)):
    """'Make border perfect': an OpenAI image model (gpt-image-1, medium quality by default) redraws the design as clean line art.
    source=sketch sends the original uploaded photo; source=color sends the scanned image (checkpoint 1).
    Paid: needs API_TOKEN (if set), and is limited per photo and per hour."""
    token = os.environ.get("API_TOKEN")
    if token and not hmac.compare_digest((authorization or "").encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "Not allowed: missing or wrong API token.")
    if source not in ("sketch", "color"):
        raise HTTPException(422, "source must be 'sketch' or 'color'")
    entry = _get(sid)

    # copy what the call needs and reserve this photo's slot, then let go of the lock:
    # the paid call can take a minute and must not block other requests for this photo
    max_per_session = _env_int("PERFECT_MAX_PER_SESSION", 3)
    with entry.lock:
        if entry.perfect_calls >= max_per_session:
            raise HTTPException(429, f"Make border perfect can be used {max_per_session} times per photo. "
                                     "Upload the photo again to try more.")
        s = entry.sess
        if source == "sketch":
            picture = np.asarray(ImageOps.exif_transpose(Image.open(s.path)).convert("RGB"))
        else:
            picture = s.preview_scan().copy()
        color, dpi = s.settings.output.color, s.settings.output.dpi
        entry.perfect_calls += 1
    stamp = _reserve_hourly()
    if stamp is None:
        with entry.lock:
            entry.perfect_calls -= 1
        raise HTTPException(429, "Make border perfect has been used too often in the last hour. "
                                 "Please try again later.")

    try:
        rgb, meta = perfect.make_perfect(picture, source, color)
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
        Image.fromarray(rgb, "RGB").save(path, dpi=(dpi, dpi))
        entry.perfect = path
    return {"image": _data_url(rgb)}


@app.get("/api/sessions/{sid}/download")
def download(sid: str, fmt: str = "zip"):
    """One file (png, pdf, svg, eps, dxf, tiff, bmp) or everything in one zip."""
    entry = _get(sid)
    fmt = fmt.lower()
    if fmt == "perfect":
        if entry.perfect is None or not entry.perfect.exists():
            raise HTTPException(404, "Press Make border perfect first.")
        return FileResponse(entry.perfect, filename=entry.perfect.name)
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
