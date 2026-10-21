from domain.enums import RoomType
from domain.filters import drop_excluded_room_types
from domain.schemas import RoomItem
from tests.helpers import room


def test_drop_and_renumber():
    rooms = [room(1, RoomType.SLEEPBOX), room(2, RoomType.ROOM), room(3, None), room(4, RoomType.STUDIO)]
    out = drop_excluded_room_types(rooms, [RoomType.SLEEPBOX, RoomType.STUDIO])
    assert [r.id for r in out] == ["nhatot_2", "nhatot_3"]
    assert [r.rank for r in out] == [1, 2] and out[0].rankText == "Top 1 - Tối ưu nhất"
    assert rooms[0].rank == 1 and rooms[1].rank == 2                    # không sửa danh sách gốc


def test_unknown_room_type_is_kept_and_no_exclusion_noop():
    rooms = [room(1, None), room(2, RoomType.ROOM)]
    assert len(drop_excluded_room_types(rooms, [RoomType.SLEEPBOX])) == 2
    assert [r.id for r in drop_excluded_room_types(rooms, [])] == ["nhatot_1", "nhatot_2"]
    assert drop_excluded_room_types([], [RoomType.ROOM]) == []


def test_room_type_parsed_from_backend_listing():
    for lt, expected in [({"id": 4, "name": "x"}, RoomType.SLEEPBOX), ({"name": "Ký túc xá"}, RoomType.SLEEPBOX),
                         ("STUDIO", RoomType.STUDIO), (None, None), ({"name": "không rõ"}, None)]:
        r = RoomItem.from_backend_result({"listing": {"id": "a", "room_type": lt}})
        assert r.room_type is expected, lt
