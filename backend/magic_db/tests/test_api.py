import base64
import io
import threading
import uuid

from PIL import Image

from .conftest import login, register, session_of


def png_data_url(w=300, h=200):
    out = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def phone():
    return "9" + str(uuid.uuid4().int)[:9]


def version(kind, **kw):
    return {"kind": kind, "label": kind.capitalize(), "image_url": png_data_url(), **kw}


def test_login_signup_gives_trial(client):
    h = login(client, phone(), "Ravi", "Ravi Prints")
    me = client.get("/api/me", headers=h).json()
    assert me["role"] == "owner" and me["account"]["business_name"] == "Ravi Prints"
    b = client.get("/api/billing", headers=h).json()
    assert b["plan"]["id"] == "free" and b["credits"]["balance"] == 100
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"X-Session-Token": "nope"}).status_code == 401


def test_register_validation_and_password_login(client):
    p = "+91" + phone()
    bad = register(client, p, gstin="24ABCDE1234")
    assert bad.status_code == 422 and "GST" in bad.json()["detail"]
    assert register(client, p, password="short").status_code == 422
    assert register(client, p, pincode="12").status_code == 422
    r = register(client, p, gstin="24abcde1234f1z5", email="Ravi@Example.com", address="Ring Road",
                 city="Surat", state="Gujarat", pincode="395002")
    assert r.status_code == 201, r.text
    assert "token" not in r.text and "mo_session" in r.headers["set-cookie"]
    assert "httponly" in r.headers["set-cookie"].lower() and "Path=/" in r.headers["set-cookie"]
    acc = r.json()["account"]
    assert (acc["gstin"], acc["email"], acc["city"], acc["pincode"]) == ("24ABCDE1234F1Z5", "ravi@example.com",
                                                                         "Surat", "395002")
    assert register(client, p).status_code == 409
    client.cookies.clear()

    assert client.post("/api/auth/login", json={"phone": p, "password": "wrong-pass"}).status_code == 401
    ok = client.post("/api/auth/login", json={"phone": p[3:], "password": "secret123"})   # 10 digits also work
    assert ok.status_code == 200 and ok.json()["role"] == "owner"
    assert client.get("/api/me").status_code == 200                                       # cookie login
    assert client.post("/api/auth/logout").json()["ok"]
    assert client.get("/api/me").status_code == 401


def test_login_lock_after_wrong_passwords(client):
    p = phone()
    login(client, p)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"phone": p, "password": "nope-nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"phone": p, "password": "secret123"}).status_code == 429


def test_change_and_reset_password(client):
    p = phone()
    h = login(client, p)
    other = session_of(client.post("/api/auth/login", json={"phone": p, "password": "secret123"}))
    client.cookies.clear()
    r = client.post("/api/auth/password/change", json={"current_password": "bad-one!", "new_password": "newpass99"},
                    headers=h)
    assert r.status_code == 401
    r = client.post("/api/auth/password/change", json={"current_password": "secret123", "new_password": "newpass99"},
                    headers=h)
    assert r.json()["ok"]
    assert client.get("/api/me", headers=h).status_code == 200          # this device stays logged in
    assert client.get("/api/me", headers=other).status_code == 401      # other devices are logged out

    assert client.post("/api/auth/password/reset/request", json={"phone": phone()}).json() == {"sent": True,}
    code = client.post("/api/auth/password/reset/request", json={"phone": p}).json()["dev_code"]
    assert client.post("/api/auth/password/reset", json={"phone": p, "code": "000000", "new_password": "again123"}
                       ).status_code == 400
    assert client.post("/api/auth/password/reset", json={"phone": p, "code": code, "new_password": "again123"}
                       ).json()["ok"]
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.post("/api/auth/login", json={"phone": p, "password": "again123"}).status_code == 200


def test_otp_login_and_attempt_limit(client):
    p = phone()
    code = client.post("/api/auth/otp/send", json={"phone": p}).json()["dev_code"]
    r = client.post("/api/auth/otp/verify", json={"phone": p, "code": code, "business_name": "OTP shop"})
    assert r.status_code == 200 and r.json()["account"]["business_name"] == "OTP shop"
    client.post("/api/auth/otp/send", json={"phone": p})
    for _ in range(5):
        assert client.post("/api/auth/otp/verify", json={"phone": p, "code": "000000x"}).status_code == 401
    assert client.post("/api/auth/otp/verify", json={"phone": p, "code": "1"}).status_code == 429


def test_parties_designs_versions_chats(client):
    h = login(client, phone())
    r = client.post("/api/parties", json={"name": "Shree Textiles", "usual_motifs": "Paisley",
                                          "line_thickness": "medium", "default_formats": ["EPS", "bmp"]}, headers=h)
    assert r.status_code == 200, r.text
    party = r.json()
    assert party["default_formats"] == ["eps", "bmp"] and "Paisley" in party["ai_summary"]
    assert client.post("/api/parties", json={"name": "Shree Textiles"}, headers=h).status_code == 409

    d = client.post("/api/designs", json={"party_id": party["id"], "name": "Paisley border"}, headers=h).json()
    raw = client.post(f"/api/designs/{d['id']}/versions", json=version("raw", make_current=False), headers=h).json()
    assert raw["width_px"] == 300 and raw["image_url"].startswith("/api/backend/files/acc/")
    img = client.get(raw["image_url"].replace("/api/backend", "/api"))
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get(raw["image_url"].replace("/api/backend", "/api").replace("s=", "s=0")).status_code == 403
    out = client.post(f"/api/designs/{d['id']}/versions",
                      json=version("outline", parent_id=raw["id"], dpi=300, settings={"thickness": 70}),
                      headers=h).json()
    # a saved link sent back is copied, not shared
    again = client.post(f"/api/designs/{d['id']}/versions", json={**version("outline"), "image_url": out["image_url"]},
                        headers=h)
    assert again.status_code == 200, again.text

    full = client.get(f"/api/designs/{d['id']}", headers=h).json()
    assert [v["kind"] for v in full["versions"]] == ["raw", "outline", "outline"]
    assert full["current_version_id"] == again.json()["id"]
    assert client.post(f"/api/designs/{d['id']}/exports", json={"format": "svg"}, headers=h).json()["ok"]
    assert client.post(f"/api/designs/{d['id']}/exports", json={"format": "svg"}, headers=h).json()["ok"]
    assert client.get(f"/api/designs/{d['id']}", headers=h).json()["last_exports"] == ["svg"]

    c = client.post("/api/chats", json={"design_id": d["id"], "title": "Clean it"}, headers=h).json()
    assert c["party_id"] == party["id"]
    for i in range(3):
        client.post(f"/api/chats/{c['id']}/messages", json={"role": "user", "content": f"lotus buds {i}"}, headers=h)
    m = client.post(f"/api/chats/{c['id']}/messages",
                    json={"role": "assistant", "content": "Done", "attachment_version_id": out["id"],
                          "credits_used": 3}, headers=h).json()
    chat = client.get(f"/api/chats/{c['id']}", headers=h).json()
    assert len(chat["messages"]) == 4 and chat["result_label"] == "Made Outline · 3 credits"
    assert client.get("/api/chats?q=lotus", headers=h).json()[0]["id"] == c["id"]
    assert client.get("/api/chats?q=peacock", headers=h).json() == []
    ctx = client.get(f"/api/chats/{c['id']}/ai-context", headers=h).json()
    assert ctx["last_messages"] == 4 and ctx["current_image"] == "Outline"
    assert client.get(f"/api/designs/{d['id']}", headers=h).json()["versions"][1]["chat_message_id"] == m["id"]

    p = client.get(f"/api/parties/{party['id']}", headers=h).json()
    assert (p["design_count"], p["chat_count"], p["raw_count"]) == (1, 1, 1)
    r = client.post(f"/api/parties/{party['id']}/references", json={"version_ids": [out["id"], raw["id"]]}, headers=h)
    assert r.json()["reference_version_ids"] == [out["id"], raw["id"]]

    layers = client.put(f"/api/versions/{out['id']}/layers",
                        json={"layers": [{"color": "#B91C1C", "name": "Red"}, {"color": "#000", "name": ""}]},
                        headers=h).json()
    assert [x["name"] for x in layers] == ["Red", "Layer 2"]

    assert client.delete(f"/api/designs/{d['id']}", headers=h).json()["ok"]
    assert client.get(raw["image_url"].replace("/api/backend", "/api")).status_code == 404
    assert client.get(f"/api/parties/{party['id']}", headers=h).json()["reference_version_ids"] == []


def test_shops_cannot_see_each_other(client):
    a, b = login(client, phone()), login(client, phone())
    party = client.post("/api/parties", json={"name": "Secret"}, headers=a).json()
    d = client.post("/api/designs", json={"party_id": party["id"], "name": "X"}, headers=a).json()
    assert client.get(f"/api/parties/{party['id']}", headers=b).status_code == 404
    assert client.get(f"/api/designs/{d['id']}", headers=b).status_code == 404
    assert client.post("/api/designs", json={"party_id": party["id"], "name": "Y"}, headers=b).status_code == 404
    assert client.get("/api/parties", headers=b).json() == []


def test_credits_reserve_settle_and_limits(client):
    h = login(client, phone())
    r = client.post("/api/credits/reserve", json={"action": "multi_colour"}, headers=h).json()
    assert (r["cost"], r["balance"]) == (3, 97)
    assert client.post(f"/api/credits/{r['hold_id']}/settle", json={"ok": False}, headers=h).json()["balance"] == 100
    assert client.post(f"/api/credits/{r['hold_id']}/settle", json={"ok": False}, headers=h).json()["balance"] == 100
    assert client.post("/api/credits/reserve", json={"action": "multi_colour_hd"}, headers=h).status_code == 402
    for count in (3, 20):                                     # 9 + 60 credits spent: 31 left
        r = client.post("/api/credits/reserve", json={"action": "multi_colour", "count": count}, headers=h).json()
        client.post(f"/api/credits/{r['hold_id']}/settle", json={"ok": True}, headers=h)
    assert client.post("/api/credits/reserve", json={"action": "multi_colour", "count": 11}, headers=h).status_code == 402
    usage = client.get("/api/billing/usage", headers=h).json()
    assert [u["change"] for u in usage] == [-60, -9, 100]     # the given-back reserve is hidden
    assert client.get("/api/billing", headers=h).json()["credits"]["used_this_period"] == 69


def test_two_requests_cannot_spend_the_same_credits(client):
    h = login(client, phone())
    results = []

    def go():
        results.append(client.post("/api/credits/reserve", json={"action": "multi_colour", "count": 20},
                                   headers=h).status_code)
    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 402, 402, 402]
    assert client.get("/api/billing", headers=h).json()["credits"]["balance"] == 40      # 100 - 60


def test_plans_team_seats_and_top_up(client):
    owner_phone, designer_phone = phone(), phone()
    h = login(client, owner_phone)
    assert [p["id"] for p in client.get("/api/plans").json()] == ["free", "starter", "pro", "studio"]
    assert client.post("/api/team/invite", json={"phone": designer_phone}, headers=h).status_code == 402
    assert client.post("/api/billing/top-up", json={"credits": 50}, headers=h).status_code == 402
    assert client.post("/api/billing/plan", json={"plan_id": "pro"}, headers=h).json()["ok"]
    b = client.get("/api/billing", headers=h).json()
    assert b["plan"]["id"] == "pro" and b["credits"]["balance"] == 570
    assert client.post("/api/billing/top-up", json={"credits": 50}, headers=h).json()["balance"] == 620
    r = client.post("/api/team/invite", json={"phone": designer_phone, "full_name": "Asha"}, headers=h).json()
    temp = r["temp_password"]
    d = session_of(client.post("/api/auth/login", json={"phone": designer_phone, "password": temp}))
    client.cookies.clear()
    me = client.get("/api/me", headers=d).json()
    assert me["role"] == "designer" and me["account"]["id"] == client.get("/api/me", headers=h).json()["account"]["id"]
    assert client.post("/api/billing/plan", json={"plan_id": "studio"}, headers=d).status_code == 403
    assert len(client.get("/api/team", headers=h).json()) == 2
    uid = me["user"]["id"]
    assert client.delete(f"/api/team/{uid}", headers=h).json()["ok"]
    assert client.get("/api/me", headers=d).status_code == 401


def test_monthly_renewal_and_carry_over():
    from datetime import timedelta

    from magic_db import auth, credits
    from magic_db.db import session_scope
    with session_scope() as db:
        m = auth.get_or_create_user(db, auth.normalise_phone(phone()))
        sub = credits.set_plan(db, m.account_id, "pro", "monthly")     # 100 trial + 470
        db.flush()
        sub.next_grant_at = credits.now() - timedelta(minutes=1)
        sub.current_end = credits.now() + timedelta(days=1)            # still paid: next month's credits
        credits.renew_due(db)
        assert credits.balance(db, m.account_id) == 470 + 470          # pro keeps 1 month (470)
        sub.current_end = credits.now() - timedelta(minutes=1)         # not paid: past due
        credits.renew_due(db)
        assert sub.status == "past_due"


def test_api_token(client, monkeypatch):
    from magic_db import config
    monkeypatch.setattr(config, "API_TOKEN", "abc")
    assert client.get("/api/plans").status_code == 401
    assert client.get("/api/plans", headers={"Authorization": "Bearer abc"}).status_code == 200
