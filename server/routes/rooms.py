# server/routes/rooms.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from server.db import get_db
from server.models import Room, Participant, Post
from server.schemas import RoomCreate, RoomSummary, RoomDetail, ParticipantCreate, ParticipantRegistered
from server.auth import require_admin, err, make_token

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
