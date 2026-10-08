import os
from datetime import datetime, timedelta, timezone

from database import connection


EAT = timedelta(hours=3)
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def overview():
    now = datetime.now(timezone.utc) + EAT
    year, month = now.year, now.month
    months = []
    for offset in range(11, -1, -1):
        absolute_month = year * 12 + month - 1 - offset
        months.append((absolute_month // 12, absolute_month % 12 + 1))
    first_year, first_month = months[0]
    start = int(
        (datetime(first_year, first_month, 1, tzinfo=timezone.utc) - EAT).timestamp()
        * 1000
    )

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
