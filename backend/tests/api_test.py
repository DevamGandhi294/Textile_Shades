#!/usr/bin/env python3
"""Checks the web API (api.py): setting limits, error messages and the paid
"Make border perfect" endpoint. No network calls: OpenAI is never contacted.

    python tests/api_test.py          (also works with pytest)
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402  (this also reads backend/.env)
import perfect  # noqa: E402

# start from a clean, offline setup whatever is in backend/.env
for var in ("OPENAI_API_KEY", "API_TOKEN", "PERFECT_MAX_PER_SESSION", "PERFECT_MAX_PER_HOUR"):
    os.environ.pop(var, None)


def _no_network(*a, **k):
    raise AssertionError("a test tried to call OpenAI")


perfect.httpx.post = _no_network
api.USAGE_LOG = ROOT / "outputs" / "api_test_usage.jsonl"     # keep the real cost log clean

SAMPLE = ROOT / "samples" / "06_kurta_web_image.jpg"
CLASSIC = '{"method": "classic"}'
client = TestClient(api.app)


def new_session():
    with open(SAMPLE, "rb") as f:
        r = client.post("/api/sessions", files={"file": (SAMPLE.name, f, "image/jpeg")}, data={"settings": CLASSIC})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def fake_perfect(picture, kind="sketch", color="#000000"):
    rgb = np.full(picture.shape[:2] + (3,), 255, np.uint8)
    return rgb, {"model": "fake", "quality": "medium", "size": "1024x1024", "usage": None}


# ----------------------------------------------------------------- 1. setting limits

def test_bad_settings_return_422():
    sid = new_session()
    for bad in ({"dpi": 0}, {"dpi": -300}, {"width_cm": -5}, {"width_cm": 100000},
                {"method": "banana"}, {"even_width": "banana"}):
        r = client.post(f"/api/sessions/{sid}/update", json={"method": "classic", **bad})
        assert r.status_code == 422, (bad, r.status_code, r.text)


def test_valid_update_and_svg_download():
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/update", json={"method": "classic", "dpi": 300, "width_cm": 20})
    assert r.status_code == 200, r.text
    r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "svg"})
    assert r.status_code == 200 and r.content.lstrip().startswith(b"<"), r.status_code


def test_too_large_output_returns_422():
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/update", json={"method": "classic", "dpi": 1200, "width_cm": 300})
    assert r.status_code == 200, r.text
    r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "png"})
    assert r.status_code == 422 and "too large" in r.json()["detail"], r.text


# ----------------------------------------------------------------- 2. no server paths in errors

def test_corrupt_upload_returns_400_without_paths():
    r = client.post("/api/sessions", files={"file": ("broken.jpg", b"this is not an image", "image/jpeg")})
    assert r.status_code == 400, r.status_code
    detail = r.json()["detail"]
    for leak in ("/tmp", "\\", "sketch_api_", "Temp"):
        assert leak not in detail, detail


# ----------------------------------------------------------------- 3. Make border perfect

def test_perfect_without_key_returns_502_setup_message():
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/perfect")
    assert r.status_code == 502 and "OPENAI_API_KEY" in r.json()["detail"], r.text


def test_perfect_needs_token_when_set():
    sid = new_session()
    os.environ["API_TOKEN"] = "test-secret"
    try:
        assert client.post(f"/api/sessions/{sid}/perfect").status_code == 401
        r = client.post(f"/api/sessions/{sid}/perfect", headers={"Authorization": "Bearer wrong"})
        assert r.status_code == 401
    finally:
        os.environ.pop("API_TOKEN", None)


def test_perfect_per_session_limit():
    sid = new_session()
    real = perfect.make_perfect
    perfect.make_perfect = fake_perfect
    os.environ["PERFECT_MAX_PER_SESSION"] = "2"
    try:
        codes = [client.post(f"/api/sessions/{sid}/perfect").status_code for _ in range(3)]
        assert codes == [200, 200, 429], codes
        assert client.get(f"/api/sessions/{sid}/download", params={"fmt": "perfect"}).status_code == 200
    finally:
        perfect.make_perfect = real
        os.environ.pop("PERFECT_MAX_PER_SESSION", None)
        api.USAGE_LOG.unlink(missing_ok=True)


def test_perfect_hourly_limit():
    real = perfect.make_perfect
    perfect.make_perfect = fake_perfect
    os.environ["PERFECT_MAX_PER_HOUR"] = "1"
    api._perfect_times.clear()
    try:
        assert client.post(f"/api/sessions/{new_session()}/perfect").status_code == 200
        assert client.post(f"/api/sessions/{new_session()}/perfect").status_code == 429
    finally:
        perfect.make_perfect = real
        os.environ.pop("PERFECT_MAX_PER_HOUR", None)
        api._perfect_times.clear()
        api.USAGE_LOG.unlink(missing_ok=True)


# ----------------------------------------------------------------- runner

def main():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as e:
            failures += 1
            print(f"  FAIL {name}: {e!r}")
    print("all passed" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
