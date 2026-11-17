"""Kiểm thử Black-Box (4 nhóm) cho cơ chế Plan & Execute đa mệnh lệnh tuần tự trong 1 lượt."""

from __future__ import annotations

from typing import Any, Optional

from core.session_store import PersistentSessionStore
from domain.schemas import RoomItem
from intelligence.advice import Advice
from intelligence.nlu import PreferencePatch, TurnAnalysis
from tests.e2e_helpers import FakeAgent, FakeLLM, Harness, SKILL, agent_reply, nlu, raw_room
from tests.test_market_price_advisor import _MarketHarness


# ===========================================================================
# Nhóm 1: Happy Path — Các tổ hợp đa mệnh lệnh chạy trọn vẹn trong 1 lượt
# ===========================================================================
def test_multi_intent_followup_then_search_runs_followup_before_overwriting_rooms():
    old_rooms = [RoomItem.from_backend_result(raw_room(1, 2_500_000, title="Phòng cũ UIT"), rank=1)]
    new_rooms = [raw_room(10, 3_200_000, title="Phòng mới Dĩ An"), raw_room(11, 3_400_000, title="Phòng mới 2 Dĩ An")]
    good_advice = Advice(
        intro="Đã tìm được các phòng mới ở Dĩ An.",
        top_reason="Phù hợp ngân sách.",
        comparison="Top 10 rộng rãi hơn.",
        checklist=["Kiểm tra hợp đồng"],
    )

    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        task_order=["followup", "search"],
        patch=PreferencePatch(location_text="Dĩ An", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Dĩ An dưới 3.5 triệu",
    )
    llm = FakeLLM().on("TurnAnalysis", compound).on("Advice", good_advice)
    agent = FakeAgent(
        agent_reply(
            "Phòng cũ UIT có giá điện 3.500đ/kWh và nước 100k/tháng.",
            tool='{"electricity_price": "3.500đ/kWh", "water_price": "100k/tháng"}',
        )
    )
    h = Harness(llm, new_rooms, agent=agent, constrained_generation=True)
    h.session.last_rooms = old_rooms

    resp = h.turn("phòng số 1 điện nước sao, xong tìm giúp mình phòng ở Dĩ An dưới 3.5 triệu")

    assert len(agent.inputs) == 1
    # Followup phải nhìn thấy phòng cũ (nhatot_1), KHÔNG phải phòng mới Dĩ An
    followup_ctx = agent.inputs[0]["messages"][0].content
    assert "Phòng cũ UIT" in followup_ctx
    assert "Phòng mới Dĩ An" not in followup_ctx

    assert len(h.search_calls) == 1
    assert [r.id for r in resp.rooms] == ["nhatot_10", "nhatot_11"]
    assert resp.searched is True
    assert "3.500đ/kWh" in resp.text_reply
    assert "Đã tìm được các phòng mới ở Dĩ An" in resp.text_reply


def test_multi_intent_followup_then_advisory_preserves_last_rooms():
    old_rooms = [RoomItem.from_backend_result(raw_room(1, 2_500_000, title="Phòng Top 1"), rank=1)]
    compound = TurnAnalysis(
        intent="room_followup",
        referenced_room_rank=1,
        skill_slug=SKILL.slug,
    )
    llm = FakeLLM().on("TurnAnalysis", compound).on(
        "text",
        "Hợp đồng thuê trọ cần ghi rõ điều khoản hoàn trả tiền cọc khi báo trước 30 ngày.",
    )
    agent = FakeAgent(agent_reply("Phòng Top 1 đặt cọc 1 tháng tiền phòng.", tool="detail"))
    h = Harness(llm, [], agent=agent)
    h.session.last_rooms = old_rooms

    resp = h.turn("phòng đầu tiên cọc bao nhiêu, và hợp đồng cọc cần lưu ý gì?")

    assert h.search_calls == []
    assert len(agent.inputs) == 1
    assert len(h.skill_calls) == 1
    assert resp.searched is False
    assert [r.id for r in resp.rooms] == ["nhatot_1"]
    assert "đặt cọc 1 tháng" in resp.text_reply
    assert "hoàn trả tiền cọc" in resp.text_reply


def test_multi_intent_triple_followup_search_advisory_in_one_turn():
    old_rooms = [RoomItem.from_backend_result(raw_room(1, 2_400_000, title="Phòng cũ số 1"), rank=1)]
    new_rooms = [raw_room(20, 3_300_000, title="Phòng mới Thủ Đức")]
    good_advice = Advice(
        intro="Đây là phòng mới tại Thủ Đức.",
        top_reason="Đúng mức giá yêu cầu.",
        comparison="",
        checklist=["Kiểm tra khóa cửa"],
    )
    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        skill_slug=SKILL.slug,
        task_order=["followup", "search", "advisory"],
        patch=PreferencePatch(location_text="Thủ Đức", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Thủ Đức dưới 3.5 triệu",
    )
    llm = (
        FakeLLM()
        .on("TurnAnalysis", compound)
        .on("Advice", good_advice)
        .on("text", "Khi ký hợp đồng cần giữ 01 bản gốc có chữ ký đầy đủ hai bên.")
    )
    agent = FakeAgent(agent_reply("Phòng cũ số 1 giữ xe miễn phí dưới hầm.", tool="detail"))
    h = Harness(llm, new_rooms, agent=agent)
    h.session.last_rooms = old_rooms

    resp = h.turn("phòng 1 gửi xe sao, tìm phòng mới ở Thủ Đức dưới 3.5tr, tiện hỏi hợp đồng ký sao cho chắc?")

    assert len(agent.inputs) == 1
    assert len(h.search_calls) == 1
    assert len(h.skill_calls) == 1
    assert [r.id for r in resp.rooms] == ["nhatot_20"]
    assert "giữ xe miễn phí" in resp.text_reply
    assert "phòng mới tại Thủ Đức" in resp.text_reply
    assert "01 bản gốc" in resp.text_reply


def test_multi_intent_search_and_market_price_advisor_executes_both():
    analysis = TurnAnalysis(
        intent="new_search",
        skill_slug="market-price-advisor",
        patch=PreferencePatch(location_text="Gò Vấp", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Gò Vấp dưới 3.5 triệu",
    )
    advice = Advice(
        intro="Mình đã tìm giúp bạn phòng tại Gò Vấp.",
        top_reason="Giá nằm trong ngân sách 3.5 triệu.",
        comparison="",
        checklist=["Xem phòng ban ngày"],
    )
    market_reply = "Mặt bằng giá phòng trọ tại Gò Vấp trung bình khoảng 3.6 triệu/tháng dựa trên 85 tin đăng thực tế."
    llm = FakeLLM().on("TurnAnalysis", analysis).on("Advice", advice).on("text", market_reply)
    h = _MarketHarness(llm)

    resp = h.turn("tìm phòng ở Gò Vấp dưới 3.5 triệu và cho biết giá trung bình ở đó")

    assert len(h.search_calls) == 1
    assert h.stats_calls == [(79, 764, None)]
    assert "Gò Vấp" in resp.text_reply
    assert "3.6 triệu" in resp.text_reply


# ===========================================================================
# Nhóm 2: Boundary & Edge Cases
# ===========================================================================
def test_multi_intent_verify_retry_completes_before_advancing_to_advisory():
    rooms = [raw_room(1, 2_600_000), raw_room(2, 2_800_000)]
    bad_advice = Advice(intro="Chỉ có 1.2 triệu thôi siêu rẻ!", top_reason="ok", comparison="", checklist=[])
    good_advice = Advice(intro="Phòng phù hợp ngân sách.", top_reason="Gần trường.", comparison="", checklist=["Kiểm tra điện nước"])
    compound = nlu(
        "new_search",
        location_text="UIT",
        location_kind="place",
        max_price=3_500_000,
        semantic_query="phòng trọ gần UIT dưới 3.5 triệu",
    ).model_copy(update={"skill_slug": SKILL.slug})

    llm = (
        FakeLLM()
        .on("TurnAnalysis", compound)
        .on("Advice", bad_advice, good_advice)
        .on("text", "Lưu ý kiểm tra rõ điều khoản tiền cọc và chi phí phát sinh trong hợp đồng.")
    )
    h = Harness(llm, rooms)

    resp = h.turn("tìm phòng gần UIT dưới 3.5 triệu và hỏi hợp đồng cọc")

    assert llm.count("Advice") == 2  # phải retry Advice trước khi chạy advisory
    assert len(h.skill_calls) == 1
    assert "1.2 triệu" not in resp.text_reply
    assert "Phòng phù hợp ngân sách" in resp.text_reply
    assert "điều khoản tiền cọc" in resp.text_reply


def test_multi_intent_followup_with_empty_last_rooms_does_not_crash_and_runs_search():
    new_rooms = [raw_room(3, 2_900_000, title="Phòng Quận 7")]
    good_advice = Advice(intro="Đã tìm thấy phòng tại Quận 7.", top_reason="Giá hợp lý.", comparison="", checklist=[])
    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        task_order=["followup", "search"],
        patch=PreferencePatch(location_text="Quận 7", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Quận 7 dưới 3.5 triệu",
    )
    llm = FakeLLM().on("TurnAnalysis", compound).on("Advice", good_advice)
    agent = FakeAgent(agent_reply("Không gọi", tool="detail"))
    h = Harness(llm, new_rooms, agent=agent)
    h.session.last_rooms = []

    resp = h.turn("phòng 1 sao rồi, thôi tìm phòng ở Quận 7 dưới 3.5tr")

    assert agent.inputs == []
    assert len(h.search_calls) == 1
    assert [r.id for r in resp.rooms] == ["nhatot_3"]


# ===========================================================================
# Nhóm 3: State Mutation & Zero Leakage
# ===========================================================================
def test_multi_intent_search_updates_last_rooms_after_followup_step():
    old_rooms = [RoomItem.from_backend_result(raw_room(1, 2_300_000, title="Phòng cũ"), rank=1)]
    new_rooms = [raw_room(5, 3_100_000, title="Phòng mới")]
    good_advice = Advice(intro="Phòng mới hợp tiêu chí.", top_reason="Tốt.", comparison="", checklist=[])
    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        task_order=["followup", "search"],
        patch=PreferencePatch(location_text="Dĩ An", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Dĩ An dưới 3.5 triệu",
    )
    llm = FakeLLM().on("TurnAnalysis", compound).on("Advice", good_advice)
    agent = FakeAgent(agent_reply("Phòng cũ giá 2.3 triệu/tháng, giờ giấc tự do.", tool="detail"))
    h = Harness(llm, new_rooms, agent=agent)
    h.session.last_rooms = old_rooms

    h.turn("phòng 1 giờ giấc sao, và tìm phòng ở Dĩ An dưới 3.5 triệu")

    assert [r.id for r in h.session.last_rooms] == ["nhatot_5"]
    assert h.session.preferences.location_text == "Dĩ An"


# ===========================================================================
# Nhóm 4: Persistence & Integration Consistency
# ===========================================================================
def test_multi_intent_persistence_and_ordered_trace(tmp_path):
    db_path = str(tmp_path / "multi_intent.db")
    store1 = PersistentSessionStore(db_path)
    rooms = [raw_room(8, 2_800_000, title="Phòng UIT 8")]
    advice = Advice(intro="Tìm được phòng gần UIT.", top_reason="Gần trường.", comparison="", checklist=[])
    compound = nlu(
        "new_search",
        location_text="UIT",
        location_kind="place",
        max_price=3_500_000,
        semantic_query="phòng trọ gần UIT dưới 3.5 triệu",
    ).model_copy(update={"skill_slug": SKILL.slug})

    llm = FakeLLM().on("TurnAnalysis", compound).on("Advice", advice).on(
        "text", "Hợp đồng cần có điều khoản báo trước 30 ngày để nhận lại đủ tiền cọc."
    )
    h = Harness(llm, rooms)
    h.deps.sessions = store1
    from graph import build_housing_graph, run_turn
    g = build_housing_graph(h.deps)

    resp = run_turn(g, "tìm phòng gần UIT dưới 3.5 triệu và tư vấn hợp đồng đặt cọc", session_id="s-multi")
    finished_tools = [e.get("tool") for e in resp.trace_events if e.get("type") == "tool_finished"]
    assert "search_rooms" in finished_tools
    assert "consult_housing_skill" in finished_tools
    assert finished_tools.index("search_rooms") < finished_tools.index("consult_housing_skill")

    store2 = PersistentSessionStore(db_path)
    reloaded = store2.get_or_create_session("s-multi")
    assert reloaded.preferences.location_text == "UIT"
    assert reloaded.preferences.max_price == 3_500_000
    assert [r.id for r in reloaded.last_rooms] == ["nhatot_8"]


# ===========================================================================
# Nhóm 5: Đảo chiều search -> followup (kể cả từ lượt đầu chưa có last_rooms)
# ===========================================================================
def test_multi_intent_search_then_followup_on_turn_1_with_empty_last_rooms():
    new_rooms = [raw_room(10, 3_200_000, title="Phòng mới Dĩ An"), raw_room(11, 3_400_000, title="Phòng 2 Dĩ An")]
    good_advice = Advice(
        intro="Đã tìm được 2 phòng ở Dĩ An.",
        top_reason="Phòng mới Dĩ An đạt điểm cao nhất.",
        comparison="Rộng rãi và giá tốt hơn.",
        checklist=["Kiểm tra đồng hồ điện"],
    )
    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        task_order=["search", "followup"],
        patch=PreferencePatch(location_text="Dĩ An", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Dĩ An dưới 3.5 triệu",
    )
    llm = FakeLLM().on("TurnAnalysis", compound).on("Advice", good_advice)
    agent = FakeAgent(
        agent_reply(
            "Phòng mới Dĩ An có giá điện 3.800đ/kWh và nước 100k/tháng.",
            tool='{"electricity_price": "3.800đ/kWh", "water_price": "100k/tháng"}',
        )
    )
    h = Harness(llm, new_rooms, agent=agent)
    h.session.last_rooms = []

    resp = h.turn("tìm phòng ở Dĩ An dưới 3.5 triệu rồi xem chi tiết phòng đầu tiên điện nước sao")

    assert len(h.search_calls) == 1
    assert len(agent.inputs) == 1
    followup_ctx = agent.inputs[0]["messages"][0].content
    assert "Phòng mới Dĩ An" in followup_ctx
    assert [r.id for r in resp.rooms] == ["nhatot_10", "nhatot_11"]
    assert resp.searched is True
    assert "Đã tìm được 2 phòng ở Dĩ An" in resp.text_reply
    assert "3.800đ/kWh" in resp.text_reply


def test_multi_intent_search_then_followup_inspects_new_room_not_old_room():
    old_rooms = [RoomItem.from_backend_result(raw_room(1, 2_300_000, title="Phòng cũ UIT"), rank=1)]
    new_rooms = [raw_room(20, 3_300_000, title="Phòng mới Thủ Đức")]
    good_advice = Advice(
        intro="Đã chuyển sang tìm phòng mới tại Thủ Đức.",
        top_reason="Gần trung tâm.",
        comparison="",
        checklist=["Xem hợp đồng"],
    )
    compound = TurnAnalysis(
        intent="refine_search",
        referenced_room_rank=1,
        patch=PreferencePatch(location_text="Thủ Đức", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Thủ Đức dưới 3.5 triệu",
    )
    llm = FakeLLM().on("TurnAnalysis", compound).on("Advice", good_advice)
    agent = FakeAgent(
        agent_reply(
            "Phòng mới Thủ Đức có điện 3.500đ/kWh, nước miễn phí.",
            tool='{"electricity_price": "3.500đ/kWh", "water": "miễn phí"}',
        )
    )
    h = Harness(llm, new_rooms, agent=agent)
    h.session.last_rooms = old_rooms
    h.session.focused_room_rank = 1

    resp = h.turn("đổi sang Thủ Đức dưới 3.5 triệu rồi kiểm tra phòng top 1 điện nước sao")

    assert len(h.search_calls) == 1
    assert len(agent.inputs) == 1
    followup_ctx = agent.inputs[0]["messages"][0].content
    assert "Phòng mới Thủ Đức" in followup_ctx
    assert "Phòng cũ UIT" not in followup_ctx
    assert [r.id for r in resp.rooms] == ["nhatot_20"]
    assert "3.500đ/kWh" in resp.text_reply


def test_multi_intent_search_then_followup_then_advisory_in_one_turn():
    new_rooms = [raw_room(30, 3_100_000, title="Phòng Thủ Đức Top 1")]
    good_advice = Advice(
        intro="Đã tìm được phòng tại Thủ Đức.",
        top_reason="Phù hợp ngân sách.",
        comparison="",
        checklist=["Kiểm tra giấy tờ"],
    )
    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        skill_slug=SKILL.slug,
        task_order=["search", "followup", "advisory"],
        patch=PreferencePatch(location_text="Thủ Đức", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Thủ Đức dưới 3.5 triệu",
    )
    llm = (
        FakeLLM()
        .on("TurnAnalysis", compound)
        .on("Advice", good_advice)
        .on("text", "Hợp đồng cọc cần ghi rõ thời hạn hoàn trả tiền cọc.")
    )
    agent = FakeAgent(
        agent_reply(
            "Phòng Thủ Đức Top 1 tính điện 3.500đ/kWh.",
            tool='{"electricity_price": "3.500đ/kWh"}',
        )
    )
    h = Harness(llm, new_rooms, agent=agent)

    resp = h.turn("tìm phòng ở Thủ Đức dưới 3.5 triệu, xong xem phòng top 1 điện sao với tư vấn hợp đồng cọc")

    assert len(h.search_calls) == 1
    assert len(agent.inputs) == 1
    assert len(h.skill_calls) == 1
    assert "Đã tìm được phòng tại Thủ Đức" in resp.text_reply
    assert "3.500đ/kWh" in resp.text_reply
    assert "hoàn trả tiền cọc" in resp.text_reply


def test_multi_intent_search_then_followup_with_zero_rooms_skips_followup_cleanly():
    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        patch=PreferencePatch(location_text="Dĩ An", location_kind="admin", max_price=500_000),
        semantic_query="phòng trọ Dĩ An dưới 500k",
    )
    llm = FakeLLM().on("TurnAnalysis", compound)
    agent = FakeAgent(agent_reply("Không được gọi khi 0 phòng", tool="detail"))
    h = Harness(llm, [], agent=agent)

    resp = h.turn("tìm phòng ở Dĩ An dưới 500k rồi xem chi tiết phòng top 1")

    assert len(h.search_calls) == 1
    assert agent.inputs == []
    assert resp.rooms == []
    assert resp.searched is True


# ===========================================================================
# Nhóm 6: Tự do hoán vị kể cả advisory đứng đầu / đứng giữa
# ===========================================================================
def test_multi_intent_advisory_then_search_runs_advisory_first_and_preserves_order():
    rooms = [raw_room(40, 3_200_000, title="Phòng Dĩ An Mới")]
    good_advice = Advice(
        intro="Đã tìm được phòng ở Dĩ An.",
        top_reason="Giá phù hợp.",
        comparison="",
        checklist=["Kiểm tra an ninh"],
    )
    compound = TurnAnalysis(
        intent="skill_advice",
        skill_slug=SKILL.slug,
        patch=PreferencePatch(location_text="Dĩ An", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Dĩ An dưới 3.5 triệu",
    )
    llm = (
        FakeLLM()
        .on("TurnAnalysis", compound)
        .on("text", "Lưu ý kiểm tra rõ thời hạn hoàn trả tiền cọc trong hợp đồng.")
        .on("Advice", good_advice)
    )
    h = Harness(llm, rooms)

    resp = h.turn("tư vấn hợp đồng đặt cọc trước rồi tìm phòng ở Dĩ An dưới 3.5 triệu")

    finished_tools = [e.get("tool") for e in resp.trace_events if e.get("type") == "tool_finished"]
    assert "consult_housing_skill" in finished_tools
    assert "search_rooms" in finished_tools
    assert finished_tools.index("consult_housing_skill") < finished_tools.index("search_rooms")

    adv_pos = resp.text_reply.find("thời hạn hoàn trả tiền cọc")
    search_pos = resp.text_reply.find("Đã tìm được phòng ở Dĩ An")
    assert adv_pos != -1 and search_pos != -1 and adv_pos < search_pos
    assert [r.id for r in resp.rooms] == ["nhatot_40"]
    assert resp.searched is True


def test_multi_intent_advisory_then_followup_preserves_last_rooms_and_order():
    old_rooms = [RoomItem.from_backend_result(raw_room(1, 2_400_000, title="Phòng cũ Top 1"), rank=1)]
    compound = TurnAnalysis(
        intent="skill_advice",
        skill_slug=SKILL.slug,
        referenced_room_rank=1,
    )
    llm = (
        FakeLLM()
        .on("TurnAnalysis", compound)
        .on("text", "Hợp đồng thuê nên có phụ lục bàn giao tài sản.")
    )
    agent = FakeAgent(
        agent_reply(
            "Phòng cũ Top 1 giá 2.4 triệu/tháng và điện 3.500đ/kWh.",
            tool='{"electricity_price": "3.500đ/kWh"}',
        )
    )
    h = Harness(llm, [], agent=agent)
    h.session.last_rooms = old_rooms

    resp = h.turn("tư vấn hợp đồng giúp mình, sẵn kiểm tra phòng số 1 điện nước sao")

    assert h.search_calls == []
    assert len(h.skill_calls) == 1
    assert len(agent.inputs) == 1
    assert "Phòng cũ Top 1" in agent.inputs[0]["messages"][0].content
    adv_pos = resp.text_reply.find("phụ lục bàn giao tài sản")
    fol_pos = resp.text_reply.find("3.500đ/kWh")
    assert adv_pos != -1 and fol_pos != -1 and adv_pos < fol_pos
    assert [r.id for r in resp.rooms] == ["nhatot_1"]
    assert resp.searched is False


def test_multi_intent_search_then_advisory_then_followup_preserves_new_rooms():
    new_rooms = [raw_room(50, 3_000_000, title="Phòng Thủ Đức Mới Nhất")]
    good_advice = Advice(
        intro="Đã tìm thấy phòng tại Thủ Đức.",
        top_reason="Giá tốt.",
        comparison="",
        checklist=["Kiểm tra khóa cửa"],
    )
    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        skill_slug=SKILL.slug,
        task_order=["search", "advisory", "followup"],
        patch=PreferencePatch(location_text="Thủ Đức", location_kind="admin", max_price=3_500_000),
        semantic_query="phòng trọ Thủ Đức dưới 3.5 triệu",
    )
    llm = (
        FakeLLM()
        .on("TurnAnalysis", compound)
        .on("Advice", good_advice)
        .on("text", "Khi ký hợp đồng cần ghi rõ điều khoản hoàn cọc.")
    )
    agent = FakeAgent(
        agent_reply(
            "Phòng Thủ Đức Mới Nhất có điện 3.500đ/kWh và nước 100k/tháng.",
            tool='{"electricity_price": "3.500đ/kWh", "water_price": "100k/tháng"}',
        )
    )
    h = Harness(llm, new_rooms, agent=agent)

    resp = h.turn(
        "tìm phòng ở Thủ Đức dưới 3.5 triệu, tư vấn thêm hợp đồng cọc, xong xem phòng top 1 điện nước sao"
    )

    finished_tools = [e.get("tool") for e in resp.trace_events if e.get("type") == "tool_finished"]
    assert "search_rooms" in finished_tools
    assert "consult_housing_skill" in finished_tools
    assert "get_listing_detail" in finished_tools
    assert (
        finished_tools.index("search_rooms")
        < finished_tools.index("consult_housing_skill")
        < finished_tools.index("get_listing_detail")
    )
    s_pos = resp.text_reply.find("Đã tìm thấy phòng tại Thủ Đức")
    a_pos = resp.text_reply.find("điều khoản hoàn cọc")
    f_pos = resp.text_reply.find("3.500đ/kWh")
    assert s_pos != -1 and a_pos != -1 and f_pos != -1
    assert s_pos < a_pos < f_pos
    assert [r.id for r in resp.rooms] == ["nhatot_50"]


def test_multi_intent_advisory_then_vague_search_preserves_clarification():
    from graph.nodes.clarification import ClarifyReply

    compound = TurnAnalysis(
        intent="skill_advice",
        skill_slug=SKILL.slug,
        is_multi_intent=True,
        task_order=["advisory", "search"],
        patch=PreferencePatch(location_is_vague=True, vague_category="trường đại học"),
    )
    llm = (
        FakeLLM()
        .on("TurnAnalysis", compound)
        .on("text", "Hợp đồng thuê trọ cần kiểm tra kỹ tiền cọc.")
        .on("ClarifyReply", ClarifyReply(text="Bạn muốn tìm phòng gần trường đại học cụ thể nào ạ?", suggestions=["ĐH Bách Khoa", "UIT"]))
    )
    h = Harness(llm, [])

    resp = h.turn("tư vấn hợp đồng cọc trước rồi tìm phòng gần trường đại học")

    assert h.search_calls == []
    assert len(h.skill_calls) == 1
    assert resp.need_clarification is True
    assert "kiểm tra kỹ tiền cọc" in resp.text_reply
    assert "trường đại học cụ thể nào" in resp.text_reply
    assert resp.follow_up_questions == ["ĐH Bách Khoa", "UIT"]


def test_search_then_followup_with_unconstrained_agent_calls_detail_only_once(monkeypatch):
    """Hồi quy run_ae681851333f: với constrained_generation=False, bước 1 (search) KHÔNG được prefetch get_listing_detail hay gắn <focus>; chỉ bước 2 (followup) gọi đúng 1 lần."""
    import graph.nodes.decision as dec_mod

    detail_calls: list[str] = []
    monkeypatch.setattr(
        dec_mod,
        "fetch_listing_detail",
        lambda lid: detail_calls.append(lid) or {"ok": True, "data": {"id": lid, "title": "Studio Thủ Đức", "description": "Có bảo vệ 24/7, có thang máy."}},
    )

    new_rooms = [raw_room(10, 4_200_000, room_type="STUDIO", title="Studio Thủ Đức")]
    compound = TurnAnalysis(
        intent="new_search",
        referenced_room_rank=1,
        is_multi_intent=True,
        task_order=["search", "followup"],
        patch=PreferencePatch(location_text="Thủ Đức", location_kind="admin", max_price=5_000_000, allowed_room_types=["STUDIO"]),
        semantic_query="căn hộ studio gần Thủ Đức dưới 5 triệu",
    )
    llm = FakeLLM().on("TurnAnalysis", compound)
    agent = FakeAgent(
        agent_reply("Đã tìm thấy căn hộ Studio Thủ Đức giá 4.2 triệu/tháng phù hợp ngân sách."),
        agent_reply("Phòng Top 1 (Studio Thủ Đức) có bảo vệ 24/7 và thang máy theo mô tả chi tiết."),
    )
    h = Harness(llm, new_rooms, agent=agent, constrained_generation=False)

    resp = h.turn("Tìm căn hộ studio gần Thủ Đức dưới 5 triệu, rồi kiểm tra giúp phòng đầu tiên có bảo vệ 24/7 và thang máy không")

    # get_listing_detail chỉ được gọi ĐÚNG 1 lần ở bước 2 (followup), không bị gọi 2 lần như run_ae681851333f
    assert detail_calls == ["nhatot_10"]
    assert len(agent.inputs) == 2
    step1_ctx = agent.inputs[0]["messages"][0].content
    step1_query = agent.inputs[0]["messages"][-1].content
    assert "<prefetched_listing_detail>" not in step1_ctx
    assert "<focus>" not in step1_query
    step2_ctx = agent.inputs[1]["messages"][0].content
    step2_query = agent.inputs[1]["messages"][-1].content
    assert "<prefetched_listing_detail>" in step2_ctx
    assert "<focus>" in step2_query
    verifier_spans = [e for e in resp.trace_events if e.get("type") == "verifier_decision"]
    assert len(verifier_spans) == 2
    assert all(sp["passed"] is True for sp in verifier_spans)


def test_dod_verifier_flags_premature_detail_on_search_and_duplicate_detail_calls():
    """DoD Verifier phát hiện và chặn nếu bước search gọi sớm get_listing_detail hoặc bước followup gọi lặp cùng 1 phòng."""
    from domain.schemas import UserPreferenceState
    from safety.dod_verifier import derive_dod_spec, verify_dod

    spec_search = derive_dod_spec(
        "new_search",
        UserPreferenceState(location_text="Thủ Đức"),
        user_message="Tìm phòng Thủ Đức",
        forbid_detail_on_search_step=True,
    )
    rep_search = verify_dod(
        spec_search,
        candidate_answer="Đã tìm được phòng Thủ Đức.",
        direct_system_state={"rooms": []},
        trace_spans=[
            {"type": "tool_finished", "tool": "search_rooms", "status": "ok", "args": {"query": "Thủ Đức"}},
            {"type": "tool_finished", "tool": "get_listing_detail", "status": "ok", "args": {"listing_id": "nhatot_10"}},
        ],
        enforce_trace=True,
    )
    assert rep_search.passed is False
    assert any(f["condition_id"] == "cond_no_premature_detail_on_search" for f in rep_search.failures)

    spec_dup = derive_dod_spec(
        "room_followup",
        UserPreferenceState(),
        user_message="Phòng 1 có bảo vệ không?",
        forbid_duplicate_detail_call=True,
    )
    rep_dup = verify_dod(
        spec_dup,
        candidate_answer="Phòng 1 có bảo vệ 24/7.",
        direct_system_state={"rooms": []},
        trace_spans=[
            {"type": "tool_finished", "tool": "get_listing_detail", "status": "ok", "args": {"listing_id": "nhatot_10"}},
            {"type": "tool_finished", "tool": "get_listing_detail", "status": "ok", "args": {"listing_id": "nhatot_10"}},
        ],
        enforce_trace=True,
    )
    assert rep_dup.passed is False
    assert any(f["condition_id"] == "cond_no_duplicate_detail_call" for f in rep_dup.failures)
