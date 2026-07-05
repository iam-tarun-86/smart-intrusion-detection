"""
database.py — PostgreSQL connection & session management
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Use SQLite for dev (easy), switch to PostgreSQL later
# For now: SQLite file-based so you don't need to setup PostgreSQL yet
SQLALCHEMY_DATABASE_URL = "sqlite:///./intrusion.db"
# Later: "postgresql://user:password@localhost/intrusion_db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {},
    pool_size=10,        # Increase from default 5
    max_overflow=20,     # Increase from default 10
    pool_timeout=60      # Wait longer before timeout
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()