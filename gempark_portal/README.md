# Hotel Gem Park, Ooty — Owner Portal

The hotel-facing portal for Nora, the Gem Park voice agent. Built like the Lotus
Sutra portal (`client_dashboard/`), but Nora takes no bookings, so it shows only:

- **Overview** — calls today / this week, callbacks waiting, hot leads, call volume, languages, busiest hours
- **Calls** — every call with its recording, transcript and the post-call review (summary, lead level, dates, guests)
- **Callbacks** — guests who asked about booking, rates or events (by call or WhatsApp); "Mark contacted" when done
- **WhatsApp** — bot conversations, and whether each caller got the thank-you message
- **Settings** — change the portal password

Reads only the `gp_calls` and `gp_whatsapp_sessions` tables (`supabase_gempark.sql`)
and the `recordings` storage bucket. Per-call Gemini/VoBiz costs are never sent.

## Backend — `backend/` (FastAPI, port 8004)

```bash
cd gempark_portal/backend
pip install -r requirements.txt
uvicorn main:app --port 8004 --reload
```

Env (local dev reads the repo-root `.env`):
```
SUPABASE_URL=...
SUPABASE_KEY=...
GP_PORTAL_USERNAME=...       # default gempark
GP_PORTAL_PASSWORD=...       # default gempark — set a real one
GP_PORTAL_JWT_SECRET=...     # any long random string
GP_HOTEL_NAME=Hotel Gem Park, Ooty
```
A password changed in Settings is saved in `portal_settings` under the key
`gp_portal_password` and takes precedence over `GP_PORTAL_PASSWORD`.

## Frontend — `frontend/` (React + Vite + Tailwind, port 5175)

```bash
cd gempark_portal/frontend
npm install
npm run dev      # http://localhost:5175  (proxies /api -> :8004)
npm run build    # production build -> dist/
```

## Deploy on Railway — two new services from this repo, branch `gempark-ooty`

| Service | Root directory | Variables |
|---|---|---|
| Gem Park portal backend | `gempark_portal/backend` | the backend env above |
| Gem Park portal frontend | `gempark_portal/frontend` | `BACKEND_URL=https://<backend public domain>` |

Each folder has its own `Dockerfile` and `railway.toml`. Give both a public domain;
the frontend's nginx proxies `/api/` to `BACKEND_URL`.
