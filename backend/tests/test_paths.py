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

    # ==============================================================================
    # BỔ SUNG CÁC BÀI TEST BIÊN & BẺ GÃY CODE (ANTI-CHEATING RIGOROUS TESTS)
    # ==============================================================================

    def test_resolve_model_cache_dir_with_whitespace_only(self):
        """Nhóm 2 - Boundary: Chuỗi chỉ chứa khoảng trắng ('   ') phải fallback về MODELS_CACHE_DIR."""
        resolved = resolve_model_cache_dir("   ")
        assert Path(resolved).resolve() == MODELS_CACHE_DIR.resolve()

    def test_resolve_model_cache_dir_when_custom_path_is_file(self, tmp_path):
        """Nhóm 2 - Boundary: Tham số custom_path là file thông thường (không phải thư mục)
        thì hàm resolve_model_cache_dir KHÔNG được trả về file mà phải fallback về thư mục hợp lệ.
        """
        regular_file = tmp_path / "not_a_dir.txt"
        regular_file.write_text("This is a regular file, not a directory.")

        resolved = resolve_model_cache_dir(str(regular_file))
        assert Path(resolved).resolve() == MODELS_CACHE_DIR.resolve()
        assert Path(resolved).is_dir(), "Kết quả resolve_model_cache_dir luôn phải là thư mục"

    def test_resolve_model_cache_dir_with_vietnamese_diacritics_and_spaces(self, tmp_path):
        """Nhóm 2 - Boundary: Đường dẫn có chứa khoảng trắng và dấu tiếng Việt (ví dụ: 'Đồ Án tốt nghiệp')."""
        vn_dir = tmp_path / "Đồ Án Tốt Nghiệp Cache Thử Nghiệm" / "Thư Mục Mô Hình 2026"
        vn_dir.mkdir(parents=True)

        resolved = resolve_model_cache_dir(str(vn_dir))
        assert Path(resolved).resolve() == vn_dir.resolve()
        assert Path(resolved).is_dir()

    def test_resolve_model_cache_dir_with_path_object(self, tmp_path):
        """Nhóm 2 - Boundary: Truyền trực tiếp đối tượng Path thay vì str."""
        custom_dir = tmp_path / "path_obj_dir"
        custom_dir.mkdir()

        resolved = resolve_model_cache_dir(custom_dir)
        assert Path(resolved).resolve() == custom_dir.resolve()

    def test_resolve_model_cache_dir_when_env_is_invalid_fallback_safe(self, tmp_path, monkeypatch):
        """Nhóm 4 - Persistence & Environment: Biến môi trường MODELS_CACHE_DIR trỏ tới thư mục không tồn tại
        -> fallback an toàn về root MODELS_CACHE_DIR.
        """
        monkeypatch.setenv("MODELS_CACHE_DIR", str(tmp_path / "ghost_models_dir"))

        resolved = resolve_model_cache_dir()
        assert Path(resolved).resolve() == MODELS_CACHE_DIR.resolve()
        assert Path(resolved).is_dir()

    def test_resolve_model_cache_dir_when_env_is_file(self, tmp_path, monkeypatch):
        """Nhóm 4 - Persistence & Environment: Biến môi trường MODELS_CACHE_DIR trỏ tới file thông thường
        -> không được trả về file mà phải fallback an toàn.
        """
        fake_file = tmp_path / "fake_cache_file.bin"
        fake_file.write_bytes(b"data")

        monkeypatch.setenv("MODELS_CACHE_DIR", str(fake_file))

        resolved = resolve_model_cache_dir()
        assert Path(resolved).resolve() == MODELS_CACHE_DIR.resolve()
        assert Path(resolved).is_dir()

    def test_resolve_model_cache_dir_priority_hierarchy(self, tmp_path, monkeypatch):
        """Nhóm 3 - State Mutation & Hierarchy: Kiểm tra thứ tự ưu tiên:
        custom_path (hợp lệ) > MODELS_CACHE_DIR (hợp lệ) > root default.
        """
        custom_dir = tmp_path / "custom_priority"
        custom_dir.mkdir()

        models_dir = tmp_path / "models_env_dir"
        models_dir.mkdir()

        monkeypatch.setenv("MODELS_CACHE_DIR", str(models_dir))

        # 1. custom_path cao nhất
        assert Path(resolve_model_cache_dir(str(custom_dir))).resolve() == custom_dir.resolve()

        # 2. Không có custom_path -> MODELS_CACHE_DIR
        assert Path(resolve_model_cache_dir()).resolve() == models_dir.resolve()

        # 3. MODELS_CACHE_DIR bị xóa -> Default root
        monkeypatch.delenv("MODELS_CACHE_DIR", raising=False)
        assert Path(resolve_model_cache_dir()).resolve() == MODELS_CACHE_DIR.resolve()

    def test_paths_immutability_and_constants_integrity(self):
        """Nhóm 3 - State Mutation: Các biến hằng số đường dẫn phải giữ nguyên tính toàn vẹn."""
        from app.core import paths

        assert isinstance(paths.PROJECT_ROOT, Path)
        assert isinstance(paths.MODELS_CACHE_DIR, Path)
        assert isinstance(paths.BACKEND_DIR, Path)
        assert isinstance(paths.APP_DIR, Path)

        # Đảm bảo PROJECT_ROOT là thư mục cha cấp 2 của APP_DIR
        assert paths.APP_DIR.parent.parent == paths.PROJECT_ROOT
