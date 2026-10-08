import logging
import re

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from auth import Fail
from config import cookie


def register_error_handlers(app: FastAPI):
    @app.exception_handler(Fail)
    async def fail_handler(request, error):
        headers = {"Set-Cookie": cookie("", 0)} if error.status == 401 else None
        return JSONResponse(
            {"ok": False, "reason": error.reason, "message": str(error)},
            status_code=error.status,
            headers=headers or {},
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(request, error):
        logging.exception("Unhandled server error", exc_info=error)
        database_error = re.search(r"sqlite|database|disk", str(error), re.I) is not None
        return JSONResponse(
            {
                "ok": False,
                "reason": "database_error" if database_error else "server_error",
                "message": (
                    "The server could not use its database (app.db). Check that the file exists and is not locked or full."
                    if database_error
                    else "The server hit an unexpected problem. Check the server log for details."
                ),
            },
            status_code=500,
        )
