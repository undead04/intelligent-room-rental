import csv
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.models.listing import Listing
from app.models.user import User
from app.schemas.listing import ListingResponse, ListingDetailResponse
from app.schemas.user import UserResponse

router = APIRouter()


# Dynamic path resolution to dataset CSV
def find_csv_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "crawler" / "data" / "processed" / "listings_clean.csv"
        if candidate.exists():
            return candidate
    return current.parents[4] / "crawler" / "data" / "processed" / "listings_clean.csv"


CSV_PATH = find_csv_path()


def parse_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def parse_bool(val: Optional[str]) -> Optional[bool]:
    if not val:
        return None
    return val.strip().lower() in ("true", "1", "t", "yes")


# --------------------------------------------------------------------------
# 1. GET LISTINGS (Danh sách tin đăng phòng trọ)
# --------------------------------------------------------------------------
@router.get("/", response_model=List[ListingResponse], summary="Lấy danh sách tin đăng phòng trọ")
def get_listings(
    limit: int = Query(default=20, ge=1, le=100, description="Số lượng kết quả mỗi trang"),
    offset: int = Query(default=0, ge=0, description="Vị trí bắt đầu (Phân trang)"),
    search: Optional[str] = Query(default=None, description="Từ khóa tìm kiếm theo tiêu đề/địa chỉ"),
    district: Optional[str] = Query(default=None, description="Lọc theo Quận/Huyện"),
    db: Session = Depends(get_db)
):
    """
    **Lấy danh sách tin đăng phòng trọ (phân trang + lọc từ khóa)**.
    Thực hiện truy vấn từ CSDL PostgreSQL/SQLAlchemy, tự động chuyển về dataset file nếu DB chưa được populate.
    """
    try:
        query = db.query(Listing)
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Listing.title.ilike(search_pattern),
                    Listing.address_raw.ilike(search_pattern)
                )
            )
        if district:
            query = query.filter(Listing.district.ilike(f"%{district}%"))

        db_listings = query.offset(offset).limit(limit).all()
        if db_listings:
            return db_listings
    except Exception:
        # Fallback if DB is not reachable or uninitialized
        pass

    # Fallback: Read from cleaned dataset CSV file
    results: List[ListingResponse] = []
    if CSV_PATH.exists():
        with open(CSV_PATH, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            count = 0
            skipped = 0
            for row in reader:
                title = row.get("title") or ""
                addr = row.get("address_raw") or ""
                dist = row.get("district") or ""
                
                if search:
                    s = search.lower()
                    if s not in title.lower() and s not in addr.lower():
                        continue
                
                if district:
                    if district.lower() not in dist.lower():
                        continue

                if skipped < offset:
                    skipped += 1
                    continue

                item = ListingResponse(
                    listing_id=row.get("listing_id") or row.get("\ufefflisting_id") or "N/A",
                    title=title or "Untitled",
                    price_vnd=parse_float(row.get("price_vnd")),
                    area_m2=parse_float(row.get("area_m2")),
                    address_raw=addr,
                    lat=parse_float(row.get("lat")),
                    lng=parse_float(row.get("lng")),
                    main_image=row.get("main_image"),
                    room_type=row.get("room_type"),
                    price_string=row.get("price_string"),
                    price_million_per_m2=parse_float(row.get("price_million_per_m2")),
                    deposit=parse_float(row.get("deposit")),
                    furnishing=row.get("furnishing"),
                    district=dist,
                    city=row.get("city"),
                    poster_id=row.get("poster_id")
                )
                results.append(item)
                count += 1
                if count >= limit:
                    break

    return results


# --------------------------------------------------------------------------
# 2. GET LISTING BY ID (Chi tiết 1 tin đăng)
# --------------------------------------------------------------------------
@router.get("/{listing_id}", response_model=ListingDetailResponse, summary="Lấy chi tiết 1 tin đăng theo ID")
def get_listing_by_id(
    listing_id: str,
    db: Session = Depends(get_db)
):
    """
    **Lấy chi tiết tin đăng phòng trọ theo listing_id**.
    Trả về toàn bộ thông tin chi tiết bài đăng cùng thông tin người đăng (User/Poster).
    """
    try:
        db_listing = db.query(Listing).filter(Listing.listing_id == listing_id).first()
        if db_listing:
            return db_listing
    except Exception:
        pass

    # Fallback: Find item by ID in cleaned dataset CSV file
    if CSV_PATH.exists():
        with open(CSV_PATH, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                current_id = row.get("listing_id") or row.get("\ufefflisting_id")
                if current_id == listing_id:
                    # Poster details
                    poster_data = None
                    if row.get("poster_id"):
                        poster_data = UserResponse(
                            id=row.get("poster_id"),
                            name=row.get("poster_name") or "Khách hàng",
                            avatar_url=row.get("poster_avatar"),
                            live_ads=int(row.get("poster_live_ads") or 0),
                            sold_ads=int(row.get("poster_sold_ads") or 0),
                            is_company=parse_bool(row.get("is_company_ad"))
                        )

                    # Image list parsing
                    img_list = []
                    if row.get("images"):
                        try:
                            import ast
                            img_list = ast.literal_eval(row.get("images"))
                        except Exception:
                            img_list = [row.get("main_image")] if row.get("main_image") else []

                    return ListingDetailResponse(
                        listing_id=current_id,
                        title=row.get("title") or "Untitled",
                        price_vnd=parse_float(row.get("price_vnd")),
                        area_m2=parse_float(row.get("area_m2")),
                        address_raw=row.get("address_raw"),
                        lat=parse_float(row.get("lat")),
                        lng=parse_float(row.get("lng")),
                        main_image=row.get("main_image"),
                        room_type=row.get("room_type"),
                        price_string=row.get("price_string"),
                        price_million_per_m2=parse_float(row.get("price_million_per_m2")),
                        deposit=parse_float(row.get("deposit")),
                        furnishing=row.get("furnishing"),
                        district=row.get("district"),
                        city=row.get("city"),
                        poster_id=row.get("poster_id"),
                        ad_id=row.get("ad_id"),
                        list_id=row.get("list_id"),
                        source=row.get("source"),
                        url=row.get("url"),
                        description=row.get("description"),
                        images=img_list,
                        street_name=row.get("street_name"),
                        ward=row.get("ward"),
                        poster=poster_data
                    )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Listing with id '{listing_id}' not found"
    )
