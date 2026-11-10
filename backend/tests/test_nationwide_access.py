"""Regresje: cała Polska, stabilna siatka, grupy mapy i przeniesienie dostępu."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import session_factory
from app.domain.nlquery import parse_query
from app.geo import public_area
from app.models import Claim, Guest
from app.security import hash_recovery_code, new_recovery_code, normalize_recovery_code, valid_recovery_code
from tests.conftest import report_payload


@pytest.mark.parametrize(
    "lat,lon",
    [
        (52.2297, 21.0122),
        (54.35, 18.65),
        (53.43, 14.55),
        (49.30, 19.95),
        (54.79, 18.42),
        (49.01, 22.86),
        (52.83, 14.12),
        (50.87, 24.14),
    ],
)
def test_reports_across_poland(client, guest_factory, lat, lon):
    g = guest_factory()
    r = g.post("/v1/reports", json=report_payload(location={"lat": lat, "lon": lon, "source": "map"}))
    assert r.status_code == 201
    rid = r.json()["id"]
    results = client.get("/v1/reports", params={"lat": lat, "lon": lon, "radius_m": 1000}).json()
    item = next(i for i in results["items"] if i["id"] == rid)
    assert "private" not in item and item["area"]["precision"] == "approximate"


def test_country_map_counts_and_local_cells(client, guest_factory):
    g = guest_factory()
    for lat, lon in [(52.23, 21.01), (52.2301, 21.0101), (54.35, 18.65), (50.06, 19.94)]:
        assert (
            g.post("/v1/reports", json=report_payload(location={"lat": lat, "lon": lon, "source": "map"})).status_code
            == 201
        )
    country = client.get("/v1/reports/areas", params={"bbox": "13,48,25,56"})
    assert country.status_code == 200
    groups = country.json()["areas"]
    assert sum(a["count"] for a in groups) == 4
    assert all(a["cell_id"].startswith("cluster:") for a in groups)
    local = client.get("/v1/reports/areas", params={"bbox": "21.00,52.22,21.02,52.24"}).json()["areas"]
    assert sum(a["count"] for a in local) == 2
    assert all(not a["cell_id"].startswith("cluster:") for a in local)


def test_search_places_diacritics_ambiguity_and_no_auth(client):
    for query, expected in [("warsza", "Warszawa"), ("lodz", "Łódź"), ("Ustrzyki Gorne", "Ustrzyki Górne")]:
        r = client.get("/v1/places", params={"q": query})
        assert r.status_code == 200
        assert any(p["name"] == expected for p in r.json()["items"])
    many = client.get("/v1/places", params={"q": "Nowa Wies"}).json()["items"]
    assert 1 < len(many) <= 20
    assert len({p["key"] for p in many}) == len(many)
    assert all("region" in p and "county" in p for p in many)
    assert client.get("/v1/places", params={"q": "x"}).status_code == 422
    assert client.get("/v1/places", params={"q": "x" * 81}).status_code == 422


@pytest.mark.parametrize(
    "sentence,name",
    [
        ("czarna czapka w Warszawie", "Warszawa"),
        ("portfel w Gdańsku", "Gdańsk"),
        ("klucze w Łodzi", "Łódź"),
        ("laptop we Wrocławiu", "Wrocław"),
    ],
)
def test_nationwide_query_parser(sentence, name):
    p = parse_query(sentence)
    assert p.place["name"] == name
    assert not p.text


def test_generic_landmarks_do_not_select_krakow():
    assert parse_query("czapka przy dworcu").place is None
    assert parse_query("klucze na rynku").place is None


def test_map_and_list_apply_the_same_filters(client, guest_factory):
    g = guest_factory()
    for lat, lon, color in [(52.23, 21.01, "black"), (52.24, 21.02, "red"), (54.35, 18.65, "black")]:
        assert (
            g.post(
                "/v1/reports",
                json=report_payload(colors=[color], location={"lat": lat, "lon": lon, "source": "map"}),
            ).status_code
            == 201
        )
    filters = {"category": "clothing", "colors": "black", "lat": 52.23, "lon": 21.01, "radius_m": 5000}
    results = client.get("/v1/reports", params=filters).json()["items"]
    areas = client.get("/v1/reports/areas", params=filters | {"bbox": "13,48,25,56"}).json()["areas"]
    assert len(results) == sum(a["count"] for a in areas) == 1


def test_map_center_configuration_does_not_move_privacy_grid(monkeypatch):
    before = public_area(52.23012, 21.01456)
    s = get_settings()
    monkeypatch.setattr(s, "pilot_center_lat", 54.0)
    assert public_area(52.23012, 21.01456) == before


def test_recovery_length_checksum_and_existing_codes(client, guest_factory):
    code = new_recovery_code()
    assert len(normalize_recovery_code(code)) == 36
    assert len(code.split("-")) == 9 and valid_recovery_code(code)
    corrupted = code[:-1] + ("Z" if code[-1] != "Z" else "X")
    assert not valid_recovery_code(corrupted)
    assert not valid_recovery_code("!" * 36)
    g = guest_factory()
    legacy = "7K2M-QX9D-4WZA-HJ8P-6F3R"
    with session_factory()() as db:
        guest = db.scalar(select(Guest).where(Guest.id == g.id))
        guest.recovery_hash = hash_recovery_code(legacy)
        db.commit()
    rec = client.post("/v1/sessions/recover", json={"code": legacy.lower().replace("-", " ")})
    assert rec.status_code == 201
    assert valid_recovery_code(rec.json()["new_recovery_code"])
    assert len(rec.json()["token"].removeprefix("fnd_")) == 64
    assert g.get("/v1/me").status_code == 401


def test_one_recovery_code_cannot_create_two_sessions(client, guest_factory):
    g = guest_factory()
    code = g.post("/v1/me/recovery-code").json()["code"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(lambda _: client.post("/v1/sessions/recover", json={"code": code}).status_code, range(2))
        )
    assert sorted(statuses) == [201, 404]


def test_existing_six_digit_handover_still_works(client, guest_factory):
    finder, owner = guest_factory(), guest_factory()
    rid = finder.post("/v1/reports", json=report_payload()).json()["id"]
    cid = owner.post(f"/v1/reports/{rid}/claims", json={"answer": "Ukryty szczegół"}).json()["id"]
    assert finder.post(f"/v1/claims/{cid}/accept", json={}).status_code == 200
    with session_factory()() as db:
        claim = db.scalar(select(Claim).where(Claim.id == cid))
        claim.handover_code = "012345"
        db.commit()
    assert finder.get(f"/v1/claims/{cid}").json()["handover_code_length"] == 6
    assert owner.get(f"/v1/claims/{cid}").json()["handover_code"] == "012345"
    assert finder.post(f"/v1/claims/{cid}/handover", json={"code": "012345"}).json()["status"] == "returned"
