#!/usr/bin/env python3
"""Tạo payload BẢN HẠN CHẾ: lược sạch mọi trường tiền, không chỉ ẩn trên giao diện."""
import json, sys, copy

src = sys.argv[1] if len(sys.argv) > 1 else "data.json"
dst = sys.argv[2] if len(sys.argv) > 2 else "data-team.json"
d = json.load(open(src, encoding="utf-8"))
d["masked"] = True

for h in d.get("hubs", []):
    h.pop("priceGrid", None)          # bảng giá = doanh thu
    h.pop("priceRules", None)
    h["con"] = [[r[0], r[1], r[3], r[4]] for r in h.get("con", [])]   # bỏ cột tiền

sysd = d.get("system")
if sysd:
    for h in sysd.get("hubs", []):
        h.pop("money", None); h.pop("byType", None)
        h["series"] = [{"label": s["label"], "days": s["days"], "full": s["full"]}
                       for s in h.get("series", [])]
    sysd["daily"] = {k: [[r[0], r[2], r[4]] for r in v]           # chỉ còn giờ cố định / giờ vãng lai
                     for k, v in (sysd.get("daily") or {}).items()}

out = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
open(dst, "w", encoding="utf-8").write(out)

# kiểm tra: không còn chuỗi số tiền lớn nào lọt lại
import re
big = re.findall(r'\b\d{6,}\b', out)
susp = [x for x in big if x.endswith("000") and len(x) >= 6]
print(f"→ {dst} ({len(out)/1024:.0f} KB) · masked=True")
print(f"   số ≥6 chữ số kết thúc bằng 000 còn sót: {len(susp)}"
      + (f" (ví dụ {susp[:5]})" if susp else " — sạch"))
