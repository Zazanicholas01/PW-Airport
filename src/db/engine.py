import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.engine.url import make_url

Base = declarative_base()

def build_database_url() -> str:
    """Return the Postgres connection URL, preferring DATABASE_URL when set."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return str(make_url(url))

    user = os.environ.get("POSTGRES_USER", "airport")
    password = os.environ.get("POSTGRES_PASSWORD", "airport")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5433")
    db = os.environ.get("POSTGRES_DB", "Airport")

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


@lru_cache()
def get_engine():
    """Create (and cache) a SQLAlchemy engine."""
    return create_engine(build_database_url(), future=True, pool_pre_ping=True)

def get_db(Session):
    db = Session()
    try:
        yield db
    finally:
        db.close()
