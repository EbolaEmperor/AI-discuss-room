# server/routes/admin.py
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from server.db import get_db
from server.models import Room, Post, Read, Participant
from server.auth import require_admin, err

router = APIRouter(tags=["admin"])


@router.post("/rooms/{room_id}/close")
def close_room(room_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    room = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not room:
        err("not_found", "room not found", http=404)
    if room.status not in ("open", "closed_capped"):
        err("room_closed", f"room already in terminal state {room.status}", http=409)
    room.status = "closed_manual"
    room.closed_at = datetime.utcnow()
    db.commit()
    return {"id": room.id, "status": room.status}


@router.get("/admin/rooms/{room_id}/audit")
def audit(room_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    posts = db.query(Post).filter(Post.room_id == room_id).all()
    reads = (db.query(Read)
             .join(Participant, Read.participant_id == Participant.id)
             .filter(Participant.room_id == room_id).all())

    events = []
    for p in posts:
        events.append({
            "kind": "post",
            "ts": p.created_at.isoformat(),
            "by": p.author.name,
            "detail": {
                "id": p.id, "type": p.type, "parent_id": p.parent_id,
                "superseded_by": p.superseded_by,
            },
        })
    for r in reads:
        events.append({
            "kind": "read",
            "ts": r.read_at.isoformat(),
            "by": r.participant.name,
            "detail": {"post_id": r.post_id},
        })
    events.sort(key=lambda e: e["ts"])
    return events
