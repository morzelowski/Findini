"""Prywatność lokalizacji i geowyszukiwanie."""

from __future__ import annotations

import random

from app.geo import haversine_m, public_area
from tests.conftest import report_payload

EXACT = (50.06123, 19.94567)


def test_points_in_same_cell_share_public_area():
    a = public_area(*EXACT)
    rnd = random.Random(7)
    same = 0
    for _ in range(500):
        lat = EXACT[0] + rnd.uniform(-0.002, 0.002)
        lon = EXACT[1] + rnd.uniform(-0.003, 0.003)
        b = public_area(lat, lon)
        if b.cell_id == a.cell_id:
            same += 1
            assert (b.lat, b.lon) == (a.lat, a.lon)
    assert same > 20
    # środek komórki jest odległy od punktu, ale nie dalej niż pół przekątnej (~354 m)
    d = haversine_m(EXACT[0], EXACT[1], a.lat, a.lon)
    assert d <= 360


def test_repeated_radius_queries_do_not_reveal_exact_point(client, guest_factory):
    """Atakujący zawęża promień (wyszukiwanie binarne) wokół wielu punktów.
    Dowiaduje się co najwyżej odległości do środka komórki — nigdy do ukrytego punktu."""
    g = guest_factory()
    rid = g.post(
        "/v1/reports", json=report_payload(location={"lat": EXACT[0], "lon": EXACT[1], "source": "gps"})
    ).json()["id"]
    pub = client.get(f"/v1/reports/{rid}").json()
    center = (pub["area"]["lat"], pub["area"]["lon"])
    assert center != EXACT

    def found_within(lat: float, lon: float, r: int) -> bool:
        res = client.get("/v1/reports", params={"lat": lat, "lon": lon, "radius_m": r, "limit": 50})
        return rid in [i["id"] for i in res.json()["items"]]

    probes = [(EXACT[0] + 0.004, EXACT[1]), (EXACT[0], EXACT[1] - 0.006), (EXACT[0] - 0.003, EXACT[1] + 0.004)]
    for plat, plon in probes:
        lo, hi = 100, 2000
        while hi - lo > 10:
            mid = (lo + hi) // 2
            if found_within(plat, plon, mid):
                hi = mid
            else:
                lo = mid
        to_center = haversine_m(plat, plon, *center)
        to_exact = haversine_m(plat, plon, *EXACT)
        # zmierzony promień odpowiada środkowi komórki, nie dokładnemu punktowi
        assert abs(hi - to_center) < 15
        assert abs(to_exact - to_center) > 30 or abs(hi - to_exact) >= abs(hi - to_center)
    # publiczny dystans też liczony od środka komórki i zaokrąglany
    res = client.get("/v1/reports", params={"lat": probes[0][0], "lon": probes[0][1], "radius_m": 3000}).json()
    item = next(i for i in res["items"] if i["id"] == rid)
    assert item["distance_m"] % 100 == 0


def test_radius_filter_and_sorting(client, guest_factory):
    g = guest_factory()
    near = g.post(
        "/v1/reports",
        json=report_payload(title="Blisko Rynku", location={"lat": 50.0617, "lon": 19.9373, "source": "map"}),
    ).json()["id"]
    far = g.post(
        "/v1/reports",
        json=report_payload(title="Nowa Huta", location={"lat": 50.0722, "lon": 20.0378, "source": "map"}),
    ).json()["id"]
    res = client.get("/v1/reports", params={"lat": 50.0617, "lon": 19.9373, "radius_m": 2000}).json()
    ids = [i["id"] for i in res["items"]]
    assert near in ids and far not in ids
    res = client.get(
        "/v1/reports", params={"lat": 50.0617, "lon": 19.9373, "radius_m": 10000, "sort": "nearest"}
    ).json()
    ids = [i["id"] for i in res["items"]]
    assert ids.index(near) < ids.index(far)
    assert res["items"][0]["match"]["reasons"]


def test_outside_pilot_rejected(guest_factory):
    g = guest_factory()
    r = g.post("/v1/reports", json=report_payload(location={"lat": 52.2297, "lon": 21.0122, "source": "gps"}))
    assert r.status_code == 422 and r.json()["error"]["code"] == "outside_pilot"


def test_map_areas_are_aggregated_cells(client, guest_factory):
    g = guest_factory()
    for dx in (0.0, 0.0004, 0.0008):
        g.post(
            "/v1/reports",
            json=report_payload(location={"lat": 50.0617 + dx / 3, "lon": 19.9373 + dx / 3, "source": "map"}),
        )
    res = client.get("/v1/reports/areas", params={"bbox": "19.90,50.04,19.97,50.08"}).json()
    assert sum(a["count"] for a in res["areas"]) == 3
    for a in res["areas"]:
        assert set(a) == {"cell_id", "lat", "lon", "radius_m", "count", "lost", "found", "sample_ids"}
