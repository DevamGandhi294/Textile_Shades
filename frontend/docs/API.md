# REST routes the frontend expects (database part)

These are what `lib/api/data.ts` calls when `NEXT_PUBLIC_USE_MOCKS=0`. They do not exist in the
backend yet. Shapes are the types in `lib/api/types.ts` (rows of `magic_outline_schema.sql` plus a
few joined counts). All paths are under `/api`, and every query must filter by the caller's `account_id`.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/me` | | `Me` |
| PATCH | `/me` | `{full_name, business_name, gstin}` | `{ok}` |
| GET | `/parties` | `?q=&archived=` | `Party[]` (with `design_count`, `chat_count`, `raw_count`, `last_activity_at`, `reference_version_ids`) |
| GET | `/parties/{id}` | | `Party` |
| POST | `/parties` | `PartyInput` | `Party` (402 when the plan's party limit is reached) |
| PATCH | `/parties/{id}` | `Partial<PartyInput>` or `{archived}` | `Party` |
| POST | `/parties/{id}/summary/rebuild` | | `Party` (text model writes `ai_summary`) |
| POST | `/parties/{id}/references` | `{version_ids: string[]}` (max 4) | `Party` |
| GET | `/designs` | `?party_id=&q=` | `Design[]` (with `versions`, `chat_count`, `credits_used`, `last_exports`) |
| GET | `/designs/{id}` | | `Design` |
| POST | `/designs` | `{party_id, name}` | `Design` |
| PATCH | `/designs/{id}` | `{name?, party_id?, current_version_id?}` | `Design` |
| DELETE | `/designs/{id}` | | `{ok}` |
| POST | `/designs/{id}/versions` | `NewVersion` + `make_current` | `DesignVersion` (`image_url` = signed storage link) |
| POST | `/designs/{id}/exports` | `{format}` | `{ok}` |
| GET / POST | `/designs/{id}/session` | `{sid}` | `{sid}`: which image session belongs to the design |
| GET | `/chats` | `?party_id=&design_id=&q=` | `Chat[]` (with `messages`, `result_label`) |
| GET | `/chats/{id}` | | `Chat` |
| POST | `/chats` | `{design_id, title}` | `Chat` |
| POST | `/chats/{id}/messages` | `NewMessage` | `ChatMessage` |
| GET | `/chats/{id}/ai-context` | | `AiContext` |
| GET | `/plans` | | `Plan[]` |
| GET | `/billing` | | `{subscription, plan, credits}` |
| PATCH | `/billing` | `{warn_at}` | `{ok}` |
| GET | `/billing/usage` | | `LedgerEntry[]` |
| GET | `/billing/invoices` | | `Invoice[]` |
| POST | `/billing/plan` | `{plan_id, period}` | Razorpay order / `{ok}` |
| POST | `/billing/top-up` | `{credits}` | Razorpay order / `{balance}` |
| GET | `/team` | | `Member[]` |
| POST | `/team/invite` | `{phone, full_name}` | `{ok}` |
| DELETE | `/team/{user_id}` | | `{ok}` |

Endpoints the "Needs backend" buttons will call (suggested names):

| Feature | Suggested route |
|---|---|
| Remove watermark and text | `POST /sessions/{id}/watermark` |
| Resize and fill with AI / repeat | `POST /sessions/{id}/resize` `{width_cm, height_cm, mode: "repeat" \| "ai"}` |
| Mirror and flip | new fields in `SettingsIn`: `flip_h`, `flip_v`, `mirror_half` |
| Area edit | `POST /sessions/{id}/areas` multipart: one mask PNG + prompt per colour (masks are already built in the area selector) |
| Layer names in files | `names: {id: name}` in `LayersIn` |

With the real database, credits are reserved and charged inside the paid endpoints, so
`billingApi.reserve` becomes a no-op (it already is when mocks are off).
