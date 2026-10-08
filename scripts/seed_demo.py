from datetime import datetime, timedelta, timezone
import math

from database import connection, initialize


EAT = timedelta(hours=3)
TENANTS = [
    ("Wanjiru Kamau", "A1", "0712 345 601", 15000),
    ("Otieno Odhiambo", "A2", "0722 345 602", 18000),
    ("Amina Hassan", "B1", "0733 345 603", 20000),
    ("Kiprono Cheruiyot", "B2", "0700 345 604", 16000),
    ("Njeri Mwangi", "C1", "0711 345 605", 25000),
    ("Brian Mutua", "C2", "0721 345 606", 22000),
    ("Faith Achieng", "D1", "0734 345 607", 12000),
    ("Peter Ndungu", "D2", "0701 345 608", 14000),
]
CURRENT_PAYMENTS = [
    [(2, 1)],
    [(3, 1)],
    [(5, 0.5), (18, 0.25)],
    [],
    [(1, 1)],
    [(12, 0.4)],
    [(4, 1)],
    [],
]


def utc_milliseconds(year, month, day, hour=9):
    absolute_month = year * 12 + month - 1
    date = datetime(
        absolute_month // 12,
        absolute_month % 12 + 1,
        day,
        hour,
        tzinfo=timezone.utc,
    )
    return int((date - EAT).timestamp() * 1000)


def main():
    initialize()
    now = datetime.now(timezone.utc) + EAT
    year, month, today = now.year, now.month, now.day
    with connection() as db:
        insert_payment = db.execute
        for index, (name, unit, phone, rent) in enumerate(TENANTS):
            db.execute(
                "INSERT OR IGNORE INTO tenants(name,unit,phone,rent) VALUES(?,?,?,?)",
                (name, unit, phone, rent),
            )
            tenant_id = db.execute("SELECT id FROM tenants WHERE unit=?", (unit,)).fetchone()["id"]
            for k in range(11, 0, -1):
                history_index = 11 - k
                amount = (
                    rent
                    if (index * 7 + history_index * 5) % 9 < 7
                    else math.floor(
                        rent * (0.4 + ((index + history_index) % 4) * 0.15) / 500 + 0.5
                    ) * 500
                )
                insert_payment(
                    "INSERT OR IGNORE INTO payments(tenant_id,amount,mpesa_code,paid_at) VALUES(?,?,?,?)",
                    (tenant_id, amount, f"DEMO{index}H{k}", utc_milliseconds(year, month - k, 5)),
                )
            for payment_index, (day, fraction) in enumerate(CURRENT_PAYMENTS[index]):
                if day <= today:
                    insert_payment(
                        "INSERT OR IGNORE INTO payments(tenant_id,amount,mpesa_code,paid_at) VALUES(?,?,?,?)",
                        (
                            tenant_id,
                            math.floor(rent * fraction + 0.5),
                            f"DEMO{index}C{payment_index}",
                            utc_milliseconds(year, month, day),
                        ),
                    )
        db.commit()
    print("Demo tenants and payments added.")


if __name__ == "__main__":
    main()
