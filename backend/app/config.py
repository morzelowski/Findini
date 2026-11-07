"""Konfiguracja serwera — wyłącznie ze zmiennych środowiskowych (prefiks FINDINI_)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FINDINI_", env_file=None, extra="ignore")

    env: str = Field(default="dev", description="dev | test | prod")
    database_url: str = "postgresql+psycopg://findini:findini@localhost:5432/findini"
    db_pool_size: int = 15
    db_max_overflow: int = 10

    # Sekret serwera używany jako "pepper" dla skrótów kodów odzyskiwania i adresów IP
    # w licznikach limitów. W produkcji MUSI być ustawiony (min. 32 znaki).
    server_secret: str = "dev-only-insecure-secret-change-me-0000000000"
    # Token administratora (moderacja). Pusty = panel moderacji wyłączony.
    admin_token: str = ""

    storage_dir: Path = Path("/data/photos")
    public_base_url: str = "http://localhost:8080"

    # Model AI (lokalny CLIP w ONNX). Brak plików => funkcje AI niedostępne, reszta działa.
    ai_enabled: bool = True
    ai_model_dir: Path = Path("/models/clip-vit-b32")
    ai_vision_file: str = "onnx/vision_model.onnx"
    ai_text_file: str = "onnx/text_model_quantized.onnx"
    ai_timeout_s: float = 8.0
    ai_max_concurrency: int = 2
    ai_threads: int = 2
    background_jobs: bool = True

    # Pilotaż: Kraków i okolice. Zgłoszenia spoza obszaru są odrzucane.
    pilot_name: str = "Kraków"
    pilot_center_lat: float = 50.0614
    pilot_center_lon: float = 19.9366
    pilot_min_lat: float = 49.90
    pilot_max_lat: float = 50.20
    pilot_min_lon: float = 19.65
    pilot_max_lon: float = 20.30
    # Rozmiar komórki publicznej siatki (m). Publiczna lokalizacja = środek komórki.
    grid_cell_m: int = 500

    # Retencja (dni)
    report_active_days: int = 60
    report_purge_after_days: int = 180
    orphan_photo_hours: int = 24
    session_idle_days: int = 365

    # Limity
    max_upload_bytes: int = 10 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    trust_proxy_headers: bool = False
    rate_limits_enabled: bool = True

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod:
        if len(s.server_secret) < 32 or s.server_secret.startswith("dev-only"):
            raise RuntimeError("FINDINI_SERVER_SECRET musi być ustawiony w produkcji (min. 32 znaki)")
        if not s.public_base_url.startswith("https://"):
            raise RuntimeError("W produkcji FINDINI_PUBLIC_BASE_URL musi używać HTTPS")
    return s
