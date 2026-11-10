"""Aplikacja FastAPI — Findini."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import get_settings
from app.errors import ApiError
from app.routers import claims, misc, photos, reports, sessions
from app.services import ai, jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("findini.http")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    # Model ładujemy w tle — API odpowiada od razu, AI dołącza, gdy będzie gotowe.
    threading.Thread(target=ai.engine().load, name="ai-load", daemon=True).start()
    if s.background_jobs:
        jobs.start()
    yield
    jobs.stop()


app = FastAPI(
    title="Findini API",
    version=__version__,
    description="API aplikacji Findini — zgłaszanie znalezionych przedmiotów i odnajdywanie zgub w całej Polsce.",
    lifespan=lifespan,
)


@app.middleware("http")
async def access_log(request: Request, call_next):  # type: ignore[no-untyped-def]
    rid = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("rid=%s %s %s -> 500", rid, request.method, request.url.path)
        raise
    ms = (time.perf_counter() - t0) * 1000
    # Logujemy tylko metodę, szablon ścieżki i czas — bez nagłówków, tokenów, zapytań i treści.
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    log.info("rid=%s %s %s -> %s %.0fms", rid, request.method, path, response.status_code, ms)
    response.headers["X-Request-Id"] = rid
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.exception_handler(ApiError)
async def api_error(_req: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse({"error": {"code": exc.code, "message": exc.message, **exc.extra}}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_req: Request, exc: RequestValidationError) -> JSONResponse:
    fields = []
    for e in exc.errors()[:10]:
        loc = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query"))
        fields.append({"field": loc, "problem": e.get("msg", "")})
    return JSONResponse(
        {"error": {"code": "validation_error", "message": "Sprawdź poprawność formularza.", "fields": fields}},
        status_code=422,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
    msg = {404: "Nie znaleziono.", 405: "Niedozwolona metoda.", 413: "Za duże żądanie."}.get(exc.status_code, "Błąd.")
    return JSONResponse({"error": {"code": f"http_{exc.status_code}", "message": msg}}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled(_req: Request, exc: Exception) -> JSONResponse:
    log.error("Nieobsłużony błąd: %s", type(exc).__name__)
    return JSONResponse(
        {"error": {"code": "server_error", "message": "Wystąpił błąd serwera. Spróbuj ponownie za chwilę."}},
        status_code=500,
    )


app.include_router(sessions.router)
app.include_router(reports.router)
app.include_router(photos.router)
app.include_router(claims.router)
app.include_router(misc.router)
