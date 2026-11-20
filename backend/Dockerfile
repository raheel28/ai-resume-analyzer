FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
ENV PYTHONUNBUFFERED=1 PORT=8000
# GEMINI_API_KEY, LLM_MODEL, CORS_ORIGINS come from the host's environment settings.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
