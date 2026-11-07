"""Zadania w tle: indeksowanie zdjęć (embeddingi) i porządki zgodne z retencją.

Wątek działa w procesie API. Zadania pobierane są przez SELECT ... FOR UPDATE SKIP LOCKED,
więc kilka procesów/instancji może pracować równolegle bez dublowania pracy.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from datetime import timedelta

from PIL import Image
from sqlalchemy import delete, select, text, update

from app.config import get_settings
from app.db import session_factory
from app.models import AuditEvent, Photo, Report, Session
from app.security import now_utc
from app.services import ai, photos

log = logging.getLogger("findini.jobs")
MAX_ATTEMPTS = 3

_stop = threading.Event()
_thread: threading.Thread | None = None


def index_pending(batch: int = 4) -> int:
    eng = ai.engine()
    if not eng.ready and not eng.load():
        return 0
    done = 0
    db = session_factory()()
    try:
        # Model zmieniony => ponowne indeksowanie (zgodność modelu/wersji między indeksem a zapytaniem).
        db.execute(
            update(Photo)
            .where(
                Photo.purpose == "report", Photo.embedding_status == "ready", Photo.embedding_model != eng.model_version
            )
            .values(embedding_status="pending", embedding_attempts=0, embedding=None)
        )
        db.commit()
        rows = db.scalars(
            select(Photo)
            .where(
                Photo.purpose == "report", Photo.embedding_status == "pending", Photo.embedding_attempts < MAX_ATTEMPTS
            )
            .order_by(Photo.created_at)
            .limit(batch)
            .with_for_update(skip_locked=True)
        ).all()
        for p in rows:
            # Nie indeksujemy zdjęć ukrytych/usuniętych zgłoszeń.
            if p.report_id is not None:
                r = db.get(Report, p.report_id)
                if r is None or r.hidden_at is not None or r.status in ("withdrawn",):
                    p.embedding_status = "skipped"
                    continue
            try:
                img = Image.open(io.BytesIO(photos.read(p.storage_key)))
                emb = eng.embed(img)
                if emb is None:
                    raise RuntimeError("model unavailable or timeout")
                p.embedding = emb.tolist()
                p.embedding_model = eng.model_version
                p.embedding_status = "ready"
                p.embedding_error = None
                if p.ai_suggestion is None:
                    p.ai_suggestion = eng.suggest(emb)
                done += 1
            except Exception as e:
                p.embedding_attempts += 1
                p.embedding_error = type(e).__name__[:200]
                if p.embedding_attempts >= MAX_ATTEMPTS:
                    p.embedding_status = "failed"
                log.warning("Indeksowanie zdjęcia nie powiodło się (próba %s)", p.embedding_attempts)
        db.commit()
    finally:
        db.close()
    return done


def maintenance() -> dict[str, int]:
    """Retencja: wygaszanie, usuwanie danych po terminie, osierocone pliki, stare liczniki."""
    s = get_settings()
    now = now_utc()
    stats = {"expired": 0, "purged_reports": 0, "orphan_photos": 0}
    db = session_factory()()
    try:
        expired = db.scalars(
            select(Report).where(Report.status == "active", Report.expires_at < now).with_for_update(skip_locked=True)
        ).all()
        for r in expired:
            r.status = "expired"
            r.updated_at = now
            db.add(
                AuditEvent(
                    actor_id=None,
                    entity="report",
                    entity_id=r.id,
                    action="expire",
                    from_status="active",
                    to_status="expired",
                )
            )
            from app.services.claims import close_open_claims_for_report

            close_open_claims_for_report(db, r.id, "resolved_outside", None)
        stats["expired"] = len(expired)
        db.commit()

        cutoff = now - timedelta(days=s.report_purge_after_days)
        old = db.scalars(
            select(Report)
            .where(Report.status.in_(["resolved", "withdrawn", "expired"]), Report.updated_at < cutoff)
            .limit(200)
        ).all()
        for r in old:
            for p in db.scalars(select(Photo).where(Photo.report_id == r.id)).all():
                photos.delete(p.storage_key)
                photos.delete(p.thumb_key)
                db.delete(p)
            db.delete(r)  # kaskadowo: report_private, roszczenia, wiadomości
        stats["purged_reports"] = len(old)
        db.commit()

        orphan_cut = now - timedelta(hours=s.orphan_photo_hours)
        orphans = db.scalars(
            select(Photo)
            .where(Photo.report_id.is_(None), Photo.claim_id.is_(None), Photo.created_at < orphan_cut)
            .limit(500)
        ).all()
        for p in orphans:
            photos.delete(p.storage_key)
            photos.delete(p.thumb_key)
            db.delete(p)
        stats["orphan_photos"] = len(orphans)
        db.execute(
            delete(Session).where(Session.revoked_at.is_not(None), Session.revoked_at < now - timedelta(days=30))
        )
        db.execute(delete(Session).where(Session.last_used_at < now - timedelta(days=s.session_idle_days)))
        db.execute(text("DELETE FROM rate_buckets WHERE window_start < now() - interval '2 days'"))
        db.commit()
    finally:
        db.close()
    if any(stats.values()):
        log.info("Porządki: %s", stats)
    return stats


def _loop() -> None:
    last_maint = 0.0
    while not _stop.is_set():
        try:
            index_pending()
        except Exception:
            log.exception("Błąd indeksowania")
        if time.monotonic() - last_maint > 600:
            try:
                maintenance()
            except Exception:
                log.exception("Błąd porządków")
            last_maint = time.monotonic()
        _stop.wait(3.0)


def start() -> None:
    global _thread
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="findini-jobs", daemon=True)
        _thread.start()


def stop() -> None:
    _stop.set()
