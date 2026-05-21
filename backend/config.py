import logging
import sys
from pydantic_settings import BaseSettings
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    ANTHROPIC_API_KEY: str
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    DASHBOARD_API_KEY: str = ""
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env"}


settings = Settings()
try:
    cipher = Fernet(settings.ENCRYPTION_KEY.encode())
except Exception as _e:
    print(
        f"FATAL: ENCRYPTION_KEY is invalid — must be a 32-byte url-safe base64 key.\n"
        f"Generate one with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
        f"Error: {_e}",
        file=sys.stderr,
    )
    sys.exit(1)


def setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        stream=sys.stdout,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    # Silence noisy third-party loggers
    logging.getLogger("instagrapi").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
