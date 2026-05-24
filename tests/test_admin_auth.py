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
    client.post("/admin/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    # wrong current
    r = client.post("/admin/settings/password",
                    data={"current_password": "wrong", "new_password": "newpassword", "confirm": "newpassword"},
                    follow_redirects=False)
    assert r.status_code == 400 or "Incorrect" in r.text or "incorrect" in r.text

    # mismatching confirm
    r = client.post("/admin/settings/password",
                    data={"current_password": "secret", "new_password": "newpassword", "confirm": "different"},
                    follow_redirects=False)
    assert r.status_code == 400 or "match" in r.text.lower()

    # too short
    r = client.post("/admin/settings/password",
                    data={"current_password": "secret", "new_password": "short", "confirm": "short"},
                    follow_redirects=False)
    assert r.status_code == 400 or "8" in r.text

    # success
    r = client.post("/admin/settings/password",
                    data={"current_password": "secret", "new_password": "newpassword", "confirm": "newpassword"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "ok=1" in r.headers["location"]

    # log in with new password
    client.post("/admin/logout", follow_redirects=False)
    r = client.post("/admin/login", data={"username": "admin", "password": "newpassword"}, follow_redirects=False)
    assert r.status_code == 303
