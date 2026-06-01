import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Amal Blood Donation & Transfer API")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-amal-key-change-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    
    # Supabase / PostgreSQL or Local SQLite fallback
    # Replace legacy postgres:// with postgresql:// for SQLAlchemy compatibility
    _db_url = os.getenv("DATABASE_URL", "sqlite:///./amal.db")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    DATABASE_URL: str = _db_url
    
    # Matching configurations
    MATCH_RADIUS_KM: float = float(os.getenv("MATCH_RADIUS_KM", "30.0"))
    MIN_DONATION_INTERVAL_DAYS: int = int(os.getenv("MIN_DONATION_INTERVAL_DAYS", "56"))
    
    # Scheduler interval
    SCHEDULER_INTERVAL_MINUTES: int = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "15"))

settings = Settings()
