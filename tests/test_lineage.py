# tests/test_lineage.py
from server.models import Room, Participant, Post
from server.lineage import lineage_of, comments_for_lineage
from datetime import datetime


def _setup_room(db_session):
    room = Room(title="T", problem="P", status="open", max_rounds=20, created_at=datetime.utcnow())
    db_session.add(room); db_session.commit()
    p = Participant(room_id=room.id, name="a", role="producer", token="t", registered_at=datetime.utcnow())
    db_session.add(p); db_session.commit()
    return room, p


def test_lineage_root_only(db_session):
    room, p = _setup_room(db_session)
    proof = Post(room_id=room.id, author_id=p.id, type="proof", body="v1", created_at=datetime.utcnow())
    db_session.add(proof); db_session.commit()
    line = lineage_of(db_session, proof)
    assert [x.id for x in line] == [proof.id]


def test_lineage_root_and_revisions(db_session):
    room, p = _setup_room(db_session)
    v1 = Post(room_id=room.id, author_id=p.id, type="proof", body="v1", created_at=datetime.utcnow())
    db_session.add(v1); db_session.commit()
    v2 = Post(room_id=room.id, author_id=p.id, type="revision", parent_id=v1.id, body="v2", created_at=datetime.utcnow())
    db_session.add(v2); db_session.commit()
    v1.superseded_by = v2.id
    v3 = Post(room_id=room.id, author_id=p.id, type="revision", parent_id=v2.id, body="v3", created_at=datetime.utcnow())
    db_session.add(v3); db_session.commit()
    v2.superseded_by = v3.id
    db_session.commit()

    # From any version, lineage returns all in chronological order
    for start in (v1, v2, v3):
        line = lineage_of(db_session, start)
        assert [x.id for x in line] == [v1.id, v2.id, v3.id]


def test_comments_for_lineage(db_session):
    room, a = _setup_room(db_session)
    b = Participant(room_id=room.id, name="b", role="producer", token="t2", registered_at=datetime.utcnow(),
                    first_post_at=datetime.utcnow())
    db_session.add(b); db_session.commit()
    a.first_post_at = datetime.utcnow()
    v1 = Post(room_id=room.id, author_id=a.id, type="proof", body="v1", created_at=datetime.utcnow())
    db_session.add(v1); db_session.commit()
    # comment on v1
    c1 = Post(room_id=room.id, author_id=b.id, type="comment", parent_id=v1.id, body="c1", created_at=datetime.utcnow())
    db_session.add(c1); db_session.commit()
    # revision
    v2 = Post(room_id=room.id, author_id=a.id, type="revision", parent_id=v1.id, body="v2", created_at=datetime.utcnow())
    db_session.add(v2); db_session.commit()
    v1.superseded_by = v2.id; db_session.commit()
    # comment on v2
    c2 = Post(room_id=room.id, author_id=b.id, type="comment", parent_id=v2.id, body="c2", created_at=datetime.utcnow())
    # reply to c1
    c3 = Post(room_id=room.id, author_id=a.id, type="comment", parent_id=c1.id, body="reply", created_at=datetime.utcnow())
    # agree on v2
    ag = Post(room_id=room.id, author_id=b.id, type="agree", parent_id=v2.id, body=None, created_at=datetime.utcnow())
    db_session.add_all([c2, c3, ag]); db_session.commit()

    comments = comments_for_lineage(db_session, v2)
    ids = [x.id for x in comments]
    # all three comments + the agree, chronological
    assert set(ids) == {c1.id, c2.id, c3.id, ag.id}
    # sorted by created_at
    times = [x.created_at for x in comments]
    assert times == sorted(times)
