import re
import time

from fastapi import Request

import sms
from auth import Fail
from config import DEFAULT_RENT
from database import connection
from overview import overview
from routes import json_response, read_body, require_auth, router


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
            raise Fail(
                400,
                "bad_unit",
                "The unit number can only use letters, digits and dashes (no spaces), up to 12 characters.",
            )
        tenant["unit"] = unit
    elif current is None:
        tenant["unit"] = next_unit()

    if has("rent"):
        try:
            rent = float(re.sub(r"[,\s]", "", str(body["rent"])))
        except ValueError:
            rent = 0
        if not rent.is_integer() or rent <= 0:
            raise Fail(
                400,
                "bad_rent",
                "The monthly rent must be a whole number of shillings, more than zero.",
            )
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


@router.post("/api/tenants")
async def create_tenant(request: Request):
    require_auth(request, "/api/tenants")
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


@router.patch("/api/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, request: Request):
    require_auth(request, request.url.path)
    if not re.fullmatch(r"[0-9]+", tenant_id):
        raise Fail(404, "not_found", "That address does not exist on this server.")
    tenant_id = int(tenant_id)
    with connection() as db:
        current = db.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
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


@router.post("/api/tenants/{tenant_id}/remind")
async def remind_tenant(tenant_id: str, request: Request):
    require_auth(request, request.url.path)
    if not re.fullmatch(r"[0-9]+", tenant_id):
        raise Fail(404, "not_found", "That address does not exist on this server.")
    tenant_id = int(tenant_id)
    with connection() as db:
        tenant = db.execute("SELECT * FROM tenants WHERE id=?", (tenant_id,)).fetchone()
    if tenant is None:
        raise Fail(404, "no_tenant", "That tenant no longer exists.")
    data = overview()
    overview_tenant = next(item for item in data["tenants"] if item["id"] == tenant["id"])
    balance = tenant["rent"] - sum(payment["amount"] for payment in overview_tenant["payments"])
    if balance <= 0:
        raise Fail(
            400,
            "nothing_owed",
            f"{tenant['name']} has already paid {data['month']}'s rent in full.",
        )
    message = (
        f"Hi {tenant['name'].split()[0]}, your {data['month']} rent balance is KES {balance:,}. "
        f"Pay via M-Pesa Paybill {data['paybill']}, account {tenant['unit']}."
    )
    try:
        await sms.send(tenant["phone"], message)
    except Fail:
        raise
    except Exception as error:
        raise Fail(
            502,
            "sms_failed",
            "The SMS provider did not accept the message: " + str(error),
        ) from error
    with connection() as db:
        db.execute(
            "INSERT INTO reminders(tenant_id,message,sent_at) VALUES(?,?,?)",
            (tenant["id"], message, int(time.time() * 1000)),
        )
        db.commit()
    return json_response(200, {"ok": True})
