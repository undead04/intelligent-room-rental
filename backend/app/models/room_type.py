from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class RoomType(Base):
    __tablename__ = "room_types"

    id = Column(Integer, primary_key=True)
    room_type = Column(String, nullable=True)
    listings = relationship("Listing", back_populates="room_type")
    
