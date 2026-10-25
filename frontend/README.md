# Magic Outline: frontend

Next.js (App Router) + TypeScript + Tailwind CSS + TanStack Query. It follows the 7 screens in
"Magic Outline – App Screens" and talks only to the FastAPI backend in `../backend`.

## Run it

```bash
# 1. the backend (in ../backend)
python api.py                       # http://127.0.0.1:8000

# 2. the frontend
cp .env.example .env.local          # BACKEND_URL, BACKEND_API_TOKEN, NEXT_PUBLIC_USE_MOCKS
npm install
npm run dev                         # http://localhost:3000
```

The app opens straight into the workspace. There is no login page yet.

## What is live and what is demo

| Part | Status |
|---|---|
| Upload raw image, scan, AI line finder, outline | **Live**: `POST /api/sessions` |
| Apply settings (thickness, fixed width, gap fill, smooth, sharpness, width cm, DPI, colour, line finder…) | **Live**: `POST /api/sessions/{id}/update` |
| Generate (chat prompt) and redraw with AI | **Live**: `/chat` and `/perfect` (needs `OPENAI_API_KEY` in `backend/.env`) |
| Colour layers: find colours, merge, hide, show lines, PSD / SVG / PNG zip | **Live**: `/layers` and `/download` |
| Downloads SVG, EPS, PDF, DXF, BMP, TIFF, PNG, ZIP, AI PNG, AI PSD | **Live**: `/download?fmt=` |
| Check gaps view (loose line ends) | **Live**: `previews.check` |
| Parties, designs, version chain, chats, credits, plans, team, invoices | **Demo data** in the browser (`lib/mock`), because the backend has no database yet |

Anything marked **Needs backend** in the UI shows the full design but has no backend yet:

- Remove watermark and text, Fill with AI, Height and repeat-fill in Resize and fill
- Mirror and flip (flip ↔, flip ↕, mirror half)
- Area selector "Regenerate selected areas" (the page already builds one mask PNG per colour)
- "Rebuild from chats" for the party AI summary
- Import designs (saved only in the browser for now)
- Layer renaming in files, and "each layer outlined in its own colour"
- Razorpay payments, plan change, top-ups, GST invoice PDFs, inviting designers

## How it is built

```
app/
  (app)/workspace/[designId]        Screen 1: chat | raw + outline | settings / colour layers
  (app)/workspace/[designId]/areas  Screen 2: area selector (brush, box, eraser, undo)
  (app)/parties, parties/[partyId]  Screen 3: party list + profile; Screen 5: party card popup
  (app)/designs, designs/[designId] Screen 4: design detail with the linked chain
  (app)/chats?party=&chat=          Screen 6: chats + "What AI will see"
  (app)/billing                     Screen 7: account and billing
  api/backend/[...path]/route.ts    Proxy to the FastAPI backend (adds the API token server side)
components/                         Screens' parts; components/ui/primitives.tsx = buttons, inputs, dialogs…
lib/api/outline.ts                  The real backend calls (sessions, update, chat, perfect, layers, download)
lib/api/data.ts                     Parties, designs, chats, billing: demo store or REST (see docs/API.md)
lib/api/types.ts                    Types that mirror magic_outline_schema.sql
lib/mock/                           Demo database (saved in localStorage) and its seed data
```

- The browser calls `/api/backend/*` only; the Next.js server forwards to `BACKEND_URL` and adds
  `Authorization: Bearer BACKEND_API_TOKEN`. No secret reaches the browser and CORS is not needed.
- The backend keeps an uploaded photo in memory for one hour. When it has expired, the workspace
  uploads the saved raw image again and retries, so the designer never sees "expired".
- Credits are reserved before a paid call and given back if it fails or makes no image.
- When the database API exists, set `NEXT_PUBLIC_USE_MOCKS=0`. The screens stay the same; the calls
  go to the routes in `docs/API.md`.

## Checked

`npm run build` passes (type check included). Tested in a browser against the real backend:
upload a phone photo (about 17 s on CPU), apply settings, colour layers on `07_color_border.jpg`,
PSD and SVG downloads, area painting, and every page at phone width (390 px) with no sideways scroll.
Generate was tested only without an OpenAI key (it shows the server's message and charges nothing).
