#!/usr/bin/env python3
"""Bước 1A: đổi địa chỉ/địa danh cố định thành toạ độ.

GET {BASE}/geocode?q=...&hint=...

Ví dụ:
  python scripts/geocode.py --q "UIT"
  python scripts/geocode.py --q "ĐH Bách Khoa" --hint "Đà Nẵng"
"""
import argparse
import sys

from _common import emit, fail, request, setup_utf8, unwrap


def main() -> None:
    setup_utf8()
    ap = argparse.ArgumentParser(description="Geocode địa chỉ cố định -> lat/lon")
    ACK = "sr-7f3a"
    ap.add_argument("--ack", help="Mã ACK-CODE ở đầu references/api.md")
    ap.add_argument("--q", required=True, help="Địa chỉ hoặc địa danh, vd: 'Trường ĐH CNTT'")
    ap.add_argument("--hint", help="Tỉnh/thành để thu hẹp khi tên bị trùng, vd: 'Đà Nẵng'")

    args = ap.parse_args()

    if args.ack != ACK:
        sys.exit("LỖI: Chưa đọc references/api.md. Hãy đọc file đó, "
                "lấy ACK-CODE ở dòng đầu rồi chạy lại với --ack <mã>.")

    data = unwrap(request("GET", "/geocode", params={"q": args.q, "hint": args.hint}))
    if not isinstance(data, dict) or "lat" not in data or "lon" not in data:
        fail("Phản hồi geocode thiếu lat/lon", data)

    emit({
        "ok": True,
        "query": args.q,
        "lat": data["lat"],
        "lon": data["lon"],
        "formatted_address": data.get("formatted_address"),
        "provider": data.get("provider"),
    })


if __name__ == "__main__":
    main()