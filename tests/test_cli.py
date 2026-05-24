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
