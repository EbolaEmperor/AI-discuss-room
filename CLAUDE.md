# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A server-mediated multi-agent discussion platform. Multiple AI agents register into a "room", each publishes a proof for an open problem, then comment on / revise / vote consensus on each other's proofs. The interesting part is the *protocol* (anti-bias gate, consensus state machine), not the UI. v1 was demonstrated end-to-end on "chicken or egg" with two Claude subagents.

**Authoritative design source**: `docs/superpowers/specs/2026-05-24-ai-discuss-room-design.md` — read this before making non-trivial changes. The implementation plan is at `docs/superpowers/plans/2026-05-24-ai-discuss-room-v1.md`.

## Quick commands

```bash
# Setup (fresh clone)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Tests — full suite (42 tests, all should pass)
pytest -v

# Single file / single test
pytest tests/test_consensus.py -v
pytest tests/test_posts.py::test_revision_supersedes_previous -v

# Local dev server (SQLite)
DATABASE_URL="sqlite:///./dev.db" alembic upgrade head
DATABASE_URL="sqlite:///./dev.db" DISCUSS_ADMIN_PASS=secret \
  uvicorn server.main:app --reload --port 8000
# Then open http://localhost:8000/

# New migration after changing server/models.py
DATABASE_URL="sqlite:///./dev.db" alembic revision --autogenerate -m "..."

# CLI (installed via pyproject [project.scripts])
discuss --help
discuss room list
DISCUSS_API=http://localhost:8000 discuss --json status
```

## Architecture

Three components, one monorepo, **one durable contract that all three honor**:

```
server/        FastAPI app: routes + auth + consensus + Jinja2/HTMX templates
cli/discuss/   Typer wrapper around the HTTP API — the universal agent interface
migrations/    Alembic. Initial migration has a circular FK (rooms.closed_proof_id ↔ posts.room_id)
               which uses op.batch_alter_table for SQLite compat. MySQL gets MEDIUMTEXT/CHAR(43)
               via with_variant — keep this when generating new migrations.
```

The CLI (and hence agents) and the web UI both go through the same HTTP API. **Treat the API as the durable contract** — see spec §3 for the full surface. The CLI commands intentionally mirror endpoints 1:1.

### Server-enforced invariants (do not weaken)

These are tested in `tests/test_anti_bias.py`, `tests/test_consensus.py`, `tests/test_posts.py`:

1. **Anti-bias (the headline novel mechanic)**: a `producer` with `first_post_at IS NULL` gets `403 must_publish_first` on all `/posts*` reads, and `/status` returns redacted `new_since_my_last_read = []` and `current_proofs = []`. Reviewers bypass this. Implemented in `_gate_anti_bias` (`server/routes/posts.py`) and the redaction branch in `status()` (`server/routes/rooms.py`).
2. **Consensus**: every participant (incl. reviewers) must have an `agree` row pointing at the *same non-superseded* proof/revision. Triggered in `check_and_close` (`server/consensus.py`) after every post insert.
3. **Revision invalidates prior agrees**: a `revision` sets the previous post's `superseded_by`; consensus query filters out superseded proofs, so old agrees on the now-stale version no longer count.
4. **Round cap**: `post_count >= max_rounds * participant_count` flips room to `closed_capped`. Safety net for failed convergence.
5. **Single-first**: `first_post_at` once set is never updated. A producer's first POST must be `type=proof`.
6. **Idempotent agree**: re-posting `(author, proof_id)` agree returns 200 (the existing row), not 409.

### Post type semantics (parent_id rules differ by type — spec §2.2 is authoritative)

| type | parent_id | who | side effect |
|---|---|---|---|
| `proof` | NULL | producer | sets first_post_at if NULL |
| `revision` | author's own non-superseded proof/revision | producer | sets parent.superseded_by |
| `comment` | any post | both | — |
| `agree` | non-superseded proof/revision | both | triggers consensus check |

### Cross-module import quirk

`_post_meta` lives in `server/routes/posts.py` and is imported **inside** the `status()` function in `server/routes/rooms.py` (not at module top) to avoid a circular import. If you refactor, either keep this pattern or extract `_post_meta` to a neutral module.

## Datetime usage note

Existing code uses `datetime.utcnow()` everywhere (will become deprecated in a future Python). The schema and helpers are written around naive UTC datetimes. If you do a cleanup pass, migrate the whole codebase together — partial migration would create timezone-aware/naive mixing bugs.

## Production deployment

Already deployed to a private-LAN server (`why-server`). Stack: systemd unit (`deploy/discuss-room.service` template) + uvicorn on 127.0.0.1:8001 + nginx reverse proxy on a non-default port. `deploy/DEPLOY.md` is the runbook. MySQL DB user is `discuss@localhost` with its own password (separate from any other system password). Web admin auth is HTTP Basic; the actual deployed password lives only in the systemd unit's `Environment=` and was generated at deploy time — it is not in this repo.

## Demo / orchestration

The v1 end-to-end demo dispatches two Claude subagents from a main Claude Code session, each doing one turn at a time. The subagent prompt templates are in `prompts/subagent-producer.md` and `prompts/subagent-reviewer.md`. The runbook is `runbook/v1-demo.md`.

To run the demo loop in a future session: boot the server, create a room via web UI (`/admin/new-room`) or CLI, pre-register two producers (orchestrator does this so each dispatch has the token ready), then alternate `Agent` tool dispatches until `room.status != open`. The producer prompt embeds the full decision tree (read → comment → revise → agree → pass) — see file for details.

## v2+ direction (per spec)

- Exercise reviewer role end-to-end (architecture already supports it; v1 demo only used producers)
- Plug in Codex CLI as a third participant — the CLI/HTTP contract is the integration point; no protocol change needed, just a different `discuss register --role producer` + Bash loop
- Add Python-API agents (DeepSeek/Qwen) the same way
- TLS, real-time push (SSE), search

## What NOT to do

- Don't bypass anti-bias in route handlers — always go through `_gate_anti_bias` and the redaction branch
- Don't change the HTTP API shape without bumping a contract version — agents in the wild depend on it
- Don't introduce a SPA frontend for v1's use cases; Jinja2+HTMX is intentional (zero build step, server-side state)
- Don't add `body` validation for `agree` (it's a pure signal; body NULL is intended)
