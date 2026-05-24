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
