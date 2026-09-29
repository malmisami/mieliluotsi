"""Mieliluotsi API.

The earlier OmaGenomi features live on in app/legacy_api.py and are mounted only when LEGACY_FEATURES_ENABLED=1.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR, settings
from app.valituki import ai
from app.valituki.router import router as valituki_router

app = FastAPI(title='Mieliluotsi API', version=settings.APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(valituki_router)


@app.get('/api/health')
def health() -> dict:
    return {
        'status': 'ok',
        'application': 'Mieliluotsi',
        'application_version': settings.APP_VERSION,
        'ai_mode': ai.effective_mode(),
        'legacy_features_enabled': bool(settings.LEGACY_FEATURES_ENABLED),
        'synthetic_data_only': True,
    }


if settings.LEGACY_FEATURES_ENABLED:
    from app.legacy_api import include_legacy_routes

    include_legacy_routes(app)

# Single-port demo: serve the production build of the frontend when it exists (npm --prefix frontend run build).
# Mounted last, so every /api route above takes precedence.
_DIST = Path(BASE_DIR) / 'frontend' / 'dist'
if (_DIST / 'index.html').exists():
    app.mount('/', StaticFiles(directory=_DIST, html=True), name='frontend')
