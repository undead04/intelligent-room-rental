import os
from pathlib import Path
import pytest

from app.core.paths import (
    APP_DIR,
    BACKEND_DIR,
    ENV_FILE_PATH,
    MODELS_CACHE_DIR,
    MODELS_CACHE_DIR_STR,
    PROJECT_ENV_FILE_PATH,
    PROJECT_ROOT,
    PROJECT_ROOT_STR,
)
from app.services.embedding import resolve_model_cache_dir


class TestBackendPaths:
    """Kiểm thử tập trung các định nghĩa đường dẫn của Backend."""

    def test_core_directories_exist(self):
        """Nhóm 1 - Happy Path: Các thư mục cốt lõi phải tồn tại và đúng cấu trúc."""
        assert APP_DIR.is_dir(), "APP_DIR phải là một thư mục tồn tại"
        assert BACKEND_DIR.is_dir(), "BACKEND_DIR phải là một thư mục tồn tại"
        assert PROJECT_ROOT.is_dir(), "PROJECT_ROOT phải là một thư mục tồn tại"

        # Kiểm tra quan hệ thứ bậc
        assert APP_DIR.parent == BACKEND_DIR
        assert BACKEND_DIR.parent == PROJECT_ROOT

        # PROJECT_ROOT phải chứa cả backend và crawler
        assert (PROJECT_ROOT / "backend").is_dir()
        assert (PROJECT_ROOT / "crawler").is_dir()

    def test_models_cache_is_direct_child_of_project_root(self):
        """Nhóm 1 - Happy Path: models_cache bắt buộc phải là con trực tiếp của PROJECT_ROOT."""
        assert MODELS_CACHE_DIR.name == "models_cache"
        assert MODELS_CACHE_DIR.parent == PROJECT_ROOT
        assert MODELS_CACHE_DIR == PROJECT_ROOT / "models_cache"

    def test_env_file_paths(self):
        """Nhóm 1 - Happy Path: Kiểm tra đường dẫn các tệp cấu hình .env."""
        assert ENV_FILE_PATH == BACKEND_DIR / ".env"
        assert PROJECT_ENV_FILE_PATH == PROJECT_ROOT / ".env"

    def test_string_helpers(self):
        """Nhóm 1 - Happy Path: Kiểm tra chuỗi định dạng đường dẫn."""
        assert PROJECT_ROOT_STR == str(PROJECT_ROOT)
        assert MODELS_CACHE_DIR_STR == str(MODELS_CACHE_DIR)

    def test_resolve_model_cache_dir_default(self):
        """Nhóm 1 - Happy Path: resolve_model_cache_dir mặc định trỏ về MODELS_CACHE_DIR."""
        resolved = resolve_model_cache_dir()
        assert Path(resolved).resolve() == MODELS_CACHE_DIR.resolve()
        assert Path(resolved).is_dir()

    def test_resolve_model_cache_dir_with_valid_custom_path(self, tmp_path):
        """Nhóm 2 - Boundary: Truyền custom_path hợp lệ phải được ưu tiên."""
        custom_dir = tmp_path / "custom_cache"
        custom_dir.mkdir()

        resolved = resolve_model_cache_dir(str(custom_dir))
        assert Path(resolved).resolve() == custom_dir.resolve()

    def test_resolve_model_cache_dir_with_invalid_custom_path(self, tmp_path):
        """Nhóm 2 - Boundary: Truyền custom_path không tồn tại hoặc None/Rỗng phải fallback về MODELS_CACHE_DIR."""
        non_existent = str(tmp_path / "does_not_exist")
        resolved = resolve_model_cache_dir(non_existent)
        assert Path(resolved).resolve() == MODELS_CACHE_DIR.resolve()

        resolved_none = resolve_model_cache_dir(None)
        assert Path(resolved_none).resolve() == MODELS_CACHE_DIR.resolve()

        resolved_empty = resolve_model_cache_dir("")
        assert Path(resolved_empty).resolve() == MODELS_CACHE_DIR.resolve()

    def test_resolve_model_cache_dir_with_env_var(self, tmp_path, monkeypatch):
        """Nhóm 4 - Persistence & Environment: Biến môi trường MODELS_CACHE_DIR phải được nhận diện."""
        env_dir = tmp_path / "env_cache"
        env_dir.mkdir()

        monkeypatch.setenv("MODELS_CACHE_DIR", str(env_dir))
        resolved = resolve_model_cache_dir()
        assert Path(resolved).resolve() == env_dir.resolve()
