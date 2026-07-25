# Lotus Sutra — Owner Portal (Client Dashboard)

A hotel-owner–facing dashboard, separate from the internal admin panel. Shows
only business-relevant data — calls, conversations (with recordings), bookings,
guests, event enquiries, and the bookings that **need attention**. No costs,
no usage/billing, no system internals.

## Stack
React 18 + Vite + Tailwind + Recharts (same stack as the admin `dashboard/`).

## Backend
Served by `dashboard_backend/client_main.py` (FastAPI) on **port 8003**.

```bash
cd dashboard_backend
uvicorn client_main:app --port 8003 --reload
```

Client login credentials come from env (defaults `hotel` / `hotel`):
```
CLIENT_USERNAME=...
CLIENT_PASSWORD=...
CLIENT_JWT_SECRET=...   # falls back to DASHBOARD_JWT_SECRET
HOTEL_NAME=Lotus Sutra Goa
```

## Frontend
```bash
cd client_dashboard
npm install
npm run dev      # http://localhost:5174  (proxies /api -> :8003)
npm run build    # production build -> dist/
```
