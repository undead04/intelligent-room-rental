"""Dataset 40 Benchmark Queries cho bài toán Gợi ý Phòng trọ Thông minh (Homigo).

Mỗi truy vấn đại diện cho một Persona thực tế của sinh viên và người đi làm tại TP.HCM,
đi kèm GroundTruthExpectation chứa các ràng buộc cứng (hard constraints) và tiêu chí ưu tiên
(soft priorities) để đo đạc định lượng các chỉ số Information Retrieval (IR):
- Precision@K
- MRR (Mean Reciprocal Rank)
- nDCG@K
- CSR (Constraint Satisfaction Rate)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GroundTruthExpectation:
    """Kỳ vọng chân lý (Ground Truth) của một truy vấn tìm phòng trọ.

    Được dùng làm tiêu chuẩn đánh giá mức độ thỏa mãn của các phòng trọ được đề xuất.
    """

    max_budget: Optional[float] = None
    min_budget: Optional[float] = None
    target_lat: Optional[float] = None
    target_lng: Optional[float] = None
    max_distance_km: Optional[float] = None
    target_location_name: Optional[str] = None
    required_amenities: list[str] = field(default_factory=list)
    allowed_room_types: list[str] = field(default_factory=list)
    forbidden_room_types: list[str] = field(default_factory=list)
    min_area_m2: Optional[float] = None
    ideal_priorities: dict[str, str] = field(default_factory=dict)


@dataclass
class BenchmarkQuery:
    """Một mẫu truy vấn đánh giá chuẩn (Benchmark Query)."""

    id: str
    group: str
    query: str
    persona_description: str
    expectation: GroundTruthExpectation


# ============================================================================
# BỘ DỮ LIỆU ĐÁNH GIÁ CHUẨN 40 QUERIES (BENCHMARK_QUERIES)
# ============================================================================

BENCHMARK_QUERIES: list[BenchmarkQuery] = [
    # ------------------------------------------------------------------------
    # NHÓM 1: G1_BUDGET (8 queries)
    # Trọng tâm: Sinh viên ngân sách thấp, KTX, Sleepbox, ở ghép giá 1tr-2.5tr quanh ĐHQG TP.HCM (lat 10.8700, lng 106.8031), Thủ Đức.
    # ------------------------------------------------------------------------
    BenchmarkQuery(
        id="G1_01",
        group="G1_BUDGET",
        query="Em là sinh viên năm nhất ĐHQG TP.HCM, tài chính eo hẹp tầm 1.5 triệu quay đầu, muốn tìm giường KTX hoặc sleepbox gần trường có máy lạnh.",
        persona_description="Tân sinh viên ĐHQG TP.HCM, tài chính rất hạn hẹp, cần tiết kiệm tối đa chi phí nhưng cần có điều hòa.",
        expectation=GroundTruthExpectation(
            max_budget=1_500_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=3.0,
            target_location_name="ĐHQG TP.HCM",
            required_amenities=["aircon"],
            allowed_room_types=["SLEEPBOX", "ROOM"],
            forbidden_room_types=[],
            ideal_priorities={"price": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G1_02",
        group="G1_BUDGET",
        query="Tìm phòng trọ hoặc sleepbox giá rẻ dưới 2 triệu gần làng đại học Thủ Đức, có giờ giấc tự do 24/7.",
        persona_description="Sinh viên ĐHQG hay làm thêm về muộn, cần giờ giấc tự do và giá dưới 2 triệu.",
        expectation=GroundTruthExpectation(
            max_budget=2_000_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=4.0,
            target_location_name="Làng Đại học Thủ Đức",
            required_amenities=["free_hours"],
            allowed_room_types=["SLEEPBOX", "ROOM"],
            forbidden_room_types=[],
            ideal_priorities={"price": "high", "amenity": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G1_03",
        group="G1_BUDGET",
        query="Sinh viên ngân sách từ 1 triệu đến 1.8 triệu tìm chỗ ở KTX sleepbox sạch sẽ, có máy giặt chung gần ĐHQG TP.HCM.",
        persona_description="Sinh viên cần chỗ ở sạch sẽ, có máy giặt chung để đỡ tốn thời gian giặt tay.",
        expectation=GroundTruthExpectation(
            min_budget=1_000_000.0,
            max_budget=1_800_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=3.5,
            target_location_name="ĐHQG TP.HCM",
            required_amenities=["washing_machine"],
            allowed_room_types=["SLEEPBOX", "ROOM"],
            forbidden_room_types=[],
            ideal_priorities={"price": "high", "amenity": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G1_04",
        group="G1_BUDGET",
        query="Cần tìm phòng trọ giá sinh viên dưới 2.5 triệu quanh khu vực Thủ Đức, bán kính 3km quanh ĐHQG, yêu cầu có WC riêng.",
        persona_description="Sinh viên muốn ở phòng trọ truyền thống có nhà vệ sinh riêng để đảm bảo riêng tư.",
        expectation=GroundTruthExpectation(
            max_budget=2_500_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=3.0,
            target_location_name="ĐHQG TP.HCM, Thủ Đức",
            required_amenities=["private_wc"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"price": "high", "amenity": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G1_05",
        group="G1_BUDGET",
        query="Nam sinh viên tìm chỗ ở ghép hoặc sleepbox giá dưới 1.2 triệu gần Ký túc xá khu B ĐHQG.",
        persona_description="Nam sinh viên với mức ngân sách tối thiểu, cần chỗ ngả lưng gần KTX Khu B.",
        expectation=GroundTruthExpectation(
            max_budget=1_200_000.0,
            target_lat=10.8780,
            target_lng=106.8070,
            max_distance_km=2.5,
            target_location_name="KTX Khu B ĐHQG",
            required_amenities=[],
            allowed_room_types=["SLEEPBOX", "ROOM"],
            forbidden_room_types=[],
            ideal_priorities={"price": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G1_06",
        group="G1_BUDGET",
        query="Tìm phòng trọ giá rẻ từ 1.5tr đến 2.2tr gần ĐHQG Thủ Đức, có chỗ để xe an toàn và không chung chủ.",
        persona_description="Sinh viên có xe máy, cần tìm phòng trọ không chung chủ, có chỗ để xe.",
        expectation=GroundTruthExpectation(
            min_budget=1_500_000.0,
            max_budget=2_200_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=4.0,
            target_location_name="ĐHQG Thủ Đức",
            required_amenities=["no_shared_landlord"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"price": "high", "amenity": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G1_07",
        group="G1_BUDGET",
        query="Nữ sinh viên tìm phòng hoặc sleepbox dưới 2 triệu gần ĐHQG, có điều hòa và an ninh tốt.",
        persona_description="Nữ sinh viên tìm phòng trọ giá sinh viên nhưng bắt buộc có điều hòa và môi trường an ninh.",
        expectation=GroundTruthExpectation(
            max_budget=2_000_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=3.0,
            target_location_name="ĐHQG TP.HCM",
            required_amenities=["aircon", "safe_area"],
            allowed_room_types=["SLEEPBOX", "ROOM"],
            forbidden_room_types=[],
            ideal_priorities={"price": "high", "safety": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G1_08",
        group="G1_BUDGET",
        query="Sinh viên tài chính eo hẹp tối đa 2.5 triệu muốn thuê phòng đơn riêng gần ĐHQG TP.HCM trong bán kính 4km, có gác lửng.",
        persona_description="Sinh viên cần phòng riêng biệt có gác lửng để tối ưu không gian sinh hoạt với giá dưới 2.5tr.",
        expectation=GroundTruthExpectation(
            max_budget=2_500_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=4.0,
            target_location_name="ĐHQG TP.HCM",
            required_amenities=["mezzanine"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"price": "high", "amenity": "medium"},
        ),
    ),

    # ------------------------------------------------------------------------
    # NHÓM 2: G2_SAFETY_AMENITY (8 queries)
    # Trọng tâm: Sinh viên nữ ưu tiên an ninh (camera, khóa vân tay, khu an ninh), máy lạnh, máy giặt gần ĐH Bách Khoa CS1 Q10 (10.7725, 106.6578), ĐH Kinh Tế UEH Q10 (10.7607, 106.6669).
    # ------------------------------------------------------------------------
    BenchmarkQuery(
        id="G2_01",
        group="G2_SAFETY_AMENITY",
        query="Em là nữ sinh viên Bách Khoa CS1 Q10, muốn tìm phòng an ninh cao có camera và khóa vân tay, có máy lạnh, ngân sách 3.5 - 4.5 triệu.",
        persona_description="Nữ sinh viên Bách Khoa Q10 coi trọng an ninh, khóa vân tay và cần máy lạnh.",
        expectation=GroundTruthExpectation(
            min_budget=3_500_000.0,
            max_budget=4_500_000.0,
            target_lat=10.7725,
            target_lng=106.6578,
            max_distance_km=3.0,
            target_location_name="ĐH Bách Khoa CS1 Q10",
            required_amenities=["aircon", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"safety": "high", "amenity": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G2_02",
        group="G2_SAFETY_AMENITY",
        query="Nữ sinh viên UEH cơ sở B Nguyễn Tri Phương Q10 cần thuê phòng khép kín WC riêng, có máy lạnh máy giặt, khu an ninh, tối đa 4 triệu.",
        persona_description="Sinh viên UEH cần tiện nghi khép kín, có máy giặt máy lạnh và khu vực an toàn.",
        expectation=GroundTruthExpectation(
            max_budget=4_000_000.0,
            target_lat=10.7607,
            target_lng=106.6669,
            max_distance_km=2.5,
            target_location_name="UEH Cơ sở B Q10",
            required_amenities=["private_wc", "aircon", "washing_machine", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"safety": "high", "amenity": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G2_03",
        group="G2_SAFETY_AMENITY",
        query="Tìm phòng trọ cho nữ gần ĐH Bách Khoa Lý Thường Kiệt trong bán kính 2km, bắt buộc có khóa vân tay, không chung chủ, giá dưới 5 triệu.",
        persona_description="Nữ sinh viên đề cao sự riêng tư không chung chủ nhưng an toàn tuyệt đối với khóa vân tay.",
        expectation=GroundTruthExpectation(
            max_budget=5_000_000.0,
            target_lat=10.7725,
            target_lng=106.6578,
            max_distance_km=2.0,
            target_location_name="ĐH Bách Khoa CS1 Q10",
            required_amenities=["no_shared_landlord", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"safety": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G2_04",
        group="G2_SAFETY_AMENITY",
        query="Cần tìm phòng nữ gần UEH Q10, giá dưới 4.5 triệu, yêu cầu có camera an ninh, có máy lạnh và cửa sổ ban công thoáng.",
        persona_description="Sinh viên UEH cần phòng có ban công/cửa sổ thoáng mát, có điều hòa và hệ thống camera an ninh.",
        expectation=GroundTruthExpectation(
            max_budget=4_500_000.0,
            target_lat=10.7607,
            target_lng=106.6669,
            max_distance_km=3.0,
            target_location_name="UEH Q10",
            required_amenities=["aircon", "window_balcony", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"safety": "high", "amenity": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G2_05",
        group="G2_SAFETY_AMENITY",
        query="Sinh viên nữ tìm phòng studio hoặc phòng trọ an ninh tuyệt đối gần Bách Khoa Q10, có thang máy, máy giặt, tài chính 4 - 5.5 triệu.",
        persona_description="Nữ sinh viên ở các tầng cao cần thang máy và máy giặt tiện ích trong tòa nhà an ninh.",
        expectation=GroundTruthExpectation(
            min_budget=4_000_000.0,
            max_budget=5_500_000.0,
            target_lat=10.7725,
            target_lng=106.6578,
            max_distance_km=2.5,
            target_location_name="ĐH Bách Khoa Q10",
            required_amenities=["elevator", "washing_machine", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"safety": "high", "amenity": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G2_06",
        group="G2_SAFETY_AMENITY",
        query="Tìm phòng trọ an ninh cho 2 bạn nữ gần ngã tư Lý Thường Kiệt - Tô Hiến Thành Q10, có máy lạnh, WC riêng, giờ tự do, giá dưới 5 triệu.",
        persona_description="Hai bạn nữ sinh viên ở ghép cần phòng khép kín, có điều hòa, giờ tự do và an ninh tốt.",
        expectation=GroundTruthExpectation(
            max_budget=5_000_000.0,
            target_lat=10.7725,
            target_lng=106.6578,
            max_distance_km=2.0,
            target_location_name="Lý Thường Kiệt - Tô Hiến Thành Q10",
            required_amenities=["aircon", "private_wc", "free_hours", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"safety": "high", "amenity": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G2_07",
        group="G2_SAFETY_AMENITY",
        query="Nữ sinh viên năm cuối cần phòng yên tĩnh an ninh gần ĐH Kinh Tế Q10, có camera an ninh, full nội thất, ngân sách tối đa 4.8 triệu.",
        persona_description="Nữ sinh viên năm cuối chuẩn bị tốt nghiệp cần không gian yên tĩnh, an ninh và đầy đủ nội thất.",
        expectation=GroundTruthExpectation(
            max_budget=4_800_000.0,
            target_lat=10.7607,
            target_lng=106.6669,
            max_distance_km=3.0,
            target_location_name="UEH Q10",
            required_amenities=["furniture", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"safety": "high", "amenity": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G2_08",
        group="G2_SAFETY_AMENITY",
        query="Tìm phòng trọ khép kín gần ĐH Bách Khoa CS1 dưới 4.2 triệu, ưu tiên khu vực an ninh cao, có máy lạnh, chỗ để xe rộng rãi.",
        persona_description="Sinh viên tìm phòng an toàn gần trường Bách Khoa, có điều hòa và nhà vệ sinh riêng.",
        expectation=GroundTruthExpectation(
            max_budget=4_200_000.0,
            target_lat=10.7725,
            target_lng=106.6578,
            max_distance_km=2.5,
            target_location_name="ĐH Bách Khoa CS1 Q10",
            required_amenities=["aircon", "private_wc", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"safety": "high", "distance": "high"},
        ),
    ),

    # ------------------------------------------------------------------------
    # NHÓM 3: G3_GROUP_FRIENDS (8 queries)
    # Trọng tâm: Nhóm bạn ở chung, cần phòng rộng >= 30m2, có gác lửng/nhiều phòng ngủ, cho nuôi thú cưng, giờ tự do gần ĐH Sư Phạm Kỹ Thuật HCMUTE (10.8514, 106.7720), HUTECH Bình Thạnh (10.8016, 106.7114).
    # ------------------------------------------------------------------------
    BenchmarkQuery(
        id="G3_01",
        group="G3_GROUP_FRIENDS",
        query="Nhóm 3 bạn sinh viên SPKT HCMUTE tìm phòng trọ rộng trên 30m2 có gác lửng cao, giờ tự do, giá từ 3.5 đến 5 triệu gần trường.",
        persona_description="Nhóm 3 sinh viên kỹ thuật ở ghép để tiết kiệm chi phí, cần diện tích tối thiểu 30m2 và gác lửng cao.",
        expectation=GroundTruthExpectation(
            min_budget=3_500_000.0,
            max_budget=5_000_000.0,
            target_lat=10.8514,
            target_lng=106.7720,
            max_distance_km=3.5,
            target_location_name="ĐH Sư Phạm Kỹ Thuật HCMUTE",
            required_amenities=["mezzanine", "free_hours"],
            allowed_room_types=["ROOM", "APARTMENT"],
            forbidden_room_types=[],
            min_area_m2=30.0,
            ideal_priorities={"amenity": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G3_02",
        group="G3_GROUP_FRIENDS",
        query="Nhóm bạn sinh viên HUTECH Điện Biên Phủ cần tìm phòng rộng >= 35m2 có gác lửng, cho nấu ăn, không chung chủ, ngân sách dưới 6 triệu.",
        persona_description="Nhóm sinh viên HUTECH cần phòng lớn để ở cùng nhau, tự nấu ăn và không phụ thuộc chủ nhà.",
        expectation=GroundTruthExpectation(
            max_budget=6_000_000.0,
            target_lat=10.8016,
            target_lng=106.7114,
            max_distance_km=3.0,
            target_location_name="HUTECH Điện Biên Phủ, Bình Thạnh",
            required_amenities=["mezzanine", "kitchen", "no_shared_landlord"],
            allowed_room_types=["ROOM", "APARTMENT"],
            forbidden_room_types=[],
            min_area_m2=35.0,
            ideal_priorities={"amenity": "high", "price": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G3_03",
        group="G3_GROUP_FRIENDS",
        query="Tụi mình 3 người có nuôi 1 bé mèo, cần thuê phòng gần HCMUTE Võ Văn Ngân, diện tích >= 30m2, cho phép nuôi pet, giờ giấc tự do, dưới 5.5 triệu.",
        persona_description="Nhóm bạn trẻ có nuôi thú cưng (mèo), cần phòng trọ cho nuôi pet và diện tích rộng rãi.",
        expectation=GroundTruthExpectation(
            max_budget=5_500_000.0,
            target_lat=10.8514,
            target_lng=106.7720,
            max_distance_km=3.0,
            target_location_name="HCMUTE Võ Văn Ngân, Thủ Đức",
            required_amenities=["pet_allowed", "free_hours"],
            allowed_room_types=["ROOM", "APARTMENT", "WHOLE_HOUSE"],
            forbidden_room_types=[],
            min_area_m2=30.0,
            ideal_priorities={"amenity": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G3_04",
        group="G3_GROUP_FRIENDS",
        query="Nhóm 4 sinh viên HUTECH Bình Thạnh tìm căn hộ mini hoặc phòng trọ lớn >= 40m2, có gác lửng, máy lạnh, máy giặt, giá dưới 7 triệu.",
        persona_description="Nhóm 4 sinh viên ở chung cần không gian lớn từ 40m2 trở lên với đầy đủ điều hòa và máy giặt.",
        expectation=GroundTruthExpectation(
            max_budget=7_000_000.0,
            target_lat=10.8016,
            target_lng=106.7114,
            max_distance_km=3.5,
            target_location_name="HUTECH Bình Thạnh",
            required_amenities=["mezzanine", "aircon", "washing_machine"],
            allowed_room_types=["ROOM", "APARTMENT", "STUDIO"],
            forbidden_room_types=[],
            min_area_m2=40.0,
            ideal_priorities={"amenity": "high", "price": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G3_05",
        group="G3_GROUP_FRIENDS",
        query="Cần tìm phòng trọ diện tích từ 30m2 trở lên cho nhóm bạn gần ĐH Sư Phạm Kỹ Thuật Thủ Đức, có ban công, gác lửng, kệ bếp nấu ăn, tối đa 5 triệu.",
        persona_description="Nhóm sinh viên kỹ thuật cần ban công phơi đồ thoáng và kệ bếp nấu nướng.",
        expectation=GroundTruthExpectation(
            max_budget=5_000_000.0,
            target_lat=10.8514,
            target_lng=106.7720,
            max_distance_km=3.0,
            target_location_name="ĐH SPKT Thủ Đức",
            required_amenities=["window_balcony", "mezzanine", "kitchen"],
            allowed_room_types=["ROOM", "APARTMENT"],
            forbidden_room_types=[],
            min_area_m2=30.0,
            ideal_priorities={"amenity": "high", "distance": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G3_06",
        group="G3_GROUP_FRIENDS",
        query="3 bạn sinh viên cần thuê phòng gần HUTECH Ung Văn Khiêm, diện tích tối thiểu 30m2, cho nuôi thú cưng, có máy lạnh, giá dưới 6.5 triệu.",
        persona_description="Nhóm sinh viên HUTECH Ung Văn Khiêm nuôi thú cưng và cần có máy lạnh cho mùa hè.",
        expectation=GroundTruthExpectation(
            max_budget=6_500_000.0,
            target_lat=10.8016,
            target_lng=106.7114,
            max_distance_km=2.5,
            target_location_name="HUTECH Ung Văn Khiêm, Bình Thạnh",
            required_amenities=["pet_allowed", "aircon"],
            allowed_room_types=["ROOM", "APARTMENT", "STUDIO"],
            forbidden_room_types=[],
            min_area_m2=30.0,
            ideal_priorities={"amenity": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G3_07",
        group="G3_GROUP_FRIENDS",
        query="Nhóm bạn tìm phòng trọ rộng rãi >= 32m2 gần ngã tư Thủ Đức / HCMUTE, có gác lửng, giờ tự do 24/7, không chung chủ, ngân sách 4 - 5.5 triệu.",
        persona_description="Nhóm sinh viên năm cuối đi thực tập về muộn, cần giờ giấc 24/7 và độc lập không chung chủ.",
        expectation=GroundTruthExpectation(
            min_budget=4_000_000.0,
            max_budget=5_500_000.0,
            target_lat=10.8514,
            target_lng=106.7720,
            max_distance_km=3.0,
            target_location_name="Ngã tư Thủ Đức / HCMUTE",
            required_amenities=["mezzanine", "free_hours", "no_shared_landlord"],
            allowed_room_types=["ROOM", "APARTMENT"],
            forbidden_room_types=[],
            min_area_m2=32.0,
            ideal_priorities={"amenity": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G3_08",
        group="G3_GROUP_FRIENDS",
        query="Nhóm sinh viên tìm căn hộ dịch vụ hoặc phòng trọ lớn >= 35m2 gần HUTECH Bình Thạnh, có thang máy, gác lửng, máy giặt, ngân sách dưới 7 triệu.",
        persona_description="Nhóm bạn ở chung tìm phòng cao tầng có thang máy, gác lửng và máy giặt tiện lợi.",
        expectation=GroundTruthExpectation(
            max_budget=7_000_000.0,
            target_lat=10.8016,
            target_lng=106.7114,
            max_distance_km=3.0,
            target_location_name="HUTECH Bình Thạnh",
            required_amenities=["elevator", "mezzanine", "washing_machine"],
            allowed_room_types=["ROOM", "APARTMENT", "STUDIO"],
            forbidden_room_types=[],
            min_area_m2=35.0,
            ideal_priorities={"amenity": "high", "distance": "medium"},
        ),
    ),

    # ------------------------------------------------------------------------
    # NHÓM 4: G4_PREMIUM_STUDIO (8 queries)
    # Trọng tâm: Người đi làm, studio/căn hộ dịch vụ cao cấp 5-8tr, full nội thất, thang máy, ban công ở Q1 (Bến Thành 10.7725, 106.6980), Q7 (Phú Mỹ Hưng 10.7326, 106.7058), Phú Nhuận (10.7992, 106.6803).
    # ------------------------------------------------------------------------
    BenchmarkQuery(
        id="G4_01",
        group="G4_PREMIUM_STUDIO",
        query="Tôi là chuyên viên làm việc tại Quận 1, cần tìm căn hộ studio cao cấp full nội thất, có ban công view đẹp, thang máy, ngân sách 6 - 8 triệu gần Chợ Bến Thành.",
        persona_description="Chuyên viên văn phòng trung tâm Q1, thu nhập khá, cần studio đẹp đầy đủ tiện nghi cao cấp.",
        expectation=GroundTruthExpectation(
            min_budget=6_000_000.0,
            max_budget=8_000_000.0,
            target_lat=10.7725,
            target_lng=106.6980,
            max_distance_km=3.0,
            target_location_name="Chợ Bến Thành, Quận 1",
            required_amenities=["furniture", "window_balcony", "elevator"],
            allowed_room_types=["STUDIO", "APARTMENT"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"amenity": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G4_02",
        group="G4_PREMIUM_STUDIO",
        query="Tìm studio hoặc căn hộ dịch vụ 1 phòng ngủ tại Phú Mỹ Hưng Quận 7, đầy đủ tiện nghi máy giặt, thang máy, giá dưới 8 triệu.",
        persona_description="Nhân viên công ty quốc tế tại Nam Sài Gòn cần căn hộ dịch vụ văn minh, có thang máy và máy giặt.",
        expectation=GroundTruthExpectation(
            max_budget=8_000_000.0,
            target_lat=10.7326,
            target_lng=106.7058,
            max_distance_km=3.5,
            target_location_name="Phú Mỹ Hưng, Quận 7",
            required_amenities=["furniture", "washing_machine", "elevator"],
            allowed_room_types=["STUDIO", "APARTMENT"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"amenity": "high", "distance": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G4_03",
        group="G4_PREMIUM_STUDIO",
        query="Chuyên viên tìm căn hộ studio hiện đại ở Phú Nhuận gần Phan Xích Long, full nội thất xịn, ban công thoáng mát, ngân sách 6.5 - 8 triệu.",
        persona_description="Người đi làm khu ẩm thực Phan Xích Long thích phòng studio có ánh sáng tự nhiên và nội thất sẵn.",
        expectation=GroundTruthExpectation(
            min_budget=6_500_000.0,
            max_budget=8_000_000.0,
            target_lat=10.7992,
            target_lng=106.6803,
            max_distance_km=2.5,
            target_location_name="Phan Xích Long, Phú Nhuận",
            required_amenities=["furniture", "window_balcony", "aircon"],
            allowed_room_types=["STUDIO", "APARTMENT"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"amenity": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G4_04",
        group="G4_PREMIUM_STUDIO",
        query="Cần thuê căn hộ dịch vụ cao cấp tại Quận 1, có thang máy, ban công, máy giặt riêng, tài chính tối đa 8 triệu.",
        persona_description="Quản lý trẻ làm việc tại trung tâm TP, yêu cầu sự riêng tư với máy giặt riêng và ban công thoáng.",
        expectation=GroundTruthExpectation(
            max_budget=8_000_000.0,
            target_lat=10.7725,
            target_lng=106.6980,
            max_distance_km=3.0,
            target_location_name="Quận 1",
            required_amenities=["elevator", "window_balcony", "washing_machine"],
            allowed_room_types=["STUDIO", "APARTMENT"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"amenity": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G4_05",
        group="G4_PREMIUM_STUDIO",
        query="Tìm căn studio sang trọng gần Crescent Mall Phú Mỹ Hưng Q7, diện tích >= 28m2, full nội thất cao cấp, giờ tự do, an ninh 24/7, ngân sách 6 - 7.5 triệu.",
        persona_description="Chuyên viên làm việc gần Crescent Mall Q7 cần không gian sống an ninh tuyệt đối và tự do giờ giấc.",
        expectation=GroundTruthExpectation(
            min_budget=6_000_000.0,
            max_budget=7_500_000.0,
            target_lat=10.7326,
            target_lng=106.7058,
            max_distance_km=3.0,
            target_location_name="Crescent Mall, Quận 7",
            required_amenities=["furniture", "free_hours", "safe_area"],
            allowed_room_types=["STUDIO", "APARTMENT"],
            forbidden_room_types=["SLEEPBOX"],
            min_area_m2=28.0,
            ideal_priorities={"amenity": "high", "safety": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G4_06",
        group="G4_PREMIUM_STUDIO",
        query="Nhân viên văn phòng cần studio ở Phú Nhuận giáp Quận 1, có ban công rộng, bếp riêng, máy lạnh, thang máy, giá từ 5.5 đến 7.5 triệu.",
        persona_description="Nhân viên văn phòng thích tự nấu ăn tại nhà, cần studio có bếp riêng biệt và ban công.",
        expectation=GroundTruthExpectation(
            min_budget=5_500_000.0,
            max_budget=7_500_000.0,
            target_lat=10.7992,
            target_lng=106.6803,
            max_distance_km=3.0,
            target_location_name="Phú Nhuận giáp Quận 1",
            required_amenities=["window_balcony", "kitchen", "aircon", "elevator"],
            allowed_room_types=["STUDIO", "APARTMENT"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"amenity": "high", "distance": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G4_07",
        group="G4_PREMIUM_STUDIO",
        query="Tìm căn hộ dịch vụ cao cấp tại Quận 1, khu vực Bến Thành - Đa Kao, full nội thất, không chung chủ, thang máy, ngân sách 7 - 8 triệu.",
        persona_description="Chuyên gia tài chính tại Q1 cần căn hộ dịch vụ độc lập không chung chủ, nội thất sang trọng.",
        expectation=GroundTruthExpectation(
            min_budget=7_000_000.0,
            max_budget=8_000_000.0,
            target_lat=10.7725,
            target_lng=106.6980,
            max_distance_km=3.0,
            target_location_name="Bến Thành - Đa Kao, Quận 1",
            required_amenities=["furniture", "no_shared_landlord", "elevator"],
            allowed_room_types=["STUDIO", "APARTMENT"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"amenity": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G4_08",
        group="G4_PREMIUM_STUDIO",
        query="Thuê studio view đẹp tại Quận 7 giáp Phú Mỹ Hưng, đầy đủ nội thất cao cấp, máy giặt riêng, ban công đón sáng, giá tối đa 7.5 triệu.",
        persona_description="Người làm việc sáng tạo nội dung cần ban công rộng đón ánh sáng tự nhiên và máy giặt riêng.",
        expectation=GroundTruthExpectation(
            max_budget=7_500_000.0,
            target_lat=10.7326,
            target_lng=106.7058,
            max_distance_km=3.5,
            target_location_name="Quận 7 giáp Phú Mỹ Hưng",
            required_amenities=["furniture", "washing_machine", "window_balcony"],
            allowed_room_types=["STUDIO", "APARTMENT"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"amenity": "high", "distance": "medium"},
        ),
    ),

    # ------------------------------------------------------------------------
    # NHÓM 5: G5_EDGE_CASES (8 queries)
    # Trọng tâm: Ca khó: tiếng lóng ('3 củ rưỡi', 'triệu hai'), phủ định ('không chung chủ', 'ko lấy ktx'), tìm phòng theo trạm xe buýt/địa bàn giáp ranh Dĩ An - Thủ Đức.
    # ------------------------------------------------------------------------
    BenchmarkQuery(
        id="G5_01",
        group="G5_EDGE_CASES",
        query="Cần tìm phòng tầm 3 củ rưỡi đổ lại gần ĐHQG, ko lấy ktx hay sleepbox nha, muốn phòng riêng có gác lửng và giờ tự do.",
        persona_description="Sinh viên dùng tiếng lóng ngân sách ('3 củ rưỡi') và mệnh đề phủ định ('ko lấy ktx hay sleepbox').",
        expectation=GroundTruthExpectation(
            max_budget=3_500_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=3.5,
            target_location_name="ĐHQG TP.HCM",
            required_amenities=["mezzanine", "free_hours"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"price": "high", "amenity": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G5_02",
        group="G5_EDGE_CASES",
        query="Tìm chỗ trọ giá khoảng triệu hai đến triệu rưỡi gần trạm xe buýt Suối Tiên / ĐHQG Thủ Đức, có máy lạnh.",
        persona_description="Sinh viên di chuyển bằng xe buýt dùng từ 'triệu hai đến triệu rưỡi', cần máy lạnh và giá cực rẻ.",
        expectation=GroundTruthExpectation(
            min_budget=1_200_000.0,
            max_budget=1_500_000.0,
            target_lat=10.8650,
            target_lng=106.8000,
            max_distance_km=2.5,
            target_location_name="Trạm xe buýt Suối Tiên",
            required_amenities=["aircon"],
            allowed_room_types=["SLEEPBOX", "ROOM"],
            forbidden_room_types=[],
            ideal_priorities={"price": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G5_03",
        group="G5_EDGE_CASES",
        query="Muốn thuê phòng trọ không chung chủ, tuyệt đối không ở ghép ktx, giá dưới 3 triệu ở khu vực giáp ranh Dĩ An Bình Dương và Thủ Đức.",
        persona_description="Người đi làm khu công nghiệp giáp ranh Dĩ An - Thủ Đức, kiên quyết phủ định KTX và chung chủ.",
        expectation=GroundTruthExpectation(
            max_budget=3_000_000.0,
            target_lat=10.8850,
            target_lng=106.7800,
            max_distance_km=3.5,
            target_location_name="Khu vực giáp ranh Dĩ An - Thủ Đức",
            required_amenities=["no_shared_landlord"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"price": "high", "distance": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G5_04",
        group="G5_EDGE_CASES",
        query="Tìm phòng tầm 2 củ 8 quay đầu gần làng đại học, phòng có máy lạnh với wc khép kín, cấm chung chủ.",
        persona_description="Sinh viên dùng tiếng lóng '2 củ 8 quay đầu', ràng buộc máy lạnh, vệ sinh riêng và cấm chung chủ.",
        expectation=GroundTruthExpectation(
            max_budget=2_800_000.0,
            target_lat=10.8700,
            target_lng=106.8031,
            max_distance_km=3.5,
            target_location_name="Làng Đại học",
            required_amenities=["aircon", "private_wc", "no_shared_landlord"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"price": "high", "amenity": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G5_05",
        group="G5_EDGE_CASES",
        query="Cần căn studio hoặc phòng đơn giá dưới 4 củ gần trạm xe bus Bến Thành Q1, yêu cầu ko chung chủ và có khóa vân tay.",
        persona_description="Người đi làm di chuyển bằng xe bus trung tâm, dùng tiếng lóng '4 củ' và yêu cầu khóa vân tay an ninh.",
        expectation=GroundTruthExpectation(
            max_budget=4_000_000.0,
            target_lat=10.7725,
            target_lng=106.6980,
            max_distance_km=3.0,
            target_location_name="Trạm xe bus Bến Thành Q1",
            required_amenities=["no_shared_landlord", "safe_area"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"safety": "high", "distance": "high"},
        ),
    ),
    BenchmarkQuery(
        id="G5_06",
        group="G5_EDGE_CASES",
        query="Tìm phòng 5 triệu rưỡi ở Phú Nhuận, không lấy phòng không có cửa sổ, phải có ban công hoặc giếng trời thoáng đãng.",
        persona_description="Khách hàng phủ định kép ('không lấy phòng không có cửa sổ'), yêu cầu ban công thoáng đãng.",
        expectation=GroundTruthExpectation(
            max_budget=5_500_000.0,
            target_lat=10.7992,
            target_lng=106.6803,
            max_distance_km=3.0,
            target_location_name="Phú Nhuận",
            required_amenities=["window_balcony"],
            allowed_room_types=["ROOM", "STUDIO"],
            forbidden_room_types=[],
            ideal_priorities={"amenity": "high", "distance": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G5_07",
        group="G5_EDGE_CASES",
        query="Tài chính 2 củ rưỡi, tìm phòng quanh ngã tư Bình Phước Thủ Đức giáp ranh Dĩ An, cấm ktx sleepbox, cần giờ tự do có gác.",
        persona_description="Công nhân/sinh viên khu ngã tư Bình Phước giáp Dĩ An, cấm sleepbox, cần giờ giấc 24/7 và gác lửng.",
        expectation=GroundTruthExpectation(
            max_budget=2_500_000.0,
            target_lat=10.8520,
            target_lng=106.7200,
            max_distance_km=3.5,
            target_location_name="Ngã tư Bình Phước Thủ Đức",
            required_amenities=["free_hours", "mezzanine"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"price": "high", "amenity": "medium"},
        ),
    ),
    BenchmarkQuery(
        id="G5_08",
        group="G5_EDGE_CASES",
        query="Tìm phòng trọ tầm 3 củ ở khu vực Bách Khoa Q10, không chung chủ, không hạn chế giờ giấc, có chỗ để xe máy.",
        persona_description="Sinh viên Bách Khoa dùng tiếng lóng '3 củ', ràng buộc không chung chủ và giờ giấc tự do.",
        expectation=GroundTruthExpectation(
            max_budget=3_000_000.0,
            target_lat=10.7725,
            target_lng=106.6578,
            max_distance_km=3.0,
            target_location_name="ĐH Bách Khoa Q10",
            required_amenities=["no_shared_landlord", "free_hours"],
            allowed_room_types=["ROOM"],
            forbidden_room_types=["SLEEPBOX"],
            ideal_priorities={"price": "high", "distance": "high"},
        ),
    ),
]
