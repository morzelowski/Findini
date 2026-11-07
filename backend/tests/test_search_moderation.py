"""Wyszukiwanie, paginacja, dopasowania i moderacja."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import iso, report_payload

ADMIN = {"X-Admin-Token": "test-admin-token-0123456789abcdef"}


def test_keyset_pagination_is_stable_and_complete(client, guest_factory):
    g = guest_factory()
    created = set()
    for i in range(9):
        r = g.post("/v1/reports", json=report_payload(title=f"Czapka numer {i}"))
        assert r.status_code == 201, r.text
        created.add(r.json()["id"])
    for sort in ("newest", "nearest", "relevance"):
        params = {"limit": 4, "sort": sort, "lat": 50.06, "lon": 19.92, "radius_m": 5000, "q": "czapka"}
        seen: list[str] = []
        cursor = None
        while True:
            p = dict(params)
            if cursor:
                p["cursor"] = cursor
            res = client.get("/v1/reports", params=p).json()
            seen += [i["id"] for i in res["items"]]
            cursor = res["next_cursor"]
            if not cursor:
                break
        assert len(seen) == len(set(seen)) == 9, sort
        assert set(seen) == created


def test_text_search_handles_polish_inflection_and_diacritics(client, guest_factory):
    g = guest_factory()
    rid = g.post(
        "/v1/reports",
        json=report_payload(
            title="Żółty parasol w kropki", category="accessories", attributes={"subtype": "parasol"}, colors=["yellow"]
        ),
    ).json()["id"]
    for q in ("parasol", "zolty parasol", "parasola", "żółty"):
        ids = [i["id"] for i in client.get("/v1/reports", params={"q": q}).json()["items"]]
        assert rid in ids, q


def test_filters_and_empty_state_suggestions(client, guest_factory):
    g = guest_factory()
    g.post("/v1/reports", json=report_payload(colors=["black"]))
    res = client.get("/v1/reports", params={"colors": "navy"}).json()
    assert len(res["items"]) == 1  # granatowy ~ czarny (bliskie kolory)
    res = client.get("/v1/reports", params={"colors": "yellow", "lat": 50.06, "lon": 19.92, "radius_m": 500}).json()
    assert res["items"] == []
    actions = [s["action"] for s in res["suggestions"]]
    assert "expand_radius" in actions and "create_lost" in actions
    old = datetime.now(UTC) - timedelta(days=30)
    res = client.get("/v1/reports", params={"date_from": iso(old - timedelta(days=2)), "date_to": iso(old)}).json()
    assert res["items"] == [] and "expand_dates" in [s["action"] for s in res["suggestions"]]


def test_matches_explain_and_flag_conflicts(client, guest_factory):
    owner, f1, f2, f3 = guest_factory(), guest_factory(), guest_factory(), guest_factory()
    now = datetime.now(UTC)
    lost = owner.post(
        "/v1/reports",
        json=report_payload(
            "lost",
            title="Czarna czapka",
            attributes={"subtype": "czapka", "brand": "4F"},
            occurred_from=iso(now - timedelta(hours=10)),
            occurred_to=iso(now - timedelta(hours=8)),
        ),
    ).json()["id"]
    good = f1.post("/v1/reports", json=report_payload(attributes={"subtype": "czapka", "brand": "4F"})).json()["id"]
    wrong_color = f2.post(
        "/v1/reports", json=report_payload(colors=["red"], attributes={"subtype": "czapka", "brand": "Nike"})
    ).json()["id"]
    too_early = f3.post(
        "/v1/reports",
        json=report_payload(
            occurred_from=iso(now - timedelta(days=5)),
            occurred_to=iso(now - timedelta(days=5, hours=-1)),
        ),
    ).json()["id"]
    m = owner.get(f"/v1/reports/{lost}/matches").json()
    strong_ids = [i["id"] for i in m["strong"]]
    assert good in strong_ids
    g = next(i for i in m["strong"] if i["id"] == good)
    assert any("Marka" in r for r in g["match"]["reasons"])
    assert wrong_color not in strong_ids and too_early not in strong_ids
    everything = m["strong"] + m["possible"]
    for i in everything:
        if i["id"] == wrong_color:
            assert any("Inny kolor" in w for w in i["match"]["warnings"])
    # cudze dopasowania są prywatne
    assert f1.get(f"/v1/reports/{lost}/matches").status_code == 404


def test_no_convincing_matches_message(client, guest_factory):
    owner, finder = guest_factory(), guest_factory()
    lost = owner.post(
        "/v1/reports",
        json=report_payload(
            "lost",
            category="electronics",
            title="Laptop Dell",
            attributes={"subtype": "laptop", "brand": "Dell"},
            colors=["silver"],
        ),
    ).json()["id"]
    finder.post("/v1/reports", json=report_payload())  # czapka — inna kategoria
    m = owner.get(f"/v1/reports/{lost}/matches").json()
    assert m["strong"] == [] and m["possible"] == []
    assert "Brak przekonujących dopasowań" in m["notice"]


def test_abuse_auto_hide_blocks_further_use(client, guest_factory):
    scammer, victim = guest_factory(), guest_factory()
    rid = scammer.post(
        "/v1/reports",
        json=report_payload(
            title="Znaleziony iPhone przynęta", category="electronics", attributes={"subtype": "telefon"}
        ),
    ).json()["id"]
    cid = victim.post(f"/v1/reports/{rid}/claims", json={"answer": "mój telefon"}).json()["id"]
    reporters = [victim, guest_factory(), guest_factory()]
    out = [
        r.post("/v1/abuse-reports", json={"target_type": "report", "target_id": rid, "reason": "bait"}).json()
        for r in reporters
    ]
    assert out[-1]["auto_hidden"] is True
    assert client.get(f"/v1/reports/{rid}").status_code == 404
    assert rid not in [i["id"] for i in client.get("/v1/reports").json()["items"]]
    assert victim.get(f"/v1/claims/{cid}").json()["status"] == "closed"
    assert scammer.patch(f"/v1/reports/{rid}", json={"title": "Nowy tytuł"}).status_code == 409
    newcomer = guest_factory()
    assert newcomer.post(f"/v1/reports/{rid}/claims", json={"answer": "abc"}).status_code == 404
    # Moderator: lista i blokada autora
    assert client.get("/v1/admin/abuse-reports").status_code == 403
    items = client.get("/v1/admin/abuse-reports", headers=ADMIN).json()["items"]
    assert len(items) == 3
    r = client.post(
        f"/v1/admin/abuse-reports/{items[0]['id']}/resolve",
        headers=ADMIN,
        json={"action": "ban_guest", "note": "przynęta"},
    )
    assert r.status_code == 200
    assert scammer.get("/v1/me").status_code in (401, 403)
    assert client.get("/v1/admin/abuse-reports", headers=ADMIN).json()["items"] == []


def test_abuse_on_foreign_claim_not_allowed(client, guest_factory):
    finder, owner, stranger = guest_factory(), guest_factory(), guest_factory()
    rid = finder.post("/v1/reports", json=report_payload()).json()["id"]
    cid = owner.post(f"/v1/reports/{rid}/claims", json={"answer": "abc"}).json()["id"]
    r = stranger.post("/v1/abuse-reports", json={"target_type": "claim", "target_id": cid, "reason": "spam"})
    assert r.status_code == 404


def test_meta_and_parse(client):
    meta = client.get("/v1/meta").json()
    assert {c["key"] for c in meta["categories"]} >= {"electronics", "keys", "clothing", "bags", "wallets", "jewelry"}
    assert meta["pilot"]["name"] == "Kraków"
    p = client.post("/v1/search/parse", json={"text": "zgubiłem czarną czapkę wczoraj przy AGH"}).json()
    assert p["kind"] == "found" and p["category"] == "clothing" and p["colors"] == ["black"]
    assert p["place"]["key"] == "agh" and p["date_from"]


def test_health(client):
    h = client.get("/health").json()
    assert h["db"] is True and h["storage"] is True
