# server/routes/web.py
import markdown as md
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from server.db import get_db
from server.models import Room, Participant, Post
from server.auth import err, current_admin_or_none
from server.avatars import avatar_url

router = APIRouter(tags=["web"])


def _templates():
    from server.main import templates
    return templates


def _ctx(request: Request, db: Session, extra: dict | None = None) -> dict:
    base = {
        "current_admin": current_admin_or_none(request, db),
        "avatar_url": avatar_url,
    }
    if extra:
        base.update(extra)
    return base


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    rooms = db.query(Room).order_by(Room.id.desc()).all()
    out = []
    for r in rooms:
        pc = db.query(func.count(Participant.id)).filter(Participant.room_id == r.id).scalar()
        postc = db.query(func.count(Post.id)).filter(Post.room_id == r.id).scalar()
        names = [n for (n,) in db.query(Participant.name).filter(Participant.room_id == r.id).all()]
        out.append({"id": r.id, "title": r.title, "status": r.status,
                    "participant_count": pc, "post_count": postc,
                    "participants": names})
    return _templates().TemplateResponse(request, "index.html", _ctx(request, db, {"rooms": out}))


def _room_or_404(db: Session, room_id: int) -> Room:
    r = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not r:
        err("not_found", "room not found", http=404)
    return r


@router.get("/room/{room_id}", response_class=HTMLResponse)
def room_view(request: Request, room_id: int, db: Session = Depends(get_db)):
    room = _room_or_404(db, room_id)
    participants = db.query(Participant).filter(Participant.room_id == room_id).all()
    current = (db.query(Post)
               .filter(Post.room_id == room_id,
                       Post.type.in_(("proof", "revision")),
                       Post.superseded_by.is_(None)).all())
    current_proofs = []
    for c in current:
        agrees = db.query(func.count(Post.id)).filter(
            Post.room_id == room_id, Post.type == "agree", Post.parent_id == c.id
        ).scalar()
        current_proofs.append({"id": c.id, "author": c.author.name, "agree_count": agrees})
    problem_html = md.markdown(room.problem)
    parts = [{"name": p.name, "role": p.role,
              "has_published_first": p.first_post_at is not None}
             for p in participants]
    return _templates().TemplateResponse(
        request, "room.html",
        _ctx(request, db, {"room": room, "participants": parts, "current_proofs": current_proofs,
         "problem_html": problem_html}),
    )


@router.get("/room/{room_id}/timeline-partial", response_class=HTMLResponse)
def timeline_partial(request: Request, room_id: int, db: Session = Depends(get_db)):
    _room_or_404(db, room_id)
    posts = db.query(Post).filter(Post.room_id == room_id).order_by(Post.id.asc()).all()
    items = []
    for p in posts:
        items.append({
            "id": p.id, "type": p.type, "author": p.author.name,
            "parent_id": p.parent_id, "superseded_by": p.superseded_by,
            "ts": p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "body": p.body or "",
            "body_preview": bool(p.body),
        })
    return _templates().TemplateResponse(request, "partials/timeline.html", _ctx(request, db, {"posts": items}))


from fastapi import Form, status as http_status
from fastapi.responses import RedirectResponse
from datetime import datetime
from server.auth import require_admin


@router.get("/admin/new-room", response_class=HTMLResponse)
def new_room_form(request: Request, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    return _templates().TemplateResponse(request, "admin_new_room.html", _ctx(request, db))


@router.post("/admin/new-room")
def new_room_submit(
    title: str = Form(...),
    problem: str = Form(...),
    max_rounds: int = Form(20),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    room = Room(title=title, problem=problem, max_rounds=max_rounds,
                status="open", created_at=datetime.utcnow())
    db.add(room); db.commit(); db.refresh(room)
    return RedirectResponse(url=f"/room/{room.id}", status_code=http_status.HTTP_303_SEE_OTHER)


@router.get("/room/{room_id}/post/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, room_id: int, post_id: int, db: Session = Depends(get_db)):
    _room_or_404(db, room_id)
    post = db.query(Post).filter(Post.id == post_id, Post.room_id == room_id).one_or_none()
    if not post:
        err("not_found", "post not found", http=404)
    return _templates().TemplateResponse(
        request, "post_detail.html",
        _ctx(request, db, {"post": type("PostView", (), {
            "id": post.id, "type": post.type, "room_id": post.room_id,
            "author_name": post.author.name, "created_at": post.created_at,
            "parent_id": post.parent_id, "superseded_by": post.superseded_by,
            "body": post.body,
        })()}))


@router.get("/room/{room_id}/audit", response_class=HTMLResponse)
def room_audit(request: Request, room_id: int, db: Session = Depends(get_db)):
    room = _room_or_404(db, room_id)
    from server.models import Read
    posts = db.query(Post).filter(Post.room_id == room_id).all()
    reads = (db.query(Read).join(Participant, Read.participant_id == Participant.id)
             .filter(Participant.room_id == room_id).all())
    events = []
    for p in posts:
        events.append({"ts": p.created_at.isoformat(), "kind": "post", "by": p.author.name,
                       "detail": f"#{p.id} {p.type}" + (f" → #{p.parent_id}" if p.parent_id else "")})
    for r in reads:
        events.append({"ts": r.read_at.isoformat(), "kind": "read", "by": r.participant.name,
                       "detail": f"read post #{r.post_id}"})
    events.sort(key=lambda e: e["ts"])
    return _templates().TemplateResponse(request, "audit.html", _ctx(request, db, {"room": room, "events": events}))


from server.avatars import fallback_svg


@router.get("/avatar-fallback/{name}")
def avatar_fallback(name: str):
    return Response(
        content=fallback_svg(name),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=31536000"},
    )
