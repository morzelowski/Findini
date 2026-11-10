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
import re
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
    ap.add_argument("--nationwide", action="store_true", help="rozłóż dane wokół miast całej Polski")
    ap.add_argument("--embedding-file", type=Path)
    ap.add_argument("--embedding-model")
    ap.add_argument("--model-dir", type=Path, default=ROOT / "models" / "clip-vit-b16")
    args = ap.parse_args()
    rnd = random.Random(42)
    np_rnd = np.random.default_rng(42)

    admin_url = args.db.rsplit("/", 1)[0] + "/findini"
    name = args.db.rsplit("/", 1)[1]
    if not re.fullmatch(r"findini_load(?:_[a-z0-9_]+)?", name):
        raise SystemExit("Skrypt resetuje tylko bazę testową o nazwie findini_load lub findini_load_…")
    eng = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        c.execute(text(f"CREATE DATABASE {name}"))
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.attributes["database_url"] = args.db
    command.upgrade(cfg, "head")

    # Nigdy nie oznaczamy wektorów B/32 jako B/16. Domyślnie liczymy prawdziwe
    # embeddingi zdjęć demonstracyjnych modelem używanym w nowej instalacji.
    if args.embedding_file:
        if not args.embedding_model:
            raise SystemExit("Podaj --embedding-model zgodny z plikiem wektorów.")
        base = np.load(args.embedding_file, allow_pickle=False)
        model_id = args.embedding_model
        if base.ndim != 2 or base.shape[1] != 512 or not len(base) or not np.isfinite(base).all():
            raise SystemExit("Plik musi zawierać skończone wektory N×512.")
    else:
        from PIL import Image

        from app.services.ai import AiEngine

        model = AiEngine(model_dir=args.model_dir)
        if not model.load():
            raise SystemExit("Pobierz model: python backend/scripts/download_model.py")
        base = np.stack(
            [
                model._embed_sync(Image.open(p).convert("RGB"))
                for p in sorted((ROOT / "backend" / "scripts" / "demo_photos").glob("*.jpg"))
            ]
        )
        model_id = model.model_version
    db = create_engine(args.db)
    now = datetime.now(UTC)
    locations = LANDMARKS
    if args.nationwide:
        from app.domain.places import popular_places

        locations = [(p["lat"], p["lon"]) for p in popular_places()]
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
            lm = rnd.choice(locations)
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
                v = base[rnd.randrange(len(base))] + np_rnd.normal(0, 0.03, 512)
                v = v / np.linalg.norm(v)
                photos.append(
                    {
                        "id": uuid.uuid4(),
                        "owner": rows[-1]["owner"],
                        "rid": rid,
                        "key": args.photo_key or "00/00000000000000000000000000000000.jpg",
                        "tkey": (args.photo_key or "00/00000000000000000000000000000000.jpg").replace(".jpg", "_t.jpg"),
                        "emb": str([round(float(x), 6) for x in v]),
                        "model": model_id,
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
              CAST(:emb AS vector), :model, 'ready')
        """),
            photos,
        )
        c.execute(text("ANALYZE"))
    print(f"Baza {name}: {len(rows)} zgłoszeń, {len(photos)} zdjęć z wektorami, {len(guests)} gości.")


if __name__ == "__main__":
    main()
