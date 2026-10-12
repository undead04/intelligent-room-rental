"""csv-quality script: thống kê fixture, tổng giờ theo người, dòng bị loại, --max-hours, lỗi input/schema/parse."""

import json
import subprocess
import sys

import pytest

import paths

SCRIPT = paths.FIXTURES_DIR / "skills" / "csv-quality" / "scripts" / "check_csv.py"


def run(path, *extra, max_hours="8"):
    args = [sys.executable, str(SCRIPT), "--input", str(path)]
    if max_hours is not None:
        args += ["--max-hours", max_hours]
    return subprocess.run(args + list(extra), capture_output=True, text=True, encoding="utf-8", timeout=10)


def run_json(path, max_hours="8"):
    result = run(path, max_hours=max_hours)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def write_csv(tmp_path, text, name="t.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_fixture_statistics():
    data = run_json(paths.FIXTURES_DIR / "data" / "tasks.csv")
    assert data["row_count"] == 6
    assert data["missing_owner_count"] == 1
    assert data["invalid_hours_count"] == 1
    assert data["duplicate_id_count"] == 1
    assert data["duplicate_ids"] == ["T02"]
    assert [(i["line"], i["column"], i["type"]) for i in data["issues"]] == [
        (4, "owner", "missing_owner"),
        (5, "hours", "invalid_hours"),
        (6, "task_id", "duplicate_id"),
    ]
    assert "total_hours" not in data


@pytest.mark.parametrize("hours", ["NaN", "nan", "Infinity", "-inf", "-1", ""])
def test_non_finite_negative_or_empty_hours_rejected(tmp_path, hours):
    data = run_json(write_csv(tmp_path, f"task_id,owner,hours\nT01,Lan,{hours}\n"))
    assert data["invalid_hours_count"] == 1
    assert data["issues"][0]["line"] == 2
    assert data["hours_by_owner"] == {}
    assert data["excluded_rows"] == [{"line": 2, "task_id": "T01", "reasons": ["invalid_hours"]}]


def test_clean_data_exit_0_without_issues(tmp_path):
    data = run_json(write_csv(tmp_path, "task_id,owner,hours\nT01,Lan,4\nT02,Minh,2.5\n"))
    assert data["issues"] == [] and data["excluded_rows"] == []
    assert data["hours_by_owner"] == {"Lan": 4, "Minh": 2.5}


# --- tổng giờ theo người -------------------------------------------------------------------------

def test_workload_threshold_8():
    data = run_json(paths.FIXTURES_DIR / "data" / "workload.csv", max_hours="8")
    assert data["max_hours"] == 8
    assert data["hours_by_owner"] == {"Lan": 9, "Minh": 3}
    assert data["overloaded_owners"] == [{"owner": "Lan", "total_hours": 9}]
    assert data["excluded_rows"] == [
        {"line": 5, "task_id": "T04", "reasons": ["invalid_hours"]},
        {"line": 6, "task_id": "T02", "reasons": ["duplicate_id"]},
        {"line": 7, "task_id": "T05", "reasons": ["missing_owner"]},
    ]
    # thống kê chất lượng cũ vẫn tính trên toàn bộ dòng dữ liệu
    assert (data["row_count"], data["missing_owner_count"], data["invalid_hours_count"], data["duplicate_ids"]) == (6, 1, 1, ["T02"])


def test_workload_threshold_9_equal_is_not_overloaded():
    data8 = run_json(paths.FIXTURES_DIR / "data" / "workload.csv", max_hours="8")
    data9 = run_json(paths.FIXTURES_DIR / "data" / "workload.csv", max_hours="9")
    assert data9["max_hours"] == 9
    assert data9["overloaded_owners"] == []
    assert data9["hours_by_owner"] == data8["hours_by_owner"]
    assert data9["excluded_rows"] == data8["excluded_rows"]


def test_first_occurrence_with_invalid_hours_still_claims_id():
    """ID xuất hiện lần đầu với hours lỗi: lần sau vẫn là duplicate, không thay bằng "lần hợp lệ đầu tiên"."""
    data = run_json(paths.FIXTURES_DIR / "data" / "workload-edge.csv", max_hours="0")
    assert data["max_hours"] == 0
    assert data["hours_by_owner"] == {"Minh": 0}
    assert data["overloaded_owners"] == []
    assert data["excluded_rows"] == [
        {"line": 2, "task_id": "E01", "reasons": ["invalid_hours"]},
        {"line": 3, "task_id": "E01", "reasons": ["duplicate_id"]},
    ]
    assert "Lan" not in data["hours_by_owner"]


def test_all_reasons_listed_once_in_fixed_order(tmp_path):
    csv_text = "task_id,owner,hours\nT01,Lan,1\nT01,,abc\n,Lan,2\nT02,Lan,1,extra\n\nT03, Lan ,2\nT04,lan,3\n"
    data = run_json(write_csv(tmp_path, csv_text))
    assert data["excluded_rows"] == [
        {"line": 3, "task_id": "T01", "reasons": ["duplicate_id", "missing_owner", "invalid_hours"]},
        {"line": 4, "task_id": None, "reasons": ["missing_task_id"]},
        {"line": 5, "task_id": "T02", "reasons": ["wrong_field_count"]},
    ]
    # dòng trống bị bỏ qua; khoảng trắng được bỏ; khác hoa/thường là người khác
    assert data["row_count"] == 6
    assert data["hours_by_owner"] == {"Lan": 3, "lan": 3}


def test_overloaded_sorted_by_name_and_decimal_threshold(tmp_path):
    data = run_json(write_csv(tmp_path, "task_id,owner,hours\nA,Minh,0.1\nB,Minh,0.2\nC,An,0.4\nD,Hoa,0.3\n"), max_hours="0.3")
    assert data["hours_by_owner"] == {"An": 0.4, "Hoa": 0.3, "Minh": 0.3}
    assert data["overloaded_owners"] == [{"owner": "An", "total_hours": 0.4}]


# --- tham số --max-hours -------------------------------------------------------------------------

def test_missing_max_hours_exit_non_zero(tmp_path):
    result = run(paths.FIXTURES_DIR / "data" / "workload.csv", max_hours=None)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "--max-hours" in result.stderr


@pytest.mark.parametrize("value", ["abc", "-1", "nan", "inf", "-Infinity", ""])
def test_invalid_max_hours_exit_non_zero(value):
    result = run(paths.FIXTURES_DIR / "data" / "workload.csv", max_hours=value)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "--max-hours" in result.stderr


# --- lỗi input giữ nguyên hành vi cũ ------------------------------------------------------------

def test_missing_file_exit_1(tmp_path):
    result = run(tmp_path / "khong-co.csv")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Không đọc được file" in result.stderr


def test_missing_column_exit_1(tmp_path):
    result = run(write_csv(tmp_path, "task_id,owner\nT01,Lan\n"))
    assert result.returncode == 1
    assert "Thiếu cột bắt buộc: hours" in result.stderr


def test_parse_error_exit_1(tmp_path):
    result = run(write_csv(tmp_path, 'task_id,owner,hours\nT01,"La"n,4\n'))
    assert result.returncode == 1
    assert "Lỗi parse CSV" in result.stderr


@pytest.mark.parametrize("name", ["tasks.csv", "workload.csv", "workload-edge.csv"])
def test_script_does_not_modify_input(name):
    source = paths.FIXTURES_DIR / "data" / name
    before = source.read_bytes()
    run(source)
    assert source.read_bytes() == before


def test_workspace_skill_synced_with_fixtures():
    fixture_skill = paths.FIXTURES_DIR / "skills" / "csv-quality"
    workspace_skill = paths.WORKSPACE_DIR / "skills" / "csv-quality"
    for rel in ("SKILL.md", "references/report-template.md", "scripts/check_csv.py"):
        assert (workspace_skill / rel).read_bytes() == (fixture_skill / rel).read_bytes(), rel
