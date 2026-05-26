# server/consensus.py
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from server.models import Room, Participant, Post


def check_and_close(db: Session, room: Room) -> bool:
    """Check consensus or cap. Returns True if room was closed."""
    if room.status != "open":
        return False

    # 1. Consensus: all *active* (non-unregistered) participants agreed on same non-superseded proof
    participant_ids = [pid for (pid,) in
                       db.query(Participant.id)
                       .filter(Participant.room_id == room.id,
                               Participant.unregistered_at.is_(None)).all()]
    if not participant_ids:
        return False

    current_proof_ids = [pid for (pid,) in
                         db.query(Post.id)
                         .filter(Post.room_id == room.id,
                                 Post.type.in_(("proof", "revision")),
                                 Post.superseded_by.is_(None)).all()]

    for proof_id in current_proof_ids:
        agreeing = {aid for (aid,) in
                    db.query(Post.author_id)
                    .filter(Post.room_id == room.id, Post.type == "agree",
                            Post.parent_id == proof_id).distinct().all()}
        if set(participant_ids).issubset(agreeing):
            room.status = "closed_consensus"
            room.closed_proof_id = proof_id
            room.closed_at = datetime.utcnow()
            db.commit()
            return True

    # 2. Round cap
    post_count = db.query(func.count(Post.id)).filter(Post.room_id == room.id).scalar()
    n_participants = len(participant_ids)
    cap = room.max_rounds * n_participants
    if post_count >= cap:
        room.status = "closed_capped"
        room.closed_at = datetime.utcnow()
        db.commit()
        return True

    return False
