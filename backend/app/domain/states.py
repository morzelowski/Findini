"""Maszyny stanów zgłoszeń i roszczeń (czyste funkcje — testowane jednostkowo).

Zgłoszenie (report):
    active ──(znalazca akceptuje roszczenie)──> reserved ──(oba potwierdzenia)──> resolved
    reserved ──(cofnięcie akceptacji / wycofanie roszczenia)──> active
    active|reserved ──(właściciel usuwa)──> withdrawn
    active ──(minął termin aktywności)──> expired
    lost: active ──(właściciel: „odnalazłem”)──> resolved
  Ukrycie przez moderację to osobna flaga (hidden_at) — blokuje każdą operację publiczną.

Roszczenie (claim) — tylko do zgłoszeń „znaleziono”:
    pending ──(znalazca)──> accepted | rejected
    pending|accepted ──(zgłaszający)──> withdrawn
    accepted ──(znalazca cofa akceptację)──> rejected
    accepted ──(potwierdzenie znalazcy + właściciela)──> returned
    pending|accepted ──(przedmiot wydany komuś innemu / zgłoszenie usunięte/ukryte / blokada)──> closed
"""

from __future__ import annotations

from app.errors import ApiError

REPORT_TRANSITIONS: dict[str, set[str]] = {
    "active": {"reserved", "resolved", "withdrawn", "expired"},
    "reserved": {"active", "resolved", "withdrawn"},
    "resolved": set(),
    "withdrawn": set(),
    "expired": {"active"},  # odnowienie przez właściciela
}

CLAIM_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"accepted", "rejected", "withdrawn", "closed"},
    "accepted": {"returned", "rejected", "withdrawn", "closed"},
    "rejected": set(),
    "withdrawn": set(),
    "returned": set(),
    "closed": set(),
}

OPEN_CLAIM_STATES = {"pending", "accepted"}
PUBLIC_REPORT_STATES = {"active", "reserved"}


def can_report(src: str, dst: str) -> bool:
    return dst in REPORT_TRANSITIONS.get(src, set())


def can_claim(src: str, dst: str) -> bool:
    return dst in CLAIM_TRANSITIONS.get(src, set())


def require_report_transition(src: str, dst: str) -> None:
    if not can_report(src, dst):
        raise ApiError(409, "invalid_state", f"Nie można zmienić stanu zgłoszenia z „{src}” na „{dst}”.")


def require_claim_transition(src: str, dst: str) -> None:
    if not can_claim(src, dst):
        raise ApiError(409, "invalid_state", f"Nie można zmienić stanu roszczenia z „{src}” na „{dst}”.")


def claim_is_returned(finder_confirmed: bool, owner_confirmed: bool) -> bool:
    """Zwrot jest zakończony dopiero po potwierdzeniu obu stron (kod przekazania = oba)."""
    return finder_confirmed and owner_confirmed
