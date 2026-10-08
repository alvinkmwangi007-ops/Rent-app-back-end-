import math
import time

from fastapi import Request

import mpesa
from auth import Fail
from config import DEV_ENABLED
from routes import json_response, read_body, require_auth, router


@router.post("/api/dev/simulate-payment")
async def simulate_payment(request: Request):
    require_auth(request, "/api/dev/simulate-payment")
    if not DEV_ENABLED:
        raise Fail(404, "not_found", "That address does not exist on this server.")
    body = await read_body(request)
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    if not math.isfinite(amount):
        amount = 0
    event = mpesa.record_payment(
        body.get("unit"),
        amount,
        "SIM" + str(int(time.time() * 1000)),
    )
    return json_response(200, {"ok": True, "event": event})
