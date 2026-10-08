import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import auth
import mpesa
import sms
from auth import Fail
from database import ROOT, connection, initialize


PORT = int(os.environ.get("PORT", "3000"))
ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.environ.get("ALLOWED_ORIGIN", "").split(",")
    if origin.strip()
]
CROSS = bool(ORIGINS)
SECURE = CROSS or os.environ.get("COOKIE_SECURE") == "1"
DEFAULT_RENT = int(os.environ.get("DEFAULT_RENT", "") or "0")
PUBLIC_DIR = Path(os.environ.get("STATIC_DIR", str(ROOT / "public"))).resolve()
EAT = timedelta(hours=3)
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

app = FastAPI()
if CROSS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )


@app.on_event("startup")
def startup():
    initialize()


def cookie(value, age):
    same_site = "None" if CROSS else "Lax"
    secure = "; Secure" if SECURE else ""
    return f"session={value}; HttpOnly; Path=/; Max-Age={age}; SameSite={same_site}{secure}"


def token_of(request, path):
    match = re.match(r"^Bearer\s+(.+)$", request.headers.get("authorization", ""), re.I)
    if match:
        return match.group(1).strip()
    for item in request.headers.get("cookie", "").split(";"):
        key, separator, value = item.partition("=")
        if separator and key.strip() == "session":
            from urllib.parse import unquote
            return unquote(value.strip())
    if path == "/api/events":
        return request.query_params.get("token")
    return None


async def read_body(request):
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


def overview():
    now = datetime.now(timezone.utc) + EAT
    year, month = now.year, now.month
    months = []
    for offset in range(11, -1, -1):
        absolute_month = year * 12 + month - 1 - offset
        months.append((absolute_month // 12, absolute_month % 12 + 1))
    first_year, first_month = months[0]
    start = int((datetime(first_year, first_month, 1, tzinfo=timezone.utc) - EAT).timestamp() * 1000)

    with connection() as db:
        tenants = [
            {**dict(row), "history": [0] * 11, "payments": []}
            for row in db.execute("SELECT id,name,unit,phone,rent FROM tenants ORDER BY unit")
        ]
        by_id = {tenant["id"]: tenant for tenant in tenants}
        payments = db.execute(
            "SELECT tenant_id,amount,paid_at FROM payments WHERE paid_at>=?", (start,)
        )
        for payment in payments:
            local = datetime.fromtimestamp(payment["paid_at"] / 1000, timezone.utc) + EAT
            index = next(
                (i for i, item in enumerate(months) if item == (local.year, local.month)),
                -1,
            )
            tenant = by_id.get(payment["tenant_id"])
            if index < 0 or tenant is None:
                continue
            if index == 11:
                tenant["payments"].append({"day": local.day, "amount": payment["amount"]})
            else:
                tenant["history"][index] += payment["amount"]

    next_month = datetime(year, month, 28, tzinfo=timezone.utc) + timedelta(days=4)
    days_in_month = (next_month.replace(day=1) - timedelta(days=1)).day
    return {
        "month": MONTHS[month - 1],
        "daysInMonth": days_in_month,
        "today": now.day,
        "paybill": os.environ.get("PAYBILL", ""),
        "labels": [MONTHS[item[1] - 1][:3] for item in months],
        "tenants": tenants,
    }


def next_unit():
    with connection() as db:
        used = {row["unit"].upper() for row in db.execute("SELECT unit FROM tenants")}
    number = 1
    while f"T{number}" in used:
        number += 1
    return f"T{number}"


def clean_tenant(body, current):
    tenant = dict(current) if current else {}

    def has(key):
        return key in body and body[key] is not None and str(body[key]).strip() != ""

    if current is None or "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            raise Fail(400, "missing_name", "Enter the tenant's name.")
        if len(name) > 80:
            raise Fail(400, "name_too_long", "The name is too long. Use 80 characters or fewer.")
        tenant["name"] = name

    if current is None or "phone" in body:
        raw = re.sub(r"[\s()\-]", "", str(body.get("phone") or ""))
        raw = raw[1:] if raw.startswith("+") else raw
        if not raw:
            raise Fail(400, "missing_phone", "Enter the tenant's phone number.")
        phone = "254" + raw[1:] if raw.startswith("0") else raw
        if not re.fullmatch(r"254[17]\d{8}", phone):
            raise Fail(
                400,
                "bad_phone",
                "That is not a valid Kenyan mobile number. It must start with 07 or 01 (or 2547 / 2541) followed by 8 more digits.",
            )
        tenant["phone"] = phone

    if has("unit"):
        unit = str(body["unit"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9-]{1,12}", unit):
            raise Fail(400, "bad_unit", "The unit number can only use letters, digits and dashes (no spaces), up to 12 characters.")
        tenant["unit"] = unit
    elif current is None:
        tenant["unit"] = next_unit()

    if has("rent"):
        try:
            rent = float(re.sub(r"[,\s]", "", str(body["rent"])))
        except ValueError:
            rent = 0
        if not rent.is_integer() or rent <= 0:
            raise Fail(400, "bad_rent", "The monthly rent must be a whole number of shillings, more than zero.")
        tenant["rent"] = int(rent)
    elif current is None:
        if not DEFAULT_RENT:
            raise Fail(
                400,
                "rent_not_configured",
                "No monthly rent was given and the server has no default rent. Set DEFAULT_RENT on the server, or send a rent with the tenant.",
            )
        tenant["rent"] = DEFAULT_RENT

    with connection() as db:
        duplicate = db.execute(
            "SELECT name FROM tenants WHERE unit=? COLLATE NOCASE AND id<>?",
            (tenant["unit"], tenant.get("id", 0)),
        ).fetchone()
    if duplicate:
        raise Fail(
            409,
            "duplicate_unit",
            f"Unit {tenant['unit']} already belongs to {duplicate['name']}. Each unit needs its own account number.",
        )
    return tenant


def json_response(status, body, headers=None):
    return JSONResponse(body, status_code=status, headers=headers or {})


@app.exception_handler(Fail)
async def fail_handler(request, error):
    headers = {"Set-Cookie": cookie("", 0)} if error.status == 401 else None
    return json_response(
        error.status,
        {"ok": False, "reason": error.reason, "message": str(error)},
        headers,
    )


@app.exception_handler(Exception)
async def unexpected_handler(request, error):
    logging.exception("Unhandled server error", exc_info=error)
    database_error = re.search(r"sqlite|database|disk", str(error), re.I) is not None
    return json_response(
        500,
        {
            "ok": False,
            "reason": "database_error" if database_error else "server_error",
            "message": (
                "The server could not use its database (app.db). Check that the file exists and is not locked or full."
                if database_error
                else "The server hit an unexpected problem. Check the server log for details."
            ),
        },
    )


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


@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "OPTIONS"])
async def route(request: Request, path: str):
    path = "/" + path
    method = request.method

    if path == "/api/login" and method == "POST":
        body = await read_body(request)
        result = auth.login(str(body.get("username") or "").strip(), str(body.get("password") or ""))
        return json_response(
            200,
            {"ok": True, "manager": result["manager"], "token": result["token"]},
            {"Set-Cookie": cookie(result["token"], result["maxAge"])},
        )

    if path == "/api/logout" and method == "POST":
        auth.logout(token_of(request, path))
        return json_response(200, {"ok": True}, {"Set-Cookie": cookie("", 0)})

    if path == "/api/mpesa/confirmation" and method == "POST":
        return json_response(200, await mpesa.on_confirmation(await read_body(request)))

    if path.startswith("/api/"):
        token = token_of(request, path)
        auth.authenticate(token)

        if path == "/api/me":
            return json_response(200, {"ok": True})
        if path == "/api/overview":
            return json_response(200, {"ok": True, **overview()})
        if path == "/api/events":
            return StreamingResponse(
                event_stream(token),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        if path == "/api/tenants" and method == "POST":
            tenant = clean_tenant(await read_body(request), None)
            with connection() as db:
                cursor = db.execute(
                    "INSERT INTO tenants(name,unit,phone,rent) VALUES(?,?,?,?)",
                    (tenant["name"], tenant["unit"], tenant["phone"], tenant["rent"]),
                )
                tenant["id"] = cursor.lastrowid
                db.commit()
            return json_response(
                201,
                {"ok": True, "tenant": {**tenant, "history": [0] * 11, "payments": []}},
            )

        match = re.fullmatch(r"/api/tenants/(\d+)", path)
        if method == "PATCH" and match:
            with connection() as db:
                current = db.execute("SELECT * FROM tenants WHERE id=?", (int(match[1]),)).fetchone()
            body = await read_body(request)
            if current is None:
                raise Fail(404, "no_tenant", "That tenant no longer exists.")
            if not any(key in body for key in ("name", "phone", "unit", "rent")):
                raise Fail(400, "nothing_to_change", "Send at least one of name, phone, unit or rent.")
            tenant = clean_tenant(body, current)
            with connection() as db:
                db.execute(
                    "UPDATE tenants SET name=?,unit=?,phone=?,rent=? WHERE id=?",
                    (tenant["name"], tenant["unit"], tenant["phone"], tenant["rent"], tenant["id"]),
                )
                db.commit()
            return json_response(200, {"ok": True, "tenant": tenant})

        match = re.fullmatch(r"/api/tenants/(\d+)/remind", path)
        if method == "POST" and match:
            with connection() as db:
                tenant = db.execute("SELECT * FROM tenants WHERE id=?", (int(match[1]),)).fetchone()
            if tenant is None:
                raise Fail(404, "no_tenant", "That tenant no longer exists.")
            data = overview()
            overview_tenant = next(item for item in data["tenants"] if item["id"] == tenant["id"])
            balance = tenant["rent"] - sum(payment["amount"] for payment in overview_tenant["payments"])
            if balance <= 0:
                raise Fail(400, "nothing_owed", f"{tenant['name']} has already paid {data['month']}'s rent in full.")
            message = (
                f"Hi {tenant['name'].split()[0]}, your {data['month']} rent balance is KES {balance:,}. "
                f"Pay via M-Pesa Paybill {data['paybill']}, account {tenant['unit']}."
            )
            try:
                await sms.send(tenant["phone"], message)
            except Fail:
                raise
            except Exception as error:
                raise Fail(502, "sms_failed", "The SMS provider did not accept the message: " + str(error)) from error
            with connection() as db:
                db.execute(
                    "INSERT INTO reminders(tenant_id,message,sent_at) VALUES(?,?,?)",
                    (tenant["id"], message, int(time.time() * 1000)),
                )
                db.commit()
            return json_response(200, {"ok": True})

        if path == "/api/dev/simulate-payment" and method == "POST" and os.environ.get("DEV") == "1":
            body = await read_body(request)
            try:
                amount = float(body.get("amount", 0))
            except (TypeError, ValueError):
                amount = 0
            event = mpesa.record_payment(body.get("unit"), amount, "SIM" + str(int(time.time() * 1000)))
            return json_response(200, {"ok": True, "event": event})

        raise Fail(404, "not_found", "That address does not exist on this server.")

    if method != "GET":
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
