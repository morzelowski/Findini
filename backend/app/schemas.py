"""Kontrakty wejścia (walidacja) i jawne reprezentacje wyjścia.

Publiczna reprezentacja zgłoszenia jest budowana pole po polu w `public_report()` —
nigdy przez serializację całego obiektu bazy.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.errors import invalid

_CTRL = re.compile(r"[\u0000-\u0008\u000b-\u001f\u007f​-‏‪-‮⁦-⁩]")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?48[\s-]?)?(?:\d[\s-]?){9,}")
_URL = re.compile(r"(https?://|www\.)\S+", re.I)


def clean_text(value: str | None, max_len: int, multiline: bool = False) -> str:
    if value is None:
        return ""
    s = unicodedata.normalize("NFC", value)
    s = _CTRL.sub("", s)
    if multiline:
        lines = [" ".join(line.split()) for line in s.splitlines()]
        s = "\n".join(lines).strip()
        s = re.sub(r"\n{3,}", "\n\n", s)
    else:
        s = " ".join(s.split())
    if len(s) > max_len:
        raise invalid("too_long", f"Tekst może mieć maksymalnie {max_len} znaków.")
    return s


def reject_contact_data(field: str, value: str) -> None:
    """Publiczne pola nie mogą zawierać telefonu, e-maila ani linków (ochrona przed oszustwami)."""
    if _EMAIL.search(value) or _PHONE.search(value) or _URL.search(value):
        raise invalid(
            "contact_data_in_public_text",
            f"Pole „{field}” wygląda na dane kontaktowe lub link. Kontakt odbywa się przez prywatną "
            "rozmowę w aplikacji — usuń numer, e-mail lub adres strony.",
        )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=2000)


class LocationIn(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: int | None = Field(default=None, ge=0, le=10000)
    uncertainty_m: int = Field(default=0, ge=0, le=3000)
    source: Literal["gps", "map"]


class ReportCreate(StrictModel):
    kind: Literal["lost", "found"]
    category: str = Field(max_length=32)
    title: str = Field(min_length=3, max_length=80)
    description: str = Field(default="", max_length=1000)
    attributes: dict[str, Any] = Field(default_factory=dict)
    colors: list[str] = Field(default_factory=list, max_length=3)
    occurred_from: datetime
    occurred_to: datetime
    location: LocationIn
    area_label: str | None = Field(default=None, max_length=80)
    holding: Literal["with_finder", "at_place", "office"] | None = None
    holding_note: str | None = Field(default=None, max_length=120)
    secret_details: str | None = Field(default=None, max_length=500)
    claim_question: str | None = Field(default=None, max_length=200)
    photo_ids: list[uuid.UUID] = Field(default_factory=list, max_length=4)

    @field_validator("occurred_from", "occurred_to")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("data musi zawierać strefę czasową (ISO 8601 z przesunięciem)")
        return v


class ReportUpdate(StrictModel):
    category: str | None = Field(default=None, max_length=32)
    title: str | None = Field(default=None, min_length=3, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    attributes: dict[str, Any] | None = None
    colors: list[str] | None = Field(default=None, max_length=3)
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    location: LocationIn | None = None
    area_label: str | None = Field(default=None, max_length=80)
    holding: Literal["with_finder", "at_place", "office"] | None = None
    holding_note: str | None = Field(default=None, max_length=120)
    secret_details: str | None = Field(default=None, max_length=500)
    claim_question: str | None = Field(default=None, max_length=200)
    photo_ids: list[uuid.UUID] | None = Field(default=None, max_length=4)


class ResolveIn(StrictModel):
    note: Literal["owner_found", "handed_to_office", "returned_outside_app", "other"] = "other"


class ClaimCreate(StrictModel):
    answer: str = Field(min_length=3, max_length=500)
    proof_details: str = Field(default="", max_length=1000)
    evidence_photo_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2)
    lost_report_id: uuid.UUID | None = None


class DecisionIn(StrictModel):
    note: str | None = Field(default=None, max_length=300)


class HandoverIn(StrictModel):
    code: str | None = Field(default=None, max_length=12)


class MessageIn(StrictModel):
    body: str = Field(min_length=1, max_length=1000)


class RecoverIn(StrictModel):
    code: str = Field(min_length=10, max_length=40)


class AbuseIn(StrictModel):
    target_type: Literal["report", "claim", "message"]
    target_id: str = Field(max_length=40)
    reason: Literal["scam", "bait", "spam", "offensive", "personal_data", "stolen", "other"]
    details: str = Field(default="", max_length=500)


class AdminResolveIn(StrictModel):
    action: Literal["dismiss", "hide_report", "unhide_report", "ban_guest"]
    note: str = Field(default="", max_length=300)


class ParseIn(StrictModel):
    text: str = Field(min_length=1, max_length=300)


class ReadIn(StrictModel):
    last_read_id: int = Field(ge=0)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None
