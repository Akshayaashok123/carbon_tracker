"""
Centralized configuration for EcoTracker.
Reads from environment variables with sensible defaults for local development.
"""
import os


class Config:
    # ── Core Flask ────────────────────────────────────────────
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or "eco-tracker-dev-secret"

    # ── Database ──────────────────────────────────────────────
    # Render provides DATABASE_URL automatically when you add a PostgreSQL instance.
    # For local development, falls back to SQLite.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///ecotracker.db"
    )
    # Render uses 'postgres://' prefix which SQLAlchemy 2.x doesn't accept
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # ── Google OAuth 2.0 ──────────────────────────────────────
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # ── External API Keys ─────────────────────────────────────
    OLA_MAPS_KEY = os.environ.get("OLA_MAPS_KEY", "")
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")
    CALORIENINJAS_API_KEY = os.environ.get("CALORIENINJAS_API_KEY", "")
    ELECTRICITY_MAPS_API_KEY = os.environ.get("ELECTRICITY_MAPS_API_KEY", "")

    # ── Strava ────────────────────────────────────────────────
    STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID", "")
    STRAVA_CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET", "")
    STRAVA_REDIRECT_URI = os.environ.get(
        "STRAVA_REDIRECT_URI", "http://localhost:5000/api/strava/callback"
    )

    # ── App Constants ─────────────────────────────────────────
    GREEN_DAY_LIMIT = 5.0
    MAX_LEADERBOARD_SIZE = 15
