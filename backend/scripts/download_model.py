"""Pobiera lokalny model CLIP ViT-B/32 (ONNX) używany przez Findini.

Źródło: https://huggingface.co/Xenova/clip-vit-base-patch32 (licencja MIT,
eksport ONNX). Rewizja jest przypięta,
a każdy plik weryfikowany sumą SHA-256 — nie pobieramy "najnowszej" wersji
w ciemno.

Użycie (bez zależności poza biblioteką standardową):
    python3 backend/scripts/download_model.py [--dest models/clip-vit-b32] [--with-quantized]
"""

from __future__ import annotations

import argparse
import hashlib
import ssl
import sys
import urllib.request
from pathlib import Path

REPO = "Xenova/clip-vit-base-patch32"
REVISION = "6b7c523703ae26e39be4b03774966f8571c7f523"

# path -> (size, sha256 lub None dla małych plików tekstowych sprawdzanych rozmiarem)
FILES: dict[str, tuple[int, str | None]] = {
    "onnx/vision_model.onnx": (
        351685709,
        "fd6e1402a588279d1723c7534d4bcba5bc0b14b47dfab0e46f8c47b8270d7d40",
    ),
    "onnx/text_model_quantized.onnx": (
        64504507,
        "73baab855d406190da9faa498cfedf65f15cf309f4cc7385b7b032e6d08e5c3a",
    ),
    "tokenizer.json": (2224119, None),
    "preprocessor_config.json": (520, None),
}
OPTIONAL_QUANTIZED = {
    "onnx/vision_model_quantized.onnx": (
        89117001,
        "583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299",
    ),
}

B16_REPO = "Xenova/clip-vit-base-patch16"
B16_REVISION = "342fdf2f67aded64d138ff074745fb4a5d2bba5f"
B16_FILES = {
    "onnx/vision_model.onnx": (
        345060583,
        "b5170b47c0ecc667c9af5b42ed460c341377706d1466d177798c65fe49ea1e6b",
    ),
    "onnx/text_model_quantized.onnx": (
        64504507,
        "9106b51e6c663a56b99182ec617c2b3d53577b037e7e24a7717eb78048a0c97a",
    ),
    "tokenizer.json": (2224081, None),
    "preprocessor_config.json": (520, None),
}


def _ssl_context() -> ssl.SSLContext:
    """Python z python.org na macOS nie ma domyślnie magazynu CA — użyj certifi, jeśli jest."""
    try:
        import certifi  # type: ignore[import-not-found]

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(rel: str, size: int, sha: str | None, dest: Path, repo: str = REPO, revision: str = REVISION) -> None:
    target = dest / rel
    if target.exists() and target.stat().st_size == size and (sha is None or sha256_of(target) == sha):
        print(f"[ok]   {rel} (już pobrany)")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{rel}"
    tmp = target.with_suffix(target.suffix + ".part")
    print(f"[get]  {rel} ({size / 1e6:.1f} MB)")
    req = urllib.request.Request(url, headers={"User-Agent": "findini-model-downloader/1.0"})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp, tmp.open("wb") as out:
        done = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if size > 5_000_000:
                print(f"\r       {done / size:6.1%}", end="", flush=True)
    if size > 5_000_000:
        print()
    if tmp.stat().st_size != size:
        tmp.unlink()
        sys.exit(f"Nieprawidłowy rozmiar pliku {rel}")
    if sha is not None and sha256_of(tmp) != sha:
        tmp.unlink()
        sys.exit(f"Suma SHA-256 pliku {rel} nie zgadza się — przerwano.")
    tmp.rename(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--model", choices=["b16", "b32"], default="b16")
    parser.add_argument("--dest")
    parser.add_argument("--with-quantized", action="store_true", help="pobierz też wersję int8 (do eksperymentu)")
    args = parser.parse_args()
    dest = Path(args.dest) if args.dest else root / "models" / f"clip-vit-{args.model}"
    repo, revision = (B16_REPO, B16_REVISION) if args.model == "b16" else (REPO, REVISION)
    files = dict(B16_FILES if args.model == "b16" else FILES)
    if args.with_quantized and args.model == "b32":
        files.update(OPTIONAL_QUANTIZED)
    for rel, (size, sha) in files.items():
        fetch(rel, size, sha, dest, repo, revision)
    (dest / "REVISION").write_text(f"{repo}@{revision}\n")
    print(f"Model gotowy w {dest}")


if __name__ == "__main__":
    main()
