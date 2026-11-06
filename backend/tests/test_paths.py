import os
from pathlib import Path
import pytest

from app.core.paths import (
    APP_DIR,
    BACKEND_DIR,
    MODELS_CACHE_DIR,
    PROJECT_ROOT,
)
from app.services.embedding import resolve_model_cache_dir


class TestBackendPaths:
    """Kiểm thử tập trung các định nghĩa đường dẫn cốt lõi của Backend."""

    def test_core_directories_structure(self):
        """Kiểm tra các thư mục cốt lõi phải tồn tại và đúng cấu trúc phân cấp."""
        assert APP_DIR.is_dir(), "APP_DIR phải là một thư mục tồn tại"
        assert BACKEND_DIR.is_dir(), "BACKEND_DIR phải là một thư mục tồn tại"
        assert PROJECT_ROOT.is_dir(), "PROJECT_ROOT phải là một thư mục tồn tại"
        assert MODELS_CACHE_DIR == PROJECT_ROOT / "models_cache"

        assert APP_DIR.parent == BACKEND_DIR
        assert BACKEND_DIR.parent == PROJECT_ROOT

    def test_resolve_model_cache_dir_priority_and_custom(self, tmp_path, monkeypatch):
        """Kiểm tra thứ tự ưu tiên: custom_path > biến môi trường MODELS_CACHE_DIR > default root."""
        # 1. Mặc định trỏ về MODELS_CACHE_DIR
        resolved_default = resolve_model_cache_dir()
        assert Path(resolved_default).resolve() == MODELS_CACHE_DIR.resolve()
        assert Path(resolved_default).is_dir()

        # 2. Ưu tiên biến môi trường MODELS_CACHE_DIR
        env_dir = tmp_path / "env_cache"
        env_dir.mkdir()
        monkeypatch.setenv("MODELS_CACHE_DIR", str(env_dir))
        assert Path(resolve_model_cache_dir()).resolve() == env_dir.resolve()

        # 3. custom_path có độ ưu tiên cao nhất
        custom_dir = tmp_path / "custom_cache"
        custom_dir.mkdir()
        assert Path(resolve_model_cache_dir(str(custom_dir))).resolve() == custom_dir.resolve()
        assert Path(resolve_model_cache_dir(custom_dir)).resolve() == custom_dir.resolve()

    def test_resolve_model_cache_dir_fallbacks(self, tmp_path, monkeypatch):
        """Kiểm tra fallback an toàn khi đường dẫn không hợp lệ hoặc là file thông thường."""
        # Custom path không tồn tại hoặc rỗng/whitespace -> fallback về default
        assert Path(resolve_model_cache_dir(str(tmp_path / "ghost"))).resolve() == MODELS_CACHE_DIR.resolve()
        assert Path(resolve_model_cache_dir("   ")).resolve() == MODELS_CACHE_DIR.resolve()
        assert Path(resolve_model_cache_dir(None)).resolve() == MODELS_CACHE_DIR.resolve()

        # Custom path hoặc env var là file (không phải thư mục) -> fallback về default
        regular_file = tmp_path / "not_a_dir.txt"
        regular_file.write_text("file content")
        assert Path(resolve_model_cache_dir(str(regular_file))).resolve() == MODELS_CACHE_DIR.resolve()

        monkeypatch.setenv("MODELS_CACHE_DIR", str(regular_file))
        assert Path(resolve_model_cache_dir()).resolve() == MODELS_CACHE_DIR.resolve()
