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
- Backend: set `ALLOWED_ORIGINS` to the website address (e.g. `https://yourapp.vercel.app`) so only your site can call it.
- Frontend: set `NEXT_PUBLIC_API_URL` to the backend address, then build again.
