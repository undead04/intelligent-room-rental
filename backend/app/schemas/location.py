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
