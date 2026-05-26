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


@app.command("unregister")
def unregister(room: Optional[int] = typer.Option(None, "--room")):
    """Unregister yourself from the room.

    After this, the room no longer waits for your agreement to reach consensus,
    and your token cannot post / agree / read anymore. Your previously posted
    content stays in the room's audit trail.
    """
    rid = _room_id(room)
    try:
        r = api.delete(f"/rooms/{rid}/participants/me", bearer=_bearer())
    except api.APIError as e:
        typer.echo(str(e), err=True); raise typer.Exit(1)
    body = r.json()
    typer.echo(_json.dumps(body, ensure_ascii=False, indent=2, default=str))
    typer.echo(f"# unregistered {body['name']} from room {rid}", err=True)


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
