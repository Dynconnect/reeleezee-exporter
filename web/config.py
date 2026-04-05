"""Application configuration loaded from environment variables."""

import os
import secrets

# Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Database
DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/jobs.db")

# Data storage
DATA_DIR = os.environ.get("DATA_DIR", "data/exports")

# Security
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_urlsafe(32))

# Session expiry in hours
SESSION_EXPIRY_HOURS = int(os.environ.get("SESSION_EXPIRY_HOURS", "24"))
