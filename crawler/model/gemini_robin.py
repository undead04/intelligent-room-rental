from google import genai

# ============================================================
# API KEY / ROUND ROBIN
# ============================================================
class GeminiRoundRobin:
    """
    Quản lý nhiều Gemini API key.

    - Bình thường: tiếp tục dùng key hiện tại.
    - Gặp quota / rate limit: chuyển sang key tiếp theo.
    - Key đã hết quota sẽ không được dùng lại trong lần chạy này.
    """

    def __init__(
        self,
        api_keys: list[str],
        model_name: str,
    ):
        if not api_keys:
            raise ValueError("api_keys không được rỗng")

        # Loại duplicate + key rỗng
        self.api_keys = list(dict.fromkeys(
            key.strip()
            for key in api_keys
            if key and key.strip()
        ))

        if not self.api_keys:
            raise ValueError("Không có API key hợp lệ")

        self.model_name = model_name

        self.current_index = 0

        self.clients = [
            genai.Client(api_key=key)
            for key in self.api_keys
        ]

        # Index của các key đã hết quota
        self.exhausted_keys: set[int] = set()

    @property
    def current_client(self):
        return self.clients[self.current_index]

    @property
    def current_key_number(self) -> int:
        """
        Số thứ tự key để hiển thị cho user: 1, 2, 3...
        """
        return self.current_index + 1

    @property
    def total_keys(self) -> int:
        return len(self.api_keys)

    def mark_current_exhausted(self) -> None:
        """Đánh dấu key hiện tại đã hết quota."""
        self.exhausted_keys.add(self.current_index)

        print(
            f"  [QUOTA] API key "
            f"{self.current_key_number}/{self.total_keys} "
            f"đã hết quota."
        )

    def rotate(self) -> bool:
        """
        Đánh dấu key hiện tại exhausted và chuyển
        sang key còn khả dụng.

        Returns:
            True  -> còn key để sử dụng.
            False -> tất cả key đều exhausted.
        """

        self.mark_current_exhausted()

        total = self.total_keys

        for _ in range(total):

            self.current_index = (
                self.current_index + 1
            ) % total

            if self.current_index not in self.exhausted_keys:

                print(
                    f"  [ROUND-ROBIN] "
                    f"Chuyển sang API key "
                    f"{self.current_key_number}/{self.total_keys}"
                )

                return True

        return False

    def all_exhausted(self) -> bool:
        return len(self.exhausted_keys) >= self.total_keys
