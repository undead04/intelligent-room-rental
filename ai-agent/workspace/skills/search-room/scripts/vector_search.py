#!/usr/bin/env python3
"""Bước 2: Tìm phòng bằng vector search (Đã sync với FastAPI Endpoint).

POST {BASE}/listings/vector-search?limit=10&offset=0&city_id=...
Body: JSON {"query": "...", "amenities": [...]}
"""
import argparse
import json
import sys
from typing import Any, Dict, Optional

from _common import build_url, emit, fail, request, setup_utf8, strip_keys, unwrap


def build_request_data(args) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Tách biệt params (Query String) và payload (JSON Body) chuẩn theo FastAPI contract."""
    
    # 1. Query Parameters (Khớp với Depends(VectorSearchRequest))
    params: Dict[str, Any] = {
        "limit": args.limit,
        "offset": args.offset,
    }
    if args.city_id is not None:
        params["city_id"] = args.city_id
    if args.district_id is not None:
        params["district_id"] = args.district_id
    if args.ward_id is not None:
        params["ward_id"] = args.ward_id
    if args.min_price is not None:
        params["min_price"] = args.min_price
    if args.max_price is not None:
        params["max_price"] = args.max_price
    if args.min_area is not None:
        params["min_area"] = args.min_area
    if args.max_area is not None:
        params["max_area"] = args.max_area
    if args.lat is not None:
        params["lat"] = args.lat
    if args.lng is not None:
        params["lng"] = args.lng

    # 2. Body Payload (Khớp với Body(...) trong FastAPI)
    if args.body_file:
        with open(args.body_file, encoding="utf-8") as f:
            body = json.load(f)
    else:
        body = {"query": args.query}
        if args.amenities:
            body["amenities"] = args.amenities

    if args.extra_json:
        try:
            body.update(json.loads(args.extra_json))
        except ValueError as e:
            fail(f"--extra-json không phải JSON hợp lệ: {e}")

    return params, body


def main() -> None:
    setup_utf8()
    ap = argparse.ArgumentParser(description="Vector search phòng trọ")
    ACK = "sr-7f3a"
    ap.add_argument("--ack", help="Mã ACK-CODE ở đầu references/api.md")
    # Query & Body args
    ap.add_argument("--query", required=True, help="Mô tả nhu cầu bằng ngôn ngữ tự nhiên")
    ap.add_argument("--amenities", action="append", default=[], help="Tiện ích (VD: --amenities wifi --amenities parking)")
    
    # Query Filter args (Khớp VectorSearchRequest)
    ap.add_argument("--city-id", type=int, dest="city_id")
    ap.add_argument("--district-id", type=int, dest="district_id")
    ap.add_argument("--ward-id", type=int, dest="ward_id")
    ap.add_argument("--min-price", type=float, dest="min_price")
    ap.add_argument("--max-price", type=float, dest="max_price")
    ap.add_argument("--min-area", type=float, dest="min_area")
    ap.add_argument("--max-area", type=float, dest="max_area")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lng", type=float)
    
    # Pagination & Control
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--extra-json", help='JSON gộp thêm vào body')
    ap.add_argument("--body-file", help="Đọc toàn bộ body từ file JSON")
    ap.add_argument("--keep-vectors", action="store_true", help="Không lược bỏ field embedding")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ in request, không gọi API")

    args = ap.parse_args()
    
    if args.ack != ACK:
        sys.exit("LỖI: Chưa đọc references/api.md. Hãy đọc file đó, "
                "lấy ACK-CODE ở dòng đầu rồi chạy lại với --ack <mã>.")
        
    params, body = build_request_data(args)

    if args.dry_run:
        emit({
            "ok": True,
            "method": "POST",
            "url": build_url("/listings/vector-search", params),
            "body": body
        })
        return

    # Thực hiện request
    res = request("POST", "/listings/vector-search", params=params, body=body)
    data = unwrap(res)

    if not args.keep_vectors:
        data = strip_keys(data)

    emit({
        "ok": True,
        "request": {"params": params, "body": body},
        "count": len(data) if isinstance(data, list) else None,
        "listings": data,
    })


if __name__ == "__main__":
    main()