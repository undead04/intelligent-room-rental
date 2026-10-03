from sqlalchemy import Column, String, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class Listing(Base):
    __tablename__ = "listings"

    id = Column(String, primary_key=True)
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
    furnishing_code = Column(Integer, nullable=True)

    # Location
    address_raw = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    # Timestamps
    posted_date = Column(DateTime, nullable=True)
    crawled_at = Column(DateTime, nullable=True)

    # Safety Score
    safety_score = Column(Float, nullable=True)
    concept_scores = Column(JSON, nullable=True)  # JSON object with concept scores

    # Poster Foreign Key
    poster_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    ward_id = Column(Integer, ForeignKey("wards.id"),nullable=True,index=True)
    district_id = Column(Integer,ForeignKey("districts.id"), nullable=True, index=True)
    region_id = Column(Integer,ForeignKey("cities.id"), nullable=True, index=True)
    room_type_id = Column(Integer,ForeignKey("room_types.id"), nullable=True, index=True)

    # Relationship
    poster = relationship("User", back_populates="listings")
    city = relationship("City", back_populates="listings", foreign_keys=[region_id])
    district = relationship("District", back_populates="listings", foreign_keys=[district_id])
    ward = relationship("Ward", back_populates="listings", foreign_keys=[ward_id])
    room_type = relationship("RoomType", back_populates="listings", foreign_keys=[room_type_id])
    # Danh sách chứa nhiều embedding
    embeddings = relationship("ListingEmbedding", back_populates="listing")
