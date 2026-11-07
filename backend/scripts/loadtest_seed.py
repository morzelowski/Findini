"""Generuje bazę do testu obciążenia: 10 000 zgłoszeń (Kraków), ~1000 gości, ~30% ze zdjęciem i wektorem.

Dane są SYNTETYCZNE i trafiają do osobnej bazy (domyślnie findini_load) — nie mieszają się z demo.
Wektory zdjęć: prawdziwe embeddingi CLIP zdjęć z eksperymentu (ABO) + szum, znormalizowane —
koszt zapytań wektorowych jest więc realistyczny.

Użycie (z katalogu backend, baza w docker compose na porcie 5433):
    python -m scripts.loadtest_seed --db postgresql+psycopg://findini:findini-dev-password@localhost:5433/findini_load
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine, text

from app.domain.categories import CATEGORIES, COLOR_KEYS
from app.geo import public_area

ROOT = Path(__file__).resolve().parents[2]
LANDMARKS = [
    (50.0617, 19.9373),
    (50.0675, 19.9450),
    (50.0656, 19.9189),
    (50.0287, 19.9065),
    (50.0712, 19.9435),
    (50.0688, 19.9548),
    (50.0517, 19.9447),
    (50.0597, 19.9128),
    (50.0722, 20.0378),
    (50.0283, 19.9531),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--reports", type=int, default=10_000)
    ap.add_argument("--guests", type=int, default=1_000)
    ap.add_argument("--photo-key", default="", help="istniejący storage_key zdjęcia (do testu GET /photos)")
    args = ap.parse_args()
    rnd = random.Random(42)
    np_rnd = np.random.default_rng(42)

    admin_url = args.db.rsplit("/", 1)[0] + "/findini"
    name = args.db.rsplit("/", 1)[1]
    eng = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {name}"))
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.attributes["database_url"] = args.db
    command.upgrade(cfg, "head")

    # embeddingi bazowe z eksperymentu (jeśli dostępne) — inaczej losowe
    base = None
    emb_file = ROOT / "data" / "abo" / "embeddings_fp32.npy"
    if emb_file.exists():
        base = np.load(emb_file)
    db = create_engine(args.db)
    now = datetime.now(UTC)
    guests = [uuid.uuid4() for _ in range(args.guests)]
    with db.begin() as c:
        c.execute(text("INSERT INTO guests(id, alias) VALUES (:id, 'Loadtest')"), [{"id": g} for g in guests])
        rows, priv, photos = [], [], []
        for _ in range(args.reports):
            cat = rnd.choice(CATEGORIES)
            sub_attr = next((a for a in cat.attrs if a.key == "subtype"), None)
            attrs = {}
            if sub_attr and sub_attr.options:
                attrs["subtype"] = rnd.choice(sub_attr.options)
            lm = rnd.choice(LANDMARKS)
            lat = lm[0] + np_rnd.normal(0, 0.012)
            lon = lm[1] + np_rnd.normal(0, 0.018)
            area = public_area(lat, lon, rnd.choice([0, 0, 0, 300, 800]))
            occurred_to = now - timedelta(hours=rnd.uniform(0.5, 24 * 55))
            occurred_from = occurred_to - timedelta(hours=rnd.uniform(0.2, 30))
            colors = rnd.sample(COLOR_KEYS[:15], rnd.choice([1, 1, 2]))
            rid = uuid.uuid4()
            kind = "found" if rnd.random() < 0.6 else "lost"
            title = f"{attrs.get('subtype', cat.label).capitalize()} ({', '.join(colors)})"
            rows.append(
                {
                    "id": rid,
                    "kind": kind,
                    "owner": rnd.choice(guests),
                    "cat": cat.key,
                    "title": title[:80],
                    "desc": "Syntetyczne zgłoszenie testu obciążenia.",
                    "attrs": json.dumps(attrs),
                    "colors": colors,
                    "f": occurred_from,
                    "t": occurred_to,
                    "cell": area.cell_id,
                    "plat": area.lat,
                    "plon": area.lon,
                    "rad": area.radius_m,
                    "pub": occurred_to + timedelta(minutes=rnd.randint(5, 600)),
                    "exp": now + timedelta(days=30),
                    "st": f"{title} {cat.label} {' '.join(attrs.values())}",
                    "holding": "with_finder" if kind == "found" else None,
                }
            )
            priv.append({"id": rid, "lat": lat, "lon": lon})
            if rnd.random() < 0.3:
                if base is not None:
                    v = base[rnd.randrange(len(base))] + np_rnd.normal(0, 0.03, 512)
                else:
                    v = np_rnd.normal(0, 1, 512)
                v = v / np.linalg.norm(v)
                photos.append(
                    {
                        "id": uuid.uuid4(),
                        "owner": rows[-1]["owner"],
                        "rid": rid,
                        "key": args.photo_key or "00/00000000000000000000000000000000.jpg",
                        "tkey": (args.photo_key or "00/00000000000000000000000000000000.jpg").replace(".jpg", "_t.jpg"),
                        "emb": str([round(float(x), 6) for x in v]),
                    }
                )
        c.execute(
            text("""
            INSERT INTO reports(id, kind, status, owner_id, category, title, description, attributes, colors,
              occurred_from, occurred_to, cell_id, public_lat, public_lon, area_radius_m, holding, search_text,
              published_at, expires_at)
            VALUES (:id, :kind, 'active', :owner, :cat, :title, :desc, CAST(:attrs AS jsonb), :colors, :f, :t, :cell,
              :plat, :plon, :rad, :holding, :st, :pub, :exp)
        """),
            rows,
        )
        c.execute(
            text("""INSERT INTO report_private(report_id, exact_lat, exact_lon, location_source)
                          VALUES (:id, :lat, :lon, 'map')"""),
            priv,
        )
        c.execute(
            text("""
            INSERT INTO photos(id, owner_id, report_id, purpose, storage_key, thumb_key, width, height, bytes, sha256,
              embedding, embedding_model, embedding_status)
            VALUES (:id, :owner, :rid, 'report', :key, :tkey, 800, 600, 50000, 'x',
              CAST(:emb AS vector), 'clip-vit-b32@6b7c523/fp32', 'ready')
        """),
            photos,
        )
        c.execute(text("ANALYZE"))
    print(f"Baza {name}: {len(rows)} zgłoszeń, {len(photos)} zdjęć z wektorami, {len(guests)} gości.")


if __name__ == "__main__":
    main()
