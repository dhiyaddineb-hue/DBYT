"""DBYT FastAPI application entrypoint."""
from __future__ import annotations

import hmac
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, settings
from .routes import dub, upload, youtube

app = FastAPI(title=settings.app_name, version="1.0.0")
_API_KEY = os.environ.get("DBYT_API_KEY", "").strip()


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    """Protect public API routes when DBYT_API_KEY is configured.

    Health remains public for reverse-proxy checks. Local development keeps the
    historical open behavior when no key is supplied.
    """
    path = request.url.path
    if (
        _API_KEY
        and request.method != "OPTIONS"
        and path.startswith("/api/")
        and path != "/api/health"
    ):
        supplied = request.headers.get("x-api-key", "")
        if not supplied:
            authorization = request.headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                supplied = authorization[7:].strip()
        if not supplied or not hmac.compare_digest(supplied, _API_KEY):
            return JSONResponse({"detail": "API key required"}, status_code=401)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(youtube.router)
app.include_router(upload.router)
app.include_router(dub.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


# Serve the frontend (single-page app) at the root
_frontend = BASE_DIR / "frontend"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
