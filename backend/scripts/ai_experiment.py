"""Powtarzalny eksperyment: wyszukiwanie zdjęciem wśród wielu podobnych przedmiotów.

Dane: Amazon Berkeley Objects (ABO), licencja CC BY 4.0
      https://amazon-berkeley-objects.s3.amazonaws.com/index.html
      Collins i in., "ABO: Dataset and Benchmarks for Real-World 3D Object Understanding", CVPR 2022.

Układ (zapytania ODDZIELONE od indeksu — to nie jest test „ta sama kopia zdjęcia”):
- indeks („zdjęcia znalazców”): zdjęcie główne (main_image) każdego produktu z wybranych typów
  + zdjęcia rozpraszające z niezwiązanych kategorii (meble, lampy…);
- zapytania („zdjęcie właściciela”): INNE ujęcie tego samego produktu (other_image);
- negatywy: zapytania o produkty, których NIE ma w indeksie (oczekiwane: „brak przekonujących dopasowań”).

Uwaga: ABO to zdjęcia katalogowe (białe tło, studyjne światło). Zdjęcia rzeczy znalezionych na ulicy
będą trudniejsze — wyniki to górne oszacowanie, nie obietnica skuteczności w terenie.

Użycie:
    python -m scripts.ai_experiment download   # pobiera metadane i ~1,3 tys. małych zdjęć do data/abo
    python -m scripts.ai_experiment run        # liczy metryki dla fp32 i int8, zapisuje docs/eksperyment_ai_wyniki.json
"""

from __future__ import annotations

import csv
import gzip
import json
import random
import ssl
import statistics
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "abo"
IMG_DIR = DATA / "images"
BASE = "https://amazon-berkeley-objects.s3.amazonaws.com"
SEED = 20261107
PER_TYPE = 30  # produktów w indeksie na typ
HELDOUT_PER_TYPE = 10  # produktów tylko jako negatywne zapytania
DISTRACTOR_PER_TYPE = 25

# typ ABO -> (kategoria Findini, rodzaj)
TYPES: dict[str, tuple[str, str]] = {
    "HAT": ("clothing", "czapka"),
    "BACKPACK": ("bags", "plecak"),
    "HANDBAG": ("bags", "torebka"),
    "SUITCASE": ("bags", "walizka"),
    "WALLET": ("wallets", "portfel"),
    "CELLULAR_PHONE_CASE": ("electronics", "telefon"),
    "HEADPHONES": ("electronics", "słuchawki"),
    "CHARGING_ADAPTER": ("electronics", "ładowarka / powerbank"),
    "FINERING": ("jewelry", "pierścionek"),
    "FINENECKLACEBRACELETANKLET": ("jewelry", "naszyjnik"),
    "WATCH": ("jewelry", "zegarek"),
    "EYEWEAR": ("accessories", "okulary"),
    "UMBRELLA": ("accessories", "parasol"),
    "DRINKING_CUP": ("accessories", "bidon / kubek"),
}
DISTRACTORS = ["CHAIR", "LAMP", "RUG", "PILLOW"]

COLOR_WORDS = {
    "black": "black",
    "white": "white",
    "grey": "gray",
    "gray": "gray",
    "silver": "silver",
    "gold": "gold",
    "brown": "brown",
    "beige": "beige",
    "tan": "beige",
    "khaki": "beige",
    "camel": "beige",
    "red": "red",
    "burgundy": "red",
    "pink": "pink",
    "rose": "pink",
    "orange": "orange",
    "yellow": "yellow",
    "green": "green",
    "olive": "green",
    "blue": "blue",
    "navy": "navy",
    "purple": "purple",
    "violet": "purple",
}


def _ctx() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "findini-experiment/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
                dest.write_bytes(r.read())
            return
        except (TimeoutError, OSError):
            if attempt == 3:
                raise
            time.sleep(1 + attempt * 2)


def _en_color(item: dict) -> list[str]:
    out: list[str] = []
    for c in item.get("color", []):
        if not str(c.get("language_tag", "")).startswith("en"):
            continue
        for w in str(c.get("value", "")).lower().replace("/", " ").replace("-", " ").split():
            key = COLOR_WORDS.get(w)
            if key and key not in out:
                out.append(key)
    return out


def download() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    _get(f"{BASE}/images/metadata/images.csv.gz", DATA / "images.csv.gz")
    _get(f"{BASE}/LICENSE-CC-BY-4.0.txt", DATA / "LICENSE-CC-BY-4.0.txt")
    shards = [f"listings_{h}.json.gz" for h in "0123456789abcdef"]
    for s in shards:
        _get(f"{BASE}/listings/metadata/{s}", DATA / s)
    paths: dict[str, str] = {}
    with gzip.open(DATA / "images.csv.gz", "rt") as f:
        for row in csv.DictReader(f):
            paths[row["image_id"]] = row["path"]
    by_type: dict[str, list[dict]] = defaultdict(list)
    for s in shards:
        with gzip.open(DATA / s, "rt") as f:
            for line in f:
                d = json.loads(line)
                pt = (d.get("product_type") or [{}])[0].get("value")
                if pt not in TYPES and pt not in DISTRACTORS:
                    continue
                main = d.get("main_image_id")
                others = [o for o in d.get("other_image_id", []) if o in paths and o != main]
                if not main or main not in paths:
                    continue
                if pt in TYPES and not others:
                    continue
                by_type[pt].append(
                    {
                        "item_id": d["item_id"],
                        "type": pt,
                        "main": main,
                        "other": others[0] if others else None,
                        "colors": _en_color(d),
                    }
                )
    rnd = random.Random(SEED)
    manifest: dict[str, list] = {"gallery": [], "heldout": [], "distractors": []}
    seen_main: set[str] = set()
    for pt in TYPES:
        items = sorted(by_type[pt], key=lambda x: x["item_id"])
        # ABO zawiera warianty tego samego produktu z identycznym zdjęciem głównym — deduplikacja.
        uniq = []
        for it in items:
            if it["main"] in seen_main or it["other"] in seen_main:
                continue
            seen_main.add(it["main"])
            seen_main.add(it["other"])
            uniq.append(it)
        rnd.shuffle(uniq)
        manifest["gallery"] += uniq[:PER_TYPE]
        manifest["heldout"] += uniq[PER_TYPE : PER_TYPE + HELDOUT_PER_TYPE]
    for pt in DISTRACTORS:
        items = sorted(by_type[pt], key=lambda x: x["item_id"])
        rnd.shuffle(items)
        manifest["distractors"] += items[:DISTRACTOR_PER_TYPE]
    needed = set()
    for group in manifest.values():
        for it in group:
            needed.add(it["main"])
            if it.get("other"):
                needed.add(it["other"])
    print(f"Pobieram {len(needed)} zdjęć (rozmiar 'small', maks. 256 px)…")

    def fetch(img_id: str) -> None:
        _get(f"{BASE}/images/small/{paths[img_id]}", IMG_DIR / f"{img_id}.jpg")

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(fetch, sorted(needed)))
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print({k: len(v) for k, v in manifest.items()})


def _embed_all(engine, ids: list[str]) -> tuple[dict[str, np.ndarray], float]:
    from PIL import Image

    out: dict[str, np.ndarray] = {}
    t0 = time.perf_counter()
    for i in ids:
        with Image.open(IMG_DIR / f"{i}.jpg") as im:
            out[i] = engine._embed_sync(im.convert("RGB"))
    return out, (time.perf_counter() - t0) / max(1, len(ids)) * 1000


def _metrics(manifest: dict, emb: dict[str, np.ndarray], thresholds: tuple[float, float]) -> dict:
    gallery = manifest["gallery"] + manifest["distractors"]
    g_ids = [g["item_id"] for g in gallery]
    g_type = [g["type"] for g in gallery]
    G = np.stack([emb[g["main"]] for g in gallery])
    ranks, ranks_cat = [], []
    pos_sims, top_neg_same_type, per_type_r1 = [], [], defaultdict(list)
    for q in manifest["gallery"]:
        sims = G @ emb[q["other"]]
        order = np.argsort(-sims)
        rank = int(np.where(np.array(g_ids)[order] == q["item_id"])[0][0]) + 1
        ranks.append(rank)
        per_type_r1[q["type"]].append(rank == 1)
        # z filtrem kategorii (sygnał od użytkownika): ograniczamy indeks do tej samej kategorii Findini
        cat = TYPES[q["type"]][0]
        mask = np.array([t in TYPES and TYPES[t][0] == cat for t in g_type])
        sims_c = np.where(mask, sims, -np.inf)
        order_c = np.argsort(-sims_c)
        ranks_cat.append(int(np.where(np.array(g_ids)[order_c] == q["item_id"])[0][0]) + 1)
        true_idx = g_ids.index(q["item_id"])
        pos_sims.append(float(sims[true_idx]))
        same = [float(sims[j]) for j in range(len(g_ids)) if g_type[j] == q["type"] and j != true_idx]
        top_neg_same_type.append(max(same))
    # negatywy: produktu nie ma w indeksie
    neg_top1 = [float(np.max(G @ emb[q["other"]])) for q in manifest["heldout"]]
    # kryterium względne: przewaga top-1 nad top-2
    margins_ok, margins_wrong, margins_held = [], [], []
    for q, rank in zip(manifest["gallery"], ranks, strict=True):
        o = np.sort(G @ emb[q["other"]])[::-1]
        (margins_ok if rank == 1 else margins_wrong).append(float(o[0] - o[1]))
    for q in manifest["heldout"]:
        o = np.sort(G @ emb[q["other"]])[::-1]
        margins_held.append(float(o[0] - o[1]))
    margin_table = {}
    for t in (0.03, 0.04, 0.05, 0.06):
        tp = sum(m >= t for m in margins_ok)
        fp = sum(m >= t for m in margins_wrong) + sum(m >= t for m in margins_held)
        margin_table[str(t)] = {
            "correct_top1_flagged": round(tp / max(1, len(margins_ok)), 3),
            "wrong_top1_flagged": round(sum(m >= t for m in margins_wrong) / max(1, len(margins_wrong)), 3),
            "heldout_flagged": round(sum(m >= t for m in margins_held) / max(1, len(margins_held)), 3),
            "precision": round(tp / max(1, tp + fp), 3),
        }
    strong, related = thresholds

    def recall(rs: list[int], k: int) -> float:
        return round(sum(r <= k for r in rs) / len(rs), 3)

    n_items = len(manifest["gallery"])
    return {
        "queries": len(ranks),
        "gallery_size": len(gallery),
        "recall@1": recall(ranks, 1),
        "recall@5": recall(ranks, 5),
        "recall@10": recall(ranks, 10),
        "mrr": round(float(np.mean([1 / r for r in ranks])), 3),
        "median_rank": float(statistics.median(ranks)),
        "random_baseline_recall@10": round(10 / len(gallery), 3),
        "with_category_filter": {
            "recall@1": recall(ranks_cat, 1),
            "recall@5": recall(ranks_cat, 5),
            "recall@10": recall(ranks_cat, 10),
        },
        "per_type_recall@1": {t: round(sum(v) / len(v), 2) for t, v in sorted(per_type_r1.items())},
        "similarity": {
            "positive_pair_median": round(statistics.median(pos_sims), 3),
            "positive_pair_p10": round(float(np.percentile(pos_sims, 10)), 3),
            "hardest_same_type_negative_median": round(statistics.median(top_neg_same_type), 3),
            "positive_above_hardest_negative": round(
                sum(p > n for p, n in zip(pos_sims, top_neg_same_type, strict=True)) / n_items, 3
            ),
            "heldout_top1_median": round(statistics.median(neg_top1), 3),
        },
        "distinct_margin_criterion": margin_table,
        "thresholds": {
            "similar": strong,
            "related": related,
            "true_match_ge_strong": round(sum(s >= strong for s in pos_sims) / n_items, 3),
            "true_match_ge_related": round(sum(s >= related for s in pos_sims) / n_items, 3),
            "heldout_false_convincing_ge_related": round(sum(s >= related for s in neg_top1) / len(neg_top1), 3),
            "heldout_false_strong_ge_strong": round(sum(s >= strong for s in neg_top1) / len(neg_top1), 3),
        },
    }


def _zero_shot(engine, manifest: dict, emb: dict[str, np.ndarray]) -> dict:
    cat_ok, sub_ok, n, col_ok, col_n, clear_n, clear_ok = 0, 0, 0, 0, 0, 0, 0
    for q in manifest["gallery"] + manifest["heldout"]:
        cat, sub = TYPES[q["type"]]
        s = engine.suggest(emb[q["other"]])
        n += 1
        cat_ok += s["category"] == cat
        sub_ok += s["subtype"] == sub
        if s["confidence"] == "clear":
            clear_n += 1
            clear_ok += s["category"] == cat
        if q["colors"]:
            col_n += 1
            col_ok += s["colors"][0] in q["colors"] or (s["colors"][0] == "navy" and "blue" in q["colors"])
    return {
        "images": n,
        "category_top1_accuracy": round(cat_ok / n, 3),
        "subtype_top1_accuracy": round(sub_ok / n, 3),
        "share_marked_clear": round(clear_n / n, 3),
        "category_accuracy_when_clear": round(clear_ok / max(1, clear_n), 3),
        "color_images_with_english_label": col_n,
        "color_top1_in_label": round(col_ok / max(1, col_n), 3),
    }


def run() -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    import os

    os.environ.setdefault("FINDINI_AI_MODEL_DIR", str(ROOT / "models" / "clip-vit-b32"))
    from app.domain.matching import SIM_RELATED, SIM_SIMILAR
    from app.services.ai import AiEngine

    manifest = json.loads((DATA / "manifest.json").read_text())
    ids = sorted({x for g in manifest.values() for it in g for x in (it["main"], it.get("other")) if x})
    results: dict = {
        "dataset": "Amazon Berkeley Objects (CC BY 4.0), zdjęcia 'small' (maks. 256 px)",
        "seed": SEED,
        "counts": {k: len(v) for k, v in manifest.items()},
        "types": {k: list(v) for k, v in TYPES.items()},
        "distractor_types": DISTRACTORS,
        "variants": {},
    }
    for vf in ("onnx/vision_model.onnx", "onnx/vision_model_quantized.onnx"):
        eng = AiEngine(vision_file=vf)
        if not eng.load():
            print(f"Pomijam {vf}: {eng.status}")
            continue
        emb, ms = _embed_all(eng, ids)
        r = _metrics(manifest, emb, (SIM_SIMILAR, SIM_RELATED))
        r["ms_per_image_cpu"] = round(ms, 1)
        r["zero_shot"] = _zero_shot(eng, manifest, emb)
        results["variants"][eng.model_version] = r
        print(eng.model_version, json.dumps(r, indent=1, ensure_ascii=False))
    import platform

    results["hardware"] = f"{platform.machine()} {platform.system()} {platform.release()}, ONNX Runtime CPU, 2 wątki"
    out = ROOT / "docs" / "eksperyment_ai_wyniki.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"Zapisano {out}")


if __name__ == "__main__":
    {"download": download, "run": run}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
