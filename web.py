from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ORIGINS
from database import initialize
from errors import register_error_handlers
from routes import router


app = FastAPI()
if ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

register_error_handlers(app)
app.include_router(router)


@app.on_event("startup")
def startup():
    initialize()
