from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    id: str = Field(..., description="ID người đăng (poster_id)")
    name: str = Field(..., description="Tên hiển thị người đăng")
    avatar_url: Optional[str] = Field(None, description="URL ảnh đại diện")
    live_ads: Optional[int] = Field(0, description="Số tin đang đăng")
    sold_ads: Optional[int] = Field(0, description="Số tin đã cho thuê/bán")
    is_company: Optional[bool] = Field(False, description="Môi giới/công ty hay cá nhân")


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    live_ads: Optional[int] = None
    sold_ads: Optional[int] = None
    is_company: Optional[bool] = None


class UserResponse(UserBase):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
