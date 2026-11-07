"""Zgłoszenia: publiczne wyszukiwanie (bez sesji) i zarządzanie własnymi zgłoszeniami."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app import ratelimit
from app.db import get_db
from app.errors import ApiError, invalid
from app.models import AuditEvent, Photo, Report
from app.schemas import ReportCreate, ReportUpdate, ResolveIn
from app.security import Actor, current_actor, ip_key, now_utc, optional_actor
from app.services import claims as claim_svc
from app.services import photos as photo_svc
from app.services import reports as svc

router = APIRouter(prefix="/v1", tags=["zgłoszenia"])


def _bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    try:
        parts = [float(x) for x in raw.split(",")]
    except ValueError as e:
        raise invalid("bad_bbox", "Nieprawidłowy obszar mapy.") from e
    if len(parts) != 4 or parts[0] >= parts[2] or parts[1] >= parts[3]:
        raise invalid("bad_bbox", "Nieprawidłowy obszar mapy.")
    return parts[0], parts[1], parts[2], parts[3]


def _dt(raw: str | None, name: str) -> datetime | None:
    if not raw:
        return None
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as e:
        raise invalid("bad_date", f"Nieprawidłowa data: {name}.") from e
    if d.tzinfo is None:
        raise invalid("bad_date", "Data musi zawierać strefę czasową.")
    return d


@router.get("/reports")
def search_reports(
    request: Request,
    kind: Literal["lost", "found"] | None = None,
    category: str | None = Query(default=None, max_length=32),
    subtype: str | None = Query(default=None, max_length=40),
    colors: str | None = Query(default=None, max_length=100, description="lista po przecinku"),
    brand: str | None = Query(default=None, max_length=40),
    q: str | None = Query(default=None, max_length=120),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
    radius_m: int | None = Query(default=None, ge=100, le=25000),
    bbox: str | None = Query(default=None, max_length=120),
    date_from: str | None = None,
    date_to: str | None = None,
    sort: Literal["relevance", "newest", "nearest"] = "relevance",
    cursor: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=20, ge=1, le=50),
    actor: Actor | None = Depends(optional_actor),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    ratelimit.check(db, "search", None, ip_key(request))
    if (lat is None) != (lon is None):
        raise invalid("bad_location", "Podaj obie współrzędne.")
    d_from, d_to = _dt(date_from, "od"), _dt(date_to, "do")
    if d_from and d_to and (d_to - d_from).days > 366:
        raise invalid("bad_date", "Zakres dat może obejmować maksymalnie rok.")
    color_list = [c for c in (colors or "").split(",") if c]
    res = svc.search(
        db,
        actor=actor,
        kind=kind,
        category=category,
        subtype=subtype,
        colors=color_list,
        brand=brand,
        q=q,
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        bbox=_bbox(bbox),
        date_from=d_from,
        date_to=d_to,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )
    if not res["items"] and not cursor:
        res["suggestions"] = svc.suggestions_for_empty(
            radius_m or (3000 if lat is not None else None),
            bool(d_from or d_to),
            bool(color_list or brand or subtype or category),
        )
    return res


@router.get("/reports/areas")
def report_areas(
    bbox: str = Query(max_length=120),
    kind: Literal["lost", "found"] | None = None,
    category: str | None = Query(default=None, max_length=32),
    date_from: str | None = None,
    date_to: str | None = None,
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    box = _bbox(bbox)
    assert box is not None
    return {
        "areas": svc.map_areas(
            db, bbox=box, kind=kind, category=category, date_from=_dt(date_from, "od"), date_to=_dt(date_to, "do")
        ),
        "note": "Kółka pokazują przybliżone obszary (siatka ok. 500 m), nie dokładne miejsca.",
    }


@router.get("/reports/{report_id}")
def get_report(
    report_id: uuid.UUID, actor: Actor | None = Depends(optional_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    r = db.get(Report, report_id)
    if r is not None and actor is not None and r.owner_id == actor.guest_id and r.status != "withdrawn":
        return svc.owner_report(db, r, actor)
    r = svc.visible_report(db, report_id)
    return svc.public_report(r, actor=actor)


@router.post("/reports", status_code=201)
def create_report(
    body: ReportCreate, request: Request, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    ratelimit.check(db, "report_create", actor.guest_id, ip_key(request))
    r = svc.create_report(db, actor, body)
    return svc.owner_report(db, r, actor)


@router.patch("/reports/{report_id}")
def update_report(
    report_id: uuid.UUID, body: ReportUpdate, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    ratelimit.check(db, "report_edit", actor.guest_id, None)
    r = svc.update_report(db, actor, report_id, body)
    return svc.owner_report(db, r, actor)


@router.delete("/reports/{report_id}", status_code=204)
def withdraw_report(
    report_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> None:
    r = svc.load_owned(db, report_id, actor, for_update=True)
    if r.status == "withdrawn":
        return
    prev = r.status
    now = now_utc()
    claim_svc.close_open_claims_for_report(db, r.id, "report_withdrawn", actor)
    r.status = "withdrawn"
    r.withdrawn_at = now
    r.updated_at = now
    # Usuń zdjęcia publiczne od razu (pliki + wektory); dane rekordu usuwa retencja.
    files = db.scalars(select(Photo).where(Photo.report_id == r.id, Photo.purpose == "report")).all()
    keys = [(p.storage_key, p.thumb_key) for p in files]
    for p in files:
        db.delete(p)
    db.add(
        AuditEvent(
            actor_id=actor.guest_id,
            entity="report",
            entity_id=r.id,
            action="withdraw",
            from_status=prev,
            to_status="withdrawn",
        )
    )
    db.commit()
    for full, thumb in keys:
        photo_svc.delete(full)
        photo_svc.delete(thumb)


@router.post("/reports/{report_id}/resolve")
def resolve_report(
    report_id: uuid.UUID, body: ResolveIn, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    """Zamknięcie poza procesem roszczeń: „odnalazłem” (zguba) lub „oddane do biura / zwrócone poza aplikacją”."""
    r = svc.load_owned(db, report_id, actor, for_update=True)
    if r.status == "resolved":
        return svc.owner_report(db, r, actor)
    if r.status not in ("active", "reserved", "expired"):
        raise ApiError(409, "invalid_state", "Tego zgłoszenia nie można już zamknąć.")
    if r.status == "reserved":
        raise ApiError(409, "item_reserved", "Trwa przekazanie w ramach roszczenia — zakończ je w rozmowie.")
    claim_svc.close_open_claims_for_report(db, r.id, "resolved_outside", actor)
    prev = r.status
    r.status = "resolved"
    r.resolved_at = now_utc()
    r.updated_at = r.resolved_at
    db.add(
        AuditEvent(
            actor_id=actor.guest_id,
            entity="report",
            entity_id=r.id,
            action=f"resolve:{body.note}",
            from_status=prev,
            to_status="resolved",
        )
    )
    db.commit()
    return svc.owner_report(db, r, actor)


@router.post("/reports/{report_id}/renew")
def renew_report(
    report_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    from datetime import timedelta

    from app.config import get_settings

    r = svc.load_owned(db, report_id, actor, for_update=True)
    if r.status not in ("expired", "active"):
        raise ApiError(409, "invalid_state", "Można odnowić tylko aktywne lub wygasłe zgłoszenie.")
    if r.hidden_at is not None:
        raise ApiError(409, "hidden", "Zgłoszenie ukryte przez moderację.")
    r.status = "active"
    r.expires_at = now_utc() + timedelta(days=get_settings().report_active_days)
    r.updated_at = now_utc()
    db.commit()
    return svc.owner_report(db, r, actor)


@router.get("/reports/{report_id}/matches")
def report_matches(
    report_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    return svc.matches_for(db, actor, report_id)


@router.get("/reports/{report_id}/claims")
def report_claims(
    report_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    from app.models import Claim

    r = svc.load_owned(db, report_id, actor)
    rows = db.scalars(select(Claim).where(Claim.report_id == r.id).order_by(Claim.created_at)).all()
    return {"items": [claim_svc.serialize_claim(db, c, "finder", actor) for c in rows]}


@router.get("/reports/{report_id}/claim-form")
def claim_form(
    report_id: uuid.UUID, request: Request, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    ratelimit.check(db, "claim_question", actor.guest_id, ip_key(request))
    return claim_svc.claim_form(db, actor, report_id)
