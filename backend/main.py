import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import setup_logging
from database import Base, engine
from api import accounts, bot, conversations, stats

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


@app.get("/health")
def health_check():
    return {"status": "ok"}
