#!/usr/bin/env python3
"""Chặn không cho publish payload thiếu dữ liệu.

API quanlysan thỉnh thoảng timeout giữa chừng. build_data.py vẫn ghi file,
nhưng chuỗi ngày của hub bị timeout sẽ ngắn đi (vd 207 ngày -> 82 ngày).
Nếu cứ publish, dashboard sẽ hiện biểu đồ cụt mà không ai biết.

Thoát 0 = dữ liệu đủ, cho phép publish.
Thoát 1 = thiếu, deploy.sh sẽ thử lại rồi bỏ qua kỳ này.
"""
import json, sys

MIN_DAYS = 150          # chuỗi ngày tối thiểu mỗi hub
NEED_HUBS = 3           # phải đủ 3 hub trong Report API

src = sys.argv[1] if len(sys.argv) > 1 else "data.json"
d = json.load(open(src))
sysd = d.get("system") or {}
hubs = sysd.get("hubs") or []
bad = []

if len(hubs) < NEED_HUBS:
    bad.append(f"chỉ có {len(hubs)}/{NEED_HUBS} hub trong Report API")

for h in hubs:
    n = len([x for x in (sysd.get("daily", {}).get(h["name"]) or [])])
    if n < MIN_DAYS:
        bad.append(f"{h['name']}: chuỗi ngày chỉ {n} (cần >= {MIN_DAYS})")
    if not h.get("money") or not h.get("hours"):
        bad.append(f"{h['name']}: thiếu doanh thu hoặc giờ-sân")

if len(d.get("hubs") or []) < NEED_HUBS:
    bad.append(f"chỉ có {len(d.get('hubs') or [])}/{NEED_HUBS} hub chi tiết (token hỏng?)")

if bad:
    print("   KHÔNG ĐẠT — " + "; ".join(bad))
    sys.exit(1)
print(f"   dữ liệu đạt: {len(hubs)} hub, chuỗi ngày ngắn nhất "
      f"{min(len(sysd.get('daily', {}).get(h['name']) or []) for h in hubs)} ngày")
