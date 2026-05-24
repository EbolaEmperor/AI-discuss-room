# tests/test_posts.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_room(client, problem="P"):
    return client.post("/rooms", json={"title": "T", "problem": problem}, headers=basic("admin", "secret")).json()


def register(client, room_id, name, role="producer"):
    return client.post(f"/rooms/{room_id}/participants", json={"name": name, "role": role}).json()


def test_create_proof(client):
    room = make_room(client)
    me = register(client, room["id"], "a")
    r = client.post(
        f"/rooms/{room['id']}/posts",
        json={"type": "proof", "body": "hello"},
        headers=auth(me["token"]),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == "proof"
    assert body["author"] == "a"


def test_first_post_sets_first_post_at(client, db_session):
    from server.models import Participant
    room = make_room(client)
    me = register(client, room["id"], "a")
    client.post(
        f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"},
        headers=auth(me["token"]),
    )
    p = db_session.query(Participant).filter(Participant.name == "a").one()
    assert p.first_post_at is not None


def test_reviewer_cannot_post_proof(client):
    room = make_room(client)
    me = register(client, room["id"], "r", role="reviewer")
    r = client.post(
        f"/rooms/{room['id']}/posts",
        json={"type": "proof", "body": "x"},
        headers=auth(me["token"]),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "role_forbidden"


def test_revision_supersedes_previous(client, db_session):
    from server.models import Post
    room = make_room(client)
    me = register(client, room["id"], "a")
    p1 = client.post(
        f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "v1"},
        headers=auth(me["token"]),
    ).json()
    p2 = client.post(
        f"/rooms/{room['id']}/posts",
        json={"type": "revision", "parent_id": p1["id"], "body": "v2"},
        headers=auth(me["token"]),
    ).json()
    assert p2["type"] == "revision"
    p1_db = db_session.query(Post).filter(Post.id == p1["id"]).one()
    assert p1_db.superseded_by == p2["id"]


def test_revision_must_target_own(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    b = register(client, room["id"], "b")
    a_proof = client.post(
        f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"},
        headers=auth(a["token"]),
    ).json()
    # b posts own first proof so they're past first_post gate
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "y"},
                headers=auth(b["token"]))
    # b tries to revise a's proof
    r = client.post(
        f"/rooms/{room['id']}/posts",
        json={"type": "revision", "parent_id": a_proof["id"], "body": "no"},
        headers=auth(b["token"]),
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "bad_parent"
