from fastapi import Request
from fastapi.responses import FileResponse

from auth import Fail
from config import PUBLIC_DIR
from routes import require_auth, router


@router.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "OPTIONS"])
async def fallback(request: Request, path: str = ""):
    path = "/" + path
    if path.startswith("/api/"):
        require_auth(request, path)
        raise Fail(404, "not_found", "That address does not exist on this server.")
    if request.method != "GET":
        raise Fail(404, "not_found", "That address does not exist on this server.")

    relative = "index.html" if path == "/" else path.lstrip("/")
    target = (PUBLIC_DIR / relative).resolve()
    if not target.is_relative_to(PUBLIC_DIR) or not target.exists() or target.is_dir():
        raise Fail(404, "not_found", "That page does not exist.")
    content_type = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
    }.get(target.suffix, "application/octet-stream")
    return FileResponse(target, media_type=content_type)
