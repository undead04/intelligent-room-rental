from types import SimpleNamespace

from domain.schemas import RoomItem, UserPreferenceState


class FakeStructured:
    def __init__(self, result):
        self.result, self.calls = result, []

    def invoke(self, messages):
        self.calls.append(messages)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeModel:
    def __init__(self, result):
        self.structured = FakeStructured(result)
        self.kwargs = None

    def with_structured_output(self, schema, **kwargs):
        self.schema, self.kwargs = schema, kwargs
        return self.structured


def make_session(*, pref=None, rooms=None, hitl_streak=0, proposed_budget=None, messages=None, multipliers=None):
    return SimpleNamespace(
        preferences=pref or UserPreferenceState(),
        multipliers=multipliers or {"price": 1.0, "location": 1.0, "safety": 1.0, "amenity": 1.0, "semantic": 1.0},
        last_rooms=rooms or [], hitl_streak=hitl_streak, proposed_budget=proposed_budget, messages=messages or [],
    )


def room(i, rt=None, title=None, price="2.5 triệu/tháng"):
    return RoomItem(id=f"nhatot_{i}", rank=i, title=title or f"Phòng {i}", price=price, priceNum=2_500_000, room_type=rt)


SKILLS = {"rental-contract-advisor": SimpleNamespace(slug="rental-contract-advisor", name="X", description="Tư vấn hợp đồng thuê trọ, tiền cọc", follow_ups=[])}
