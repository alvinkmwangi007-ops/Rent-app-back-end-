from fastapi import Request
from fastapi.responses import StreamingResponse

import auth
from config import cookie
from routes import event_stream, json_response, read_body, require_auth, router, token_of


@router.post("/api/login")
async def login(request: Request):
    body = await read_body(request)
    result = auth.login(
        str(body.get("username") or "").strip(),
        str(body.get("password") or ""),
    )
    return json_response(
        200,
        {"ok": True, "manager": result["manager"], "token": result["token"]},
        {"Set-Cookie": cookie(result["token"], result["maxAge"])},
    )


@router.post("/api/logout")
async def logout(request: Request):
    auth.logout(token_of(request, "/api/logout"))
    return json_response(200, {"ok": True}, {"Set-Cookie": cookie("", 0)})


@router.get("/api/me")
async def me(request: Request):
    require_auth(request, "/api/me")
    return json_response(200, {"ok": True})


@router.get("/api/events")
async def events(request: Request):
    token = require_auth(request, "/api/events")
    return StreamingResponse(
        event_stream(token),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
