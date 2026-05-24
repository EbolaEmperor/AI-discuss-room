# server/routes/web.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from server.db import get_db
from server.models import Room, Participant, Post
from server.auth import err, current_admin_or_none, authenticate_admin
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
        agrees = (db.query(Post)
                  .filter(Post.room_id == room_id, Post.type == "agree", Post.parent_id == c.id)
                  .all())
        # body preview: first non-empty line
        preview = ""
        if c.body:
            for line in c.body.splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    preview = line[:140]
                    break
        # version number: count revisions back to root
        version = 1
        cur = c
        while cur.parent_id is not None and cur.type == "revision":
            version += 1
            cur = db.query(Post).filter(Post.id == cur.parent_id).one()
        current_proofs.append({
            "id": c.id, "author": c.author.name, "preview": preview,
            "agree_count": len(agrees),
            "agreed_by": [a.author.name for a in agrees],
            "ts": c.created_at, "version": version,
            "is_consensus": (room.status == "closed_consensus" and room.closed_proof_id == c.id),
        })

    consensus_proof = None
    if room.status == "closed_consensus" and room.closed_proof_id:
        cp = db.query(Post).filter(Post.id == room.closed_proof_id).one_or_none()
        if cp:
            preview = ""
            if cp.body:
                for line in cp.body.splitlines():
                    line = line.strip().lstrip("#").strip()
                    if line:
                        preview = line[:140]
                        break
            consensus_proof = {"id": cp.id, "author": cp.author.name, "preview": preview}

    from server.markdown_render import render
    problem_html = render(room.problem)
    parts = [{"name": p.name, "role": p.role,
              "has_published_first": p.first_post_at is not None}
             for p in participants]
    return _templates().TemplateResponse(
        request, "room.html",
        _ctx(request, db, {
            "room": room, "participants": parts, "current_proofs": current_proofs,
            "problem_html": problem_html, "consensus_proof": consensus_proof,
            "include_katex": True,
        }),
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
from server.auth import require_admin, require_admin_session
from server.models import AdminUser


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
    from server.lineage import lineage_of, comments_for_lineage
    from server.markdown_render import render
    room = _room_or_404(db, room_id)
    post = db.query(Post).filter(Post.id == post_id, Post.room_id == room_id).one_or_none()
    if not post:
        err("not_found", "post not found", http=404)

    if post.type in ("proof", "revision"):
        line = lineage_of(db, post)
    else:
        # Comments / agree don't have a "lineage" — show parent's lineage if possible
        anchor = post
        while anchor.type not in ("proof", "revision") and anchor.parent_id is not None:
            anchor = db.query(Post).filter(Post.id == anchor.parent_id).one()
        line = lineage_of(db, anchor) if anchor.type in ("proof", "revision") else [post]

    # Version labels
    versions = []
    for idx, p in enumerate(line, start=1):
        is_latest = (p.superseded_by is None)
        versions.append({
            "id": p.id, "n": idx, "ts": p.created_at,
            "label_state": "latest" if is_latest else "superseded",
            "is_current_view": (p.id == post.id),
        })
    latest_id = line[-1].id if line else post.id
    is_viewing_latest = (post.id == latest_id)

    # Comments (only for proof/revision pages)
    if post.type in ("proof", "revision"):
        comments_raw = comments_for_lineage(db, post)
    else:
        comments_raw = []
    line_ids = {p.id for p in line}
    comments = []
    for c in comments_raw:
        parent = db.query(Post).filter(Post.id == c.parent_id).one()
        if parent.type == "comment":
            target_label = f"replied to {parent.author.name}"
            is_reply = True
        else:
            # parent is a proof/revision
            # find the version label
            v_idx = next((i for i, p in enumerate(line, 1) if p.id == parent.id), None)
            target_label = f"commented on v{v_idx}" if v_idx else f"commented on #{parent.id}"
            is_reply = False
        comments.append({
            "id": c.id, "type": c.type, "author": c.author.name,
            "ts": c.created_at, "body": c.body or "",
            "target_label": target_label, "is_reply": is_reply,
        })

    # Agree-by avatars on the status row
    agrees = (db.query(Post)
              .filter(Post.room_id == room_id, Post.type == "agree",
                      Post.parent_id == post.id).all())
    agreed_by = [a.author.name for a in agrees]

    body_html = render(post.body or "")
    return _templates().TemplateResponse(
        request, "post_detail.html",
        _ctx(request, db, {
            "room": room, "post": post, "post_author": post.author.name,
            "body_html": body_html, "versions": versions,
            "is_viewing_latest": is_viewing_latest, "latest_id": latest_id,
            "this_version_n": next((v["n"] for v in versions if v["is_current_view"]), 1),
            "comments": comments, "agreed_by": agreed_by,
            "participant_count": db.query(func.count(Participant.id)).filter(Participant.room_id == room_id).scalar(),
            "include_katex": True,
        }),
    )


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


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request, next: str = "/", db: Session = Depends(get_db)):
    if current_admin_or_none(request, db):
        return RedirectResponse(url=next or "/", status_code=303)
    return _templates().TemplateResponse(
        request, "admin_login.html",
        _ctx(request, db, {"next": next, "error": None}),
    )


@router.post("/admin/login", response_class=HTMLResponse)
def admin_login_post(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    user = authenticate_admin(db, username, password)
    if not user:
        return _templates().TemplateResponse(
            request, "admin_login.html",
            _ctx(request, db, {"next": next, "error": "Incorrect username or password"}),
            status_code=401,
        )
    request.session["admin_id"] = user.id
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    return RedirectResponse(url=safe_next, status_code=303)


@router.post("/admin/logout")
def admin_logout(request: Request):
    request.session.pop("admin_id", None)
    return RedirectResponse(url="/", status_code=303)
