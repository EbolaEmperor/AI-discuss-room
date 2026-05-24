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
