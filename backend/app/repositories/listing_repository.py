from typing import Optional

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.models.embedding import ListingEmbedding
from app.models.listing import Listing


class ListingRepository:
    def __init__(self, db: Session):
        self.db = db

    def base_query(self) -> Query:
        return self.db.query(Listing).options(
            joinedload(Listing.city),
            joinedload(Listing.district),
            joinedload(Listing.ward),
            joinedload(Listing.room_type),
        )

    def filtered_query(
        self,
        *,
        search: Optional[str],
        city_id: Optional[int],
        district_id: Optional[int],
        ward_id: Optional[int],
        room_type_id: Optional[int],
        min_price: Optional[float],
        max_price: Optional[float],
        min_area: Optional[float],
        max_area: Optional[float],
    ) -> Query:
        query = self.base_query()
        if search:
            pattern = f"%{search}%"
            query = query.filter(or_(Listing.title.ilike(pattern), Listing.address_raw.ilike(pattern)))
        for column, value in (
            (Listing.region_id, city_id),
            (Listing.district_id, district_id),
            (Listing.ward_id, ward_id),
            (Listing.room_type_id, room_type_id),
        ):
            if value is not None:
                query = query.filter(column == value)
        if min_price is not None:
            query = query.filter(Listing.price_vnd >= min_price)
        if max_price is not None:
            query = query.filter(Listing.price_vnd <= max_price)
        if min_area is not None:
            query = query.filter(Listing.area_m2 >= min_area)
        if max_area is not None:
            query = query.filter(Listing.area_m2 <= max_area)
        return query

    def search(
        self,
        *,
        search: Optional[str],
        city_id: Optional[int],
        district_id: Optional[int],
        ward_id: Optional[int],
        room_type_id: Optional[int],
        min_price: Optional[float],
        max_price: Optional[float],
        min_area: Optional[float],
        max_area: Optional[float],
        order_by: str,
        sort_desc: bool,
        limit: int,
        offset: int,
    ) -> list[Listing]:
        query = self.filtered_query(
            search=search,
            city_id=city_id,
            district_id=district_id,
            ward_id=ward_id,
            room_type_id=room_type_id,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
        )
        sort_column = getattr(Listing, order_by)
        query = query.order_by(sort_column.desc() if sort_desc else sort_column)
        return query.offset(offset).limit(limit).all()

    def count(
        self,
        *,
        search: Optional[str],
        city_id: Optional[int],
        district_id: Optional[int],
        ward_id: Optional[int],
        room_type_id: Optional[int],
        min_price: Optional[float],
        max_price: Optional[float],
        min_area: Optional[float],
        max_area: Optional[float],
    ) -> int:
        query = self.filtered_query(
            search=search,
            city_id=city_id,
            district_id=district_id,
            ward_id=ward_id,
            room_type_id=room_type_id,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
        )
        return query.order_by(None).count()

    def get_by_id(self, listing_id: str) -> Optional[Listing]:
        return (
            self.base_query()
            .options(joinedload(Listing.poster))
            .filter(Listing.id == listing_id)
            .one_or_none()
        )

    def count_and_average(self, filters: list) -> tuple[int, Optional[float]]:
        return self.db.query(
            func.count(Listing.id),
            func.avg(Listing.price_vnd),
        ).filter(*filters).one()

    def get_by_ids(self, ids: list[str], preserve_order: bool = True) -> list[Listing]:
        """
        Lấy danh sách Listing dựa theo danh sách listing_id.
        Nếu preserve_order=True, kết quả trả về sẽ giữ đúng thứ tự của danh sách ids đầu vào.
        """
        if not ids:
            return []

        query = self.base_query().filter(Listing.id.in_(ids))

        if preserve_order:
            order_case = case(
                {listing_id: index for index, listing_id in enumerate(ids)},
                value=Listing.id,
            )
            query = query.order_by(order_case)

        return query.all()

    def vector_search(
        self,
        query_vector: list[float],
        model_name: Optional[str] = None,
        limit: int = 20,
        similarity_threshold: Optional[float] = None,
        city_id: Optional[int] = None,
        district_id: Optional[int] = None,
        ward_id: Optional[int] = None,
        room_type_id: Optional[int] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> list[dict]:
        """
        Tìm kiếm tin đăng theo vector embedding bằng khoảng cách Cosine,
        trả về đầy đủ Listing kèm điểm khoảng cách (distance) và độ tương đồng (similarity_score).
        """
        # Cosine distance: d = 1 - cosine_similarity
        distance_col = ListingEmbedding.vector.cosine_distance(query_vector).label("distance")

        query = (
            self.db.query(Listing, distance_col)
            .join(ListingEmbedding, Listing.id == ListingEmbedding.listing_id)
            .options(
                joinedload(Listing.city),
                joinedload(Listing.district),
                joinedload(Listing.ward),
                joinedload(Listing.room_type),
            )
        )

        if model_name:
            query = query.filter(ListingEmbedding.model_name == model_name)

        if similarity_threshold is not None:
            # similarity_score >= threshold  <=>  1 - distance >= threshold  <=>  distance <= 1 - threshold
            max_distance = 1.0 - similarity_threshold
            query = query.filter(distance_col <= max_distance)

        # Bộ lọc metadata
        for column, value in (
            (Listing.region_id, city_id),
            (Listing.district_id, district_id),
            (Listing.ward_id, ward_id),
            (Listing.room_type_id, room_type_id),
        ):
            if value is not None:
                query = query.filter(column == value)

        if min_price is not None:
            query = query.filter(Listing.price_vnd >= min_price)
        if max_price is not None:
            query = query.filter(Listing.price_vnd <= max_price)

        rows = query.order_by(distance_col.asc()).limit(limit).all()

        results = []
        for listing, dist in rows:
            dist_val = float(dist)
            # cosine_distance thuộc [0, 2] -> similarity_score = 1 - distance
            # Giới hạn similarity trong khoảng [0.0, 1.0] cho an toàn
            similarity_score = max(0.0, min(1.0, 1.0 - dist_val))

            results.append({
                "listing": listing,
                "distance": round(dist_val, 4),
                "similarity_score": round(similarity_score, 4),
            })

        return results
