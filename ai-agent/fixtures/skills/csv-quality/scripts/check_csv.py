#!/usr/bin/env python3
"""Kiểm tra chất lượng CSV công việc (task_id, owner, hours), tính tổng giờ theo người và in JSON ra stdout.

Cách chạy (cwd là workspace):
    python skills/csv-quality/scripts/check_csv.py --input data/tasks.csv --max-hours <ngưỡng>

Exit 0: phân tích thành công, kể cả khi dữ liệu có lỗi chất lượng, có dòng bị loại hoặc có người quá tải.
Exit 1: file không tồn tại/không đọc được, thiếu cột bắt buộc hoặc lỗi parse CSV; thông báo ra stderr.
Exit 2: thiếu --max-hours hoặc giá trị không phải số hữu hạn không âm; thông báo ra stderr.
Script chỉ đọc, không sửa CSV.

Quy tắc tính tổng giờ:
- task_id, owner, hours được bỏ khoảng trắng đầu/cuối; owner phân biệt hoa/thường.
- Mỗi task_id không rỗng chỉ giữ lần xuất hiện đầu tiên trong file (kể cả khi lần đầu không hợp lệ);
  các lần sau bị loại vì duplicate_id.
- Chỉ cộng dòng có đúng số trường, task_id và owner không rỗng, hours là số hữu hạn không âm.
- Quá tải khi tổng giờ lớn hơn ngưỡng (bằng ngưỡng không phải quá tải).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys

REQUIRED_COLUMNS = ("task_id", "owner", "hours")
# Thứ tự cố định của mã lý do loại dòng trong excluded_rows.
EXCLUSION_REASONS = ("wrong_field_count", "missing_task_id", "duplicate_id", "missing_owner", "invalid_hours")


class InputError(Exception):
    pass


def parse_hours(raw: str | None) -> float | None:
    """Số giờ hợp lệ: số hữu hạn, không âm. Trả None nếu không hợp lệ."""
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def max_hours_arg(raw: str) -> float:
    value = parse_hours(raw)
    if value is None:
        raise argparse.ArgumentTypeError(f"'{raw}' không phải số hữu hạn không âm.")
    return value


def as_number(value: float) -> int | float:
    """In 9 thay vì 9.0 khi là số nguyên; cắt sai số cộng dồn của float."""
    value = round(value, 9)
    return int(value) if value.is_integer() else value


def analyze(path: str, max_hours: float) -> dict:
    try:
        handle = open(path, encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError(f"Không đọc được file {path}: {exc.strerror or exc}") from exc
    with handle:
        reader = csv.reader(handle, strict=True)
        try:
            header = next(reader, None)
            if header is None:
                raise InputError(f"File {path} rỗng, không có header.")
            columns = [c.strip() for c in header]
            missing = [c for c in REQUIRED_COLUMNS if c not in columns]
            if missing:
                raise InputError(f"Thiếu cột bắt buộc: {', '.join(missing)}. Header hiện có: {', '.join(columns)}")
            index = {name: columns.index(name) for name in REQUIRED_COLUMNS}

            row_count = 0
            missing_owner = 0
            invalid_hours = 0
            first_seen: dict[str, int] = {}
            duplicate_ids: list[str] = []
            issues: list[dict] = []
            hours_by_owner: dict[str, list[float]] = {}
            excluded_rows: list[dict] = []
            for row in reader:
                line = reader.line_num
                if not any(cell.strip() for cell in row):
                    continue  # bỏ qua dòng trống
                row_count += 1

                def cell(name: str) -> str:
                    position = index[name]
                    return row[position].strip() if position < len(row) else ""

                task_id, owner, hours = cell("task_id"), cell("owner"), cell("hours")
                reasons: set[str] = set()
                if len(row) != len(columns):
                    reasons.add("wrong_field_count")
                    issues.append({"line": line, "column": None, "type": "wrong_field_count", "task_id": task_id or None,
                                   "message": f"Có {len(row)} trường, header có {len(columns)} cột."})
                if not task_id:
                    reasons.add("missing_task_id")
                    issues.append({"line": line, "column": "task_id", "type": "missing_task_id", "task_id": None,
                                   "message": "task_id trống."})
                elif task_id in first_seen:
                    reasons.add("duplicate_id")
                    if task_id not in duplicate_ids:
                        duplicate_ids.append(task_id)
                    issues.append({"line": line, "column": "task_id", "type": "duplicate_id", "task_id": task_id,
                                   "message": f"task_id {task_id} đã xuất hiện ở line {first_seen[task_id]}."})
                else:
                    first_seen[task_id] = line  # lần đầu luôn được giữ làm mốc, kể cả khi dòng đó không hợp lệ
                if not owner:
                    reasons.add("missing_owner")
                    missing_owner += 1
                    issues.append({"line": line, "column": "owner", "type": "missing_owner", "task_id": task_id or None,
                                   "message": "owner trống."})
                value = parse_hours(hours)
                if value is None:
                    reasons.add("invalid_hours")
                    invalid_hours += 1
                    issues.append({"line": line, "column": "hours", "type": "invalid_hours", "task_id": task_id or None,
                                   "value": hours, "message": f"hours '{hours}' không phải số hữu hạn không âm."})

                if reasons:
                    excluded_rows.append({"line": line, "task_id": task_id or None,
                                          "reasons": [r for r in EXCLUSION_REASONS if r in reasons]})
                else:
                    hours_by_owner.setdefault(owner, []).append(value)
        except csv.Error as exc:
            raise InputError(f"Lỗi parse CSV ở line {reader.line_num}: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise InputError(f"File {path} không phải UTF-8: {exc}") from exc

    # làm tròn trước khi so ngưỡng để 0.1 + 0.2 không thành "lớn hơn" 0.3
    totals = {owner: as_number(math.fsum(values)) for owner, values in sorted(hours_by_owner.items())}
    return {
        "input": path,
        "row_count": row_count,
        "missing_owner_count": missing_owner,
        "invalid_hours_count": invalid_hours,
        "duplicate_id_count": len(duplicate_ids),
        "duplicate_ids": duplicate_ids,
        "issues": sorted(issues, key=lambda item: item["line"]),
        "max_hours": as_number(max_hours),
        "hours_by_owner": totals,
        "overloaded_owners": [{"owner": owner, "total_hours": total} for owner, total in totals.items() if total > max_hours],
        "excluded_rows": sorted(excluded_rows, key=lambda item: item["line"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra chất lượng CSV công việc (task_id, owner, hours) và tổng giờ theo người.")
    parser.add_argument("--input", required=True, help="Đường dẫn CSV, ví dụ data/tasks.csv")
    parser.add_argument("--max-hours", required=True, type=max_hours_arg,
                        help="Ngưỡng giờ do người dùng cung cấp (số hữu hạn không âm). Quá tải khi tổng giờ > ngưỡng.")
    args = parser.parse_args(argv)
    try:
        result = analyze(args.input, args.max_hours)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
