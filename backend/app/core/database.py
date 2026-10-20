from typing import Any
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

db_url = settings.sync_database_url
is_sqlite = db_url.startswith("sqlite")

connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_kwargs: dict[str, Any] = {
    "connect_args": connect_args,
    "pool_pre_ping": settings.DB_POOL_PRE_PING,
}

# PostgreSQL connection pool settings được cấu hình trực tiếp từ .env
if not is_sqlite:
    engine_kwargs.update(
        {
            "poolclass": QueuePool,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE,
        }
    )

engine = create_engine(db_url, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
