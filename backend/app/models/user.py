from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)  # poster_id string representation
    name = Column(String, nullable=False)
    avatar_url = Column(String, nullable=True)
    live_ads = Column(Integer, default=0)
    sold_ads = Column(Integer, default=0)
    is_company = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship with listings
    listings = relationship("Listing", back_populates="poster", cascade="all, delete-orphan")
