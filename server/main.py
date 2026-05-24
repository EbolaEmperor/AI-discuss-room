# server/main.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from starlette.requests import Request

app = FastAPI(title="AI Discuss Room", version="0.1.0")

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

_HERE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=_HERE / "templates")


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

__all__ = ["app", "templates"]
