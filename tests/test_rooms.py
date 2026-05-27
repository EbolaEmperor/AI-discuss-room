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


# ─── Isolation: per-room content gating ───────────────────────────────────
# Public summary endpoints must NOT leak content (problem text, posts, etc.).
# Participant tokens are bound to their registered room — a token from room A
# cannot read any content endpoint of room B (returns 404 not_found).

def _make_room_with_token(client, title, problem, name, role="producer"):
    """Helper: admin-creates a room, registers a participant, returns
    (room_id, token)."""
    rid = client.post("/rooms",
                      json={"title": title, "problem": problem},
                      headers=basic("admin", "secret")).json()["id"]
    body = client.post(f"/rooms/{rid}/participants",
                       json={"name": name, "role": role}).json()
    return rid, body["token"]


def test_public_room_detail_does_not_leak_problem(client):
    """GET /rooms/{id} is a discovery endpoint — it must NOT include the
    problem text. The problem is content; only same-room participants
    should be able to read it via /rooms/{id}/problem."""
    rid = client.post("/rooms",
                      json={"title": "Secret problem", "problem": "FLAG{do-not-leak}"},
                      headers=basic("admin", "secret")).json()["id"]
    r = client.get(f"/rooms/{rid}")
    assert r.status_code == 200
    body = r.json()
    # Summary fields are fine.
    assert body["id"] == rid
    assert body["title"] == "Secret problem"
    assert body["status"] == "open"
    # Content fields must be absent.
    assert "problem" not in body
    assert "FLAG" not in r.text


def test_public_room_list_does_not_leak_problem(client):
    """GET /rooms must not expose problem text either."""
    client.post("/rooms",
                json={"title": "T", "problem": "FLAG{also-do-not-leak}"},
                headers=basic("admin", "secret"))
    r = client.get("/rooms")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert "problem" not in body[0]
    assert "FLAG" not in r.text


def test_public_room_summary_includes_active_participants(client):
    """Summary should include the names + roles of *active* participants so
    pre-registration callers can pick a room based on who's already in it.
    Unregistered participants are filtered out."""
    rid, tok_a = _make_room_with_token(client, "T", "P", "alice", "producer")
    # Register a second participant, then unregister them.
    body_b = client.post(f"/rooms/{rid}/participants",
                         json={"name": "bob", "role": "reviewer"}).json()
    client.delete(f"/rooms/{rid}/participants/me",
                  headers={"Authorization": f"Bearer {body_b['token']}"})
    # Now /rooms/{id} should show alice only.
    body = client.get(f"/rooms/{rid}").json()
    names = sorted(p["name"] for p in body["participants"])
    assert names == ["alice"]
    assert body["participant_count"] == 1
    # Also reflected on the list endpoint.
    list_body = client.get("/rooms").json()
    assert sorted(p["name"] for p in list_body[0]["participants"]) == ["alice"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def test_cross_room_token_cannot_read_problem(client):
    """A participant of room A presenting their token at room B's /problem
    endpoint gets 404 (room-not-found, indistinguishable from a nonexistent
    room — does not leak whether room B exists)."""
    rid_a, tok_a = _make_room_with_token(client, "A", "problem-A", "alice")
    rid_b, tok_b = _make_room_with_token(client, "B", "problem-B", "bob")
    # alice (token for A) tries to read B's problem.
    r = client.get(f"/rooms/{rid_b}/problem", headers=_hdr(tok_a))
    assert r.status_code == 404


def test_cross_room_token_cannot_list_posts(client):
    rid_a, tok_a = _make_room_with_token(client, "A", "p", "alice")
    rid_b, _ = _make_room_with_token(client, "B", "p", "bob")
    r = client.get(f"/rooms/{rid_b}/posts", headers=_hdr(tok_a))
    assert r.status_code == 404


def test_cross_room_token_cannot_read_specific_post(client):
    """Even if alice knows a specific post id from room B, her token can't
    fetch it. The endpoint resolves at the room level, then 404s."""
    rid_a, tok_a = _make_room_with_token(client, "A", "p", "alice")
    rid_b, tok_b = _make_room_with_token(client, "B", "p", "bob")
    # bob publishes a proof in B.
    proof = client.post(f"/rooms/{rid_b}/posts",
                        json={"type": "proof", "body": "secret body"},
                        headers=_hdr(tok_b)).json()
    # alice cannot read it.
    r = client.get(f"/rooms/{rid_b}/posts/{proof['id']}", headers=_hdr(tok_a))
    assert r.status_code == 404


def test_cross_room_token_cannot_read_status(client):
    rid_a, tok_a = _make_room_with_token(client, "A", "p", "alice")
    rid_b, _ = _make_room_with_token(client, "B", "p", "bob")
    r = client.get(f"/rooms/{rid_b}/status", headers=_hdr(tok_a))
    assert r.status_code == 404


def test_cross_room_token_cannot_list_participants(client):
    rid_a, tok_a = _make_room_with_token(client, "A", "p", "alice")
    rid_b, _ = _make_room_with_token(client, "B", "p", "bob")
    r = client.get(f"/rooms/{rid_b}/participants", headers=_hdr(tok_a))
    assert r.status_code == 404


def test_cross_room_token_cannot_post(client):
    rid_a, tok_a = _make_room_with_token(client, "A", "p", "alice")
    rid_b, _ = _make_room_with_token(client, "B", "p", "bob")
    r = client.post(f"/rooms/{rid_b}/posts",
                    json={"type": "proof", "body": "x"},
                    headers=_hdr(tok_a))
    assert r.status_code == 404


def test_cross_room_token_cannot_unregister(client):
    rid_a, tok_a = _make_room_with_token(client, "A", "p", "alice")
    rid_b, _ = _make_room_with_token(client, "B", "p", "bob")
    r = client.delete(f"/rooms/{rid_b}/participants/me", headers=_hdr(tok_a))
    assert r.status_code == 404


def test_own_room_problem_readable(client):
    """Sanity: same-room token CAN read its own room's problem."""
    rid, tok = _make_room_with_token(client, "A", "the actual problem text", "alice")
    r = client.get(f"/rooms/{rid}/problem", headers=_hdr(tok))
    assert r.status_code == 200
    assert "the actual problem text" in r.text
