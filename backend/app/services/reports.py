"""Logika zgłoszeń: tworzenie, edycja, serializacja publiczna/prywatna, wyszukiwanie, dopasowania."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.domain import categories as cats
from app.domain.matching import DISTINCT_MARGIN, SIM_RELATED, Cand, QueryCtx, explain
from app.domain.states import OPEN_CLAIM_STATES, PUBLIC_REPORT_STATES
from app.errors import ApiError, forbidden, invalid, not_found
from app.geo import ensure_in_pilot, public_area, rounded_distance_m
from app.models import AuditEvent, Claim, Photo, Report, ReportPrivate
from app.schemas import ReportCreate, ReportUpdate, clean_text, iso, reject_contact_data
from app.security import Actor, now_utc

DOCUMENT_SUBTYPES = {"dowód osobisty", "legitymacja", "prawo jazdy", "paszport", "karta płatnicza", "inne dokumenty"}
MAX_EVENT_WINDOW = timedelta(days=14)
MAX_EVENT_AGE = timedelta(days=365)


# ---------------------------------------------------------------- serializacja
def photo_ref(p: Photo) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "url": f"/v1/photos/{p.id}",
        "thumb_url": f"/v1/photos/{p.id}?size=thumb",
        "width": p.width,
        "height": p.height,
    }


def _attr_list(r: Report) -> list[dict[str, Any]]:
    return [{"key": k, "label": cats.attr_label(r.category, k), "value": v} for k, v in (r.attributes or {}).items()]


def public_report(
    r: Report,
    *,
    actor: Actor | None = None,
    distance_m: int | None = None,
    match: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Jawna lista pól publicznych. Nie zawiera: dokładnej lokalizacji, ukrytej cechy,
    pytania weryfikacyjnego, identyfikatora właściciela, danych roszczeń."""
    photos = [p for p in r.photos if p.purpose == "report"]
    cat = cats.CATEGORY_BY_KEY.get(r.category)
    return {
        "id": str(r.id),
        "kind": r.kind,
        "status": r.status,
        "category": r.category,
        "category_label": cat.label if cat else r.category,
        "title": r.title,
        "description": r.description,
        "attributes": _attr_list(r),
        "colors": list(r.colors or []),
        "occurred_from": iso(r.occurred_from),
        "occurred_to": iso(r.occurred_to),
        "published_at": iso(r.published_at),
        "updated_at": iso(r.updated_at),
        "area": {
            "lat": r.public_lat,
            "lon": r.public_lon,
            "radius_m": r.area_radius_m,
            "label": r.area_label,
            "precision": "approximate",
        },
        "holding": r.holding,
        "holding_note": r.holding_note,
        "photos": [photo_ref(p) for p in photos],
        "ai_indexed": any(p.embedding_status == "ready" for p in photos),
        "distance_m": distance_m,
        "match": match,
        "is_mine": bool(actor and actor.guest_id == r.owner_id),
    }


def owner_report(db: DbSession, r: Report, actor: Actor) -> dict[str, Any]:
    out = public_report(r, actor=actor)
    pv = r.private
    counts = db.execute(select(Claim.status, func.count()).where(Claim.report_id == r.id).group_by(Claim.status)).all()
    by_status = {s: int(n) for s, n in counts}
    out["private"] = {
        "exact_lat": pv.exact_lat,
        "exact_lon": pv.exact_lon,
        "accuracy_m": pv.accuracy_m,
        "uncertainty_m": pv.uncertainty_m,
        "location_source": pv.location_source,
        "secret_details": pv.secret_details,
        "claim_question": pv.claim_question,
    }
    out["expires_at"] = iso(r.expires_at)
    out["hidden"] = r.hidden_at is not None
    out["claims"] = {
        "open": sum(v for k, v in by_status.items() if k in OPEN_CLAIM_STATES),
        "pending": by_status.get("pending", 0),
        "total": sum(by_status.values()),
    }
    out["photo_status"] = [
        {"id": str(p.id), "embedding_status": p.embedding_status} for p in r.photos if p.purpose == "report"
    ]
    return out


def build_search_text(r: Report) -> str:
    cat = cats.CATEGORY_BY_KEY.get(r.category)
    parts = [r.title, r.description, cat.label if cat else ""]
    parts += [str(v) for v in (r.attributes or {}).values()]
    parts += [cats.COLOR_PL.get(c, c) for c in (r.colors or [])]
    if r.area_label:
        parts.append(r.area_label)
    return " ".join(p for p in parts if p)[:3000]


# ---------------------------------------------------------------- walidacja
def _norm_times(t_from: datetime, t_to: datetime) -> tuple[datetime, datetime]:
    a, b = t_from.astimezone(UTC), t_to.astimezone(UTC)
    now = now_utc()
    if a > b:
        raise invalid("bad_time", "Początek przedziału czasu musi być przed jego końcem.")
    if b > now + timedelta(minutes=10):
        raise invalid("bad_time", "Czas zdarzenia nie może być w przyszłości.")
    if a < now - MAX_EVENT_AGE:
        raise invalid("bad_time", "Zgłoszenie może dotyczyć zdarzeń z ostatniego roku.")
    if b - a > MAX_EVENT_WINDOW:
        raise invalid("bad_time", "Przedział czasu może mieć maksymalnie 14 dni.")
    return a, b


def _check_public_text(title: str, description: str, area_label: str | None, holding_note: str | None) -> None:
    reject_contact_data("Tytuł", title)
    reject_contact_data("Opis", description)
    if area_label:
        reject_contact_data("Opis miejsca", area_label)
    if holding_note:
        reject_contact_data("Gdzie jest przedmiot", holding_note)


def _attach_photos(db: DbSession, r: Report, actor: Actor, photo_ids: list[uuid.UUID]) -> None:
    if len(set(photo_ids)) != len(photo_ids):
        raise invalid("bad_photos", "Zdjęcia powtarzają się.")
    sub = r.attributes.get("subtype") if r.attributes else None
    if photo_ids and (sub in DOCUMENT_SUBTYPES):
        raise invalid(
            "photo_not_allowed",
            "Nie publikuj zdjęć dokumentów. Opisz dokument ogólnie — szczegóły zweryfikujesz w prywatnej rozmowie.",
        )
    photos = db.scalars(select(Photo).where(Photo.id.in_(photo_ids))).all() if photo_ids else []
    by_id = {p.id: p for p in photos}
    for pid in photo_ids:
        p = by_id.get(pid)
        if p is None or p.owner_id != actor.guest_id or p.purpose != "report":
            raise invalid("bad_photos", "Nieprawidłowe zdjęcie.")
        if p.report_id is not None and p.report_id != r.id:
            raise invalid("bad_photos", "To zdjęcie jest już użyte w innym zgłoszeniu.")
    # odłącz zdjęcia usunięte z listy (pliki usuwa zadanie porządkowe jako osierocone)
    current = db.scalars(select(Photo).where(Photo.report_id == r.id, Photo.purpose == "report")).all()
    for p in current:
        if p.id not in by_id:
            p.report_id = None
            p.created_at = now_utc() - timedelta(days=2)  # kwalifikuje się do natychmiastowego usunięcia
    for pos, pid in enumerate(photo_ids):
        p = by_id[pid]
        p.report_id = r.id
        p.position = pos


def _audit(
    db: DbSession,
    actor_id: Any,
    entity: str,
    entity_id: Any,
    action: str,
    from_s: str | None = None,
    to_s: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=actor_id, entity=entity, entity_id=entity_id, action=action, from_status=from_s, to_status=to_s
        )
    )


# ---------------------------------------------------------------- tworzenie / edycja
def create_report(db: DbSession, actor: Actor, body: ReportCreate) -> Report:
    cat = cats.validate_category(body.category)
    attrs = cats.validate_attributes(cat.key, body.attributes)
    colors = cats.validate_colors(body.colors)
    title = clean_text(body.title, 80)
    if len(title) < 3:
        raise invalid("bad_title", "Tytuł jest za krótki.")
    description = clean_text(body.description, 1000, multiline=True)
    area_label = clean_text(body.area_label, 80) or None
    holding_note = clean_text(body.holding_note, 120) or None
    _check_public_text(title, description, area_label, holding_note)
    t_from, t_to = _norm_times(body.occurred_from, body.occurred_to)
    loc = body.location
    ensure_in_pilot(loc.lat, loc.lon)
    area = public_area(loc.lat, loc.lon, loc.uncertainty_m)

    if body.kind == "found":
        holding = body.holding or "with_finder"
        claim_question = clean_text(body.claim_question, 200) or None
    else:
        if body.holding or body.claim_question:
            raise invalid("bad_field", "Pola „gdzie jest przedmiot” i „pytanie” dotyczą tylko rzeczy znalezionych.")
        holding, claim_question = None, None
        holding_note = None
    secret = clean_text(body.secret_details, 500, multiline=True) or None

    now = now_utc()
    r = Report(
        id=uuid.uuid4(),
        kind=body.kind,
        status="active",
        owner_id=actor.guest_id,
        category=cat.key,
        title=title,
        description=description,
        attributes=attrs,
        colors=colors,
        occurred_from=t_from,
        occurred_to=t_to,
        cell_id=area.cell_id,
        public_lat=area.lat,
        public_lon=area.lon,
        area_radius_m=area.radius_m,
        area_label=area_label,
        holding=holding,
        holding_note=holding_note,
        created_at=now,
        updated_at=now,
        published_at=now,
        expires_at=now + timedelta(days=get_settings().report_active_days),
    )
    r.search_text = build_search_text(r)
    r.private = ReportPrivate(
        exact_lat=loc.lat,
        exact_lon=loc.lon,
        accuracy_m=loc.accuracy_m,
        uncertainty_m=loc.uncertainty_m,
        location_source=loc.source,
        secret_details=secret,
        claim_question=claim_question,
    )
    db.add(r)
    db.flush()
    _attach_photos(db, r, actor, body.photo_ids)
    _audit(db, actor.guest_id, "report", r.id, "create", None, "active")
    db.commit()
    db.refresh(r)
    return r


def load_owned(db: DbSession, report_id: uuid.UUID, actor: Actor, *, for_update: bool = False) -> Report:
    q = select(Report).where(Report.id == report_id)
    if for_update:
        q = q.with_for_update(of=Report)
    r = db.scalar(q)
    if r is None or r.owner_id != actor.guest_id:
        # Ten sam błąd dla „nie istnieje” i „nie Twoje” — nie ujawniamy istnienia.
        raise not_found("Nie znaleziono zgłoszenia.")
    return r


def update_report(db: DbSession, actor: Actor, report_id: uuid.UUID, body: ReportUpdate) -> Report:
    r = load_owned(db, report_id, actor, for_update=True)
    if r.status not in ("active", "reserved"):
        raise ApiError(409, "invalid_state", "Można edytować tylko aktywne zgłoszenia.")
    if r.hidden_at is not None:
        raise ApiError(409, "hidden", "Zgłoszenie zostało ukryte przez moderację i nie może być edytowane.")
    data = body.model_dump(exclude_unset=True)
    category = data.get("category", r.category)
    cat = cats.validate_category(category)
    if "category" in data and "attributes" not in data and category != r.category:
        r.attributes = {}
    if "attributes" in data or "category" in data:
        r.attributes = cats.validate_attributes(cat.key, data.get("attributes", r.attributes))
    r.category = cat.key
    if "colors" in data:
        r.colors = cats.validate_colors(data["colors"])
    if "title" in data:
        r.title = clean_text(data["title"], 80)
        if len(r.title) < 3:
            raise invalid("bad_title", "Tytuł jest za krótki.")
    if "description" in data:
        r.description = clean_text(data["description"], 1000, multiline=True)
    if "area_label" in data:
        r.area_label = clean_text(data["area_label"], 80) or None
    if r.kind == "found":
        if data.get("holding"):
            r.holding = data["holding"]
        if "holding_note" in data:
            r.holding_note = clean_text(data["holding_note"], 120) or None
        if "claim_question" in data:
            r.private.claim_question = clean_text(data["claim_question"], 200) or None
    elif any(k in data and data[k] for k in ("holding", "holding_note", "claim_question")):
        raise invalid("bad_field", "Te pola dotyczą tylko rzeczy znalezionych.")
    if "secret_details" in data:
        r.private.secret_details = clean_text(data["secret_details"], 500, multiline=True) or None
    _check_public_text(r.title, r.description, r.area_label, r.holding_note)
    if "occurred_from" in data or "occurred_to" in data:
        r.occurred_from, r.occurred_to = _norm_times(
            data.get("occurred_from") or r.occurred_from, data.get("occurred_to") or r.occurred_to
        )
    if body.location is not None:
        loc = body.location
        ensure_in_pilot(loc.lat, loc.lon)
        area = public_area(loc.lat, loc.lon, loc.uncertainty_m)
        r.cell_id, r.public_lat, r.public_lon, r.area_radius_m = area.cell_id, area.lat, area.lon, area.radius_m
        pv = r.private
        pv.exact_lat, pv.exact_lon = loc.lat, loc.lon
        pv.accuracy_m, pv.uncertainty_m, pv.location_source = loc.accuracy_m, loc.uncertainty_m, loc.source
    if body.photo_ids is not None:
        _attach_photos(db, r, actor, body.photo_ids)
    elif "attributes" in data and r.attributes.get("subtype") in DOCUMENT_SUBTYPES:
        if db.scalar(select(func.count()).select_from(Photo).where(Photo.report_id == r.id)):
            raise invalid("photo_not_allowed", "Usuń zdjęcia — dokumentów nie publikujemy na zdjęciach.")
    r.search_text = build_search_text(r)
    r.updated_at = now_utc()
    _audit(db, actor.guest_id, "report", r.id, "edit")
    db.commit()
    db.refresh(r)
    return r


def visible_report(db: DbSession, report_id: uuid.UUID) -> Report:
    r = db.get(Report, report_id)
    if r is None or r.hidden_at is not None or r.status not in PUBLIC_REPORT_STATES:
        raise not_found("Zgłoszenie nie istnieje, zostało zamknięte lub ukryte.")
    return r


# ---------------------------------------------------------------- wyszukiwanie
NEAR_EXPAND = {
    "navy": ["blue", "black"],
    "blue": ["navy"],
    "gray": ["silver", "black"],
    "silver": ["gray", "white"],
    "beige": ["brown", "white"],
    "brown": ["beige"],
    "gold": ["yellow"],
    "yellow": ["gold"],
    "pink": ["red", "purple"],
    "red": ["pink", "orange"],
    "orange": ["red"],
    "purple": ["pink"],
    "black": ["navy", "gray"],
    "white": ["beige", "silver"],
}


def _encode_cursor(d: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).decode().rstrip("=")


def _decode_cursor(c: str) -> dict[str, Any]:
    try:
        pad = "=" * (-len(c) % 4)
        d = json.loads(base64.urlsafe_b64decode(c + pad))
        if not isinstance(d, dict):
            raise ValueError
        return d
    except (ValueError, json.JSONDecodeError) as e:
        raise invalid("bad_cursor", "Nieprawidłowy kursor stronicowania.") from e


def search(
    db: DbSession,
    *,
    actor: Actor | None,
    kind: str | None,
    category: str | None,
    subtype: str | None,
    colors: list[str],
    brand: str | None,
    q: str | None,
    lat: float | None,
    lon: float | None,
    radius_m: int | None,
    bbox: tuple[float, float, float, float] | None,
    date_from: datetime | None,
    date_to: datetime | None,
    sort: str,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    where = ["r.status IN ('active', 'reserved')", "r.hidden_at IS NULL"]
    params: dict[str, Any] = {}
    if kind:
        where.append("r.kind = :kind")
        params["kind"] = kind
    if category:
        cats.validate_category(category)
        where.append("r.category = :category")
        params["category"] = category
    if subtype:
        where.append("r.attributes->>'subtype' = :subtype")
        params["subtype"] = subtype
    if colors:
        cats.validate_colors(colors)
        expanded = sorted({c for col in colors for c in [col, *NEAR_EXPAND.get(col, [])]} | {"multi"})
        where.append("r.colors && CAST(:colors AS varchar[])")
        params["colors"] = expanded
    if brand:
        where.append("f_unaccent(lower(r.attributes->>'brand')) LIKE f_unaccent(lower(:brand))")
        params["brand"] = "%" + brand.replace("%", "").replace("_", "")[:40] + "%"
    if date_from:
        where.append("r.occurred_to >= :dfrom")
        params["dfrom"] = date_from
    if date_to:
        where.append("r.occurred_from <= :dto")
        params["dto"] = date_to
    if lat is not None and lon is not None:
        params["lat"], params["lon"] = lat, lon
        params["radius"] = radius_m or 3000
        where.append("ST_DWithin(r.public_geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius)")
        dist_sql = "ST_Distance(r.public_geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)"
    else:
        dist_sql = "NULL::float8"
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        where.append("r.public_lat BETWEEN :bminlat AND :bmaxlat AND r.public_lon BETWEEN :bminlon AND :bmaxlon")
        params.update(bminlat=min_lat, bmaxlat=max_lat, bminlon=min_lon, bmaxlon=max_lon)
    qn = clean_text(q, 120) if q else ""
    if qn:
        params["q"] = qn
        text_sql = "word_similarity(f_unaccent(lower(:q)), f_unaccent(lower(r.search_text)))"
        where.append(
            "(f_unaccent(lower(:q)) <% f_unaccent(lower(r.search_text)) "
            "OR f_unaccent(lower(r.search_text)) LIKE '%' || f_unaccent(lower(:q)) || '%')"
        )
    else:
        text_sql = "NULL::float4"

    if sort == "relevance" and not qn:
        sort = "nearest" if "lat" in params else "newest"
    if sort == "nearest" and "lat" not in params:
        sort = "newest"

    if sort == "relevance":
        order, key_cols, cmp = "text_sim DESC, id DESC", ("text_sim", "id"), "<"
    elif sort == "nearest":
        order, key_cols, cmp = "dist ASC, id ASC", ("dist", "id"), ">"
    else:
        order, key_cols, cmp = "published_at DESC, id DESC", ("published_at", "id"), "<"

    outer_where = ""
    if cursor:
        c = _decode_cursor(cursor)
        if c.get("s") != sort:
            raise invalid("bad_cursor", "Kursor nie pasuje do sortowania.")
        params["c0"] = datetime.fromisoformat(c["k"]) if sort == "newest" else float(c["k"])
        params["c1"] = uuid.UUID(c["id"])
        outer_where = f"WHERE ({key_cols[0]}, {key_cols[1]}) {cmp} (:c0, :c1)"
    params["lim"] = limit + 1
    sql = f"""
        WITH base AS (
            SELECT r.id, r.published_at, {dist_sql} AS dist, {text_sql} AS text_sim
            FROM reports r
            WHERE {" AND ".join(where)}
        )
        SELECT id, published_at, dist, text_sim FROM base {outer_where}
        ORDER BY {order}
        LIMIT :lim
    """
    db.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = 0.45"))
    rows = db.execute(text(sql), params).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    ids = [r.id for r in rows]
    reports = {r.id: r for r in db.scalars(select(Report).where(Report.id.in_(ids))).all()} if ids else {}
    ctx = QueryCtx(
        category=category,
        colors=colors,
        attrs={k: v for k, v in {"brand": brand, "subtype": subtype}.items() if v},
        text=qn or None,
        lat=lat,
        lon=lon,
        radius_m=radius_m or (3000 if lat is not None else None),
        time_from=date_from,
        time_to=date_to,
        category_is_filter=True,
    )
    items = []
    for row in rows:
        rep = reports[row.id]
        cand = _cand(rep, text_sim=row.text_sim)
        ex = explain(ctx, cand)
        items.append(
            public_report(
                rep,
                actor=actor,
                distance_m=rounded_distance_m(row.dist) if row.dist is not None else None,
                match={"reasons": ex.reasons, "warnings": ex.warnings},
            )
        )
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        k = {"newest": iso(last.published_at), "nearest": last.dist, "relevance": last.text_sim}[sort]
        next_cursor = _encode_cursor({"s": sort, "k": k, "id": str(last.id)})
    db.commit()
    return {"items": items, "next_cursor": next_cursor, "sort": sort}


def _cand(r: Report, text_sim: float | None = None, image_sim: float | None = None) -> Cand:
    return Cand(
        id=r.id,
        kind=r.kind,
        category=r.category,
        colors=list(r.colors or []),
        attrs=dict(r.attributes or {}),
        lat=r.public_lat,
        lon=r.public_lon,
        occurred_from=r.occurred_from,
        occurred_to=r.occurred_to,
        text_sim=text_sim,
        image_sim=image_sim,
    )


def suggestions_for_empty(radius_m: int | None, has_dates: bool, has_filters: bool) -> list[dict[str, str]]:
    out = []
    if radius_m is not None and radius_m < 10000:
        out.append({"action": "expand_radius", "label": "Poszerz obszar wyszukiwania"})
    if has_dates:
        out.append({"action": "expand_dates", "label": "Poszerz zakres dat"})
    if has_filters:
        out.append({"action": "clear_filters", "label": "Usuń część filtrów (np. kolor)"})
    out.append({"action": "create_lost", "label": "Dodaj zgłoszenie zguby — pokażemy Ci nowe dopasowania"})
    out.append({"action": "share", "label": "Udostępnij link do zgłoszenia w lokalnej grupie lub na uczelni"})
    return out


def map_areas(
    db: DbSession,
    *,
    bbox: tuple[float, float, float, float],
    kind: str | None,
    category: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[dict[str, Any]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    if max_lat - min_lat > 1.0 or max_lon - min_lon > 1.5:
        raise invalid("bbox_too_large", "Przybliż mapę, aby zobaczyć zgłoszenia.")
    where = [
        "status IN ('active','reserved')",
        "hidden_at IS NULL",
        "public_lat BETWEEN :a AND :b",
        "public_lon BETWEEN :c AND :d",
    ]
    params: dict[str, Any] = {"a": min_lat, "b": max_lat, "c": min_lon, "d": max_lon}
    if kind:
        where.append("kind = :kind")
        params["kind"] = kind
    if category:
        where.append("category = :category")
        params["category"] = category
    if date_from:
        where.append("occurred_to >= :dfrom")
        params["dfrom"] = date_from
    if date_to:
        where.append("occurred_from <= :dto")
        params["dto"] = date_to
    sql = f"""
        SELECT cell_id, min(public_lat) AS lat, min(public_lon) AS lon, max(area_radius_m) AS radius,
               count(*) AS n, count(*) FILTER (WHERE kind = 'lost') AS lost,
               count(*) FILTER (WHERE kind = 'found') AS found,
               (array_agg(id ORDER BY published_at DESC))[1:3] AS sample
        FROM reports WHERE {" AND ".join(where)}
        GROUP BY cell_id ORDER BY n DESC LIMIT 400
    """
    rows = db.execute(text(sql), params).all()
    return [
        {
            "cell_id": r.cell_id,
            "lat": r.lat,
            "lon": r.lon,
            "radius_m": r.radius,
            "count": r.n,
            "lost": r.lost,
            "found": r.found,
            "sample_ids": [str(x) for x in r.sample],
        }
        for r in rows
    ]


# ---------------------------------------------------------------- dopasowania
def matches_for(db: DbSession, actor: Actor, report_id: uuid.UUID) -> dict[str, Any]:
    src = load_owned(db, report_id, actor)
    if src.status not in ("active", "reserved", "expired"):
        return {"strong": [], "possible": [], "weak_count": 0, "notice": "Zgłoszenie jest zamknięte."}
    target_kind = "found" if src.kind == "lost" else "lost"
    if src.kind == "lost":
        time_sql = "r.occurred_to >= :sfrom - interval '1 day' AND r.occurred_from <= :sto + interval '60 days'"
    else:
        time_sql = "r.occurred_from <= :sto + interval '1 day' AND r.occurred_to >= :sfrom - interval '60 days'"
    sql = f"""
        SELECT r.id,
               similarity(f_unaccent(lower(r.search_text)), f_unaccent(lower(:stext))) AS text_sim,
               (SELECT max(1 - (cp.embedding <=> sp.embedding))
                  FROM photos cp JOIN photos sp ON sp.report_id = :src AND sp.purpose = 'report'
                       AND sp.embedding_status = 'ready' AND sp.embedding_model = cp.embedding_model
                 WHERE cp.report_id = r.id AND cp.purpose = 'report' AND cp.embedding_status = 'ready'
               ) AS image_sim
        FROM reports r
        WHERE r.kind = :tkind AND r.status IN ('active', 'reserved') AND r.hidden_at IS NULL
          AND r.owner_id <> :owner
          AND ST_DWithin(r.public_geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 12000)
          AND {time_sql}
        ORDER BY r.published_at DESC
        LIMIT 400
    """
    rows = db.execute(
        text(sql),
        {
            "src": src.id,
            "stext": src.search_text,
            "tkind": target_kind,
            "owner": actor.guest_id,
            "lat": src.public_lat,
            "lon": src.public_lon,
            "sfrom": src.occurred_from,
            "sto": src.occurred_to,
        },
    ).all()
    ids = [r.id for r in rows]
    reps = {r.id: r for r in db.scalars(select(Report).where(Report.id.in_(ids))).all()} if ids else {}
    ctx = QueryCtx(
        category=src.category,
        colors=list(src.colors or []),
        attrs=dict(src.attributes or {}),
        text=None,
        lat=src.public_lat,
        lon=src.public_lon,
        time_from=src.occurred_from,
        time_to=src.occurred_to,
        source_kind=src.kind,
    )
    sims = sorted((float(r.image_sim) for r in rows if r.image_sim is not None), reverse=True)
    distinct_best = sims[0] if len(sims) >= 2 and sims[0] - sims[1] >= DISTINCT_MARGIN else None
    scored = []
    for row in rows:
        rep = reps[row.id]
        same_cat = rep.category == src.category
        img = float(row.image_sim) if row.image_sim is not None else None
        if not same_cat and (img is None or img < SIM_RELATED):
            continue
        cand = _cand(rep, text_sim=None, image_sim=img)
        cand.image_distinct = distinct_best is not None and img == distinct_best
        ex = explain(ctx, cand)
        if row.text_sim is not None and row.text_sim >= 0.3:
            ex.reasons.append("Podobne słowa w opisie")
            ex.score += 0.5
        scored.append((ex, rep))
    scored.sort(key=lambda t: (-t[0].score, str(t[1].id)))
    strong, possible, weak = [], [], 0
    for ex, rep in scored:
        item = public_report(
            rep,
            actor=actor,
            distance_m=ex.distance_m,
            match={"tier": ex.tier, "reasons": ex.reasons, "warnings": ex.warnings},
        )
        if ex.tier == "strong" and len(strong) < 20:
            strong.append(item)
        elif ex.tier == "possible" and len(possible) < 30:
            possible.append(item)
        else:
            weak += 1
    db.commit()
    notice = None
    if not strong and not possible:
        notice = (
            "Brak przekonujących dopasowań. To nie znaczy, że nikt nie znalazł Twojej rzeczy — "
            "nowe zgłoszenia sprawdzamy na bieżąco."
            if src.kind == "lost"
            else "Brak przekonujących dopasowań wśród zgłoszonych zgub."
        )
    return {"strong": strong, "possible": possible, "weak_count": weak, "notice": notice}


def ensure_owner_or_404(r: Report | None, actor: Actor) -> Report:
    if r is None or r.owner_id != actor.guest_id:
        raise not_found("Nie znaleziono zgłoszenia.")
    return r


def forbid_if_hidden(r: Report) -> None:
    if r.hidden_at is not None:
        raise forbidden("Zgłoszenie zostało ukryte przez moderację.")
