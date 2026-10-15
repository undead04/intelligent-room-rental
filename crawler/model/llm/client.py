import json
import time
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

try:
    from crawler.model.llm.prompt import build_ai_contents
    from crawler.schema.listing import ChunkExtractionWrapper
except ImportError:
    from prompt import build_ai_contents
    from schema.listing import ChunkExtractionWrapper


DEFAULT_MAX_RETRIES = 2
DEFAULT_RPM_DELAY = 4.0


class GeminiRoundRobin:
    """
    Quản lý luân chuyển nhiều Gemini API key.
    - Dùng key hiện tại đến khi gặp Quota / Rate-limit.
    - Tự động xoay sang key tiếp theo khi chạm ngưỡng.
    - Đánh dấu các key đã cạn kiệt.
    """

    def __init__(
        self,
        api_keys: List[str],
        model_name: str,
    ):
        if not api_keys:
            raise ValueError("api_keys không được rỗng")

        # Loại bỏ duplicate và key rỗng
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
        self.exhausted_keys: set[int] = set()

    @property
    def current_client(self) -> genai.Client:
        return self.clients[self.current_index]

    @property
    def current_key_number(self) -> int:
        return self.current_index + 1

    @property
    def total_keys(self) -> int:
        return len(self.api_keys)

    def mark_current_exhausted(self) -> None:
        """Đánh dấu key hiện tại đã hết quota."""
        self.exhausted_keys.add(self.current_index)
        print(
            f"  [QUOTA] API key {self.current_key_number}/{self.total_keys} đã hết quota."
        )

    def rotate(self) -> bool:
        """
        Đánh dấu key hiện tại exhausted và xoay sang key kế tiếp còn khả dụng.
        Returns:
            True nếu còn key khả dụng, False nếu tất cả đã cạn.
        """
        self.mark_current_exhausted()
        total = self.total_keys

        for _ in range(total):
            self.current_index = (self.current_index + 1) % total
            if self.current_index not in self.exhausted_keys:
                print(
                    f"  [ROUND-ROBIN] Chuyển sang API key {self.current_key_number}/{self.total_keys}"
                )
                return True

        return False

    def all_exhausted(self) -> bool:
        return len(self.exhausted_keys) >= self.total_keys


def is_quota_error(exc: Exception) -> bool:
    """Kiểm tra exception có phải là quota hoặc rate-limit hay không."""
    message = str(exc).lower()
    quota_keywords = [
        "quota",
        "rate limit",
        "ratelimit",
        "resource exhausted",
        "resource_exhausted",
        "too many requests",
        "429",
    ]
    return any(keyword in message for keyword in quota_keywords)


def call_gemini_chunk(
    api_manager: GeminiRoundRobin,
    chunk: List[Dict[str, Any]],
    system_prompt: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    rpm_delay: float = DEFAULT_RPM_DELAY,
) -> Optional[ChunkExtractionWrapper]:
    """Gọi Gemini API trích xuất một chunk các bài đăng."""
    chunk_payload = [
        {
            "id": str(a.get("listing_id") or a.get("id")),
            "text": a.get("text") or a.get("description", ""),
        }
        for a in chunk
    ]

    contents = build_ai_contents(
        json.dumps(chunk_payload, ensure_ascii=False)
    )

    attempt = 0

    while True:
        try:
            print(
                f"  [API] Key {api_manager.current_key_number}/{api_manager.total_keys} "
                f"| Model: {api_manager.model_name}"
            )

            response = (
                api_manager.current_client
                .models
                .generate_content(
                    model=api_manager.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=ChunkExtractionWrapper,
                        temperature=0.0,
                    ),
                )
            )

            raw_text = (response.text or "").strip()
            # Bóc tách nếu response bị model bọc trong ```json ... ```
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            return ChunkExtractionWrapper.model_validate_json(raw_text)

        except Exception as e:
            # QUOTA / RATE LIMIT -> Xoay vòng key
            if is_quota_error(e):
                print(
                    f"  [QUOTA] API Key {api_manager.current_key_number} chạm giới hạn quota."
                )
                has_next_key = api_manager.rotate()
                if has_next_key:
                    continue
                print("  [QUOTA] Tất cả API keys đều đã cạn quota.")
                return None

            # LỖI KHÁC -> Exponential backoff retry
            attempt += 1
            if attempt <= max_retries:
                wait = rpm_delay * (2 ** (attempt - 1))
                print(f"  [CANH BAO] Lần thử {attempt} gặp lỗi: {e}")
                print(f"  [RETRY] Đợi {wait:.1f}s trước khi thử lại...")
                time.sleep(wait)
                continue

            print(f"  [LOI] Thất bại sau {max_retries + 1} lần thử: {e}")
            return None
