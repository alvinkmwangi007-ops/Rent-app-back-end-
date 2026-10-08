# Rent Desk backend

Python 3.9 or newer is required. Install dependencies with `python -m pip install -r requirements.txt`. Data lives in `app.db` (created on first run); the Python backend uses the same SQLite schema and database file as the previous backend.

1. `python -m scripts.create_manager manager YourPassword123` (the one and only login)
2. `python -m scripts.seed_demo` (optional demo data)
3. `python app.py`, then open http://localhost:3000 (serves the front-end from `public/`)

Settings (environment variables): `PORT`, `PAYBILL` (shown in reminder SMS), `DEV=1` (turns on `/api/dev/simulate-payment` for testing), `DEFAULT_RENT` (monthly rent given to tenants added with only a name and phone), `COOKIE_SECURE=1` (use when behind HTTPS), `ALLOWED_ORIGIN=https://your-frontend-site` (only if the front-end is hosted elsewhere; separate several with commas), `DB_PATH` (optional SQLite path), and `STATIC_DIR` (optional frontend directory).

Sign-in works with the session cookie or `Authorization: Bearer <token>` (login returns the token).

Your parts: `mpesa.py` (`on_confirmation`) and `sms.py` (`send`). Until they are filled in, the app shows "M-Pesa is not set up yet" / "SMS is not set up yet".
