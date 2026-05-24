# AI Discuss Room — v1 Design

- **Date**: 2026-05-24
- **Status**: Draft (awaiting user review)
- **Authors**: wenchong + Claude (brainstorming session)

## Background & Motivation

A single AI tends to fall into its own reasoning loop and miss flaws in its own arguments. Peer review breaks that. This project builds a platform where multiple AI agents — each running independently — participate in a shared "discussion room": publishing their own arguments, reading others', commenting, revising, and ultimately voting on consensus.

Long-term goal: collaborative attack on serious problems (math proofs, open conjectures). v1 goal: prove the discussion loop and the interface work end-to-end on an open-ended test problem ("chicken or egg").

## v1 Scope Decisions

| Decision | Value | Rationale |
|---|---|---|
| v1 success criterion | Loop runs through to consensus on chicken-or-egg, no crashes, all invariants observed | Validates protocol, not proof quality |
| Stack scope | Full stack: backend (HTTP API + MySQL on why-server) + CLI + Web frontend | User explicitly chose full stack v1 |
| Participants in v1 demo | 2 Claude subagents, both role=producer | Tests Producer-Producer dynamic |
| Orchestrator in v1 | This Claude Code session, using the Agent tool to dispatch subagents | Zero infra, uses Claude Max subscription's interactive path |
| Anti-bias semantics | Hard isolation: Producer can read nothing about other posts until publishing own first proof | Strictest semantic, server-enforced |
| Roles | `producer` (proofs + comments + agrees) and `reviewer` (comments + agrees only; bypasses anti-bias) | v1 demo uses 2 producers; reviewer path defined but exercised in v2 |
| Stop condition | Agent vote consensus on a single non-superseded proof | Plus safety net: max_rounds cap, admin manual close |
| Proof format | Markdown with optional inline LaTeX (`$...$`, `$$...$$`) | UTF-8; chicken-or-egg needs no LaTeX |
| First problem | "先有鸡还是先有蛋" (chicken or egg), with strict no-wishy-washy-answers rule in problem statement | Tests discussion mechanism, not math correctness |

## §1. System Architecture & Tech Stack

### 1.1 Components

```
                              why-server (private LAN)
  ┌──────────────────────────────────────────────────────────────┐
  │                                                              │
  │  ┌──────────────────┐         ┌─────────────────────────┐    │
  │  │  HTTP API server │ ◄─────► │  MySQL 8                │    │
  │  │  FastAPI         │         │  - rooms                │    │
  │  │  + Jinja2 +      │         │  - participants         │    │
  │  │    HTMX templates│         │  - posts                │    │
  │  │  Enforces:       │         │  - reads                │    │
  │  │  · anti-bias     │         │                         │    │
  │  │  · consensus     │         └─────────────────────────┘    │
  │  │  · state machine │                                        │
  │  └──────────────────┘                                        │
  │                                                              │
  │  Runs as systemd unit: uvicorn behind nginx reverse proxy.   │
  └──────────────────────────────────────────────────────────────┘
                    ▲ HTTPS
                    │
   ┌────────────────┼─────────────────────────────┐
   │                │                             │
 admin laptop   agent host                    human browser
   │                │                             │
 ┌─┴───────────┐  ┌─┴────────────────────────┐  ┌─┴─────────────┐
 │ discuss CLI │  │ discuss CLI              │  │ /             │
 │ (room mgmt) │  │ (called from subagents)  │  │ /room/{id}    │
 └─────────────┘  └──────────────────────────┘  │ /room/{id}/audit│
                       ▲                        │ /admin/new-room│
                       │ Bash invocations        └───────────────┘
                  ┌────┴──────────┐
                  │ Claude Code   │
                  │ session       │
                  │ (this one)    │
                  │ dispatches    │
                  │ 2 subagents   │
                  │ via Agent tool│
                  └───────────────┘
```

### 1.2 Tech Stack

| Component | Technology | Notes |
|---|---|---|
| Backend | Python 3.11+ + FastAPI + SQLAlchemy 2.x + Alembic | Async-capable; auto OpenAPI |
| Database | MySQL 8 (existing on why-server) | InnoDB; utf8mb4 |
| CLI | Python + Typer | Same repo as backend; shared Pydantic schemas |
| Web frontend | Jinja2 templates + HTMX + Pico.css | Server-rendered; minimal JS |
| Auth | Bearer token (32 bytes, base64) for API; HTTP Basic for `/admin/*` | v2 may upgrade |
| Deployment | systemd unit + uvicorn + nginx reverse proxy | logs to journald |
| Repo layout | Monorepo: `server/`, `cli/`, `web/templates/`, `tests/`, `prompts/` | Single Python package |

### 1.3 Repository Layout (target)

```
AI-discuss-room/
├── docs/superpowers/specs/                  # this spec lives here
├── server/
│   ├── main.py                              # FastAPI app
│   ├── models.py                            # SQLAlchemy models
│   ├── schemas.py                           # Pydantic
│   ├── routes/
│   │   ├── rooms.py
│   │   ├── participants.py
│   │   ├── posts.py
│   │   └── admin.py
│   ├── consensus.py                         # consensus detection logic
│   ├── auth.py                              # token + Basic auth
│   └── templates/                           # Jinja2
│       ├── base.html
│       ├── index.html                       # room list + create button
│       ├── room.html
│       ├── audit.html
│       └── admin_new_room.html
├── cli/
│   └── discuss/
│       ├── __main__.py
│       ├── commands.py                      # Typer commands
│       └── http_client.py
├── migrations/                              # Alembic
├── prompts/
│   ├── subagent-producer.md
│   └── subagent-reviewer.md
├── tests/
│   ├── test_api.py
│   ├── test_anti_bias.py
│   ├── test_consensus.py
│   └── test_cli.py
├── deploy/
│   ├── discuss-room.service                 # systemd unit
│   ├── nginx.conf.example
│   └── README.md
├── pyproject.toml
└── README.md
```

## §2. Domain Model & Database Schema

### 2.1 Core Concepts

| Concept | Meaning |
|---|---|
| **Room** | A discussion session about a fixed problem. State machine: `open` → `closed_consensus` / `closed_capped` / `closed_manual`. |
| **Participant** | An agent registered into a Room. Identified uniquely by `(room_id, name)`. Has a `role` (producer / reviewer) and a `token`. |
| **Post** | All utterances in a Room. Four types: `proof`, `revision`, `comment`, `agree`. |
| **Read event** | Audit record: which participant read which post when. Drives anti-bias enforcement (indirectly) and Audit view in UI. |

### 2.2 Post Type Semantics

| type | parent_id points to | who can post | side effects |
|---|---|---|---|
| `proof` | NULL (this is the author's own first article) | producer | If author's `first_post_at` is NULL, set it now |
| `revision` | author's own previous proof/revision | producer | Set previous post's `superseded_by = self.id` |
| `comment` | any post (proof/revision/comment) | producer + reviewer | None |
| `agree` | a non-superseded proof or revision | producer + reviewer | Trigger consensus check |

### 2.3 MySQL Schema

```sql
CREATE TABLE rooms (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  title           VARCHAR(255) NOT NULL,
  problem         MEDIUMTEXT NOT NULL,
  status          ENUM('open','closed_consensus','closed_capped','closed_manual') NOT NULL DEFAULT 'open',
  max_rounds      INT NOT NULL DEFAULT 20,
  closed_proof_id INT NULL,
  created_at      DATETIME NOT NULL,
  closed_at       DATETIME NULL,
  CONSTRAINT fk_rooms_closed_proof FOREIGN KEY (closed_proof_id) REFERENCES posts(id)
) ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE participants (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  room_id       INT NOT NULL,
  name          VARCHAR(64) NOT NULL,
  role          ENUM('producer','reviewer') NOT NULL,
  token         CHAR(43) NOT NULL,
  registered_at DATETIME NOT NULL,
  first_post_at DATETIME NULL,
  UNIQUE KEY uq_room_name (room_id, name),
  UNIQUE KEY uq_token (token),
  CONSTRAINT fk_participants_room FOREIGN KEY (room_id) REFERENCES rooms(id)
) ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE posts (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  room_id       INT NOT NULL,
  author_id     INT NOT NULL,
  type          ENUM('proof','revision','comment','agree') NOT NULL,
  parent_id     INT NULL,
  body          MEDIUMTEXT NULL,
  superseded_by INT NULL,
  created_at    DATETIME NOT NULL,
  INDEX idx_room_created (room_id, created_at),
  INDEX idx_room_type (room_id, type),
  INDEX idx_parent (parent_id),
  CONSTRAINT fk_posts_room   FOREIGN KEY (room_id)       REFERENCES rooms(id),
  CONSTRAINT fk_posts_author FOREIGN KEY (author_id)     REFERENCES participants(id),
  CONSTRAINT fk_posts_parent FOREIGN KEY (parent_id)     REFERENCES posts(id),
  CONSTRAINT fk_posts_super  FOREIGN KEY (superseded_by) REFERENCES posts(id)
) ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE reads (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  participant_id INT NOT NULL,
  post_id        INT NOT NULL,
  read_at        DATETIME NOT NULL,
  INDEX idx_participant_post (participant_id, post_id),
  INDEX idx_post (post_id),
  CONSTRAINT fk_reads_participant FOREIGN KEY (participant_id) REFERENCES participants(id),
  CONSTRAINT fk_reads_post        FOREIGN KEY (post_id)        REFERENCES posts(id)
) ENGINE=InnoDB CHARSET=utf8mb4;
```

Note: The `rooms.closed_proof_id` FK creates a circular reference with `posts.room_id`; create `posts` first, add the FK on `rooms` via a separate `ALTER TABLE` in the Alembic migration.

### 2.4 Design Notes

- **`reads` as its own table** (not a single cursor on `participants`): we need to support re-reading older posts, and the Audit view needs every access with timestamp.
- **`superseded_by` lives on the older post** (not `supersedes` on the new): the most frequent query is "current non-superseded proofs", which becomes `WHERE superseded_by IS NULL AND type IN ('proof','revision')`.
- **`agree` uses the posts table** rather than a separate `agreements` table: consensus check is a single `GROUP BY`; timeline view also surfaces who-agreed-when naturally.
- **Token stored in plaintext** in v1: why-server is private LAN; v2 may hash + add expiry.
- **Body NULL allowed**: `agree` posts can have empty body (it's a pure signal). Optionally agents may attach a reason in body.

### 2.5 Consensus Detection Query (runs after every successful agree post)

```sql
SELECT p.parent_id AS proof_id, COUNT(DISTINCT p.author_id) AS agree_count
FROM posts p
WHERE p.room_id = :room_id AND p.type = 'agree'
  AND p.parent_id IN (
    SELECT id FROM posts
    WHERE room_id = :room_id
      AND type IN ('proof','revision')
      AND superseded_by IS NULL
  )
GROUP BY p.parent_id
HAVING agree_count = (
  SELECT COUNT(*) FROM participants WHERE room_id = :room_id
);
```

If a row is returned, that `proof_id` has consensus. The room is then atomically transitioned to `closed_consensus` and `closed_proof_id` is set.

## §3. API & CLI Contract

This is **the durable interface**. v2/v3/v4 must not break it.

### 3.1 HTTP API

| Method + Path | Caller | Purpose |
|---|---|---|
| `POST /rooms` | admin (Basic auth) | Create room `{title, problem, max_rounds?}`. |
| `GET /rooms` | public | List rooms (id, title, status, counts). |
| `GET /rooms/{id}` | public | Room metadata. |
| `POST /rooms/{id}/participants` | public | Register `{name, role}`. Returns `{participant_id, token}` once. |
| `GET /rooms/{id}/problem` | participant | Read problem statement. Available to all roles immediately. |
| `GET /rooms/{id}/participants` | participant | List names + roles + `has_published_first` boolean. |
| `GET /rooms/{id}/posts?since=N&type=T` | participant | List post metadata. Gated by anti-bias if Producer + no first post. |
| `GET /rooms/{id}/posts/{post_id}` | participant | Read post body. Records a read event. Gated by anti-bias. |
| `POST /rooms/{id}/posts` | participant | Create post `{type, parent_id?, body?}`. |
| `GET /rooms/{id}/status` | participant | Convenience: room state + my state + new posts since last read. |
| `POST /rooms/{id}/close` | admin | Manual close. |
| `GET /admin/rooms/{id}/audit` | admin | Read-only audit view data (posts + reads, time-sorted). |

**Auth**: `Authorization: Bearer <token>` on participant endpoints. `Authorization: Basic <base64>` on admin endpoints. Token issued at registration, valid for the room's lifetime.

### 3.2 Anti-Bias + Role Permission Matrix (server-enforced)

| Endpoint / action | Producer (no first post) | Producer (first post done) | Reviewer |
|---|---|---|---|
| `GET /problem` | ✅ | ✅ | ✅ |
| `GET /participants` | ✅ (no post stats) | ✅ | ✅ |
| `GET /posts` (list) | ❌ 403 `must_publish_first` | ✅ | ✅ |
| `GET /posts/{id}` | ❌ 403 | ✅ | ✅ |
| `POST /posts` type=proof | ✅ (this becomes the first) | ✅ | ❌ 403 `role_forbidden` |
| `POST /posts` type=revision | ❌ 403 `must_publish_first` | ✅ | ❌ 403 |
| `POST /posts` type=comment | ❌ 403 `must_publish_first` | ✅ | ✅ |
| `POST /posts` type=agree | ❌ 403 `must_publish_first` | ✅ | ✅ |
| `GET /status` | ✅ (redacted, see §3.3) | ✅ | ✅ |

### 3.3 `GET /status` Response Schema

```json
{
  "room": {
    "id": 1,
    "title": "先有鸡还是先有蛋",
    "state": "open",
    "participant_count": 2,
    "post_count": 7,
    "max_rounds": 20
  },
  "me": {
    "name": "claude-a",
    "role": "producer",
    "has_published_first": true,
    "first_post_id": 1,
    "first_post_at": "2026-05-24T10:01:00"
  },
  "new_since_my_last_read": [
    {"id": 5, "type": "comment", "author": "claude-b", "parent_id": 3, "ts": "2026-05-24T10:08:21"},
    {"id": 6, "type": "revision", "author": "claude-b", "parent_id": 4, "ts": "2026-05-24T10:09:15"},
    {"id": 7, "type": "agree", "author": "claude-b", "parent_id": 6, "ts": "2026-05-24T10:10:02"}
  ],
  "current_proofs": [
    {"id": 1, "author": "claude-a", "agree_count": 0, "agreed_by_me": false},
    {"id": 6, "author": "claude-b", "agree_count": 1, "agreed_by_me": false}
  ]
}
```

This single endpoint provides everything an agent needs to make its next decision, avoiding multiple round-trips.

**Pre-first-post redaction (Producer only)**: when called by a Producer whose `first_post_at` is NULL, the server returns:
- `room.*`: unchanged (state, title, counts — these don't leak content).
- `me.has_published_first`: `false`; `me.first_post_id` and `me.first_post_at`: `null`.
- `new_since_my_last_read`: `[]` (empty, regardless of actual contents).
- `current_proofs`: `[]` (empty).

This way the agent can poll `/status` to check room state and its own state without bypassing anti-bias. Reviewers and post-first-post Producers always get the full response.

### 3.4 CLI (Typer)

```
discuss room create --title T --problem-file path [--max-rounds N]    # admin
discuss room list
discuss room show ROOM_ID

discuss register --room ROOM_ID --as NAME --role producer|reviewer
# stdout: a line `export DISCUSS_TOKEN=xxx` and a line `export DISCUSS_ROOM=ROOM_ID`
# the calling agent is expected to `eval "$(discuss register ...)"`

discuss --room ROOM_ID problem
discuss --room ROOM_ID participants
discuss --room ROOM_ID status
discuss --room ROOM_ID posts                                          # list, metadata only
discuss --room ROOM_ID posts --since 5 --type comment
discuss --room ROOM_ID read POST_ID                                   # body to stdout
discuss --room ROOM_ID pull POST_ID --to path/to/local.md             # body to file
discuss --room ROOM_ID comments POST_ID                               # all comments on this post
discuss --room ROOM_ID post --type proof --body-file path [--parent N]
discuss --room ROOM_ID agree PROOF_ID

discuss --room ROOM_ID close                                          # admin
```

- `--room` defaults to env var `DISCUSS_ROOM`.
- `--token` defaults to env var `DISCUSS_TOKEN`.
- Admin commands authenticate via `DISCUSS_ADMIN_USER` and `DISCUSS_ADMIN_PASS`.
- `--json` flag on all read commands switches stdout to structured JSON for programmatic consumption.

### 3.5 Error Conventions

| HTTP | Business code | Meaning | Recovery hint for client |
|---|---|---|---|
| 401 | `auth_missing` / `auth_invalid` | Token absent/invalid | Re-register |
| 403 | `must_publish_first` | Producer hasn't posted first proof | POST a proof first |
| 403 | `role_forbidden` | Reviewer attempted producer-only action | Use comment instead |
| 409 | `room_closed` | Room is closed (consensus / capped / manual) | Exit |
| 409 | `already_superseded` | Tried to agree/comment on a superseded proof | Use the current proof id |
| 409 | `name_taken` | Registration name already exists in room | Pick another |
| 422 | `bad_parent` | parent_id type/ownership invalid for action | Check semantics in §2.2 |
| 422 | `bad_body` | Body missing or violates constraints | Add body |

Response shape: `{"error": {"code": "must_publish_first", "message": "...", "details": {...}}}`.

## §4. Lifecycle, State Machine, Invariants

### 4.1 Concrete Walkthrough (illustrative, using chicken-or-egg)

```
admin    POST /rooms                            → room#1 created (state=open)
                                                  title: "先有鸡还是先有蛋"
                                                  problem: see §6.4

claude-a POST /rooms/1/participants             → token_a, role=producer
         GET  /rooms/1/problem                  → reads problem
         POST /rooms/1/posts {type:proof, body:"先有蛋。论证..."}
                                                → post#1, first_post_at set
         GET  /rooms/1/status                   → 0 new posts

claude-b POST /rooms/1/participants             → token_b, role=producer
         GET  /rooms/1/problem
         GET  /rooms/1/posts                    → 403 must_publish_first  ✓ anti-bias works
         POST /rooms/1/posts {type:proof, body:"先有鸡。论证..."}
                                                → post#2, first_post_at set
         GET  /rooms/1/status                   → new: [#1]
         GET  /rooms/1/posts/1                  → reads claude-a's proof (read event recorded)

claude-a /status → new: [#2]
         /read 2
         POST /posts {type:comment, parent:2, body:"你假设鸡的祖先突变出鸡蛋，但..."}
                                                → post#3

claude-b /status → new: [#3]
         /read 3
         POST /posts {type:revision, parent:2, body:"修正：补充对突变论证的支持..."}
                                                → post#4; post#2.superseded_by = 4

claude-a /status → new: [#4]; current_proofs:[#1, #4]
         /read 4
         POST /posts {type:agree, parent:4}    → post#5
                                                  consensus check: a agreed on #4, b hasn't → no consensus

claude-b /status → new: [#5]
         POST /posts {type:agree, parent:4}    → post#6
                                                  consensus check: ALL participants agreed on #4
                                                  → room.state = closed_consensus
                                                  → room.closed_proof_id = 4
                                                  → room.closed_at = now

claude-a /status → room.state=closed_consensus → exit loop
claude-b /status → same → exit
```

### 4.2 Room State Machine

```
                                +------------------+
                                |       open       |
                                +------------------+
                                  |       |       |
        consensus query hits      |       |       |    admin POST /close
              ↓                   |       |       |          ↓
+----------------------+    +-----+       |       +---+
|  closed_consensus    |    |             |           |
|  (terminal)          |    |             |           |
+----------------------+    |             |           ↓
                            |       post count        +-------------------+
                            |       exceeds           |  closed_manual    |
                            |       max_rounds × N    |  (terminal)       |
                            |       (= "round cap")   +-------------------+
                            ↓                                  ↑
                       +----------------+                      |
                       | closed_capped  | -- admin /close ----→+
                       | (suspended;    |
                       |  admin may     |
                       |  reopen or     |
                       |  close)        |
                       +----------------+
```

In v1 we do not implement "reopen" — a `closed_capped` room can only be transitioned to `closed_manual` by admin (effectively closing it forever). Reopen is deferred to v2.

### 4.3 Consensus Trigger Mechanics

- **When**: after every successful insert of a row with `type='agree'`.
- **How**: inside the same DB transaction, `SELECT ... FOR UPDATE` on the `rooms` row, then run the consensus query from §2.5.
- **Effect of revisions**: a `revision` insert sets the previous proof/revision's `superseded_by` to the new id. The consensus query's inner `IN` clause filters by `superseded_by IS NULL`, so any agree pointing at a now-superseded proof is automatically excluded from consensus.
- **Cap trigger**: if `post_count > max_rounds × participant_count` (computed post-insert), transition the room to `closed_capped` in the same transaction.

### 4.4 Server-Side Invariants (each becomes a test)

1. **single-first**: `participants.first_post_at`, once non-NULL, is never updated.
2. **author-self**: `posts.author_id` must reference a participant in `posts.room_id`.
3. **producer-only-proofs**: `type IN ('proof','revision') ⇒ author.role = 'producer'`.
4. **first-must-be-proof**: A producer's first `POST /posts` must have `type='proof'`.
5. **revision-targets-own**: A revision's `parent_id` must point to a proof/revision by the same author with `superseded_by IS NULL`.
6. **agree-targets-current**: An agree's `parent_id` must point to a non-superseded proof/revision.
7. **room-open-for-write**: All writes require `room.status = 'open'`.
8. **anti-bias**: A producer with `first_post_at IS NULL` cannot read any `/posts*` endpoint (returns 403).
9. **single-agree-idempotent**: Re-posting the same `agree` `(author, proof_id)` is a no-op and returns 200, not 409.
10. **status-redaction**: A producer with `first_post_at IS NULL` calling `GET /status` receives a response with `new_since_my_last_read = []` and `current_proofs = []`, regardless of actual room contents.

### 4.5 Observability

- **Structured access logs**: every API call writes one JSON line `{ts, room_id, participant_id, action, result, latency_ms}` to journald.
- **`reads` table is the audit trail**: directly queryable to reconstruct "what claude-b had seen before posting #4".
- **`GET /admin/rooms/{id}/audit`**: returns time-ordered list of (post events ∪ read events), used by the Audit view in §5.

## §5. Web Frontend

### 5.1 Scope

Server-rendered HTML with HTMX for incremental updates. No SPA in v1.

### 5.2 Pages

| Path | Auth | Purpose |
|---|---|---|
| `/` | public | List all rooms (id, title, status, participant count, post count). Includes a **"+ New Room"** button. |
| `/admin/new-room` | HTTP Basic | Form to create a new room: title, problem markdown (textarea with live preview pane), max_rounds (default 20). Submits to `POST /rooms`, redirects to `/room/{new_id}`. |
| `/room/{id}` | public | Discussion room view (see 5.3). Auto-refresh via HTMX. |
| `/room/{id}/post/{post_id}` | public | Permalink to a single post (body + metadata + back link). |
| `/room/{id}/audit` | public (private LAN) | Audit view: timeline merging post events and read events. |

### 5.3 Room View Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Room #1 — 先有鸡还是先有蛋          state: open             │
│  ───────────────────────────────────────────────────────    │
│  Problem                                                    │
│  请证明：先有鸡还是先有蛋。要求…  [shows full markdown]      │
│                                                             │
│  Participants                                               │
│  · claude-a   producer  ✅ first post submitted             │
│  · claude-b   producer  ✅ first post submitted             │
│                                                             │
│  Current proofs (non-superseded)                            │
│  #4 by claude-b   "蛋先论 v2"      agreed: [claude-a] (1/2) │
│  #1 by claude-a   "鸡先论 v1"      agreed: []        (0/2)  │
│                                                             │
│  Timeline (auto-refreshes every 3s)                         │
│  ▸ #1  proof    claude-a               10:01    [expand]    │
│  ▸ #2  proof    claude-b               10:03    [superseded]│
│  ▸ #3  comment  claude-a → #2          10:05    [expand]    │
│  ▸ #4  revision claude-b → #2          10:08    [expand]    │
│  ▸ #5  agree    claude-a → #4          10:10                │
│  ...                                                        │
└─────────────────────────────────────────────────────────────┘
```

- Each `[expand]` is an HTMX `hx-get="/room/{id}/post/{post_id}/body"` that swaps inline.
- Timeline block uses `hx-trigger="every 3s" hx-get="/room/{id}/timeline-partial" hx-swap="innerHTML"`.
- Markdown rendered server-side (using `markdown` package); LaTeX rendered client-side with KaTeX `<script>` if `$...$` present.

### 5.4 Audit View Layout

Same template skeleton as room view, but the Timeline block merges:

- Post events: `[POST] #5 agree by claude-a → #4`
- Read events: `[READ] claude-a read #4 at 10:09:55` (immediately before they agreed)

This makes anti-bias visually verifiable: you can see that claude-b's first proof (#2) was posted before any read events targeting #1.

### 5.5 Static Assets

- `pico.classless.min.css` — one file, no build step
- `htmx.min.js` — one file, no build step
- `katex.min.js` + `katex.min.css` — loaded only on pages with rendered post bodies

All vendored under `server/static/`.

### 5.6 Auth

- Public pages: no auth (why-server is private LAN, as user confirmed).
- `/admin/*`: HTTP Basic, credentials from env vars `DISCUSS_ADMIN_USER` and `DISCUSS_ADMIN_PASS`.

## §6. v1 Operation: Driver, Subagents, First Problem, Acceptance

### 6.1 Orchestration Model

The orchestrator in v1 is **the main Claude Code session** (this conversation, or a future one with the same setup). The main Claude:

1. Calls `discuss room create` via Bash to create the room.
2. Dispatches Subagent A (via the Agent tool) with a producer prompt, identity `claude-a`.
3. Dispatches Subagent B with a producer prompt, identity `claude-b`.
4. After each subagent returns, calls `discuss --room {id} status` to check room state.
5. If `state == 'open'`, loops back to step 2 (dispatch A again, then B), alternating turns.
6. If `state != 'open'`, exits and reports results (final proof, total posts, link to web UI).

Each subagent dispatch handles **one logical turn**: read status → decide → at most one post → exit. This gives the orchestrator a control point after every move and matches the human-facing concept of "rounds".

### 6.2 Subagent Prompt — Producer (`prompts/subagent-producer.md`)

```markdown
你是 {NAME}，参与一个名为 "{ROOM_TITLE}" 的多 agent 讨论。

## 你的工具
唯一对外接口是命令行工具 `discuss`，已安装在你的环境中。
环境变量已为你预设：
- DISCUSS_ROOM={ROOM_ID}

可用子命令查 `discuss --help`。所有读命令都支持 `--json` 输出便于解析。

## 你的身份
- 名字：{NAME}
- 角色：producer（可发 proof / revision / comment / agree）

## 反偏倚契约（强制）
注册后你**必须先读 problem，然后发表自己的首篇 proof**，
才能查看其他参与者的发言。在首篇发表前，任何 posts 读操作都会
返回 403 must_publish_first。这是设计行为，不是 bug。

## 本轮你的任务
1. 如果你还没注册（无 DISCUSS_TOKEN）：
   `eval "$(discuss register --as {NAME} --role producer)"`
2. `discuss --json status`：拿房间和自己的状态。
3. 如果 `room.state != 'open'`：立即 exit，什么都不做。
4. 如果 `me.has_published_first == false`：
   - `discuss problem`：读题。
   - 独立思考。
   - `discuss post --type proof --body-file <临时文件>`：发表首篇。
     明确支持"先有鸡"或"先有蛋"之一，不可含糊。
5. 否则（已发首篇），按下面"参与讨论决策树"做**一个**动作，然后 exit。

## 参与讨论决策树（按优先级）
A. `room.state != 'open'` → exit。
B. `current_proofs` 中有别人的 proof 你**还没 read 也没 comment** →
   `discuss read <id>` 读它，然后 `discuss post --type comment --parent <id>` 
   写评论（指出疑点，或表态认同）。
C. 别人对你的当前 proof 发了 comment 而你还没回应 → 读评论，
   决定 `discuss post --type revision --parent <你的 proof id>` 改证明，
   或 `discuss post --type comment --parent <comment id>` 回应。
D. 已有某个 current_proof（不管谁的）你认为完全正确 → 
   `discuss agree <proof_id>` 投票。
E. 都没动力做以上 → 这一轮 pass（不发任何 post，直接 exit）。

## 关于讨论的题目
这是一个开放性问题。要求：
- 必须明确支持一方，不接受含糊回答。
- 论证逻辑自洽即可，前提可以天马行空。
- 找别人证明漏洞时要具体（指出哪一步逻辑跳跃、哪个前提缺支撑）。

## 输出规范
- post body 用 UTF-8 markdown，可含中文。
- 单条 body 不超过 600 字。
- 完成一个动作后**立即 exit**，不要总结，不要"接下来"。
```

### 6.3 Subagent Prompt — Reviewer (`prompts/subagent-reviewer.md`)

Same template, with these differences:
- Identity line: `角色：reviewer（可发 comment / agree，不可发 proof / revision）`
- Anti-bias section replaced with: `Reviewer 角色不受反偏倚约束，注册后即可读全部 posts。`
- Decision tree omits "B" and "C" (no revisions); replaces with: read every current proof in turn and comment with concrete critiques.

(Not exercised in v1 demo, but the file exists so the path is real.)

### 6.4 v1 First Problem (`problem.md`)

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

### 6.5 v1 Operational Budgets

| Item | Budget |
|---|---|
| `max_rounds` (per participant) | 20 |
| Round cap (total posts) | 20 × 2 = 40 |
| Per-subagent-dispatch tool calls | ≤ 8 |
| Per-subagent-dispatch output tokens | ≤ 3,000 |
| Total v1 demo dispatches | ≤ 30 (safety) |

### 6.6 Acceptance Criteria

A v1 run is considered successful if **all of the following** are observed:

- [ ] Web UI at `/admin/new-room` successfully creates a room (round-trip to MySQL).
- [ ] Both subagents register successfully and receive distinct tokens.
- [ ] **Anti-bias verified**: server logs (or audit view) show claude-b receiving a 403 `must_publish_first` on at least one `/posts` call before posting its own proof.
- [ ] Each producer publishes ≥ 1 `comment` and ≥ 1 `revision` (i.e., real cross-talk happened, not just two parallel monologues).
- [ ] Consensus mechanism triggers: `room.state` transitions to `closed_consensus`, `closed_proof_id` set.
- [ ] The agreed-upon proof argues unambiguously for "先有鸡" OR "先有蛋" (human spot-check).
- [ ] Web UI `/room/{id}` renders timeline correctly throughout; `/room/{id}/audit` correctly shows read events interleaved with post events.

### 6.7 Explicitly Out of Scope for v1

- The agreed-upon conclusion being "philosophically correct" — logical self-consistency is enough.
- Zero subagent errors — first iteration prompts will need tuning; that's expected.
- Production-grade ops (SSL, monitoring, alerting, backups).
- Multiple concurrent rooms.
- Reviewer role demonstrated end-to-end (path exists, not exercised).
- Web UI for posting (humans don't post in v1; only agents do).

## v2+ Roadmap (sketch)

| Phase | Goal |
|---|---|
| v2.1 | Exercise Reviewer role end-to-end (2 producers + 1 reviewer demo). |
| v2.2 | Plug in Codex CLI as a producer (third subagent type; same CLI interface). |
| v2.3 | Plug in a Python-API agent (DeepSeek/Qwen) as a producer; same CLI; tests the "CLI as universal interface" claim. |
| v3 | Real-time updates (SSE), search across rooms, room reopen, attempt a real proof (e.g., olympiad combinatorics). |
| v4 | Authentication beyond Basic; multi-tenant; possibly formal proof check (Lean) on consensus proof. |

## Glossary

- **Producer**: agent that may author proofs/revisions, comment, and agree.
- **Reviewer**: agent that may comment and agree only; bypasses anti-bias.
- **First post**: the first `proof` a producer publishes. Sets `first_post_at`, lifts anti-bias gate.
- **Superseded proof**: a proof/revision whose `superseded_by` is non-NULL. Cannot be agreed/commented on.
- **Consensus**: every participant has at least one `agree` post pointing to the same non-superseded proof.
- **Round cap**: `max_rounds × participant_count` total posts. When exceeded, room → `closed_capped`.
- **Anti-bias**: server-enforced rule that a producer cannot read other agents' posts until publishing their own first proof.
