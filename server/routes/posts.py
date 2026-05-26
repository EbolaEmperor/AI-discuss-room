# server/routes/posts.py
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from server.db import get_db
from server.models import Room, Participant, Post
from server.schemas import PostCreate
from server.auth import require_participant, err

router = APIRouter(tags=["posts"])


def _post_meta(p: Post) -> dict:
    return {
        "id": p.id,
        "type": p.type,
        "author": p.author.name,
        "parent_id": p.parent_id,
        "superseded_by": p.superseded_by,
        "ts": p.created_at,
    }


@router.post("/rooms/{room_id}/posts", status_code=201)
def create_post(
    room_id: int,
    payload: PostCreate,
    db: Session = Depends(get_db),
    me: Participant = Depends(require_participant),
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    if me.unregistered_at is not None:
        err("unregistered", "you have unregistered from this room", http=403)
    room = db.query(Room).filter(Room.id == room_id).one()
    if room.status != "open":
        err("room_closed", "room is closed", http=409)

    # Role gate
    if payload.type in ("proof", "revision") and me.role != "producer":
        err("role_forbidden", f"role={me.role} cannot post {payload.type}", http=403)

    # Anti-bias: producer with no first post can only do `proof` (which becomes first)
    if me.role == "producer" and me.first_post_at is None and payload.type != "proof":
        err("must_publish_first", "publish your first proof before any other action", http=403)
    if me.role == "reviewer" and payload.type in ("proof", "revision"):
        err("role_forbidden", "reviewers cannot post proofs", http=403)

    parent: Post | None = None
    if payload.parent_id is not None:
        parent = db.query(Post).filter(Post.id == payload.parent_id, Post.room_id == room_id).one_or_none()
        if not parent:
            err("bad_parent", "parent_id not found in this room", http=422)

    # Type-specific parent rules
    if payload.type == "proof":
        if parent is not None:
            err("bad_parent", "proof must have no parent", http=422)
    elif payload.type == "revision":
        if parent is None or parent.author_id != me.id:
            err("bad_parent", "revision must target your own previous proof/revision", http=422)
        if parent.type not in ("proof", "revision") or parent.superseded_by is not None:
            err("bad_parent", "revision must target a non-superseded proof/revision", http=422)
    elif payload.type == "comment":
        if parent is None:
            err("bad_parent", "comment requires parent_id", http=422)
        if parent.type not in ("proof", "revision", "comment"):
            err("bad_parent", "comment must target a proof/revision/comment", http=422)
    elif payload.type == "agree":
        if parent is None:
            err("bad_parent", "agree requires parent_id", http=422)
        if parent.type not in ("proof", "revision") or parent.superseded_by is not None:
            err("already_superseded", "agree must target a non-superseded proof/revision", http=409)

    if payload.type != "agree" and not (payload.body and payload.body.strip()):
        err("bad_body", f"body required for type={payload.type}", http=422)

    # Single-agree idempotent
    if payload.type == "agree":
        existing = (
            db.query(Post)
            .filter(Post.room_id == room_id, Post.author_id == me.id,
                    Post.type == "agree", Post.parent_id == payload.parent_id)
            .one_or_none()
        )
        if existing:
            return _post_meta(existing)

    now = datetime.utcnow()
    new = Post(
        room_id=room_id,
        author_id=me.id,
        type=payload.type,
        parent_id=payload.parent_id,
        body=payload.body if payload.type != "agree" else (payload.body or None),
        created_at=now,
    )
    db.add(new); db.flush()  # get new.id

    if payload.type == "revision":
        parent.superseded_by = new.id
    if payload.type == "proof" and me.first_post_at is None:
        me.first_post_at = now

    db.commit(); db.refresh(new)

    from server.consensus import check_and_close
    check_and_close(db, room)
    db.refresh(room)

    return _post_meta(new)


def _gate_anti_bias(me: Participant):
    if me.role == "producer" and me.first_post_at is None:
        err("must_publish_first", "publish your first proof before reading posts", http=403)


@router.get("/rooms/{room_id}/posts")
def list_posts(
    room_id: int,
    since: int = 0,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    me: Participant = Depends(require_participant),
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    _gate_anti_bias(me)
    q = db.query(Post).filter(Post.room_id == room_id, Post.id > since)
    if type:
        q = q.filter(Post.type == type)
    posts = q.order_by(Post.id.asc()).all()
    return [_post_meta(p) for p in posts]


@router.get("/rooms/{room_id}/posts/{post_id}")
def read_post(
    room_id: int,
    post_id: int,
    db: Session = Depends(get_db),
    me: Participant = Depends(require_participant),
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    _gate_anti_bias(me)
    post = db.query(Post).filter(Post.id == post_id, Post.room_id == room_id).one_or_none()
    if not post:
        err("not_found", "post not found", http=404)
    # Record read event
    from server.models import Read
    db.add(Read(participant_id=me.id, post_id=post_id, read_at=datetime.utcnow()))
    db.commit()
    return {**_post_meta(post), "body": post.body}
