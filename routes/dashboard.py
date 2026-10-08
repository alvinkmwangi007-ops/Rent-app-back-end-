from fastapi import Request

from overview import overview
from routes import json_response, require_auth, router


@router.get("/api/overview")
async def get_overview(request: Request):
    require_auth(request, "/api/overview")
    return json_response(200, {"ok": True, **overview()})
