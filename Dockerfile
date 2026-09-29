# Mieliluotsi as one web service: the React build is served by the FastAPI backend from the same origin.
# Used by Render (render.yaml); works with any Docker host: docker build -t mieliluotsi . && docker run -p 10000:10000 mieliluotsi

# 1 · Frontend build
FROM node:20-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2 · Backend + the built frontend
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VALITUKI_AI_MODE=DEMO_AI_MODE
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/ data/
COPY --from=web /app/frontend/dist frontend/dist

# Render sets PORT; the demo state is kept in runtime/ and starts over when the service restarts.
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-10000}"]
