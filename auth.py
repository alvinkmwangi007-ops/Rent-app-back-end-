import hashlib
import hmac
import secrets
import time

from database import connection


SESSION_MS = 12 * 60 * 60 * 1000
MAX_FAILS = 5
LOCK_MS = 15 * 60 * 1000


class Fail(Exception):
    def __init__(self, status, reason, message):
        super().__init__(message)
        self.status = status
        self.reason = reason


def sha(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"{salt.hex()}:{hashed.hex()}"


def check_password(password, stored):
    salt_hex, hash_hex = stored.split(":")
    actual = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=64
    )
    return hmac.compare_digest(actual, bytes.fromhex(hash_hex))


def login(username, password):
    if not username:
        raise Fail(400, "missing_username", "Enter your username.")
    if not password:
        raise Fail(400, "missing_password", "Enter your password.")

    now = int(time.time() * 1000)
    with connection() as db:
        manager = db.execute(
            "SELECT * FROM managers WHERE username=?", (username,)
        ).fetchone()
        if manager is None:
            raise Fail(401, "unknown_user", "No manager account has that username.")
        if manager["locked_until"] > now:
            minutes = (manager["locked_until"] - now + 59999) // 60000
            raise Fail(
                429,
                "locked",
                f"Too many wrong passwords. This account is locked for {minutes} more minute(s).",
            )
        if not check_password(password, manager["password_hash"]):
            failures = manager["failed_attempts"] + 1
            if failures >= MAX_FAILS:
                db.execute(
                    "UPDATE managers SET failed_attempts=0,locked_until=? WHERE id=?",
                    (now + LOCK_MS, manager["id"]),
                )
                db.commit()
                raise Fail(
                    429,
                    "locked",
                    f"Wrong password. The account is now locked for {LOCK_MS // 60000} minutes.",
                )
            db.execute(
                "UPDATE managers SET failed_attempts=? WHERE id=?",
                (failures, manager["id"]),
            )
            db.commit()
            raise Fail(
                401,
                "wrong_password",
                f"The password is incorrect. {MAX_FAILS - failures} attempt(s) left before the account locks.",
            )
        db.execute(
            "UPDATE managers SET failed_attempts=0,locked_until=0 WHERE id=?",
            (manager["id"],),
        )
        token = secrets.token_hex(32)
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?,0)",
            (sha(token), manager["id"], now, now + SESSION_MS),
        )
        db.commit()
        return {"token": token, "maxAge": SESSION_MS // 1000, "manager": manager["username"]}


def authenticate(token):
    if not token:
        raise Fail(401, "no_session", "You are not signed in. Sign in to continue.")
    with connection() as db:
        session = db.execute(
            "SELECT * FROM sessions WHERE token_hash=?", (sha(token),)
        ).fetchone()
    if session is None:
        raise Fail(401, "invalid_session", "Your sign-in is not valid. Sign in again.")
    if session["revoked"]:
        raise Fail(401, "signed_out", "You were signed out. Sign in again.")
    if session["expires_at"] < int(time.time() * 1000):
        raise Fail(401, "session_expired", "Your session expired. Sign in again.")
    return session


def logout(token):
    if token:
        with connection() as db:
            db.execute(
                "UPDATE sessions SET revoked=1 WHERE token_hash=?", (sha(token),)
            )
            db.commit()
