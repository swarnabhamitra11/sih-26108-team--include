"""Centralized application configuration, loaded from .env."""

import os
from dotenv import load_dotenv

load_dotenv()

# Database
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
DB_NAME = os.getenv("POSTGRES_DB", "standards")
DB_USER = os.getenv("POSTGRES_USER", "user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

# App settings
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.55"))
TOP_K = int(os.getenv("TOP_K", "5"))
RRF_K = int(os.getenv("RRF_K", "60"))

# Optional LLM settings
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
