from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.room_type import RoomType
from app.schemas.room_type import RoomTypeResponse

router = APIRouter()


@router.get("/", response_model=List[RoomTypeResponse], summary="Lấy danh sách loại phòng")
def get_room_types(
    search: Optional[str] = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(RoomType)
    if search:
        query = query.filter(RoomType.room_type.ilike(f"%{search}%"))
    return query.order_by(RoomType.room_type).all()
