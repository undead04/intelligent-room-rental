from typing import Optional, Any
import math
import re
import unicodedata
from sqlalchemy import Float, case, cast, func, or_, union
from sqlalchemy.orm import Query, Session, joinedload

from app.models.embedding import ListingEmbedding
from app.models.listing import Listing

RRF_K: float = 60.0
DEFAULT_HYBRID_ALPHA: float = 0.7

def _active_listing_filter():
    """Bộ lọc tin đăng công khai còn hiệu lực (active và chưa bị gỡ)."""
    return (Listing.is_active == True) & (Listing.status.is_(None) | (func.lower(Listing.status) == "active"))


def _strip_accents(text: str) -> str:
    """Khử dấu tiếng Việt (kể cả đ/Đ -> d/D) để khớp với hàm PostgreSQL f_unaccent."""
    s = (text or "").replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


_FTS_STOPWORDS = {
    "tim", "giup", "toi", "minh", "em", "cho", "hoi", "o", "tai", "quanh", "gan",
    "khu", "vuc", "duoi", "tren", "tam", "khoang", "tu", "den", "gia", "trieu",
    "tr", "vnd", "nhe", "a", "voi", "co", "va", "can", "muon", "thue",
}

ROOM_TYPE_CODE_TO_ID: dict[str, int] = {
    "ROOM": 1,
    "STUDIO": 2,
    "APARTMENT": 3,
    "SLEEPBOX": 4,
    "WHOLE_HOUSE": 5,
}


def _build_or_tsquery_string(query_text: str) -> str:
    """Chuyển câu truy vấn tự nhiên thành chuỗi OR-tsquery không dấu cho PostgreSQL simple + f_unaccent.
    Giúp Sparse Full-Text Search (30% trọng số Hybrid) khớp cả truy vấn có dấu lẫn không dấu
    ngay cả khi câu hỏi chứa các từ hội thoại ('tìm', 'dưới', 'quanh',...).
    """
    normalized = _strip_accents((query_text or "").lower())
    tokens = re.findall(r"\w+", normalized, flags=re.UNICODE)
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

    @staticmethod
    def _apply_numeric_filters(
        query: Query,
        *,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_area: Optional[float] = None,
        max_area: Optional[float] = None,
        min_bedrooms: Optional[int] = None,
        min_bathrooms: Optional[int] = None,
    ) -> Query:
        """Áp dụng thống nhất các bộ lọc khoảng giá, diện tích và số phòng."""
        if min_price is not None:
            query = query.filter(Listing.price_vnd >= min_price)
        if max_price is not None:
            query = query.filter(Listing.price_vnd <= max_price)
        if min_area is not None:
            query = query.filter(Listing.area_m2 >= min_area)
        if max_area is not None:
            query = query.filter(Listing.area_m2 <= max_area)
        if min_bedrooms is not None:
            query = query.filter(Listing.bedrooms >= min_bedrooms)
        if min_bathrooms is not None:
            query = query.filter(Listing.bathrooms >= min_bathrooms)
        return query

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
        min_bedrooms: Optional[int] = None,
        min_bathrooms: Optional[int] = None,
        include_inactive: bool = False,
    ) -> Query:
        query = self.base_query()
        if not include_inactive:
            query = query.filter(_active_listing_filter())
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
        return self._apply_numeric_filters(
            query,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
            min_bedrooms=min_bedrooms,
            min_bathrooms=min_bathrooms,
        )

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
        min_bedrooms: Optional[int] = None,
        min_bathrooms: Optional[int] = None,
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
            min_bedrooms=min_bedrooms,
            min_bathrooms=min_bathrooms,
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
        min_bedrooms: Optional[int] = None,
        min_bathrooms: Optional[int] = None,
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
            min_bedrooms=min_bedrooms,
            min_bathrooms=min_bathrooms,
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
        ).filter(*filters).filter(_active_listing_filter()).one()

    def price_aggregates(self, filters: list) -> tuple[int, Optional[float], Optional[float], Optional[float]]:
        row = self.db.query(
            func.count(Listing.id),
            func.avg(Listing.price_vnd),
            func.min(Listing.price_vnd),
            func.max(Listing.price_vnd),
        ).filter(*filters).filter(_active_listing_filter()).one()
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
        room_type: Optional[str | int | list[str | int]] = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_area: float | None = None,
        max_area: float | None = None,
        min_bedrooms: int | None = None,
        min_bathrooms: int | None = None,
        limit: int = 50,
        alpha: float = DEFAULT_HYBRID_ALPHA,
        model_name: Optional[str] = None,
        lat: float | None = None,
        lng: float | None = None,
        max_distance_km: float | None = None,
        amenities: list[Any] | None = None,
        excluded_room_types: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Tìm kiếm tin đăng kết hợp Hybrid Search (Dense pgvector + Sparse FTS không dấu) qua RRF & Multi-source Union.

        - Dense (alpha=0.7): Cosine embedding hiểu ngữ nghĩa sâu
        - Sparse (1-alpha=0.3): ts_rank_cd với public.f_unaccent trên (title, address_raw, description) khớp cả không dấu
        - RRF (k=60): Gộp thứ hạng Dense + Sparse ổn định thang điểm
        - Multi-source Pool (khi limit >= 100): Dự phòng slot cho Top vị trí gần nhất & Top price_score trước MCDM Rerank.
        """
        distance_col = ListingEmbedding.vector.cosine_distance(query_vector).label("distance")

        clean_query = _strip_accents((query_text or "").strip())
        text_content = func.public.f_unaccent(
            func.coalesce(Listing.title, "")
            + " "
            + func.coalesce(Listing.address_raw, "")
            + " "
            + func.coalesce(Listing.description, "")
        )
        ts_vector = func.to_tsvector("simple", text_content)
        or_query_str = _build_or_tsquery_string(query_text or "")
        if or_query_str:
            ts_query = func.to_tsquery("simple", or_query_str)
        else:
            ts_query = func.plainto_tsquery("simple", clean_query)

        sparse_score_col = func.ts_rank_cd(ts_vector, ts_query).label("sparse_score")
        has_fts_query = bool(or_query_str or clean_query)

        # Lọc cứng dùng chung cho toàn bộ nhánh ứng viên
        filter_q = (
            self.db.query(Listing.id)
            .join(ListingEmbedding, Listing.id == ListingEmbedding.listing_id)
            .filter(_active_listing_filter())
        )
        if model_name:
            filter_q = filter_q.filter(ListingEmbedding.model_name == model_name)
        if city_id is not None:
            filter_q = filter_q.filter(Listing.region_id == city_id)
        if district_id is not None:
            filter_q = filter_q.filter(Listing.district_id == district_id)
        if ward_id is not None:
            filter_q = filter_q.filter(Listing.ward_id == ward_id)

        def _resolve_room_type_ids(raw_items: Any) -> set[int]:
            items = list(raw_items) if isinstance(raw_items, (list, tuple, set)) else ([raw_items] if raw_items is not None else [])
            ids: set[int] = set()
            for item in items:
                if isinstance(item, bool):
                    continue
                if isinstance(item, int):
                    if 1 <= item <= 5:
                        ids.add(item)
                    continue
                clean = item.value if hasattr(item, "value") else str(item).strip().upper()
                if clean == "BOARDING_HOUSE":
                    clean = "ROOM"
                if clean.isdigit() and 1 <= int(clean) <= 5:
                    ids.add(int(clean))
                elif clean in ROOM_TYPE_CODE_TO_ID:
                    ids.add(ROOM_TYPE_CODE_TO_ID[clean])
            return ids

        allowed_ids = _resolve_room_type_ids(room_type)
        if allowed_ids:
            filter_q = filter_q.filter(Listing.room_type_id.in_(list(allowed_ids)))

        excluded_ids = _resolve_room_type_ids(excluded_room_types)
        if excluded_ids:
            filter_q = filter_q.filter(Listing.room_type_id.notin_(excluded_ids))

        filter_q = self._apply_numeric_filters(
            filter_q,
            min_price=min_price,
            max_price=max_price,
            min_area=min_area,
            max_area=max_area,
            min_bedrooms=min_bedrooms,
            min_bathrooms=min_bathrooms,
        )

        haversine_expr = None
        if lat is not None and lng is not None and max_distance_km:
            lat_delta = float(max_distance_km) / 110.574
            lng_delta = float(max_distance_km) / max(10.0, 111.320 * math.cos(math.radians(lat)))
            filter_q = filter_q.filter(
                Listing.lat.isnot(None),
                Listing.lng.isnot(None),
                Listing.lat >= lat - lat_delta,
                Listing.lat <= lat + lat_delta,
                Listing.lng >= lng - lng_delta,
                Listing.lng <= lng + lng_delta,
            )
            haversine_expr = 2.0 * 6371.0 * func.asin(
                func.sqrt(
                    func.least(
                        1.0,
                        func.pow(func.sin(func.radians(Listing.lat - lat) / 2.0), 2)
                        + func.cos(func.radians(lat))
                        * func.cos(func.radians(Listing.lat))
                        * func.pow(func.sin(func.radians(Listing.lng - lng) / 2.0), 2),
                    )
                )
            )
            filter_q = filter_q.filter(haversine_expr <= float(max_distance_km))

        if amenities:
            for am in amenities:
                clean_code = str(getattr(am, "value", am)).strip().lower()
                if clean_code == "safe_area":
                    c_safe = func.coalesce(cast(Listing.concept_scores.op("->>")("safe_area"), Float), 0.0) >= 0.5
                    c_cam = func.coalesce(cast(Listing.concept_scores.op("->>")("camera"), Float), 0.0) >= 0.5
                    c_lock = func.coalesce(cast(Listing.concept_scores.op("->>")("fingerprint_lock"), Float), 0.0) >= 0.5
                    c_guard = func.coalesce(cast(Listing.concept_scores.op("->>")("guard"), Float), 0.0) >= 0.5
                    c_score = func.coalesce(Listing.safety_score, 0.0) >= 0.7
                    filter_q = filter_q.filter(or_(c_safe, c_cam, c_lock, c_guard, c_score))
                elif clean_code == "furniture":
                    c_furn = func.coalesce(cast(Listing.concept_scores.op("->>")("furniture"), Float), 0.0) >= 0.5
                    c_code = Listing.furnishing_code.in_([1, 2])
                    filter_q = filter_q.filter(or_(c_furn, c_code))
                elif clean_code == "no_shared_landlord":
                    c_nsl = func.coalesce(cast(Listing.concept_scores.op("->>")("no_shared_landlord"), Float), 0.0) >= 0.5
                    c_free = func.coalesce(cast(Listing.concept_scores.op("->>")("free_hours"), Float), 0.0) >= 0.5
                    c_fp = func.coalesce(cast(Listing.concept_scores.op("->>")("fingerprint_lock"), Float), 0.0) >= 0.5
                    filter_q = filter_q.filter(or_(c_nsl, c_free & c_fp))
                else:
                    filter_q = filter_q.filter(
                        func.coalesce(cast(Listing.concept_scores.op("->>")(clean_code), Float), 0.0) >= 0.5
                    )

        # Lấy tập ứng viên qua CTE 2 nhánh (Dense + Sparse) + RRF + nhánh Geo/Price dự phòng
        geo_col = haversine_expr.label("geo_dist") if haversine_expr is not None else cast(0.0, Float).label("geo_dist")
        filtered_cte = (
            filter_q.with_entities(
                Listing.id.label("listing_id"),
                distance_col,
                sparse_score_col,
                func.coalesce(Listing.price_score, 0.0).label("price_score"),
                geo_col,
            )
            .cte("filtered_candidates")
        )

        branch_k = max(limit, 150)
        dense_order = (
            filtered_cte.c.distance.asc(),
            filtered_cte.c.sparse_score.desc(),
            filtered_cte.c.listing_id.asc(),
        )
        dense_top = (
            self.db.query(
                filtered_cte.c.listing_id.label("listing_id"),
                func.row_number().over(order_by=dense_order).label("dense_rank"),
            )
            .order_by(*dense_order)
            .limit(branch_k)
            .cte("dense_top")
        )

        sparse_q = self.db.query(
            filtered_cte.c.listing_id.label("listing_id"),
            func.row_number().over(order_by=filtered_cte.c.sparse_score.desc()).label("sparse_rank"),
        )
        if has_fts_query:
            sparse_q = sparse_q.filter(filtered_cte.c.sparse_score > 0.0)
        else:
            sparse_q = sparse_q.filter(cast(False, Listing.is_active.type))
        sparse_top = sparse_q.order_by(filtered_cte.c.sparse_score.desc()).limit(branch_k).cte("sparse_top")

        # Gộp điểm RRF giữa dense_top và sparse_top
        rrf_score_expr = (
            case((dense_top.c.dense_rank.isnot(None), alpha / (RRF_K + dense_top.c.dense_rank)), else_=0.0)
            + case((sparse_top.c.sparse_rank.isnot(None), (1.0 - alpha) / (RRF_K + sparse_top.c.sparse_rank)), else_=0.0)
        ).label("rrf_score")

        dense_sim_expr = func.greatest(0.0, func.least(1.0, 1.0 - filtered_cte.c.distance))
        sparse_norm_expr = func.greatest(0.0, func.least(1.0, filtered_cte.c.sparse_score * 3.0))
        hybrid_sim_expr = (alpha * dense_sim_expr + (1.0 - alpha) * sparse_norm_expr).label("hybrid_sim")

        if limit >= 100:
            # Chế độ pool cho MCDM Reranker: dành riêng slot cho RRF + vị trí gần + giá hời
            rrf_budget = max(1, int(limit * 0.6))
            geo_budget = max(1, int(limit * 0.2)) if haversine_expr is not None else 0
            price_budget = max(1, limit - rrf_budget - geo_budget)

            rrf_ids_sel = (
                self.db.query(filtered_cte.c.listing_id.label("listing_id"))
                .outerjoin(dense_top, filtered_cte.c.listing_id == dense_top.c.listing_id)
                .outerjoin(sparse_top, filtered_cte.c.listing_id == sparse_top.c.listing_id)
                .filter(or_(dense_top.c.listing_id.isnot(None), sparse_top.c.listing_id.isnot(None)))
                .order_by(rrf_score_expr.desc(), hybrid_sim_expr.desc())
                .limit(rrf_budget)
            )
            price_ids_sel = (
                self.db.query(filtered_cte.c.listing_id.label("listing_id"))
                .order_by(filtered_cte.c.price_score.desc(), hybrid_sim_expr.desc())
                .limit(price_budget)
            )
            union_parts = [rrf_ids_sel, price_ids_sel]
            if geo_budget > 0:
                geo_ids_sel = (
                    self.db.query(filtered_cte.c.listing_id.label("listing_id"))
                    .order_by(filtered_cte.c.geo_dist.asc(), filtered_cte.c.price_score.desc())
                    .limit(geo_budget)
                )
                union_parts.append(geo_ids_sel)
            pool_cte = union(*union_parts).cte("candidate_pool")
        else:
            # Caller gọi trực tiếp với limit nhỏ: lấy đúng Top-K theo RRF
            pool_cte = (
                self.db.query(filtered_cte.c.listing_id.label("listing_id"))
                .outerjoin(dense_top, filtered_cte.c.listing_id == dense_top.c.listing_id)
                .outerjoin(sparse_top, filtered_cte.c.listing_id == sparse_top.c.listing_id)
                .order_by(rrf_score_expr.desc(), hybrid_sim_expr.desc())
                .limit(limit)
                .cte("candidate_pool")
            )

        rows = (
            self.db.query(
                Listing,
                filtered_cte.c.distance,
                filtered_cte.c.sparse_score,
                rrf_score_expr,
            )
            .join(filtered_cte, Listing.id == filtered_cte.c.listing_id)
            .join(pool_cte, Listing.id == pool_cte.c.listing_id)
            .outerjoin(dense_top, Listing.id == dense_top.c.listing_id)
            .outerjoin(sparse_top, Listing.id == sparse_top.c.listing_id)
            .options(
                joinedload(Listing.city),
                joinedload(Listing.district),
                joinedload(Listing.ward),
                joinedload(Listing.room_type),
            )
            .order_by(rrf_score_expr.desc(), hybrid_sim_expr.desc())
            .all()
        )

        results = []
        for listing, dist, sparse_val, rrf_val in rows:
            dist_val = float(dist) if dist is not None else 1.0
            dense_sim = max(0.0, min(1.0, 1.0 - dist_val))
            sparse_norm = max(0.0, min(1.0, float(sparse_val or 0.0) * 3.0))
            similarity_score = alpha * dense_sim + (1.0 - alpha) * sparse_norm

            results.append(
                {
                    "listing": listing,
                    "similarity_score": round(similarity_score, 4),
                    "rrf_score": round(float(rrf_val or 0.0), 6),
                }
            )

        return results
