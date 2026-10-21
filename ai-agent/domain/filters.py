"""Bộ lọc kết quả sau retrieval (loại trừ loại phòng người dùng đã từ chối)."""

from __future__ import annotations

from typing import Iterable, Sequence

from domain.enums import RoomType
from domain.schemas import RoomItem, rank_text


def renumber(rooms: Sequence[RoomItem]) -> list[RoomItem]:
    """Đánh lại hạng 1..n (trả bản sao, không sửa danh sách gốc)."""
    return [r.model_copy(update={"rank": i, "rankText": rank_text(i)}) for i, r in enumerate(rooms, 1)]


def drop_excluded_room_types(rooms: Sequence[RoomItem], excluded: Iterable[RoomType]) -> list[RoomItem]:
    """Bỏ phòng thuộc loại bị loại trừ rồi ĐÁNH LẠI hạng (1..n).

    Phòng không rõ loại (room_type=None) được GIỮ: không có căn cứ để loại.
    Gợi ý: khi excluded khác rỗng, gọi search_rooms với limit lớn hơn (vd 10) rồi cắt còn 5 sau khi lọc.
    """
    ex = set(excluded or [])
    kept = [r for r in rooms if r.room_type is None or r.room_type not in ex] if ex else list(rooms)
    return renumber(kept)
