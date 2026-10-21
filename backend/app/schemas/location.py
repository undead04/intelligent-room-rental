from pydantic import BaseModel, ConfigDict


class CityResponse(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class DistrictResponse(BaseModel):
    id: int
    city_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class WardResponse(BaseModel):
    id: int
    district_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class NearbyLocationItem(BaseModel):
    id: int
    name: str
    level: str  # "ward" hoặc "district"
    parent_name: str | None = None
    distance_km: float
    total_listings: int
    min_price_vnd: float
    max_price_vnd: float | None = None
    avg_price_vnd: float
    is_filtered: bool = False

    model_config = ConfigDict(from_attributes=True)
