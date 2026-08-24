#!/usr/bin/env python3
"""Ghép dữ liệu + template thành dashboard HTML độc lập."""
import json, sys, os, datetime
here = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "data.json")))
out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "dashboard.html")
parts = [open(os.path.join(here, f), encoding="utf-8").read()
         for f in ("tpl_head.html", "tpl_body.html")]
js = open(os.path.join(here, "tpl_js.html"), encoding="utf-8").read()
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = parts[0] + parts[1] + f'<script id="payload">window.__ARENA__={payload};</script>\n' + js
open(out, "w", encoding="utf-8").write(html)
print(f"→ {out}  ({os.path.getsize(out)/1024:.0f} KB)  ·  chốt {data['generated']}")
