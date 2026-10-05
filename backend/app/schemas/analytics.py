from typing import Optional

from pydantic import BaseModel


class PriceStatsGeneral(BaseModel):
    total_listings: int
    average_price_vnd: Optional[float] = None
    area_hotspot: Optional[str] = None

class PriceStatsByArea(BaseModel):
    area_id: int
    area: str
    total_listings: int
    fluctuation_month: Optional[float] = None
    average_price_vnd: Optional[float] = None
    minimum_price_vnd: Optional[float] = None
    maximum_price_vnd: Optional[float] = None

class PriceStatsResponse(BaseModel):
    price_stats_general: PriceStatsGeneral
    price_stats_by_area: Optional[list[PriceStatsByArea]] = None
