"""Testy jednostkowe: stany, sygnały rankingu, parser zapytań, walidacja."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.categories import validate_attributes, validate_colors
from app.domain.matching import Cand, QueryCtx, color_relation, explain
from app.domain.nlquery import parse_query
from app.domain.states import can_claim, can_report, claim_is_returned
from app.errors import ApiError
from app.geo import public_area, rounded_distance_m
from app.schemas import reject_contact_data

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def test_state_machines():
    assert can_report("active", "reserved") and can_report("reserved", "active")
    assert not can_report("resolved", "active") and not can_report("withdrawn", "active")
    assert can_claim("pending", "accepted") and can_claim("accepted", "returned")
    assert not can_claim("pending", "returned")  # zwrot tylko po akceptacji
    assert not can_claim("rejected", "accepted") and not can_claim("returned", "closed")
    assert not claim_is_returned(True, False) and claim_is_returned(True, True)


def _cand(**kw) -> Cand:
    base = dict(
        id=1,
        kind="found",
        category="clothing",
        colors=["black"],
        attrs={"subtype": "czapka"},
        lat=50.0617,
        lon=19.9373,
        occurred_from=NOW,
        occurred_to=NOW + timedelta(hours=1),
    )
    base.update(kw)
    return Cand(**base)


def _lost_ctx(**kw) -> QueryCtx:
    base = dict(
        category="clothing",
        colors=["black"],
        attrs={"subtype": "czapka"},
        lat=50.0617,
        lon=19.9373,
        time_from=NOW - timedelta(hours=3),
        time_to=NOW - timedelta(hours=1),
        source_kind="lost",
    )
    base.update(kw)
    return QueryCtx(**base)


def test_explain_strong_match_has_reasons_not_percentages():
    ex = explain(_lost_ctx(), _cand())
    assert ex.tier == "strong"
    assert any("kategoria" in r for r in ex.reasons) and any("Kolor" in r for r in ex.reasons)
    assert not any("%" in r for r in ex.reasons)


def test_image_similarity_cannot_hide_conflicts():
    ex = explain(
        _lost_ctx(attrs={"subtype": "czapka", "brand": "Nike"}),
        _cand(colors=["red"], attrs={"subtype": "czapka", "brand": "Adidas"}, image_sim=0.97),
    )
    assert ex.tier != "strong"
    assert any("Inny kolor" in w for w in ex.warnings) and any("marka" in w for w in ex.warnings)


def test_found_before_lost_is_flagged():
    ex = explain(_lost_ctx(), _cand(occurred_from=NOW - timedelta(days=3), occurred_to=NOW - timedelta(days=3)))
    assert any("wcześniej" in w for w in ex.warnings) and ex.tier != "strong"


def test_weak_when_nothing_matches():
    ex = explain(_lost_ctx(category="electronics", colors=["silver"], attrs={}), _cand(lat=50.10, lon=20.05))
    assert ex.tier == "weak"


def test_color_relations():
    assert color_relation(["navy"], ["blue"]) == "near"
    assert color_relation(["black"], ["black", "white"]) == "match"
    assert color_relation(["red"], ["green"]) == "conflict"
    assert color_relation([], ["green"]) == "unknown"


def test_parse_query_polish():
    now = datetime(2026, 11, 7, 10, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    p = parse_query("Zgubiłem czarną czapkę wczoraj przy AGH", now=now)
    assert (p.kind, p.category, p.subtype, p.colors) == ("found", "clothing", "czapka", ["black"])
    assert p.date_from.date().isoformat() == "2026-11-06" and p.place["key"] == "agh"
    p = parse_query("znalazłem klucze z brelokiem misia na Kazimierzu", now=now)
    assert p.kind == "lost" and p.category == "keys" and p.place["key"] == "kazimierz"
    assert "misia" in (p.text or "")
    p = parse_query("srebrny laptop Dell 3 dni temu", now=now)
    assert p.category == "electronics" and p.brand == "Dell" and p.colors == ["silver"]
    p = parse_query("xyzzy", now=now)
    assert p.category is None and p.text == "xyzzy"


def test_attribute_validation():
    assert validate_attributes("keys", {"key_count": "3", "keychain": " Miś "}) == {"key_count": 3, "keychain": "Miś"}
    with pytest.raises(ApiError):
        validate_attributes("keys", {"brand": "x"})
    with pytest.raises(ApiError):
        validate_attributes("clothing", {"subtype": "laptop"})
    with pytest.raises(ApiError):
        validate_colors(["black", "white", "red", "blue"])


def test_contact_data_detection():
    for bad in ("tel. 600-123-456", "+48 600123456", "pisz: a.b@c.pl", "https://zly.link/x"):
        with pytest.raises(ApiError):
            reject_contact_data("Opis", bad)
    reject_contact_data("Opis", "Czapka rozmiar 56, 2 klucze")


def test_public_area_and_rounding():
    a = public_area(50.0617, 19.9373, 0)
    assert a.radius_m == 400
    assert public_area(50.0617, 19.9373, 1100).radius_m == 1250
    assert rounded_distance_m(149) == 100 and rounded_distance_m(1260) == 1500


def test_strong_requires_distinguishing_signal():
    # Ta sama kategoria, rodzaj, bliskość i czas — ale bez koloru/marki/zdjęcia: tylko „możliwe”.
    ex = explain(_lost_ctx(colors=[]), _cand(colors=[]))
    assert ex.tier == "possible"
    ex = explain(
        _lost_ctx(colors=[], attrs={"subtype": "czapka", "brand": "4F"}),
        _cand(colors=[], attrs={"subtype": "czapka", "brand": "4F"}),
    )
    assert ex.tier == "strong"


def test_distinct_image_counts_but_similarity_alone_does_not():
    base = dict(colors=[], attrs={"subtype": "czapka"})
    plain = explain(_lost_ctx(**base), _cand(colors=[], image_sim=0.9))
    assert plain.tier == "possible" and "Zdjęcie podobne wizualnie" in plain.reasons
    c = _cand(colors=[], image_sim=0.9)
    c.image_distinct = True
    assert explain(_lost_ctx(**base), c).tier == "strong"
