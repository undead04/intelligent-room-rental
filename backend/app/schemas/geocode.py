from pydantic import BaseModel


class GeocodeResponse(BaseModel):
    query: str
    lat: float
    lon: float
    formatted_address: str
    provider: str