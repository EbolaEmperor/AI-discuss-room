# tests/test_models.py
from datetime import datetime
from server.models import Room, Participant, Post, Read


def test_create_room(db_session):
    room = Room(title="T", problem="P", status="open", max_rounds=10)
    db_session.add(room)
    db_session.commit()
    assert room.id is not None
    assert room.status == "open"


def test_participant_and_post_relationship(db_session):
    room = Room(title="T", problem="P")
    db_session.add(room); db_session.commit()
    p = Participant(room_id=room.id, name="a", role="producer", token="tok_a")
    db_session.add(p); db_session.commit()
    post = Post(room_id=room.id, author_id=p.id, type="proof", body="hello")
    db_session.add(post); db_session.commit()
    assert post.author.name == "a"
    assert room.posts[0].id == post.id


def test_read_audit(db_session):
    room = Room(title="T", problem="P"); db_session.add(room); db_session.commit()
    p = Participant(room_id=room.id, name="a", role="producer", token="t")
    db_session.add(p); db_session.commit()
    post = Post(room_id=room.id, author_id=p.id, type="proof", body="x")
    db_session.add(post); db_session.commit()
    r = Read(participant_id=p.id, post_id=post.id)
    db_session.add(r); db_session.commit()
    assert len(p.reads) == 1
