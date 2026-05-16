import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from config import setup_logging
from database import Base, engine, SessionLocal
from api import accounts, bot, conversations, stats, triggers as triggers_api

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
    allow_origins=["http://localhost:3000", "http://frontend"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router, prefix="/api", tags=["accounts"])
app.include_router(bot.router, prefix="/api", tags=["bot"])
app.include_router(conversations.router, prefix="/api", tags=["conversations"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(triggers_api.router, prefix="/api", tags=["triggers"])


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
