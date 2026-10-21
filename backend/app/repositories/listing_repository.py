from typing import Optional, Any
import re
from sqlalchemy import Float, case, cast, func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.models.embedding import ListingEmbedding
from app.models.listing import Listing

_FTS_STOPWORDS = {
    "tìm", "tim", "giúp", "giup", "tôi", "toi", "mình", "minh", "em", "cho",
    "hỏi", "hoi", "ở", "o", "tại", "tai", "quanh", "gần", "gan", "khu", "vực",
    "vuc", "dưới", "duoi", "trên", "tren", "tầm", "tam", "khoảng", "khoang",
    "từ", "tu", "đến", "den", "giá", "gia", "triệu", "trieu", "tr", "vnd",
    "nhé", "nhe", "ạ", "a", "với", "voi", "có", "co", "và", "va", "cần", "can",
    "muốn", "muon", "thuê", "thue",
}

ROOM_TYPE_CODE_TO_ID: dict[str, int] = {
    "ROOM": 1,
    "STUDIO": 2,
    "APARTMENT": 3,
    "SLEEPBOX": 4,
    "WHOLE_HOUSE": 5,
}


def _build_or_tsquery_string(query_text: str) -> str:
    """Chuyển câu truy vấn tự nhiên thành chuỗi OR-tsquery an toàn cho PostgreSQL simple dictionary.
    Giúp Sparse Full-Text Search (30% trọng số Hybrid) vẫn chấm điểm khớp từ khóa địa danh/tiện ích
    ngay cả khi câu hỏi chứa các từ hội thoại ('tìm', 'dưới', 'quanh',...).
    """
    tokens = re.findall(r"\w+", (query_text or "").lower(), flags=re.UNICODE)
    valid_tokens: list[str] = []
    for tok in tokens:
        if len(tok) < 2 or tok in _FTS_STOPWORDS or tok.isdigit():
            continue
        if tok not in valid_tokens:
            valid_tokens.append(tok)
    return " | ".join(valid_tokens)


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

    def price_aggregates(self, filters: list) -> tuple[int, Optional[float], Optional[float], Optional[float]]:
        row = self.db.query(
            func.count(Listing.id),
            func.avg(Listing.price_vnd),
            func.min(Listing.price_vnd),
            func.max(Listing.price_vnd),
        ).filter(*filters).one()
        return row[0], row[1], row[2], row[3]

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
        query_text: Optional[str] = None,
        city_id: int | None = None,
        district_id: int | None = None,
        ward_id: int | None = None,
        room_type_id: int | None = None,
        room_type: Optional[str] = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_area: float | None = None,
        max_area: float | None = None,
        limit: int = 50,
        alpha: float = 0.6,
        model_name: Optional[str] = None,
        lat: float | None = None,
        lng: float | None = None,
        max_distance_km: float | None = None,
        amenities: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Tìm kiếm tin đăng kết hợp Hybrid Search (Dense pgvector + Sparse PostgreSQL Full-Text Search).

        - Dense: Khoảng cách Cosine embedding hiểu ngữ nghĩa sâu
        - Sparse: ts_rank_cd trên (title, address_raw, description) bắt chính xác tên đường, địa danh, từ khóa
        - Linear Fusion: alpha * dense + (1 - alpha) * sparse
        """

        # Biến đổi cosine distance sang column expression
        distance_col = ListingEmbedding.vector.cosine_distance(
            query_vector
        ).label("distance")

        clean_query = (query_text or "").strip()
        text_content = func.concat_ws(
            " ",
            func.coalesce(Listing.title, ""),
            func.coalesce(Listing.address_raw, ""),
            func.coalesce(Listing.description, ""),
        )
        ts_vector = func.to_tsvector("simple", text_content)
        or_query_str = _build_or_tsquery_string(clean_query)
        if or_query_str:
            ts_query = func.to_tsquery("simple", or_query_str)
        else:
            ts_query = func.plainto_tsquery("simple", clean_query)
        
        sparse_score_col = func.ts_rank_cd(ts_vector, ts_query).label("sparse_score")

        # Chuẩn hoá Dense similarity: [0..1]
        dense_sim = func.greatest(0.0, func.least(1.0, 1.0 - distance_col))
        # Chuẩn hoá Sparse rank: clamp(rank * 3.0, 0, 1)
        sparse_norm = func.greatest(0.0, func.least(1.0, sparse_score_col * 3.0))
        # Điểm tổng hợp Hybrid Fusion
        hybrid_score_col = (alpha * dense_sim + (1.0 - alpha) * sparse_norm).label("hybrid_score")

        query = (
            self.db.query(Listing, distance_col, sparse_score_col)
            .join(ListingEmbedding, Listing.id == ListingEmbedding.listing_id)
            .options(
                joinedload(Listing.city),
                joinedload(Listing.district),
                joinedload(Listing.ward),
                joinedload(Listing.room_type),
            )
        )

        # Filters
        if model_name:
            query = query.filter(ListingEmbedding.model_name == model_name)
        if city_id is not None:
            query = query.filter(Listing.region_id == city_id)
        if district_id is not None:
            query = query.filter(Listing.district_id == district_id)
        if ward_id is not None:
            query = query.filter(Listing.ward_id == ward_id)

        # Cách 1: Lọc an toàn bằng room_type_id (tránh so sánh relationship với str)
        effective_room_type_id = room_type_id
        if effective_room_type_id is None and room_type is not None:
            clean = room_type.value if hasattr(room_type, "value") else str(room_type).strip().upper()
            if clean.isdigit():
                effective_room_type_id = int(clean)
            elif clean in ROOM_TYPE_CODE_TO_ID:
                effective_room_type_id = ROOM_TYPE_CODE_TO_ID[clean]

        if effective_room_type_id is not None:
            query = query.filter(Listing.room_type_id == effective_room_type_id)

        if min_price is not None:
            query = query.filter(Listing.price_vnd >= min_price)
        if max_price is not None:
            query = query.filter(Listing.price_vnd <= max_price)

        if min_area is not None:
            query = query.filter(Listing.area_m2 >= min_area)
        if max_area is not None:
            query = query.filter(Listing.area_m2 <= max_area)

        # Lọc không gian theo bán kính (bounding box) quanh toạ độ mục tiêu
        if lat is not None and lng is not None and max_distance_km:
            lat_delta = max_distance_km / 111.0
            lng_delta = max_distance_km / 105.0
            query = query.filter(
                Listing.lat.isnot(None),
                Listing.lng.isnot(None),
                Listing.lat >= lat - lat_delta,
                Listing.lat <= lat + lat_delta,
                Listing.lng >= lng - lng_delta,
                Listing.lng <= lng + lng_delta,
            )

        # Lọc cứng tiện ích bắt buộc từ concept_scores
        if amenities:
            from app.services.reranker import _NORMALIZE_AMENITY

            for am in amenities:
                clean_code = _NORMALIZE_AMENITY(str(getattr(am, "value", am)))
                query = query.filter(
                    func.coalesce(cast(Listing.concept_scores.op("->>")(clean_code), Float), 0.0) >= 0.5
                )

        rows = query.order_by(hybrid_score_col.desc()).limit(limit).all()

        results = []
        for row in rows:
            listing, dist, sparse_val = row
            dist_val = float(dist) if dist is not None else 1.0
            dense_sim = max(0.0, min(1.0, 1.0 - dist_val))
            sparse_norm = max(0.0, min(1.0, float(sparse_val or 0.0) * 3.0))
            similarity_score = alpha * dense_sim + (1.0 - alpha) * sparse_norm

            results.append(
                {
                    "listing": listing,
                    "similarity_score": round(similarity_score, 4),
                }
            )

        return results
