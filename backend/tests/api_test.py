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
