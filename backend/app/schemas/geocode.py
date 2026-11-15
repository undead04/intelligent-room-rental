from typing import Optional
from pydantic import BaseModel, Field


class GeocodeCandidate(BaseModel):
    """Ứng viên toạ độ trả về khi kết quả geocoding có nhiều cơ sở/điểm phân tán."""

    name: str
    lat: float
    lon: float
    formatted_address: str = ""
    provider: str = ""


class GeocodeResponse(BaseModel):
    """Kết quả phân giải địa điểm từ dịch vụ Geocoding (1 điểm hoặc danh sách ambiguous)."""

    query: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    formatted_address: str = ""
    provider: str = ""
    ambiguous: bool = False
    candidates: list[GeocodeCandidate] = Field(default_factory=list)