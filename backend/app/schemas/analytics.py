from typing import Optional

from pydantic import BaseModel


class PriceStatsResponse(BaseModel):
    city: Optional[str] = None
    district: Optional[str] = None
    room_type: Optional[str] = None
    total_listings: int
    average_price_vnd: Optional[float] = None
    minimum_price_vnd: Optional[float] = None
    maximum_price_vnd: Optional[float] = None
    average_area_m2: Optional[float] = None
