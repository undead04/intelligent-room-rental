from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    id: str = Field(..., description="ID người đăng (poster_id)")
    name: str = Field(..., description="Tên hiển thị người đăng")
    avatar_url: Optional[str] = Field(None, description="URL ảnh đại diện")
    live_ads: Optional[int] = Field(0, description="Số tin đang đăng")
    sold_ads: Optional[int] = Field(0, description="Số tin đã cho thuê/bán")
    is_company: Optional[bool] = Field(False, description="Môi giới/công ty hay cá nhân")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
