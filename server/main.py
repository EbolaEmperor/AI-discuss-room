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
