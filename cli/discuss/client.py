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
    r = httpx.request(method, base_url() + path, headers=headers, json=json, params=params, auth=auth, timeout=30.0, trust_env=False)
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


def delete(path: str, **kw) -> httpx.Response:
    return _request("DELETE", path, **kw)
