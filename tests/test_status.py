# tests/test_status.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_room(client):
    return client.post("/rooms", json={"title": "T", "problem": "P"},
                       headers=basic("admin", "secret")).json()


def register(client, room_id, name, role="producer"):
    return client.post(f"/rooms/{room_id}/participants",
                       json={"name": name, "role": role}).json()


def test_status_basic_shape(client):
    room = make_room(client)
    me = register(client, room["id"], "a")
    r = client.get(f"/rooms/{room['id']}/status", headers=auth(me["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["room"]["state"] == "open"
    assert body["me"]["name"] == "a"
    assert body["me"]["has_published_first"] is False


def test_status_redacted_before_first_post(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    # a posts first
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    # b registers, hasn't posted
    b = register(client, room["id"], "b")
    r = client.get(f"/rooms/{room['id']}/status", headers=auth(b["token"]))
    body = r.json()
    assert body["new_since_my_last_read"] == []
    assert body["current_proofs"] == []
    assert body["me"]["has_published_first"] is False


def test_status_full_after_first_post(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    b = register(client, room["id"], "b")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "y"}, headers=auth(b["token"]))
    r = client.get(f"/rooms/{room['id']}/status", headers=auth(b["token"]))
    body = r.json()
    assert body["me"]["has_published_first"] is True
    assert len(body["current_proofs"]) >= 1
    # b should see a's proof in new_since_my_last_read
    assert len(body["new_since_my_last_read"]) >= 1


def test_reviewer_status_not_redacted(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    rv = register(client, room["id"], "rv", role="reviewer")
    r = client.get(f"/rooms/{room['id']}/status", headers=auth(rv["token"]))
    body = r.json()
    assert len(body["current_proofs"]) == 1
