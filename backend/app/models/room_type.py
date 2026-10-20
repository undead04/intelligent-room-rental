from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base


class RoomType(Base):
    __tablename__ = "room_types"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=True, unique=True, index=True)
    name = Column(String, nullable=True)
    listings = relationship("Listing", back_populates="room_type")
