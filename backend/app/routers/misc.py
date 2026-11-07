"""Metadane, asystent wyszukiwania, zgłoszenia nadużyć, moderacja, strona udostępniania, healthcheck."""

from __future__ import annotations

import html
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app import __version__, ratelimit
from app.config import get_settings
from app.db import get_db
from app.domain import categories as cats
from app.domain.nlquery import LANDMARKS, nearest_landmark, parse_query
from app.errors import ApiError, conflict, not_found
from app.models import AbuseReport, Claim, Guest, Message, Report, Session
from app.schemas import AbuseIn, AdminResolveIn, ParseIn, iso
from app.security import Actor, current_actor, ip_key, now_utc, require_admin
from app.services import ai
from app.services import claims as claim_svc
from app.services import photos as photo_svc
from app.services.claims import SAFETY_TIPS
from app.services.reports import public_report

router = APIRouter(tags=["inne"])
AUTO_HIDE_THRESHOLD = 3


@router.get("/health")
def health(db: DbSession = Depends(get_db)) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    eng = ai.engine()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "db": db_ok,
        "storage": photo_svc.storage_writable(),
        "ai": eng.info(),
    }


@router.get("/v1/meta")
def meta() -> dict[str, Any]:
    s = get_settings()
    eng = ai.engine()
    return cats.meta_payload() | {
        "pilot": {
            "name": s.pilot_name,
            "center": {"lat": s.pilot_center_lat, "lon": s.pilot_center_lon},
            "bounds": {
                "min_lat": s.pilot_min_lat,
                "max_lat": s.pilot_max_lat,
                "min_lon": s.pilot_min_lon,
                "max_lon": s.pilot_max_lon,
            },
            "grid_cell_m": s.grid_cell_m,
        },
        "landmarks": [{k: v for k, v in lm.items() if k != "aliases"} for lm in LANDMARKS],
        "ai": {"status": eng.status if eng.status != "not_loaded" else ("ready" if eng.load() else eng.status)},
        "safety_tips": SAFETY_TIPS,
        "retention": {
            "active_days": s.report_active_days,
            "purge_after_days": s.report_purge_after_days,
            "orphan_photo_hours": s.orphan_photo_hours,
        },
        "limits": {"max_upload_mb": s.max_upload_bytes // (1024 * 1024), "max_photos": 4},
    }


@router.post("/v1/search/parse")
def parse(body: ParseIn) -> dict[str, Any]:
    return parse_query(body.text).as_dict()


@router.get("/v1/places/suggest")
def place_suggest(lat: float, lon: float) -> dict[str, Any]:
    lm = nearest_landmark(lat, lon)
    return {"label": f"okolice: {lm['name']}" if lm else None}


# ------------------------------------------------------------- nadużycia
@router.post("/v1/abuse-reports", status_code=201)
def report_abuse(
    body: AbuseIn, request: Request, actor: Actor = Depends(current_actor), db: DbSession = Depends(get_db)
) -> dict[str, Any]:
    ratelimit.check(db, "abuse", actor.guest_id, ip_key(request))
    report_id: uuid.UUID | None = None
    try:
        tid = uuid.UUID(body.target_id) if body.target_type != "message" else None
    except ValueError as e:
        raise not_found() from e
    if body.target_type == "report":
        r = db.get(Report, tid)
        if r is None or r.hidden_at is not None:
            raise not_found("Nie znaleziono zgłoszenia.")
        report_id = r.id
    elif body.target_type == "claim":
        claim, _ = claim_svc.load_claim(db, tid, actor)  # tylko uczestnik
        report_id = claim.report_id
    else:
        try:
            mid = int(body.target_id)
        except ValueError as e:
            raise not_found() from e
        m = db.get(Message, mid)
        if m is None:
            raise not_found()
        claim_svc.load_claim(db, m.claim_id, actor)
    ab = AbuseReport(
        id=uuid.uuid4(),
        reporter_id=actor.guest_id,
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        details=body.details.strip()[:500],
    )
    db.add(ab)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise conflict("already_reported", "To zgłoszenie nadużycia już przyjęliśmy.") from e
    hidden = False
    if body.target_type == "report" and report_id is not None:
        n = (
            db.scalar(
                select(func.count(func.distinct(AbuseReport.reporter_id))).where(
                    AbuseReport.target_type == "report",
                    AbuseReport.target_id == str(report_id),
                    AbuseReport.status == "open",
                )
            )
            or 0
        )
        if n >= AUTO_HIDE_THRESHOLD:
            _hide(db, report_id, "Automatycznie ukryte po kilku zgłoszeniach nadużycia — czeka na moderację.")
            hidden = True
    db.commit()
    return {
        "id": str(ab.id),
        "status": "received",
        "auto_hidden": hidden,
        "message": "Dziękujemy. Moderator sprawdzi zgłoszenie. Możesz też zablokować kontakt w rozmowie.",
    }


def _hide(db: DbSession, report_id: uuid.UUID, reason: str) -> None:
    r = db.scalar(select(Report).where(Report.id == report_id).with_for_update(of=Report))
    if r is None or r.hidden_at is not None:
        return
    r.hidden_at = now_utc()
    r.hidden_reason = reason
    # Ukrycie blokuje też dalsze użycie: zamyka otwarte sprawy i wyklucza z wyszukiwania/indeksu.
    claim_svc.touch_report_claims_closed_on_hide(db, r.id)


# ------------------------------------------------------------- moderacja
@router.get("/v1/admin/abuse-reports", dependencies=[Depends(require_admin)])
def admin_list(status: str = "open", db: DbSession = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(
        select(AbuseReport).where(AbuseReport.status == status).order_by(AbuseReport.created_at.desc()).limit(200)
    ).all()
    out = []
    for a in rows:
        target: dict[str, Any] = {}
        if a.target_type == "report":
            r = db.get(Report, uuid.UUID(a.target_id))
            if r:
                target = {
                    "title": r.title,
                    "kind": r.kind,
                    "status": r.status,
                    "hidden": r.hidden_at is not None,
                    "description": r.description[:300],
                    "owner_id": str(r.owner_id),
                }
        elif a.target_type == "claim":
            c = db.get(Claim, uuid.UUID(a.target_id))
            if c:
                target = {"status": c.status, "report_id": str(c.report_id), "claimant_id": str(c.claimant_id)}
        else:
            m = db.get(Message, int(a.target_id))
            if m:
                # Moderator widzi tylko zgłoszoną wiadomość, nie całą rozmowę.
                target = {"body": m.body[:500], "sender_id": str(m.sender_id) if m.sender_id else None}
        out.append(
            {
                "id": str(a.id),
                "target_type": a.target_type,
                "target_id": a.target_id,
                "reason": a.reason,
                "details": a.details,
                "created_at": iso(a.created_at),
                "target": target,
            }
        )
    return {"items": out}


@router.post("/v1/admin/abuse-reports/{abuse_id}/resolve", dependencies=[Depends(require_admin)])
def admin_resolve(abuse_id: uuid.UUID, body: AdminResolveIn, db: DbSession = Depends(get_db)) -> dict[str, Any]:
    a = db.get(AbuseReport, abuse_id)
    if a is None:
        raise not_found()
    if body.action in ("hide_report", "unhide_report"):
        if a.target_type != "report":
            raise ApiError(422, "bad_action", "Ta akcja dotyczy zgłoszeń.")
        rid = uuid.UUID(a.target_id)
        if body.action == "hide_report":
            _hide(db, rid, body.note or "Ukryte przez moderację.")
        else:
            r = db.get(Report, rid)
            if r:
                r.hidden_at, r.hidden_reason = None, None
    elif body.action == "ban_guest":
        guest_id = None
        if a.target_type == "report":
            r = db.get(Report, uuid.UUID(a.target_id))
            guest_id = r.owner_id if r else None
        elif a.target_type == "message":
            m = db.get(Message, int(a.target_id))
            guest_id = m.sender_id if m else None
        elif a.target_type == "claim":
            c = db.get(Claim, uuid.UUID(a.target_id))
            guest_id = c.claimant_id if c else None
        if guest_id:
            g = db.get(Guest, guest_id)
            if g:
                g.banned_at = now_utc()
                g.ban_reason = body.note[:300] or "Naruszenie zasad"
                db.execute(Session.__table__.update().where(Session.guest_id == g.id).values(revoked_at=now_utc()))
                for r in db.scalars(select(Report).where(Report.owner_id == g.id, Report.hidden_at.is_(None))).all():
                    _hide(db, r.id, "Autor zablokowany przez moderację.")
    # Zamyka wszystkie otwarte zgłoszenia nadużyć dotyczące tego samego celu.
    for other in db.scalars(
        select(AbuseReport).where(
            AbuseReport.target_type == a.target_type, AbuseReport.target_id == a.target_id, AbuseReport.status == "open"
        )
    ).all():
        other.status = "dismissed" if body.action == "dismiss" else "actioned"
        other.resolution_note = body.note[:300]
        other.resolved_at = now_utc()
    db.commit()
    return {"ok": True}


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_page() -> str:
    return ADMIN_HTML


# ------------------------------------------------------------- strona udostępniania
@router.get("/r/{report_id}", response_class=HTMLResponse, include_in_schema=False)
def share_page(report_id: uuid.UUID, db: DbSession = Depends(get_db)) -> HTMLResponse:
    r = db.get(Report, report_id)
    if r is None or r.hidden_at is not None or r.status not in ("active", "reserved"):
        return HTMLResponse(
            _page("Zgłoszenie niedostępne", "<p>To zgłoszenie zostało zamknięte lub usunięte.</p>"), 404
        )
    pub = public_report(r)
    esc = html.escape
    kind = "Znaleziono" if r.kind == "found" else "Zgubiono"
    img = ""
    if pub["photos"]:
        img = f'<img src="{esc(pub["photos"][0]["url"])}" alt="Zdjęcie przedmiotu">'
    attrs = "".join(f"<li>{esc(a['label'])}: {esc(str(a['value']))}</li>" for a in pub["attributes"])
    colors = ", ".join(cats.COLOR_PL.get(c, c) for c in pub["colors"])
    body = f"""
      <span class="tag {r.kind}">{kind}</span>
      <h1>{esc(r.title)}</h1>
      {img}
      <p>{esc(r.description)}</p>
      <ul>{attrs}{f"<li>Kolor: {esc(colors)}</li>" if colors else ""}</ul>
      <p class="muted">Przybliżony obszar: {esc(r.area_label or "Kraków")} · kiedy: {r.occurred_from:%d.%m.%Y}</p>
      <p><strong>To Twoja rzecz?</strong> Otwórz zgłoszenie w aplikacji Findini i złóż prywatne roszczenie.
      Nikt nie poprosi Cię o opłatę ani przelew.</p>
      <p class="muted">Identyfikator zgłoszenia: {esc(str(r.id))}</p>
    """
    return HTMLResponse(_page(f"{kind}: {r.title}", body))


def _page(title: str, body: str) -> str:
    t = html.escape(title)
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{t} — Findini</title>
<meta name="robots" content="noindex">
<style>
body{{font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:16px;color:#14302E;background:#FBF8F3}}
img{{max-width:100%;border-radius:16px}} .tag{{display:inline-block;padding:4px 10px;border-radius:99px;font-weight:600}}
.found{{background:#D8F0E6;color:#0B5C4A}} .lost{{background:#FCE3D3;color:#8A3B12}} .muted{{color:#5A6B69}}
header{{font-weight:800;font-size:20px;color:#0F5B57;margin-bottom:12px}}
</style></head><body><header>Findini</header>{body}</body></html>"""


ADMIN_HTML = """<!doctype html><html lang="pl"><head><meta charset="utf-8"><title>Findini — moderacja</title>
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px}
.card{border:1px solid #ccd;border-radius:12px;padding:12px;margin:10px 0} button{margin-right:6px}
code{background:#eef;padding:2px 4px;border-radius:4px}</style></head><body>
<h1>Findini — moderacja zgłoszeń nadużyć</h1>
<p>Token administratora (FINDINI_ADMIN_TOKEN) jest trzymany tylko w pamięci tej karty.</p>
<input id="tok" type="password" placeholder="Token administratora" size="50"> <button onclick="load()">Wczytaj</button>
<div id="list"></div>
<script>
let token='';
async function api(path, opts={}){opts.headers=Object.assign({'X-Admin-Token':token,'Content-Type':'application/json'},opts.headers||{});
 const r=await fetch(path,opts); if(!r.ok){alert('Błąd '+r.status); throw new Error(r.status)} return r.json();}
function esc(s){const d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML}
async function load(){token=document.getElementById('tok').value; const d=await api('/v1/admin/abuse-reports');
 const el=document.getElementById('list'); el.innerHTML=d.items.length?'':'<p>Brak otwartych zgłoszeń.</p>';
 for(const a of d.items){const c=document.createElement('div'); c.className='card';
  c.innerHTML=`<b>${esc(a.reason)}</b> · ${esc(a.target_type)} <code>${esc(a.target_id)}</code> · ${esc(a.created_at)}
  <p>${esc(a.details)}</p><pre>${esc(JSON.stringify(a.target,null,2))}</pre>`;
  for(const act of ['dismiss','hide_report','unhide_report','ban_guest']){const b=document.createElement('button');
   b.textContent=act; b.onclick=async()=>{const note=prompt('Notatka (opcjonalnie)')||'';
   await api(`/v1/admin/abuse-reports/${a.id}/resolve`,{method:'POST',body:JSON.stringify({action:act,note})}); load();};
   c.appendChild(b);} el.appendChild(c);} }
</script></body></html>"""
