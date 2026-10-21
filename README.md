# TextileBorder OutlineTool

Turns a photo of a sketch into clean line art and files for embroidery, CorelDRAW and CAD.

```
backend/    Python: the image pipeline + AI model (sketchclean/), Gradio app, CLI, web API
frontend/   Next.js website (simple, big buttons) that calls the web API
```

## Run on your PC (two terminals)

**1. Backend** (from the project folder, with `.venv` active)
```powershell
cd backend
pip install -r requirements.txt
python api.py          # http://127.0.0.1:8000  (test page: /docs)
```
The old tools still work from `backend/`: `python app.py` (Gradio) and `python cli.py sketch.jpg`.

**2. Frontend**
```powershell
cd frontend
npm install
npm run dev            # open http://localhost:3000
```
The website finds the API through `NEXT_PUBLIC_API_URL` in `frontend/.env.local`
(see `frontend/.env.example`).

## Live site settings

**Backend** (`backend/.env` on the server; see `backend/.env.example`):
- `ALLOWED_ORIGINS` = the website address, e.g. `https://yourapp.vercel.app` (comma-separate several).
  Without it the browser blocks every request from the live site.
- `API_TOKEN` = a long random secret. It protects the paid "Make border perfect" call.
- `OPENAI_API_KEY`, plus the optional limits `PERFECT_MAX_PER_SESSION` / `PERFECT_MAX_PER_HOUR`.

**Frontend** (Vercel → Project → Settings → Environment Variables; see `frontend/.env.example`):
- `NEXT_PUBLIC_API_URL` = the backend address (used by the browser).
- `API_TOKEN` = the **same** secret as the backend. Server-only: never name it `NEXT_PUBLIC_…`.
- Optional `BACKEND_URL` if the website's server reaches the backend on a different address.
- Build again after changing them.

How the paid calls are protected: the browser calls `/api/perfect` and `/api/chat` on the website itself
(`frontend/src/app/api/perfect/route.ts`, `frontend/src/app/api/chat/route.ts`, shared checks in
`frontend/src/lib/gateway.ts`). That server route checks the request comes from the
website, checks the photo id, adds the secret token and calls the backend. The backend refuses
calls without the token, and limits calls per photo and per hour.
