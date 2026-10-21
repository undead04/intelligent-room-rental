from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.models.location import City, District, Ward
from app.models.room_type import RoomType


class LocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def cities(self, search: Optional[str]) -> list[City]:
        query = self.db.query(City)
        if search:
            query = query.filter(City.name.ilike(f"%{search}%"))
        return query.order_by(City.name).all()

    def districts(self, city_id: Optional[int], search: Optional[str]) -> list[District]:
        query = self.db.query(District)
        if city_id is not None:
            query = query.filter(District.city_id == city_id)
        if search:
            query = query.filter(District.name.ilike(f"%{search}%"))
        return query.order_by(District.name).all()

    def wards(self, district_id: Optional[int], search: Optional[str]) -> list[Ward]:
        query = self.db.query(Ward)
        if district_id is not None:
            query = query.filter(Ward.district_id == district_id)
        if search:
            query = query.filter(Ward.name.ilike(f"%{search}%"))
        return query.order_by(Ward.name).all()

    def room_types(self, search: Optional[str]) -> list[RoomType]:
        query = self.db.query(RoomType)
        if search:
            query = query.filter(RoomType.name.ilike(f"%{search}%"))
        return query.order_by(RoomType.id).all()

    def nearby_locations(
        self,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        district_id: Optional[int] = None,
        ward_id: Optional[int] = None,
        city_id: Optional[int] = None,
        radius_km: float = 12.0,
        limit: int = 4,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        room_type: Optional[str] = None,
        amenities: Optional[list[str]] = None,
    ) -> list[dict]:
        """Truy vấn các quận/phường lân cận dựa trên toạ độ hoặc ID hành chính và thống kê phòng trọ thực tế.
        Hỗ trợ lọc số phòng trống và khoảng giá min-max theo điều kiện bắt buộc của người dùng.
        """
        target_lat, target_lng = lat, lng
        if (target_lat is None or target_lng is None) and ward_id:
            c = self.db.query(func.avg(Listing.lat), func.avg(Listing.lng)).filter(Listing.ward_id == ward_id).first()
            if c and c[0] is not None:
                target_lat, target_lng = float(c[0]), float(c[1])
        if (target_lat is None or target_lng is None) and district_id:
            c = self.db.query(func.avg(Listing.lat), func.avg(Listing.lng)).filter(Listing.district_id == district_id).first()
            if c and c[0] is not None:
                target_lat, target_lng = float(c[0]), float(c[1])
        if (target_lat is None or target_lng is None) and city_id:
            c = self.db.query(func.avg(Listing.lat), func.avg(Listing.lng)).filter(Listing.region_id == city_id).first()
            if c and c[0] is not None:
                target_lat, target_lng = float(c[0]), float(c[1])

        if target_lat is None or target_lng is None:
            return []

        # Công thức Haversine tính khoảng cách km từ toạ độ mục tiêu đến tâm phân bố phòng
        dist_km = 6371.0 * 2.0 * func.asin(
            func.sqrt(
                func.pow(func.sin(func.radians(func.avg(Listing.lat) - target_lat) / 2.0), 2)
                + func.cos(func.radians(target_lat))
                * func.cos(func.radians(func.avg(Listing.lat)))
                * func.pow(func.sin(func.radians(func.avg(Listing.lng) - target_lng) / 2.0), 2)
            )
        )

        has_mandatory = bool(max_price is not None or min_price is not None or room_type or amenities)

        def _apply_filters(q):
            if min_price is not None:
                q = q.filter(Listing.price_vnd >= min_price)
            if max_price is not None:
                q = q.filter(Listing.price_vnd <= max_price)
            if room_type:
                clean = room_type.value if hasattr(room_type, "value") else str(room_type).strip().upper()
                clean_map = {"ROOM": 1, "STUDIO": 2, "APARTMENT": 3, "SLEEPBOX": 4, "WHOLE_HOUSE": 5}
                rt_id = clean_map.get(clean) if clean in clean_map else (int(clean) if clean.isdigit() else None)
                if rt_id is not None:
                    q = q.filter(Listing.room_type_id == rt_id)
            if amenities:
                from app.services.reranker import _NORMALIZE_AMENITY
                from sqlalchemy import Float, cast

                for am in amenities:
                    clean_code = _NORMALIZE_AMENITY(str(getattr(am, "value", am)))
                    q = q.filter(
                        func.coalesce(cast(Listing.concept_scores.op("->>")(clean_code), Float), 0.0) >= 0.5
                    )
            return q

        results: list[dict] = []
        is_filtered = False

        # Nếu có ward_id hoặc bán kính nhỏ (<= 6km), ưu tiên tìm theo cấp Phường
        if ward_id or radius_km <= 6.0:
            def _build_wq(filtered: bool):
                wq = (
                    self.db.query(
                        Ward.id,
                        Ward.name,
                        District.name.label("parent_name"),
                        func.count(Listing.id).label("total_listings"),
                        func.min(Listing.price_vnd).label("min_price_vnd"),
                        func.max(Listing.price_vnd).label("max_price_vnd"),
                        func.avg(Listing.price_vnd).label("avg_price_vnd"),
                        dist_km.label("distance_km"),
                    )
                    .join(District, Ward.district_id == District.id)
                    .join(Listing, Listing.ward_id == Ward.id)
                    .filter(Listing.lat.isnot(None), Listing.lng.isnot(None))
                )
                if ward_id:
                    wq = wq.filter(Ward.id != ward_id)
                if filtered:
                    wq = _apply_filters(wq)
                return (
                    wq.group_by(Ward.id, Ward.name, District.name)
                    .having(dist_km <= radius_km, func.count(Listing.id) > 0)
                    .order_by(dist_km.asc())
                    .limit(limit)
                    .all()
                )

            w_rows = _build_wq(filtered=True) if has_mandatory else []
            if w_rows:
                is_filtered = True
            else:
                w_rows = _build_wq(filtered=False)

            for r in w_rows:
                results.append({
                    "id": r.id,
                    "name": r.name,
                    "level": "ward",
                    "parent_name": r.parent_name,
                    "distance_km": round(float(r.distance_km), 1),
                    "total_listings": int(r.total_listings),
                    "min_price_vnd": float(r.min_price_vnd) if r.min_price_vnd is not None else 0.0,
                    "max_price_vnd": float(r.max_price_vnd) if r.max_price_vnd is not None else (float(r.min_price_vnd) if r.min_price_vnd is not None else 0.0),
                    "avg_price_vnd": float(r.avg_price_vnd) if r.avg_price_vnd is not None else 0.0,
                    "is_filtered": is_filtered,
                })

        # Nếu không có phường phù hợp hoặc tìm theo quận/khoảng cách rộng hơn
        if not results:
            def _build_dq(filtered: bool):
                dq = (
                    self.db.query(
                        District.id,
                        District.name,
                        City.name.label("parent_name"),
                        func.count(Listing.id).label("total_listings"),
                        func.min(Listing.price_vnd).label("min_price_vnd"),
                        func.max(Listing.price_vnd).label("max_price_vnd"),
                        func.avg(Listing.price_vnd).label("avg_price_vnd"),
                        dist_km.label("distance_km"),
                    )
                    .join(City, District.city_id == City.id)
                    .join(Listing, Listing.district_id == District.id)
                    .filter(Listing.lat.isnot(None), Listing.lng.isnot(None))
                )
                if district_id:
                    dq = dq.filter(District.id != district_id)
                if filtered:
                    dq = _apply_filters(dq)
                return (
                    dq.group_by(District.id, District.name, City.name)
                    .having(dist_km <= radius_km, func.count(Listing.id) > 0)
                    .order_by(dist_km.asc())
                    .limit(limit)
                    .all()
                )

            d_rows = _build_dq(filtered=True) if has_mandatory else []
            if d_rows:
                is_filtered = True
            else:
                d_rows = _build_dq(filtered=False)

            for r in d_rows:
                results.append({
                    "id": r.id,
                    "name": r.name,
                    "level": "district",
                    "parent_name": r.parent_name,
                    "distance_km": round(float(r.distance_km), 1),
                    "total_listings": int(r.total_listings),
                    "min_price_vnd": float(r.min_price_vnd) if r.min_price_vnd is not None else 0.0,
                    "max_price_vnd": float(r.max_price_vnd) if r.max_price_vnd is not None else (float(r.min_price_vnd) if r.min_price_vnd is not None else 0.0),
                    "avg_price_vnd": float(r.avg_price_vnd) if r.avg_price_vnd is not None else 0.0,
                    "is_filtered": is_filtered,
                })

        return results
