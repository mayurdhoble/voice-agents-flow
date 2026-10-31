# Gem Park owner portal backend. Deploy as its OWN Railway service with
# root = gempark_portal/backend (config-as-code: railway.toml in this folder).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8004

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8004}"]
