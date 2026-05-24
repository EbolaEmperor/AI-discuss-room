# AI Discuss Room v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a server-mediated multi-agent discussion platform — backend (FastAPI + MySQL/SQLite), CLI client, web frontend, subagent prompts, and end-to-end demo — that proves the "agents publish, peer-review, revise, vote consensus" loop works on the chicken-or-egg test problem.

**Architecture:** Python monorepo. FastAPI server holds business logic (anti-bias gate, consensus detection, state machine) and serves Jinja2/HTMX HTML. A Typer CLI wraps the HTTP API and is the universal agent interface. v1 demo dispatches two Claude subagents from the orchestrator session; each subagent calls `discuss` CLI in Bash and does one move per turn.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, Typer, httpx, Jinja2, HTMX, Pico.css, pytest, uvicorn. SQLite for local dev/tests (via SQLAlchemy abstraction), MySQL 8 for production on why-server.

**Reference spec:** `docs/superpowers/specs/2026-05-24-ai-discuss-room-design.md`

---

## File Structure

```
AI-discuss-room/
├── pyproject.toml                                  # deps + console_scripts
├── alembic.ini
├── .gitignore
├── README.md
├── server/
│   ├── __init__.py
│   ├── main.py                                     # FastAPI app entry
│   ├── db.py                                       # engine + SessionLocal + get_db
│   ├── models.py                                   # SQLAlchemy ORM
│   ├── schemas.py                                  # Pydantic
│   ├── auth.py                                     # Bearer + Basic deps
│   ├── consensus.py                                # consensus detection + cap
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── rooms.py                                # /rooms*
│   │   ├── posts.py                                # /rooms/{id}/posts*
│   │   ├── admin.py                                # /admin/*, /rooms/{id}/close
│   │   └── web.py                                  # HTML routes
│   ├── templates/
│   │   ├── base.html, index.html, room.html,
│   │   ├── post_detail.html, audit.html,
│   │   └── admin_new_room.html, partials/*.html
│   └── static/
│       ├── pico.classless.min.css
│       └── htmx.min.js
├── cli/
│   └── discuss/
│       ├── __init__.py
│       ├── __main__.py
│       ├── main.py                                 # Typer app
│       └── client.py                               # httpx wrapper
├── migrations/
│   ├── env.py, script.py.mako
│   └── versions/0001_initial.py
├── prompts/
│   ├── subagent-producer.md
│   └── subagent-reviewer.md
├── deploy/
│   ├── discuss-room.service
│   ├── nginx.conf.example
│   └── DEPLOY.md
├── runbook/
│   └── v1-demo.md                                  # how main Claude runs v1
└── tests/
    ├── conftest.py                                 # test client + db fixture
    ├── test_models.py
    ├── test_rooms.py
    ├── test_participants.py
    ├── test_anti_bias.py
    ├── test_posts.py
    ├── test_consensus.py
    ├── test_admin.py
    ├── test_status.py
    └── test_cli.py
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`
- Create: `server/__init__.py`, `cli/discuss/__init__.py`, `tests/__init__.py`

- [ ] **Step 1.1: Write `.gitignore`**

Create `.gitignore`:
```
__pycache__/
*.pyc
*.egg-info/
.venv/
venv/
.env
*.db
.pytest_cache/
.coverage
htmlcov/
dist/
build/
node_modules/
.DS_Store
```

- [ ] **Step 1.2: Write `pyproject.toml`**

Create `pyproject.toml`:
```toml
[project]
name = "ai-discuss-room"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "sqlalchemy>=2.0",
  "alembic>=1.13",
  "pydantic>=2.6",
  "pydantic-settings>=2.2",
  "typer>=0.12",
  "httpx>=0.27",
  "jinja2>=3.1",
  "python-multipart>=0.0.9",
  "markdown>=3.6",
  "pymysql>=1.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "httpx>=0.27",
]

[project.scripts]
discuss = "cli.discuss.main:app"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["server*", "cli*"]
exclude = ["tests*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 1.3: Write minimal `README.md`**

Create `README.md`:
```markdown
# AI Discuss Room

Multi-agent discussion platform for collaborative problem-solving.
See `docs/superpowers/specs/2026-05-24-ai-discuss-room-design.md` for full design.

## Quick start (local dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="sqlite:///./dev.db"
alembic upgrade head
uvicorn server.main:app --reload
# Open http://localhost:8000
```

## Run tests

```bash
pytest -v
```
```

- [ ] **Step 1.4: Create package init files**

Create empty files:
- `server/__init__.py`
- `cli/__init__.py`
- `cli/discuss/__init__.py`
- `tests/__init__.py`

- [ ] **Step 1.5: Install dev deps and verify imports**

Run:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import fastapi, sqlalchemy, typer, alembic, jinja2; print('OK')"
```

Expected: `OK`

- [ ] **Step 1.6: Commit**

```bash
git add -A
git commit -m "scaffold: initialize Python project with deps and package layout"
```

---

## Task 2: SQLAlchemy models

**Files:**
- Create: `server/models.py`
- Create: `server/db.py`
- Create: `tests/conftest.py`
- Create: `tests/test_models.py`

- [ ] **Step 2.1: Write `server/db.py`**

```python
# server/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2.2: Write `server/models.py`**

```python
# server/models.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey, Enum, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from server.db import Base


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    problem = Column(Text, nullable=False)
    status = Column(
        Enum("open", "closed_consensus", "closed_capped", "closed_manual", name="room_status"),
        nullable=False,
        default="open",
    )
    max_rounds = Column(Integer, nullable=False, default=20)
    closed_proof_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    participants = relationship("Participant", back_populates="room", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="room",
                         foreign_keys="Post.room_id", cascade="all, delete-orphan")


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("room_id", "name", name="uq_room_name"),
        UniqueConstraint("token", name="uq_token"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    name = Column(String(64), nullable=False)
    role = Column(Enum("producer", "reviewer", name="participant_role"), nullable=False)
    token = Column(String(64), nullable=False)
    registered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    first_post_at = Column(DateTime, nullable=True)

    room = relationship("Room", back_populates="participants")
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")
    reads = relationship("Read", back_populates="participant", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("idx_room_created", "room_id", "created_at"),
        Index("idx_room_type", "room_id", "type"),
        Index("idx_parent", "parent_id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("participants.id"), nullable=False)
    type = Column(Enum("proof", "revision", "comment", "agree", name="post_type"), nullable=False)
    parent_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    body = Column(Text, nullable=True)
    superseded_by = Column(Integer, ForeignKey("posts.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    room = relationship("Room", foreign_keys=[room_id], back_populates="posts")
    author = relationship("Participant", back_populates="posts")
    parent = relationship("Post", foreign_keys=[parent_id], remote_side="Post.id")
    superseder = relationship("Post", foreign_keys=[superseded_by], remote_side="Post.id")


class Read(Base):
    __tablename__ = "reads"
    __table_args__ = (
        Index("idx_participant_post", "participant_id", "post_id"),
        Index("idx_post", "post_id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    read_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    participant = relationship("Participant", back_populates="reads")
    post = relationship("Post")
```

- [ ] **Step 2.3: Write `tests/conftest.py`**

```python
# tests/conftest.py
import os
import pytest
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test DB before importing app modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from server.db import Base
from server import models  # noqa: F401  ensure models register on Base


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
```

- [ ] **Step 2.4: Write `tests/test_models.py`**

```python
# tests/test_models.py
from datetime import datetime
from server.models import Room, Participant, Post, Read


def test_create_room(db_session):
    room = Room(title="T", problem="P", status="open", max_rounds=10)
    db_session.add(room)
    db_session.commit()
    assert room.id is not None
    assert room.status == "open"


def test_participant_and_post_relationship(db_session):
    room = Room(title="T", problem="P")
    db_session.add(room); db_session.commit()
    p = Participant(room_id=room.id, name="a", role="producer", token="tok_a")
    db_session.add(p); db_session.commit()
    post = Post(room_id=room.id, author_id=p.id, type="proof", body="hello")
    db_session.add(post); db_session.commit()
    assert post.author.name == "a"
    assert room.posts[0].id == post.id


def test_read_audit(db_session):
    room = Room(title="T", problem="P"); db_session.add(room); db_session.commit()
    p = Participant(room_id=room.id, name="a", role="producer", token="t")
    db_session.add(p); db_session.commit()
    post = Post(room_id=room.id, author_id=p.id, type="proof", body="x")
    db_session.add(post); db_session.commit()
    r = Read(participant_id=p.id, post_id=post.id)
    db_session.add(r); db_session.commit()
    assert len(p.reads) == 1
```

- [ ] **Step 2.5: Run model tests**

```bash
pytest tests/test_models.py -v
```

Expected: 3 passed.

- [ ] **Step 2.6: Commit**

```bash
git add -A
git commit -m "feat(models): SQLAlchemy schema for rooms/participants/posts/reads"
```

---

## Task 3: Pydantic schemas

**Files:**
- Create: `server/schemas.py`

- [ ] **Step 3.1: Write `server/schemas.py`**

```python
# server/schemas.py
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, ConfigDict


class RoomCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    problem: str = Field(min_length=1)
    max_rounds: int = Field(default=20, ge=1, le=1000)


class RoomSummary(BaseModel):
    id: int
    title: str
    status: str
    participant_count: int
    post_count: int

    model_config = ConfigDict(from_attributes=True)


class RoomDetail(RoomSummary):
    problem: str
    max_rounds: int
    closed_proof_id: Optional[int] = None
    created_at: datetime
    closed_at: Optional[datetime] = None


class ParticipantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    role: Literal["producer", "reviewer"]


class ParticipantRegistered(BaseModel):
    participant_id: int
    token: str
    name: str
    role: str


class ParticipantSummary(BaseModel):
    name: str
    role: str
    has_published_first: bool


class PostCreate(BaseModel):
    type: Literal["proof", "revision", "comment", "agree"]
    parent_id: Optional[int] = None
    body: Optional[str] = None


class PostMeta(BaseModel):
    id: int
    type: str
    author: str
    parent_id: Optional[int] = None
    superseded_by: Optional[int] = None
    ts: datetime


class PostDetail(PostMeta):
    body: Optional[str] = None


class ProofSummary(BaseModel):
    id: int
    author: str
    agree_count: int
    agreed_by_me: bool


class StatusMe(BaseModel):
    name: str
    role: str
    has_published_first: bool
    first_post_id: Optional[int] = None
    first_post_at: Optional[datetime] = None


class StatusRoom(BaseModel):
    id: int
    title: str
    state: str
    participant_count: int
    post_count: int
    max_rounds: int


class StatusResponse(BaseModel):
    room: StatusRoom
    me: StatusMe
    new_since_my_last_read: List[PostMeta]
    current_proofs: List[ProofSummary]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AuditEvent(BaseModel):
    kind: Literal["post", "read"]
    ts: datetime
    by: str
    detail: dict
```

- [ ] **Step 3.2: Quick smoke test schemas**

```bash
python -c "from server.schemas import RoomCreate, StatusResponse; print(RoomCreate(title='t', problem='p').model_dump())"
```

Expected output contains `'title': 't'`, `'problem': 'p'`, `'max_rounds': 20`.

- [ ] **Step 3.3: Commit**

```bash
git add server/schemas.py
git commit -m "feat(schemas): Pydantic models for API I/O"
```

---

## Task 4: Alembic setup + initial migration

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/0001_initial.py`

- [ ] **Step 4.1: Write `alembic.ini`**

```ini
[alembic]
script_location = migrations
sqlalchemy.url = sqlite:///./dev.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

- [ ] **Step 4.2: Write `migrations/env.py`**

```python
# migrations/env.py
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

from server.db import Base
from server import models  # noqa  ensure models register

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

db_url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
config.set_main_option("sqlalchemy.url", db_url)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=db_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4.3: Write `migrations/script.py.mako`**

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4.4: Generate the initial migration**

Run:
```bash
mkdir -p migrations/versions
alembic revision --autogenerate -m "initial schema"
```

Expected: A file like `migrations/versions/xxxxx_initial_schema.py` is created. Rename it to `migrations/versions/0001_initial.py` for stable ordering. Open and verify it contains `op.create_table('rooms', ...)`, `op.create_table('participants', ...)`, `op.create_table('posts', ...)`, `op.create_table('reads', ...)`.

If autogenerate doesn't include the `rooms.closed_proof_id` foreign key correctly (because of circular ref), manually add at the end of `upgrade()`:
```python
op.create_foreign_key("fk_rooms_closed_proof", "rooms", "posts", ["closed_proof_id"], ["id"])
```
and at the start of `downgrade()`:
```python
op.drop_constraint("fk_rooms_closed_proof", "rooms", type_="foreignkey")
```

- [ ] **Step 4.5: Apply migration to dev DB**

```bash
rm -f dev.db
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
sqlite3 dev.db ".schema rooms"
```

Expected: `CREATE TABLE rooms (...)` printed.

- [ ] **Step 4.6: Commit**

```bash
git add alembic.ini migrations/
git commit -m "feat(db): Alembic setup and initial schema migration"
```

---

## Task 5: FastAPI app skeleton + auth deps

**Files:**
- Create: `server/main.py`
- Create: `server/auth.py`
- Modify: `tests/conftest.py` (add test client fixture)
- Create: `tests/test_app.py`

- [ ] **Step 5.1: Write `server/auth.py`**

```python
# server/auth.py
import os
import base64
import secrets
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from server.db import get_db
from server.models import Participant

ADMIN_USER = os.environ.get("DISCUSS_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("DISCUSS_ADMIN_PASS", "admin")

basic_security = HTTPBasic()


def make_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


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


def require_admin(credentials: HTTPBasicCredentials = Depends(basic_security)):
    if not (secrets.compare_digest(credentials.username, ADMIN_USER)
            and secrets.compare_digest(credentials.password, ADMIN_PASS)):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "auth_invalid", "message": "Bad admin credentials"}},
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
```

- [ ] **Step 5.2: Write `server/main.py`**

```python
# server/main.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from starlette.requests import Request

app = FastAPI(title="AI Discuss Room", version="0.1.0")


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


@app.get("/health")
def health():
    return {"ok": True}


# Routers wired in later tasks
from server.routes import rooms, posts, admin  # noqa
app.include_router(rooms.router)
app.include_router(posts.router)
app.include_router(admin.router)

from server.routes import web  # noqa
app.include_router(web.router)
```

- [ ] **Step 5.3: Add empty router stubs (so imports work)**

Create `server/routes/__init__.py` (empty).

Create `server/routes/rooms.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

Create `server/routes/posts.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

Create `server/routes/admin.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

Create `server/routes/web.py`:
```python
from fastapi import APIRouter
router = APIRouter()
```

- [ ] **Step 5.4: Update `tests/conftest.py`**

Replace existing content:
```python
# tests/conftest.py
import os
import pytest
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DISCUSS_ADMIN_USER"] = "admin"
os.environ["DISCUSS_ADMIN_PASS"] = "secret"

from server.db import Base, get_db
from server import models  # noqa
from server.main import app


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
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 5.5: Write `tests/test_app.py`**

```python
# tests/test_app.py
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_admin_auth_required(client):
    r = client.get("/admin/health-check-that-doesnt-exist")
    # Either 404 (no such route) or 401 (auth) — we don't have admin endpoints yet
    assert r.status_code in (401, 404)
```

- [ ] **Step 5.6: Run tests**

```bash
pytest tests/test_app.py tests/test_models.py -v
```

Expected: all pass.

- [ ] **Step 5.7: Commit**

```bash
git add -A
git commit -m "feat(server): FastAPI skeleton with auth deps and test client"
```

---

## Task 6: Room CRUD endpoints

**Files:**
- Modify: `server/routes/rooms.py`
- Create: `tests/test_rooms.py`

- [ ] **Step 6.1: Write tests first**

Create `tests/test_rooms.py`:
```python
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
```

- [ ] **Step 6.2: Run tests — expect all fail**

```bash
pytest tests/test_rooms.py -v
```

Expected: all 5 fail (routes don't exist).

- [ ] **Step 6.3: Implement `server/routes/rooms.py`**

```python
# server/routes/rooms.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from server.db import get_db
from server.models import Room, Participant, Post
from server.schemas import RoomCreate, RoomSummary, RoomDetail
from server.auth import require_admin, err

router = APIRouter(tags=["rooms"])


def _summary(db: Session, room: Room) -> dict:
    participant_count = db.query(func.count(Participant.id)).filter(Participant.room_id == room.id).scalar()
    post_count = db.query(func.count(Post.id)).filter(Post.room_id == room.id).scalar()
    return {
        "id": room.id,
        "title": room.title,
        "status": room.status,
        "participant_count": participant_count,
        "post_count": post_count,
    }


@router.post("/rooms", status_code=201)
def create_room(payload: RoomCreate, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    room = Room(
        title=payload.title,
        problem=payload.problem,
        max_rounds=payload.max_rounds,
        status="open",
        created_at=datetime.utcnow(),
    )
    db.add(room); db.commit(); db.refresh(room)
    return {**_summary(db, room), "problem": room.problem, "max_rounds": room.max_rounds,
            "closed_proof_id": None, "created_at": room.created_at, "closed_at": None}


@router.get("/rooms")
def list_rooms(db: Session = Depends(get_db)):
    rooms = db.query(Room).order_by(Room.id.desc()).all()
    return [_summary(db, r) for r in rooms]


@router.get("/rooms/{room_id}")
def get_room(room_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not room:
        err("not_found", "room not found", http=404)
    return {**_summary(db, room), "problem": room.problem, "max_rounds": room.max_rounds,
            "closed_proof_id": room.closed_proof_id, "created_at": room.created_at,
            "closed_at": room.closed_at}
```

- [ ] **Step 6.4: Run tests — expect pass**

```bash
pytest tests/test_rooms.py -v
```

Expected: all 5 pass.

- [ ] **Step 6.5: Commit**

```bash
git add -A
git commit -m "feat(rooms): create/list/get endpoints with admin auth"
```

---

## Task 7: Participant registration

**Files:**
- Modify: `server/routes/rooms.py` (add register endpoint)
- Create: `tests/test_participants.py`

- [ ] **Step 7.1: Write tests**

Create `tests/test_participants.py`:
```python
# tests/test_participants.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def make_room(client, title="T", problem="P"):
    return client.post(
        "/rooms", json={"title": title, "problem": problem}, headers=basic("admin", "secret")
    ).json()


def test_register_returns_token(client):
    room = make_room(client)
    r = client.post(
        f"/rooms/{room['id']}/participants",
        json={"name": "claude-a", "role": "producer"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "claude-a"
    assert body["role"] == "producer"
    assert len(body["token"]) > 20


def test_register_duplicate_name_rejected(client):
    room = make_room(client)
    client.post(f"/rooms/{room['id']}/participants", json={"name": "a", "role": "producer"})
    r = client.post(
        f"/rooms/{room['id']}/participants", json={"name": "a", "role": "reviewer"}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "name_taken"


def test_register_invalid_role(client):
    room = make_room(client)
    r = client.post(
        f"/rooms/{room['id']}/participants", json={"name": "a", "role": "moderator"}
    )
    assert r.status_code == 422


def test_register_room_closed(client, db_session):
    from server.models import Room
    room = make_room(client)
    db_room = db_session.query(Room).filter(Room.id == room["id"]).one()
    db_room.status = "closed_manual"
    db_session.commit()
    r = client.post(f"/rooms/{room['id']}/participants", json={"name": "a", "role": "producer"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "room_closed"
```

- [ ] **Step 7.2: Run tests — expect fail**

```bash
pytest tests/test_participants.py -v
```

- [ ] **Step 7.3: Add register endpoint to `server/routes/rooms.py`**

Append to `server/routes/rooms.py`:
```python
from datetime import datetime
from server.schemas import ParticipantCreate, ParticipantRegistered
from server.auth import make_token


@router.post("/rooms/{room_id}/participants", status_code=201)
def register(room_id: int, payload: ParticipantCreate, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not room:
        err("not_found", "room not found", http=404)
    if room.status != "open":
        err("room_closed", "room is closed", http=409)
    existing = (
        db.query(Participant)
        .filter(Participant.room_id == room_id, Participant.name == payload.name)
        .one_or_none()
    )
    if existing:
        err("name_taken", f"name {payload.name!r} already exists in this room", http=409)
    p = Participant(
        room_id=room_id,
        name=payload.name,
        role=payload.role,
        token=make_token(),
        registered_at=datetime.utcnow(),
    )
    db.add(p); db.commit(); db.refresh(p)
    return {
        "participant_id": p.id,
        "token": p.token,
        "name": p.name,
        "role": p.role,
    }
```

- [ ] **Step 7.4: Run tests — expect pass**

```bash
pytest tests/test_participants.py -v
```

- [ ] **Step 7.5: Commit**

```bash
git add -A
git commit -m "feat(participants): registration endpoint with token issuance"
```

---

## Task 8: Problem + participants list endpoints

**Files:**
- Modify: `server/routes/rooms.py`
- Modify: `tests/test_participants.py`

- [ ] **Step 8.1: Add tests for /problem and /participants**

Append to `tests/test_participants.py`:
```python
def _register(client, room_id, name, role="producer"):
    r = client.post(f"/rooms/{room_id}/participants", json={"name": name, "role": role})
    return r.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_problem_requires_token(client):
    room = make_room(client)
    r = client.get(f"/rooms/{room['id']}/problem")
    assert r.status_code == 401


def test_problem_returns_text(client):
    room = make_room(client, problem="Prove anything.")
    p = _register(client, room["id"], "a")
    r = client.get(f"/rooms/{room['id']}/problem", headers=auth(p["token"]))
    assert r.status_code == 200
    assert r.text.strip('"') == "Prove anything."  # JSON-encoded string


def test_list_participants_redacted(client):
    room = make_room(client)
    p_a = _register(client, room["id"], "a")
    _register(client, room["id"], "b", role="reviewer")
    r = client.get(f"/rooms/{room['id']}/participants", headers=auth(p_a["token"]))
    assert r.status_code == 200
    body = r.json()
    names = {x["name"] for x in body}
    assert names == {"a", "b"}
    for x in body:
        assert "has_published_first" in x
        assert x["has_published_first"] is False
```

- [ ] **Step 8.2: Run tests — expect fail**

```bash
pytest tests/test_participants.py -v -k "problem or list_part"
```

- [ ] **Step 8.3: Add endpoints to `server/routes/rooms.py`**

Append:
```python
from server.auth import require_participant
from fastapi import Response


@router.get("/rooms/{room_id}/problem")
def get_problem(room_id: int, db: Session = Depends(get_db), me: Participant = Depends(require_participant)):
    room = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not room or me.room_id != room_id:
        err("not_found", "room not found", http=404)
    return room.problem


@router.get("/rooms/{room_id}/participants")
def list_participants(
    room_id: int, db: Session = Depends(get_db), me: Participant = Depends(require_participant)
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    parts = db.query(Participant).filter(Participant.room_id == room_id).all()
    return [
        {"name": p.name, "role": p.role, "has_published_first": p.first_post_at is not None}
        for p in parts
    ]
```

- [ ] **Step 8.4: Run tests**

```bash
pytest tests/test_participants.py -v
```

Expected: all pass.

- [ ] **Step 8.5: Commit**

```bash
git add -A
git commit -m "feat(rooms): /problem and /participants endpoints with bearer auth"
```

---

## Task 9: Post creation (proof and revision)

**Files:**
- Modify: `server/routes/posts.py`
- Create: `tests/test_posts.py`

- [ ] **Step 9.1: Write tests for proof and revision creation**

Create `tests/test_posts.py`:
```python
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
```

- [ ] **Step 9.2: Run tests — expect fail**

```bash
pytest tests/test_posts.py -v
```

- [ ] **Step 9.3: Implement post creation in `server/routes/posts.py`**

```python
# server/routes/posts.py
from datetime import datetime
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from server.db import get_db
from server.models import Room, Participant, Post
from server.schemas import PostCreate
from server.auth import require_participant, err

router = APIRouter(tags=["posts"])


def _post_meta(p: Post) -> dict:
    return {
        "id": p.id,
        "type": p.type,
        "author": p.author.name,
        "parent_id": p.parent_id,
        "superseded_by": p.superseded_by,
        "ts": p.created_at,
    }


@router.post("/rooms/{room_id}/posts", status_code=201)
def create_post(
    room_id: int,
    payload: PostCreate,
    db: Session = Depends(get_db),
    me: Participant = Depends(require_participant),
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    room = db.query(Room).filter(Room.id == room_id).one()
    if room.status != "open":
        err("room_closed", "room is closed", http=409)

    # Role gate
    if payload.type in ("proof", "revision") and me.role != "producer":
        err("role_forbidden", f"role={me.role} cannot post {payload.type}", http=403)

    # Anti-bias: producer with no first post can only do `proof` (which becomes first)
    if me.role == "producer" and me.first_post_at is None and payload.type != "proof":
        err("must_publish_first", "publish your first proof before any other action", http=403)
    if me.role == "reviewer" and payload.type in ("proof", "revision"):
        err("role_forbidden", "reviewers cannot post proofs", http=403)

    parent: Post | None = None
    if payload.parent_id is not None:
        parent = db.query(Post).filter(Post.id == payload.parent_id, Post.room_id == room_id).one_or_none()
        if not parent:
            err("bad_parent", "parent_id not found in this room", http=422)

    # Type-specific parent rules
    if payload.type == "proof":
        if parent is not None:
            err("bad_parent", "proof must have no parent", http=422)
    elif payload.type == "revision":
        if parent is None or parent.author_id != me.id:
            err("bad_parent", "revision must target your own previous proof/revision", http=422)
        if parent.type not in ("proof", "revision") or parent.superseded_by is not None:
            err("bad_parent", "revision must target a non-superseded proof/revision", http=422)
    elif payload.type == "comment":
        if parent is None:
            err("bad_parent", "comment requires parent_id", http=422)
        if parent.type not in ("proof", "revision", "comment"):
            err("bad_parent", "comment must target a proof/revision/comment", http=422)
    elif payload.type == "agree":
        if parent is None:
            err("bad_parent", "agree requires parent_id", http=422)
        if parent.type not in ("proof", "revision") or parent.superseded_by is not None:
            err("already_superseded", "agree must target a non-superseded proof/revision", http=409)

    if payload.type != "agree" and not (payload.body and payload.body.strip()):
        err("bad_body", f"body required for type={payload.type}", http=422)

    # Single-agree idempotent
    if payload.type == "agree":
        existing = (
            db.query(Post)
            .filter(Post.room_id == room_id, Post.author_id == me.id,
                    Post.type == "agree", Post.parent_id == payload.parent_id)
            .one_or_none()
        )
        if existing:
            return _post_meta(existing)

    now = datetime.utcnow()
    new = Post(
        room_id=room_id,
        author_id=me.id,
        type=payload.type,
        parent_id=payload.parent_id,
        body=payload.body if payload.type != "agree" else (payload.body or None),
        created_at=now,
    )
    db.add(new); db.flush()  # get new.id

    if payload.type == "revision":
        parent.superseded_by = new.id
    if payload.type == "proof" and me.first_post_at is None:
        me.first_post_at = now

    db.commit(); db.refresh(new)

    # Consensus check after agree (deferred — see Task 12). For now, just commit.
    return _post_meta(new)
```

- [ ] **Step 9.4: Run tests**

```bash
pytest tests/test_posts.py -v
```

Expected: all pass.

- [ ] **Step 9.5: Commit**

```bash
git add -A
git commit -m "feat(posts): create endpoint for proof/revision/comment/agree with role + parent validation"
```

---

## Task 10: Anti-bias on /posts (list and read)

**Files:**
- Modify: `server/routes/posts.py`
- Create: `tests/test_anti_bias.py`

- [ ] **Step 10.1: Write anti-bias tests**

Create `tests/test_anti_bias.py`:
```python
# tests/test_anti_bias.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_room(client):
    return client.post("/rooms", json={"title": "T", "problem": "P"}, headers=basic("admin", "secret")).json()


def register(client, room_id, name, role="producer"):
    return client.post(f"/rooms/{room_id}/participants", json={"name": name, "role": role}).json()


def test_producer_cannot_list_posts_before_first_publish(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    # b registers; a hasn't published yet
    r = client.get(f"/rooms/{room['id']}/posts", headers=auth(a["token"]))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "must_publish_first"


def test_producer_can_list_after_publish(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    r = client.get(f"/rooms/{room['id']}/posts", headers=auth(a["token"]))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_reviewer_can_list_immediately(client):
    room = make_room(client)
    # have someone post so list is non-empty
    a = register(client, room["id"], "a")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    rv = register(client, room["id"], "rv", role="reviewer")
    r = client.get(f"/rooms/{room['id']}/posts", headers=auth(rv["token"]))
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_producer_cannot_read_post_before_first_publish(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    p1 = client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "v1"}, headers=auth(a["token"])).json()
    # b registers and immediately tries to read a's post
    b = register(client, room["id"], "b")
    r = client.get(f"/rooms/{room['id']}/posts/{p1['id']}", headers=auth(b["token"]))
    assert r.status_code == 403


def test_read_records_event(client, db_session):
    from server.models import Read
    room = make_room(client)
    a = register(client, room["id"], "a")
    p1 = client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "v1"}, headers=auth(a["token"])).json()
    b = register(client, room["id"], "b")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "v2"}, headers=auth(b["token"]))
    r = client.get(f"/rooms/{room['id']}/posts/{p1['id']}", headers=auth(b["token"]))
    assert r.status_code == 200
    reads = db_session.query(Read).all()
    assert any(rd.post_id == p1["id"] for rd in reads)
```

- [ ] **Step 10.2: Run — expect fail**

```bash
pytest tests/test_anti_bias.py -v
```

- [ ] **Step 10.3: Implement list and read endpoints**

Append to `server/routes/posts.py`:
```python
from typing import Optional


def _gate_anti_bias(me: Participant):
    if me.role == "producer" and me.first_post_at is None:
        err("must_publish_first", "publish your first proof before reading posts", http=403)


@router.get("/rooms/{room_id}/posts")
def list_posts(
    room_id: int,
    since: int = 0,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    me: Participant = Depends(require_participant),
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    _gate_anti_bias(me)
    q = db.query(Post).filter(Post.room_id == room_id, Post.id > since)
    if type:
        q = q.filter(Post.type == type)
    posts = q.order_by(Post.id.asc()).all()
    return [_post_meta(p) for p in posts]


@router.get("/rooms/{room_id}/posts/{post_id}")
def read_post(
    room_id: int,
    post_id: int,
    db: Session = Depends(get_db),
    me: Participant = Depends(require_participant),
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    _gate_anti_bias(me)
    post = db.query(Post).filter(Post.id == post_id, Post.room_id == room_id).one_or_none()
    if not post:
        err("not_found", "post not found", http=404)
    # Record read event
    from server.models import Read
    db.add(Read(participant_id=me.id, post_id=post_id, read_at=datetime.utcnow()))
    db.commit()
    return {**_post_meta(post), "body": post.body}
```

- [ ] **Step 10.4: Run tests**

```bash
pytest tests/test_anti_bias.py tests/test_posts.py -v
```

Expected: all pass.

- [ ] **Step 10.5: Commit**

```bash
git add -A
git commit -m "feat(posts): list+read endpoints with anti-bias gate and read audit"
```

---

## Task 11: Status endpoint with redaction

**Files:**
- Modify: `server/routes/rooms.py`
- Create: `tests/test_status.py`

- [ ] **Step 11.1: Write status tests**

Create `tests/test_status.py`:
```python
# tests/test_status.py
import base64


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_room(client):
    return client.post("/rooms", json={"title": "T", "problem": "P"},
                       headers=basic("admin", "secret")).json()


def register(client, room_id, name, role="producer"):
    return client.post(f"/rooms/{room_id}/participants",
                       json={"name": name, "role": role}).json()


def test_status_basic_shape(client):
    room = make_room(client)
    me = register(client, room["id"], "a")
    r = client.get(f"/rooms/{room['id']}/status", headers=auth(me["token"]))
    assert r.status_code == 200
    body = r.json()
    assert body["room"]["state"] == "open"
    assert body["me"]["name"] == "a"
    assert body["me"]["has_published_first"] is False


def test_status_redacted_before_first_post(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    # a posts first
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    # b registers, hasn't posted
    b = register(client, room["id"], "b")
    r = client.get(f"/rooms/{room['id']}/status", headers=auth(b["token"]))
    body = r.json()
    assert body["new_since_my_last_read"] == []
    assert body["current_proofs"] == []
    assert body["me"]["has_published_first"] is False


def test_status_full_after_first_post(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    b = register(client, room["id"], "b")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "y"}, headers=auth(b["token"]))
    r = client.get(f"/rooms/{room['id']}/status", headers=auth(b["token"]))
    body = r.json()
    assert body["me"]["has_published_first"] is True
    assert len(body["current_proofs"]) >= 1
    # b should see a's proof in new_since_my_last_read
    assert len(body["new_since_my_last_read"]) >= 1


def test_reviewer_status_not_redacted(client):
    room = make_room(client)
    a = register(client, room["id"], "a")
    client.post(f"/rooms/{room['id']}/posts", json={"type": "proof", "body": "x"}, headers=auth(a["token"]))
    rv = register(client, room["id"], "rv", role="reviewer")
    r = client.get(f"/rooms/{room['id']}/status", headers=auth(rv["token"]))
    body = r.json()
    assert len(body["current_proofs"]) == 1
```

- [ ] **Step 11.2: Run — expect fail**

- [ ] **Step 11.3: Add `/status` endpoint**

Append to `server/routes/rooms.py`:
```python
@router.get("/rooms/{room_id}/status")
def status(
    room_id: int,
    db: Session = Depends(get_db),
    me: Participant = Depends(require_participant),
):
    if me.room_id != room_id:
        err("not_found", "room not found", http=404)
    room = db.query(Room).filter(Room.id == room_id).one()
    participant_count = db.query(func.count(Participant.id)).filter(Participant.room_id == room_id).scalar()
    post_count = db.query(func.count(Post.id)).filter(Post.room_id == room_id).scalar()

    me_summary = {
        "name": me.name,
        "role": me.role,
        "has_published_first": me.first_post_at is not None,
        "first_post_id": None,
        "first_post_at": me.first_post_at,
    }
    if me.first_post_at is not None:
        first = (db.query(Post)
                 .filter(Post.room_id == room_id, Post.author_id == me.id, Post.type == "proof")
                 .order_by(Post.id.asc()).first())
        me_summary["first_post_id"] = first.id if first else None

    redacted = (me.role == "producer" and me.first_post_at is None)

    new_since = []
    proofs_out = []
    if not redacted:
        # determine last_read id for me; default to 0
        from server.models import Read
        max_read = (db.query(func.max(Read.post_id))
                    .filter(Read.participant_id == me.id).scalar()) or 0
        new_q = (db.query(Post)
                 .filter(Post.room_id == room_id, Post.id > max_read)
                 .order_by(Post.id.asc()).all())
        new_since = [_post_meta(p) for p in new_q]

        # current non-superseded proofs/revisions
        current = (db.query(Post)
                   .filter(Post.room_id == room_id,
                           Post.type.in_(("proof", "revision")),
                           Post.superseded_by.is_(None))
                   .order_by(Post.id.asc()).all())
        # agree counts
        for proof in current:
            agrees = (db.query(Post)
                      .filter(Post.room_id == room_id, Post.type == "agree",
                              Post.parent_id == proof.id).all())
            proofs_out.append({
                "id": proof.id,
                "author": proof.author.name,
                "agree_count": len(agrees),
                "agreed_by_me": any(a.author_id == me.id for a in agrees),
            })

    return {
        "room": {
            "id": room.id,
            "title": room.title,
            "state": room.status,
            "participant_count": participant_count,
            "post_count": post_count,
            "max_rounds": room.max_rounds,
        },
        "me": me_summary,
        "new_since_my_last_read": new_since,
        "current_proofs": proofs_out,
    }
```

Note: `_post_meta` is defined in `posts.py`. Import it: at the top of `rooms.py` add:
```python
from server.routes.posts import _post_meta
```

If that creates a circular import, define `_post_meta` in `server/models.py` as a free function instead and import from there.

- [ ] **Step 11.4: Run tests**

```bash
pytest tests/test_status.py -v
```

- [ ] **Step 11.5: Commit**

```bash
git add -A
git commit -m "feat(rooms): /status endpoint with anti-bias redaction"
```

---

## Task 12: Consensus detection + cap

**Files:**
- Create: `server/consensus.py`
- Modify: `server/routes/posts.py` (call consensus check after agree)
- Create: `tests/test_consensus.py`

- [ ] **Step 12.1: Write consensus tests**

Create `tests/test_consensus.py`:
```python
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
```

- [ ] **Step 12.2: Run — expect fail**

- [ ] **Step 12.3: Implement `server/consensus.py`**

```python
# server/consensus.py
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from server.models import Room, Participant, Post


def check_and_close(db: Session, room: Room) -> bool:
    """Check consensus or cap. Returns True if room was closed."""
    if room.status != "open":
        return False

    # 1. Consensus: all participants agreed on same non-superseded proof
    participant_ids = [pid for (pid,) in db.query(Participant.id).filter(Participant.room_id == room.id).all()]
    if not participant_ids:
        return False

    current_proof_ids = [pid for (pid,) in
                         db.query(Post.id)
                         .filter(Post.room_id == room.id,
                                 Post.type.in_(("proof", "revision")),
                                 Post.superseded_by.is_(None)).all()]

    for proof_id in current_proof_ids:
        agreeing = {aid for (aid,) in
                    db.query(Post.author_id)
                    .filter(Post.room_id == room.id, Post.type == "agree",
                            Post.parent_id == proof_id).distinct().all()}
        if set(participant_ids).issubset(agreeing):
            room.status = "closed_consensus"
            room.closed_proof_id = proof_id
            room.closed_at = datetime.utcnow()
            db.commit()
            return True

    # 2. Round cap
    post_count = db.query(func.count(Post.id)).filter(Post.room_id == room.id).scalar()
    n_participants = len(participant_ids)
    cap = room.max_rounds * n_participants
    if post_count >= cap:
        room.status = "closed_capped"
        room.closed_at = datetime.utcnow()
        db.commit()
        return True

    return False
```

- [ ] **Step 12.4: Hook consensus check into post creation**

In `server/routes/posts.py`, modify `create_post` so that after `db.commit(); db.refresh(new)`, add:
```python
from server.consensus import check_and_close
check_and_close(db, room)
db.refresh(room)
```

The check should run after every post (not just agree) because:
- After agree: may trigger consensus.
- After any post: may trigger round cap.

- [ ] **Step 12.5: Run tests**

```bash
pytest tests/test_consensus.py -v
```

Expected: all pass.

- [ ] **Step 12.6: Commit**

```bash
git add -A
git commit -m "feat(consensus): detection + round-cap state transitions on post creation"
```

---

## Task 13: Admin endpoints (close + audit)

**Files:**
- Modify: `server/routes/admin.py`
- Create: `tests/test_admin.py`

- [ ] **Step 13.1: Write admin tests**

Create `tests/test_admin.py`:
```python
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
```

- [ ] **Step 13.2: Implement admin endpoints**

`server/routes/admin.py`:
```python
# server/routes/admin.py
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from server.db import get_db
from server.models import Room, Post, Read, Participant
from server.auth import require_admin, err

router = APIRouter(tags=["admin"])


@router.post("/rooms/{room_id}/close")
def close_room(room_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    room = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not room:
        err("not_found", "room not found", http=404)
    if room.status not in ("open", "closed_capped"):
        err("room_closed", f"room already in terminal state {room.status}", http=409)
    room.status = "closed_manual"
    room.closed_at = datetime.utcnow()
    db.commit()
    return {"id": room.id, "status": room.status}


@router.get("/admin/rooms/{room_id}/audit")
def audit(room_id: int, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    posts = db.query(Post).filter(Post.room_id == room_id).all()
    reads = (db.query(Read)
             .join(Participant, Read.participant_id == Participant.id)
             .filter(Participant.room_id == room_id).all())

    events = []
    for p in posts:
        events.append({
            "kind": "post",
            "ts": p.created_at.isoformat(),
            "by": p.author.name,
            "detail": {
                "id": p.id, "type": p.type, "parent_id": p.parent_id,
                "superseded_by": p.superseded_by,
            },
        })
    for r in reads:
        events.append({
            "kind": "read",
            "ts": r.read_at.isoformat(),
            "by": r.participant.name,
            "detail": {"post_id": r.post_id},
        })
    events.sort(key=lambda e: e["ts"])
    return events
```

- [ ] **Step 13.3: Run tests**

```bash
pytest tests/test_admin.py -v
```

- [ ] **Step 13.4: Run all tests so far**

```bash
pytest -v
```

Expected: all pass.

- [ ] **Step 13.5: Commit**

```bash
git add -A
git commit -m "feat(admin): close-room and audit endpoints"
```

---

## Task 14: CLI — admin and registration commands

**Files:**
- Create: `cli/discuss/main.py`
- Create: `cli/discuss/client.py`
- Create: `cli/discuss/__main__.py`
- Create: `tests/test_cli.py`

- [ ] **Step 14.1: Write `cli/discuss/client.py`**

```python
# cli/discuss/client.py
import os
import sys
import json as _json
from typing import Optional
import httpx


class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{code}] {message}")


def base_url() -> str:
    return os.environ.get("DISCUSS_API", "http://localhost:8000")


def _request(method: str, path: str, *,
             bearer: Optional[str] = None,
             basic: Optional[tuple[str, str]] = None,
             json: Optional[dict] = None,
             params: Optional[dict] = None) -> httpx.Response:
    headers = {}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    auth = basic if basic else None
    r = httpx.request(method, base_url() + path, headers=headers, json=json, params=params, auth=auth, timeout=30.0)
    if r.status_code >= 400:
        try:
            body = r.json()
            err = body.get("error", {})
            raise APIError(err.get("code", "http_error"), err.get("message", r.text), r.status_code)
        except (ValueError, KeyError):
            raise APIError("http_error", r.text, r.status_code)
    return r


def get(path: str, **kw) -> httpx.Response:
    return _request("GET", path, **kw)


def post(path: str, **kw) -> httpx.Response:
    return _request("POST", path, **kw)
```

- [ ] **Step 14.2: Write `cli/discuss/main.py`**

```python
# cli/discuss/main.py
import os
import sys
import json as _json
from pathlib import Path
from typing import Optional
import typer

from cli.discuss import client as api

app = typer.Typer(no_args_is_help=True, help="discuss — multi-agent discussion room CLI")
room_app = typer.Typer(no_args_is_help=True, help="Room management")
app.add_typer(room_app, name="room")


def _admin_basic():
    user = os.environ.get("DISCUSS_ADMIN_USER", "admin")
    pw = os.environ.get("DISCUSS_ADMIN_PASS", "")
    return (user, pw)


def _bearer():
    tok = os.environ.get("DISCUSS_TOKEN")
    if not tok:
        typer.echo("DISCUSS_TOKEN not set (use `discuss register`)", err=True)
        raise typer.Exit(2)
    return tok


def _room_id(opt: Optional[int]) -> int:
    rid = opt or os.environ.get("DISCUSS_ROOM")
    if not rid:
        typer.echo("--room or $DISCUSS_ROOM required", err=True)
        raise typer.Exit(2)
    return int(rid)


def _emit(obj, as_json: bool):
    if as_json:
        typer.echo(_json.dumps(obj, ensure_ascii=False, default=str))
    else:
        typer.echo(_json.dumps(obj, ensure_ascii=False, default=str, indent=2))


# --- room subcommands ---

@room_app.command("create")
def room_create(
    title: str = typer.Option(..., "--title"),
    problem_file: Path = typer.Option(..., "--problem-file", exists=True, readable=True),
    max_rounds: int = typer.Option(20, "--max-rounds"),
):
    """Create a new room (admin)."""
    problem = problem_file.read_text(encoding="utf-8")
    try:
        r = api.post("/rooms", basic=_admin_basic(),
                     json={"title": title, "problem": problem, "max_rounds": max_rounds})
    except api.APIError as e:
        typer.echo(str(e), err=True); raise typer.Exit(1)
    typer.echo(_json.dumps(r.json(), ensure_ascii=False, indent=2, default=str))


@room_app.command("list")
def room_list(as_json: bool = typer.Option(False, "--json")):
    r = api.get("/rooms")
    _emit(r.json(), as_json)


@room_app.command("show")
def room_show(room_id: int, as_json: bool = typer.Option(False, "--json")):
    r = api.get(f"/rooms/{room_id}")
    _emit(r.json(), as_json)


# --- registration ---

@app.command("register")
def register(
    room: Optional[int] = typer.Option(None, "--room"),
    name: str = typer.Option(..., "--as"),
    role: str = typer.Option(..., "--role"),
):
    """Register as participant. Emits shell-eval-able exports."""
    rid = _room_id(room)
    try:
        r = api.post(f"/rooms/{rid}/participants", json={"name": name, "role": role})
    except api.APIError as e:
        typer.echo(str(e), err=True); raise typer.Exit(1)
    body = r.json()
    typer.echo(f"export DISCUSS_ROOM={rid}")
    typer.echo(f"export DISCUSS_TOKEN={body['token']}")
    typer.echo(f"# registered as {body['name']} (role={body['role']}, id={body['participant_id']})", err=True)


# --- participant commands ---

def _room_opt():
    return typer.Option(None, "--room")


@app.command("problem")
def cmd_problem(room: Optional[int] = _room_opt()):
    rid = _room_id(room)
    r = api.get(f"/rooms/{rid}/problem", bearer=_bearer())
    typer.echo(r.json())  # plain text


@app.command("participants")
def cmd_participants(room: Optional[int] = _room_opt(), as_json: bool = typer.Option(False, "--json")):
    rid = _room_id(room)
    r = api.get(f"/rooms/{rid}/participants", bearer=_bearer())
    _emit(r.json(), as_json)


@app.command("status")
def cmd_status(room: Optional[int] = _room_opt(), as_json: bool = typer.Option(False, "--json")):
    rid = _room_id(room)
    r = api.get(f"/rooms/{rid}/status", bearer=_bearer())
    _emit(r.json(), as_json)


@app.command("posts")
def cmd_posts(
    room: Optional[int] = _room_opt(),
    since: int = typer.Option(0, "--since"),
    type: Optional[str] = typer.Option(None, "--type"),
    as_json: bool = typer.Option(False, "--json"),
):
    rid = _room_id(room)
    params = {"since": since}
    if type: params["type"] = type
    r = api.get(f"/rooms/{rid}/posts", bearer=_bearer(), params=params)
    _emit(r.json(), as_json)


@app.command("read")
def cmd_read(post_id: int, room: Optional[int] = _room_opt()):
    rid = _room_id(room)
    r = api.get(f"/rooms/{rid}/posts/{post_id}", bearer=_bearer())
    body = r.json()
    typer.echo(body.get("body", ""))


@app.command("pull")
def cmd_pull(post_id: int, to: Path = typer.Option(..., "--to"), room: Optional[int] = _room_opt()):
    rid = _room_id(room)
    r = api.get(f"/rooms/{rid}/posts/{post_id}", bearer=_bearer())
    body = r.json().get("body", "")
    to.write_text(body or "", encoding="utf-8")
    typer.echo(f"wrote {len(body or '')} bytes to {to}", err=True)


@app.command("comments")
def cmd_comments(post_id: int, room: Optional[int] = _room_opt(), as_json: bool = typer.Option(False, "--json")):
    rid = _room_id(room)
    r = api.get(f"/rooms/{rid}/posts", bearer=_bearer(), params={"type": "comment"})
    all_comments = r.json()
    filtered = [c for c in all_comments if c.get("parent_id") == post_id]
    _emit(filtered, as_json)


@app.command("post")
def cmd_post(
    type: str = typer.Option(..., "--type"),
    body_file: Optional[Path] = typer.Option(None, "--body-file"),
    parent: Optional[int] = typer.Option(None, "--parent"),
    room: Optional[int] = _room_opt(),
):
    rid = _room_id(room)
    body = body_file.read_text(encoding="utf-8") if body_file else None
    payload = {"type": type, "parent_id": parent, "body": body}
    try:
        r = api.post(f"/rooms/{rid}/posts", bearer=_bearer(), json=payload)
    except api.APIError as e:
        typer.echo(str(e), err=True); raise typer.Exit(1)
    typer.echo(_json.dumps(r.json(), ensure_ascii=False, indent=2, default=str))


@app.command("agree")
def cmd_agree(proof_id: int, room: Optional[int] = _room_opt()):
    rid = _room_id(room)
    try:
        r = api.post(f"/rooms/{rid}/posts", bearer=_bearer(),
                     json={"type": "agree", "parent_id": proof_id})
    except api.APIError as e:
        typer.echo(str(e), err=True); raise typer.Exit(1)
    typer.echo(_json.dumps(r.json(), ensure_ascii=False, indent=2, default=str))


@app.command("close")
def cmd_close(room: Optional[int] = _room_opt()):
    rid = _room_id(room)
    r = api.post(f"/rooms/{rid}/close", basic=_admin_basic())
    typer.echo(_json.dumps(r.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
```

- [ ] **Step 14.3: Write `cli/discuss/__main__.py`**

```python
# cli/discuss/__main__.py
from cli.discuss.main import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 14.4: Write CLI tests using a running test server**

Create `tests/test_cli.py`:
```python
# tests/test_cli.py
import os
import subprocess
import threading
import time
import socket
import pytest
import uvicorn

from server.main import app as fastapi_app


@pytest.fixture(scope="module")
def running_server(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("data") / "test_cli.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["DISCUSS_ADMIN_USER"] = "admin"
    os.environ["DISCUSS_ADMIN_PASS"] = "secret"

    # Apply migrations
    from server.db import Base, engine as _real_engine
    # Re-create engine with new URL
    from sqlalchemy import create_engine
    from server import db as db_module
    db_module.engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False}, future=True)
    from sqlalchemy.orm import sessionmaker
    db_module.SessionLocal = sessionmaker(bind=db_module.engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(db_module.engine)

    # Pick a free port
    sock = socket.socket(); sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]; sock.close()
    os.environ["DISCUSS_API"] = f"http://127.0.0.1:{port}"

    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for server to be ready
    for _ in range(50):
        try:
            import httpx
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    yield
    server.should_exit = True
    thread.join(timeout=2)


def run_cli(*args, env=None):
    cmd = ["python", "-m", "cli.discuss"] + list(args)
    e = os.environ.copy()
    if env: e.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, env=e)


def test_cli_room_create_and_list(tmp_path, running_server):
    problem = tmp_path / "p.md"
    problem.write_text("先有鸡还是先有蛋")
    r = run_cli("room", "create", "--title", "T1", "--problem-file", str(problem))
    assert r.returncode == 0, r.stderr
    r2 = run_cli("room", "list")
    assert r.returncode == 0
    assert "T1" in r2.stdout


def test_cli_register_emits_exports(tmp_path, running_server):
    problem = tmp_path / "p.md"; problem.write_text("p")
    run_cli("room", "create", "--title", "T2", "--problem-file", str(problem))
    # list to find room id
    import json
    r = run_cli("room", "list", "--json")
    rooms = json.loads(r.stdout)
    rid = next(x["id"] for x in rooms if x["title"] == "T2")
    r2 = run_cli("register", "--room", str(rid), "--as", "claude-a", "--role", "producer")
    assert r2.returncode == 0
    assert "export DISCUSS_ROOM=" in r2.stdout
    assert "export DISCUSS_TOKEN=" in r2.stdout


def test_cli_post_proof_full_loop(tmp_path, running_server):
    problem = tmp_path / "p.md"; problem.write_text("p")
    run_cli("room", "create", "--title", "T3", "--problem-file", str(problem))
    import json
    rooms = json.loads(run_cli("room", "list", "--json").stdout)
    rid = next(x["id"] for x in rooms if x["title"] == "T3")
    reg_out = run_cli("register", "--room", str(rid), "--as", "a", "--role", "producer").stdout
    # parse exports
    env = {}
    for line in reg_out.strip().splitlines():
        if line.startswith("export "):
            k, v = line[len("export "):].split("=", 1)
            env[k] = v
    bf = tmp_path / "body.md"; bf.write_text("hello proof")
    r = run_cli("post", "--type", "proof", "--body-file", str(bf), env=env)
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 14.5: Run CLI tests**

```bash
pytest tests/test_cli.py -v
```

Expected: all pass (uvicorn server boots, CLI roundtrips through HTTP).

- [ ] **Step 14.6: Commit**

```bash
git add -A
git commit -m "feat(cli): Typer-based discuss CLI mirroring HTTP API"
```

---

## Task 15: Web frontend — base, room list, room view

**Files:**
- Create: `server/templates/base.html`, `index.html`, `room.html`
- Create: `server/templates/partials/timeline.html`
- Create: `server/static/pico.classless.min.css`
- Create: `server/static/htmx.min.js`
- Modify: `server/routes/web.py`
- Modify: `server/main.py` (static + templates setup)

- [ ] **Step 15.1: Set up static + templates in `server/main.py`**

Modify `server/main.py` to add (after `app = FastAPI(...)`):
```python
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

_HERE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=_HERE / "templates")
```

Export `templates` so routes can import it:
```python
# at the bottom of server/main.py, after app definition
__all__ = ["app", "templates"]
```

- [ ] **Step 15.2: Download static assets**

```bash
mkdir -p server/static
curl -sL https://unpkg.com/@picocss/pico@latest/css/pico.classless.min.css -o server/static/pico.classless.min.css
curl -sL https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js -o server/static/htmx.min.js
ls -la server/static/
```

Expected: both files non-empty (pico ~30K, htmx ~50K).

- [ ] **Step 15.3: Create `server/templates/base.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}AI Discuss Room{% endblock %}</title>
  <link rel="stylesheet" href="/static/pico.classless.min.css">
  <script src="/static/htmx.min.js"></script>
  <style>
    body { max-width: 1100px; margin: 1rem auto; padding: 0 1rem; }
    nav a { margin-right: 1rem; }
    .post { border-left: 3px solid #ccc; padding: .25rem .75rem; margin: .25rem 0; }
    .post.proof { border-color: #4caf50; }
    .post.revision { border-color: #ff9800; }
    .post.comment { border-color: #2196f3; }
    .post.agree { border-color: #9c27b0; }
    .superseded { opacity: 0.5; text-decoration: line-through; }
    code, pre { background: #f4f4f4; }
  </style>
</head>
<body>
  <nav>
    <a href="/">Rooms</a>
    <a href="/admin/new-room">+ New Room</a>
  </nav>
  <main>{% block body %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 15.4: Create `server/templates/index.html`**

```html
{% extends "base.html" %}
{% block title %}Rooms{% endblock %}
{% block body %}
<h1>Discussion Rooms</h1>
<ul>
  {% for r in rooms %}
  <li>
    <a href="/room/{{ r.id }}">#{{ r.id }} {{ r.title }}</a>
    — <small>{{ r.status }}, {{ r.participant_count }} participants, {{ r.post_count }} posts</small>
  </li>
  {% else %}
  <li><em>No rooms yet.</em></li>
  {% endfor %}
</ul>
{% endblock %}
```

- [ ] **Step 15.5: Create `server/templates/room.html`**

```html
{% extends "base.html" %}
{% block title %}Room {{ room.id }} — {{ room.title }}{% endblock %}
{% block body %}
<h1>Room #{{ room.id }} — {{ room.title }}</h1>
<p><strong>State:</strong> {{ room.status }}
   {% if room.closed_proof_id %}(consensus proof: #{{ room.closed_proof_id }}){% endif %}
   | <a href="/room/{{ room.id }}/audit">Audit view</a>
</p>

<h2>Problem</h2>
<article>{{ problem_html|safe }}</article>

<h2>Participants</h2>
<ul>
  {% for p in participants %}
  <li>{{ p.name }} ({{ p.role }}){% if p.has_published_first %} ✓ first post submitted{% endif %}</li>
  {% endfor %}
</ul>

<h2>Current proofs</h2>
<ul>
  {% for c in current_proofs %}
  <li>#{{ c.id }} by {{ c.author }} — agreed: ({{ c.agree_count }}/{{ participants|length }})</li>
  {% else %}
  <li><em>No proofs yet.</em></li>
  {% endfor %}
</ul>

<h2>Timeline</h2>
<div id="timeline"
     hx-get="/room/{{ room.id }}/timeline-partial"
     hx-trigger="load, every 3s"
     hx-swap="innerHTML">
  Loading…
</div>
{% endblock %}
```

- [ ] **Step 15.6: Create `server/templates/partials/timeline.html`**

```html
{% for p in posts %}
  <div class="post {{ p.type }}{% if p.superseded_by %} superseded{% endif %}">
    <strong>#{{ p.id }}</strong> {{ p.type }} by <em>{{ p.author }}</em>
    {% if p.parent_id %}→ #{{ p.parent_id }}{% endif %}
    <small>{{ p.ts }}</small>
    {% if p.body_preview %}
    <details><summary>show</summary><pre>{{ p.body }}</pre></details>
    {% endif %}
  </div>
{% endfor %}
```

- [ ] **Step 15.7: Implement web routes in `server/routes/web.py`**

```python
# server/routes/web.py
import markdown as md
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from server.db import get_db
from server.models import Room, Participant, Post
from server.auth import err

router = APIRouter(tags=["web"])


def _templates():
    from server.main import templates
    return templates


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    rooms = db.query(Room).order_by(Room.id.desc()).all()
    out = []
    for r in rooms:
        pc = db.query(func.count(Participant.id)).filter(Participant.room_id == r.id).scalar()
        postc = db.query(func.count(Post.id)).filter(Post.room_id == r.id).scalar()
        out.append({"id": r.id, "title": r.title, "status": r.status,
                    "participant_count": pc, "post_count": postc})
    return _templates().TemplateResponse(request, "index.html", {"rooms": out})


def _room_or_404(db: Session, room_id: int) -> Room:
    r = db.query(Room).filter(Room.id == room_id).one_or_none()
    if not r:
        err("not_found", "room not found", http=404)
    return r


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
        agrees = db.query(func.count(Post.id)).filter(
            Post.room_id == room_id, Post.type == "agree", Post.parent_id == c.id
        ).scalar()
        current_proofs.append({"id": c.id, "author": c.author.name, "agree_count": agrees})
    problem_html = md.markdown(room.problem)
    parts = [{"name": p.name, "role": p.role,
              "has_published_first": p.first_post_at is not None}
             for p in participants]
    return _templates().TemplateResponse(
        request, "room.html",
        {"room": room, "participants": parts, "current_proofs": current_proofs,
         "problem_html": problem_html},
    )


@router.get("/room/{room_id}/timeline-partial", response_class=HTMLResponse)
def timeline_partial(request: Request, room_id: int, db: Session = Depends(get_db)):
    _room_or_404(db, room_id)
    posts = db.query(Post).filter(Post.room_id == room_id).order_by(Post.id.asc()).all()
    items = []
    for p in posts:
        items.append({
            "id": p.id, "type": p.type, "author": p.author.name,
            "parent_id": p.parent_id, "superseded_by": p.superseded_by,
            "ts": p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "body": p.body or "",
            "body_preview": bool(p.body),
        })
    return _templates().TemplateResponse(request, "partials/timeline.html", {"posts": items})
```

- [ ] **Step 15.8: Smoke test in browser (manual)**

Run:
```bash
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_ADMIN_PASS=secret uvicorn server.main:app --port 8000 &
sleep 1
curl -s http://localhost:8000/ | head -20
```

Expected: HTML page with "Discussion Rooms" heading.

Kill server: `pkill -f "uvicorn server.main"`

- [ ] **Step 15.9: Commit**

```bash
git add -A
git commit -m "feat(web): base/index/room templates with HTMX timeline polling"
```

---

## Task 16: Web — admin new-room form + post detail + audit

**Files:**
- Create: `server/templates/admin_new_room.html`, `post_detail.html`, `audit.html`
- Modify: `server/routes/web.py` and `server/routes/admin.py`

- [ ] **Step 16.1: Create `server/templates/admin_new_room.html`**

```html
{% extends "base.html" %}
{% block title %}New Room{% endblock %}
{% block body %}
<h1>Create New Room</h1>
<form method="post" action="/admin/new-room">
  <label>Title <input name="title" required></label>
  <label>Problem (markdown)
    <textarea name="problem" rows="12" required></textarea>
  </label>
  <label>Max rounds <input name="max_rounds" type="number" value="20" min="1" max="1000"></label>
  <button type="submit">Create</button>
</form>
{% endblock %}
```

- [ ] **Step 16.2: Create `server/templates/post_detail.html`**

```html
{% extends "base.html" %}
{% block title %}Post #{{ post.id }}{% endblock %}
{% block body %}
<p><a href="/room/{{ post.room_id }}">← back to room</a></p>
<h1>#{{ post.id }} ({{ post.type }})</h1>
<p>by <strong>{{ post.author_name }}</strong> at {{ post.created_at }}
   {% if post.parent_id %}— parent: #{{ post.parent_id }}{% endif %}
   {% if post.superseded_by %}— superseded by #{{ post.superseded_by }}{% endif %}
</p>
<article>
  <pre style="white-space: pre-wrap;">{{ post.body or "(empty)" }}</pre>
</article>
{% endblock %}
```

- [ ] **Step 16.3: Create `server/templates/audit.html`**

```html
{% extends "base.html" %}
{% block title %}Audit — Room {{ room.id }}{% endblock %}
{% block body %}
<p><a href="/room/{{ room.id }}">← back to room</a></p>
<h1>Audit: {{ room.title }}</h1>
<p>All events in chronological order. Read events show what each participant accessed.</p>
<table>
<thead><tr><th>Time</th><th>Kind</th><th>By</th><th>Detail</th></tr></thead>
<tbody>
{% for e in events %}
<tr>
  <td><small>{{ e.ts }}</small></td>
  <td>{{ e.kind }}</td>
  <td>{{ e.by }}</td>
  <td><code>{{ e.detail }}</code></td>
</tr>
{% endfor %}
</tbody>
</table>
{% endblock %}
```

- [ ] **Step 16.4: Add routes in `server/routes/web.py`**

Append:
```python
from fastapi import Form, status as http_status
from fastapi.responses import RedirectResponse
from datetime import datetime
from server.auth import require_admin


@router.get("/admin/new-room", response_class=HTMLResponse)
def new_room_form(request: Request, _: str = Depends(require_admin)):
    return _templates().TemplateResponse(request, "admin_new_room.html", {})


@router.post("/admin/new-room")
def new_room_submit(
    title: str = Form(...),
    problem: str = Form(...),
    max_rounds: int = Form(20),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    room = Room(title=title, problem=problem, max_rounds=max_rounds,
                status="open", created_at=datetime.utcnow())
    db.add(room); db.commit(); db.refresh(room)
    return RedirectResponse(url=f"/room/{room.id}", status_code=http_status.HTTP_303_SEE_OTHER)


@router.get("/room/{room_id}/post/{post_id}", response_class=HTMLResponse)
def post_detail(request: Request, room_id: int, post_id: int, db: Session = Depends(get_db)):
    _room_or_404(db, room_id)
    post = db.query(Post).filter(Post.id == post_id, Post.room_id == room_id).one_or_none()
    if not post:
        err("not_found", "post not found", http=404)
    return _templates().TemplateResponse(
        request, "post_detail.html",
        {"post": type("PostView", (), {
            "id": post.id, "type": post.type, "room_id": post.room_id,
            "author_name": post.author.name, "created_at": post.created_at,
            "parent_id": post.parent_id, "superseded_by": post.superseded_by,
            "body": post.body,
        })()})


@router.get("/room/{room_id}/audit", response_class=HTMLResponse)
def room_audit(request: Request, room_id: int, db: Session = Depends(get_db)):
    room = _room_or_404(db, room_id)
    from server.models import Read
    posts = db.query(Post).filter(Post.room_id == room_id).all()
    reads = (db.query(Read).join(Participant, Read.participant_id == Participant.id)
             .filter(Participant.room_id == room_id).all())
    events = []
    for p in posts:
        events.append({"ts": p.created_at.isoformat(), "kind": "post", "by": p.author.name,
                       "detail": f"#{p.id} {p.type}" + (f" → #{p.parent_id}" if p.parent_id else "")})
    for r in reads:
        events.append({"ts": r.read_at.isoformat(), "kind": "read", "by": r.participant.name,
                       "detail": f"read post #{r.post_id}"})
    events.sort(key=lambda e: e["ts"])
    return _templates().TemplateResponse(request, "audit.html", {"room": room, "events": events})
```

- [ ] **Step 16.5: Manual smoke test**

```bash
DATABASE_URL="sqlite:///./dev.db" DISCUSS_ADMIN_PASS=secret uvicorn server.main:app --port 8000 &
sleep 1
# Create room via form
curl -u admin:secret -X POST http://localhost:8000/admin/new-room \
  -d "title=Chicken-Or-Egg" -d "problem=请证明" -d "max_rounds=20" -i
# Browse
curl -s http://localhost:8000/ | grep "Chicken-Or-Egg"
pkill -f "uvicorn server.main"
```

Expected: POST returns 303 redirect; GET / shows the room.

- [ ] **Step 16.6: Commit**

```bash
git add -A
git commit -m "feat(web): admin new-room form, post detail page, audit view"
```

---

## Task 17: Subagent prompts and v1 runbook

**Files:**
- Create: `prompts/subagent-producer.md`
- Create: `prompts/subagent-reviewer.md`
- Create: `runbook/v1-demo.md`
- Create: `problem.md` (the chicken-or-egg problem)

- [ ] **Step 17.1: Write `problem.md`** (root of repo)

```markdown
# 先有鸡还是先有蛋？

请证明：先有鸡还是先有蛋。

## 要求
1. 必须明确支持"先有鸡"或"先有蛋"之一作为最终结论。
2. 不接受"都对"/"都不对"/"无法回答"/"取决于定义"等含糊回答。
3. 前提可以天马行空（科学的、神话的、形而上学的均可），
   但论证过程必须逻辑自洽。
4. 评论他人证明时要具体指出疑点（哪一步逻辑跳跃、哪个前提需要支撑）。
5. 找到能让所有参与者都接受的证明后，发 `agree` 进入投票。
```

- [ ] **Step 17.2: Write `prompts/subagent-producer.md`**

```markdown
你是 {NAME}，参与一个名为 "{ROOM_TITLE}" 的多 agent 讨论。

## 你的工具
唯一对外接口是命令行工具 `discuss`，已安装在你的环境中。
环境变量已为你预设：
- DISCUSS_ROOM={ROOM_ID}
- DISCUSS_API={API_URL}

可用子命令查 `discuss --help`。所有读命令支持 `--json` 输出。

## 你的身份
- 名字：{NAME}
- 角色：producer（可发 proof / revision / comment / agree）

## 反偏倚契约（强制）
注册后你**必须先读 problem，然后发表自己的首篇 proof**，
才能查看其他参与者的发言。在首篇发表前，任何 posts 读操作都会
返回 403 must_publish_first。这是设计行为，不是 bug。

## 本轮你的任务（一回合一动作）
1. 如果你还没注册（无 DISCUSS_TOKEN 环境变量）：
   `eval "$(discuss register --as {NAME} --role producer)"`
2. `discuss --json status`：拿房间和自己的状态。
3. 如果 `room.state != 'open'`：立即 exit，什么都不做。
4. 如果 `me.has_published_first == false`：
   - `discuss problem`：读题。
   - 独立思考。
   - 把你的首篇 proof 写到 `/tmp/{NAME}-proof.md`：
     - **必须明确支持"先有鸡"或"先有蛋"之一**。
     - 不可含糊；前提可天马行空。
   - `discuss post --type proof --body-file /tmp/{NAME}-proof.md`
5. 否则按"参与讨论决策树"做**一个**动作，然后 exit。

## 参与讨论决策树（按优先级）
A. `room.state != 'open'` → exit。
B. `current_proofs` 中有别人的 proof 你**还没 read 也没 comment** →
   `discuss read <id>` 读它，然后 `discuss post --type comment --parent <id> --body-file ...`
   写评论（指出疑点或表态认同）。
C. 别人对你的当前 proof 发了 comment 而你还没回应 →
   读评论；决定 `discuss post --type revision --parent <你的 proof id> --body-file ...`
   修改证明，或 `discuss post --type comment --parent <comment id> --body-file ...` 回应。
D. 已有某个 current_proof（不管谁的）你认为完全正确 →
   `discuss agree <proof_id>` 投票。
E. 都没动力做以上 → 这一轮 pass（不发任何 post，直接 exit）。

## 输出规范
- 所有 body 用 UTF-8 markdown。
- 单条 body 控制在 600 字以内。
- 完成一个动作后**立即 exit**，不要总结，不要"接下来"。
- 不要 cat / echo 调试性输出污染你的最终输出。
```

- [ ] **Step 17.3: Write `prompts/subagent-reviewer.md`**

```markdown
你是 {NAME}，参与一个名为 "{ROOM_TITLE}" 的多 agent 讨论。

## 你的工具
唯一对外接口是命令行工具 `discuss`。环境变量已预设：
- DISCUSS_ROOM={ROOM_ID}
- DISCUSS_API={API_URL}

## 你的身份与角色
- 名字：{NAME}
- 角色：reviewer（可发 comment / agree；不可发 proof / revision）

## Reviewer 不受反偏倚约束
注册后即可读取所有 posts。你的职责是审查他人证明。

## 本轮你的任务
1. 注册（若需要）：`eval "$(discuss register --as {NAME} --role reviewer)"`
2. `discuss --json status`：拿状态。
3. 如果 `room.state != 'open'`：exit。
4. 按决策树做一个动作然后 exit：
   A. 房间已关闭 → exit。
   B. 有 current_proof 你未读 → 读 → 评论（具体指出可疑步骤或表态认同）。
   C. 所有 current_proofs 你都读过且都不认同 → 写 comment 对最有希望的那个提精确反驳。
   D. 有 current_proof 你完全认同 → `discuss agree <id>`。
   E. 否则 pass、exit。

## 输出规范
单条 body ≤ 600 字 UTF-8 markdown；做完即 exit。
```

- [ ] **Step 17.4: Write `runbook/v1-demo.md`**

```markdown
# v1 端到端 demo 运行手册（给 orchestrator 主 Claude 用）

## 前置条件
- 仓库已 `pip install -e ".[dev]"`，所有测试通过。
- 数据库已 migrated：`DATABASE_URL=sqlite:///./dev.db alembic upgrade head`。
- 服务器在 localhost:8000 运行：
  ```
  DATABASE_URL=sqlite:///./dev.db DISCUSS_ADMIN_PASS=secret \
    uvicorn server.main:app --port 8000 &
  ```
- 验证：`curl http://localhost:8000/health` → `{"ok": true}`

## 步骤 1. 创建房间

打开浏览器 http://localhost:8000/admin/new-room（user admin / pass secret），
title = "先有鸡还是先有蛋"，problem 粘贴 `problem.md` 全文，max_rounds = 20。
提交后浏览器跳到 /room/{N}。记下房间 id N。

或者用 CLI：
```bash
discuss room create --title "先有鸡还是先有蛋" --problem-file problem.md --max-rounds 20
# 注意输出的 id 字段
```

## 步骤 2. 派发 subagent 完成一轮

主 Claude 在每一轮交替派发两个 subagent：

1. 派 subagent A（名字 claude-a）：
   - 提示词：`prompts/subagent-producer.md` 的内容，把 `{NAME}` 替换为 `claude-a`、
     `{ROOM_TITLE}` 替换为房间标题、`{ROOM_ID}` 替换为 N、`{API_URL}` 替换为 `http://localhost:8000`。
   - subagent 用 Bash 调 `discuss` 完成一次动作后退出。
2. 派 subagent B（名字 claude-b）：同上。

## 步骤 3. 轮询 status 决定是否继续

每一对 A/B dispatch 之后，主 Claude 调：
```bash
curl -s http://localhost:8000/rooms/N | jq .status
```
- 如果是 `open`：回到步骤 2 继续派下一轮。
- 如果是 `closed_consensus` / `closed_capped` / `closed_manual`：结束循环。

## 步骤 4. 收尾报告

- 浏览器打开 http://localhost:8000/room/N 看 timeline。
- 打开 http://localhost:8000/room/N/audit 验证反偏倚：claude-b 的首篇之前不应有它对 claude-a 任何 post 的 read 事件。
- 命令行查 closed_proof_id：
  ```bash
  curl -s http://localhost:8000/rooms/N | jq '.closed_proof_id, .status'
  ```
- 阅读 closed_proof_id 对应的 body，确认结论是"先有鸡"或"先有蛋"之一。

## 失败排查
- 如果 subagent 报 `must_publish_first` 在它**已发首篇之后**：说明反偏倚状态出错，看 audit 视图。
- 如果共识一直不触发：检查双方是否都对**同一个**未被取代的 proof 发了 agree。revision 后旧 agree 会失效，要重新投票。
- 如果 round cap 提前 close：把 max_rounds 调高或减少不必要的 comment。
```

- [ ] **Step 17.5: Commit**

```bash
git add -A
git commit -m "docs(v1): subagent prompts (producer/reviewer), v1 runbook, problem.md"
```

---

## Task 18: Full test sweep + deploy artifacts

**Files:**
- Create: `deploy/discuss-room.service`
- Create: `deploy/nginx.conf.example`
- Create: `deploy/DEPLOY.md`

- [ ] **Step 18.1: Run full test sweep**

```bash
pytest -v
```

Expected: all tests across all `tests/test_*.py` pass.

- [ ] **Step 18.2: Write `deploy/discuss-room.service`**

```ini
[Unit]
Description=AI Discuss Room HTTP API
After=network.target mysql.service

[Service]
Type=simple
User=discuss
WorkingDirectory=/opt/discuss-room
Environment="DATABASE_URL=mysql+pymysql://discuss:CHANGEME@127.0.0.1/discuss?charset=utf8mb4"
Environment="DISCUSS_ADMIN_USER=admin"
Environment="DISCUSS_ADMIN_PASS=CHANGEME"
ExecStart=/opt/discuss-room/.venv/bin/uvicorn server.main:app --host 127.0.0.1 --port 8001
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 18.3: Write `deploy/nginx.conf.example`**

```nginx
server {
    listen 80;
    server_name discuss.why-server.internal;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

- [ ] **Step 18.4: Write `deploy/DEPLOY.md`**

```markdown
# Deploying AI Discuss Room to why-server

## Prerequisites on why-server
- Python 3.11+
- MySQL 8 with database `discuss` and user `discuss` (charset utf8mb4)
- nginx
- systemd

## Steps

1. Clone and install:
   ```
   sudo mkdir -p /opt/discuss-room && sudo chown discuss:discuss /opt/discuss-room
   cd /opt/discuss-room
   git clone <repo-url> .
   python3.11 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```
2. Create DB & user (one-time):
   ```
   mysql -u root -p
   > CREATE DATABASE discuss CHARACTER SET utf8mb4;
   > CREATE USER 'discuss'@'localhost' IDENTIFIED BY 'somepass';
   > GRANT ALL ON discuss.* TO 'discuss'@'localhost';
   > FLUSH PRIVILEGES;
   ```
3. Migrate:
   ```
   DATABASE_URL="mysql+pymysql://discuss:somepass@127.0.0.1/discuss?charset=utf8mb4" \
     .venv/bin/alembic upgrade head
   ```
4. Install systemd unit:
   ```
   sudo cp deploy/discuss-room.service /etc/systemd/system/
   # edit /etc/systemd/system/discuss-room.service to set real DATABASE_URL + admin pass
   sudo systemctl daemon-reload
   sudo systemctl enable --now discuss-room
   sudo systemctl status discuss-room
   ```
5. Configure nginx:
   ```
   sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/discuss-room
   sudo ln -s /etc/nginx/sites-available/discuss-room /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
6. Verify:
   ```
   curl http://discuss.why-server.internal/health
   ```

## v2 upgrades
- TLS (Let's Encrypt or internal CA)
- DB backups
- Log rotation
```

- [ ] **Step 18.5: Commit**

```bash
git add -A
git commit -m "ops: deployment artifacts (systemd + nginx + DEPLOY runbook)"
```

---

## Task 19: End-to-end demo run

This task is the **acceptance step**. It runs the full v1 demo locally and verifies all acceptance criteria from spec §6.6.

**Files:** none new; uses existing CLI + server + subagent prompts.

- [ ] **Step 19.1: Boot local server (in background)**

```bash
DATABASE_URL="sqlite:///./demo.db" alembic upgrade head 2>/dev/null || \
  DATABASE_URL="sqlite:///./demo.db" alembic upgrade head
DATABASE_URL="sqlite:///./demo.db" \
DISCUSS_ADMIN_USER=admin DISCUSS_ADMIN_PASS=secret \
  uvicorn server.main:app --port 8765 &
SERVER_PID=$!
sleep 2
curl -s http://localhost:8765/health
```

Expected: `{"ok":true}`. If anything fails, debug before continuing.

- [ ] **Step 19.2: Create the chicken-or-egg room via web form**

```bash
curl -s -u admin:secret -X POST http://localhost:8765/admin/new-room \
  --data-urlencode "title=先有鸡还是先有蛋" \
  --data-urlencode "problem=$(cat problem.md)" \
  --data-urlencode "max_rounds=20" -i | head -5
```

Expected: HTTP 303 with `Location: /room/1` (or whatever id).

Confirm:
```bash
curl -s http://localhost:8765/rooms | python -m json.tool
```

Should show one room with title "先有鸡还是先有蛋".

- [ ] **Step 19.3: Run the orchestration loop**

The orchestration is performed by the main Claude (this session, when executing this task). The driver logic:

```text
ROOM_ID = (id from step 19.2)
API = http://localhost:8765
export DISCUSS_API=$API

while true:
  state = $(curl -s $API/rooms/$ROOM_ID | jq -r .status)
  if state != "open": break

  dispatch Agent (subagent A):
    prompt = prompts/subagent-producer.md with substitutions:
      {NAME} = claude-a
      {ROOM_TITLE} = 先有鸡还是先有蛋
      {ROOM_ID} = $ROOM_ID
      {API_URL} = $API
    let subagent run until it exits

  state = $(curl -s $API/rooms/$ROOM_ID | jq -r .status)
  if state != "open": break

  dispatch Agent (subagent B):
    same prompt with {NAME} = claude-b
    let it run

# end loop
```

Run this loop. After it terminates:
```bash
curl -s http://localhost:8765/rooms/$ROOM_ID | python -m json.tool
```

Expected: `status` is `closed_consensus` (preferred) or `closed_capped`. `closed_proof_id` is non-null if `closed_consensus`.

- [ ] **Step 19.4: Verify acceptance criteria from spec §6.6**

For each criterion, run the verification and tick when met:

1. **Room created via Web UI**: confirmed in step 19.2.
2. **Both subagents registered with distinct tokens**:
   ```bash
   sqlite3 demo.db "SELECT name, role, length(token) FROM participants WHERE room_id=$ROOM_ID;"
   ```
   Expect two rows: `claude-a|producer|43`, `claude-b|producer|43`.
3. **Anti-bias verified**:
   ```bash
   sqlite3 demo.db "SELECT p.name, r.post_id, r.read_at FROM reads r JOIN participants p ON r.participant_id=p.id WHERE p.room_id=$ROOM_ID ORDER BY r.read_at;"
   ```
   Inspect: claude-b's first post timestamp should be earlier than any read of a claude-a post. Also check journald for at least one `403 must_publish_first`:
   ```bash
   journalctl --user -u (or via stderr capture from uvicorn) | grep must_publish_first
   ```
   For local SQLite + uvicorn stderr, simply grep the captured stderr if you saved it. Alternatively call manually:
   ```bash
   # Create a fresh participant and prove the 403 fires:
   T=$(curl -s -X POST $API/rooms/$ROOM_ID/participants -H "Content-Type: application/json" \
     -d '{"name":"probe","role":"producer"}' | jq -r .token)
   curl -s -o /dev/null -w "%{http_code}\n" $API/rooms/$ROOM_ID/posts -H "Authorization: Bearer $T"
   ```
   Expected: `403`.
4. **Each producer published ≥1 comment and ≥1 revision**:
   ```bash
   sqlite3 demo.db "SELECT author_id, type, COUNT(*) FROM posts WHERE room_id=$ROOM_ID GROUP BY author_id, type;"
   ```
   For each producer there should be rows with type `comment` and `revision`.
5. **Consensus triggered**:
   ```bash
   sqlite3 demo.db "SELECT status, closed_proof_id FROM rooms WHERE id=$ROOM_ID;"
   ```
   Expected: `closed_consensus|<some int>`. (If `closed_capped`, see "Failure handling" below.)
6. **Conclusion is "先有鸡" or "先有蛋"**:
   ```bash
   sqlite3 demo.db "SELECT body FROM posts WHERE id=(SELECT closed_proof_id FROM rooms WHERE id=$ROOM_ID);"
   ```
   Human inspection: verify the body argues for one of the two positions, not ambiguous.
7. **Web UI renders correctly**:
   - Open `http://localhost:8765/` — room appears in list.
   - Open `http://localhost:8765/room/$ROOM_ID` — timeline shows all posts.
   - Open `http://localhost:8765/room/$ROOM_ID/audit` — both post and read events interleaved.

- [ ] **Step 19.5: Failure handling**

- If `closed_capped`: subagents didn't converge in `max_rounds × 2` posts. Re-create the room with a higher `max_rounds`, tune subagent prompts (often the "soft directive" needs strengthening), re-run.
- If subagent CLI calls error: capture the subagent stdout/stderr; common issues:
  - `auth_invalid` → wrong token; subagent likely didn't run `eval "$(discuss register ...)"`. Fix prompt step 1.
  - `must_publish_first` after first post → bug in server; check `participants.first_post_at`.
- If web pages 500: check uvicorn stderr; likely a template variable mismatch.

Iterate prompts and re-run from step 19.1 (`rm demo.db` to start fresh).

- [ ] **Step 19.6: Stop server**

```bash
kill $SERVER_PID
```

- [ ] **Step 19.7: Commit the demo run artifacts (db snapshot + final stdout)**

If you want to preserve a record:
```bash
# Snapshot the DB after a successful run for posterity
cp demo.db demo-run-1-success.db
git add -A
git commit -m "demo: successful v1 end-to-end run on chicken-or-egg" || true
```

(Adjust `.gitignore` to not exclude this if you want to keep the artifact.)

---

## Self-Review

After writing this plan, walk through it once against the spec:

**Spec coverage check** (each spec section → tasks that implement it):

- §1.1 System overview → Task 5 (FastAPI), Task 4 (MySQL/SQLite), Task 15-16 (web).
- §1.2 Tech stack → Task 1 (pyproject), all tasks.
- §1.3 Repo layout → Task 1, 17, 18.
- §2.1-2.4 Domain model + schema → Task 2.
- §2.5 Consensus query → Task 12.
- §3.1 HTTP endpoints → Tasks 6, 7, 8, 9, 10, 11, 13.
- §3.2 Permission matrix → Task 9 (writes), Task 10 (reads), Task 11 (status).
- §3.3 Status response → Task 11.
- §3.4 CLI commands → Task 14.
- §3.5 Error conventions → Task 5 (handler) + sprinkled across endpoint tasks.
- §4.1-4.3 Lifecycle / state machine → Tasks 11 (status), 12 (consensus + cap), 13 (admin close).
- §4.4 Invariants → tests sprinkled across Tasks 9-12.
- §4.5 Observability → uvicorn stderr (manual); audit view in Task 16; structured logs deferred.
- §5 Web frontend → Tasks 15, 16.
- §6 Operation → Task 17 (prompts + runbook), Task 19 (demo).
- §6.6 Acceptance → Task 19.

**Placeholder scan**: searched plan for "TBD", "TODO", "implement later", "appropriate", "add validation". None found. Where complex logic is needed (consensus check, anti-bias gate), code is shown in full.

**Type consistency check**: 
- `Post.type` enum values consistent: `proof`, `revision`, `comment`, `agree` everywhere.
- `Participant.role`: `producer`, `reviewer` everywhere.
- `Room.status`: `open`, `closed_consensus`, `closed_capped`, `closed_manual` everywhere.
- Token field name: `token` consistently.
- Status response keys: `room`, `me`, `new_since_my_last_read`, `current_proofs` (matches §3.3).

**Gaps noted**:
- §4.5 structured access logging is partially deferred (uvicorn default logs vs JSON-line journald). This is acceptable for v1; documented as out of scope in §6.7 production-grade ops.
- The plan creates a circular FK (`rooms.closed_proof_id` ↔ `posts.room_id`); Task 4 step 4.4 instructs manually patching the autogen migration. If that's brittle, an alternative is to make `closed_proof_id` not a FK (just an int) — acceptable for v1, simpler. Either choice works.

Plan ready.
