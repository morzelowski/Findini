"""Limity żądań w oknach stałych, trzymane w PostgreSQL (działa z wieloma procesami API).

Limity nakładamy jednocześnie na sesję gościa i na skrót adresu IP — sam identyfikator
gościa łatwo wymienić, a sam IP bywa współdzielony (akademik, NAT), więc progi dla IP
są wyższe. Liczniki są usuwane po 2 dobach (zadanie porządkowe).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.errors import ApiError
from app.security import now_utc


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window_s: int


# Nazwa -> (na gościa, na IP)
RULES: dict[str, tuple[Rule | None, Rule | None]] = {
    "session_create": (None, Rule("session_create_ip", 20, 3600)),
    "recover": (None, Rule("recover_ip", 8, 3600)),
    "report_create": (Rule("report_create", 10, 86400), Rule("report_create_ip", 30, 86400)),
    "report_edit": (Rule("report_edit", 60, 3600), None),
    "photo_upload": (Rule("photo_upload", 40, 3600), Rule("photo_upload_ip", 120, 3600)),
    "claim_create": (Rule("claim_create", 5, 86400), Rule("claim_create_ip", 15, 86400)),
    "claim_question": (Rule("claim_question", 30, 3600), Rule("claim_question_ip", 90, 3600)),
    "message": (Rule("message", 60, 3600), Rule("message_ip", 200, 3600)),
    "handover_code": (Rule("handover_code", 10, 3600), None),
    "image_search": (Rule("image_search", 30, 3600), Rule("image_search_ip", 90, 3600)),
    "abuse": (Rule("abuse", 20, 86400), Rule("abuse_ip", 60, 86400)),
    "search": (None, Rule("search_ip", 1200, 3600)),
}


def _window_start(now: datetime, window_s: int) -> datetime:
    ts = int(now.timestamp())
    return datetime.fromtimestamp(ts - ts % window_s, tz=now.tzinfo)


def _hit(db: DbSession, key: str, rule: Rule) -> int:
    ws = _window_start(now_utc(), rule.window_s)
    row = db.execute(
        text(
            """
            INSERT INTO rate_buckets(key, window_start, count) VALUES (:k, :ws, 1)
            ON CONFLICT (key, window_start) DO UPDATE SET count = rate_buckets.count + 1
            RETURNING count
            """
        ),
        {"k": key, "ws": ws},
    ).one()
    return int(row[0])


def check(db: DbSession, name: str, guest_id: object | None, ip_hash: str | None) -> None:
    """Zwiększa liczniki i rzuca 429 po przekroczeniu. Zatwierdza własną transakcję."""
    if not get_settings().rate_limits_enabled:
        return
    per_guest, per_ip = RULES[name]
    exceeded: Rule | None = None
    if per_guest is not None and guest_id is not None:
        if _hit(db, f"{per_guest.name}:{guest_id}", per_guest) > per_guest.limit:
            exceeded = per_guest
    if per_ip is not None and ip_hash is not None and exceeded is None:
        if _hit(db, f"{per_ip.name}:{ip_hash}", per_ip) > per_ip.limit:
            exceeded = per_ip
    db.commit()
    if exceeded is not None:
        minutes = max(1, exceeded.window_s // 60)
        raise ApiError(
            429,
            "rate_limited",
            "Zbyt wiele prób w krótkim czasie. Spróbuj ponownie później.",
            {"rule": exceeded.name, "window_minutes": minutes},
        )
