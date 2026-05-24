# server/routes/rooms.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from server.db import get_db
from server.models import Room, Participant, Post
from server.schemas import RoomCreate, RoomSummary, RoomDetail, ParticipantCreate, ParticipantRegistered
from server.auth import require_admin, require_participant, err, make_token

router = APIRouter(tags=["rooms"])


def _summary(db: Session, room: Room) -> dict:
    participant_count = db.query(func.count(Participant.id)).filter(Participant.room_id == room.id).scalar()
    post_count = db.query(func.count(Post.id)).filter(Post.room_id == room.id).scalar()
    return {
        "id": room.id,
        "title": room.title,
        "status": room.status,
        "participant_count": participant_count,
        "post_count": post_count,
    }


@router.post("/rooms", status_code=201)
def create_room(payload: RoomCreate, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    room = Room(
        title=payload.title,
        problem=payload.problem,
        max_rounds=payload.max_rounds,
        status="open",
        created_at=datetime.utcnow(),
    )
    db.add(room); db.commit(); db.refresh(room)
    return {**_summary(db, room), "problem": room.problem, "max_rounds": room.max_rounds,
            "closed_proof_id": None, "created_at": room.created_at, "closed_at": None}


@router.get("/rooms")
def list_rooms(db: Session = Depends(get_db)):
    rooms = db.query(Room).order_by(Room.id.desc()).all()
    return [_summary(db, r) for r in rooms]


@router.get("/rooms/{room_id}")
def get_room(room_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not room:
        err("not_found", "room not found", http=404)
    return {**_summary(db, room), "problem": room.problem, "max_rounds": room.max_rounds,
            "closed_proof_id": room.closed_proof_id, "created_at": room.created_at,
            "closed_at": room.closed_at}


@router.post("/rooms/{room_id}/participants", status_code=201)
def register(room_id: int, payload: ParticipantCreate, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not room:
        err("not_found", "room not found", http=404)
    if room.status != "open":
        err("room_closed", "room is closed", http=409)
    existing = (
        db.query(Participant)
        .filter(Participant.room_id == room_id, Participant.name == payload.name)
        .one_or_none()
    )
    if existing:
        err("name_taken", f"name {payload.name!r} already exists in this room", http=409)
    p = Participant(
        room_id=room_id,
        name=payload.name,
        role=payload.role,
        token=make_token(),
        registered_at=datetime.utcnow(),
    )
    db.add(p); db.commit(); db.refresh(p)
    return {
        "participant_id": p.id,
        "token": p.token,
        "name": p.name,
        "role": p.role,
    }


@router.get("/rooms/{room_id}/problem")
def get_problem(room_id: int, db: Session = Depends(get_db), me: Participant = Depends(require_participant)):
    room = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not room or me.room_id != room_id:
        err("not_found", "room not found", http=404)
    return room.problem


@router.get("/rooms/{room_id}/participants")
def list_participants(
    room_id: int, db: Session = Depends(get_db), me: Participant = Depends(require_participant)
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    parts = db.query(Participant).filter(Participant.room_id == room_id).all()
    return [
        {"name": p.name, "role": p.role, "has_published_first": p.first_post_at is not None}
        for p in parts
    ]


@router.get("/rooms/{room_id}/status")
def status(
    room_id: int,
    db: Session = Depends(get_db),
    me: Participant = Depends(require_participant),
):
    from server.routes.posts import _post_meta
    from server.models import Read

    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    room = db.query(Room).filter(Room.id == room_id).one()
    participant_count = db.query(func.count(Participant.id)).filter(Participant.room_id == room_id).scalar()
    post_count = db.query(func.count(Post.id)).filter(Post.room_id == room_id).scalar()

    me_summary = {
        "name": me.name,
        "role": me.role,
        "has_published_first": me.first_post_at is not None,
        "first_post_id": None,
        "first_post_at": me.first_post_at,
    }
    if me.first_post_at is not None:
        first = (db.query(Post)
                 .filter(Post.room_id == room_id, Post.author_id == me.id, Post.type == "proof")
                 .order_by(Post.id.asc()).first())
        me_summary["first_post_id"] = first.id if first else None

    redacted = (me.role == "producer" and me.first_post_at is None)

    new_since = []
    proofs_out = []
    if not redacted:
        max_read = (db.query(func.max(Read.post_id))
                    .filter(Read.participant_id == me.id).scalar()) or 0
        new_q = (db.query(Post)
                 .filter(Post.room_id == room_id, Post.id > max_read)
                 .order_by(Post.id.asc()).all())
        new_since = [_post_meta(p) for p in new_q]

        current = (db.query(Post)
                   .filter(Post.room_id == room_id,
                           Post.type.in_(("proof", "revision")),
                           Post.superseded_by.is_(None))
                   .order_by(Post.id.asc()).all())
        for proof in current:
            agrees = (db.query(Post)
                      .filter(Post.room_id == room_id, Post.type == "agree",
                              Post.parent_id == proof.id).all())
            proofs_out.append({
                "id": proof.id,
                "author": proof.author.name,
                "agree_count": len(agrees),
                "agreed_by_me": any(a.author_id == me.id for a in agrees),
            })

    return {
        "room": {
            "id": room.id,
            "title": room.title,
            "state": room.status,
            "participant_count": participant_count,
            "post_count": post_count,
            "max_rounds": room.max_rounds,
        },
        "me": me_summary,
        "new_since_my_last_read": new_since,
        "current_proofs": proofs_out,
    }
