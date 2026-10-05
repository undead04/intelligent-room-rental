from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)


    districts = relationship("District", back_populates="city")
    listings = relationship("Listing", back_populates="city")


class District(Base):
    __tablename__ = "districts"

    id = Column(Integer, primary_key=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    

    city = relationship("City", back_populates="districts")
    wards = relationship("Ward", back_populates="district")
    listings = relationship("Listing", back_populates="district")


class Ward(Base):
    __tablename__ = "wards"

    id = Column(Integer, primary_key=True)
    district_id = Column(Integer, ForeignKey("districts.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
   
    district = relationship("District", back_populates="wards")
    listings = relationship("Listing", back_populates="ward")
