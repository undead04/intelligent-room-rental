"""Initialize the development PostgreSQL database schema."""

import logging
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, engine
from app.models import City, District, Listing, ListingEmbedding, User, Ward

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_db() -> None:
    logger.info("Initializing database schema...")
    with engine.begin() as connection:
        # Enable pgvector extension
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        # Create all tables registered under Base.metadata
        Base.metadata.create_all(bind=connection)

    logger.info("Database schema initialized successfully.")


if __name__ == "__main__":
    init_db()