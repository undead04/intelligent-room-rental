from enum import Enum


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



# Bản đồ hiển thị tiếng Việt chuẩn hóa
ROOM_TYPE_LABELS: dict[str, str] = {
    RoomType.ROOM.value: "Phòng trọ",
    RoomType.STUDIO.value: "Căn hộ mini / Studio",
    RoomType.APARTMENT.value: "Căn hộ chung cư",
    RoomType.SLEEPBOX.value: "Ký túc xá / Sleepbox",
    RoomType.WHOLE_HOUSE.value: "Nhà nguyên căn",
}

# Bảng ánh xạ danh mục RoomType chuẩn hoá hệ thống sang ID quan hệ (1..5)
CANONICAL_ROOM_TYPES: dict[str, tuple[int, str]] = {
    RoomType.ROOM.value: (1, "Phòng trọ"),
    RoomType.STUDIO.value: (2, "Căn hộ mini / Studio"),
    RoomType.APARTMENT.value: (3, "Căn hộ chung cư"),
    RoomType.SLEEPBOX.value: (4, "Ký túc xá / Sleepbox"),
    RoomType.WHOLE_HOUSE.value: (5, "Nhà nguyên căn"),
}

ROOM_TYPE_CODE_TO_ID: dict[str, int] = {
    code: info[0] for code, info in CANONICAL_ROOM_TYPES.items()
}

AMENITY_VIETNAMESE_MAP: dict[str, str] = {
    AmenityCode.PRIVATE_WC.value: "WC riêng",
    AmenityCode.AIRCON.value: "máy lạnh",
    AmenityCode.MEZZANINE.value: "gác lửng",
    AmenityCode.KITCHEN.value: "kệ bếp",
    AmenityCode.FRIDGE.value: "tủ lạnh",
    AmenityCode.WASHING_MACHINE.value: "máy giặt",
    AmenityCode.WINDOW_BALCONY.value: "cửa sổ/ban công",
    AmenityCode.FURNITURE.value: "nội thất",
    AmenityCode.PARKING.value: "chỗ để xe",
    AmenityCode.ELEVATOR.value: "thang máy",
}

SAFETY_VIETNAMESE_MAP: dict[str, str] = {
    AmenityCode.FINGERPRINT_LOCK.value: "khóa vân tay/thẻ từ",
    AmenityCode.CAMERA.value: "camera an ninh",
    AmenityCode.GUARD.value: "bảo vệ 24/7",
    AmenityCode.SAFE_AREA.value: "khu an ninh",
}

RULES_VIETNAMESE_MAP: dict[str, str] = {
    AmenityCode.FREE_HOURS.value: "giờ giấc tự do",
    AmenityCode.NO_SHARED_LANDLORD.value: "không chung chủ",
    AmenityCode.PET_ALLOWED.value: "cho nuôi thú cưng",
}

