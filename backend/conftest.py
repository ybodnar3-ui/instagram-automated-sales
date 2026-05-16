import os
from cryptography.fernet import Fernet

# Set required env vars before any module imports settings
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests-only")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
