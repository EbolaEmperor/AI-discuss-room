# tests/test_admin.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_room(client):
    return client.post("/rooms", json={"title": "T", "problem": "P"},
                       headers=basic("admin", "secret")).json()


def register(client, room_id, name, role="producer"):
    return client.post(f"/rooms/{room_id}/participants", json={"name": name, "role": role}).json()


def test_admin_close_room(client):
    room = make_room(client)
    r = client.post(f"/rooms/{room['id']}/close", headers=basic("admin", "secret"))
    assert r.status_code == 200
    r2 = client.get(f"/rooms/{room['id']}")
    assert r2.json()["status"] == "closed_manual"


def test_close_requires_admin(client):
    room = make_room(client)
    r = client.post(f"/rooms/{room['id']}/close")
    assert r.status_code == 401


def test_audit_returns_events(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    p1 = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "proof", "body": "x"},
                     headers=auth(a["token"])).json()
    b = register(client, room["id"], "b")
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "proof", "body": "y"},
                headers=auth(b["token"]))
    client.get(f"/rooms/{room['id']}/posts/{p1['id']}", headers=auth(b["token"]))

    r = client.get(f"/admin/rooms/{room['id']}/audit", headers=basic("admin", "secret"))
    assert r.status_code == 200
    events = r.json()
    kinds = {e["kind"] for e in events}
    assert "post" in kinds
    assert "read" in kinds
