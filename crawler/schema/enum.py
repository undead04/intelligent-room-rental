from enum import Enum

class RoomType(str, Enum):
    """Phân loại phòng trọ cơ bản."""
    ROOM = "ROOM"                          # Phòng trọ truyền thống
    STUDIO = "STUDIO"                      # Căn hộ mini, studio
    APARTMENT = "APARTMENT"                # Căn hộ chung cư, chung cư dịch vụ
    SLEEPBOX = "SLEEPBOX"                  # Ký túc xá, sleepbox, giường tầng
    WHOLE_HOUSE = "WHOLE_HOUSE"            # Nhà nguyên căn

class AmenityCode(str, Enum):
    """Danh mục tiện ích chuẩn hóa (Canonical Taxonomy).
    Dùng cho UI Checkbox, Filter cứng và công thức tính trọng số Rerank.
    """
    AC = "AC"                              # Máy lạnh, điều hòa
    MEZZANINE = "MEZZANINE"                # Gác lửng, gác suốt
    WASHING_MACHINE = "WASHING_MACHINE"    # Máy giặt (chung hoặc riêng)
    FRIDGE = "FRIDGE"                      # Tủ lạnh
    BALCONY = "BALCONY"                    # Ban công, sân phơi riêng
    WINDOW = "WINDOW"                      # Cửa sổ thoáng, giếng trời
    ELEVATOR = "ELEVATOR"                  # Thang máy
    PRIVATE_WC = "PRIVATE_WC"              # WC riêng, vệ sinh khép kín
    WATER_HEATER = "WATER_HEATER"          # Bình nóng lạnh, nước nóng NLMT
    FINGERPRINT_LOCK = "FINGERPRINT_LOCK"  # Khóa vân tay, cổng thẻ từ
    PARKING = "PARKING"                    # Hầm để xe, chỗ để xe trong nhà
    KITCHEN_SHELF = "KITCHEN_SHELF"        # Kệ bếp, bồn rửa, khu nấu ăn riêng