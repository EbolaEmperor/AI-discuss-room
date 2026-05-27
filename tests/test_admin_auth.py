# tests/test_admin_auth.py
def test_login_get_renders_form(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert "Sign in" in r.text


def test_login_wrong_password(client):
    r = client.post("/admin/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert "Incorrect" in r.text


def test_login_success_sets_session(client):
    r = client.post("/admin/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_already_logged_in_redirects(client):
    client.post("/admin/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    r = client.get("/admin/login", follow_redirects=False)
    assert r.status_code == 303


def test_new_room_requires_login(client):
    r = client.get("/admin/new-room", follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert "/admin/login" in r.headers["location"]


def test_logout_clears_session(client):
    client.post("/admin/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    r = client.post("/admin/logout", follow_redirects=False)
    assert r.status_code == 303
    r2 = client.get("/admin/new-room", follow_redirects=False, headers={"Accept": "text/html"})
    assert r2.status_code == 303
    assert "/admin/login" in r2.headers["location"]


def test_settings_requires_login(client):
    r = client.get("/admin/settings", follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code == 303


def test_change_password_flow(client):
    """Canonical UI flow — the settings modal POSTs with HX-Request, so errors
    come back as 400 + inline fragment and success comes back as a fragment
    plus the HX-Trigger header that tells the modal to auto-close."""
    client.post("/admin/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    htmx = {"HX-Request": "true"}

    # wrong current
    r = client.post("/admin/settings/password",
                    data={"current_password": "wrong", "new_password": "newpassword", "confirm": "newpassword"},
                    headers=htmx, follow_redirects=False)
    assert r.status_code == 400
    assert "Incorrect" in r.text or "incorrect" in r.text

    # mismatching confirm
    r = client.post("/admin/settings/password",
                    data={"current_password": "secret", "new_password": "newpassword", "confirm": "different"},
                    headers=htmx, follow_redirects=False)
    assert r.status_code == 400
    assert "match" in r.text.lower()

    # too short
    r = client.post("/admin/settings/password",
                    data={"current_password": "secret", "new_password": "short", "confirm": "short"},
                    headers=htmx, follow_redirects=False)
    assert r.status_code == 400
    assert "8" in r.text

    # success
    r = client.post("/admin/settings/password",
                    data={"current_password": "secret", "new_password": "newpassword", "confirm": "newpassword"},
                    headers=htmx, follow_redirects=False)
    assert r.status_code == 200
    assert "Password changed" in r.text
    assert r.headers.get("HX-Trigger") == "passwordChanged"

    # log in with new password
    client.post("/admin/logout", follow_redirects=False)
    r = client.post("/admin/login", data={"username": "admin", "password": "newpassword"}, follow_redirects=False)
    assert r.status_code == 303


def test_change_password_non_htmx_fallback(client):
    """If JS is disabled / no HX-Request, the endpoint falls back to a plain
    redirect so the user isn't left on a broken page."""
    client.post("/admin/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    # Error path: bounce home (the modal will re-open via ?settings=open).
    r = client.post("/admin/settings/password",
                    data={"current_password": "wrong", "new_password": "newpassword", "confirm": "newpassword"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "/?settings=open" in r.headers["location"]
    # Success path: bounce home cleanly.
    r = client.post("/admin/settings/password",
                    data={"current_password": "secret", "new_password": "newpassword", "confirm": "newpassword"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_legacy_settings_url_redirects_to_modal(client):
    """/admin/settings used to be a standalone page; now it redirects to /
    with ?settings=open so the modal auto-opens."""
    client.post("/admin/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    r = client.get("/admin/settings", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/?settings=open"


def test_legacy_settings_url_requires_admin(client):
    """Unauthenticated GET /admin/settings goes through the admin gate and
    redirects to login like every other admin route."""
    r = client.get("/admin/settings", follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert "/admin/login" in r.headers["location"]


def test_index_renders_settings_modal_for_admin(client):
    """The settings modal lives in base.html and should be present in any
    admin-visible page. Verify by hitting / after login."""
    client.post("/admin/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="settings-modal"' in r.text
    assert "data-settings-trigger" in r.text


def test_index_does_not_render_settings_modal_when_unauthed(client):
    """The modal is gated by current_admin; unauthed users get redirected to
    login anyway, but defense in depth — confirm the login page doesn't
    include the modal markup."""
    r = client.get("/admin/login")
    assert r.status_code == 200
    assert 'id="settings-modal"' not in r.text


# --- Web frontend is admin-only: HTML routes redirect unauthenticated browsers
#     to /admin/login. JSON discovery endpoints stay public for the CLI.

def _make_room_and_post(client):
    """Create a room via admin API + register a participant + publish a proof,
    so the HTML routes have something to render and a post-detail page exists."""
    # Admin Basic auth on the API.
    r = client.post("/rooms", json={"title": "T", "problem": "P"}, auth=("admin", "secret"))
    assert r.status_code == 201, r.text
    room_id = r.json()["id"]
    r = client.post(f"/rooms/{room_id}/participants",
                    json={"name": "claude-a", "role": "producer"})
    assert r.status_code == 201
    token = r.json()["token"]
    r = client.post(f"/rooms/{room_id}/posts",
                    json={"type": "proof", "body": "p"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    post_id = r.json()["id"]
    return room_id, post_id


def test_html_index_redirects_to_login_when_unauthed(client):
    r = client.get("/", follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert r.headers["location"].startswith("/admin/login?next=/")


def test_html_room_view_redirects_to_login_when_unauthed(client):
    room_id, _ = _make_room_and_post(client)
    r = client.get(f"/room/{room_id}", follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert "/admin/login" in r.headers["location"]


def test_html_post_detail_redirects_to_login_when_unauthed(client):
    room_id, post_id = _make_room_and_post(client)
    r = client.get(f"/room/{room_id}/post/{post_id}",
                   follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert "/admin/login" in r.headers["location"]


def test_html_timeline_partial_redirects_to_login_when_unauthed(client):
    room_id, _ = _make_room_and_post(client)
    r = client.get(f"/room/{room_id}/timeline-partial",
                   follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert "/admin/login" in r.headers["location"]


def test_html_audit_redirects_to_login_when_unauthed(client):
    room_id, _ = _make_room_and_post(client)
    r = client.get(f"/room/{room_id}/audit",
                   follow_redirects=False, headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert "/admin/login" in r.headers["location"]


def test_html_routes_accessible_after_login(client):
    room_id, post_id = _make_room_and_post(client)
    client.post("/admin/login", data={"username": "admin", "password": "secret"},
                follow_redirects=False)
    assert client.get("/").status_code == 200
    assert client.get(f"/room/{room_id}").status_code == 200
    assert client.get(f"/room/{room_id}/post/{post_id}").status_code == 200
    assert client.get(f"/room/{room_id}/timeline-partial").status_code == 200
    assert client.get(f"/room/{room_id}/audit").status_code == 200


def test_json_discovery_endpoints_remain_public(client):
    """The skill bootstrap relies on `GET /rooms` and `GET /rooms/{id}` being
    reachable without admin credentials — those are deliberately public."""
    room_id, _ = _make_room_and_post(client)
    # No auth on these requests.
    assert client.get("/rooms").status_code == 200
    assert client.get(f"/rooms/{room_id}").status_code == 200


def test_api_post_read_still_blocked_for_curl_without_token(client):
    """Defense in depth: even though we locked HTML, the API was already
    participant-token-gated. Confirm a raw GET (no token) is 401, not content."""
    room_id, post_id = _make_room_and_post(client)
    r = client.get(f"/rooms/{room_id}/posts")
    assert r.status_code == 401
    r = client.get(f"/rooms/{room_id}/posts/{post_id}")
    assert r.status_code == 401
