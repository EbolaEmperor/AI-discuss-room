# tests/test_consensus.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_room(client, max_rounds=20):
    return client.post(
        "/rooms",
        json={"title": "T", "problem": "P", "max_rounds": max_rounds},
        headers=basic("admin", "secret"),
    ).json()


def register(client, room_id, name, role="producer"):
    return client.post(f"/rooms/{room_id}/participants", json={"name": name, "role": role}).json()


def test_consensus_closes_room(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    b = register(client, room["id"], "b")
    pa = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "proof", "body": "x"},
                     headers=auth(a["token"])).json()
    pb = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "proof", "body": "y"},
                     headers=auth(b["token"])).json()
    # both agree on pa
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "agree", "parent_id": pa["id"]},
                headers=auth(a["token"]))
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "agree", "parent_id": pa["id"]},
                headers=auth(b["token"]))

    r = client.get(f"/rooms/{room['id']}")
    assert r.json()["status"] == "closed_consensus"
    assert r.json()["closed_proof_id"] == pa["id"]


def test_no_consensus_partial(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    b = register(client, room["id"], "b")
    pa = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "proof", "body": "x"},
                     headers=auth(a["token"])).json()
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "proof", "body": "y"},
                headers=auth(b["token"]))
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "agree", "parent_id": pa["id"]},
                headers=auth(a["token"]))
    r = client.get(f"/rooms/{room['id']}")
    assert r.json()["status"] == "open"


def test_revision_invalidates_agree(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    b = register(client, room["id"], "b")
    pa = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "proof", "body": "x"},
                     headers=auth(a["token"])).json()
    pb = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "proof", "body": "y"},
                     headers=auth(b["token"])).json()
    # b agrees on a's proof
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "agree", "parent_id": pa["id"]},
                headers=auth(b["token"]))
    # a revises (their own proof)
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "revision", "parent_id": pa["id"], "body": "x2"},
                headers=auth(a["token"]))
    # a agrees on own revised
    pa2 = client.get(f"/rooms/{room['id']}/posts", headers=auth(a["token"])).json()[-1]
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "agree", "parent_id": pa2["id"]},
                headers=auth(a["token"]))
    # Room must still be open — b's agree on original pa is invalidated
    r = client.get(f"/rooms/{room['id']}")
    assert r.json()["status"] == "open"


def test_round_cap_closes(client):
    room = make_room(client, max_rounds=2)  # cap = 2 * 2 = 4 posts
    a = register(client, room["id"], "a")
    b = register(client, room["id"], "b")
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "proof", "body": "1"},
                headers=auth(a["token"]))
    pb = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "proof", "body": "2"},
                     headers=auth(b["token"])).json()
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "comment", "parent_id": pb["id"], "body": "3"},
                headers=auth(a["token"]))
    # 4th post hits cap
    client.post(f"/rooms/{room['id']}/posts",
                json={"type": "comment", "parent_id": pb["id"], "body": "4"},
                headers=auth(b["token"]))
    r = client.get(f"/rooms/{room['id']}")
    assert r.json()["status"] == "closed_capped"


def test_idempotent_agree(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    register(client, room["id"], "b")
    pa = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "proof", "body": "x"},
                     headers=auth(a["token"])).json()
    r1 = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "agree", "parent_id": pa["id"]},
                     headers=auth(a["token"]))
    assert r1.status_code in (200, 201)
    r2 = client.post(f"/rooms/{room['id']}/posts",
                     json={"type": "agree", "parent_id": pa["id"]},
                     headers=auth(a["token"]))
    assert r2.status_code in (200, 201)
    # ensure only one agree row created
    posts = client.get(f"/rooms/{room['id']}/posts", headers=auth(a["token"])).json()
    agrees = [p for p in posts if p["type"] == "agree"]
    assert len(agrees) == 1
