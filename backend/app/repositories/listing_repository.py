from typing import Optional,Any

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
            query_vector: list[float],  # Đảm bảo nhận vào list[float]
            city_id: int | None = None,
            district_id: int | None = None,
            ward_id: int | None = None,
            min_price: float | None = None,
            max_price: float | None = None,
            min_area: float | None = None,
            max_area: float | None = None,
            limit: int = 50,
        ) -> list[dict[str, Any]]:
            """Tìm kiếm tin đăng theo vector embedding bằng khoảng cách Cosine."""
            # Biến đổi cosine distance sang column expression
            distance_col = ListingEmbedding.vector.cosine_distance(
                query_vector
            ).label("distance")

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

            # Filters
            if city_id is not None:
                query = query.filter(Listing.region_id == city_id)
            if district_id is not None:
                query = query.filter(Listing.district_id == district_id)
            if ward_id is not None:
                query = query.filter(Listing.ward_id == ward_id)

            if min_price is not None:
                query = query.filter(Listing.price_vnd >= min_price)
            if max_price is not None:
                query = query.filter(Listing.price_vnd <= max_price)

            if min_area is not None:
                query = query.filter(Listing.area_m2 >= min_area)
            if max_area is not None:
                query = query.filter(Listing.area_m2 <= max_area)

            rows = query.order_by(distance_col.asc()).limit(limit).all()

            results = []
            for listing, dist in rows:
                dist_val = float(dist) if dist is not None else 1.0
                # Normalize Cosine Distance [0..2] -> Similarity [0..1]
                similarity_score = max(0.0, min(1.0, 1.0 - dist_val))

                results.append(
                    {
                        "listing": listing,
                        "similarity_score": similarity_score,
                    }
                )

            return results
