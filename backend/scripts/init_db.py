"""Initialize the development PostgreSQL database schema."""

from sqlalchemy import text

from app.core.database import Base, engine
from app.models import City, District, Listing, ListingEmbedding, User, Ward


def main() -> None:
    # Importing the models above registers every table with Base.metadata.
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=connection)

    print("Database schema initialized successfully.")


if __name__ == "__main__":
    main()
