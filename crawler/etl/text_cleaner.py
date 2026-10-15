import re
import unicodedata

# 1. Regex nhận diện URL / Link web
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")

# 2. Regex nhận diện số điện thoại VN (các định dạng: 0909123456, 0909.123.456, 0909 123 456, +84...)
PHONE_PATTERN = re.compile(r"(?:\+?84|0)(?:\s*[\.\-]?\s*\d){9,10}\b")

# 3. Regex nhận diện Hashtag (#chothuetro, #thuduc...)
HASHTAG_PATTERN = re.compile(r"#\w+")

# 4. Regex nhận diện ký tự trang trí, đường kẻ khung (====, ----, *****, bullet points rác)
DECORATIVE_PATTERN = re.compile(r"[═=\-_*~•❖▶★●◆✔☎►]{2,}")

# 5. Regex nhận diện Emojis, Symbols & Variation Selectors
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
    "\U0001F680-\U0001F6FF"  # Transport & Map Symbols
    "\U0001F1E0-\U0001F1FF"  # Flags
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"
    "\uFE0E\uFE0F"          # Variation selectors
    "]+",
    flags=re.UNICODE,
)

# 6. Regex nhận diện dòng thuần liên hệ, chốt sale
CONTACT_LINE_PATTERN = re.compile(
    r"^\s*[-•*+]?\s*(?:liên hệ|inbox|ib|zalo|call|alo|gọi ngay|sđt|hotline|nhanh tay|xem phòng|xem chi tiết).*$",
    flags=re.IGNORECASE | re.MULTILINE,
)

# 7. Regex xóa các cụm từ chốt sale còn sót lại trong dòng
INLINE_CTA_PATTERNS = [
    re.compile(r"(?:liên hệ|inbox|ib|zalo|call|alo|gọi ngay|sđt|hotline)[\s\:\-\/]*", flags=re.IGNORECASE),
    re.compile(r"nhanh tay kẻo hết.*", flags=re.IGNORECASE),
    re.compile(r"xem phòng trực tiếp.*", flags=re.IGNORECASE),
]

# 8. Regex nhận diện dòng rác chỉ chứa bullet hoặc dấu câu mồ côi
ORPHAN_LINE_PATTERN = re.compile(r"^\s*[-•*+:\./\s]+$")


def clean_room_description(text: str) -> str:
    """Làm sạch tiêu đề và mô tả bài đăng:
    1. Chuẩn hóa Unicode NFC (tránh lỗi ký tự dựng sẵn vs tổ hợp trong tiếng Việt)
    2. Loại bỏ URL, link web
    3. Loại bỏ số điện thoại liên hệ
    4. Loại bỏ hashtag
    5. Loại bỏ ký tự trang trí, viền khung, bullet points rác
    6. Loại bỏ Emojis & Icon
    7. Loại bỏ các dòng liên hệ / chốt sale vô nghĩa
    8. Lọc dòng rác mồ côi
    9. Chuẩn hóa khoảng trắng & dòng trống
    """
    if not text:
        return ""

    # 1. Chuẩn hóa Unicode NFC
    text = unicodedata.normalize("NFC", str(text))

    # 2. Xóa URL / Link web
    text = URL_PATTERN.sub("", text)

    # 3. Xóa số điện thoại
    text = PHONE_PATTERN.sub("", text)

    # 4. Xóa Hashtag
    text = HASHTAG_PATTERN.sub("", text)

    # 5. Xóa ký tự trang trí, đường kẻ khung
    text = DECORATIVE_PATTERN.sub(" ", text)

    # 6. Xóa Emoji & Icons
    text = EMOJI_PATTERN.sub(" ", text)

    # 7. Xóa các dòng thuần liên hệ, chốt sale
    text = CONTACT_LINE_PATTERN.sub("", text)

    # Xóa các cụm từ chốt sale còn sót lại trong dòng
    for pattern in INLINE_CTA_PATTERNS:
        text = pattern.sub(" ", text)

    # 8. Lọc bỏ các dòng chỉ còn lại dấu gạch đầu dòng hoặc dấu câu mồ côi
    lines = []
    for line in text.split("\n"):
        line_clean = ORPHAN_LINE_PATTERN.sub("", line).strip()
        if line_clean:
            lines.append(line_clean)
    text = "\n".join(lines)

    # 9. Chuẩn hóa khoảng trắng và dòng trống
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()
