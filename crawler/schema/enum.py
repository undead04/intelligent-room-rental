from enum import Enum
from typing import Optional


class RoomType(str, Enum):
    """Phân loại phòng trọ cơ bản."""
    ROOM = "ROOM"                          # Phòng trọ truyền thống
    STUDIO = "STUDIO"                      # Căn hộ mini, studio
    APARTMENT = "APARTMENT"                # Căn hộ chung cư, chung cư dịch vụ
    SLEEPBOX = "SLEEPBOX"                  # Ký túc xá, sleepbox, giường tầng
    WHOLE_HOUSE = "WHOLE_HOUSE"            # Nhà nguyên căn


class AmenityCode(str, Enum):
    """Danh mục tiện ích, quy định và an ninh chuẩn hóa (Canonical Taxonomy).
    Giá trị dạng snake_case khớp 1-1 với field name trong ListingExtraction.
    Dùng cho UI Checkbox, Filter cứng và công thức tính trọng số Rerank.
    """
    # 1. Tiện ích phòng cốt lõi (Core Amenities)
    PRIVATE_WC = "private_wc"              # WC riêng, khép kín
    AIRCON = "aircon"                      # Máy lạnh, điều hòa
    MEZZANINE = "mezzanine"                # Gác lửng, gác xép
    KITCHEN = "kitchen"                    # Kệ bếp, khu nấu ăn riêng
    FRIDGE = "fridge"                      # Tủ lạnh
    WASHING_MACHINE = "washing_machine"    # Máy giặt (chung hoặc riêng)
    WINDOW_BALCONY = "window_balcony"      # Ban công hoặc cửa sổ thoáng
    FURNITURE = "furniture"                # Đầy đủ nội thất (giường, tủ, bàn học...)
    PARKING = "parking"                    # Chỗ để xe trong nhà / hầm xe
    ELEVATOR = "elevator"                  # Thang máy

    # 2. Quy định & Lối sống (Rules & Lifestyle)
    FREE_HOURS = "free_hours"              # Giờ giấc tự do (không khóa cổng)
    NO_SHARED_LANDLORD = "no_shared_landlord"  # Không chung chủ
    PET_ALLOWED = "pet_allowed"            # Cho phép nuôi thú cưng (chó, mèo)

    # 3. An toàn & An ninh (Safety)
    FINGERPRINT_LOCK = "fingerprint_lock"  # Khóa vân tay, cổng thẻ từ
    CAMERA = "camera"                      # Camera an ninh 24/7
    GUARD = "guard"                        # Bảo vệ trực cổng 24/7
    SAFE_AREA = "safe_area"                # Khu vực an ninh, yên tĩnh

    @classmethod
    def normalize(cls, code: str) -> Optional[str]:
        """Chuẩn hóa các mã alias từ Frontend hoặc LLM về mã canonical."""
        if not code:
            return None
        c = code.strip().lower()
        alias_map = {
            "ac": "aircon",
            "air_conditioner": "aircon",
            "may_lanh": "aircon",
            "dieu_hoa": "aircon",
            "wc": "private_wc",
            "ve_sinh_rieng": "private_wc",
            "gac": "mezzanine",
            "gac_lung": "mezzanine",
            "gac_xep": "mezzanine",
            "bep": "kitchen",
            "kitchen_shelf": "kitchen",
            "tu_lanh": "fridge",
            "may_giat": "washing_machine",
            "balcony": "window_balcony",
            "window": "window_balcony",
            "ban_cong": "window_balcony",
            "cua_so": "window_balcony",
            "full_noi_that": "furniture",
            "noi_that": "furniture",
            "xe": "parking",
            "ham_xe": "parking",
            "pet": "pet_allowed",
            "cho_nuoi_pet": "pet_allowed",
            "thu_cung": "pet_allowed",
            "tu_do": "free_hours",
            "gio_tu_do": "free_hours",
            "khong_chung_chu": "no_shared_landlord",
            "van_tay": "fingerprint_lock",
            "the_tu": "fingerprint_lock",
            "khoa_van_tay": "fingerprint_lock",
            "bao_ve": "guard",
        }
        return alias_map.get(c, c)