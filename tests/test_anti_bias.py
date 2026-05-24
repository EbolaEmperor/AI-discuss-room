# tests/test_anti_bias.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_room(client):
    return client.post("/rooms", json={"title": "T", "problem": "P"}, headers=basic("admin", "secret")).json()


def register(client, room_id, name, role="producer"):
    return client.post(f"/rooms/{room_id}/participants", json={"name": name, "role": role}).json()


def test_producer_cannot_list_posts_before_first_publish(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    # b registers; a hasn't published yet
    r = client.get(f"/rooms/{room['id']}/posts", headers=auth(a["token"]))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "must_publish_first"


def test_producer_can_list_after_publish(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    r = client.get(f"/rooms/{room['id']}/posts", headers=auth(a["token"]))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_reviewer_can_list_immediately(client):
    room = make_room(client)
    # have someone post so list is non-empty
    a = register(client, room["id"], "a")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    rv = register(client, room["id"], "rv", role="reviewer")
    r = client.get(f"/rooms/{room['id']}/posts", headers=auth(rv["token"]))
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_producer_cannot_read_post_before_first_publish(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    p1 = client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "v1"}, headers=auth(a["token"])).json()
    # b registers and immediately tries to read a's post
    b = register(client, room["id"], "b")
    r = client.get(f"/rooms/{room['id']}/posts/{p1['id']}", headers=auth(b["token"]))
    assert r.status_code == 403


def test_read_records_event(client, db_session):
    from server.models import Read
    room = make_room(client)
    a = register(client, room["id"], "a")
    p1 = client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "v1"}, headers=auth(a["token"])).json()
    b = register(client, room["id"], "b")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "v2"}, headers=auth(b["token"]))
    r = client.get(f"/rooms/{room['id']}/posts/{p1['id']}", headers=auth(b["token"]))
    assert r.status_code == 200
    reads = db_session.query(Read).all()
    assert any(rd.post_id == p1["id"] for rd in reads)
