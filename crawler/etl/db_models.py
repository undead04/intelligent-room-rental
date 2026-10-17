"""Standalone SQLAlchemy ORM & Database Connection cho Crawler Container.

Giúp module `crawler` kết nối và nạp dữ liệu trực tiếp vào PostgreSQL (pgvector)
mà hoàn toàn KHÔNG phụ thuộc vào source code của module `backend` khi tách thành
các Docker container độc lập.
"""

import os
from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

load_dotenv()

DEFAULT_EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-base")


def get_database_url(override_url: str | None = None) -> str:
    url = override_url or os.environ.get("DATABASE_URL")
    if not url:
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", "ny300998")
        server = os.environ.get("POSTGRES_SERVER", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ.get("POSTGRES_DB", "smart_housing_db")
        url = f"postgresql+psycopg2://{user}:{password}@{server}:{port}/{db}"
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


Base = declarative_base()


class City(Base):
    __tablename__ = "cities"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)


class District(Base):
    __tablename__ = "districts"
    id = Column(Integer, primary_key=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)


class Ward(Base):
    __tablename__ = "wards"
    id = Column(Integer, primary_key=True)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)


class RoomType(Base):
    __tablename__ = "room_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    live_ads = Column(Integer, default=0)
    sold_ads = Column(Integer, default=0)
    is_company = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Listing(Base):
    __tablename__ = "listings"
    id = Column(String, primary_key=True)
    source = Column(String, default="nhatot")
    url = Column(String, nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price_string = Column(String, nullable=True)
    main_image = Column(String, nullable=True)
    images = Column(JSON, nullable=True)
    price_vnd = Column(Float, nullable=True, index=True)
    area_m2 = Column(Float, nullable=True, index=True)
    price_million_per_m2 = Column(Float, nullable=True)
    deposit = Column(Float, nullable=True)
    furnishing_code = Column(Integer, nullable=True)
    address_raw = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    posted_date = Column(DateTime, nullable=True)
    crawled_at = Column(DateTime, nullable=True)
    safety_score = Column(Float, nullable=True)
    concept_scores = Column(JSON, nullable=True)
    amenity_overall = Column(Float, nullable=True)
    price_score = Column(Float, nullable=True)
    poster_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    ward_id = Column(Integer, ForeignKey("wards.id"), nullable=True, index=True)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=True, index=True)
    region_id = Column(Integer, ForeignKey("cities.id"), nullable=True, index=True)
    room_type_id = Column(Integer, ForeignKey("room_types.id"), nullable=True, index=True)


class ListingEmbedding(Base):
    __tablename__ = "listing_embeddings"
    __table_args__ = (
        UniqueConstraint("listing_id", "model_name", name="uq_listing_embedding_model"),
    )
    id = Column(Integer, primary_key=True)
    listing_id = Column(
        String(150),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_name = Column(String(150), nullable=False, index=True)
    dimension = Column(Integer, nullable=False)
    vector = Column(Vector(), nullable=False)
    content_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def create_db_session(db_url: str | None = None):
    sync_url = get_database_url(db_url)
    eng = create_engine(sync_url, pool_pre_ping=True)
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return eng, SessionFactory()
