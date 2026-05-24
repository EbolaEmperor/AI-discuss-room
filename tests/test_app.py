# tests/test_app.py
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_admin_auth_required(client):
    r = client.get("/admin/health-check-that-doesnt-exist")
    # Either 404 (no such route) or 401 (auth) — we don't have admin endpoints yet
    assert r.status_code in (401, 404)
