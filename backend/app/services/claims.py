"""Roszczenia, decyzje znalazcy, przekazanie i zamknięcie sprawy.

Każda zmiana stanu odbywa się w jednej transakcji z blokadą wiersza zgłoszenia
(SELECT ... FOR UPDATE), więc równoległe akceptacje/finalizacje są serializowane.
Dodatkowo unikalny indeks częściowy `uq_claims_single_release` uniemożliwia istnienie
dwóch zaakceptowanych/zwróconych roszczeń dla jednej rzeczy — nawet przy błędzie w kodzie.
Operacje są idempotentne: powtórzenie tego samego żądania zwraca bieżący stan.
"""

from __future__ import annotations

import hmac
import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.domain.states import OPEN_CLAIM_STATES, claim_is_returned, require_claim_transition
from app.errors import ApiError, conflict, forbidden, invalid, not_found
from app.models import AuditEvent, Block, Claim, ClaimRead, Message, Photo, Report, Thanks
from app.schemas import ClaimCreate, clean_text, iso
from app.security import Actor, new_handover_code, now_utc
from app.services.reports import photo_ref, public_report

MAX_OPEN_CLAIMS_PER_REPORT = 20
MAX_HANDOVER_ATTEMPTS = 5
GENERIC_QUESTION = (
    "Opisz szczegół, którego nie widać na zdjęciu ani w opisie (np. zawartość, uszkodzenie, naklejka, grawer)."
)

SAFETY_TIPS = [
    "Umawiajcie się w ruchliwym, publicznym miejscu (np. hol dworca, portiernia uczelni, kawiarnia) i w ciągu dnia.",
    "Nie podawaj adresu domowego. Nie wysyłaj zdjęć dokumentów.",
    "Findini nigdy nie wymaga opłat, przelewów „weryfikacyjnych” ani kodów BLIK — to oznaka oszustwa.",
    "Kod przekazania pokazuje osoba odbierająca dopiero przy spotkaniu, po obejrzeniu przedmiotu.",
    "Możesz w każdej chwili zablokować kontakt i zgłosić nadużycie.",
]

STATUS_PL = {
    "pending": "Oczekuje na decyzję znalazcy",
    "accepted": "Zaakceptowane — umówcie przekazanie",
    "rejected": "Odrzucone przez znalazcę",
    "withdrawn": "Wycofane",
    "returned": "Przedmiot zwrócony",
    "closed": "Zamknięte",
}
CLOSE_REASON_PL = {
    "other_returned": "Przedmiot został wydany innej osobie.",
    "report_withdrawn": "Znalazca usunął zgłoszenie.",
    "report_hidden": "Zgłoszenie zostało ukryte przez moderację.",
    "blocked": "Kontakt został zablokowany.",
    "resolved_outside": "Sprawa została zamknięta przez znalazcę.",
    "account_deleted": "Uczestnik usunął swoje dane.",
}


def _audit(db: DbSession, actor_id: Any, entity_id: Any, action: str, a: str | None, b: str | None) -> None:
    db.add(
        AuditEvent(actor_id=actor_id, entity="claim", entity_id=entity_id, action=action, from_status=a, to_status=b)
    )


def _system(db: DbSession, claim_id: uuid.UUID, body: str) -> None:
    db.add(Message(claim_id=claim_id, sender_id=None, kind="system", body=body))


def is_blocked(db: DbSession, a: Any, b: Any) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(Block)
            .where(
                ((Block.blocker_id == a) & (Block.blocked_id == b))
                | ((Block.blocker_id == b) & (Block.blocked_id == a))
            )
        )
        or 0
    ) > 0


def claim_form(db: DbSession, actor: Actor, report_id: uuid.UUID) -> dict[str, Any]:
    r = db.get(Report, report_id)
    if r is None or r.hidden_at is not None or r.status not in ("active", "reserved") or r.kind != "found":
        raise not_found("Nie można złożyć roszczenia do tego zgłoszenia.")
    existing = db.scalar(select(Claim).where(Claim.report_id == r.id, Claim.claimant_id == actor.guest_id))
    reason = None
    if r.owner_id == actor.guest_id:
        reason = "To Twoje zgłoszenie."
    elif existing is not None:
        reason = "Już złożyłeś(-aś) roszczenie do tej rzeczy."
    elif is_blocked(db, r.owner_id, actor.guest_id):
        reason = "Kontakt z tą osobą jest zablokowany."
    return {
        "report_id": str(r.id),
        "question": r.private.claim_question or GENERIC_QUESTION,
        "custom_question": r.private.claim_question is not None,
        "can_claim": reason is None,
        "reason": reason,
        "existing_claim_id": str(existing.id) if existing else None,
        "notice": (
            "Twoja odpowiedź i dowody trafią wyłącznie do znalazcy. Nie dowiesz się automatycznie, czy odpowiedź "
            "jest „poprawna” — decyzję podejmuje człowiek. Masz jedno roszczenie do tej rzeczy."
        ),
    }


def create_claim(db: DbSession, actor: Actor, report_id: uuid.UUID, body: ClaimCreate) -> Claim:
    r = db.scalar(select(Report).where(Report.id == report_id).with_for_update(of=Report))
    if r is None or r.hidden_at is not None or r.status not in ("active", "reserved"):
        raise not_found("Nie można złożyć roszczenia do tego zgłoszenia.")
    if r.kind != "found":
        raise invalid("not_found_item", "Roszczenie można złożyć tylko do rzeczy znalezionej.")
    if r.owner_id == actor.guest_id:
        raise forbidden("Nie możesz złożyć roszczenia do własnego zgłoszenia.")
    if is_blocked(db, r.owner_id, actor.guest_id):
        raise forbidden("Kontakt z tą osobą jest zablokowany.")
    open_count = db.scalar(
        select(func.count()).select_from(Claim).where(Claim.report_id == r.id, Claim.status.in_(OPEN_CLAIM_STATES))
    )
    if (open_count or 0) >= MAX_OPEN_CLAIMS_PER_REPORT:
        raise conflict("too_many_claims", "Do tej rzeczy złożono już wiele roszczeń. Spróbuj później.")
    answer = clean_text(body.answer, 500, multiline=True)
    proof = clean_text(body.proof_details, 1000, multiline=True)
    if len(answer) < 3:
        raise invalid("answer_too_short", "Odpowiedź jest za krótka.")
    lost_id = None
    if body.lost_report_id:
        lost = db.get(Report, body.lost_report_id)
        if lost is None or lost.owner_id != actor.guest_id or lost.kind != "lost":
            raise invalid("bad_lost_report", "Możesz powiązać tylko własne zgłoszenie zguby.")
        lost_id = lost.id
    claim = Claim(
        id=uuid.uuid4(),
        report_id=r.id,
        claimant_id=actor.guest_id,
        finder_id=r.owner_id,
        status="pending",
        answer=answer,
        proof_details=proof,
        lost_report_id=lost_id,
    )
    db.add(claim)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise conflict("already_claimed", "Już złożyłeś(-aś) roszczenie do tej rzeczy.") from e
    if body.evidence_photo_ids:
        photos = db.scalars(select(Photo).where(Photo.id.in_(body.evidence_photo_ids))).all()
        if len(photos) != len(set(body.evidence_photo_ids)):
            raise invalid("bad_photos", "Nieprawidłowe zdjęcie dowodu.")
        for i, p in enumerate(photos):
            if p.owner_id != actor.guest_id or p.purpose != "evidence" or p.claim_id is not None:
                raise invalid("bad_photos", "Nieprawidłowe zdjęcie dowodu.")
            p.claim_id = claim.id
            p.position = i
    _system(db, claim.id, "Złożono roszczenie. Znalazca zobaczy odpowiedź i zdecyduje, czy przedmiot pasuje.")
    _audit(db, actor.guest_id, claim.id, "create", None, "pending")
    db.commit()
    return claim


def load_claim(db: DbSession, claim_id: uuid.UUID, actor: Actor, *, lock: bool = False) -> tuple[Claim, str]:
    """Zwraca (roszczenie, rola). Nieuprawniony = 404 (nie ujawniamy istnienia)."""
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise not_found("Nie znaleziono sprawy.")
    if actor.guest_id == claim.finder_id:
        role = "finder"
    elif actor.guest_id == claim.claimant_id:
        role = "claimant"
    else:
        raise not_found("Nie znaleziono sprawy.")
    if lock:
        # Blokada zgłoszenia, a potem roszczenia — zawsze w tej samej kolejności (bez zakleszczeń).
        # populate_existing: po uzyskaniu blokady czytamy świeży stan, nie kopię sprzed oczekiwania.
        db.scalars(
            select(Report)
            .where(Report.id == claim.report_id)
            .with_for_update(of=Report)
            .execution_options(populate_existing=True)
        ).one()
        db.scalars(
            select(Claim)
            .where(Claim.id == claim.id)
            .with_for_update(of=Claim)
            .execution_options(populate_existing=True)
        ).one()
    return claim, role


def serialize_claim(db: DbSession, claim: Claim, role: str, actor: Actor) -> dict[str, Any]:
    r: Report = claim.report
    evidence = db.scalars(
        select(Photo).where(Photo.claim_id == claim.id, Photo.purpose == "evidence").order_by(Photo.position)
    ).all()
    last_msg = db.scalar(select(func.max(Message.id)).where(Message.claim_id == claim.id)) or 0
    read = db.get(ClaimRead, (claim.id, actor.guest_id))
    thanked = db.scalar(select(func.count()).select_from(Thanks).where(Thanks.claim_id == claim.id)) or 0
    blocked = is_blocked(db, claim.finder_id, claim.claimant_id)
    out: dict[str, Any] = {
        "id": str(claim.id),
        "role": role,
        "status": claim.status,
        "status_label": STATUS_PL.get(claim.status, claim.status),
        "close_reason": CLOSE_REASON_PL.get(claim.close_reason or ""),
        "report": public_report(r, actor=actor) | {"status": r.status},
        "answer": claim.answer,
        "proof_details": claim.proof_details,
        "evidence_photos": [photo_ref(p) for p in evidence],
        "finder_note": claim.finder_note,
        "finder_confirmed": claim.finder_confirmed_at is not None,
        "owner_confirmed": claim.owner_confirmed_at is not None,
        "created_at": iso(claim.created_at),
        "accepted_at": iso(claim.accepted_at),
        "returned_at": iso(claim.returned_at),
        "thanked": thanked > 0,
        "blocked": blocked,
        "unread": max(0, last_msg - (read.last_read_id if read else 0)),
        "last_message_id": last_msg,
        "safety_tips": SAFETY_TIPS,
        "can_message": claim.status in ("pending", "accepted", "returned") and not blocked,
    }
    if role == "finder":
        # Tylko znalazca widzi swoją ukrytą cechę obok odpowiedzi — do porównania.
        out["question"] = r.private.claim_question or GENERIC_QUESTION
        out["secret_details"] = r.private.secret_details
        out["handover_attempts_left"] = max(0, MAX_HANDOVER_ATTEMPTS - claim.handover_attempts)
        out["handover_code_length"] = len(claim.handover_code) if claim.handover_code else 8
        out["counterpart_alias"] = "Osoba zgłaszająca roszczenie"
    else:
        out["question"] = r.private.claim_question or GENERIC_QUESTION
        out["handover_code"] = claim.handover_code if claim.status == "accepted" else None
        out["counterpart_alias"] = "Znalazca"
    return out


def _finalize_if_complete(db: DbSession, claim: Claim, actor: Actor) -> None:
    if not claim_is_returned(claim.finder_confirmed_at is not None, claim.owner_confirmed_at is not None):
        return
    require_claim_transition(claim.status, "returned")
    now = now_utc()
    claim.status = "returned"
    claim.returned_at = now
    claim.updated_at = now
    r = db.get(Report, claim.report_id)
    assert r is not None
    prev = r.status
    r.status = "resolved"
    r.resolved_at = now
    r.updated_at = now
    db.add(
        AuditEvent(
            actor_id=actor.guest_id,
            entity="report",
            entity_id=r.id,
            action="returned",
            from_status=prev,
            to_status="resolved",
        )
    )
    _audit(db, actor.guest_id, claim.id, "returned", "accepted", "returned")
    _system(db, claim.id, "Zwrot potwierdzony przez obie strony. Sprawa zakończona — dziękujemy!")
    others = db.scalars(
        select(Claim).where(Claim.report_id == r.id, Claim.id != claim.id, Claim.status.in_(OPEN_CLAIM_STATES))
    ).all()
    for o in others:
        _close(db, o, "other_returned", actor)
    if claim.lost_report_id:
        lost = db.get(Report, claim.lost_report_id)
        if lost is not None and lost.owner_id == claim.claimant_id and lost.status in ("active", "expired"):
            lost.status = "resolved"
            lost.resolved_at = now
            lost.updated_at = now


def _close(db: DbSession, c: Claim, reason: str, actor: Actor | None) -> None:
    prev = c.status
    c.status = "closed"
    c.close_reason = reason
    c.closed_at = now_utc()
    c.updated_at = c.closed_at
    _audit(db, actor.guest_id if actor else None, c.id, f"close:{reason}", prev, "closed")
    _system(db, c.id, CLOSE_REASON_PL.get(reason, "Sprawa zamknięta."))


def close_open_claims_for_report(db: DbSession, report_id: uuid.UUID, reason: str, actor: Actor | None) -> None:
    for c in db.scalars(select(Claim).where(Claim.report_id == report_id, Claim.status.in_(OPEN_CLAIM_STATES))).all():
        _close(db, c, reason, actor)


def accept(db: DbSession, actor: Actor, claim_id: uuid.UUID, note: str | None) -> Claim:
    claim, role = load_claim(db, claim_id, actor, lock=True)
    if role != "finder":
        raise forbidden("Tylko znalazca decyduje o wydaniu przedmiotu.")
    if claim.status == "accepted":
        db.commit()
        return claim  # idempotentnie
    r = db.get(Report, claim.report_id)
    assert r is not None
    if r.hidden_at is not None:
        raise forbidden("Zgłoszenie zostało ukryte przez moderację.")
    if r.status != "active":
        raise conflict(
            "item_reserved",
            "Inne roszczenie jest już zaakceptowane albo sprawa jest zamknięta. Najpierw cofnij poprzednią akceptację.",
        )
    if is_blocked(db, claim.finder_id, claim.claimant_id):
        raise forbidden("Kontakt jest zablokowany.")
    require_claim_transition(claim.status, "accepted")
    now = now_utc()
    claim.status = "accepted"
    claim.accepted_at = now
    claim.updated_at = now
    claim.handover_code = new_handover_code()
    claim.handover_attempts = 0
    claim.finder_note = clean_text(note, 300) or None
    r.status = "reserved"
    r.updated_at = now
    _audit(db, actor.guest_id, claim.id, "accept", "pending", "accepted")
    db.add(
        AuditEvent(
            actor_id=actor.guest_id,
            entity="report",
            entity_id=r.id,
            action="reserve",
            from_status="active",
            to_status="reserved",
        )
    )
    _system(
        db,
        claim.id,
        "Znalazca zaakceptował roszczenie. Ustalcie w rozmowie bezpieczne miejsce i czas przekazania. "
        "Osoba odbierająca ma kod przekazania — pokaże go przy spotkaniu.",
    )
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise conflict("item_reserved", "Inne roszczenie do tej rzeczy zostało właśnie zaakceptowane.") from e
    return claim


def reject(db: DbSession, actor: Actor, claim_id: uuid.UUID, note: str | None) -> Claim:
    claim, role = load_claim(db, claim_id, actor, lock=True)
    if role != "finder":
        raise forbidden("Tylko znalazca może odrzucić roszczenie.")
    if claim.status == "rejected":
        db.commit()
        return claim
    prev = claim.status
    require_claim_transition(prev, "rejected")
    now = now_utc()
    claim.status = "rejected"
    claim.finder_note = clean_text(note, 300) or claim.finder_note
    claim.handover_code = None
    claim.updated_at = now
    claim.closed_at = now
    if prev == "accepted":
        r = db.get(Report, claim.report_id)
        assert r is not None
        if r.status == "reserved":
            r.status = "active"
            r.updated_at = now
        _system(db, claim.id, "Znalazca cofnął akceptację. Przedmiot ponownie czeka na właściciela.")
    else:
        _system(db, claim.id, "Znalazca uznał, że opis nie pasuje do przedmiotu.")
    _audit(db, actor.guest_id, claim.id, "reject", prev, "rejected")
    db.commit()
    return claim


def withdraw(db: DbSession, actor: Actor, claim_id: uuid.UUID) -> Claim:
    claim, role = load_claim(db, claim_id, actor, lock=True)
    if role != "claimant":
        raise forbidden("Tylko osoba zgłaszająca może wycofać roszczenie.")
    if claim.status == "withdrawn":
        db.commit()
        return claim
    prev = claim.status
    require_claim_transition(prev, "withdrawn")
    now = now_utc()
    claim.status = "withdrawn"
    claim.handover_code = None
    claim.updated_at = now
    claim.closed_at = now
    if prev == "accepted":
        r = db.get(Report, claim.report_id)
        assert r is not None
        if r.status == "reserved":
            r.status = "active"
            r.updated_at = now
    _system(db, claim.id, "Roszczenie zostało wycofane.")
    _audit(db, actor.guest_id, claim.id, "withdraw", prev, "withdrawn")
    db.commit()
    return claim


def handover(db: DbSession, actor: Actor, claim_id: uuid.UUID, code: str | None) -> Claim:
    """Znalazca potwierdza wydanie. Prawidłowy kod = potwierdzenie obu stron (odbiorca go pokazał)."""
    claim, role = load_claim(db, claim_id, actor, lock=True)
    if role != "finder":
        raise forbidden("Wydanie potwierdza znalazca.")
    if claim.status == "returned":
        db.commit()
        return claim
    if claim.status != "accepted":
        raise conflict("invalid_state", "Najpierw zaakceptuj roszczenie.")
    now = now_utc()
    if code:
        if claim.handover_attempts >= MAX_HANDOVER_ATTEMPTS:
            raise ApiError(
                429,
                "code_locked",
                "Wykorzystano limit prób kodu. Potwierdź wydanie bez kodu — odbiorca potwierdzi odbiór w aplikacji.",
            )
        normalized = "".join(ch for ch in code if ch.isdigit())
        if not claim.handover_code or not hmac.compare_digest(normalized, claim.handover_code):
            claim.handover_attempts += 1
            db.commit()
            left = MAX_HANDOVER_ATTEMPTS - claim.handover_attempts
            raise ApiError(
                422, "bad_code", f"Nieprawidłowy kod przekazania. Pozostałe próby: {left}.", {"attempts_left": left}
            )
        claim.finder_confirmed_at = claim.finder_confirmed_at or now
        claim.owner_confirmed_at = claim.owner_confirmed_at or now
        _system(db, claim.id, "Kod przekazania potwierdzony przy spotkaniu.")
    else:
        if claim.finder_confirmed_at is None:
            claim.finder_confirmed_at = now
            _system(db, claim.id, "Znalazca potwierdził wydanie przedmiotu. Czekamy na potwierdzenie odbioru.")
    claim.updated_at = now
    _finalize_if_complete(db, claim, actor)
    db.commit()
    return claim


def confirm_received(db: DbSession, actor: Actor, claim_id: uuid.UUID) -> Claim:
    claim, role = load_claim(db, claim_id, actor, lock=True)
    if role != "claimant":
        raise forbidden("Odbiór potwierdza osoba odbierająca.")
    if claim.status == "returned":
        db.commit()
        return claim
    if claim.status != "accepted":
        raise conflict("invalid_state", "Roszczenie nie jest zaakceptowane.")
    now = now_utc()
    if claim.owner_confirmed_at is None:
        claim.owner_confirmed_at = now
        _system(db, claim.id, "Odbiorca potwierdził odbiór przedmiotu.")
    claim.updated_at = now
    _finalize_if_complete(db, claim, actor)
    db.commit()
    return claim


def thank(db: DbSession, actor: Actor, claim_id: uuid.UUID) -> None:
    claim, role = load_claim(db, claim_id, actor, lock=True)
    if role != "claimant":
        raise forbidden("Podziękować może osoba, która odzyskała przedmiot.")
    if claim.status != "returned":
        raise conflict("not_returned", "Podziękowanie jest możliwe po zakończonym zwrocie.")
    if db.scalar(select(func.count()).select_from(Thanks).where(Thanks.claim_id == claim.id)):
        db.commit()
        return
    db.add(Thanks(id=uuid.uuid4(), claim_id=claim.id, from_id=claim.claimant_id, to_id=claim.finder_id))
    _system(db, claim.id, "❤ Właściciel podziękował za zwrot.")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # równoległe podwójne kliknięcie — jedno podziękowanie


def block(db: DbSession, actor: Actor, claim_id: uuid.UUID) -> Claim:
    claim, role = load_claim(db, claim_id, actor, lock=True)
    other = claim.claimant_id if role == "finder" else claim.finder_id
    if not db.get(Block, (actor.guest_id, other)):
        db.add(Block(blocker_id=actor.guest_id, blocked_id=other))
    if claim.status in OPEN_CLAIM_STATES:
        prev = claim.status
        if prev == "accepted":
            r = db.get(Report, claim.report_id)
            if r is not None and r.status == "reserved":
                r.status = "active"
        claim.handover_code = None
        _close(db, claim, "blocked", actor)
    db.commit()
    return claim


def list_messages(db: DbSession, actor: Actor, claim_id: uuid.UUID, after_id: int) -> dict[str, Any]:
    claim, role = load_claim(db, claim_id, actor)
    msgs = db.scalars(
        select(Message).where(Message.claim_id == claim.id, Message.id > after_id).order_by(Message.id).limit(200)
    ).all()
    return {
        "items": [
            {
                "id": m.id,
                "kind": m.kind,
                "mine": m.sender_id == actor.guest_id,
                "body": m.body,
                "created_at": iso(m.created_at),
            }
            for m in msgs
        ],
        "status": claim.status,
    }


def post_message(db: DbSession, actor: Actor, claim_id: uuid.UUID, body: str) -> Message:
    claim, role = load_claim(db, claim_id, actor, lock=True)
    if claim.status not in ("pending", "accepted", "returned"):
        raise conflict("chat_closed", "Ta rozmowa jest zamknięta.")
    if is_blocked(db, claim.finder_id, claim.claimant_id):
        raise forbidden("Kontakt jest zablokowany.")
    text_ = clean_text(body, 1000, multiline=True)
    if not text_:
        raise invalid("empty_message", "Wiadomość jest pusta.")
    # Ograniczenie spamu: max 5 wiadomości z rzędu bez odpowiedzi drugiej strony.
    recent = db.scalars(
        select(Message.sender_id)
        .where(Message.claim_id == claim.id, Message.kind == "text")
        .order_by(Message.id.desc())
        .limit(5)
    ).all()
    if len(recent) == 5 and all(s == actor.guest_id for s in recent):
        raise ApiError(429, "wait_for_reply", "Poczekaj na odpowiedź drugiej strony, zanim napiszesz więcej.")
    m = Message(claim_id=claim.id, sender_id=actor.guest_id, kind="text", body=text_)
    db.add(m)
    db.flush()
    _mark_read(db, claim.id, actor.guest_id, m.id)
    db.commit()
    return m


def _mark_read(db: DbSession, claim_id: uuid.UUID, guest_id: Any, last_id: int) -> None:
    cr = db.get(ClaimRead, (claim_id, guest_id))
    if cr is None:
        db.add(ClaimRead(claim_id=claim_id, guest_id=guest_id, last_read_id=last_id))
    elif last_id > cr.last_read_id:
        cr.last_read_id = last_id


def mark_read(db: DbSession, actor: Actor, claim_id: uuid.UUID, last_id: int) -> None:
    claim, _ = load_claim(db, claim_id, actor)
    max_id = db.scalar(select(func.max(Message.id)).where(Message.claim_id == claim.id)) or 0
    _mark_read(db, claim.id, actor.guest_id, min(last_id, max_id))
    db.commit()


def unread_total(db: DbSession, guest_id: Any) -> int:
    rows = db.execute(
        select(Claim.id, func.max(Message.id), func.coalesce(func.max(ClaimRead.last_read_id), 0))
        .join(Message, Message.claim_id == Claim.id)
        .outerjoin(ClaimRead, (ClaimRead.claim_id == Claim.id) & (ClaimRead.guest_id == guest_id))
        .where((Claim.finder_id == guest_id) | (Claim.claimant_id == guest_id))
        .where(Message.sender_id.is_distinct_from(guest_id))
        .group_by(Claim.id)
    ).all()
    return sum(1 for _, last, read in rows if last and last > read)


def touch_report_claims_closed_on_hide(db: DbSession, report_id: uuid.UUID) -> None:
    close_open_claims_for_report(db, report_id, "report_hidden", None)
    db.execute(update(Report).where(Report.id == report_id, Report.status == "reserved").values(status="active"))
