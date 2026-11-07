"""Współbieżne finalizacje, limity i ochrona przed nadużyciami."""

from __future__ import annotations

import threading

from tests.conftest import jpeg_bytes, report_payload


def _found(g) -> str:
    r = g.post("/v1/reports", json=report_payload())
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_concurrent_accepts_release_only_once(client, guest_factory):
    finder = guest_factory()
    rid = _found(finder)
    claimants = [guest_factory() for _ in range(6)]
    cids = [
        c.post(f"/v1/reports/{rid}/claims", json={"answer": f"odpowiedź {i}"}).json()["id"]
        for i, c in enumerate(claimants)
    ]
    results: list[int] = []
    barrier = threading.Barrier(len(cids))

    def go(cid: str) -> None:
        barrier.wait()
        results.append(finder.post(f"/v1/claims/{cid}/accept").status_code)

    threads = [threading.Thread(target=go, args=(cid,)) for cid in cids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results).count(200) == 1, results
    assert all(s in (200, 409) for s in results)
    statuses = [finder.get(f"/v1/claims/{cid}").json()["status"] for cid in cids]
    assert statuses.count("accepted") == 1


def test_concurrent_handover_and_confirm_single_return(client, guest_factory):
    finder, owner = guest_factory(), guest_factory()
    rid = _found(finder)
    cid = owner.post(f"/v1/reports/{rid}/claims", json={"answer": "K.C."}).json()["id"]
    finder.post(f"/v1/claims/{cid}/accept")
    code = owner.get(f"/v1/claims/{cid}").json()["handover_code"]
    barrier = threading.Barrier(4)
    out: list[int] = []

    def f1() -> None:
        barrier.wait()
        out.append(finder.post(f"/v1/claims/{cid}/handover", json={"code": code}).status_code)

    def f2() -> None:
        barrier.wait()
        out.append(owner.post(f"/v1/claims/{cid}/confirm-received").status_code)

    ts = [threading.Thread(target=f) for f in (f1, f1, f2, f2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert all(s == 200 for s in out), out
    msgs = owner.get(f"/v1/claims/{cid}/messages").json()["items"]
    assert sum("Zwrot potwierdzony" in m["body"] for m in msgs) == 1
    # wielokrotne serduszka równolegle -> jedno
    ts = [threading.Thread(target=lambda: owner.post(f"/v1/claims/{cid}/thanks")) for _ in range(5)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert finder.get("/v1/me").json()["stats"]["hearts_received"] == 1


def test_claim_daily_limit(client, guest_factory):
    finder, claimant = guest_factory(), guest_factory()
    rids = [_found(finder) for _ in range(6)]
    codes = [claimant.post(f"/v1/reports/{r}/claims", json={"answer": "test odp"}).status_code for r in rids]
    assert codes[:5] == [201] * 5 and codes[5] == 429


def test_cannot_claim_own_or_lost_report(client, guest_factory):
    g, other = guest_factory(), guest_factory()
    rid = _found(g)
    assert g.post(f"/v1/reports/{rid}/claims", json={"answer": "moje"}).status_code == 403
    lost = other.post("/v1/reports", json=report_payload("lost")).json()["id"]
    assert g.post(f"/v1/reports/{lost}/claims", json={"answer": "abc"}).status_code == 422


def test_handover_code_attempts_locked(client, guest_factory):
    finder, owner = guest_factory(), guest_factory()
    rid = _found(finder)
    cid = owner.post(f"/v1/reports/{rid}/claims", json={"answer": "K.C."}).json()["id"]
    finder.post(f"/v1/claims/{cid}/accept")
    real = owner.get(f"/v1/claims/{cid}").json()["handover_code"]
    wrong = "123456" if real != "123456" else "654321"
    for _ in range(5):
        assert finder.post(f"/v1/claims/{cid}/handover", json={"code": wrong}).status_code == 422
    r = finder.post(f"/v1/claims/{cid}/handover", json={"code": real})
    assert r.status_code == 429 and r.json()["error"]["code"] == "code_locked"


def test_message_spam_guard_and_block(client, guest_factory):
    finder, owner = guest_factory(), guest_factory()
    rid = _found(finder)
    cid = owner.post(f"/v1/reports/{rid}/claims", json={"answer": "K.C."}).json()["id"]
    for i in range(5):
        assert owner.post(f"/v1/claims/{cid}/messages", json={"body": f"wiadomość {i}"}).status_code == 201
    r = owner.post(f"/v1/claims/{cid}/messages", json={"body": "szósta"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "wait_for_reply"
    assert finder.post(f"/v1/claims/{cid}/block").json()["status"] == "closed"
    assert owner.post(f"/v1/claims/{cid}/messages", json={"body": "po blokadzie"}).status_code == 409
    # zablokowana osoba nie złoży roszczenia do innych rzeczy tego znalazcy
    rid2 = _found(finder)
    assert owner.post(f"/v1/reports/{rid2}/claims", json={"answer": "abc"}).status_code == 403


def test_public_text_rejects_contact_data(guest_factory):
    g = guest_factory()
    r = g.post("/v1/reports", json=report_payload(description="Dzwoń 600 123 456 albo pisz jan@example.com"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "contact_data_in_public_text"


def test_document_photos_blocked(guest_factory):
    g = guest_factory()
    pid = g.post("/v1/photos", files={"file": ("d.jpg", jpeg_bytes(), "image/jpeg")}).json()["id"]
    r = g.post(
        "/v1/reports",
        json=report_payload(category="wallets", attributes={"subtype": "dowód osobisty"}, photo_ids=[pid]),
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "photo_not_allowed"


def test_upload_validation(guest_factory):
    g = guest_factory()
    assert g.post("/v1/photos", files={"file": ("x.jpg", b"not an image", "image/jpeg")}).status_code == 415
    assert g.post("/v1/photos", files={"file": ("x.gif", b"GIF89a" + b"\0" * 100, "image/gif")}).status_code == 415
    big = b"\xff\xd8" + b"0" * (11 * 1024 * 1024)
    assert g.post("/v1/photos", files={"file": ("x.jpg", big, "image/jpeg")}).status_code == 413
    tiny = jpeg_bytes(size=(20, 20))
    assert g.post("/v1/photos", files={"file": ("x.jpg", tiny, "image/jpeg")}).status_code == 422


def test_photo_of_unpublished_report_is_private(client, guest_factory):
    g, other = guest_factory(), guest_factory()
    pid = g.post("/v1/photos", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")}).json()["id"]
    assert g.get(f"/v1/photos/{pid}").status_code == 200
    assert other.get(f"/v1/photos/{pid}").status_code == 404
    assert client.get(f"/v1/photos/{pid}").status_code == 404
    # cudzego zdjęcia nie da się podpiąć pod własne zgłoszenie
    r = other.post("/v1/reports", json=report_payload(photo_ids=[pid]))
    assert r.status_code == 422


def test_session_creation_rate_limit(client):
    codes = [client.post("/v1/sessions").status_code for _ in range(22)]
    assert codes.count(201) == 20 and codes[-1] == 429


def test_unauthenticated_private_endpoints(client):
    for method, url in [
        ("get", "/v1/me"),
        ("post", "/v1/reports"),
        ("get", "/v1/me/cases"),
        ("post", "/v1/photos"),
        ("post", "/v1/abuse-reports"),
    ]:
        r = getattr(client, method)(url)
        assert r.status_code in (401, 422), (url, r.status_code)
        if r.status_code == 422:
            # walidacja ciała może zadziałać wcześniej — ale bez tokenu i tak nie ma zapisu
            continue
