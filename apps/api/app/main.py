from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import jobs, storage
from app.config import get_settings
from app.routers import auth, search, sources, stories, transcripts, workspaces

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    storage.ensure_bucket()
    with jobs.app.open():
        yield


app = FastAPI(
    title="Redazione API",
    version="0.1.0",
    lifespan=lifespan,
    # La documentazione interattiva solo fuori produzione
    docs_url=None if get_settings().is_production else "/api/docs",
    openapi_url=None if get_settings().is_production else "/api/openapi.json",
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Difesa CSRF in aggiunta ai cookie SameSite=Strict: le richieste che modificano dati
    # provenienti da un browser devono arrivare da un'origine autorizzata.
    if request.method in _UNSAFE:
        origin = request.headers.get("origin")
        if origin is not None and origin not in get_settings().allowed_origins:
            return JSONResponse({"detail": "Origine non autorizzata"}, status_code=403)

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}


for r in (
    auth.router,
    workspaces.router,
    stories.router,
    sources.router,
    transcripts.router,
    search.router,
):
    app.include_router(r, prefix="/api")
