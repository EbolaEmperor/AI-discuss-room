# tests/test_unregister.py
from server.models import Room, Participant, Post
from datetime import datetime


def _make_room(db, title="T", problem="P", status="open", max_rounds=20):
    r = Room(title=title, problem=problem, max_rounds=max_rounds, status=status,
             created_at=datetime.utcnow())
    db.add(r); db.commit(); db.refresh(r)
    return r


def _register(client, room_id, name, role="producer"):
    r = client.post(f"/rooms/{room_id}/participants", json={"name": name, "role": role})
    assert r.status_code == 201, r.text
    return r.json()  # {participant_id, token, name, role}


def _post(client, room_id, token, type_, parent=None, body=None):
    return client.post(
        f"/rooms/{room_id}/posts",
        json={"type": type_, "parent_id": parent, "body": body},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_unregister_sets_timestamp_and_returns_payload(client, db_session):
    room = _make_room(db_session)
    p = _register(client, room.id, "claude-a")
    r = client.delete(f"/rooms/{room.id}/participants/me",
                      headers={"Authorization": f"Bearer {p['token']}"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "claude-a"
    assert d["unregistered_at"] is not None


def test_unregister_blocks_subsequent_writes(client, db_session):
    room = _make_room(db_session)
    p = _register(client, room.id, "claude-a", role="producer")
    # First, publish a proof — should still succeed before unregistering
    r = _post(client, room.id, p["token"], "proof", body="initial argument")
    assert r.status_code == 201
    # Unregister
    r = client.delete(f"/rooms/{room.id}/participants/me",
                      headers={"Authorization": f"Bearer {p['token']}"})
    assert r.status_code == 200
    # Now try to post a revision — must be rejected with `unregistered`
    r = _post(client, room.id, p["token"], "comment",
              parent=1, body="late thought")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "unregistered"


def test_unregister_is_idempotent(client, db_session):
    room = _make_room(db_session)
    p = _register(client, room.id, "claude-a")
    r1 = client.delete(f"/rooms/{room.id}/participants/me",
                       headers={"Authorization": f"Bearer {p['token']}"})
    assert r1.status_code == 200
    first_ts = r1.json()["unregistered_at"]
    # Re-calling does not bump the timestamp, returns 200 with same data
    r2 = client.delete(f"/rooms/{room.id}/participants/me",
                       headers={"Authorization": f"Bearer {p['token']}"})
    assert r2.status_code == 200
    assert r2.json()["unregistered_at"] == first_ts


def test_unregister_unblocks_consensus(client, db_session):
    """
    Three producers join. A publishes proof. B agrees on A's proof. C also
    publishes its own proof but never agrees on A's. Normally room stays open
    because C hasn't agreed. After C unregisters, the consensus check should
    re-evaluate and close the room on A's proof (only A + B remain, both
    have agreed on A's proof — A agrees on own via consensus check requires
    each active participant to agree; A must also agree on its own proof).
    """
    room = _make_room(db_session)
    a = _register(client, room.id, "claude-a")
    b = _register(client, room.id, "claude-b")
    c = _register(client, room.id, "claude-c")

    # A publishes proof
    ra = _post(client, room.id, a["token"], "proof", body="proof by A")
    assert ra.status_code == 201
    a_proof_id = ra.json()["id"]
    # B publishes a proof too (must — anti-bias), then agrees on A's
    rb = _post(client, room.id, b["token"], "proof", body="proof by B")
    assert rb.status_code == 201
    # B agrees on A's
    r = _post(client, room.id, b["token"], "agree", parent=a_proof_id)
    assert r.status_code == 201
    # A agrees on own
    r = _post(client, room.id, a["token"], "agree", parent=a_proof_id)
    assert r.status_code == 201
    # Room must still be open (C has neither published nor agreed)
    r = client.get(f"/rooms/{room.id}")
    assert r.json()["status"] == "open"

    # C unregisters → consensus re-check on close should kick in
    r = client.delete(f"/rooms/{room.id}/participants/me",
                      headers={"Authorization": f"Bearer {c['token']}"})
    assert r.status_code == 200
    r = client.get(f"/rooms/{room.id}")
    assert r.json()["status"] == "closed_consensus"
    assert r.json()["closed_proof_id"] == a_proof_id


def test_unregister_filters_consensus_count(client, db_session):
    """Active participant filtering: an unregistered participant does not
    block consensus the next time someone posts an agree."""
    room = _make_room(db_session)
    a = _register(client, room.id, "claude-a")
    b = _register(client, room.id, "claude-b")
    c = _register(client, room.id, "claude-c")
    # C unregisters before any activity
    r = client.delete(f"/rooms/{room.id}/participants/me",
                      headers={"Authorization": f"Bearer {c['token']}"})
    assert r.status_code == 200
    # A publishes, B publishes
    ra = _post(client, room.id, a["token"], "proof", body="by A")
    a_proof_id = ra.json()["id"]
    _post(client, room.id, b["token"], "proof", body="by B")
    # Now A + B both agree on A's → consensus on 2 active participants
    _post(client, room.id, a["token"], "agree", parent=a_proof_id)
    rb = _post(client, room.id, b["token"], "agree", parent=a_proof_id)
    assert rb.status_code == 201
    r = client.get(f"/rooms/{room.id}")
    assert r.json()["status"] == "closed_consensus"
    assert r.json()["closed_proof_id"] == a_proof_id


def test_unregister_room_not_found_for_other_room(client, db_session):
    room1 = _make_room(db_session)
    room2 = _make_room(db_session)
    p = _register(client, room1.id, "claude-a")
    r = client.delete(f"/rooms/{room2.id}/participants/me",
                      headers={"Authorization": f"Bearer {p['token']}"})
    assert r.status_code == 404


def test_unregister_requires_token(client, db_session):
    room = _make_room(db_session)
    r = client.delete(f"/rooms/{room.id}/participants/me")
    assert r.status_code == 401


def test_participants_list_includes_unregistered_at(client, db_session):
    room = _make_room(db_session)
    a = _register(client, room.id, "claude-a")
    b = _register(client, room.id, "claude-b")
    # Unregister b
    client.delete(f"/rooms/{room.id}/participants/me",
                  headers={"Authorization": f"Bearer {b['token']}"})
    # Use a's token (still active) to list
    r = client.get(f"/rooms/{room.id}/participants",
                   headers={"Authorization": f"Bearer {a['token']}"})
    assert r.status_code == 200
    parts = {p["name"]: p for p in r.json()}
    assert parts["claude-a"]["unregistered_at"] is None
    assert parts["claude-b"]["unregistered_at"] is not None
