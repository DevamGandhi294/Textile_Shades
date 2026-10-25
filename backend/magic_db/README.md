# magic_db: the database part of the Magic Outline backend

This folder adds registration and login, parties, designs, saved images, chats, credits, plans and
team seats to the existing FastAPI backend. It is one Python package that you drop into the
backend folder. It does not change the image code (`sketchclean/`, `/api/sessions/*`).

- **Database:** PostgreSQL 16, using SQLAlchemy 2 models (`models.py`) and Alembic migrations (`migrations/`).
- **Images:** MinIO now, Contabo later (any S3), through `storage.py` only. Postgres keeps only the keys.
- **Tests:** 12 tests run against a real PostgreSQL and S3 (`tests/`).

New to Docker or PostgreSQL? Start with **[SETUP_GUIDE.md](SETUP_GUIDE.md)**.

## Add it to the backend (2 lines)

```
backend/
  api.py            <- add the 2 lines below
  sketchclean/
  magic_db/         <- this folder
  .env              <- add the lines from magic_db/.env.example
```

In `backend/api.py`, right after `app = FastAPI(...)`:

```python
import magic_db
magic_db.setup(app)
```

Then run these from the `backend` folder:

```bash
pip install -r magic_db/requirements.txt
python -m magic_db migrate          # creates the tables
python -m magic_db create-bucket    # creates the image bucket
python api.py                       # same as before; the new routes are under /api too
```

None of the new routes clash with the existing ones (`/api/health` and `/api/sessions/*`). If
`API_TOKEN` is set, every new route checks it the same way `/perfect` does. The Next.js proxy
already sends it.

## Files

| File | What it holds |
|---|---|
| `models.py` | All tables as SQLAlchemy classes. Change a table here, then run `python -m magic_db make-migration "what changed"` and `migrate`. |
| `migrations/versions/` | `0001` creates every table and the 4 approved plans. `0002` adds password login and the shop's address. |
| `config.py` | Every setting, read from `backend/.env`. |
| `auth.py` | Mobile number + password login (scrypt hashes), forgot-password codes, login cookie, `current` user. |
| `credits.py` | Balance, reserve and settle around AI calls, plan grants, monthly renewal and carry-over. |
| `storage.py` | MinIO / Contabo / local folder, signed image links, thumbnails. |
| `summaries.py` | Chat summary + last 6 messages, the party's "What AI remembers", `ai_messages()` for the text model. |
| `routes/` | The HTTP routes (list below). |
| `__main__.py` | Commands: `migrate`, `seed-demo`, `set-plan`, `grant`, `renew-due`, `cleanup`, and more. |

## Tables

Each business table carries `account_id`, and every route filters by the logged-in shop, so one
shop can never read another shop's rows. A test checks this.

- **Accounts and team:** `accounts` (company, GSTIN, address), `users` (mobile, password hash), `account_members` (owner / designer), `login_sessions`, `otp_codes`.
- **Plans and billing:** `plans`, `subscriptions`, `credit_ledger` (append-only; balance = SUM), `credit_holds` (reserve and release), `payments`, `invoices`.
- **Parties and designs:** `parties`, `party_references` (up to 4 favourites), `designs`, `design_versions` (raw → scan → ai → outline chain, with only the storage key), `version_layers` (colour layers and their names), `area_edit_requests` + `area_selections` (one per colour), `exports`.
- **Chats and AI:** `chats` (summary + `summarised_count`), `chat_messages`, `ai_calls` (cost tracking).

## Routes (all under `/api`)

Shapes follow `frontend/lib/api/types.ts` and `frontend/docs/API.md`.

| Area | Routes |
|---|---|
| Register / login | `POST /auth/register` `{company_name, gstin, owner_name, phone, email, password, address, city, state, pincode}` returns 201 with Me · `POST /auth/login` `{phone, password}` · `POST /auth/logout` · `POST /auth/password/change` `{current_password, new_password}` · `POST /auth/password/reset/request` `{phone}` · `POST /auth/password/reset` `{phone, code, new_password}` · `POST /auth/otp/send`, `/auth/otp/verify` (SMS login, for later) |
| Me / team | `GET, PATCH /me` · `GET /team` · `POST /team/invite` `{phone, full_name}` (returns `temp_password` once) · `DELETE /team/{user_id}` |
| Parties | `GET /parties?q=&archived=` · `GET/PATCH /parties/{id}` · `POST /parties` · `POST /parties/{id}/summary/rebuild` · `POST /parties/{id}/references` |
| Designs | `GET /designs?party_id=&q=` · `GET/PATCH/DELETE /designs/{id}` · `POST /designs` · `POST /designs/{id}/versions` (image as a data URL) · `DELETE /designs/{id}/versions/{vid}` · `POST /designs/{id}/exports` · `GET/POST /designs/{id}/session` · `GET/PUT /versions/{vid}/layers` |
| Images | `GET /files/{key}?e=&s=` (signed link, works for 1 hour, no login needed so it works in `<img>`) |
| Chats | `GET /chats?party_id=&design_id=&q=` (q searches the message text) · `GET /chats/{id}` · `POST /chats` · `POST /chats/{id}/messages` · `GET /chats/{id}/ai-context` · `GET /chats/{id}/ai-messages` |
| Billing | `GET /plans` · `GET, PATCH /billing` · `GET /billing/usage` · `GET /billing/invoices` · `POST /billing/plan` · `POST /billing/top-up` · `POST /payments/razorpay/webhook` (stub) |
| Credits | `POST /credits/reserve` `{action, design_id}` · `POST /credits/{hold_id}/settle` `{ok}` |
| Health | `GET /db/health` |

The login is an httpOnly cookie, `mo_session`, set with `path=/` and no Domain. It is never put in
a response body. The Next.js proxy has to forward the `Cookie` header and send `Set-Cookie` back, and
it needs to export `PATCH` and `DELETE` as well as `GET` and `POST`.

## Charging credits in the paid image routes (for the backend developer)

The approved prices are single-layer 1 credit, multi-colour 3 and multi-colour HD 9, and chat is
free (`config.CREDIT_COST`). The old limits (3 redraws per photo, 60 an hour for the whole
server) can stay as a safety net, but the real limit is now each shop's credits. In
`/api/sessions/{sid}/perfect` (and later area edits, watermark and resize):

```python
from fastapi import Depends
from magic_db import credits
from magic_db.auth import Current, current
from magic_db.db import SessionLocal

@app.post("/api/sessions/{sid}/perfect")
def make_perfect(sid: str, source: str = "sketch", design_id: str = None, me: Current = Depends(current)):
    action = "multi_colour" if count_colours(...) >= 3 else "single_layer"   # your colour check
    with SessionLocal() as db:
        hold = credits.reserve(db, me.account_id, action, user_id=me.user_id, design_id=design_id)  # 402 if not enough
        db.commit()
    ok = False
    try:
        result = ...  # the OpenAI call, as today
        ok = bool(result)
        return result
    finally:
        with SessionLocal() as db:
            credits.settle(db, hold.id, ok)   # failed or no image: credits go back
            db.commit()
```

For chat, `summaries.ai_messages(db, chat)` gives the small context to send to the text model:
the hidden rules, the party summary, the chat summary and the last 6 messages.

## Commands

```bash
python -m magic_db migrate                      # create / update tables
python -m magic_db make-migration "add x"       # after editing models.py (read the new file, then migrate)
python -m magic_db check                        # are PostgreSQL and storage reachable?
python -m magic_db seed-demo                    # demo shop: mobile 9999999999, password demo1234
python -m magic_db set-plan 9825012345 pro      # after a manual payment (UPI / bank)
python -m magic_db grant 9825012345 50 --top-up # extra credits (a minus number takes credits away)
python -m magic_db renew-due                    # once a day: monthly credits, carry-over, past-due
python -m magic_db release-stale                # give back credits of AI calls that never finished
python -m magic_db cleanup                      # list designs older than the plan keeps files; --yes deletes
```

## Run the tests

```bash
docker compose -f magic_db/docker-compose.yml exec postgres createdb -U magic magic_outline_test
TEST_DATABASE_URL=postgresql+psycopg://magic:magic@127.0.0.1:5432/magic_outline_test \
TEST_S3_ENDPOINT_URL=http://127.0.0.1:9000 S3_ACCESS_KEY=magicadmin S3_SECRET_KEY=magicadmin123 \
pytest magic_db/tests -q
```

Leave out `TEST_S3_ENDPOINT_URL` to test with a temporary local folder instead of MinIO.

## Decisions and open points

- **Plans** come from the approved price list: Free trial (100 credits once, 0.5 GB, 30 days, watermark), Starter ₹499 (100 credits), Pro ₹1,999 (470 credits, HD, 1-month carry-over) and Studio ₹3,999 (1,000 credits, HD, 2-month carry-over). The price list has no seats or party limits, so I set seats to **1 / 1 / 3 / 10** and parties to unlimited. Change them in `plans` (with SQL or a new migration).
- **Payments are buttons only.** Plan change and top-up answer 501 ("coming soon") until Razorpay is added. Until then, sell by hand with `set-plan` and `grant`. The webhook route checks Razorpay's signature but doesn't apply payments yet.
- **Monthly credits:** `renew-due` adds them each month while the plan is paid. Unused credits above the carry-over expire. When the paid period ends, the subscription becomes `past_due` until `set-plan` runs again. Top-up credits are counted in the carry-over too.
- **Files kept for N days:** `cleanup` deletes designs that haven't changed for longer than the plan keeps files. It only lists them unless you add `--yes`.
- **Forgot password** sends a 6-digit code. While `SMS_PROVIDER=console` the code is printed in the server log. Add MSG91 or Twilio in `auth.send_sms()`.
- **Invited designers** get a temporary password, which the owner shares. They can change it under `/auth/password/change`.
