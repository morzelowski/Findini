"""Sesje gościa, tokeny, kody odzyskiwania i zależności autoryzacji.

- Token sesji: 384 bity z `secrets`, w bazie tylko SHA-256.
- Kod odzyskiwania: 160 bitów + suma kontrolna, w bazie HMAC-SHA256(server_secret, kod).
- UUID zasobu nigdy nie jest traktowany jako uwierzytelnienie.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Guest, Session

TOKEN_PREFIX = "fnd_"
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_ADJ = [
    "Życzliwy",
    "Uważny",
    "Pomocny",
    "Spokojny",
    "Pogodny",
    "Rzetelny",
    "Uprzejmy",
    "Bystry",
    "Cichy",
    "Serdeczny",
    "Wesoły",
    "Dzielny",
    "Sprytny",
    "Miły",
    "Szczery",
    "Łagodny",
]
_NOUN = [
    "Jeż",
    "Lis",
    "Bóbr",
    "Borsuk",
    "Żuraw",
    "Wróbel",
    "Dzięcioł",
    "Zając",
    "Łoś",
    "Kos",
    "Sokół",
    "Żubr",
    "Rysiek",
    "Kruk",
    "Puchacz",
    "Szczygieł",
]


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def random_alias() -> str:
    return f"{secrets.choice(_ADJ)} {secrets.choice(_NOUN)} {secrets.randbelow(90) + 10}"


def new_recovery_code() -> str:
    """8 grup losowych (160 bitów) + grupa kontrolna wykrywająca literówki."""
    payload = "".join(secrets.choice(_CROCKFORD) for _ in range(32))
    chars = payload + _recovery_checksum(payload)
    return "-".join(chars[i : i + 4] for i in range(0, len(chars), 4))


def _recovery_checksum(payload: str) -> str:
    bits = int.from_bytes(hashlib.sha256(("findini-recovery-v2:" + payload).encode()).digest()[:3], "big")
    return "".join(_CROCKFORD[(bits >> shift) & 31] for shift in (15, 10, 5, 0))


def valid_recovery_code(code: str) -> bool:
    c = normalize_recovery_code(code)
    if not re.fullmatch(r"[0-9A-HJKMNP-TV-Z]+", c):
        return False
    # Istniejące kody zachowują ważność do wymiany/odzyskania dostępu.
    return len(c) == 20 or (len(c) == 36 and hmac.compare_digest(c[-4:], _recovery_checksum(c[:32])))


def normalize_recovery_code(code: str) -> str:
    c = code.upper().replace("-", "").replace(" ", "")
    c = c.replace("O", "0").replace("I", "1").replace("L", "1")
    return c


def hash_recovery_code(code: str) -> str:
    key = get_settings().server_secret.encode()
    return hmac.new(key, normalize_recovery_code(code).encode(), hashlib.sha256).hexdigest()


def new_handover_code() -> str:
    return f"{secrets.randbelow(100_000_000):08d}"


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ip_key(request: Request) -> str:
    """Skrót IP z sekretem serwera — w licznikach limitów nie przechowujemy jawnych adresów."""
    key = get_settings().server_secret.encode()
    return hmac.new(key, client_ip(request).encode(), hashlib.sha256).hexdigest()[:24]


@dataclass(frozen=True)
class Actor:
    guest_id: object
    session_id: object
    alias: str


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token.startswith(TOKEN_PREFIX) and 20 < len(token) < 200:
            return token
    return None


def _resolve(request: Request, db: DbSession) -> Actor | None:
    token = _bearer(request)
    if token is None:
        return None
    sess = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if sess is None or sess.revoked_at is not None:
        return None
    guest = sess.guest
    if guest.deleted_at is not None:
        return None
    if guest.banned_at is not None:
        raise ApiError(403, "banned", "Ta sesja została zablokowana przez moderację.")
    now = now_utc()
    if now - sess.last_used_at > timedelta(minutes=5):
        db.execute(update(Session).where(Session.id == sess.id).values(last_used_at=now))
        db.commit()
    return Actor(guest_id=guest.id, session_id=sess.id, alias=guest.alias)


def current_actor(request: Request, db: DbSession = Depends(get_db)) -> Actor:
    actor = _resolve(request, db)
    if actor is None:
        raise ApiError(
            401,
            "session_required",
            "Sesja wygasła lub jest nieprawidłowa. Aplikacja utworzy nową sesję gościa.",
        )
    return actor


def optional_actor(request: Request, db: DbSession = Depends(get_db)) -> Actor | None:
    try:
        return _resolve(request, db)
    except ApiError:
        return None


def require_admin(request: Request) -> None:
    token = get_settings().admin_token
    supplied = request.headers.get("x-admin-token", "")
    if not token or len(token) < 24 or not hmac.compare_digest(token, supplied):
        raise ApiError(403, "forbidden", "Brak uprawnień moderatora.")


def get_guest(db: DbSession, actor: Actor) -> Guest:
    g = db.get(Guest, actor.guest_id)
    assert g is not None
    return g
