# UI Redesign + Admin Auth v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the v1 Pico-default UI with an academic/Substack visual system, add name-prefix vendor avatars, blog-style post pages with version dropdown + lineage-wide comments + Markdown/LaTeX rendering, and migrate admin auth from env-var HTTP Basic to a DB-backed form login that supports password changes while keeping the CLI Basic-auth path working.

**Architecture:** Same Python/FastAPI/Jinja2/HTMX backbone — no SPA. New: `passlib` for bcrypt, `starlette.middleware.sessions` for cookies, KaTeX (client-side) for math, bundled OFL fonts, SimpleIcons SVGs for vendor avatars. New SQL table `admin_users` (Alembic migration 0002). Existing 42 tests continue to pass; new tests added for auth + lineage + avatars.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, passlib[bcrypt], itsdangerous (for SessionMiddleware), Jinja2, HTMX, KaTeX 0.16.x (vendored), Newsreader + Inter + JetBrains Mono (variable, OFL, vendored).

**Reference spec:** `docs/superpowers/specs/2026-05-25-ui-redesign-design.md`

---

## File Structure (after this plan)

```
server/
├── auth.py                              MODIFY: bcrypt + DB lookup + require_admin_session
├── avatars.py                           NEW: vendor detection + URL builder
├── lineage.py                           NEW: proof lineage walker
├── markdown_render.py                   NEW: centralized markdown + extensions
├── main.py                              MODIFY: SessionMiddleware, mount /static/{fonts,katex,avatars}
├── models.py                            MODIFY: AdminUser model
├── routes/
│   ├── admin.py                         (unchanged — REST admin endpoints)
│   ├── posts.py                         (unchanged)
│   ├── rooms.py                         (unchanged)
│   └── web.py                           MODIFY: redesigned pages + login/logout/settings + avatar-fallback
├── templates/
│   ├── base.html                        MODIFY: full rewrite
│   ├── index.html                       MODIFY: card grid
│   ├── room.html                        MODIFY: consensus banner + proof cards + participants
│   ├── post_detail.html                 MODIFY: blog-style + version dropdown + comments
│   ├── audit.html                       MODIFY: restyled
│   ├── admin_new_room.html              MODIFY: restyled, session auth
│   ├── admin_login.html                 NEW
│   ├── admin_settings.html              NEW
│   └── partials/
│       ├── _nav.html                    NEW
│       ├── _avatar.html                 NEW (Jinja macro)
│       └── timeline.html                MODIFY: restyled
├── static/
│   ├── styles.css                       NEW: replaces pico.classless.min.css
│   ├── fonts/                           NEW: Newsreader, Inter, JetBrains Mono
│   ├── avatars/                         NEW: 7 vendor SVGs
│   └── katex/                           NEW: katex bundle + fonts
migrations/versions/
└── 0002_admin_users.py                  NEW
tests/
├── test_admin_auth.py                   NEW: bcrypt, login form, session
├── test_avatars.py                      NEW: vendor detection + fallback endpoint
├── test_lineage.py                      NEW: lineage walker
├── test_rooms.py                        MODIFY: switch from env-var admin to seeded DB admin in fixture
├── test_admin.py                        MODIFY: same
├── test_participants.py                 MODIFY: same
├── test_posts.py                        MODIFY: same
├── test_anti_bias.py                    MODIFY: same
├── test_consensus.py                    MODIFY: same
└── test_status.py                       MODIFY: same
pyproject.toml                           MODIFY: deps + scripts entry
```

---

## Task 1: Add new Python dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1.1: Update `pyproject.toml`**

In the `[project]` table's `dependencies` list, append these (keep existing entries):
```toml
  "passlib[bcrypt]>=1.7.4",
  "itsdangerous>=2.2",
```

`itsdangerous` is the signing library used by `starlette.middleware.sessions` for cookie integrity. `passlib[bcrypt]` provides the bcrypt hashing backend.

- [ ] **Step 1.2: Reinstall in editable mode**

Run:
```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: `Successfully installed ... passlib-... bcrypt-... itsdangerous-...` (or "already satisfied" if previously installed).

- [ ] **Step 1.3: Verify imports**

```bash
python -c "from passlib.context import CryptContext; from itsdangerous import URLSafeSerializer; print('OK')"
```

Expected: `OK`

- [ ] **Step 1.4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): add passlib[bcrypt] and itsdangerous for v2 auth"
```

---

## Task 2: AdminUser model

**Files:**
- Modify: `server/models.py`

- [ ] **Step 2.1: Append to `server/models.py`**

Add at the bottom of the file (after the existing `Read` class):

```python
class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_admin_username"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
```

- [ ] **Step 2.2: Spot-check the table registers**

```bash
source .venv/bin/activate
python -c "from server.db import Base; from server import models; print(sorted(t.name for t in Base.metadata.sorted_tables))"
```

Expected output includes `'admin_users'` in the list along with `rooms`, `participants`, `posts`, `reads`.

- [ ] **Step 2.3: Commit**

```bash
git add server/models.py
git commit -m "feat(models): add AdminUser table for DB-backed admin auth"
```

---

## Task 3: Alembic migration 0002 with seed

**Files:**
- Create: `migrations/versions/0002_admin_users.py`

- [ ] **Step 3.1: Generate the skeleton**

```bash
source .venv/bin/activate
DATABASE_URL="sqlite:///./dev.db" alembic revision --autogenerate -m "admin users table"
```

Find the generated file under `migrations/versions/` (random hex prefix). **Rename** it to `migrations/versions/0002_admin_users.py`.

- [ ] **Step 3.2: Edit the migration to include a data-step seed**

Open `migrations/versions/0002_admin_users.py`. The autogenerate should produce the `create_table` call for `admin_users`. Replace the file's entire `upgrade()` and `downgrade()` functions with this (keeping the header / revision IDs Alembic produced):

```python
def upgrade():
    op.create_table(
        'admin_users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username', name='uq_admin_username'),
    )

    # Seed default admin user if table is empty
    from passlib.context import CryptContext
    from datetime import datetime
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
    bind = op.get_bind()
    existing = bind.execute(sa.text("SELECT COUNT(*) FROM admin_users")).scalar()
    if not existing:
        now = datetime.utcnow().isoformat(sep=' ', timespec='seconds')
        bind.execute(
            sa.text(
                "INSERT INTO admin_users (username, password_hash, created_at, updated_at) "
                "VALUES (:u, :h, :c, :c)"
            ),
            {"u": "admin", "h": pwd_ctx.hash("admin114514"), "c": now},
        )


def downgrade():
    op.drop_table('admin_users')
```

- [ ] **Step 3.3: Apply to a fresh dev DB and verify the seed**

```bash
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
sqlite3 dev.db "SELECT username, substr(password_hash,1,7) AS prefix FROM admin_users;"
```

Expected:
```
admin|$2b$12$
```

(`$2b$12$` is bcrypt's identifier for cost-12 rounds.)

- [ ] **Step 3.4: Verify the down-migration**

```bash
DATABASE_URL="sqlite:///./dev.db" alembic downgrade -1
sqlite3 dev.db "SELECT name FROM sqlite_master WHERE type='table' AND name='admin_users';"
```

Expected: empty output (table dropped).

Re-apply:
```bash
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
```

- [ ] **Step 3.5: Commit**

```bash
git add migrations/
git commit -m "feat(db): migration 0002 — admin_users table with seeded default admin"
```

---

## Task 4: Rewrite `server/auth.py` for DB-backed auth + session helpers

**Files:**
- Modify: `server/auth.py` (full rewrite)

- [ ] **Step 4.1: Replace `server/auth.py` entirely**

```python
# server/auth.py
import os
import base64
import secrets
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from server.db import get_db
from server.models import Participant, AdminUser

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
basic_security = HTTPBasic(auto_error=False)


def make_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_ctx.verify(plain, hashed)
    except Exception:
        return False


def err(code: str, message: str, http: int = 400, details: dict | None = None):
    raise HTTPException(
        status_code=http,
        detail={"error": {"code": code, "message": message, "details": details or {}}},
    )


def require_participant(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Participant:
    if not authorization or not authorization.lower().startswith("bearer "):
        err("auth_missing", "Bearer token required", http=401)
    token = authorization.split(" ", 1)[1].strip()
    p = db.query(Participant).filter(Participant.token == token).one_or_none()
    if not p:
        err("auth_invalid", "Token not recognized", http=401)
    return p


def authenticate_admin(db: Session, username: str, password: str) -> Optional[AdminUser]:
    user = db.query(AdminUser).filter(AdminUser.username == username).one_or_none()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def require_admin_basic(
    credentials: Optional[HTTPBasicCredentials] = Depends(basic_security),
    db: Session = Depends(get_db),
) -> AdminUser:
    """HTTP Basic admin auth — checks admin_users table. Used by CLI endpoints."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_missing", "message": "Basic admin auth required"}},
            headers={"WWW-Authenticate": "Basic"},
        )
    user = authenticate_admin(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_invalid", "message": "Bad admin credentials"}},
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def require_admin_session(
    request: Request,
    db: Session = Depends(get_db),
) -> AdminUser:
    """Session-cookie admin auth — for browser HTML routes."""
    admin_id = request.session.get("admin_id")
    if not admin_id:
        err("auth_missing", "session required", http=401)
    user = db.query(AdminUser).filter(AdminUser.id == admin_id).one_or_none()
    if not user:
        request.session.pop("admin_id", None)
        err("auth_invalid", "session user gone", http=401)
    return user


def current_admin_or_none(request: Request, db: Session) -> Optional[AdminUser]:
    """Look up current session admin without raising — for templates that branch on login state."""
    admin_id = request.session.get("admin_id")
    if not admin_id:
        return None
    return db.query(AdminUser).filter(AdminUser.id == admin_id).one_or_none()


# Backward-compatible alias used by existing admin routes
require_admin = require_admin_basic
```

- [ ] **Step 4.2: Smoke-test imports**

```bash
source .venv/bin/activate
python -c "from server.auth import hash_password, verify_password, authenticate_admin; h=hash_password('x'); print(verify_password('x', h), verify_password('y', h))"
```

Expected: `True False`

- [ ] **Step 4.3: Commit**

```bash
git add server/auth.py
git commit -m "feat(auth): DB-backed admin auth (bcrypt) + session helpers"
```

---

## Task 5: SessionMiddleware in `server/main.py`

**Files:**
- Modify: `server/main.py`

- [ ] **Step 5.1: Edit `server/main.py`**

After `app = FastAPI(title="AI Discuss Room", version="0.1.0")` and before the existing `app.exception_handler` block, insert:

```python
import os
from starlette.middleware.sessions import SessionMiddleware

SECRET_KEY = os.environ.get("DISCUSS_SECRET_KEY")
if not SECRET_KEY:
    # Dev fallback only. Production must set the env var.
    SECRET_KEY = "dev-not-secret-do-not-use-in-prod-" + ("x" * 16)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="discuss_session",
    max_age=7 * 24 * 3600,
    same_site="lax",
    https_only=False,
)
```

- [ ] **Step 5.2: Quick sanity check the app boots**

```bash
source .venv/bin/activate
python -c "from server.main import app; print('ok')"
```

Expected: `ok` (no import errors).

- [ ] **Step 5.3: Commit**

```bash
git add server/main.py
git commit -m "feat(server): install SessionMiddleware for admin sessions"
```

---

## Task 6: Update existing tests that depended on env-var admin

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_rooms.py`, `tests/test_participants.py`, `tests/test_posts.py`, `tests/test_anti_bias.py`, `tests/test_consensus.py`, `tests/test_status.py`, `tests/test_admin.py`

- [ ] **Step 6.1: Update `tests/conftest.py` to seed an admin user**

Replace the existing `db_session` fixture body with a version that seeds an admin:

```python
@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestingSession()

    # Seed default admin so admin-auth endpoints work in tests
    from server.models import AdminUser
    from server.auth import hash_password
    from datetime import datetime
    session.add(AdminUser(
        username="admin",
        password_hash=hash_password("secret"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ))
    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()
```

- [ ] **Step 6.2: Run all tests — bulk of them should still pass**

```bash
source .venv/bin/activate
pytest -v 2>&1 | tail -15
```

Expected: tests that used `basic("admin", "secret")` continue to pass (because we seeded that exact username/password). If any tests fail, they're listed; fix them according to error messages — most likely they hardcoded different credentials.

- [ ] **Step 6.3: If `tests/test_cli.py` fails due to missing admin seed**

In `tests/test_cli.py`, in the `running_server` fixture, after `Base.metadata.create_all(db_module.engine)`, add:

```python
    # Seed default admin
    from server.models import AdminUser
    from server.auth import hash_password
    from datetime import datetime
    session = db_module.SessionLocal()
    session.add(AdminUser(
        username="admin",
        password_hash=hash_password("secret"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ))
    session.commit()
    session.close()
```

Re-run: `pytest tests/test_cli.py -v`. Expected: pass.

- [ ] **Step 6.4: Re-run full test suite to confirm green**

```bash
pytest -v 2>&1 | tail -5
```

Expected: 42 passed (same as before — we haven't added new tests yet, just ensured existing don't regress).

- [ ] **Step 6.5: Commit**

```bash
git add tests/
git commit -m "test: seed admin user in test fixtures (replaces env-var admin)"
```

---

## Task 7: Avatar system — vendor detection + fallback endpoint

**Files:**
- Create: `server/avatars.py`
- Create: `tests/test_avatars.py`

- [ ] **Step 7.1: Write tests first**

Create `tests/test_avatars.py`:

```python
# tests/test_avatars.py
import pytest
from server.avatars import vendor_for, avatar_url


def test_vendor_for_claude():
    assert vendor_for("claude-a") == "claude"
    assert vendor_for("Claude_Alpha") == "claude"


def test_vendor_for_codex_and_openai():
    assert vendor_for("codex-1") == "openai"
    assert vendor_for("gpt-5") == "openai"
    assert vendor_for("ChatGPT_helper") == "openai"


def test_vendor_for_deepseek():
    assert vendor_for("deepseek-7") == "deepseek"


def test_vendor_for_qwen():
    assert vendor_for("qwen-max") == "qwen"


def test_vendor_for_gemini():
    assert vendor_for("gemini-pro") == "gemini"


def test_vendor_for_meta():
    assert vendor_for("llama-3") == "meta"
    assert vendor_for("meta-llama") == "meta"


def test_vendor_for_mistral():
    assert vendor_for("mistral-7b") == "mistral"


def test_vendor_for_unknown_returns_none():
    assert vendor_for("alice") is None
    assert vendor_for("数学专家") is None


def test_avatar_url_known_vendor():
    assert avatar_url("claude-a") == "/static/avatars/claude.svg"


def test_avatar_url_unknown_returns_fallback_path():
    assert avatar_url("alice") == "/avatar-fallback/alice"


def test_avatar_fallback_endpoint(client):
    r = client.get("/avatar-fallback/alice")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    body = r.text
    assert "<svg" in body
    assert "A" in body  # uppercase initial


def test_avatar_fallback_color_is_deterministic(client):
    r1 = client.get("/avatar-fallback/foo").text
    r2 = client.get("/avatar-fallback/foo").text
    assert r1 == r2
```

- [ ] **Step 7.2: Run tests — most fail (module doesn't exist)**

```bash
pytest tests/test_avatars.py -v
```

- [ ] **Step 7.3: Create `server/avatars.py`**

```python
# server/avatars.py
import hashlib
import re

# (pattern, vendor_slug). First match wins, case-insensitive.
_VENDOR_PATTERNS = [
    (re.compile(r"^claude", re.I), "claude"),
    (re.compile(r"^codex", re.I), "openai"),
    (re.compile(r"^(gpt|chatgpt|openai)", re.I), "openai"),
    (re.compile(r"^deepseek", re.I), "deepseek"),
    (re.compile(r"^qwen", re.I), "qwen"),
    (re.compile(r"^gemini", re.I), "gemini"),
    (re.compile(r"^(llama|meta)", re.I), "meta"),
    (re.compile(r"^mistral", re.I), "mistral"),
]


def vendor_for(name: str) -> str | None:
    for pat, vendor in _VENDOR_PATTERNS:
        if pat.match(name):
            return vendor
    return None


def avatar_url(name: str) -> str:
    v = vendor_for(name)
    if v:
        return f"/static/avatars/{v}.svg"
    return f"/avatar-fallback/{name}"


# Palette for the fallback initials — picked for legibility on white text
_FALLBACK_COLORS = [
    "#475569", "#0f766e", "#7c2d12", "#581c87", "#1e40af",
    "#9f1239", "#365314", "#92400e", "#5b21b6", "#155e75",
]


def fallback_svg(name: str) -> str:
    if not name:
        name = "?"
    initial = name[0].upper()
    # Deterministic color from name
    h = hashlib.md5(name.encode("utf-8")).digest()
    color = _FALLBACK_COLORS[h[0] % len(_FALLBACK_COLORS)]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        f'<circle cx="48" cy="48" r="48" fill="{color}"/>'
        f'<text x="48" y="52" text-anchor="middle" dominant-baseline="central" '
        f'font-family="Inter, system-ui, sans-serif" font-size="44" font-weight="600" '
        f'fill="#ffffff">{initial}</text>'
        '</svg>'
    )
```

- [ ] **Step 7.4: Add the `/avatar-fallback/{name}` endpoint to `server/routes/web.py`**

Append to `server/routes/web.py`:

```python
from fastapi.responses import Response
from server.avatars import fallback_svg


@router.get("/avatar-fallback/{name}")
def avatar_fallback(name: str):
    return Response(
        content=fallback_svg(name),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=31536000"},
    )
```

- [ ] **Step 7.5: Run tests**

```bash
pytest tests/test_avatars.py -v
```

Expected: all 11 pass.

- [ ] **Step 7.6: Commit**

```bash
git add server/avatars.py server/routes/web.py tests/test_avatars.py
git commit -m "feat(avatars): vendor detection by name prefix + SVG fallback endpoint"
```

---

## Task 8: Lineage walker

**Files:**
- Create: `server/lineage.py`
- Create: `tests/test_lineage.py`

- [ ] **Step 8.1: Write tests first**

Create `tests/test_lineage.py`:

```python
# tests/test_lineage.py
from server.models import Room, Participant, Post
from server.lineage import lineage_of, comments_for_lineage
from datetime import datetime


def _setup_room(db_session):
    room = Room(title="T", problem="P", status="open", max_rounds=20, created_at=datetime.utcnow())
    db_session.add(room); db_session.commit()
    p = Participant(room_id=room.id, name="a", role="producer", token="t", registered_at=datetime.utcnow())
    db_session.add(p); db_session.commit()
    return room, p


def test_lineage_root_only(db_session):
    room, p = _setup_room(db_session)
    proof = Post(room_id=room.id, author_id=p.id, type="proof", body="v1", created_at=datetime.utcnow())
    db_session.add(proof); db_session.commit()
    line = lineage_of(db_session, proof)
    assert [x.id for x in line] == [proof.id]


def test_lineage_root_and_revisions(db_session):
    room, p = _setup_room(db_session)
    v1 = Post(room_id=room.id, author_id=p.id, type="proof", body="v1", created_at=datetime.utcnow())
    db_session.add(v1); db_session.commit()
    v2 = Post(room_id=room.id, author_id=p.id, type="revision", parent_id=v1.id, body="v2", created_at=datetime.utcnow())
    db_session.add(v2); db_session.commit()
    v1.superseded_by = v2.id
    v3 = Post(room_id=room.id, author_id=p.id, type="revision", parent_id=v2.id, body="v3", created_at=datetime.utcnow())
    db_session.add(v3); db_session.commit()
    v2.superseded_by = v3.id
    db_session.commit()

    # From any version, lineage returns all in chronological order
    for start in (v1, v2, v3):
        line = lineage_of(db_session, start)
        assert [x.id for x in line] == [v1.id, v2.id, v3.id]


def test_comments_for_lineage(db_session):
    room, a = _setup_room(db_session)
    b = Participant(room_id=room.id, name="b", role="producer", token="t2", registered_at=datetime.utcnow(),
                    first_post_at=datetime.utcnow())
    db_session.add(b); db_session.commit()
    a.first_post_at = datetime.utcnow()
    v1 = Post(room_id=room.id, author_id=a.id, type="proof", body="v1", created_at=datetime.utcnow())
    db_session.add(v1); db_session.commit()
    # comment on v1
    c1 = Post(room_id=room.id, author_id=b.id, type="comment", parent_id=v1.id, body="c1", created_at=datetime.utcnow())
    db_session.add(c1); db_session.commit()
    # revision
    v2 = Post(room_id=room.id, author_id=a.id, type="revision", parent_id=v1.id, body="v2", created_at=datetime.utcnow())
    db_session.add(v2); db_session.commit()
    v1.superseded_by = v2.id; db_session.commit()
    # comment on v2
    c2 = Post(room_id=room.id, author_id=b.id, type="comment", parent_id=v2.id, body="c2", created_at=datetime.utcnow())
    # reply to c1
    c3 = Post(room_id=room.id, author_id=a.id, type="comment", parent_id=c1.id, body="reply", created_at=datetime.utcnow())
    # agree on v2
    ag = Post(room_id=room.id, author_id=b.id, type="agree", parent_id=v2.id, body=None, created_at=datetime.utcnow())
    db_session.add_all([c2, c3, ag]); db_session.commit()

    comments = comments_for_lineage(db_session, v2)
    ids = [x.id for x in comments]
    # all three comments + the agree, chronological
    assert set(ids) == {c1.id, c2.id, c3.id, ag.id}
    # sorted by created_at
    times = [x.created_at for x in comments]
    assert times == sorted(times)
```

- [ ] **Step 8.2: Run tests — all fail (module missing)**

```bash
pytest tests/test_lineage.py -v
```

- [ ] **Step 8.3: Create `server/lineage.py`**

```python
# server/lineage.py
from typing import List
from sqlalchemy.orm import Session
from server.models import Post


def lineage_of(db: Session, post: Post) -> List[Post]:
    """Return the full lineage of a proof — root proof + all revisions, in chronological (creation) order.

    Given any post in the lineage, walks parent_id back until type='proof' to find the root,
    then walks superseded_by forward to enumerate every version.
    """
    # Walk back to the root proof
    cur = post
    while cur.type == "revision" and cur.parent_id is not None:
        parent = db.query(Post).filter(Post.id == cur.parent_id).one()
        cur = parent
    root = cur

    # Walk forward via superseded_by
    chain = [root]
    while chain[-1].superseded_by is not None:
        nxt = db.query(Post).filter(Post.id == chain[-1].superseded_by).one()
        chain.append(nxt)
    return chain


def comments_for_lineage(db: Session, anchor: Post) -> List[Post]:
    """Return all comment + agree posts whose parent_id is in the lineage of `anchor`
    OR whose parent_id is a comment in this set (recursive closure). Sorted by created_at."""
    line_ids = {p.id for p in lineage_of(db, anchor)}
    out: List[Post] = []
    frontier = set(line_ids)
    seen_comment_ids: set[int] = set()
    while frontier:
        children = (db.query(Post)
                    .filter(Post.parent_id.in_(frontier),
                            Post.type.in_(("comment", "agree")))
                    .all())
        new_ids = set()
        for c in children:
            if c.id in seen_comment_ids:
                continue
            seen_comment_ids.add(c.id)
            out.append(c)
            if c.type == "comment":
                new_ids.add(c.id)
        frontier = new_ids
    out.sort(key=lambda p: p.created_at)
    return out
```

- [ ] **Step 8.4: Run tests — expect pass**

```bash
pytest tests/test_lineage.py -v
```

Expected: 3 pass.

- [ ] **Step 8.5: Commit**

```bash
git add server/lineage.py tests/test_lineage.py
git commit -m "feat(lineage): proof lineage walker + lineage-wide comments query"
```

---

## Task 9: Centralized markdown rendering

**Files:**
- Create: `server/markdown_render.py`

- [ ] **Step 9.1: Create `server/markdown_render.py`**

```python
# server/markdown_render.py
import markdown as _md

_md_instance = _md.Markdown(
    extensions=[
        "fenced_code",
        "tables",
        "sane_lists",
        "smarty",
    ],
    output_format="html5",
)


def render(text: str) -> str:
    """Render markdown. LaTeX delimiters ($...$, $$...$$) are left as-is for client-side KaTeX."""
    if not text:
        return ""
    _md_instance.reset()
    return _md_instance.convert(text)
```

- [ ] **Step 9.2: Smoke test**

```bash
source .venv/bin/activate
python -c "from server.markdown_render import render; print(render('# Hello\n\nThis is **bold** and \$x^2\$ math.'))"
```

Expected output (formatting may differ slightly):
```
<h1>Hello</h1>
<p>This is <strong>bold</strong> and $x^2$ math.</p>
```

Note that `$x^2$` is left intact for KaTeX.

- [ ] **Step 9.3: Commit**

```bash
git add server/markdown_render.py
git commit -m "feat(render): centralized markdown rendering with standard extensions"
```

---

## Task 10: Download and bundle assets — fonts, KaTeX, avatar SVGs

**Files:**
- Create: `server/static/fonts/`, `server/static/katex/`, `server/static/avatars/`

This task fetches third-party assets. It's a single bundled commit because the bytes are immutable and committing them lets the build work offline.

- [ ] **Step 10.1: Fetch Inter (variable, woff2)**

```bash
cd /Volumes/Applications/code/AI-discuss-room
mkdir -p server/static/fonts
curl -sL https://rsms.me/inter/font-files/InterVariable.woff2 -o server/static/fonts/inter-variable.woff2
ls -la server/static/fonts/inter-variable.woff2
```

Expected: file ≥ 300 KB. If 404, fallback: `curl -sL https://github.com/rsms/inter/raw/master/docs/font-files/InterVariable.woff2 -o server/static/fonts/inter-variable.woff2`

- [ ] **Step 10.2: Fetch Newsreader (regular + italic variable, woff2)**

```bash
curl -sL https://fonts.gstatic.com/s/newsreader/v22/cY9qfjOCX1hbuyalUrK49dLac06G1ZGsZBtoBCzBDXXD9JVF438w-FaJF6lL.woff2 -o server/static/fonts/newsreader-variable.woff2
ls -la server/static/fonts/newsreader-variable.woff2
```

Expected: file ≥ 50 KB.

- [ ] **Step 10.3: Fetch JetBrains Mono (variable, woff2)**

```bash
curl -sL https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/variable/JetBrainsMono%5Bwght%5D.ttf -o /tmp/jbm.ttf
# Convert to woff2 isn't trivial without fonttools — use the static regular weight in woff2 instead
curl -sL https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/webfonts/JetBrainsMono-Regular.woff2 -o server/static/fonts/jetbrainsmono-regular.woff2
ls -la server/static/fonts/jetbrainsmono-regular.woff2
```

Expected: woff2 file ≥ 30 KB. Cleanup `/tmp/jbm.ttf`.

- [ ] **Step 10.4: Fetch KaTeX bundle**

```bash
mkdir -p server/static/katex/fonts
KATEX_VER="0.16.10"
curl -sL https://cdn.jsdelivr.net/npm/katex@${KATEX_VER}/dist/katex.min.css -o server/static/katex/katex.min.css
curl -sL https://cdn.jsdelivr.net/npm/katex@${KATEX_VER}/dist/katex.min.js -o server/static/katex/katex.min.js
curl -sL https://cdn.jsdelivr.net/npm/katex@${KATEX_VER}/dist/contrib/auto-render.min.js -o server/static/katex/auto-render.min.js
# Fonts referenced by katex.min.css — fetch the most commonly-used ones
for f in KaTeX_Main-Regular KaTeX_Main-Bold KaTeX_Main-Italic KaTeX_Math-Italic KaTeX_Size1-Regular KaTeX_Size2-Regular KaTeX_AMS-Regular; do
  curl -sL "https://cdn.jsdelivr.net/npm/katex@${KATEX_VER}/dist/fonts/${f}.woff2" -o "server/static/katex/fonts/${f}.woff2"
done
ls -la server/static/katex/ server/static/katex/fonts/
```

Expected: katex.min.css ≥ 20 KB, katex.min.js ≥ 200 KB, 7 woff2 font files.

The katex.min.css references fonts at `fonts/KaTeX_*.woff2` (relative) — the layout above satisfies that.

- [ ] **Step 10.5: Fetch vendor avatar SVGs from SimpleIcons**

```bash
mkdir -p server/static/avatars
# SimpleIcons CDN URL pattern: https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/<slug>.svg
for vendor in claude openai deepseek qwen googlegemini meta mistralai; do
  case $vendor in
    googlegemini) out=gemini ;;
    mistralai)    out=mistral ;;
    *)            out=$vendor ;;
  esac
  curl -sL "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/${vendor}.svg" -o "server/static/avatars/${out}.svg"
done

# SimpleIcons SVGs are flat black — they need to be styled. Inspect one:
head -5 server/static/avatars/claude.svg

# Wrap each SVG in a styling group so it renders as a colored circle background.
# Use a Python one-liner for portability across macOS/Linux sed differences.
python3 - <<'PY'
from pathlib import Path
import re

VENDOR_BG = {
    "claude":   "#cc785c",   # Anthropic terracotta
    "openai":   "#000000",
    "deepseek": "#4d6bfe",
    "qwen":     "#615ced",
    "gemini":   "#4285f4",
    "meta":     "#0866ff",
    "mistral":  "#fa520f",
}

for path in Path("server/static/avatars").glob("*.svg"):
    name = path.stem
    bg = VENDOR_BG.get(name, "#475569")
    raw = path.read_text()
    # SimpleIcons SVGs are 24x24 with a <path> for the mark.
    # Replace the whole document with a circle-background + centered mark composition.
    m = re.search(r"<path[^>]*\bd=\"([^\"]+)\"", raw)
    if not m:
        print(f"warn: no <path d=> in {path}")
        continue
    d = m.group(1)
    new = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
        f'<circle cx="48" cy="48" r="48" fill="{bg}"/>'
        '<g transform="translate(24,24) scale(2)">'
        f'<path d="{d}" fill="#ffffff"/>'
        '</g>'
        '</svg>'
    )
    path.write_text(new)
    print(f"styled: {path.name}")
PY

ls -la server/static/avatars/
```

Expected: 7 SVG files (claude.svg, openai.svg, deepseek.svg, qwen.svg, gemini.svg, meta.svg, mistral.svg), each a styled 96x96 circle-background composition.

- [ ] **Step 10.6: Commit**

```bash
git add server/static/fonts/ server/static/katex/ server/static/avatars/
git commit -m "chore(assets): bundle Inter/Newsreader/JBM fonts, KaTeX 0.16.10, vendor avatars"
```

---

## Task 11: New `server/static/styles.css` — academic visual system

**Files:**
- Create: `server/static/styles.css`

- [ ] **Step 11.1: Create the stylesheet**

```bash
cat > server/static/styles.css <<'CSS'
/* ─── Tokens ─────────────────────────────────────────────────────────── */
:root {
  --bg:          #fafaf7;
  --surface:     #ffffff;
  --text:        #1a1a1a;
  --text-muted:  #6b6b66;
  --border:      #e8e6df;
  --accent:      #1d4ed8;
  --accent-hover:#1e40af;
  --success:     #15803d;
  --success-bg:  #dcfce7;
  --warning:     #a16207;
  --warning-bg:  #fef3c7;
  --danger:      #b91c1c;
  --danger-bg:   #fee2e2;
  --shadow-1:    0 1px 2px rgb(0 0 0 / 0.04);
  --radius:      8px;
  --radius-sm:   4px;
  --container:   1100px;
  --article:     720px;
}

/* ─── Fonts ──────────────────────────────────────────────────────────── */
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/inter-variable.woff2') format('woff2');
  font-weight: 100 900;
  font-display: swap;
}
@font-face {
  font-family: 'Newsreader';
  src: url('/static/fonts/newsreader-variable.woff2') format('woff2');
  font-weight: 200 800;
  font-display: swap;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('/static/fonts/jetbrainsmono-regular.woff2') format('woff2');
  font-weight: 400;
  font-display: swap;
}

/* ─── Reset + base ───────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', system-ui, -apple-system, "Helvetica Neue", sans-serif;
  font-size: 15px;
  line-height: 1.5;
}
a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-hover); text-decoration: underline; }
h1, h2, h3, h4 { font-family: 'Inter', sans-serif; font-weight: 600; line-height: 1.25; margin: 0 0 0.5em; }
h1 { font-size: 28px; }
h2 { font-size: 20px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; font-size: 13px; }
h3 { font-size: 17px; }
hr { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
code, pre { font-family: 'JetBrains Mono', ui-monospace, monospace; }
button { font-family: inherit; font-size: 14px; cursor: pointer; }
input, textarea, select { font-family: inherit; font-size: 14px; }
input:focus, textarea:focus, select:focus { outline: 2px solid var(--accent); outline-offset: 1px; }

/* ─── Layout ─────────────────────────────────────────────────────────── */
.container { max-width: var(--container); margin: 0 auto; padding: 0 24px; }
.nav {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 12px 0;
  margin-bottom: 24px;
}
.nav-inner { display: flex; align-items: center; justify-content: space-between; }
.nav-brand { font-weight: 700; font-size: 16px; color: var(--text); }
.nav-brand:hover { text-decoration: none; }
.nav-links a { margin-left: 16px; color: var(--text-muted); font-size: 14px; }
.nav-links a.primary { color: var(--accent); }
.page { padding-bottom: 64px; }

/* ─── Card ───────────────────────────────────────────────────────────── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow-1);
  margin-bottom: 16px;
}
.card.consensus-winner {
  border-left: 4px solid var(--success);
}

/* ─── Badge ──────────────────────────────────────────────────────────── */
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid currentColor;
  background: color-mix(in srgb, currentColor 8%, transparent);
}
.badge.state-open      { color: var(--accent); }
.badge.state-closed-consensus { color: var(--success); }
.badge.state-closed-capped, .badge.state-closed-manual { color: var(--text-muted); }
.badge.role-producer   { color: var(--accent); }
.badge.role-reviewer   { color: var(--warning); }
.badge.type-proof      { color: var(--accent); }
.badge.type-revision   { color: var(--warning); }
.badge.type-comment    { color: var(--text-muted); }
.badge.type-agree      { color: var(--success); }
.badge.consensus-mark  { color: var(--success); background: var(--success-bg); border-color: var(--success); font-weight: 600; }

/* ─── Buttons ────────────────────────────────────────────────────────── */
.btn {
  display: inline-block;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  font-weight: 500;
  border: 1px solid transparent;
  transition: background 75ms, color 75ms;
  text-decoration: none;
}
.btn-primary   { background: var(--accent); color: white; border-color: var(--accent); }
.btn-primary:hover { background: var(--accent-hover); color: white; text-decoration: none; }
.btn-secondary { background: var(--surface); color: var(--accent); border-color: var(--accent); }
.btn-secondary:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }

/* ─── Avatar ─────────────────────────────────────────────────────────── */
.avatar {
  display: inline-block;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: white;
  vertical-align: middle;
  object-fit: cover;
}
.avatar-24 { width: 24px; height: 24px; }
.avatar-32 { width: 32px; height: 32px; }
.avatar-48 { width: 48px; height: 48px; }
.avatar-96 { width: 96px; height: 96px; }

.avatar-stack { display: inline-flex; }
.avatar-stack .avatar { margin-left: -8px; box-shadow: 0 0 0 2px var(--surface); }
.avatar-stack .avatar:first-child { margin-left: 0; }

/* ─── Article (post body) ────────────────────────────────────────────── */
.article {
  max-width: var(--article);
  margin: 0 auto;
  font-family: 'Newsreader', Georgia, serif;
  font-size: 18px;
  line-height: 1.7;
  color: var(--text);
}
.article h1 { font-family: 'Newsreader', serif; font-size: 30px; font-weight: 600; text-transform: none; letter-spacing: 0; color: var(--text); margin: 24px 0 16px; }
.article h2 { font-family: 'Newsreader', serif; font-size: 22px; font-weight: 600; text-transform: none; letter-spacing: 0; color: var(--text); margin: 24px 0 12px; }
.article h3 { font-family: 'Newsreader', serif; font-size: 18px; font-weight: 600; margin: 16px 0 8px; }
.article p  { margin: 0 0 16px; }
.article ul, .article ol { padding-left: 24px; margin: 0 0 16px; }
.article code { background: #f4f3ee; padding: 1px 5px; border-radius: 3px; font-size: 0.88em; }
.article pre  { background: #f4f3ee; padding: 16px; border-radius: var(--radius-sm); border: 1px solid var(--border); overflow-x: auto; }
.article pre code { background: none; padding: 0; }
.article blockquote { border-left: 3px solid var(--border); padding-left: 16px; color: var(--text-muted); margin: 16px 0; }
.article table { border-collapse: collapse; margin: 16px 0; }
.article th, .article td { border: 1px solid var(--border); padding: 8px 12px; }
.article th { background: #f4f3ee; font-weight: 600; }
.article .katex-display { margin: 24px 0; }
.article a { text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 2px; }

.superseded-banner {
  max-width: var(--article);
  margin: 0 auto 24px;
  padding: 12px 16px;
  background: var(--warning-bg);
  border-left: 3px solid var(--warning);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: 14px;
}

.consensus-banner {
  background: var(--success-bg);
  border: 1px solid var(--success);
  border-radius: var(--radius);
  padding: 20px 24px;
  margin-bottom: 24px;
}
.consensus-banner h3 { margin: 0 0 4px; color: var(--success); }
.consensus-banner p  { margin: 0; color: var(--text); }

/* ─── Room list cards ────────────────────────────────────────────────── */
.room-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}
@media (min-width: 768px) {
  .room-grid { grid-template-columns: repeat(2, 1fr); }
}
.room-grid .card { margin-bottom: 0; }
.room-grid .card a.title-link { color: var(--text); }
.room-grid .card a.title-link:hover { color: var(--accent); text-decoration: none; }

.room-card-title  { font-size: 17px; font-weight: 600; margin-bottom: 8px; }
.room-card-meta   { color: var(--text-muted); font-size: 13px; margin-top: 12px; }

/* ─── Post page header / meta ───────────────────────────────────────── */
.post-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.post-meta .author-name { font-weight: 600; }
.post-meta .muted { color: var(--text-muted); font-size: 13px; }
.version-picker {
  margin-left: auto;
  font-size: 13px;
}
.version-picker select { padding: 4px 8px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); }

.post-status { 
  max-width: var(--article); margin: 24px auto 0;
  padding: 16px; border-top: 1px solid var(--border); 
  font-size: 14px; color: var(--text-muted);
}

/* ─── Comment thread ─────────────────────────────────────────────────── */
.comments {
  max-width: var(--article);
  margin: 32px auto 0;
}
.comments-heading {
  font-family: 'Inter', sans-serif;
  font-size: 13px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 16px;
}
.comment {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 18px;
  margin-bottom: 12px;
}
.comment.is-reply { margin-left: 32px; }
.comment-meta { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-muted); margin-bottom: 6px; }
.comment-meta .author { font-weight: 500; color: var(--text); }
.comment-body { font-family: 'Newsreader', Georgia, serif; font-size: 16px; line-height: 1.6; }
.agree-line {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 18px; margin-bottom: 12px;
  font-size: 13px; color: var(--success);
}

/* ─── Forms ──────────────────────────────────────────────────────────── */
.form { max-width: 480px; margin: 32px auto; }
.form .field { margin-bottom: 16px; }
.form label { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 4px; }
.form input[type=text],
.form input[type=password],
.form input[type=number],
.form textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
}
.form textarea { font-family: 'JetBrains Mono', monospace; font-size: 13px; min-height: 240px; }
.form-error { color: var(--danger); background: var(--danger-bg); border: 1px solid var(--danger); padding: 10px 14px; border-radius: var(--radius-sm); margin-bottom: 16px; font-size: 14px; }
.form-success { color: var(--success); background: var(--success-bg); border: 1px solid var(--success); padding: 10px 14px; border-radius: var(--radius-sm); margin-bottom: 16px; font-size: 14px; }

/* ─── Audit table ────────────────────────────────────────────────────── */
.audit-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.audit-table th, .audit-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: left; }
.audit-table th { color: var(--text-muted); font-weight: 500; }
.audit-table tr.kind-read { color: var(--text-muted); }
.audit-table code { background: #f4f3ee; padding: 1px 5px; border-radius: 3px; }
CSS

ls -la server/static/styles.css
```

Expected: file ≥ 5 KB.

- [ ] **Step 11.2: Commit**

```bash
git add server/static/styles.css
git commit -m "feat(ui): new academic visual system (styles.css with full token set)"
```

---

## Task 12: New base template + nav partial + avatar macro

**Files:**
- Modify: `server/templates/base.html` (full rewrite)
- Create: `server/templates/partials/_nav.html`
- Create: `server/templates/partials/_avatar.html`
- Modify: `server/routes/web.py` (expose `current_admin` to templates)

- [ ] **Step 12.1: Create `server/templates/partials/_avatar.html`**

```html
{% macro avatar(name, size=32) -%}
<img class="avatar avatar-{{ size }}" src="{{ avatar_url(name) }}" alt="{{ name }}" width="{{ size }}" height="{{ size }}" loading="lazy">
{%- endmacro %}
```

- [ ] **Step 12.2: Create `server/templates/partials/_nav.html`**

```html
<nav class="nav">
  <div class="container nav-inner">
    <a href="/" class="nav-brand">AI Discuss Room</a>
    <div class="nav-links">
      {% if current_admin %}
        <a href="/admin/new-room" class="primary">+ New Room</a>
        <a href="/admin/settings">Settings</a>
        <form method="post" action="/admin/logout" style="display:inline;">
          <button type="submit" style="background:none;border:none;color:var(--text-muted);cursor:pointer;padding:0;font-size:14px;">Logout</button>
        </form>
      {% else %}
        <a href="/admin/login">Sign in</a>
      {% endif %}
    </div>
  </div>
</nav>
```

- [ ] **Step 12.3: Replace `server/templates/base.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}AI Discuss Room{% endblock %}</title>
  <link rel="stylesheet" href="/static/styles.css">
  {% if include_katex %}
  <link rel="stylesheet" href="/static/katex/katex.min.css">
  <script defer src="/static/katex/katex.min.js"></script>
  <script defer src="/static/katex/auto-render.min.js" onload="
    renderMathInElement(document.body, {
      delimiters: [
        {left: '$$', right: '$$', display: true},
        {left: '$', right: '$', display: false},
        {left: '\\[', right: '\\]', display: true},
        {left: '\\(', right: '\\)', display: false}
      ],
      throwOnError: false
    });
  "></script>
  {% endif %}
  <script src="/static/htmx.min.js"></script>
</head>
<body>
  {% include "partials/_nav.html" %}
  <main class="container page">
    {% block body %}{% endblock %}
  </main>
</body>
</html>
```

- [ ] **Step 12.4: Update `server/routes/web.py` to inject `current_admin` and `avatar_url` into every template**

At the top of `server/routes/web.py`, near the imports, add:

```python
from server.auth import current_admin_or_none
from server.avatars import avatar_url
```

Then add a helper that builds the common context dict:

```python
def _ctx(request: Request, db: Session, extra: dict | None = None) -> dict:
    base = {
        "current_admin": current_admin_or_none(request, db),
        "avatar_url": avatar_url,
    }
    if extra:
        base.update(extra)
    return base
```

**Replace every `_templates().TemplateResponse(request, "X.html", {...})` call in this file** to pass `_ctx(request, db, {...})` as the context dict. There are currently 5 such calls (index, room_view, timeline_partial, post_detail, room_audit, new_room_form). Concretely:

- `return _templates().TemplateResponse(request, "index.html", {"rooms": out})` →
  `return _templates().TemplateResponse(request, "index.html", _ctx(request, db, {"rooms": out}))`
- Apply the same wrapping to all template responses in this file.

- [ ] **Step 12.5: Smoke test — page renders without 500**

```bash
source .venv/bin/activate
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_SECRET_KEY=devkey \
  uvicorn server.main:app --port 8000 &
SPID=$!
sleep 2
curl -sS --noproxy '*' http://127.0.0.1:8000/ | head -20
echo "---"
curl -sS --noproxy '*' -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/static/styles.css
kill $SPID
```

Expected: HTML output begins with `<!doctype html>` and contains `nav-brand`. `/static/styles.css` returns 200.

- [ ] **Step 12.6: Commit**

```bash
git add -A
git commit -m "feat(web): new base template with nav, avatar macro, katex hook"
```

---

## Task 13: Restyle `index.html` (room list card grid)

**Files:**
- Modify: `server/templates/index.html`

- [ ] **Step 13.1: Replace `server/templates/index.html`**

```html
{% extends "base.html" %}
{% block title %}Discussion Rooms{% endblock %}
{% block body %}
{% from "partials/_avatar.html" import avatar %}

<header style="margin-bottom: 24px;">
  <h1>Discussion Rooms</h1>
  <p style="color: var(--text-muted); margin: 0;">Multi-AI peer-review for difficult problems</p>
</header>

{% if rooms %}
<div class="room-grid">
  {% for r in rooms %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;">
      <a class="title-link room-card-title" href="/room/{{ r.id }}">#{{ r.id }} · {{ r.title }}</a>
      <span class="badge state-{{ r.status.replace('_','-') }}">{{ r.status }}</span>
    </div>

    {% if r.participants %}
    <div style="margin-top: 12px;">
      <span style="font-size:12px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">Participants</span>
      <div class="avatar-stack" style="margin-top:6px;">
        {% for name in r.participants %}{{ avatar(name, 24) }}{% endfor %}
      </div>
    </div>
    {% endif %}

    <div class="room-card-meta">
      {{ r.post_count }} posts · {{ r.participant_count }} participant{% if r.participant_count != 1 %}s{% endif %}
    </div>
  </div>
  {% endfor %}
</div>
{% else %}
<div class="card">
  <p style="color: var(--text-muted); margin: 0;">No rooms yet.{% if current_admin %} <a href="/admin/new-room">Create one →</a>{% endif %}</p>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 13.2: Update the `index` route in `server/routes/web.py` to pass participant names**

In `server/routes/web.py`, in the `index` function, change the room dict construction to include participant names:

```python
@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    rooms = db.query(Room).order_by(Room.id.desc()).all()
    out = []
    for r in rooms:
        pc = db.query(func.count(Participant.id)).filter(Participant.room_id == r.id).scalar()
        postc = db.query(func.count(Post.id)).filter(Post.room_id == r.id).scalar()
        names = [n for (n,) in db.query(Participant.name).filter(Participant.room_id == r.id).all()]
        out.append({"id": r.id, "title": r.title, "status": r.status,
                    "participant_count": pc, "post_count": postc,
                    "participants": names})
    return _templates().TemplateResponse(request, "index.html", _ctx(request, db, {"rooms": out}))
```

- [ ] **Step 13.3: Smoke test in browser (manual)**

```bash
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_SECRET_KEY=devkey \
  uvicorn server.main:app --port 8000 &
SPID=$!
sleep 2
# Add a test room via Basic auth (Task 1 setup admin password is 'admin114514')
curl -sS --noproxy '*' -u admin:admin114514 -X POST http://127.0.0.1:8000/rooms \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Room","problem":"Hello","max_rounds":20}' >/dev/null
# Fetch homepage
curl -sS --noproxy '*' http://127.0.0.1:8000/ | grep -E "room-grid|Test Room"
kill $SPID
```

Expected: `room-grid` div present and "Test Room" appears in the HTML.

- [ ] **Step 13.4: Commit**

```bash
git add -A
git commit -m "feat(web): redesign room list as card grid with avatar stack"
```

---

## Task 14: Restyle `room.html` (consensus banner + proof cards + participant strip)

**Files:**
- Modify: `server/templates/room.html`
- Modify: `server/routes/web.py` (room_view function)

- [ ] **Step 14.1: Update `server/routes/web.py`'s `room_view` to pass richer context**

Replace the existing `room_view` function:

```python
@router.get("/room/{room_id}", response_class=HTMLResponse)
def room_view(request: Request, room_id: int, db: Session = Depends(get_db)):
    room = _room_or_404(db, room_id)
    participants = db.query(Participant).filter(Participant.room_id == room_id).all()
    current = (db.query(Post)
               .filter(Post.room_id == room_id,
                       Post.type.in_(("proof", "revision")),
                       Post.superseded_by.is_(None)).all())
    current_proofs = []
    for c in current:
        agrees = (db.query(Post)
                  .filter(Post.room_id == room_id, Post.type == "agree", Post.parent_id == c.id)
                  .all())
        # body preview: first non-empty line
        preview = ""
        if c.body:
            for line in c.body.splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    preview = line[:140]
                    break
        # version number: count revisions back to root
        version = 1
        cur = c
        while cur.parent_id is not None and cur.type == "revision":
            version += 1
            cur = db.query(Post).filter(Post.id == cur.parent_id).one()
        current_proofs.append({
            "id": c.id, "author": c.author.name, "preview": preview,
            "agree_count": len(agrees),
            "agreed_by": [a.author.name for a in agrees],
            "ts": c.created_at, "version": version,
            "is_consensus": (room.status == "closed_consensus" and room.closed_proof_id == c.id),
        })

    consensus_proof = None
    if room.status == "closed_consensus" and room.closed_proof_id:
        cp = db.query(Post).filter(Post.id == room.closed_proof_id).one_or_none()
        if cp:
            preview = ""
            if cp.body:
                for line in cp.body.splitlines():
                    line = line.strip().lstrip("#").strip()
                    if line:
                        preview = line[:140]
                        break
            consensus_proof = {"id": cp.id, "author": cp.author.name, "preview": preview}

    from server.markdown_render import render
    problem_html = render(room.problem)
    parts = [{"name": p.name, "role": p.role,
              "has_published_first": p.first_post_at is not None}
             for p in participants]
    return _templates().TemplateResponse(
        request, "room.html",
        _ctx(request, db, {
            "room": room, "participants": parts, "current_proofs": current_proofs,
            "problem_html": problem_html, "consensus_proof": consensus_proof,
            "include_katex": True,
        }),
    )
```

Note: This also swaps the inline `markdown.markdown(...)` call for the centralized `server.markdown_render.render`. Remove the `import markdown as md` line if present at the top of the file.

- [ ] **Step 14.2: Replace `server/templates/room.html`**

```html
{% extends "base.html" %}
{% block title %}Room {{ room.id }} — {{ room.title }}{% endblock %}
{% block body %}
{% from "partials/_avatar.html" import avatar %}

<header style="margin-bottom: 8px;">
  <p style="margin:0 0 4px;"><a href="/" style="color:var(--text-muted);font-size:13px;">← Rooms</a></p>
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
    <h1 style="margin:0;">#{{ room.id }} · {{ room.title }}</h1>
    <span class="badge state-{{ room.status.replace('_','-') }}">{{ room.status }}</span>
  </div>
  <div style="color:var(--text-muted);font-size:13px;margin-top:8px;">
    Created {{ room.created_at.strftime("%Y-%m-%d") }} ·
    {{ participants|length }} participants ·
    <a href="/room/{{ room.id }}/audit">View audit →</a>
  </div>
</header>

<section style="margin: 32px 0;">
  <h2>Problem</h2>
  <div class="article" style="margin: 0; font-size: 16px;">
    {{ problem_html|safe }}
  </div>
</section>

<section style="margin: 32px 0;">
  <h2>Participants</h2>
  <div style="display:flex;flex-wrap:wrap;gap:16px;">
    {% for p in participants %}
    <div style="display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--border);border-radius:999px;padding:6px 14px 6px 6px;">
      {{ avatar(p.name, 32) }}
      <div>
        <div style="font-weight:500;">{{ p.name }}</div>
        <div style="font-size:12px;color:var(--text-muted);">
          <span class="badge role-{{ p.role }}">{{ p.role }}</span>
          {% if p.has_published_first %}<span style="margin-left:6px;color:var(--success);">✓ posted</span>{% endif %}
        </div>
      </div>
    </div>
    {% endfor %}
  </div>
</section>

{% if consensus_proof %}
<section style="margin: 32px 0;">
  <div class="consensus-banner">
    <h3>✓ Consensus reached on Post #{{ consensus_proof.id }}</h3>
    <p>{% if consensus_proof.preview %}"{{ consensus_proof.preview }}"{% endif %}
       — by <strong>{{ consensus_proof.author }}</strong>, all participants agreed.</p>
    <p style="margin-top: 10px;"><a href="/room/{{ room.id }}/post/{{ consensus_proof.id }}" class="btn btn-secondary">Read full post →</a></p>
  </div>
</section>
{% endif %}

<section style="margin: 32px 0;">
  <h2>Current proofs</h2>
  {% for c in current_proofs %}
  <div class="card {% if c.is_consensus %}consensus-winner{% endif %}">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
      <div style="display:flex;align-items:center;gap:10px;">
        {{ avatar(c.author, 32) }}
        <div>
          <div style="font-weight:500;">{{ c.author }}</div>
          <div style="font-size:12px;color:var(--text-muted);">
            <span class="badge type-proof">Proof v{{ c.version }}</span>
            · {{ c.ts.strftime("%Y-%m-%d %H:%M") }}
          </div>
        </div>
      </div>
      {% if c.is_consensus %}<span class="badge consensus-mark">✓ Consensus</span>{% endif %}
    </div>
    <div style="margin-top: 12px; font-family: 'Newsreader', serif; font-size: 16px; color: var(--text);">
      {{ c.preview }}
    </div>
    <div style="margin-top: 12px; display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-muted);">
      <span>agreed:</span>
      <span class="avatar-stack">
        {% for n in c.agreed_by %}{{ avatar(n, 24) }}{% endfor %}
      </span>
      <span>({{ c.agree_count }}/{{ participants|length }})</span>
      <a href="/room/{{ room.id }}/post/{{ c.id }}" style="margin-left: auto;">Read full post →</a>
    </div>
  </div>
  {% else %}
  <p style="color: var(--text-muted);">No proofs yet.</p>
  {% endfor %}
</section>

{% endblock %}
```

- [ ] **Step 14.3: Smoke test**

```bash
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_SECRET_KEY=devkey \
  uvicorn server.main:app --port 8000 &
SPID=$!
sleep 2
ROOM=$(curl -sS --noproxy '*' -u admin:admin114514 -X POST http://127.0.0.1:8000/rooms \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Room","problem":"# Hi\n\nSolve me.","max_rounds":20}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
# register two participants
TOKA=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/$ROOM/participants -H "Content-Type: application/json" -d '{"name":"claude-a","role":"producer"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
TOKB=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/$ROOM/participants -H "Content-Type: application/json" -d '{"name":"codex-1","role":"producer"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
# both post proofs
curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/$ROOM/posts -H "Content-Type: application/json" -H "Authorization: Bearer $TOKA" -d '{"type":"proof","body":"# Proof A\n\nv1 body"}' >/dev/null
curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/$ROOM/posts -H "Content-Type: application/json" -H "Authorization: Bearer $TOKB" -d '{"type":"proof","body":"# Proof B\n\nv1 body"}' >/dev/null
curl -sS --noproxy '*' http://127.0.0.1:8000/room/$ROOM | grep -E "Current proofs|claude-a|codex-1|Participants"
kill $SPID
```

Expected: HTML contains "Current proofs", "claude-a", "codex-1", "Participants".

- [ ] **Step 14.4: Commit**

```bash
git add -A
git commit -m "feat(web): redesign room view with consensus banner + proof cards + avatars"
```

---

## Task 15: Restyle audit page

**Files:**
- Modify: `server/templates/audit.html`

- [ ] **Step 15.1: Replace `server/templates/audit.html`**

```html
{% extends "base.html" %}
{% block title %}Audit — Room {{ room.id }}{% endblock %}
{% block body %}
{% from "partials/_avatar.html" import avatar %}
<p style="margin: 0 0 12px;"><a href="/room/{{ room.id }}" style="color:var(--text-muted);font-size:13px;">← back to room</a></p>
<h1>Audit · {{ room.title }}</h1>
<p style="color: var(--text-muted); font-size: 14px;">
  All events in chronological order. Read events show what each participant accessed (useful for verifying the anti-bias rule).
</p>

<table class="audit-table">
  <thead>
    <tr><th>Time</th><th>Kind</th><th>By</th><th>Detail</th></tr>
  </thead>
  <tbody>
    {% for e in events %}
    <tr class="kind-{{ e.kind }}">
      <td>{{ e.ts[:19] }}</td>
      <td><span class="badge type-{{ e.kind if e.kind != 'read' else 'comment' }}">{{ e.kind }}</span></td>
      <td>
        <span style="display:inline-flex;align-items:center;gap:6px;">
          {{ avatar(e.by, 24) }} {{ e.by }}
        </span>
      </td>
      <td><code>{{ e.detail }}</code></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 15.2: Commit**

```bash
git add server/templates/audit.html
git commit -m "feat(web): restyle audit page with new visual system"
```

---

## Task 16: Post page redesign — blog-style with version dropdown + lineage comments

**Files:**
- Modify: `server/templates/post_detail.html` (full rewrite)
- Modify: `server/routes/web.py` (`post_detail` function)

- [ ] **Step 16.1: Replace the `post_detail` route in `server/routes/web.py`**

```python
@router.get("/room/{room_id}/post/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, room_id: int, post_id: int, db: Session = Depends(get_db)):
    from server.lineage import lineage_of, comments_for_lineage
    from server.markdown_render import render
    room = _room_or_404(db, room_id)
    post = db.query(Post).filter(Post.id == post_id, Post.room_id == room_id).one_or_none()
    if not post:
        err("not_found", "post not found", http=404)

    if post.type in ("proof", "revision"):
        line = lineage_of(db, post)
    else:
        # Comments / agree don't have a "lineage" — show parent's lineage if possible
        anchor = post
        while anchor.type not in ("proof", "revision") and anchor.parent_id is not None:
            anchor = db.query(Post).filter(Post.id == anchor.parent_id).one()
        line = lineage_of(db, anchor) if anchor.type in ("proof", "revision") else [post]

    # Version labels
    versions = []
    for idx, p in enumerate(line, start=1):
        is_latest = (p.superseded_by is None)
        versions.append({
            "id": p.id, "n": idx, "ts": p.created_at,
            "label_state": "latest" if is_latest else "superseded",
            "is_current_view": (p.id == post.id),
        })
    latest_id = line[-1].id if line else post.id
    is_viewing_latest = (post.id == latest_id)

    # Comments (only for proof/revision pages)
    if post.type in ("proof", "revision"):
        comments_raw = comments_for_lineage(db, post)
    else:
        comments_raw = []
    line_ids = {p.id for p in line}
    comments = []
    for c in comments_raw:
        parent = db.query(Post).filter(Post.id == c.parent_id).one()
        if parent.type == "comment":
            target_label = f"replied to {parent.author.name}"
            is_reply = True
        else:
            # parent is a proof/revision
            # find the version label
            v_idx = next((i for i, p in enumerate(line, 1) if p.id == parent.id), None)
            target_label = f"commented on v{v_idx}" if v_idx else f"commented on #{parent.id}"
            is_reply = False
        comments.append({
            "id": c.id, "type": c.type, "author": c.author.name,
            "ts": c.created_at, "body": c.body or "",
            "target_label": target_label, "is_reply": is_reply,
        })

    # Agree-by avatars on the status row
    agrees = (db.query(Post)
              .filter(Post.room_id == room_id, Post.type == "agree",
                      Post.parent_id == post.id).all())
    agreed_by = [a.author.name for a in agrees]

    body_html = render(post.body or "")
    return _templates().TemplateResponse(
        request, "post_detail.html",
        _ctx(request, db, {
            "room": room, "post": post, "post_author": post.author.name,
            "body_html": body_html, "versions": versions,
            "is_viewing_latest": is_viewing_latest, "latest_id": latest_id,
            "this_version_n": next((v["n"] for v in versions if v["is_current_view"]), 1),
            "comments": comments, "agreed_by": agreed_by,
            "participant_count": db.query(func.count(Participant.id)).filter(Participant.room_id == room_id).scalar(),
            "include_katex": True,
        }),
    )
```

- [ ] **Step 16.2: Replace `server/templates/post_detail.html`**

```html
{% extends "base.html" %}
{% block title %}#{{ post.id }} — Room {{ room.id }}{% endblock %}
{% block body %}
{% from "partials/_avatar.html" import avatar %}

<p style="margin: 0 0 12px;"><a href="/room/{{ room.id }}" style="color:var(--text-muted);font-size:13px;">← back to Room #{{ room.id }}</a></p>

{% if not is_viewing_latest and post.type in ('proof','revision') %}
<div class="superseded-banner">
  ⚠ You're viewing v{{ this_version_n }} (superseded).
  <a href="/room/{{ room.id }}/post/{{ latest_id }}">Read latest →</a>
</div>
{% endif %}

<header class="article" style="font-family: 'Inter', sans-serif;">
  <div class="post-meta">
    {{ avatar(post_author, 48) }}
    <div>
      <div class="author-name">{{ post_author }}</div>
      <div class="muted">
        <span class="badge type-{{ post.type }}">{{ post.type }}{% if post.type in ('proof','revision') %} v{{ this_version_n }}{% endif %}</span>
        · {{ post.created_at.strftime("%Y-%m-%d %H:%M") }}
      </div>
    </div>
    {% if versions|length > 1 %}
    <div class="version-picker">
      <label for="version-select" style="color:var(--text-muted);">Viewing:</label>
      <select id="version-select" onchange="if(this.value){window.location='/room/{{ room.id }}/post/'+this.value;}">
        {% for v in versions %}
        <option value="{{ v.id }}" {% if v.is_current_view %}selected{% endif %}>
          v{{ v.n }} ({{ v.label_state }} · {{ v.ts.strftime("%Y-%m-%d") }})
        </option>
        {% endfor %}
      </select>
    </div>
    {% endif %}
  </div>
</header>

<article class="article">
  {{ body_html|safe }}
</article>

{% if post.type in ('proof','revision') %}
<div class="post-status">
  <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
    <span>Agreed by:</span>
    {% for n in agreed_by %}<span style="display:inline-flex;align-items:center;gap:6px;">{{ avatar(n, 24) }} {{ n }}</span>{% if not loop.last %} ·{% endif %}{% endfor %}
    {% if not agreed_by %}<span style="color:var(--text-muted);">no agrees yet</span>{% endif %}
    <span style="color:var(--text-muted);margin-left:auto;">({{ agreed_by|length }}/{{ participant_count }})</span>
  </div>
</div>
{% endif %}

{% if comments %}
<section class="comments">
  <h3 class="comments-heading">Discussion · {{ comments|length }} {% if comments|length == 1 %}reply{% else %}replies{% endif %}</h3>
  {% for c in comments %}
    {% if c.type == 'agree' %}
    <div class="agree-line">
      {{ avatar(c.author, 24) }}
      <strong>{{ c.author }}</strong> agreed · <span style="color:var(--text-muted);">{{ c.ts.strftime("%Y-%m-%d %H:%M") }}</span>
    </div>
    {% else %}
    <div class="comment {% if c.is_reply %}is-reply{% endif %}">
      <div class="comment-meta">
        {{ avatar(c.author, 24) }}
        <span class="author">{{ c.author }}</span>
        · {{ c.target_label }}
        · {{ c.ts.strftime("%Y-%m-%d %H:%M") }}
      </div>
      <div class="comment-body">{{ c.body }}</div>
    </div>
    {% endif %}
  {% endfor %}
</section>
{% endif %}

{% endblock %}
```

- [ ] **Step 16.3: Smoke test the post page with KaTeX**

```bash
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_SECRET_KEY=devkey \
  uvicorn server.main:app --port 8000 &
SPID=$!
sleep 2
ROOM=$(curl -sS --noproxy '*' -u admin:admin114514 -X POST http://127.0.0.1:8000/rooms \
  -H "Content-Type: application/json" -d '{"title":"T","problem":"hi","max_rounds":20}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
TOK=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/$ROOM/participants \
  -H "Content-Type: application/json" -d '{"name":"claude-a","role":"producer"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
POST=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/$ROOM/posts \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOK" \
  -d '{"type":"proof","body":"# Proof\n\nInline: $x^2+y^2=z^2$.\n\nDisplay: $$\\int_0^1 x\\,dx = \\tfrac{1}{2}$$"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -sS --noproxy '*' http://127.0.0.1:8000/room/$ROOM/post/$POST | grep -E "katex|article|claude-a"
kill $SPID
```

Expected: HTML contains `katex` (the asset link), `article` class, and `claude-a`.

- [ ] **Step 16.4: Commit**

```bash
git add -A
git commit -m "feat(web): post page redesign — blog-style, version dropdown, lineage comments, KaTeX"
```

---

## Task 17: Admin login + logout

**Files:**
- Create: `server/templates/admin_login.html`
- Modify: `server/routes/web.py` (login GET/POST, logout POST)

- [ ] **Step 17.1: Create `server/templates/admin_login.html`**

```html
{% extends "base.html" %}
{% block title %}Sign in{% endblock %}
{% block body %}
<form class="form" method="post" action="/admin/login">
  <h1 style="text-align:center;">Sign in</h1>

  {% if error %}<div class="form-error">{{ error }}</div>{% endif %}

  <div class="field">
    <label for="username">Username</label>
    <input id="username" name="username" type="text" required autofocus>
  </div>
  <div class="field">
    <label for="password">Password</label>
    <input id="password" name="password" type="password" required>
  </div>
  <input type="hidden" name="next" value="{{ next or '/' }}">
  <button type="submit" class="btn btn-primary" style="width:100%;">Sign in</button>
  <p style="text-align:center;margin-top:16px;font-size:13px;">
    <a href="/" style="color:var(--text-muted);">← back to discussions</a>
  </p>
</form>
{% endblock %}
```

- [ ] **Step 17.2: Add login/logout routes to `server/routes/web.py`**

Append:

```python
from fastapi.responses import RedirectResponse
from server.auth import authenticate_admin


@router.get("/admin/login", response_class=HTMLResponse)
def admin_login_get(request: Request, next: str = "/", db: Session = Depends(get_db)):
    if current_admin_or_none(request, db):
        return RedirectResponse(url=next or "/", status_code=303)
    return _templates().TemplateResponse(
        request, "admin_login.html",
        _ctx(request, db, {"next": next, "error": None}),
    )


@router.post("/admin/login", response_class=HTMLResponse)
def admin_login_post(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    user = authenticate_admin(db, username, password)
    if not user:
        return _templates().TemplateResponse(
            request, "admin_login.html",
            _ctx(request, db, {"next": next, "error": "Incorrect username or password"}),
            status_code=401,
        )
    request.session["admin_id"] = user.id
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    return RedirectResponse(url=safe_next, status_code=303)


@router.post("/admin/logout")
def admin_logout(request: Request):
    request.session.pop("admin_id", None)
    return RedirectResponse(url="/", status_code=303)
```

- [ ] **Step 17.3: Smoke test login flow**

```bash
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_SECRET_KEY=devkey \
  uvicorn server.main:app --port 8000 &
SPID=$!
sleep 2
# GET login page
curl -sS --noproxy '*' http://127.0.0.1:8000/admin/login | grep -E "Sign in|password"
# POST wrong credentials
curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/admin/login \
  --data-urlencode "username=admin" --data-urlencode "password=wrong" \
  -o /dev/null -w "%{http_code}\n"
# POST correct credentials, capture cookie
curl -sS --noproxy '*' -c /tmp/discuss.cookies -X POST http://127.0.0.1:8000/admin/login \
  --data-urlencode "username=admin" --data-urlencode "password=admin114514" -i 2>&1 | head -5
# verify cookie works
curl -sS --noproxy '*' -b /tmp/discuss.cookies http://127.0.0.1:8000/ | grep -E "New Room|Logout"
kill $SPID
rm -f /tmp/discuss.cookies
```

Expected:
- GET shows "Sign in" + "password"
- wrong creds → 401
- correct creds → 303 with Set-Cookie
- subsequent GET with cookie → page contains "New Room" and "Logout" (admin nav visible)

- [ ] **Step 17.4: Commit**

```bash
git add -A
git commit -m "feat(auth): admin login form + logout (session cookie)"
```

---

## Task 18: Migrate admin `new-room` UI to session auth

**Files:**
- Modify: `server/routes/web.py` (replace `require_admin` with `require_admin_session` on the new-room HTML routes)
- Modify: `server/templates/admin_new_room.html` (restyle)

- [ ] **Step 18.1: Edit `server/routes/web.py`**

Find the existing `new_room_form` and `new_room_submit` handlers. Replace their auth dependency from `require_admin` to `require_admin_session`. Concretely:

```python
from server.auth import require_admin_session

@router.get("/admin/new-room", response_class=HTMLResponse)
def new_room_form(
    request: Request,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin_session),
):
    return _templates().TemplateResponse(request, "admin_new_room.html", _ctx(request, db, {}))


@router.post("/admin/new-room")
def new_room_submit(
    title: str = Form(...),
    problem: str = Form(...),
    max_rounds: int = Form(20),
    request: Request = None,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_admin_session),
):
    room = Room(title=title, problem=problem, max_rounds=max_rounds,
                status="open", created_at=datetime.utcnow())
    db.add(room); db.commit(); db.refresh(room)
    return RedirectResponse(url=f"/room/{room.id}", status_code=303)
```

(Add `from server.models import AdminUser` if not yet imported in this file.)

- [ ] **Step 18.2: Handle `require_admin_session` raising 401 gracefully on the HTML route**

When the user isn't logged in, `require_admin_session` raises an HTTPException 401, but for the HTML routes we want to redirect to `/admin/login?next=/admin/new-room`. Add an exception handler in `server/main.py`:

In `server/main.py`, find `@app.exception_handler(HTTPException)` and modify the body:

```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # For HTML routes that fail auth, redirect to login instead of returning 401 JSON
    if exc.status_code == 401:
        accept = request.headers.get("accept", "")
        if "text/html" in accept and "/admin/" in str(request.url.path):
            next_url = str(request.url.path)
            if request.url.query:
                next_url += "?" + request.url.query
            return RedirectResponse(url=f"/admin/login?next={next_url}", status_code=303)
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )
```

Also add `from fastapi.responses import RedirectResponse` at the top of `server/main.py` if not present.

- [ ] **Step 18.3: Restyle `server/templates/admin_new_room.html`**

```html
{% extends "base.html" %}
{% block title %}New Room{% endblock %}
{% block body %}
<form class="form" method="post" action="/admin/new-room" style="max-width: 720px;">
  <h1>Create New Room</h1>
  <p style="color: var(--text-muted); margin: 0 0 24px;">A room hosts a single problem and the AI discussion that converges on it.</p>

  <div class="field">
    <label for="title">Title</label>
    <input id="title" name="title" type="text" required maxlength="255">
  </div>
  <div class="field">
    <label for="problem">Problem (Markdown · LaTeX with $...$)</label>
    <textarea id="problem" name="problem" required></textarea>
  </div>
  <div class="field" style="max-width: 200px;">
    <label for="max_rounds">Max rounds (per participant)</label>
    <input id="max_rounds" name="max_rounds" type="number" value="20" min="1" max="1000">
  </div>
  <button type="submit" class="btn btn-primary">Create</button>
</form>
{% endblock %}
```

- [ ] **Step 18.4: Smoke test the full admin flow**

```bash
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_SECRET_KEY=devkey \
  uvicorn server.main:app --port 8000 &
SPID=$!
sleep 2
# without login, /admin/new-room should redirect to /admin/login
curl -sS --noproxy '*' -H "Accept: text/html" -o /dev/null -w "%{http_code} %{redirect_url}\n" http://127.0.0.1:8000/admin/new-room
# log in, get cookie
curl -sS --noproxy '*' -c /tmp/c -X POST http://127.0.0.1:8000/admin/login \
  --data-urlencode "username=admin" --data-urlencode "password=admin114514" >/dev/null
# with login, /admin/new-room should return 200 form
curl -sS --noproxy '*' -b /tmp/c http://127.0.0.1:8000/admin/new-room | grep -E "Create New Room|<textarea"
# POST the form
curl -sS --noproxy '*' -b /tmp/c -X POST http://127.0.0.1:8000/admin/new-room \
  --data-urlencode "title=From Form" --data-urlencode "problem=hi" --data-urlencode "max_rounds=20" -i | head -5
kill $SPID
rm -f /tmp/c
```

Expected: 
- unauthenticated GET returns 303 with Location containing /admin/login
- authenticated GET shows form with `<textarea`
- authenticated POST returns 303 with Location /room/<id>

- [ ] **Step 18.5: Commit**

```bash
git add -A
git commit -m "feat(auth): new-room HTML routes use session auth + redirect to login on 401"
```

---

## Task 19: Admin settings page (password change)

**Files:**
- Create: `server/templates/admin_settings.html`
- Modify: `server/routes/web.py`
- Create: `tests/test_admin_auth.py`

- [ ] **Step 19.1: Write tests first**

Create `tests/test_admin_auth.py`:

```python
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
```

- [ ] **Step 19.2: Create `server/templates/admin_settings.html`**

```html
{% extends "base.html" %}
{% block title %}Settings{% endblock %}
{% block body %}
<h1>Settings</h1>
<p style="color: var(--text-muted); margin: 0 0 32px;">Signed in as <strong>{{ current_admin.username }}</strong></p>

{% if ok %}<div class="form-success">Password changed successfully.</div>{% endif %}

<form class="form" method="post" action="/admin/settings/password" style="margin-left:0;">
  <h3 style="font-family:'Inter',sans-serif;color:var(--text-muted);font-size:13px;text-transform:uppercase;letter-spacing:0.05em;">Change password</h3>
  {% if error %}<div class="form-error">{{ error }}</div>{% endif %}

  <div class="field">
    <label for="current_password">Current password</label>
    <input id="current_password" name="current_password" type="password" required autocomplete="current-password">
  </div>
  <div class="field">
    <label for="new_password">New password (≥ 8 characters)</label>
    <input id="new_password" name="new_password" type="password" required minlength="8" autocomplete="new-password">
  </div>
  <div class="field">
    <label for="confirm">Confirm new password</label>
    <input id="confirm" name="confirm" type="password" required minlength="8" autocomplete="new-password">
  </div>
  <button type="submit" class="btn btn-primary">Change password</button>
</form>
{% endblock %}
```

- [ ] **Step 19.3: Add settings routes to `server/routes/web.py`**

Append:

```python
from server.auth import verify_password, hash_password


@router.get("/admin/settings", response_class=HTMLResponse)
def admin_settings_get(
    request: Request,
    db: Session = Depends(get_db),
    ok: int = 0,
    me: AdminUser = Depends(require_admin_session),
):
    return _templates().TemplateResponse(
        request, "admin_settings.html",
        _ctx(request, db, {"ok": ok == 1, "error": None}),
    )


@router.post("/admin/settings/password")
def admin_settings_change_password(
    request: Request,
    db: Session = Depends(get_db),
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm: str = Form(...),
    me: AdminUser = Depends(require_admin_session),
):
    error = None
    if not verify_password(current_password, me.password_hash):
        error = "Current password is incorrect."
    elif new_password != confirm:
        error = "New password and confirmation do not match."
    elif len(new_password) < 8:
        error = "New password must be at least 8 characters."
    if error:
        return _templates().TemplateResponse(
            request, "admin_settings.html",
            _ctx(request, db, {"ok": False, "error": error}),
            status_code=400,
        )
    me.password_hash = hash_password(new_password)
    me.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url="/admin/settings?ok=1", status_code=303)
```

- [ ] **Step 19.4: Run the new test file + full suite**

```bash
source .venv/bin/activate
pytest tests/test_admin_auth.py -v
pytest -v 2>&1 | tail -5
```

Expected: new tests pass; total count is 42 (original) + ~11 (new auth) + 11 (avatars) + 3 (lineage) = ~67.

- [ ] **Step 19.5: Commit**

```bash
git add -A
git commit -m "feat(auth): admin settings page with password change + tests"
```

---

## Task 20: Update existing timeline partial for new visual

**Files:**
- Modify: `server/templates/partials/timeline.html`

- [ ] **Step 20.1: Replace `server/templates/partials/timeline.html`**

```html
{% from "partials/_avatar.html" import avatar %}
{% for p in posts %}
  <div class="card" style="padding:14px 18px;margin-bottom:8px;{% if p.superseded_by %}opacity:0.6;{% endif %}">
    <div style="display:flex;align-items:center;gap:10px;font-size:13px;color:var(--text-muted);">
      {{ avatar(p.author, 24) }}
      <strong style="color:var(--text);">{{ p.author }}</strong>
      <span class="badge type-{{ p.type }}">{{ p.type }}</span>
      {% if p.parent_id %}<span>→ #{{ p.parent_id }}</span>{% endif %}
      {% if p.superseded_by %}<span style="color:var(--warning);">superseded</span>{% endif %}
      <span style="margin-left:auto;">{{ p.ts }}</span>
    </div>
    {% if p.body_preview %}
    <details style="margin-top:8px;"><summary style="font-size:13px;color:var(--text-muted);cursor:pointer;">show</summary>
      <pre style="white-space:pre-wrap;background:#f4f3ee;padding:12px;border-radius:4px;margin-top:8px;">{{ p.body }}</pre>
    </details>
    {% endif %}
  </div>
{% endfor %}
```

- [ ] **Step 20.2: Commit**

```bash
git add server/templates/partials/timeline.html
git commit -m "feat(web): restyle timeline partial to match new visual system"
```

---

## Task 21: Cleanup — remove old pico CSS, full test sweep, end-to-end demo

**Files:**
- Delete: `server/static/pico.classless.min.css`

- [ ] **Step 21.1: Remove the old Pico stylesheet**

```bash
rm server/static/pico.classless.min.css
ls server/static/
```

Expected: `pico.classless.min.css` gone. `styles.css`, `htmx.min.js`, `fonts/`, `avatars/`, `katex/` remain.

- [ ] **Step 21.2: Run the full test suite one final time**

```bash
source .venv/bin/activate
pytest -v 2>&1 | tail -10
```

Expected: all tests pass. No regressions. Total ~67 tests.

- [ ] **Step 21.3: End-to-end visual smoke test**

```bash
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_SECRET_KEY=devkey \
  uvicorn server.main:app --port 8000 &
SPID=$!
sleep 2

# 1. Login as admin
curl -sS --noproxy '*' -c /tmp/c -X POST http://127.0.0.1:8000/admin/login \
  --data-urlencode "username=admin" --data-urlencode "password=admin114514" >/dev/null

# 2. Create a room with rich problem
curl -sS --noproxy '*' -b /tmp/c -X POST http://127.0.0.1:8000/admin/new-room \
  --data-urlencode "title=Rich Test" \
  --data-urlencode "problem=# Hello world

Solve this:

$$\\sqrt{2} \\notin \\mathbb{Q}$$" \
  --data-urlencode "max_rounds=20" -o /dev/null

# 3. Register two participants (different vendors)
TOKA=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/1/participants -H "Content-Type: application/json" -d '{"name":"claude-a","role":"producer"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
TOKB=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/1/participants -H "Content-Type: application/json" -d '{"name":"codex-1","role":"producer"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 4. Post + revise + agree to drive consensus
P1=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/1/posts -H "Content-Type: application/json" -H "Authorization: Bearer $TOKA" -d '{"type":"proof","body":"# Proof A v1\n\nSuppose $\\sqrt{2} = p/q$ in lowest terms..."}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
P2=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/1/posts -H "Content-Type: application/json" -H "Authorization: Bearer $TOKB" -d '{"type":"proof","body":"# Proof B v1\n\nAssume $\\sqrt{2}$ is rational..."}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/1/posts -H "Content-Type: application/json" -H "Authorization: Bearer $TOKA" -d "{\"type\":\"comment\",\"parent_id\":$P2,\"body\":\"Nice but please clarify step 3.\"}" >/dev/null
P1v2=$(curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/1/posts -H "Content-Type: application/json" -H "Authorization: Bearer $TOKA" -d "{\"type\":\"revision\",\"parent_id\":$P1,\"body\":\"# Proof A v2\n\nRevised with clarifications.\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/1/posts -H "Content-Type: application/json" -H "Authorization: Bearer $TOKA" -d "{\"type\":\"agree\",\"parent_id\":$P1v2}" >/dev/null
curl -sS --noproxy '*' -X POST http://127.0.0.1:8000/rooms/1/posts -H "Content-Type: application/json" -H "Authorization: Bearer $TOKB" -d "{\"type\":\"agree\",\"parent_id\":$P1v2}" >/dev/null

# 5. Verify pages render
echo "=== / (index) ==="
curl -sS --noproxy '*' -b /tmp/c http://127.0.0.1:8000/ | grep -cE "room-grid|Rich Test|claude|codex"
echo "=== /room/1 ==="
curl -sS --noproxy '*' -b /tmp/c http://127.0.0.1:8000/room/1 | grep -cE "consensus|Proof|claude-a|codex-1"
echo "=== /room/1/post/$P1v2 ==="
curl -sS --noproxy '*' -b /tmp/c http://127.0.0.1:8000/room/1/post/$P1v2 | grep -cE "article|katex|Proof A v2|Discussion"
echo "=== /room/1/post/$P1 (superseded view) ==="
curl -sS --noproxy '*' -b /tmp/c http://127.0.0.1:8000/room/1/post/$P1 | grep -cE "superseded|version-picker|Read latest"
echo "=== /room/1/audit ==="
curl -sS --noproxy '*' -b /tmp/c http://127.0.0.1:8000/room/1/audit | grep -cE "Audit|post|read"
echo "=== /admin/settings ==="
curl -sS --noproxy '*' -b /tmp/c http://127.0.0.1:8000/admin/settings | grep -cE "Change password|admin"
echo "=== /static/avatars/claude.svg ==="
curl -sS --noproxy '*' -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/static/avatars/claude.svg
echo "=== /static/katex/katex.min.css ==="
curl -sS --noproxy '*' -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/static/katex/katex.min.css

kill $SPID
rm -f /tmp/c
```

Expected: each grep returns a positive count (≥1). Both static asset URLs return 200.

- [ ] **Step 21.4: Commit cleanup**

```bash
git add -A
git commit -m "chore: remove obsolete pico.classless.min.css after styles.css migration"
```

---

## Self-Review

**Spec coverage check** (mapping spec sections → tasks):

- §1 Visual system → Tasks 10 (assets) + 11 (styles.css)
- §2 IA (routes + nav) → Tasks 12 (base + nav) + 17 (login routes) + 18 (admin new-room) + 19 (settings)
- §3 Room list → Task 13
- §3 Room detail → Task 14
- §3 Post page (version dropdown + lineage comments) → Tasks 8 (lineage backend) + 16 (template + route)
- §3 Audit restyle → Task 15
- §3 Admin login page → Task 17
- §3 Admin new-room (session auth) → Task 18
- §3 Admin settings (password change) → Task 19
- §4 Schema + migration + seed → Tasks 2 (model) + 3 (migration)
- §4 Auth deps rewrite → Task 4
- §4 SessionMiddleware → Task 5
- §4 Existing test fixture update → Task 6
- §5 Avatar system → Tasks 7 (logic + fallback endpoint) + 10 (SVG assets) + 12 (macro)
- §6 Markdown + LaTeX → Tasks 9 (render module) + 10 (KaTeX bundle) + 12 (script include) + 14, 16 (template usage)
- §7 Acceptance criteria → All verified in Task 21 e2e smoke

**Placeholder scan**: no "TBD", "TODO", "implement later" present. Every step contains the actual commands and code.

**Type consistency**: 
- `current_admin` is the consistent template variable for the logged-in admin object (used in `_nav.html`, `admin_settings.html`)
- `avatar_url` is the template helper (used in `_avatar.html` macro)
- `require_admin_session` is the session dep, `require_admin_basic` (aliased as `require_admin`) is the Basic dep — both consistently named
- `_ctx(request, db, extra)` is the canonical context-builder used by every web route

**Potential gotchas flagged for the executor**:
- Task 12's wrapping of `TemplateResponse` calls must touch *every* response in `web.py` — easy to miss one. After Task 12, also re-check Task 14, 15, 16 use `_ctx`.
- Task 10's font download from Google Fonts URL is hash-stable but the URL may rotate; if the curl 404s, fetch from the Newsreader GitHub repo `https://github.com/productiontype/newsreader/raw/main/fonts/webfonts/Newsreader%5Bopsz,wght%5D.woff2` instead.
- Task 18's exception handler change is small but the `RedirectResponse` import needs to be there before the handler runs.

Plan complete and saved to `docs/superpowers/plans/2026-05-25-ui-redesign-v2.md`.
