"""Funkcje AI na prawdziwym modelu (jeśli pobrany) oraz zachowanie przy jego braku."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import ai
from tests.conftest import jpeg_bytes, report_payload

MODEL = Path(__file__).resolve().parents[2] / "models" / "clip-vit-b32" / "onnx" / "vision_model.onnx"
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="model CLIP nie jest pobrany (scripts/download_model.py)")


@needs_model
def test_upload_returns_suggestion_and_photo_search(client, guest_factory):
    g, searcher = guest_factory(), guest_factory()
    up = g.post("/v1/photos", files={"file": ("x.jpg", jpeg_bytes((10, 10, 10), pattern=3), "image/jpeg")})
    assert up.status_code == 201
    body = up.json()
    assert body["ai_status"] == "ready"
    sug = body["suggestion"]
    assert sug["category"] and sug["colors"] and "confidence" in sug
    assert not any(isinstance(v, float) for v in sug.values())  # brak „procentów pewności”
    rid = g.post("/v1/reports", json=report_payload(photo_ids=[body["id"]])).json()["id"]
    other = g.post("/v1/photos", files={"file": ("y.jpg", jpeg_bytes((200, 180, 40)), "image/jpeg")}).json()["id"]
    g.post("/v1/reports", json=report_payload(title="Żółta czapka", colors=["yellow"], photo_ids=[other]))
    # to samo zdjęcie (test techniczny) musi być na pierwszym miejscu
    res = searcher.post(
        "/v1/search/by-photo",
        files={"file": ("q.jpg", jpeg_bytes((10, 10, 10), pattern=3), "image/jpeg")},
        data={"kind": "found"},
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["items"][0]["id"] == rid
    assert out["items"][0]["match"]["visual"] == "distinct"
    assert out["no_convincing_match"] is False
    assert "nie zostało zapisane" in out["notice"]


@needs_model
def test_photo_search_reports_no_convincing_match(client, guest_factory):
    g, searcher = guest_factory(), guest_factory()
    pid = g.post("/v1/photos", files={"file": ("x.jpg", jpeg_bytes((240, 240, 240)), "image/jpeg")}).json()["id"]
    g.post("/v1/reports", json=report_payload(photo_ids=[pid]))
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 400), (30, 120, 30))
    d = ImageDraw.Draw(img)
    for i in range(0, 400, 20):
        d.line([(i, 0), (400 - i, 400)], fill=(200, 50, 200), width=3)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    out = searcher.post("/v1/search/by-photo", files={"file": ("q.jpg", buf.getvalue(), "image/jpeg")}).json()
    assert out["no_convincing_match"] is True
    assert "nie wyróżnia się" in out["notice"]


def test_ai_unavailable_does_not_block(client, guest_factory, monkeypatch):
    g = guest_factory()
    eng = ai.engine()
    monkeypatch.setattr(eng, "status", "missing_model")
    monkeypatch.setattr(eng, "load", lambda: False)
    up = g.post("/v1/photos", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")})
    assert up.status_code == 201 and up.json()["ai_status"] == "unavailable" and up.json()["suggestion"] is None
    r = g.post("/v1/reports", json=report_payload(photo_ids=[up.json()["id"]]))
    assert r.status_code == 201  # publikacja działa bez AI
    assert r.json()["photo_status"][0]["embedding_status"] == "pending"
    s = g.post("/v1/search/by-photo", files={"file": ("q.jpg", jpeg_bytes(), "image/jpeg")})
    assert s.status_code == 503 and s.json()["error"]["code"] == "ai_unavailable"
    assert client.get("/v1/reports").status_code == 200  # wyszukiwanie filtrami działa


@needs_model
def test_background_indexer_and_hidden_reports_not_indexed(client, guest_factory, monkeypatch):
    from sqlalchemy import select

    from app.db import session_factory
    from app.models import Photo
    from app.services import jobs

    g = guest_factory()
    eng = ai.engine()
    real_load = eng.load
    monkeypatch.setattr(eng, "status", "missing_model")
    monkeypatch.setattr(eng, "load", lambda: False)
    pid = g.post("/v1/photos", files={"file": ("x.jpg", jpeg_bytes(), "image/jpeg")}).json()["id"]
    g.post("/v1/reports", json=report_payload(photo_ids=[pid]))
    monkeypatch.setattr(eng, "load", real_load)
    monkeypatch.setattr(eng, "status", "not_loaded")
    assert jobs.index_pending() == 1
    with session_factory()() as db:
        p = db.scalar(select(Photo).where(Photo.id == pid))
        assert p.embedding_status == "ready" and p.embedding_model == eng.model_version


def test_preprocess_shape():
    from PIL import Image

    x = ai.preprocess(Image.new("RGB", (300, 500)))
    assert x.shape == (1, 3, 224, 224)
