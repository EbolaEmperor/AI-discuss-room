# tests/test_rooms.py
import base64

ADMIN_AUTH = ("admin", "secret")


def basic(user, pw):
    raw = f"{user}:{pw}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def test_create_room_requires_admin(client):
    r = client.post("/rooms", json={"title": "T", "problem": "P"})
    assert r.status_code == 401


def test_create_room_ok(client):
    r = client.post(
        "/rooms",
        json={"title": "Chicken-or-egg", "problem": "Prove it.", "max_rounds": 5},
        headers=basic("admin", "secret"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Chicken-or-egg"
    assert body["status"] == "open"
    assert body["max_rounds"] == 5
    assert "id" in body


def test_list_rooms_public(client):
    client.post("/rooms", json={"title": "A", "problem": "x"}, headers=basic("admin", "secret"))
    client.post("/rooms", json={"title": "B", "problem": "y"}, headers=basic("admin", "secret"))
    r = client.get("/rooms")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    titles = {x["title"] for x in body}
    assert titles == {"A", "B"}


def test_get_room_public(client):
    cr = client.post(
        "/rooms", json={"title": "T", "problem": "P"}, headers=basic("admin", "secret")
    ).json()
    r = client.get(f"/rooms/{cr['id']}")
    assert r.status_code == 200
    assert r.json()["title"] == "T"


def test_get_room_not_found(client):
    r = client.get("/rooms/99999")
    assert r.status_code == 404
