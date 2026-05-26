# tests/test_edit_problem.py
from server.models import Room, Participant, Post
from datetime import datetime


def _make_room(db, title="T", problem="Original problem text.", status="open"):
    r = Room(title=title, problem=problem, max_rounds=20, status=status,
             created_at=datetime.utcnow())
    db.add(r); db.commit(); db.refresh(r)
    return r


def _login(client):
    r = client.post("/admin/login", data={"username": "admin", "password": "secret"},
                    follow_redirects=False)
    assert r.status_code == 303


def test_edit_problem_get_requires_login(client, db_session):
    room = _make_room(db_session)
    r = client.get(f"/admin/room/{room.id}/edit-problem", follow_redirects=False,
                   headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert "/admin/login" in r.headers["location"]


def test_edit_problem_post_requires_login(client, db_session):
    room = _make_room(db_session)
    r = client.post(f"/admin/room/{room.id}/edit-problem",
                    data={"problem": "Hacked."}, follow_redirects=False,
                    headers={"Accept": "text/html"})
    assert r.status_code == 303
    assert "/admin/login" in r.headers["location"]
    # And the problem stays untouched
    db_session.expire_all()
    assert db_session.query(Room).filter(Room.id == room.id).one().problem == "Original problem text."


def test_edit_problem_form_renders_current_problem(client, db_session):
    room = _make_room(db_session, problem="Sentinel-Problem-X")
    _login(client)
    r = client.get(f"/admin/room/{room.id}/edit-problem")
    assert r.status_code == 200
    assert "Sentinel-Problem-X" in r.text
    # No warning when no activity
    assert "already has activity" not in r.text


def test_edit_problem_form_warns_when_activity_exists(client, db_session):
    room = _make_room(db_session)
    db_session.add(Participant(room_id=room.id, name="claude-a", role="producer",
                               token="tok-a"))
    db_session.commit()
    _login(client)
    r = client.get(f"/admin/room/{room.id}/edit-problem")
    assert r.status_code == 200
    assert "already has activity" in r.text
    assert "1 participant" in r.text


def test_edit_problem_submit_updates_and_redirects(client, db_session):
    room = _make_room(db_session)
    _login(client)
    r = client.post(f"/admin/room/{room.id}/edit-problem",
                    data={"problem": "New problem statement."},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/room/{room.id}"
    db_session.expire_all()
    assert db_session.query(Room).filter(Room.id == room.id).one().problem == "New problem statement."


def test_edit_problem_404_on_bad_room(client, db_session):
    _login(client)
    r = client.get("/admin/room/9999/edit-problem")
    assert r.status_code == 404
    r = client.post("/admin/room/9999/edit-problem",
                    data={"problem": "x"}, follow_redirects=False)
    assert r.status_code == 404


def test_room_page_shows_edit_button_only_for_admin(client, db_session):
    room = _make_room(db_session)
    # Anonymous: no Edit button
    r = client.get(f"/room/{room.id}")
    assert r.status_code == 200
    assert f"/admin/room/{room.id}/edit-problem" not in r.text
    # Admin: Edit button visible
    _login(client)
    r = client.get(f"/room/{room.id}")
    assert r.status_code == 200
    assert f"/admin/room/{room.id}/edit-problem" in r.text
    assert "Edit problem" in r.text


def test_room_page_edit_button_has_confirm_when_activity(client, db_session):
    room = _make_room(db_session)
    db_session.add(Participant(room_id=room.id, name="claude-a", role="producer",
                               token="tok-a"))
    db_session.commit()
    _login(client)
    r = client.get(f"/room/{room.id}")
    assert r.status_code == 200
    # Confirm dialog wired via onclick
    assert "onclick=\"return confirm(" in r.text
    assert "already has activity" in r.text


def test_room_page_edit_button_no_confirm_when_empty(client, db_session):
    room = _make_room(db_session)
    _login(client)
    r = client.get(f"/room/{room.id}")
    assert r.status_code == 200
    # No participants, no posts → no confirm wrapper around the edit button
    assert "onclick=\"return confirm(" not in r.text
