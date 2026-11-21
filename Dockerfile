# Single service: builds the React frontend, then runs FastAPI, which serves
# both the API (/api/...) and the built site (/). Used by render.yaml.

# ---- 1. build the frontend
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
# Same origin as the API, so no VITE_API_BASE needed.
RUN npm run build

# ---- 2. backend + built site
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static

ENV PYTHONUNBUFFERED=1 PORT=8000 STATIC_DIR=/app/static
# GEMINI_API_KEY and other settings come from the host's environment settings.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
