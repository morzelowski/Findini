"""Lokalna analiza obrazu: CLIP ViT-B/32 (ONNX Runtime, CPU).

Zastosowania:
1. Wektor (embedding) zdjęcia zgłoszenia -> wyszukiwanie zdjęciem i sygnał w dopasowaniach.
2. Sugestie kategorii/rodzaju i koloru (zero-shot) — tylko podpowiedź do zatwierdzenia.

Ograniczenia (opisane też w docs/EKSPERYMENT_AI.md):
- Podobieństwo wektorów NIE jest prawdopodobieństwem i nie dowodzi własności.
- Model nie rozróżnia pewnie egzemplarzy tego samego modelu produktu.
- Brak modelu / błąd / przekroczenie czasu => funkcje AI zwracają None, aplikacja działa dalej.
- Zdjęcia dowodów (roszczeń) nigdy nie są tu przetwarzane.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.config import get_settings
from app.domain.categories import CATEGORIES, COLOR_EN, COLOR_PL

log = logging.getLogger("findini.ai")

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32).reshape(3, 1, 1)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32).reshape(3, 1, 1)
LOGIT_SCALE = 100.0  # skala CLIP: exp(logit_scale)
COLOR_TEMPLATES = [
    "a photo of a {} object",
    "a {} colored item",
    "a close-up photo of something {}",
    "a {} thing",
]


def preprocess(img: Image.Image) -> np.ndarray:
    """Odpowiednik CLIPImageProcessor: skalowanie krótszego boku do 224 (bicubic), crop 224, normalizacja."""
    img = img.convert("RGB")
    w, h = img.size
    scale = 224 / min(w, h)
    nw, nh = max(224, round(w * scale)), max(224, round(h * scale))
    img = img.resize((nw, nh), Image.Resampling.BICUBIC)
    left, top = (nw - 224) // 2, (nh - 224) // 2
    img = img.crop((left, top, left + 224, top + 224))
    arr = np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0
    arr = (arr - MEAN) / STD
    return arr[np.newaxis, ...].astype(np.float32)


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


@dataclass
class Label:
    kind: str  # category | color
    key: str
    subtype: str | None
    prompt: str


class AiEngine:
    def __init__(self, vision_file: str | None = None, model_dir: Path | None = None) -> None:
        s = get_settings()
        self.model_dir: Path = model_dir or s.ai_model_dir
        self.vision_file = vision_file or s.ai_vision_file
        self.enabled = s.ai_enabled
        self._lock = threading.Lock()
        self._vision: Any = None
        self._text: Any = None
        self._tokenizer: Any = None
        self._labels: list[Label] = []
        self._label_emb: np.ndarray | None = None
        self.status = "not_loaded"
        self.error: str | None = None
        self.variant = "fp32" if "quantized" not in self.vision_file else "int8"
        rev = "unknown"
        family = "clip-vit-b32"  # zgodność dotychczasowych instalacji
        rev_file = self.model_dir / "REVISION"
        if rev_file.exists():
            source = rev_file.read_text().strip()
            rev = source.split("@")[-1][:7]
            if "patch16@" in source:
                family = "clip-vit-b16"
        self.model_version = f"{family}@{rev}/{self.variant}"
        self._pool = ThreadPoolExecutor(max_workers=max(1, s.ai_max_concurrency), thread_name_prefix="ai")
        self._pending = 0
        self._pending_lock = threading.Lock()

    # ---------- ładowanie ----------
    def load(self) -> bool:
        with self._lock:
            if self.status == "ready":
                return True
            if not self.enabled:
                self.status = "disabled"
                return False
            s = get_settings()
            vision_path = self.model_dir / self.vision_file
            text_path = self.model_dir / s.ai_text_file
            tok_path = self.model_dir / "tokenizer.json"
            if not vision_path.exists():
                self.status = "missing_model"
                self.error = f"Brak pliku modelu: {vision_path.name}"
                log.warning("AI niedostępne: brak modelu w %s", self.model_dir)
                return False
            try:
                import onnxruntime as ort

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = max(1, s.ai_threads)
                opts.inter_op_num_threads = 1
                t0 = time.monotonic()
                self._vision = ort.InferenceSession(str(vision_path), opts, providers=["CPUExecutionProvider"])
                if text_path.exists() and tok_path.exists():
                    from tokenizers import Tokenizer

                    self._text = ort.InferenceSession(str(text_path), opts, providers=["CPUExecutionProvider"])
                    self._tokenizer = Tokenizer.from_file(str(tok_path))
                    self._build_labels()
                self.status = "ready"
                log.info("Model AI załadowany (%s) w %.1fs", self.model_version, time.monotonic() - t0)
                return True
            except Exception as e:
                self.status = "error"
                self.error = type(e).__name__
                log.exception("Nie udało się załadować modelu AI")
                return False

    def _encode_text(self, prompts: list[str]) -> np.ndarray:
        out = []
        for p in prompts:
            ids = np.array([self._tokenizer.encode(p).ids[:77]], dtype=np.int64)
            out.append(self._text.run(["text_embeds"], {"input_ids": ids})[0][0])
        return _normalize(np.stack(out).astype(np.float32))

    def _build_labels(self) -> None:
        labels: list[Label] = []
        for c in CATEGORIES:
            for subtype, prompt in c.prompts.items():
                labels.append(Label("category", c.key, subtype, prompt))
        cat_emb = self._encode_text([lab.prompt for lab in labels])
        # Kolory: średnia z kilku szablonów (w eksperymencie 54% vs 44% dla jednego szablonu).
        col_emb = []
        for key, en in COLOR_EN.items():
            labels.append(Label("color", key, None, COLOR_TEMPLATES[0].format(en)))
            col_emb.append(_normalize(self._encode_text([t.format(en) for t in COLOR_TEMPLATES]).mean(axis=0)))
        self._labels = labels
        self._label_emb = np.concatenate([cat_emb, np.stack(col_emb)], axis=0)

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    # ---------- inferencja ----------
    def _embed_sync(self, img: Image.Image) -> np.ndarray:
        x = preprocess(img)
        emb = self._vision.run(["image_embeds"], {"pixel_values": x})[0][0]
        return _normalize(emb.astype(np.float32))

    def embed(self, img: Image.Image, timeout_s: float | None = None) -> np.ndarray | None:
        """Wektor zdjęcia albo None (brak modelu, przeciążenie, timeout, błąd)."""
        if not self.ready and not self.load():
            return None
        with self._pending_lock:
            if self._pending >= 8:  # ograniczenie kolejki = ograniczenie kosztu
                log.warning("Kolejka AI pełna — pomijam")
                return None
            self._pending += 1
        fut: Future[np.ndarray] = self._pool.submit(self._embed_sync, img.copy())
        fut.add_done_callback(lambda _f: self._dec())
        try:
            return fut.result(timeout=timeout_s or get_settings().ai_timeout_s)
        except FutureTimeout:
            log.warning("Przekroczono czas analizy obrazu")
            return None
        except Exception:
            log.exception("Błąd analizy obrazu")
            return None

    def _dec(self) -> None:
        with self._pending_lock:
            self._pending -= 1

    def suggest(self, emb: np.ndarray) -> dict[str, Any] | None:
        """Sugestia kategorii, rodzaju i kolorów. Bez procentów — tylko kolejność i siła 'wyraźna/niepewna'."""
        if self._label_emb is None:
            return None
        sims = self._label_emb @ emb
        cat_idx = [i for i, lab in enumerate(self._labels) if lab.kind == "category"]
        col_idx = [i for i, lab in enumerate(self._labels) if lab.kind == "color"]

        def softmax(idx: list[int]) -> np.ndarray:
            z = sims[idx] * LOGIT_SCALE
            z = z - z.max()
            e = np.exp(z)
            return e / e.sum()

        pc = softmax(cat_idx)
        order = np.argsort(-pc)
        best = self._labels[cat_idx[order[0]]]
        second = self._labels[cat_idx[order[1]]]
        cat_clear = bool(pc[order[0]] >= 0.5)
        # Sumujemy prawdopodobieństwa po kategorii (np. kilka rodzajów elektroniki).
        cat_mass: dict[str, float] = {}
        for i, p in zip(cat_idx, pc, strict=True):
            cat_mass[self._labels[i].key] = cat_mass.get(self._labels[i].key, 0.0) + float(p)
        best_cat = max(cat_mass, key=lambda k: cat_mass[k])

        pcol = softmax(col_idx)
        corder = np.argsort(-pcol)
        colors = [self._labels[col_idx[corder[0]]].key]
        if pcol[corder[1]] >= 0.25:
            colors.append(self._labels[col_idx[corder[1]]].key)
        return {
            "category": best_cat,
            "subtype": best.subtype if best.key == best_cat else None,
            "alternative": {"category": second.key, "subtype": second.subtype} if not cat_clear else None,
            "confidence": "clear" if cat_clear and cat_mass[best_cat] >= 0.6 else "uncertain",
            "colors": colors,
            "colors_pl": [COLOR_PL[c] for c in colors],
            "model": self.model_version,
        }

    def info(self) -> dict[str, Any]:
        return {"status": self.status, "model": self.model_version if self.ready else None, "error": self.error}


_engine: AiEngine | None = None
_engine_lock = threading.Lock()


def engine() -> AiEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = AiEngine()
        return _engine


def reset_engine() -> None:
    global _engine
    with _engine_lock:
        _engine = None
