"""Roszczenia, decyzje, przekazanie, podziękowania i prywatna rozmowa."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session as DbSession

from app import ratelimit
from app.db import get_db
from app.schemas import ClaimCreate, DecisionIn, HandoverIn, MessageIn, ReadIn, iso
from app.security import Actor, current_actor, ip_key
from app.services import claims as svc

router = APIRouter(prefix="/v1", tags=["roszczenia"])


def _out(db: DbSession, claim_id: uuid.UUID, actor: Actor) -> dict[str, Any]:
    claim, role = svc.load_claim(db, claim_id, actor)
    return svc.serialize_claim(db, claim, role, actor)


@router.post("/reports/{report_id}/claims", status_code=201)
def create_claim(
    report_id: uuid.UUID,
    body: ClaimCreate,
    request: Request,
    actor: Actor = Depends(current_actor),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    ratelimit.check(db, "claim_create", actor.guest_id, ip_key(request))
    claim = svc.create_claim(db, actor, report_id, body)
    return _out(db, claim.id, actor)


@router.get("/claims/{claim_id}")
def get_claim(
    claim_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    return _out(db, claim_id, actor)


@router.post("/claims/{claim_id}/accept")
def accept(
    claim_id: uuid.UUID,
    body: DecisionIn | None = None,
    actor: Actor = Depends(current_actor),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    svc.accept(db, actor, claim_id, body.note if body else None)
    return _out(db, claim_id, actor)


@router.post("/claims/{claim_id}/reject")
def reject(
    claim_id: uuid.UUID,
    body: DecisionIn | None = None,
    actor: Actor = Depends(current_actor),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    svc.reject(db, actor, claim_id, body.note if body else None)
    return _out(db, claim_id, actor)


@router.post("/claims/{claim_id}/withdraw")
def withdraw(
    claim_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    svc.withdraw(db, actor, claim_id)
    return _out(db, claim_id, actor)


@router.post("/claims/{claim_id}/handover")
def handover(
    claim_id: uuid.UUID, body: HandoverIn, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    if body.code:
        ratelimit.check(db, "handover_code", actor.guest_id, None)
    svc.handover(db, actor, claim_id, body.code)
    return _out(db, claim_id, actor)


@router.post("/claims/{claim_id}/confirm-received")
def confirm_received(
    claim_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    svc.confirm_received(db, actor, claim_id)
    return _out(db, claim_id, actor)


@router.post("/claims/{claim_id}/thanks")
def thanks(
    claim_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    svc.thank(db, actor, claim_id)
    return _out(db, claim_id, actor)


@router.post("/claims/{claim_id}/block")
def block(
    claim_id: uuid.UUID, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    svc.block(db, actor, claim_id)
    return _out(db, claim_id, actor)


@router.get("/claims/{claim_id}/messages")
def messages(
    claim_id: uuid.UUID,
    after_id: int = Query(default=0, ge=0),
    actor: Actor = Depends(current_actor),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    return svc.list_messages(db, actor, claim_id, after_id)


@router.post("/claims/{claim_id}/messages", status_code=201)
def post_message(
    claim_id: uuid.UUID,
    body: MessageIn,
    request: Request,
    actor: Actor = Depends(current_actor),
    db: DbSession = Depends(get_db),
) -> dict[str, Any]:
    ratelimit.check(db, "message", actor.guest_id, ip_key(request))
    m = svc.post_message(db, actor, claim_id, body.body)
    return {"id": m.id, "kind": m.kind, "mine": True, "body": m.body, "created_at": iso(m.created_at)}


@router.post("/claims/{claim_id}/read", status_code=204)
def read(
    claim_id: uuid.UUID, body: ReadIn, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> None:
    svc.mark_read(db, actor, claim_id, body.last_read_id)
