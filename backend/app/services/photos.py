"""Przetwarzanie i przechowywanie zdjęć.

- Typ pliku ustalamy, dekodując obraz (nagłówek Content-Type klienta jest ignorowany).
- Limity: rozmiar pliku, liczba pikseli (ochrona przed "bombą dekompresyjną"), wymiary.
- Zapisujemy wyłącznie nową, przeskalowaną wersję JPEG bez metadanych (EXIF/GPS/XMP),
  po obrocie zgodnie z orientacją. Oryginał nie jest przechowywany.
- Nazwy plików są losowe (128 bitów) i nie zależą od nazwy przesłanej przez klienta.
  Pliki nigdy nie są serwowane bezpośrednio z dysku — tylko przez endpoint z kontrolą uprawnień.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings
from app.errors import ApiError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIDE = 1600
THUMB_SIDE = 480
MIN_SIDE = 64


@dataclass
class ProcessedImage:
    full: bytes
    thumb: bytes
    width: int
    height: int
    sha256: str
    image: Image.Image  # wersja RGB do analizy (bez metadanych)


def process_upload(raw: bytes) -> ProcessedImage:
    s = get_settings()
    if len(raw) == 0:
        raise ApiError(422, "empty_file", "Plik jest pusty.")
    if len(raw) > s.max_upload_bytes:
        raise ApiError(413, "file_too_large", f"Zdjęcie jest za duże (maks. {s.max_upload_bytes // (1024 * 1024)} MB).")
    Image.MAX_IMAGE_PIXELS = s.max_image_pixels
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            w, h = probe.size
            if fmt not in ALLOWED_FORMATS:
                raise ApiError(415, "unsupported_image", "Obsługiwane formaty: JPEG, PNG, WEBP.")
            if w * h > s.max_image_pixels or max(w, h) > 12000:
                raise ApiError(413, "image_too_large", "Zdjęcie ma zbyt duże wymiary.")
            if min(w, h) < MIN_SIDE:
                raise ApiError(422, "image_too_small", "Zdjęcie jest zbyt małe.")
            probe.load()
            img = ImageOps.exif_transpose(probe)
    except ApiError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as e:
        raise ApiError(415, "unsupported_image", "Nie udało się odczytać zdjęcia.") from e

    img = img.convert("RGB")  # usuwa kanał alfa i paletę; nowy obiekt bez info/EXIF
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    clean = Image.new("RGB", img.size)
    clean.paste(img)

    full_buf = io.BytesIO()
    clean.save(full_buf, "JPEG", quality=85, optimize=True, progressive=True)
    thumb_img = clean.copy()
    thumb_img.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.Resampling.LANCZOS)
    thumb_buf = io.BytesIO()
    thumb_img.save(thumb_buf, "JPEG", quality=80, optimize=True)
    full = full_buf.getvalue()
    return ProcessedImage(
        full=full,
        thumb=thumb_buf.getvalue(),
        width=clean.width,
        height=clean.height,
        sha256=hashlib.sha256(full).hexdigest(),
        image=clean,
    )


_KEY_RE = re.compile(r"^[0-9a-f]{2}/[0-9a-f]{32}(_t)?\.jpg$")


def _path_for(key: str) -> Path:
    if not key or not _KEY_RE.match(key):
        raise ValueError("invalid storage key")
    return get_settings().storage_dir / key


def store(data: bytes, suffix: str) -> str:
    name = secrets.token_hex(16)
    key = f"{name[:2]}/{name}{suffix}.jpg"
    path = _path_for(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    return key


def read(key: str) -> bytes:
    return _path_for(key).read_bytes()


def delete(key: str | None) -> None:
    if not key:
        return
    try:
        _path_for(key).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


def storage_writable() -> bool:
    d = get_settings().storage_dir
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".probe"
        probe.write_bytes(b"ok")
        probe.unlink()
        return True
    except OSError:
        return False
