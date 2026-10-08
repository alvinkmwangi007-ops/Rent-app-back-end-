import os
from pathlib import Path

from database import ROOT


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
DEV_ENABLED = os.environ.get("DEV") == "1"


def cookie(value, age):
    same_site = "None" if CROSS else "Lax"
    secure = "; Secure" if SECURE else ""
    return f"session={value}; HttpOnly; Path=/; Max-Age={age}; SameSite={same_site}{secure}"
