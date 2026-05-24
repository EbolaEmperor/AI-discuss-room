# server/routes/web.py
import markdown as md
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from server.db import get_db
from server.models import Room, Participant, Post
from server.auth import err

router = APIRouter(tags=["web"])


def _templates():
    from server.main import templates
    return templates


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    rooms = db.query(Room).order_by(Room.id.desc()).all()
    out = []
    for r in rooms:
        pc = db.query(func.count(Participant.id)).filter(Participant.room_id == r.id).scalar()
        postc = db.query(func.count(Post.id)).filter(Post.room_id == r.id).scalar()
        out.append({"id": r.id, "title": r.title, "status": r.status,
                    "participant_count": pc, "post_count": postc})
    return _templates().TemplateResponse(request, "index.html", {"rooms": out})


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
        {"room": room, "participants": parts, "current_proofs": current_proofs,
         "problem_html": problem_html},
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
    return _templates().TemplateResponse(request, "partials/timeline.html", {"posts": items})
