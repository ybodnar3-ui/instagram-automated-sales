import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config import setup_logging, settings
from database import Base, engine, SessionLocal
from api import accounts, bot, conversations, stats, triggers as triggers_api, outbound as outbound_api

setup_logging()
logger = logging.getLogger(__name__)

try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified/created")
except Exception as exc:
    logger.warning("Could not create tables at startup (expected during tests): %s", exc)

app = FastAPI(title="Instagram AI Sales Bot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    # Pass-through: auth disabled, CORS preflight, non-API paths
    if (
        not settings.DASHBOARD_API_KEY
        or request.method == "OPTIONS"
        or request.url.path in ("/health", "/")
        or not request.url.path.startswith("/api")
    ):
        return await call_next(request)
    key = request.headers.get("X-API-Key", "")
    if key != settings.DASHBOARD_API_KEY:
        logger.warning("api_key_auth: rejected %s %s from %s", request.method, request.url.path, request.client.host if request.client else "unknown")
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

app.include_router(accounts.router, prefix="/api", tags=["accounts"])
app.include_router(bot.router, prefix="/api", tags=["bot"])
app.include_router(conversations.router, prefix="/api", tags=["conversations"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(triggers_api.router, prefix="/api", tags=["triggers"])
app.include_router(outbound_api.router, prefix="/api", tags=["outbound"])


@app.get("/health")
def health_check():
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        logger.error("Health check DB ping failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "error", "db": "unreachable"})
