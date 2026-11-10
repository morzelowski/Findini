"""Model prywatności lokalizacji.

Dokładny punkt (report_private) nigdy nie bierze udziału w publicznych zapytaniach.
Publicznie istnieje tylko środek komórki siatki ~500 x 500 m (stała siatka w stopniach,
skalowana do szerokości geograficznej pilotażu). Wszystkie punkty w tej samej komórce dają
identyczną publiczną lokalizację, więc wielokrotne zapytania "w promieniu" lub o dystans
nie pozwalają odtworzyć ukrytego punktu — można co najwyżej ustalić komórkę, którą i tak
pokazujemy na mapie.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.config import get_settings
from app.errors import invalid

EARTH_RADIUS_M = 6_371_008.8
M_PER_DEG_LAT = 111_320.0


@dataclass(frozen=True)
class PublicArea:
    cell_id: str
    lat: float
    lon: float
    radius_m: int


def _steps() -> tuple[float, float]:
    s = get_settings()
    dlat = s.grid_cell_m / M_PER_DEG_LAT
    dlon = s.grid_cell_m / (M_PER_DEG_LAT * math.cos(math.radians(s.grid_reference_lat)))
    return dlat, dlon


def in_pilot(lat: float, lon: float) -> bool:
    s = get_settings()
    return s.pilot_min_lat <= lat <= s.pilot_max_lat and s.pilot_min_lon <= lon <= s.pilot_max_lon


def ensure_in_pilot(lat: float, lon: float) -> None:
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise invalid("bad_location", "Nieprawidłowe współrzędne.")
    if not in_pilot(lat, lon):
        raise invalid(
            "outside_pilot",
            f"Wskaż miejsce na obsługiwanym obszarze: {get_settings().pilot_name}. "
            "Możesz wyszukać miejscowość lub przesunąć mapę.",
        )


def public_area(lat: float, lon: float, uncertainty_m: int = 0) -> PublicArea:
    dlat, dlon = _steps()
    i = math.floor(lat / dlat)
    j = math.floor(lon / dlon)
    c_lat = (i + 0.5) * dlat
    c_lon = (j + 0.5) * dlon
    cell = get_settings().grid_cell_m
    # Promień obszaru: co najmniej połowa przekątnej komórki; większa niepewność deklarowana
    # przez użytkownika powiększa obszar (zaokrąglenie do 250 m, by nie zdradzać wartości).
    base = int(math.ceil(cell * math.sqrt(2) / 2 / 50.0) * 50)
    if uncertainty_m > base:
        radius = int(math.ceil(uncertainty_m / 250.0) * 250)
    else:
        radius = base
    return PublicArea(cell_id=f"{i}:{j}", lat=round(c_lat, 6), lon=round(c_lon, 6), radius_m=min(radius, 5000))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def rounded_distance_m(d: float) -> int:
    """Publiczny dystans: liczony od środka komórki i zaokrąglany (100 m / 500 m)."""
    if d < 1000:
        return int(round(d / 100.0) * 100)
    return int(round(d / 500.0) * 500)
