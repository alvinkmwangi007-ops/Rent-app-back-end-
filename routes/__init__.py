import asyncio
import json
import re
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import auth
import mpesa
from auth import Fail


router = APIRouter()


def json_response(status, body, headers=None):
    return JSONResponse(body, status_code=status, headers=headers or {})


def token_of(request: Request, path: str):
    match = re.match(r"^Bearer\s+(.+)$", request.headers.get("authorization", ""), re.I)
    if match:
        return match.group(1).strip()
    for item in request.headers.get("cookie", "").split(";"):
        key, separator, value = item.partition("=")
        if separator and key.strip() == "session":
            return unquote(value.strip())
    if path == "/api/events":
        return request.query_params.get("token")
    return None


def require_auth(request: Request, path: str):
    token = token_of(request, path)
    auth.authenticate(token)
    return token


async def read_body(request: Request):
    raw = await request.body()
    if len(raw) > 100_000:
        raise Fail(413, "bad_request", "The request body is too large.")
    if not raw:
        return {}
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise Fail(400, "bad_request", "The request was not valid JSON.") from error
    if not isinstance(body, dict):
        raise Fail(400, "bad_request", "The request was not valid JSON.")
    return body


async def event_stream(token):
    subscriber, queue = mpesa.subscribe()
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=25)
                yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"
            except asyncio.TimeoutError:
                try:
                    auth.authenticate(token)
                except Fail as error:
                    payload = json.dumps(
                        {"reason": error.reason, "message": str(error)},
                        separators=(",", ":"),
                    )
                    yield f"event: auth\ndata: {payload}\n\n"
                    return
                yield ": ping\n\n"
    finally:
        mpesa.unsubscribe(subscriber)


from . import callbacks, dashboard, dev, session, tenants, static  # noqa: E402,F401
