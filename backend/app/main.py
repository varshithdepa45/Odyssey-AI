import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import SessionLocal, init_db
from .routers import admin, admin_ops, auth, chat, game, map as map_routes
from .seed import seed

settings = get_settings()
logging.basicConfig(level=logging.INFO)
production = settings.env == "production"


@asynccontextmanager
async def lifespan(_: FastAPI):
    insecure = settings.insecure_defaults()
    if production and insecure:
        raise RuntimeError(f"Refusing to start in production with default secrets: {', '.join(insecure)}")
    init_db()
    if settings.auto_seed:
        with SessionLocal() as db:
            if seed(db):
                logging.getLogger("codehunt").info("Empty database: seeded placeholder event")
    yield


app = FastAPI(
    title="CodeHunt API",
    lifespan=lifespan,
    # The interactive docs list every admin route, so they stay off in production.
    docs_url=None if production else "/docs",
    redoc_url=None,
    openapi_url=None if production else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth.router)
app.include_router(game.router)
app.include_router(chat.router)
app.include_router(map_routes.router)
app.include_router(admin.router)
app.include_router(admin_ops.router)


@app.get("/api/health")
def health():
    return {"ok": True}
