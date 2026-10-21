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
    assert body["model"] == "gpt-4.1-nano" and body["max_completion_tokens"] <= 200, body
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
    assert [layer.name for layer in psd] == ["Background", "01 Pink", "02 Orange", "03 Green", "04 Yellow", "Lines"], \
        [layer.name for layer in psd]
    assert all(layer.kind == "pixel" for layer in psd)
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
        assert [layer.name for layer in open_psd(r.content)] == ["Background", "Perfect border"]
    finally:
        perfect.make_perfect = real
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
