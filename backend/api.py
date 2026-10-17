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
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sketchclean import CleanSettings, EvenSettings, OutputSettings, Session, Settings
from sketchclean import ai

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
    """Every setting is optional; missing ones use the same defaults as the GUI."""
    output: str = _c.output
    method: str = _c.method
    keep_detail: bool = _c.keep_detail
    remove_shading: bool = _c.remove_shading
    contrast: float = _c.contrast
    sharpness: float = _c.sharpness
    thickness: float = _c.thickness
    even_width: str = _e.even_width
    uniform_width: float = _e.uniform_width
    beautify: float = _e.beautify
    smooth: float = _e.smooth
    join_gaps: bool = _e.join_gaps
    color: str = _o.color
    dpi: int = _o.dpi
    width_cm: float = _o.width_cm

    def to_settings(self) -> Settings:
        if self.output not in ("bw", "scan"):
            raise HTTPException(422, "output must be 'bw' or 'scan'")
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


_sessions: "OrderedDict[str, Entry]" = OrderedDict()
_store_lock = threading.Lock()


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
    return {"ok": True, "ai": ai.available(), "ai_status": ai.status(),
            "defaults": asdict(Settings())}


@app.post("/api/sessions")
def create_session(file: UploadFile = File(...), auto_crop: bool = Form(True), settings: str = Form("{}")):
    """Upload a photo: runs checkpoint 1, then 2 and 3 with the given settings."""
    name = Path(file.filename or "sketch.jpg").name
    if Path(name).suffix.lower() not in IMAGE_TYPES:
        raise HTTPException(415, "Please upload a photo (JPG or PNG).")
    s = SettingsIn.model_validate_json(settings or "{}").to_settings()

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
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, f"Could not read this photo: {e}")
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


@app.get("/api/sessions/{sid}/download")
def download(sid: str, fmt: str = "zip"):
    """One file (png, pdf, svg, eps, dxf, tiff, bmp) or everything in one zip."""
    entry = _get(sid)
    fmt = fmt.lower()
    if fmt not in ("zip",) + ALL_FORMATS:
        raise HTTPException(422, f"Unknown format: {fmt}")
    with entry.lock:
        out = entry.folder / "files"
        shutil.rmtree(out, ignore_errors=True)
        files = entry.sess.export(out, entry.stem)
        if fmt == "zip":
            bundle = entry.folder / f"{entry.stem}_all_files.zip"
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as z:
                for f in files.values():
                    z.write(f, Path(f).name)
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
