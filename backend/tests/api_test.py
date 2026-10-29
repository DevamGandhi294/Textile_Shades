#!/usr/bin/env python3
"""Checks the web API (api.py): setting limits, error messages and the paid
"Make border perfect" endpoint. No network calls: OpenAI is never contacted.

    python tests/api_test.py          (also works with pytest)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402  (this also reads backend/.env)
import chat  # noqa: E402
import perfect  # noqa: E402

# start from a clean, offline setup whatever is in backend/.env
for var in ("OPENAI_API_KEY", "API_TOKEN", "PERFECT_MAX_PER_SESSION", "PERFECT_MAX_PER_HOUR",
            "CHAT_MAX_MESSAGES_PER_SESSION", "CHAT_MAX_PER_HOUR"):
    os.environ.pop(var, None)


def _no_network(*a, **k):
    raise AssertionError("a test tried to call OpenAI")


perfect.httpx.post = _no_network
api.USAGE_LOG = ROOT / "outputs" / "api_test_usage.jsonl"     # keep the real cost log clean
api.LINES_ON_UPLOAD = True                                     # most tests check the local results of the upload

SAMPLE = ROOT / "samples" / "06_kurta_web_image.jpg"
CLASSIC = '{"method": "classic"}'
client = TestClient(api.app)


def new_session():
    with open(SAMPLE, "rb") as f:
        r = client.post("/api/sessions", files={"file": (SAMPLE.name, f, "image/jpeg")}, data={"settings": CLASSIC})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def fake_perfect(picture, kind="sketch", color="#000000", extra=None):
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
        replies = [client.post(f"/api/sessions/{sid}/perfect") for _ in range(3)]
        assert [r.status_code for r in replies] == [200, 200, 429], [r.status_code for r in replies]
        assert replies[1].json()["perfect"] == {"used": 2, "limit": 2}, replies[1].json()["perfect"]
        r = client.post(f"/api/sessions/{sid}/update", json={"method": "classic"})
        assert r.json()["perfect"] == {"used": 2, "limit": 2}, r.json()["perfect"]
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


# ----------------------------------------------------------------- 4. Chat to perfect

OFF_TOPIC = {"on_topic": False, "reply": "", "edit_instruction": None, "model": "fake", "usage": None}
ON_TOPIC = {"on_topic": True, "reply": "Making the lines thinner.", "edit_instruction": "Make the lines thinner.",
            "model": "fake", "usage": {"total_tokens": 1}}


class FakeChat:
    """Replaces the paid text and image calls; remembers what was asked."""

    def __init__(self, verdict):
        self.verdict, self.questions, self.redraws = verdict, [], []

    def classify(self, message, history=()):
        self.questions.append((message, list(history)))
        return dict(self.verdict)

    def make_perfect(self, picture, kind="sketch", color="#000000", extra=None):
        assert kind in perfect.PROMPTS, f"unknown picture type: {kind}"   # the real function refuses these
        self.redraws.append(extra)
        return np.full(picture.shape[:2] + (3,), 255, np.uint8), {"model": "fake", "usage": None}


def with_fake(verdict, fn):
    fake = FakeChat(verdict)
    real = (chat.classify, perfect.make_perfect)
    chat.classify, perfect.make_perfect = fake.classify, fake.make_perfect
    api._chat_times.clear()
    api._perfect_times.clear()
    try:
        fn(fake)
    finally:
        chat.classify, perfect.make_perfect = real
        api._chat_times.clear()
        api._perfect_times.clear()
        api.USAGE_LOG.unlink(missing_ok=True)
        for var in ("CHAT_MAX_MESSAGES_PER_SESSION", "PERFECT_MAX_PER_SESSION", "API_TOKEN"):
            os.environ.pop(var, None)


def test_chat_off_topic_is_refused_and_makes_no_image():
    def run(fake):
        sid = new_session()
        r = client.post(f"/api/sessions/{sid}/chat", json={"message": "who won the cricket match?"})
        body = r.json()
        assert r.status_code == 200 and body["image"] is None and body["reply"] == chat.REFUSAL, body
        assert fake.redraws == [], "an off-topic message must not call the image model"
        assert body["perfect"]["used"] == 0 and body["chat"]["used"] == 1, body
    with_fake(OFF_TOPIC, run)


def test_chat_edit_makes_one_image_with_the_instruction():
    def run(fake):
        sid = new_session()
        r = client.post(f"/api/sessions/{sid}/chat", json={"message": "make the lines thinner"})
        body = r.json()
        assert r.status_code == 200 and body["image"].startswith("data:image/png"), body
        assert fake.redraws == ["Make the lines thinner."], fake.redraws
        assert body["reply"] == "Making the lines thinner." and body["perfect"]["used"] == 1, body
        # the next message sees the earlier turn, and refines the last perfect border
        client.post(f"/api/sessions/{sid}/chat", json={"message": "a bit more"})
        assert len(fake.questions[1][1]) == 2, fake.questions[1]
        assert client.get(f"/api/sessions/{sid}/download", params={"fmt": "perfect"}).status_code == 200
    with_fake(ON_TOPIC, run)


def test_chat_question_without_edit_makes_no_image():
    def run(fake):
        r = client.post(f"/api/sessions/{new_session()}/chat", json={"message": "how do I get thinner lines?"})
        assert r.status_code == 200 and r.json()["image"] is None and fake.redraws == [], r.text
    with_fake({**ON_TOPIC, "edit_instruction": None, "reply": "Ask me to make the lines thinner."}, run)


def test_chat_message_length_is_checked():
    sid = new_session()
    for bad in ("", "   ", "x" * (api.CHAT_MAX_CHARS + 1)):
        r = client.post(f"/api/sessions/{sid}/chat", json={"message": bad})
        assert r.status_code == 422, (len(bad), r.status_code)


def test_chat_needs_token_when_set():
    def run(fake):
        sid = new_session()
        os.environ["API_TOKEN"] = "test-secret"
        assert client.post(f"/api/sessions/{sid}/chat", json={"message": "thinner"}).status_code == 401
        ok = client.post(f"/api/sessions/{sid}/chat", json={"message": "thinner"},
                         headers={"Authorization": "Bearer test-secret"})
        assert ok.status_code == 200, ok.text
    with_fake(OFF_TOPIC, run)


def test_chat_message_limit_per_photo():
    def run(fake):
        sid = new_session()
        os.environ["CHAT_MAX_MESSAGES_PER_SESSION"] = "2"
        codes = [client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"}).status_code for _ in range(3)]
        assert codes == [200, 200, 429], codes
    with_fake(OFF_TOPIC, run)


def test_chat_edits_share_the_image_limit():
    def run(fake):
        sid = new_session()
        os.environ["PERFECT_MAX_PER_SESSION"] = "1"
        codes = [client.post(f"/api/sessions/{sid}/chat", json={"message": "thinner"}).status_code for _ in range(2)]
        assert codes == [200, 429], codes
        assert len(fake.redraws) == 1, fake.redraws
    with_fake(ON_TOPIC, run)


def test_chat_without_key_returns_502_setup_message():
    sid = new_session()
    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "thinner"})
    assert r.status_code == 502 and "OPENAI_API_KEY" in r.json()["detail"], r.text
    assert client.post(f"/api/sessions/{sid}/update", json={"method": "classic"}).json()["chat"]["used"] == 0


class FakeResponse:
    def __init__(self, content=None, status=200, refusal=None):
        self.status_code = status
        self._body = {"choices": [{"message": {"content": content, "refusal": refusal}}], "usage": {"total_tokens": 7}}
        self.text = "error"

    def json(self):
        return self._body


def classify_with(response):
    seen = {}

    def post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, body=json)
        return response

    real, had_key = chat.httpx.post, os.environ.get("OPENAI_API_KEY")
    chat.httpx.post, os.environ["OPENAI_API_KEY"] = post, "sk-test"
    try:
        return chat.classify("make it thinner", [{"role": "user", "content": "hello"}]), seen
    finally:
        chat.httpx.post = real
        os.environ.pop("OPENAI_API_KEY", None) if had_key is None else os.environ.__setitem__("OPENAI_API_KEY", had_key)


def test_chat_classify_request_and_parsing():
    answer = '{"on_topic": true, "reply": "**Okay**, thinner lines.\\n", "edit_instruction": "Make the lines thinner."}'
    verdict, seen = classify_with(FakeResponse(answer))
    body = seen["body"]
    assert body["model"] == "gpt-4.1-mini" and body["max_completion_tokens"] <= 200, body
    assert body["response_format"]["json_schema"]["strict"] is True
    assert [m["role"] for m in body["messages"]] == ["system", "user", "user"], body["messages"]
    assert body["messages"][-1]["content"] == "make it thinner"
    assert verdict["on_topic"] and verdict["edit_instruction"] == "Make the lines thinner."
    assert verdict["reply"] == "Okay, thinner lines.", verdict["reply"]
    # an off-topic verdict never carries text or an instruction, whatever the model wrote
    off, _ = classify_with(FakeResponse('{"on_topic": false, "reply": "sure!", "edit_instruction": "do evil"}'))
    assert off == {**off, "on_topic": False, "reply": "", "edit_instruction": None}, off
    # the model declining on its own counts as off topic
    declined, _ = classify_with(FakeResponse(None, refusal="I cannot help with that."))
    assert declined["on_topic"] is False
    try:
        classify_with(FakeResponse("not json"))
        raise AssertionError("an unreadable answer must raise ChatError")
    except chat.ChatError:
        pass


# ----------------------------------------------------------------- 5. Colour layers

COLOUR_SAMPLE = ROOT / "samples" / "07_color_border.jpg"


def new_colour_session(settings=CLASSIC):
    with open(COLOUR_SAMPLE, "rb") as f:
        r = client.post("/api/sessions", files={"file": (COLOUR_SAMPLE.name, f, "image/jpeg")}, data={"settings": settings})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_layers_find_the_colours_of_the_design():
    sid = new_colour_session()
    r = client.post(f"/api/sessions/{sid}/layers", json={})
    assert r.status_code == 200, r.text
    names = {e["name"] for e in r.json()["palette"]}
    assert names == {"Pink", "Orange", "Green", "Yellow"}, names
    assert r.json()["image"].startswith("data:image/png")
    assert abs(sum(e["share"] for e in r.json()["palette"]) - 1) < 1e-6


def test_layers_number_of_colours_merge_and_hide():
    sid = new_colour_session()
    url = f"/api/sessions/{sid}/layers"
    full = client.post(url, json={}).json()
    assert len(client.post(url, json={"colors": 2}).json()["palette"]) == 2
    pink = next(e["id"] for e in full["palette"] if e["name"] == "Pink")
    orange = next(e["id"] for e in full["palette"] if e["name"] == "Orange")
    merged = client.post(url, json={"merge": [[orange, pink]]}).json()["palette"]
    assert len(merged) == len(full["palette"]) - 1, merged
    hidden = client.post(url, json={"hidden": [pink]}).json()
    assert hidden["image"] != full["image"], "hiding a layer must change the preview"
    assert [e["id"] for e in hidden["palette"]] == [e["id"] for e in full["palette"]], "hiding keeps the layer list"


def test_a_pencil_sketch_has_no_colour_layers():
    """Tinted paper and shadows are not colours: a grey sketch gets an empty layer list, not false layers."""
    with open(ROOT / "samples" / "05_peacock_phone_photo.jpg", "rb") as f:
        sid = client.post("/api/sessions", files={"file": ("p.jpg", f, "image/jpeg")}, data={"settings": CLASSIC}).json()["id"]
    r = client.post(f"/api/sessions/{sid}/layers", json={})
    assert r.status_code == 200 and r.json()["palette"] == [], r.text[:200]
    assert client.get(f"/api/sessions/{sid}/download", params={"fmt": "layers-svg"}).status_code == 400


def test_layers_bad_input_is_rejected():
    sid = new_colour_session()
    url = f"/api/sessions/{sid}/layers"
    for bad in ({"colors": 99}, {"colors": -1}, {"merge": [[0, 99]]}, {"merge": [[0]]}, {"hidden": [-1]}, {"colors": "many"}):
        assert client.post(url, json=bad).status_code == 422, bad


def test_layers_need_black_and_white_output():
    sid = new_colour_session('{"method": "classic", "output": "scan"}')
    r = client.post(f"/api/sessions/{sid}/layers", json={})
    assert r.status_code == 400 and "Black & white" in r.json()["detail"], r.text


def test_layers_svg_download_has_a_group_per_colour():
    sid = new_colour_session()
    client.post(f"/api/sessions/{sid}/layers", json={})
    r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "layers-svg"})
    assert r.status_code == 200 and "_layers.svg" in r.headers["content-disposition"], r.text[:200]
    text = r.text
    assert text.count('inkscape:groupmode="layer"') == 5, text.count('inkscape:groupmode="layer"')   # 4 colours + lines
    for label in ("01 Pink", "Lines"):
        assert f'inkscape:label="{label}"' in text, label
    assert text.count("<path") >= 5, text.count("<path")                 # a path per colour + the lines


def test_layers_zip_download_has_transparent_png_layers():
    import io
    import zipfile

    from PIL import Image

    sid = new_colour_session()
    r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "layers-zip"})
    assert r.status_code == 200, r.text[:200]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "lines.png" in names and "composite.png" in names and len([n for n in names if n[:2].isdigit()]) == 4, names
    sizes = set()
    for name in names:
        im = Image.open(io.BytesIO(z.read(name)))
        assert im.mode == "RGBA", name
        sizes.add(im.size)
    assert len(sizes) == 1, f"all layer images must have the same size: {sizes}"
    first = Image.open(io.BytesIO(z.read(sorted(n for n in names if n[:2].isdigit())[0])))
    assert first.getchannel("A").getextrema() == (0, 255), "a layer is transparent except where it has colour"


def test_layers_download_respects_the_size_limit():
    sid = new_colour_session('{"method": "classic", "dpi": 1200, "width_cm": 300}')
    r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "layers-svg"})
    assert r.status_code == 422 and "too large" in r.json()["detail"], r.text


def test_colour_names_are_plain_words():
    from sketchclean.layers import colour_name
    assert colour_name((226, 112, 160)) == "Pink" and colour_name((70, 150, 84)) == "Green"
    assert colour_name((240, 150, 60)) == "Orange" and colour_name((250, 250, 250)) == "White"
    assert colour_name((40, 40, 40)) == "Black" and colour_name((140, 140, 140)) == "Grey"


# ----------------------------------------------------------------- 6. Perfect border is lines on transparent

def lines_on_white(picture, kind="sketch", color="#000000", extra=None):
    """Stand-in for the AI: a black bar on white paper, at the size of the picture."""
    rgb = np.full(picture.shape[:2] + (3,), 255, np.uint8)
    h, w = rgb.shape[:2]
    rgb[h // 2 - 8:h // 2 + 8, w // 10:w * 9 // 10] = 0
    return rgb, {"model": "fake", "usage": None}


def test_perfect_download_is_black_lines_on_transparent():
    import io

    from PIL import Image

    real = perfect.make_perfect
    seen = []

    def fake(picture, kind="sketch", color="#000000", extra=None):
        seen.append(picture)
        return lines_on_white(picture, kind, color, extra)

    perfect.make_perfect = fake
    chat_real = chat.classify
    chat.classify = lambda message, history=(): dict(ON_TOPIC)
    api._perfect_times.clear()
    api._chat_times.clear()
    try:
        sid = new_session()
        assert client.post(f"/api/sessions/{sid}/perfect").status_code == 200
        r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "perfect"})
        im = Image.open(io.BytesIO(r.content))
        assert im.mode == "RGBA", im.mode
        rgba = np.asarray(im)
        assert rgba[..., 3].min() == 0 and rgba[..., 3].max() == 255, "paper must be transparent, lines opaque"
        assert (rgba[rgba[..., 3] == 255][:, :3] == 0).all(), "the opaque pixels are the black lines"
        # the next chat edit starts from this picture, which must go back onto white paper (not black)
        assert client.post(f"/api/sessions/{sid}/chat", json={"message": "thinner"}).status_code == 200
        assert seen[-1].mean() > 200, "the last perfect border was sent as a black picture"
    finally:
        perfect.make_perfect, chat.classify = real, chat_real
        api._perfect_times.clear()
        api._chat_times.clear()
        api.USAGE_LOG.unlink(missing_ok=True)


def test_make_perfect_has_soft_edges_and_the_line_colour():
    import base64

    import cv2

    bar = np.full((1536, 1024), 255, np.uint8)
    bar[700:740, 100:900] = 0
    bar = cv2.GaussianBlur(bar, (0, 0), 1.5)                          # a soft edge, like an anti-aliased line
    png = base64.b64encode(cv2.imencode(".png", bar)[1].tobytes()).decode()

    class Answer:
        status_code, text = 200, ""

        def json(self):
            return {"data": [{"b64_json": png}], "usage": {"total_tokens": 1}}

    real_post, real_key = perfect.httpx.post, os.environ.get("OPENAI_API_KEY")
    perfect.httpx.post, os.environ["OPENAI_API_KEY"] = (lambda *a, **k: Answer()), "sk-test"
    try:
        rgb, meta = perfect.make_perfect(np.full((300, 200, 3), 255, np.uint8), "sketch", "#1d4ed8")
    finally:
        perfect.httpx.post = real_post
        os.environ.pop("OPENAI_API_KEY", None) if real_key is None else os.environ.__setitem__("OPENAI_API_KEY", real_key)
    assert max(rgb.shape[:2]) == 2400 and rgb.shape[2] == 3, rgb.shape
    ink = (rgb == (29, 78, 216)).all(axis=2)
    assert ink.any(), "fully inked pixels have exactly the line colour"
    middle_column = rgb[:, rgb.shape[1] // 2]
    assert len({tuple(px) for px in middle_column}) > 2, "the edge is soft, not a hard black/white cut"
    rgba = perfect.to_transparent(rgb, "#1d4ed8")
    assert rgba[..., 3].min() == 0 and rgba[..., 3].max() == 255
    assert (rgba[..., :3] == (29, 78, 216)).all(), "every pixel carries the line colour; only the transparency varies"


# ----------------------------------------------------------------- 7. One layered PSD

def open_psd(content):
    import io

    from psd_tools import PSDImage
    return PSDImage.open(io.BytesIO(content))


def test_layers_psd_has_background_colours_and_lines():
    sid = new_colour_session()
    r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "layers-psd"})
    assert r.status_code == 200 and "_layers.psd" in r.headers["content-disposition"], r.text[:200]
    psd = open_psd(r.content)
    assert [layer.name for layer in psd] == ["Background", "Reference (original photo)", "01 Pink", "02 Orange",
                                             "03 Green", "04 Yellow", "Lines"], [layer.name for layer in psd]
    assert all(layer.kind == "pixel" for layer in psd)
    assert [layer.visible for layer in psd] == [True, False, True, True, True, True, True], \
        "only the reference photo is hidden"
    flat = psd.composite()                                       # what Photoshop shows with every layer on
    u = 1.5                                                      # working pixels per photo pixel for this sample
    pink = flat.getpixel((int((200 + 52) * u), int(350 * u)))
    orange = flat.getpixel((int((500 + 52) * u), int(350 * u)))
    green = flat.getpixel((int(350 * u), int(350 * u)))
    assert pink[0] > 200 and pink[1] < 150, pink
    assert orange[0] > 220 and 110 < orange[1] < 200 and orange[2] < 110, orange
    assert green[1] > green[0] and green[1] > green[2], green
    assert flat.getpixel((5, 5)) == (255, 255, 255), "paper stays white"


def test_perfect_psd_puts_the_ai_lines_over_the_same_colours():
    import cv2

    shift = (3, 2)                                               # the AI redraws the lines a few pixels off

    def fake_ai(picture, kind="sketch", color="#000000", extra=None):
        ink = cv2.cvtColor(picture, cv2.COLOR_RGB2GRAY) < 60    # the dark lines of the scan
        ink = np.roll(ink, shift, axis=(0, 1))
        rgb = np.full(picture.shape[:2] + (3,), 255, np.uint8)
        rgb[ink] = (0, 0, 0)
        return rgb, {"model": "fake", "usage": None}

    real = perfect.make_perfect
    perfect.make_perfect = fake_ai
    api._perfect_times.clear()
    try:
        sid = new_colour_session()
        assert client.get(f"/api/sessions/{sid}/download", params={"fmt": "perfect-psd"}).status_code == 404, \
            "needs a perfect border first"
        assert client.post(f"/api/sessions/{sid}/perfect").status_code == 200
        r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "perfect-psd"})
        assert r.status_code == 200 and "_perfect_layers.psd" in r.headers["content-disposition"], r.text[:200]
        psd = open_psd(r.content)
        names = [layer.name for layer in psd]
        assert names[0] == "Background" and names[-1] == "Perfect border", names
        assert {"01 Pink", "02 Orange", "03 Green", "04 Yellow"} <= set(names), names
        flat = psd.composite()
        u = 1.5
        pink = flat.getpixel((int((200 + 52) * u), int(350 * u)))
        orange = flat.getpixel((int((500 + 52) * u), int(350 * u)))
        green = flat.getpixel((int(350 * u), int(350 * u)))
        assert pink[0] > 200 and pink[1] < 150, pink
        assert orange[0] > 220 and 110 < orange[1] < 200 and orange[2] < 110, orange
        assert green[1] > green[0] and green[1] > green[2], green
    finally:
        perfect.make_perfect = real
        api._perfect_times.clear()
        api.USAGE_LOG.unlink(missing_ok=True)


def test_perfect_psd_without_colours_still_has_the_lines_layer():
    """A black-and-white sketch has no colour layers: the PSD is the white background + the perfect border."""
    def fake_ai(picture, kind="sketch", color="#000000", extra=None):
        return lines_on_white(picture, kind, color, extra)

    real = perfect.make_perfect
    perfect.make_perfect = fake_ai
    api._perfect_times.clear()
    try:
        sid = new_session()
        assert client.post(f"/api/sessions/{sid}/perfect").status_code == 200
        r = client.get(f"/api/sessions/{sid}/download", params={"fmt": "perfect-psd"})
        assert r.status_code == 200, r.text[:200]
        assert [layer.name for layer in open_psd(r.content)] == ["Background", "Reference (original photo)", "Perfect border"]
    finally:
        perfect.make_perfect = real
        api._perfect_times.clear()
        api.USAGE_LOG.unlink(missing_ok=True)


# ----------------------------------------------------------------- 8. AI layers (layer_pipeline.py)

import layer_pipeline  # noqa: E402

LAYERS = [{"name": "Outline", "description": "All the black outlines of the design.", "fill_color": "#222222",
           "border_color": "#111111"},
          {"name": "Flowers", "description": "The dark pink flower petals.", "fill_color": "#e04080",
           "border_color": "#C2185B"},
          {"name": "Leaves", "description": "The green leaves.", "fill_color": "#80b040", "border_color": "#558b2f"}]


def analysis(**changes):
    return {"image_type": "color", "is_complete": True, "is_symmetric": False, "mirror": False,
            "background_color": "#1f7a78", "layers": LAYERS, **changes}


class Answer:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


class FakeOpenAI:
    """Replaces httpx.post: the analysis (chat completions) and the outline picture (image edits)."""

    def __init__(self, answer, fail=False):
        self.answer, self.fail = answer, fail               # fail: the image call fails
        self.chats, self.images = [], []

    def __call__(self, url, json=None, data=None, files=None, headers=None, timeout=None):
        import base64

        import cv2
        if "chat/completions" in url:
            self.chats.append(json)
            content = self.answer if isinstance(self.answer, str) else __import__("json").dumps(self.answer)
            return Answer(200, {"choices": [{"message": {"content": content, "refusal": None}}], "usage": {"total_tokens": 5}})
        self.images.append({"data": data, "files": files})
        if self.fail:
            return Answer(500, {"error": {"message": "the image model is busy"}})
        if data.get("background") == "transparent":                          # a model that draws on transparency
            img = np.zeros((1536, 1024, 4), np.uint8)
            img[600:640, 100:300] = (180, 40, 120, 255)
        else:                                                                # drawn on white: the white becomes transparent
            img = np.full((1536, 1024, 3), 255, np.uint8)
            img[600:640, 100:300] = (180, 40, 120)
        png = base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode()
        return Answer(200, {"data": [{"b64_json": png}], "usage": {"total_tokens": 9}})


def with_openai(answer, fn, fail=False):
    fake = FakeOpenAI(answer, fail)
    real_post, real_key = perfect.httpx.post, os.environ.get("OPENAI_API_KEY")
    perfect.httpx.post, os.environ["OPENAI_API_KEY"] = fake, "sk-test"
    api._perfect_times.clear()
    api._chat_times.clear()
    try:
        fn(fake)
    finally:
        perfect.httpx.post = real_post
        os.environ.pop("OPENAI_API_KEY", None) if real_key is None else os.environ.__setitem__("OPENAI_API_KEY", real_key)
        api._perfect_times.clear()
        api._chat_times.clear()
        api.USAGE_LOG.unlink(missing_ok=True)
        for var in ("PERFECT_MAX_PER_HOUR", "AI_LAYERS_MAX_RUNS_PER_SESSION", "API_TOKEN"):
            os.environ.pop(var, None)


def analyse(sid, machine="embroidery"):
    return client.post(f"/api/sessions/{sid}/ai-analyse", json={"machine": machine})


def test_ai_analysis_picks_layers_and_the_model():
    def run(fake):
        sid = new_colour_session()
        r = analyse(sid, "embroidery")
        assert r.status_code == 200, r.text
        plan = r.json()["plan"]
        assert plan["model"] == layer_pipeline.MODEL_COMPLETE and plan["machine"] == "embroidery"
        assert [x["name"] for x in plan["layers"]] == ["Outline", "Flowers", "Leaves"] and r.json()["runs"] == {"used": 0, "limit": 2}
        body = fake.chats[0]
        assert body["model"] == "gpt-4.1-mini" and body["response_format"]["json_schema"]["strict"] is True
        user = body["messages"][1]["content"]
        assert user[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"), "the photo is sent as it was uploaded"
        assert "thread colour" in body["messages"][0]["content"] and "Embroidery" in user[0]["text"]
        analyse(sid, "cad")
        assert "one layer per motif" in fake.chats[1]["messages"][0]["content"]
        analyse(sid, "print")
        assert "one layer per ink colour" in fake.chats[2]["messages"][0]["content"]
    with_openai(analysis(), run)


def test_ai_analysis_routes_an_incomplete_design_to_the_other_model():
    def run(fake):
        plan = analyse(new_colour_session()).json()["plan"]
        assert plan["is_complete"] is False and plan["model"] == layer_pipeline.MODEL_INCOMPLETE
        assert layer_pipeline.MODEL_COMPLETE != layer_pipeline.MODEL_INCOMPLETE
    with_openai(analysis(is_complete=False), run)


def test_ai_analysis_cleans_up_what_the_ai_says():
    many = [{"name": "Petals", "description": f"Petal group {n}."} for n in range(12)] + [{"name": "", "description": "no name"}]

    def run(fake):
        plan = analyse(new_colour_session()).json()["plan"]
        names = [x["name"] for x in plan["layers"]]
        assert len(names) == layer_pipeline.MAX_LAYERS and len({n.lower() for n in names}) == len(names), names
        assert plan["mirror"] is False, "mirror counts only for a symmetric design"
        assert analyse(new_colour_session(), "banana").status_code == 422
    with_openai(analysis(layers=many, mirror=True, is_symmetric=False), run)


def test_ai_analysis_errors_are_readable():
    def unreadable(fake):
        r = analyse(new_colour_session())
        assert r.status_code == 502 and "could not be read" in r.json()["detail"], r.text
        assert client.post(f"/api/sessions/{new_colour_session()}/update", json={"method": "classic"}).json()["chat"]["used"] == 0
    with_openai("this is not json", unreadable)

    def empty(fake):
        r = analyse(new_colour_session())
        assert r.status_code == 502 and "could not find any layers" in r.json()["detail"], r.text
    with_openai(analysis(layers=[]), empty)
    r = analyse(new_colour_session())                                           # no key: the setup message
    assert r.status_code == 502 and "OPENAI_API_KEY" in r.json()["detail"], r.text


def ai_layers_of(sid):
    """The layers kept for this photo: [(name, rgba)], the background colour first."""
    return api._sessions[sid].ai_layers["layers"]


def test_ai_layers_make_one_image_call_and_cut_it_into_aligned_layers():
    def run(fake):
        sid = new_colour_session()
        assert client.post(f"/api/sessions/{sid}/ai-layers").status_code == 400, "check the design first"
        analyse(sid, "embroidery")
        r = client.post(f"/api/sessions/{sid}/ai-layers")
        assert r.status_code == 200, r.text
        assert len(fake.images) == 1, "ONE image call for all the layers"
        names = [x["name"] for x in r.json()["layers"]]
        assert names[0] == "Background colour", "the background colour is one extra layer, made without an AI call"
        assert len(names) > 1 and all(n in ("Outline", "Flowers", "Leaves") or "details" in n for n in names[1:]), names
        assert r.json()["image"].startswith("data:image/png") and r.json()["runs"] == {"used": 1, "limit": 2}
        call = fake.images[0]["data"]
        prompt = call["prompt"]
        assert "Machine type: Embroidery" in prompt and "OUTLINES ONLY" in prompt and "NO FILL" in prompt
        assert "EXACTLY the same position" in prompt and all(l["description"] in prompt for l in LAYERS)
        assert call["model"] == layer_pipeline.MODEL_COMPLETE and "pure white" in prompt, "2.5 draws on white"
        layers = ai_layers_of(sid)[1:]
        drawn = [rgba[..., 3] > 0 for _, rgba in layers]
        assert sum(d.sum() for d in drawn) > 0 and not (sum(d.astype(int) for d in drawn) > 1).any(), \
            "every outline pixel is in exactly one layer: the layers never overlap and always line up"
        for name, rgba in layers:
            assert (rgba[..., 3] > 0).any(), f"{name}: layers without outlines are left out"
            layer = next((l for l in LAYERS if l["name"] == name), None)
            if layer:
                assert tuple(rgba[rgba[..., 3] > 0][0][:3]) == tuple(layer_pipeline._rgb(layer["border_color"].lower())), \
                    f"{name} is drawn in its own border colour"
        psd = open_psd(client.get(f"/api/sessions/{sid}/download", params={"fmt": "ai-layers-psd"}).content)
        assert [x.name for x in psd] == ["Background", "Reference (original photo)"] + names, [x.name for x in psd]
        assert [x.visible for x in psd] == [True, False] + [True] * len(names)
        assert psd.composite().getpixel((5, 5)) == (0x1f, 0x7a, 0x78), "the background colour layer covers the page"
        hidden = client.get(f"/api/sessions/{sid}/ai-layers", params={"hidden": "0"}).json()
        assert hidden["image"] != r.json()["image"] and hidden["made"] is True
        logged = [json.loads(line) for line in api.USAGE_LOG.read_text(encoding="utf-8").splitlines()]
        made = [x for x in logged if x["source"] == "ai-layers"]
        assert len(made) == 1 and made[0]["prompt"] and made[0]["layer"] == ", ".join(names[1:])
        assert any(x["source"] == "ai-analyse" and x["analysis"]["layers"] == ["Outline", "Flowers", "Leaves"] for x in logged)
    with_openai(analysis(), run)


def test_outlines_go_to_the_layer_of_the_colour_the_photo_has_there():
    photo = np.zeros((60, 100, 3), np.uint8)
    photo[:, :50] = (0, 0, 255)                                         # left half blue flowers
    photo[:, 50:] = (255, 0, 128)                                       # right half pink flowers
    photo[:8] = (255, 255, 255)                                         # a strip of background at the top
    outlines = np.zeros((60, 100, 4), np.uint8)
    outlines[10:50, 10:12, 3] = 255                                     # a line on the blue side ...
    outlines[10:50, 88:90, 3] = 255                                     # ... and one on the pink side
    outlines[2:4, 10:20, 3] = 255                                       # an edge in the background, next to blue
    plan = {"image_type": "color", "mirror": False, "background_color": "#ffffff",
            "layers": [{"name": "Blue", "fill_color": "#0000ff", "border_color": "#000080"},
                       {"name": "Pink", "fill_color": "#ff0080", "border_color": "#800040"}]}
    (blue_name, blue), (pink_name, pink) = layer_pipeline.split_layers(outlines, photo, plan)
    assert (blue_name, pink_name) == ("Blue", "Pink")
    assert blue[10:50, 10:12, 3].all() and not pink[10:50, 10:12, 3].any(), "the blue side's line is in Blue only"
    assert pink[10:50, 88:90, 3].all() and not blue[10:50, 88:90, 3].any(), "the pink side's line is in Pink only"
    assert blue[2:4, 10:20, 3].all(), "a line on the background goes to the nearest object's layer"
    assert tuple(blue[20, 10, :3]) == (0, 0, 128) and tuple(pink[20, 88, :3]) == (128, 0, 64), "each in its border colour"
    one = layer_pipeline.split_layers(outlines, photo, {**plan, "image_type": "line"})
    assert [n for n, _ in one] == ["Outlines"] and tuple(one[0][1][20, 10, :3]) == (0x1a, 0x1a, 0x1a), \
        "line art has one colour: one outline layer"


def test_a_colour_the_ai_did_not_name_gets_its_own_layer():
    photo = np.zeros((80, 120, 3), np.uint8)
    photo[:] = (20, 120, 115)                                            # teal background
    photo[10:70, 10:50] = (40, 210, 230)                                 # blue flower
    photo[30:50, 70:110] = (235, 240, 220)                               # white beads: not named by the AI
    outlines = np.zeros((80, 120, 4), np.uint8)
    outlines[20:60, 29:32, 3] = 255                                      # inside the blue flower
    outlines[39:42, 75:105, 3] = 255                                     # through the white beads
    plan = {"image_type": "color", "mirror": False, "background_color": "#147873",
            "layers": [{"name": "Blue Flowers", "fill_color": "#28d2e6", "border_color": "#0e8fa6"}]}
    out = dict(layer_pipeline.split_layers(outlines, photo, plan))
    assert set(out) == {"Blue Flowers", "White details"}, list(out)
    assert out["Blue Flowers"][25:55, 28:33, 3].any() and not out["Blue Flowers"][:, 65:, 3].any(), \
        "the white beads are NOT drawn in the blue flowers' layer"
    assert out["White details"][38:43, 80:100, 3].any(axis=0).all(), "they get their own layer"
    assert (out["White details"][..., 3] > 0).sum(axis=0).max() <= 6, "thick lines are made thin and even"


def test_ai_layers_incomplete_design_uses_the_transparent_model_and_a_line_design_one_colour():
    def run(fake):
        sid = new_colour_session()
        analyse(sid, "print")
        assert client.post(f"/api/sessions/{sid}/ai-layers").status_code == 200
        call = fake.images[0]["data"]
        assert len(fake.images) == 1 and call["model"] == layer_pipeline.MODEL_INCOMPLETE
        assert call["background"] == "transparent" and call["output_format"] == "png"
        assert "Machine type: Digital Print" in call["prompt"] and "fully transparent" in call["prompt"]
        assert sum((rgba[..., 3] > 0).sum() for _, rgba in ai_layers_of(sid)[1:]) > 0, "the model's own transparency is used"
    with_openai(analysis(is_complete=False), run)

    def line(fake):
        sid = new_colour_session()
        analyse(sid, "cad")
        assert client.post(f"/api/sessions/{sid}/ai-layers").status_code == 200
        assert "one dark colour (#1a1a1a)" in fake.images[0]["data"]["prompt"] and "Machine type: CAD" in fake.images[0]["data"]["prompt"]
        assert [n for n, _ in ai_layers_of(sid)] == ["Background colour", "Outlines"], "line art: one outline layer"
        flat = open_psd(client.get(f"/api/sessions/{sid}/download", params={"fmt": "ai-layers-psd"}).content).composite()
        assert flat.getpixel((5, 5)) == (255, 255, 255), "a line design has a white background colour"
    with_openai(analysis(image_type="line"), line)


def test_ai_layers_of_a_symmetric_design_are_drawn_as_a_half_and_mirrored():
    def run(fake):
        sid = new_colour_session()
        analyse(sid)
        assert client.post(f"/api/sessions/{sid}/ai-layers").status_code == 200
        assert "LEFT HALF" in fake.images[0]["data"]["prompt"]
        flat = open_psd(client.get(f"/api/sessions/{sid}/download", params={"fmt": "ai-layers-psd"}).content).composite()
        arr = np.asarray(flat)
        assert arr.shape[1] % 2 == 0, "the left half and its mirror"
        assert np.array_equal(arr[:, : arr.shape[1] // 2], arr[:, ::-1][:, : arr.shape[1] // 2]), "the right half is its mirror"
    with_openai(analysis(is_symmetric=True, mirror=True), run)


def test_ai_layers_respect_the_token_and_the_limits():
    def run(fake):
        sid = new_colour_session()
        os.environ["API_TOKEN"] = "test-secret"
        assert analyse(sid).status_code == 401 and client.post(f"/api/sessions/{sid}/ai-layers").status_code == 401
        assert fake.chats == [] and fake.images == [], "nothing is paid without the token"
        os.environ.pop("API_TOKEN")
        analyse(sid)
        os.environ["PERFECT_MAX_PER_HOUR"] = "0"                              # the hour is full
        assert client.post(f"/api/sessions/{sid}/ai-layers").status_code == 429 and fake.images == []
        assert client.get(f"/api/sessions/{sid}/ai-layers").json()["runs"]["used"] == 0, "a refused run is not counted"
        os.environ.pop("PERFECT_MAX_PER_HOUR")
        os.environ["AI_LAYERS_MAX_RUNS_PER_SESSION"] = "1"
        assert client.post(f"/api/sessions/{sid}/ai-layers").status_code == 200
        assert len(api._perfect_times) == 1, "one hourly slot for all the layers"
        assert client.post(f"/api/sessions/{sid}/ai-layers").status_code == 429 and len(fake.images) == 1
    with_openai(analysis(), run)


def test_ai_layers_that_fail_cost_nothing():
    def run(fake):
        sid = new_colour_session()
        analyse(sid)
        r = client.post(f"/api/sessions/{sid}/ai-layers")
        assert r.status_code == 502 and "the image model is busy" in r.json()["detail"], r.text
        assert client.get(f"/api/sessions/{sid}/ai-layers").json()["runs"]["used"] == 0, "nothing made: the run is not counted"
        assert len(api._perfect_times) == 0, "the hourly slot is given back"
        assert client.get(f"/api/sessions/{sid}/download", params={"fmt": "ai-layers-psd"}).status_code == 404
    with_openai(analysis(), run, fail=True)


def test_a_fast_upload_makes_only_the_scan_and_the_lines_when_a_file_needs_them():
    api.LINES_ON_UPLOAD = False
    try:
        with open(COLOUR_SAMPLE, "rb") as f:
            r = client.post("/api/sessions", files={"file": (COLOUR_SAMPLE.name, f, "image/jpeg")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["previews"]["scan"].startswith("data:image/jpeg") and body["previews"]["final"] is None
        assert body["info"]["closed_boxes"] is None and body["info"]["width"] > 0
        entry = api._sessions[body["id"]]
        assert entry.sess.clean is None, "the slow line steps did not run on upload"
        assert client.get(f"/api/sessions/{body['id']}/download", params={"fmt": "png"}).status_code == 200
        assert entry.sess.clean is not None, "a download makes the lines when they are needed"
    finally:
        api.LINES_ON_UPLOAD = True


def test_refit_keeps_a_background_that_touches_the_page_edge():
    from sketchclean.layers import refit_to_lines

    labels = np.zeros((40, 40), np.int8)                      # layer 0 = the background colour everywhere ...
    labels[10:30, 10:30] = 1                                  # ... and layer 1 inside a box
    lines = np.zeros((40, 40), bool)
    lines[9:11, 9:31] = lines[29:31, 9:31] = lines[9:31, 9:11] = lines[9:31, 29:31] = True
    out = refit_to_lines(labels, lines, 2.0)
    assert out[2, 2] == 0 and out[35, 20] == 0, "the open background keeps its colour"
    assert out[20, 20] == 1, "the closed box gets its own colour"
    assert out[9, 20] in (0, 1), "the colour continues under the line"


# ----------------------------------------------------------------- runner

def test_transform_flips_mirrors_resizes_and_repeats_the_motif():
    rgba = np.zeros((10, 20, 4), np.uint8)
    rgba[:, :5] = (255, 0, 0, 255)                                    # a red stripe on the left
    T = api.TransformIn
    assert (api.transform_rgba(rgba, T(flip_h=True))[:, -5:, 0] == 255).all(), "flip: the stripe is on the right"
    m = api.transform_rgba(rgba, T(mirror_half=True))
    assert m.shape == rgba.shape and (m[:, -5:, 0] == 255).all() and (m[:, :5, 0] == 255).all(), "mirror half"
    assert (api.transform_rgba(rgba, T(flip_v=True)) == rgba).all(), "nothing changes top to bottom here"
    cm = lambda px: px * 2.54 / 100                                   # at 100 DPI
    keep = api.transform_rgba(rgba, T(width_cm=cm(40), dpi=100))
    assert keep.shape[:2] == (20, 40), "only a width keeps the shape"
    rep = api.transform_rgba(rgba, T(width_cm=cm(60), height_cm=cm(10), fill="repeat", dpi=100))
    assert rep.shape[:2] == (10, 60) and (rep[:, 20:25, 0] == 255).all() and (rep[:, 40:45, 0] == 255).all(), \
        "repeat: the motif is tiled across the new width"
    fit = api.transform_rgba(rgba, T(width_cm=cm(60), height_cm=cm(10), fill="fit", dpi=100))
    assert fit.shape[:2] == (10, 60) and fit[:, :20, 3].max() == 0, "fit: transparent around the picture"
    try:
        api.transform_rgba(rgba, T(width_cm=300, height_cm=300, dpi=1200))
        raise AssertionError("a huge size must be refused")
    except api.HTTPException as e:
        assert e.status_code == 422 and "too large" in e.detail


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
