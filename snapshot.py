#!/usr/bin/env python3
"""Xuất một bản chụp tĩnh của dashboard (để publish/chia sẻ, không realtime)."""
import sys, os, datetime, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app

hub = sys.argv[1] if len(sys.argv) > 1 else next(iter(app.HUBS))
days = int(sys.argv[2]) if len(sys.argv) > 2 else 28
out = sys.argv[3] if len(sys.argv) > 3 else "snapshot.html"

main = app.render_main(hub, days)
now = datetime.datetime.now()

banner = (
    '<div class="snapnote"><strong>Bản chụp tĩnh</strong> — số liệu đóng băng lúc '
    f'{now.strftime("%H:%M")} ngày {now.strftime("%d/%m/%Y")}. '
    'Bản realtime tự làm mới chạy trên máy bằng <code>python3 app.py</code>.</div>'
)

EXTRA = """
.snapnote{border:1px solid var(--line);border-left:3px solid var(--peak);background:var(--card);
 padding:12px 16px;margin:18px 0 0;font-size:13.5px;color:var(--ink2)}
.snapnote code{font-family:var(--fm);font-size:12.5px;background:var(--h0);padding:1px 5px}
"""

html = f"""<title>Arena Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;600;800&family=IBM+Plex+Mono:wght@500;600&display=swap">
<style>{app.CSS}{EXTRA}</style>
<div class="wrap">
<header class="top">
  <p class="brand">arena by lona&amp;co · {app.esc(hub)}</p>
  <h1>Bảng điều khiển vận hành</h1>
  <p class="sub">Occupancy, giá, sân và khách hàng — đọc thẳng từ Mewin Partner API.</p>
  {banner}
</header>
<main>{main}</main></div>"""

# bỏ chấm nhấp nháy "live" vì bản tĩnh không realtime
html = html.replace('<span class="live-dot"></span>', '')
html = re.sub(r'<h2>Lịch hôm nay\s*</h2>', '<h2>Lịch ngày chụp</h2>', html)

open(out, "w").write(html)
print(f"Đã ghi {out} ({len(html):,} bytes) — hub {hub}, {days} ngày")
