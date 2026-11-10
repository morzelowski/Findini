"""Sesje gościa, odzyskiwanie dostępu i dane „Moje”."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import false, func, or_, select, update
from sqlalchemy.orm import Session as DbSession

from app import ratelimit
from app.db import get_db
from app.errors import ApiError
from app.models import Claim, Guest, Photo, Report, Session, Thanks
from app.schemas import RecoverIn, iso
from app.security import (
    Actor,
    current_actor,
    hash_recovery_code,
    hash_token,
    ip_key,
    new_recovery_code,
    new_token,
    now_utc,
    random_alias,
    valid_recovery_code,
)
from app.services import claims as claim_svc
from app.services import photos as photo_svc
from app.services.reports import owner_report

router = APIRouter(prefix="/v1", tags=["sesje"])

SESSION_NOTICE = (
    "Findini nie wymaga konta. Twoje zgłoszenia są przypisane do tej anonimowej sesji na tym telefonie. "
    "Jeśli usuniesz aplikację lub zgubisz telefon, stracisz do nich dostęp — chyba że zapiszesz kod odzyskiwania."
)


def _issue(db: DbSession, guest: Guest) -> dict[str, Any]:
    token = new_token()
    db.add(Session(id=uuid.uuid4(), guest_id=guest.id, token_hash=hash_token(token)))
    db.commit()
    return {"token": token, "guest": {"id": str(guest.id), "alias": guest.alias}, "notice": SESSION_NOTICE}


@router.post("/sessions", status_code=201)
def create_session(request: Request, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    ratelimit.check(db, "session_create", None, ip_key(request))
    guest = Guest(id=uuid.uuid4(), alias=random_alias())
    db.add(guest)
    db.flush()
    return _issue(db, guest)


@router.post("/sessions/recover", status_code=201)
def recover(body: RecoverIn, request: Request, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    ratelimit.check(db, "recover", None, ip_key(request))
    if not valid_recovery_code(body.code):
        raise ApiError(404, "bad_recovery_code", "Nieprawidłowy kod odzyskiwania. Sprawdź wszystkie grupy znaków.")
    guest = db.scalar(select(Guest).where(Guest.recovery_hash == hash_recovery_code(body.code)).with_for_update())
    if guest is None or guest.deleted_at is not None:
        raise ApiError(404, "bad_recovery_code", "Nieprawidłowy kod odzyskiwania.")
    if guest.banned_at is not None:
        raise ApiError(403, "banned", "Ta sesja została zablokowana przez moderację.")
    # Utracony telefon: unieważniamy stare sesje i jednorazowy kod; wydajemy nowy kod.
    db.execute(
        update(Session).where(Session.guest_id == guest.id, Session.revoked_at.is_(None)).values(revoked_at=now_utc())
    )
    code = new_recovery_code()
    guest.recovery_hash = hash_recovery_code(code)
    guest.recovery_created_at = now_utc()
    out = _issue(db, guest)
    out["new_recovery_code"] = code
    return out


@router.delete("/sessions/current", status_code=204)
def logout(actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)) -> None:
    db.execute(update(Session).where(Session.id == actor.session_id).values(revoked_at=now_utc()))
    db.commit()


@router.get("/me")
def me(actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)) -> dict[str, Any]:
    g = db.get(Guest, actor.guest_id)
    assert g is not None
    hearts = db.scalar(select(func.count()).select_from(Thanks).where(Thanks.to_id == g.id)) or 0
    active = (
        db.scalar(
            select(func.count())
            .select_from(Report)
            .where(Report.owner_id == g.id, Report.status.in_(["active", "reserved"]))
        )
        or 0
    )
    returned = (
        db.scalar(select(func.count()).select_from(Claim).where(Claim.finder_id == g.id, Claim.status == "returned"))
        or 0
    )
    return {
        "guest": {"id": str(g.id), "alias": g.alias, "created_at": iso(g.created_at)},
        "has_recovery_code": g.recovery_hash is not None,
        "recovery_created_at": iso(g.recovery_created_at),
        "stats": {"active_reports": active, "hearts_received": hearts, "items_returned": returned},
        "unread": claim_svc.unread_total(db, g.id),
        "notice": SESSION_NOTICE,
    }


@router.post("/me/recovery-code", status_code=201)
def make_recovery_code(actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)) -> dict[str, Any]:
    g = db.get(Guest, actor.guest_id)
    assert g is not None
    code = new_recovery_code()
    g.recovery_hash = hash_recovery_code(code)
    g.recovery_created_at = now_utc()
    db.commit()
    return {
        "code": code,
        "notice": "Zapisz ten kod w bezpiecznym miejscu. Pokazujemy go tylko raz — serwer przechowuje wyłącznie jego "
        "skrót. Kod pozwala przenieść Twoje zgłoszenia i rozmowy na nowy telefon. Wygenerowanie nowego kodu "
        "unieważnia poprzedni.",
    }


@router.get("/me/reports")
def my_reports(actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)) -> dict[str, Any]:
    reps = db.scalars(
        select(Report)
        .where(Report.owner_id == actor.guest_id, Report.status != "withdrawn")
        .order_by(Report.created_at.desc())
        .limit(100)
    ).all()
    return {"items": [owner_report(db, r, actor) for r in reps]}


@router.get("/me/cases")
def my_cases(actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)) -> dict[str, Any]:
    """Sprawy (roszczenia) w obu rolach: jako znalazca i jako osoba odbierająca."""
    rows = db.scalars(
        select(Claim)
        .where((Claim.finder_id == actor.guest_id) | (Claim.claimant_id == actor.guest_id))
        .order_by(Claim.updated_at.desc())
        .limit(100)
    ).all()
    out = []
    for c in rows:
        role = "finder" if c.finder_id == actor.guest_id else "claimant"
        out.append(claim_svc.serialize_claim(db, c, role, actor))
    return {"items": out}


@router.get("/me/updates")
def updates(
    since: str | None = None, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    """Lekki endpoint dla okresowego sprawdzania (WorkManager) — liczniki, bez treści prywatnych."""
    from datetime import datetime

    from app.services.reports import matches_for

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            since_dt = None
    new_matches = 0
    reps = db.scalars(
        select(Report).where(Report.owner_id == actor.guest_id, Report.status == "active").limit(10)
    ).all()
    for r in reps:
        m = matches_for(db, actor, r.id)
        for item in m["strong"] + m["possible"]:
            if since_dt is None or (item["published_at"] and datetime.fromisoformat(item["published_at"]) > since_dt):
                new_matches += 1
    changed = 0
    if since_dt:
        changed = (
            db.scalar(
                select(func.count())
                .select_from(Claim)
                .where((Claim.finder_id == actor.guest_id) | (Claim.claimant_id == actor.guest_id))
                .where(Claim.updated_at > since_dt)
            )
            or 0
        )
    return {
        "unread_cases": claim_svc.unread_total(db, actor.guest_id),
        "new_matches": new_matches,
        "changed_cases": changed,
        "server_time": iso(now_utc()),
    }


@router.delete("/me", status_code=204)
def delete_me(actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)) -> None:
    """Usuwa wszystkie dane gościa: zgłoszenia, zdjęcia (pliki), roszczenia, wiadomości, sesje."""
    g = db.get(Guest, actor.guest_id)
    assert g is not None
    my_reports = db.scalars(select(Report.id).where(Report.owner_id == g.id)).all()
    # Moje zaakceptowane roszczenia do cudzych rzeczy: zwolnij rezerwację przedmiotu.
    for c in db.scalars(select(Claim).where(Claim.claimant_id == g.id, Claim.status == "accepted")).all():
        db.execute(update(Report).where(Report.id == c.report_id, Report.status == "reserved").values(status="active"))
    files = db.scalars(
        select(Photo).where(or_(Photo.owner_id == g.id, Photo.report_id.in_(my_reports) if my_reports else false()))
    ).all()
    keys = [(p.storage_key, p.thumb_key) for p in files]
    db.delete(g)  # kaskada w bazie
    db.commit()
    for full, thumb in keys:
        photo_svc.delete(full)
        photo_svc.delete(thumb)
