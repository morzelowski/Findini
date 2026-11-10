"""Pełny przepływ na dwóch (i trzech) niezależnych sesjach:
zdjęcie + miejsce -> publikacja -> anonimowe wyszukanie -> prywatny dowód -> decyzja znalazcy
-> rozmowa -> kod przekazania -> zwrot -> podziękowanie. Obca sesja nie ma dostępu."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from tests.conftest import iso, jpeg_bytes, report_payload


def _publish_found_with_photo(finder) -> dict:
    up = finder.post(
        "/v1/photos",
        files={"file": ("x.jpg", jpeg_bytes(with_exif_gps=True), "image/jpeg")},
        data={"purpose": "report"},
    )
    assert up.status_code == 201, up.text
    r = finder.post("/v1/reports", json=report_payload(photo_ids=[up.json()["id"]]))
    assert r.status_code == 201, r.text
    return r.json()


def test_full_recovery_flow(client, guest_factory):
    finder, owner, stranger = guest_factory(), guest_factory(), guest_factory()

    # 1. Znalazca publikuje zgłoszenie ze zdjęciem, miejscem i ukrytą cechą.
    rep = _publish_found_with_photo(finder)
    rid = rep["id"]
    assert rep["private"]["secret_details"].startswith("Na metce")
    assert rep["private"]["exact_lat"] == 50.06571

    # 2. Druga osoba BEZ sesji wyszukuje w obszarze i otwiera szczegóły.
    res = client.get("/v1/reports", params={"lat": 50.0650, "lon": 19.9180, "radius_m": 2000, "kind": "found"})
    assert res.status_code == 200
    ids = [i["id"] for i in res.json()["items"]]
    assert rid in ids
    detail = client.get(f"/v1/reports/{rid}")
    assert detail.status_code == 200
    raw = detail.text
    assert "inicjały" not in raw and "metce" not in raw  # ukryta cecha ani pytanie nie są publiczne
    assert "50.06571" not in raw and "19.91893" not in raw  # dokładne miejsce nie jest publiczne
    assert "private" not in detail.json()
    photo_url = detail.json()["photos"][0]["url"]
    img = client.get(photo_url)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert b"SecretCam" not in img.content and b"Exif" not in img.content[:200]

    # 3. Właściciel składa prywatne roszczenie (pytanie widzi dopiero w formularzu).
    form = owner.get(f"/v1/reports/{rid}/claim-form").json()
    assert form["question"] == "Co jest wyszyte na metce?" and form["can_claim"]
    ev = owner.post(
        "/v1/photos", files={"file": ("e.jpg", jpeg_bytes((200, 10, 10)), "image/jpeg")}, data={"purpose": "evidence"}
    )
    assert ev.status_code == 201 and ev.json()["ai_status"] == "skipped"
    c = owner.post(
        f"/v1/reports/{rid}/claims",
        json={
            "answer": "Inicjały K.C. na metce",
            "proof_details": "Mam zdjęcie z zimy w tej czapce",
            "evidence_photo_ids": [ev.json()["id"]],
        },
    )
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    assert c.json()["status"] == "pending"
    assert "secret_details" not in c.json()  # osoba zgłaszająca NIE widzi ukrytej cechy
    assert "handover_code" in c.json() and c.json()["handover_code"] is None

    # Dowód jest prywatny: anonim i obca sesja nie mają dostępu, znalazca ma.
    ev_url = f"/v1/photos/{ev.json()['id']}"
    assert client.get(ev_url).status_code == 404
    assert stranger.get(ev_url).status_code == 404
    assert finder.get(ev_url).status_code == 200

    # 4. Znalazca widzi odpowiedź obok swojej ukrytej cechy i decyduje.
    fc = finder.get(f"/v1/claims/{cid}").json()
    assert fc["role"] == "finder" and fc["answer"] == "Inicjały K.C. na metce"
    assert fc["secret_details"].startswith("Na metce")
    assert "handover_code" not in fc  # znalazca nie zna kodu przekazania

    # Obca sesja nie może czytać ani zmieniać sprawy.
    assert stranger.get(f"/v1/claims/{cid}").status_code == 404
    assert stranger.get(f"/v1/claims/{cid}/messages").status_code == 404
    assert stranger.post(f"/v1/claims/{cid}/accept").status_code == 404
    assert stranger.post(f"/v1/claims/{cid}/messages", json={"body": "hej"}).status_code == 404
    assert owner.post(f"/v1/claims/{cid}/accept").status_code == 403  # tylko znalazca decyduje

    acc = finder.post(f"/v1/claims/{cid}/accept", json={"note": "Pasuje, umówmy się"})
    assert acc.status_code == 200 and acc.json()["status"] == "accepted"
    assert client.get(f"/v1/reports/{rid}").json()["status"] == "reserved"

    # 5. Rozmowa w aplikacji.
    assert (
        owner.post(f"/v1/claims/{cid}/messages", json={"body": "Dziękuję! Może jutro o 12 w holu AGH?"}).status_code
        == 201
    )
    assert finder.post(f"/v1/claims/{cid}/messages", json={"body": "Pasuje, do zobaczenia"}).status_code == 201
    msgs = owner.get(f"/v1/claims/{cid}/messages").json()["items"]
    bodies = [m["body"] for m in msgs if m["kind"] == "text"]
    assert bodies == ["Dziękuję! Może jutro o 12 w holu AGH?", "Pasuje, do zobaczenia"]
    assert any(m["kind"] == "system" for m in msgs)

    # 6. Przekazanie: odbiorca pokazuje kod, znalazca go wpisuje.
    code = owner.get(f"/v1/claims/{cid}").json()["handover_code"]
    assert code and len(code) == 8
    assert finder.get(f"/v1/claims/{cid}").json()["handover_code_length"] == 8
    bad = finder.post(f"/v1/claims/{cid}/handover", json={"code": "000000" if code != "000000" else "111111"})
    assert bad.status_code == 422 and bad.json()["error"]["attempts_left"] == 4
    ok = finder.post(f"/v1/claims/{cid}/handover", json={"code": code})
    assert ok.status_code == 200 and ok.json()["status"] == "returned"
    # Idempotencja: powtórzenie nie psuje stanu.
    assert finder.post(f"/v1/claims/{cid}/handover", json={"code": code}).json()["status"] == "returned"

    # 7. Zgłoszenie zamknięte, znika z wyszukiwania; właściciel dziękuje raz.
    assert client.get(f"/v1/reports/{rid}").status_code == 404
    assert rid not in [i["id"] for i in client.get("/v1/reports", params={"kind": "found"}).json()["items"]]
    assert owner.post(f"/v1/claims/{cid}/thanks").status_code == 200
    assert owner.post(f"/v1/claims/{cid}/thanks").status_code == 200
    assert finder.get("/v1/me").json()["stats"]["hearts_received"] == 1
    assert finder.post(f"/v1/claims/{cid}/thanks").status_code == 403  # znalazca nie dziękuje sam sobie


def test_handover_without_code_requires_both_confirmations(client, guest_factory):
    finder, owner = guest_factory(), guest_factory()
    rid = _publish_found_with_photo(finder)["id"]
    cid = owner.post(f"/v1/reports/{rid}/claims", json={"answer": "K.C. na metce"}).json()["id"]
    finder.post(f"/v1/claims/{cid}/accept")
    r1 = finder.post(f"/v1/claims/{cid}/handover", json={})
    assert r1.json()["status"] == "accepted" and r1.json()["finder_confirmed"]
    assert owner.post(f"/v1/claims/{cid}/thanks").status_code == 409  # brak zakończonego zwrotu
    r2 = owner.post(f"/v1/claims/{cid}/confirm-received")
    assert r2.json()["status"] == "returned"


def test_other_claims_closed_and_lost_report_resolved(client, guest_factory):
    finder, owner, other = guest_factory(), guest_factory(), guest_factory()
    rid = _publish_found_with_photo(finder)["id"]
    now = datetime.now(UTC)
    lost = owner.post(
        "/v1/reports",
        json=report_payload(
            "lost",
            title="Zgubiłem czarną czapkę",
            occurred_from=iso(now - timedelta(hours=7)),
            occurred_to=iso(now - timedelta(hours=5)),
        ),
    )
    assert lost.status_code == 201, lost.text
    c_owner = owner.post(
        f"/v1/reports/{rid}/claims", json={"answer": "inicjały K.C.", "lost_report_id": lost.json()["id"]}
    ).json()["id"]
    c_other = other.post(f"/v1/reports/{rid}/claims", json={"answer": "nie wiem, chyba logo"}).json()["id"]
    # druga akceptacja przy aktywnej pierwszej jest niemożliwa
    assert finder.post(f"/v1/claims/{c_owner}/accept").status_code == 200
    assert finder.post(f"/v1/claims/{c_other}/accept").status_code == 409
    code = owner.get(f"/v1/claims/{c_owner}").json()["handover_code"]
    finder.post(f"/v1/claims/{c_owner}/handover", json={"code": code})
    o = other.get(f"/v1/claims/{c_other}").json()
    assert o["status"] == "closed" and "innej osobie" in o["close_reason"]
    assert owner.get(f"/v1/reports/{lost.json()['id']}").json()["status"] == "resolved"


def test_unaccept_returns_item_to_active(client, guest_factory):
    finder, a, b = guest_factory(), guest_factory(), guest_factory()
    rid = _publish_found_with_photo(finder)["id"]
    ca = a.post(f"/v1/reports/{rid}/claims", json={"answer": "odp A"}).json()["id"]
    cb = b.post(f"/v1/reports/{rid}/claims", json={"answer": "odp B"}).json()["id"]
    finder.post(f"/v1/claims/{ca}/accept")
    # osoba A nie przyszła — znalazca cofa akceptację i wybiera B
    r = finder.post(f"/v1/claims/{ca}/reject", json={"note": "Brak kontaktu"})
    assert r.json()["status"] == "rejected"
    assert client.get(f"/v1/reports/{rid}").json()["status"] == "active"
    assert finder.post(f"/v1/claims/{cb}/accept").json()["status"] == "accepted"
    # A nie może złożyć drugiego roszczenia (ochrona przed zgadywaniem)
    assert a.post(f"/v1/reports/{rid}/claims", json={"answer": "druga próba"}).status_code == 409


def test_edit_and_withdraw_own_report_only(client, guest_factory):
    finder, other = guest_factory(), guest_factory()
    rid = _publish_found_with_photo(finder)["id"]
    assert other.patch(f"/v1/reports/{rid}", json={"title": "Przejęte"}).status_code == 404
    assert other.delete(f"/v1/reports/{rid}").status_code == 404
    e = finder.patch(
        f"/v1/reports/{rid}",
        json={
            "title": "Czarna czapka z pomponem",
            "location": {"lat": 50.0617, "lon": 19.9373, "uncertainty_m": 600, "source": "map"},
        },
    )
    assert e.status_code == 200, e.text
    assert e.json()["title"] == "Czarna czapka z pomponem"
    assert e.json()["area"]["radius_m"] == 750
    photo_url = e.json()["photos"][0]["url"]
    assert finder.delete(f"/v1/reports/{rid}").status_code == 204
    assert client.get(f"/v1/reports/{rid}").status_code == 404
    assert client.get(photo_url).status_code == 404


def test_session_recovery_and_loss(client, guest_factory):
    g = guest_factory()
    rid = g.post("/v1/reports", json=report_payload()).json()["id"]
    code = g.post("/v1/me/recovery-code").json()["code"]
    # Utrata telefonu: nowa instalacja odzyskuje dostęp kodem, stara sesja wygasa.
    rec = client.post("/v1/sessions/recover", json={"code": code.lower().replace("-", " ")})
    assert rec.status_code == 201, rec.text
    new_h = {"Authorization": f"Bearer {rec.json()['token']}"}
    assert client.get(f"/v1/reports/{rid}", headers=new_h).json()["is_mine"] is True
    assert g.get("/v1/me").status_code == 401
    # stary kod jest jednorazowy
    assert client.post("/v1/sessions/recover", json={"code": code}).status_code == 404
    assert rec.json()["new_recovery_code"] != code
    # Bez kodu: utrata sesji = brak dostępu (uczciwie komunikowane w aplikacji)
    assert client.get("/v1/me", headers={"Authorization": "Bearer fnd_nieistniejacy_token_123456"}).status_code == 401


def test_delete_my_data(client, guest_factory):
    finder, owner = guest_factory(), guest_factory()
    rep = _publish_found_with_photo(finder)
    cid = owner.post(f"/v1/reports/{rep['id']}/claims", json={"answer": "K.C."}).json()["id"]
    finder.post(f"/v1/claims/{cid}/accept")
    assert owner.delete("/v1/me").status_code == 204
    # rezerwacja zwolniona, sprawa usunięta
    assert client.get(f"/v1/reports/{rep['id']}").json()["status"] == "active"
    assert finder.get(f"/v1/claims/{cid}").status_code == 404
    assert finder.delete("/v1/me").status_code == 204
    assert client.get(f"/v1/reports/{rep['id']}").status_code == 404
    assert client.get(rep["photos"][0]["url"]).status_code == 404


def test_public_payload_has_only_allowed_fields(client, guest_factory):
    g = guest_factory()
    rid = _publish_found_with_photo(g)["id"]
    pub = client.get(f"/v1/reports/{rid}").json()
    allowed = {
        "id",
        "kind",
        "status",
        "category",
        "category_label",
        "title",
        "description",
        "attributes",
        "colors",
        "occurred_from",
        "occurred_to",
        "published_at",
        "updated_at",
        "area",
        "holding",
        "holding_note",
        "photos",
        "ai_indexed",
        "distance_m",
        "match",
        "is_mine",
    }
    assert set(pub) == allowed
    assert set(pub["area"]) == {"lat", "lon", "radius_m", "label", "precision"}
    dumped = json.dumps(client.get("/v1/reports").json())
    for forbidden_text in ("owner_id", "exact_lat", "secret_details", "claim_question", "inicjały", "Co jest wyszyte"):
        assert forbidden_text not in dumped
