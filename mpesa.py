import asyncio
import json
import math
import time
from datetime import datetime, timezone, timedelta

from auth import Fail
from database import connection


EAT = timedelta(hours=3)
_subscribers = set()


def subscribe():
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    subscriber = (loop, queue)
    _subscribers.add(subscriber)
    return subscriber, queue


def unsubscribe(subscriber):
    _subscribers.discard(subscriber)


def record_payment(account, amount, code, paid_at=None):
    account = str(account or "").strip()
    with connection() as db:
        tenant = db.execute("SELECT id FROM tenants WHERE unit=?", (account,)).fetchone()
        if tenant is None:
            raise Fail(404, "unknown_account", f'No tenant has the account number "{account}".')
        if not math.isfinite(amount) or amount <= 0:
            raise Fail(400, "bad_amount", "The payment amount must be more than zero.")
        paid_at = int(time.time() * 1000) if paid_at is None else paid_at
        rounded_amount = math.floor(amount + 0.5)
        try:
            db.execute(
                "INSERT INTO payments(tenant_id,amount,mpesa_code,paid_at) VALUES(?,?,?,?)",
                (tenant["id"], rounded_amount, code, paid_at),
            )
            db.commit()
        except Exception as error:
            if "UNIQUE" in str(error).upper():
                raise Fail(409, "duplicate_payment", f"Payment {code} was already recorded.") from error
            raise

    local = datetime.fromtimestamp(paid_at / 1000, timezone.utc) + EAT
    event = {
        "id": code,
        "tenantId": tenant["id"],
        "amount": rounded_amount,
        "day": local.day,
        "time": local.strftime("%H:%M"),
    }
    for loop, queue in tuple(_subscribers):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            _subscribers.discard((loop, queue))
    return event


async def on_confirmation(body):
    raise Fail(
        501,
        "mpesa_not_configured",
        "M-Pesa is not set up yet. Add your Daraja code in mpesa.py (on_confirmation).",
    )
