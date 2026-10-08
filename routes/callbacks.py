from fastapi import Request

import mpesa
from routes import json_response, read_body, router


@router.post("/api/mpesa/confirmation")
async def mpesa_confirmation(request: Request):
    return json_response(200, await mpesa.on_confirmation(await read_body(request)))
