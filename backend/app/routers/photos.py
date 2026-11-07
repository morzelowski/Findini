"""Zdjęcia: upload (z sugestią AI), odczyt z kontrolą uprawnień, wyszukiwanie zdjęciem."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from app import ratelimit
from app.config import get_settings
from app.db import get_db
from app.domain import categories as cats
from app.domain.matching import DISTINCT_MARGIN, SIM_RELATED, SIM_SIMILAR, QueryCtx, explain
from app.errors import ApiError, not_found
from app.models import Claim, Photo, Report
from app.security import Actor, current_actor, ip_key, optional_actor
from app.services import ai
from app.services import photos as svc
from app.services.reports import _cand, public_report

router = APIRouter(prefix="/v1", tags=["zdjęcia"])

AI_UNAVAILABLE = (
    "Analiza zdjęć jest chwilowo niedostępna. Możesz wyszukiwać filtrami i tekstem — wszystko inne działa normalnie."
)


def _read_limited(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_bytes
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise ApiError(413, "file_too_large", f"Zdjęcie jest za duże (maks. {limit // (1024 * 1024)} MB).")
    return data


@router.post("/photos", status_code=201)
def upload_photo(
    request: Request,
    file: UploadFile = File(...),
    purpose: Literal["report", "evidence"] = Form("report"),
    actor: Actor = Depends(current_actor),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    ratelimit.check(db, "photo_upload", actor.guest_id, ip_key(request))
    raw = _read_limited(file)
    return _store_photo(db, actor, raw, purpose)


def _store_photo(db: DbSession, actor: Actor, raw: bytes, purpose: str) -> dict[str, Any]:
    img = svc.process_upload(raw)
    full_key = svc.store(img.full, "")
    thumb_key = full_key.replace(".jpg", "_t.jpg")
    path_thumb = svc._path_for(thumb_key)
    path_thumb.write_bytes(img.thumb)
    p = Photo(
        id=uuid.uuid4(),
        owner_id=actor.guest_id,
        purpose=purpose,
        storage_key=full_key,
        thumb_key=thumb_key,
        width=img.width,
        height=img.height,
        bytes=len(img.full),
        sha256=img.sha256,
        embedding_status="pending" if purpose == "report" else "skipped",
    )
    suggestion = None
    ai_status = "skipped"
    if purpose == "report":
        eng = ai.engine()
        # Krótki limit czasu: sugestia ma pomóc, nie blokować formularza. Indeksowanie dokończy wątek w tle.
        emb = eng.embed(img.image, timeout_s=min(4.0, get_settings().ai_timeout_s))
        if emb is not None:
            p.embedding = emb.tolist()
            p.embedding_model = eng.model_version
            p.embedding_status = "ready"
            suggestion = eng.suggest(emb)
            p.ai_suggestion = suggestion
            ai_status = "ready"
        else:
            ai_status = "unavailable" if not eng.ready else "pending"
    db.add(p)
    db.commit()
    return {
        "id": str(p.id),
        "purpose": purpose,
        "width": p.width,
        "height": p.height,
        "url": f"/v1/photos/{p.id}",
        "thumb_url": f"/v1/photos/{p.id}?size=thumb",
        "ai_status": ai_status,
        "suggestion": suggestion,
        "notice": "Metadane (EXIF, GPS) zostały usunięte. Sprawdź, czy na zdjęciu nie widać dokumentów, adresów, "
        "twarzy ani danych kontaktowych.",
    }


def _can_view(db: DbSession, p: Photo, actor: Actor | None) -> tuple[bool, bool]:
    """(czy wolno, czy publiczne). Kontrola przy każdym pobraniu pliku."""
    if actor is not None and p.owner_id == actor.guest_id:
        return True, False
    if p.purpose == "report":
        if p.report_id is None:
            return False, False
        r = db.get(Report, p.report_id)
        if r is None or r.hidden_at is not None:
            return False, False
        if r.status in ("active", "reserved"):
            return True, True
        # Po zamknięciu: tylko uczestnicy spraw tej rzeczy.
        if actor is not None and db.scalar(
            select(Claim.id).where(Claim.report_id == r.id, Claim.claimant_id == actor.guest_id)
        ):
            return True, False
        return False, False
    # Dowód: autor (wyżej) lub znalazca w sprawie, do której jest dołączony.
    if p.claim_id is not None and actor is not None:
        c = db.get(Claim, p.claim_id)
        if c is not None and c.finder_id == actor.guest_id:
            return True, False
    return False, False


@router.get("/photos/{photo_id}")
def get_photo(
    photo_id: uuid.UUID,
    size: Literal["full", "thumb"] = "full",
    actor: Actor | None = Depends(optional_actor),
    db: DbSession = Depends(get_db),
) -> Response:
    p = db.get(Photo, photo_id)
    if p is None:
        raise not_found("Nie znaleziono zdjęcia.")
    ok, public = _can_view(db, p, actor)
    if not ok:
        raise not_found("Nie znaleziono zdjęcia.")
    try:
        data = svc.read(p.thumb_key if size == "thumb" else p.storage_key)
    except (OSError, ValueError) as e:
        raise not_found("Plik zdjęcia jest niedostępny.") from e
    headers = {
        "Cache-Control": "public, max-age=300" if public else "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
    }
    return Response(content=data, media_type="image/jpeg", headers=headers)


@router.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)) -> None:
    p = db.get(Photo, photo_id)
    if p is None or p.owner_id != actor.guest_id:
        raise not_found("Nie znaleziono zdjęcia.")
    if p.claim_id is not None:
        raise ApiError(409, "attached", "Zdjęcie jest dowodem w trwającej sprawie.")
    keys = (p.storage_key, p.thumb_key)
    db.delete(p)
    db.commit()
    svc.delete(keys[0])
    svc.delete(keys[1])


@router.post("/search/by-photo")
def search_by_photo(
    request: Request,
    file: UploadFile = File(...),
    kind: Literal["lost", "found"] = Form("found"),
    category: str | None = Form(None),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    radius_m: int | None = Form(None),
    actor: Actor = Depends(current_actor),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    """Zdjęcie zapytania jest analizowane w pamięci i NIE jest zapisywane."""
    ratelimit.check(db, "image_search", actor.guest_id, ip_key(request))
    raw = _read_limited(file)
    return _photo_search(db, actor, raw, kind, category, lat, lon, radius_m)


def _photo_search(
    db: DbSession,
    actor: Actor,
    raw: bytes,
    kind: str,
    category: str | None,
    lat: float | None,
    lon: float | None,
    radius_m: int | None,
) -> dict[str, Any]:
    img = svc.process_upload(raw)
    eng = ai.engine()
    emb = eng.embed(img.image)
    if emb is None:
        raise ApiError(503, "ai_unavailable", AI_UNAVAILABLE)
    if category:
        cats.validate_category(category)
    where = [
        "p.purpose = 'report'",
        "p.embedding_status = 'ready'",
        "p.embedding_model = :model",
        "r.status IN ('active','reserved')",
        "r.hidden_at IS NULL",
        "r.kind = :kind",
    ]
    params: dict[str, Any] = {"q": str(emb.tolist()), "model": eng.model_version, "kind": kind}
    if category:
        where.append("r.category = :category")
        params["category"] = category
    if lat is not None and lon is not None:
        where.append("ST_DWithin(r.public_geog, ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography, :rad)")
        params.update(lat=lat, lon=lon, rad=min(max(radius_m or 5000, 100), 25000))
    rows = db.execute(
        text(
            f"""
            SELECT r.id AS rid, max(1 - (p.embedding <=> CAST(:q AS vector))) AS sim
            FROM photos p JOIN reports r ON r.id = p.report_id
            WHERE {" AND ".join(where)}
            GROUP BY r.id ORDER BY sim DESC LIMIT 24
            """
        ),
        params,
    ).all()
    ranked = sorted(((row.rid, float(row.sim)) for row in rows), key=lambda t: -t[1])
    reps = {r.id: r for r in db.scalars(select(Report).where(Report.id.in_([r for r, _ in ranked]))).all()}
    suggestion = eng.suggest(emb)
    # Kolory ze zdjęcia zapytania (ocena modelu) służą tylko do OSTRZEŻENIA o niezgodności —
    # wysokie podobieństwo nie może ukryć, że rzecz ma inny kolor.
    q_colors = list((suggestion or {}).get("colors") or [])
    ctx = QueryCtx(
        category=category, colors=q_colors, lat=lat, lon=lon, radius_m=radius_m, category_is_filter=bool(category)
    )
    # „Wyróżniające się” = najlepszy wynik wyraźnie lepszy od drugiego (eksperyment: precyzja ok. 0,7).
    # Pojedynczy kandydat nie ma z czym się porównać — wtedy nie twierdzimy, że się wyróżnia.
    distinct = len(ranked) >= 2 and ranked[0][1] - ranked[1][1] >= DISTINCT_MARGIN and ranked[0][1] >= SIM_RELATED
    items = []
    for pos, (rid, sim) in enumerate(ranked):
        if sim < SIM_RELATED - 0.08:
            break  # wyraźnie inne rzeczy (najczęściej inna kategoria) — nie pokazujemy
        rep = reps[rid]
        cand = _cand(rep, image_sim=sim)
        cand.image_distinct = distinct and pos == 0
        ex = explain(ctx, cand)
        ex.reasons = [r for r in ex.reasons if not r.startswith(("Kolor:", "Zbliżony kolor"))]
        ex.warnings = [
            w.replace("Inny kolor (", "Inny kolor niż na Twoim zdjęciu — ocena modelu (") for w in ex.warnings
        ]
        level = "distinct" if cand.image_distinct else "similar" if sim >= SIM_SIMILAR else "related"
        items.append(
            public_report(
                rep,
                actor=actor,
                distance_m=ex.distance_m,
                match={"visual": level, "reasons": ex.reasons, "warnings": ex.warnings},
            )
        )
    db.commit()
    return {
        "items": items[:12],
        "no_convincing_match": not distinct,
        "query_suggestion": suggestion,
        "model": eng.model_version,
        "notice": (
            "Jedno zgłoszenie wyraźnie wyróżnia się podobieństwem — sprawdź szczegóły, miejsce i czas."
            if distinct
            else "Żadne zdjęcie nie wyróżnia się wyraźnie. Poniżej rzeczy wizualnie najbardziej podobne — "
            "wiele przedmiotów wygląda podobnie, więc porównaj cechy, miejsce i czas."
        )
        + " Zdjęcie zapytania nie zostało zapisane. Własność potwierdza znalazca po Twoim opisie szczegółów.",
    }
