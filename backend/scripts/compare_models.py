"""Porównanie B/32 i B/16 na tym samym, rozdzielonym zbiorze ABO; tylko CPU."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from scripts.ai_experiment import DATA, ROOT, _embed_all, _metrics, _zero_shot


def main() -> None:
    os.environ.setdefault("FINDINI_AI_THREADS", "2")
    from app.domain.matching import SIM_RELATED, SIM_SIMILAR
    from app.services.ai import AiEngine

    manifest = json.loads((DATA / "manifest.json").read_text())
    ids = sorted({x for g in manifest.values() for it in g for x in (it["main"], it.get("other")) if x})
    result = {
        "dataset": "ABO, CC BY 4.0; ten sam podział co eksperyment 07.11.2026",
        "hardware": f"{platform.machine()} {platform.system()} {platform.release()}, CPU, 2 wątki",
        "variants": {},
    }
    for family in ("b32", "b16"):
        engine = AiEngine(model_dir=ROOT / "models" / f"clip-vit-{family}")
        if not engine.load():
            raise RuntimeError(f"Model {family}: {engine.status}")
        emb, ms = _embed_all(engine, ids)
        metrics = _metrics(manifest, emb, (SIM_SIMILAR, SIM_RELATED))
        metrics["ms_per_image_cpu"] = round(ms, 2)
        metrics["zero_shot"] = _zero_shot(engine, manifest, emb)
        result["variants"][engine.model_version] = metrics
        print(engine.model_version, json.dumps(metrics, ensure_ascii=False), flush=True)
    out: Path = ROOT / "docs" / "porownanie_modeli_cpu.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
