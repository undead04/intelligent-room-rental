from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class Listing(Base):
    __tablename__ = "listings"

    listing_id = Column(String, primary_key=True, index=True)  # e.g. "nhatot_45314692"
    ad_id = Column(String, nullable=True, index=True)
    list_id = Column(String, nullable=True)
    source = Column(String, default="nhatot")
    url = Column(String, nullable=True)

    # General info
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price_string = Column(String, nullable=True)
    main_image = Column(String, nullable=True)
    images = Column(JSON, nullable=True)  # JSON array of image URLs

    # Financial & Property Specs
    price_vnd = Column(Float, nullable=True, index=True)
    area_m2 = Column(Float, nullable=True, index=True)
    price_million_per_m2 = Column(Float, nullable=True)
    deposit = Column(Float, nullable=True)
    furnishing = Column(String, nullable=True)
    furnishing_code = Column(Integer, nullable=True)
    room_type = Column(String, nullable=True)
    category_id = Column(Integer, nullable=True)

    # Location
    address_raw = Column(String, nullable=True)
    street_name = Column(String, nullable=True)
    ward = Column(String, nullable=True)
    district = Column(String, nullable=True, index=True)
    city = Column(String, nullable=True, index=True)
    ward_id = Column(Integer, nullable=True)
    district_id = Column(Integer, nullable=True)
    region_id = Column(Integer, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    # Poster Foreign Key
    poster_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)

    # Timestamps
    posted_date = Column(DateTime, nullable=True)
    crawled_at = Column(DateTime, nullable=True)

    # Relationship
    poster = relationship("User", back_populates="listings")
