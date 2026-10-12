# Báo cáo chất lượng dữ liệu và tải công việc: `{đường dẫn CSV}`

Công cụ: `skills/csv-quality/scripts/check_csv.py --max-hours {max_hours}` | exit code: {exit_code}

## Tổng quan chất lượng
| Chỉ số | Giá trị |
|---|---|
| Số dòng dữ liệu (không tính header) | {row_count} |
| Dòng thiếu owner | {missing_owner_count} |
| Dòng hours không hợp lệ | {invalid_hours_count} |
| Số task_id bị lặp (distinct) | {duplicate_id_count} ({duplicate_ids}) |

## Chi tiết lỗi
| Line | Cột | Loại | task_id | Mô tả |
|---|---|---|---|---|
| {line} | {column} | {type} | {task_id} | {message} |

## Tải công việc theo người

Ngưỡng: **{max_hours} giờ** (do người dùng cung cấp). Quá tải khi tổng giờ **lớn hơn** ngưỡng; bằng ngưỡng không tính là quá tải.

Tổng giờ chỉ tính các dòng hợp lệ (xem mục "Dòng bị loại khỏi tổng giờ").

| Owner | Tổng giờ | Vượt ngưỡng? |
|---|---|---|
| {owner} | {total_hours} | {Có / Không} |

### Người vượt ngưỡng
- {owner}: {total_hours} giờ (vượt {total_hours − max_hours} giờ)
- Nếu `overloaded_owners` rỗng: "Không ai vượt ngưỡng {max_hours} giờ."

### Dòng bị loại khỏi tổng giờ
| Line | task_id | Lý do |
|---|---|---|
| {line} | {task_id hoặc "(trống)"} | {tất cả mã lý do, kèm giải thích ngắn} |

## Đánh giá
- Mức độ tin cậy của tổng giờ: nêu số dòng bị loại và ảnh hưởng (ví dụ giờ của dòng bị loại không được cộng cho ai).

## Khuyến nghị
- {Cách sửa đề xuất cho từng nhóm lỗi; không tự sửa file nguồn}
