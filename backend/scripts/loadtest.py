"""Prosty test obciążenia: N równoległych sesji gościa z mieszanym profilem żądań.

Każda wirtualna sesja: tworzy sesję gościa, potem w pętli losuje operację wg wag (wyszukiwanie,
mapa, szczegóły, zdjęcia, asystent, „moje”, dopasowania, publikacja, wyszukiwanie zdjęciem).
Wynik: liczba żądań, przepustowość, p50/p95/p99 i błędy na endpoint — zapis do JSON.

Użycie:
    python -m scripts.loadtest --base http://localhost:8081 --users 50 --duration 120 --out ../docs/loadtest_wyniki.json
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import random
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

WEIGHTS = [
    ("search", 35),
    ("areas", 12),
    ("detail", 15),
    ("photo_thumb", 10),
    ("parse", 5),
    ("me", 6),
    ("matches", 6),
    ("create", 5),
    ("photo_search", 2),
]
CATS = ["electronics", "keys", "clothing", "bags", "wallets", "jewelry", "accessories"]
COLORS = ["black", "white", "gray", "blue", "navy", "red", "green", "brown"]
WORDS = ["czapka", "plecak", "klucze", "telefon", "portfel", "zegarek", "okulary", "słuchawki", "torebka"]
PHRASES = [
    "zgubiłem czarną czapkę wczoraj przy AGH",
    "znalazłem klucze na Kazimierzu",
    "srebrny laptop Dell 3 dni temu",
    "niebieski plecak dworzec",
]


def _jpeg() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 480), (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
    d = ImageDraw.Draw(img)
    for _ in range(8):
        x, y = random.randint(0, 600), random.randint(0, 440)
        d.ellipse([x, y, x + 60, y + 60], fill=(random.randint(0, 255), 80, 120))
    b = io.BytesIO()
    img.save(b, "JPEG")
    return b.getvalue()


class Stats:
    def __init__(self) -> None:
        self.lat: dict[str, list[float]] = defaultdict(list)
        self.err: dict[str, int] = defaultdict(int)
        self.codes: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    def add(self, op: str, ms: float, code: int) -> None:
        self.lat[op].append(ms)
        self.codes[op][code] += 1
        if code >= 500 or code == 0:
            self.err[op] += 1


async def user(
    client: httpx.AsyncClient,
    st: Stats,
    deadline: float,
    ids: list[str],
    photo_ids: list[str],
    jpeg: bytes,
    think: float = 1.0,
) -> None:
    r = await client.post("/v1/sessions")
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    own: list[str] = []
    ops, weights = zip(*WEIGHTS, strict=True)
    while time.monotonic() < deadline:
        op = random.choices(ops, weights)[0]
        t0 = time.perf_counter()
        code = 0
        try:
            if op == "search":
                p: dict[str, Any] = {"limit": 20}
                if random.random() < 0.7:
                    p |= {
                        "lat": 50.06 + random.uniform(-0.03, 0.03),
                        "lon": 19.94 + random.uniform(-0.05, 0.05),
                        "radius_m": random.choice([1000, 2000, 5000]),
                    }
                if random.random() < 0.5:
                    p["category"] = random.choice(CATS)
                if random.random() < 0.3:
                    p["colors"] = random.choice(COLORS)
                if random.random() < 0.3:
                    p["q"] = random.choice(WORDS)
                if random.random() < 0.3:
                    p["date_from"] = (datetime.now(UTC) - timedelta(days=random.choice([1, 7, 30]))).isoformat()
                resp = await client.get("/v1/reports", params=p)
                code = resp.status_code
                if code == 200 and resp.json().get("next_cursor") and random.random() < 0.3:
                    p["cursor"] = resp.json()["next_cursor"]
                    code = (await client.get("/v1/reports", params=p)).status_code
            elif op == "areas":
                lat, lon = 50.06 + random.uniform(-0.02, 0.02), 19.94 + random.uniform(-0.04, 0.04)
                bbox = f"{lon - 0.04},{lat - 0.025},{lon + 0.04},{lat + 0.025}"
                code = (await client.get("/v1/reports/areas", params={"bbox": bbox})).status_code
            elif op == "detail":
                code = (await client.get(f"/v1/reports/{random.choice(ids)}")).status_code
            elif op == "photo_thumb":
                code = (
                    await client.get(f"/v1/photos/{random.choice(photo_ids)}", params={"size": "thumb"})
                ).status_code
            elif op == "parse":
                code = (await client.post("/v1/search/parse", json={"text": random.choice(PHRASES)})).status_code
            elif op == "me":
                code = (await client.get("/v1/me/cases", headers=h)).status_code
            elif op == "matches":
                if own:
                    code = (await client.get(f"/v1/reports/{random.choice(own)}/matches", headers=h)).status_code
                else:
                    code = (await client.get("/v1/me", headers=h)).status_code
            elif op == "create":
                now = datetime.now(UTC)
                body = {
                    "kind": random.choice(["lost", "found"]),
                    "category": "clothing",
                    "title": "Czapka testowa",
                    "description": "Test obciążenia",
                    "attributes": {"subtype": "czapka"},
                    "colors": [random.choice(COLORS)],
                    "occurred_from": (now - timedelta(hours=3)).isoformat(),
                    "occurred_to": now.isoformat(),
                    "location": {
                        "lat": 50.06 + random.uniform(-0.02, 0.02),
                        "lon": 19.94 + random.uniform(-0.03, 0.03),
                        "source": "map",
                    },
                }
                resp = await client.post("/v1/reports", json=body, headers=h)
                code = resp.status_code
                if code == 201:
                    own.append(resp.json()["id"])
            elif op == "photo_search":
                resp = await client.post(
                    "/v1/search/by-photo",
                    headers=h,
                    files={"file": ("q.jpg", jpeg, "image/jpeg")},
                    data={"kind": "found"},
                )
                code = resp.status_code
        except httpx.HTTPError:
            code = 0
        st.add(op, (time.perf_counter() - t0) * 1000, code)
        if think > 0:
            await asyncio.sleep(random.uniform(0.2 * think, think))  # „czas myślenia” użytkownika


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(p / 100 * (len(xs) - 1))))
    return round(xs[k], 1)


async def run(base: str, users: int, duration: int, out: str | None, think: float = 1.0) -> None:
    limits = httpx.Limits(max_connections=users + 10, max_keepalive_connections=users + 10)
    async with httpx.AsyncClient(base_url=base, timeout=30, limits=limits) as client:
        res = (await client.get("/v1/reports", params={"limit": 50})).json()["items"]
        ids = [r["id"] for r in res]
        cursor = None
        for _ in range(10):
            p = {"limit": 50, "sort": "newest"} | ({"cursor": cursor} if cursor else {})
            page = (await client.get("/v1/reports", params=p)).json()
            ids += [r["id"] for r in page["items"]]
            cursor = page.get("next_cursor")
        photo_ids = [ph["id"] for r in res for ph in r["photos"]] or ["00000000-0000-0000-0000-000000000000"]
        st = Stats()
        jpeg = _jpeg()
        t0 = time.monotonic()
        deadline = t0 + duration
        await asyncio.gather(*(user(client, st, deadline, ids, photo_ids, jpeg, think) for _ in range(users)))
        elapsed = time.monotonic() - t0
    total = sum(len(v) for v in st.lat.values())
    allv = [x for v in st.lat.values() for x in v]
    report = {
        "users": users,
        "think_max_s": think,
        "duration_s": round(elapsed, 1),
        "requests": total,
        "rps": round(total / elapsed, 1),
        "overall": {
            "p50_ms": pct(allv, 50),
            "p95_ms": pct(allv, 95),
            "p99_ms": pct(allv, 99),
            "errors_5xx_or_network": sum(st.err.values()),
        },
        "per_op": {
            op: {
                "n": len(v),
                "p50_ms": pct(v, 50),
                "p95_ms": pct(v, 95),
                "p99_ms": pct(v, 99),
                "max_ms": round(max(v), 1),
                "mean_ms": round(statistics.mean(v), 1),
                "errors": st.err.get(op, 0),
                "codes": dict(st.codes[op]),
            }
            for op, v in sorted(st.lat.items())
        },
    }
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if out:
        with open(out, "w") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8081")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--duration", type=int, default=120)
    ap.add_argument("--out")
    ap.add_argument("--think", type=float, default=1.0, help="maks. czas myślenia (s); 0 = bez przerw (stres)")
    a = ap.parse_args()
    asyncio.run(run(a.base, a.users, a.duration, a.out, a.think))
