"""Testy integracyjne na prawdziwym PostgreSQL (PostGIS + pgvector) z docker compose.

Baza testowa `findini_test` jest tworzona od zera przy każdym uruchomieniu i migrowana Alembikiem.
Wymaga działającej usługi `db` (docker compose up -d db) — port 5433 na localhost.
"""

from __future__ import annotations

import io
import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get(
    "TEST_DB_ADMIN_URL", "postgresql+psycopg://findini:findini-dev-password@localhost:5433/findini"
)
TEST_DB = "findini_test"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"

os.environ["FINDINI_ENV"] = "test"
os.environ["FINDINI_DATABASE_URL"] = TEST_URL
os.environ["FINDINI_STORAGE_DIR"] = tempfile.mkdtemp(prefix="findini-photos-")
os.environ["FINDINI_AI_MODEL_DIR"] = str(ROOT / "models" / "clip-vit-b16")
os.environ["FINDINI_BACKGROUND_JOBS"] = "false"
os.environ["FINDINI_ADMIN_TOKEN"] = "test-admin-token-0123456789abcdef"
os.environ["FINDINI_SERVER_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
os.environ.setdefault("FINDINI_RATE_LIMITS_ENABLED", "true")


def _recreate_db() -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {TEST_DB}"))
    eng.dispose()
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.attributes["database_url"] = TEST_URL
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    _recreate_db()
    yield


@pytest.fixture(autouse=True)
def clean_tables(database: None) -> Iterator[None]:
    from sqlalchemy import text

    from app.db import get_engine

    with get_engine().begin() as c:
        c.execute(
            text(
                "TRUNCATE rate_buckets, audit_events, abuse_reports, blocks, thanks, claim_reads, messages, "
                "photos, claims, report_private, reports, sessions, guests CASCADE"
            )
        )
    yield


@pytest.fixture(scope="session")
def client() -> Iterator[Any]:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


class Guest:
    def __init__(self, client: Any, ip: str = "testclient") -> None:
        self.client = client
        r = client.post("/v1/sessions")
        assert r.status_code == 201, r.text
        self.token = r.json()["token"]
        self.id = r.json()["guest"]["id"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def get(self, url: str, **kw: Any) -> Any:
        return self.client.get(url, headers=self.h, **kw)

    def post(self, url: str, **kw: Any) -> Any:
        return self.client.post(url, headers=self.h, **kw)

    def patch(self, url: str, **kw: Any) -> Any:
        return self.client.patch(url, headers=self.h, **kw)

    def delete(self, url: str, **kw: Any) -> Any:
        return self.client.delete(url, headers=self.h, **kw)


@pytest.fixture
def guest_factory(client: Any) -> Any:
    def make() -> Guest:
        return Guest(client)

    return make


def jpeg_bytes(
    color: tuple[int, int, int] = (20, 20, 20),
    size: tuple[int, int] = (640, 480),
    with_exif_gps: bool = False,
    pattern: int = 0,
) -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    for i in range(pattern):
        d.rectangle([20 + i * 30, 40, 40 + i * 30, 200], fill=(255 - color[0], 120, 60))
    buf = io.BytesIO()
    if with_exif_gps:
        exif = Image.Exif()
        exif[0x010F] = "SecretCam"  # Make
        exif[0x8825] = {1: "N", 2: (50.0, 3.0, 41.0), 3: "E", 4: (19.0, 56.0, 12.0)}  # GPSInfo
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def report_payload(kind: str = "found", **over: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    base = {
        "kind": kind,
        "category": "clothing",
        "title": "Czarna czapka zimowa",
        "description": "Wełniana czapka z pomponem, leżała na ławce.",
        "attributes": {"subtype": "czapka", "material": "wełna"},
        "colors": ["black"],
        "occurred_from": iso(now - timedelta(hours=5)),
        "occurred_to": iso(now - timedelta(hours=4)),
        "location": {"lat": 50.06571, "lon": 19.91893, "accuracy_m": 12, "uncertainty_m": 0, "source": "gps"},
        "area_label": "okolice: Kampus AGH",
    }
    if kind == "found":
        base |= {
            "holding": "with_finder",
            "secret_details": "Na metce wyszyte inicjały K.C. i dziura na lewym boku",
            "claim_question": "Co jest wyszyte na metce?",
        }
    base.update(over)
    return base
