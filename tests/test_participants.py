# tests/test_participants.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def make_room(client, title="T", problem="P"):
    return client.post(
        "/rooms", json={"title": title, "problem": problem}, headers=basic("admin", "secret")
    ).json()


def test_register_returns_token(client):
    room = make_room(client)
    r = client.post(
        f"/rooms/{room['id']}/participants",
        json={"name": "claude-a", "role": "producer"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "claude-a"
    assert body["role"] == "producer"
    assert len(body["token"]) > 20


def test_register_duplicate_name_rejected(client):
    room = make_room(client)
    client.post(f"/rooms/{room['id']}/participants", json={"name": "a", "role": "producer"})
    r = client.post(
        f"/rooms/{room['id']}/participants", json={"name": "a", "role": "reviewer"}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "name_taken"


def test_register_invalid_role(client):
    room = make_room(client)
    r = client.post(
        f"/rooms/{room['id']}/participants", json={"name": "a", "role": "moderator"}
    )
    assert r.status_code == 422


def test_register_room_closed(client, db_session):
    from server.models import Room
    room = make_room(client)
    db_room = db_session.query(Room).filter(Room.id == room["id"]).one()
    db_room.status = "closed_manual"
    db_session.commit()
    r = client.post(f"/rooms/{room['id']}/participants", json={"name": "a", "role": "producer"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "room_closed"
