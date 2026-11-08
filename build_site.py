#!/usr/bin/env python3
"""Dựng site/ để đưa lên GitHub Pages.

    python3 build_site.py <CODE_FULL> <CODE_TEAM>

site/index.html      trang nhập mã + khung dashboard (không nhúng sẵn dữ liệu)
site/d/team.json     payload bản team — đã lược sạch mọi trường tiền
site/d/full.enc.json payload đầy đủ, mã hoá AES-256-GCM, khoá dẫn xuất từ CODE_FULL

Repo có thể để công khai: bản đầy đủ chỉ tồn tại dưới dạng ciphertext.
"""
import hashlib, json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crypt import encrypt, ITER

here = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) < 3:
    sys.exit("Dùng: python3 build_site.py <CODE_FULL> <CODE_TEAM>")
c_full, c_team = sys.argv[1].strip(), sys.argv[2].strip()
if c_full == c_team:
    sys.exit("Hai mã phải khác nhau.")
if len(c_full) < 10:
    sys.exit("CODE_FULL tối thiểu 10 ký tự — nó là khoá giải mã, đừng đặt ngắn.")
if len(c_team) < 6:
    sys.exit("CODE_TEAM tối thiểu 6 ký tự.")

read = lambda f: open(os.path.join(here, f), encoding="utf-8").read()
site = os.path.join(here, "docs")   # GitHub Pages phục vụ từ /docs
fonts = os.path.join(site, "fonts")

# GIỮ LẠI docs/fonts/ — file font có license nằm ở đó, dựng lại không được xoá
keep = None
if os.path.isdir(fonts):
    keep = os.path.join(here, ".fonts.bak")
    shutil.rmtree(keep, ignore_errors=True)
    shutil.copytree(fonts, keep)

shutil.rmtree(site, ignore_errors=True)
os.makedirs(os.path.join(site, "d"))

if keep:
    shutil.copytree(keep, fonts)
    shutil.rmtree(keep, ignore_errors=True)
    n = sum(len(f) for _, _, f in os.walk(fonts))
    print(f"  giữ lại docs/fonts/ ({n} file)")
else:
    os.makedirs(fonts, exist_ok=True)

# 1) dữ liệu
if not os.path.exists(os.path.join(here, "data-team.json")):
    subprocess.run([sys.executable, os.path.join(here, "mask_data.py"),
                    os.path.join(here, "data.json"),
                    os.path.join(here, "data-team.json")], check=True)
# cả hai bản đều mã hoá — repo công khai không lộ tên khách lẫn doanh thu
for code, src, out in ((c_team, "data-team.json", "a.json"),
                       (c_full, "data.json",      "b.json")):
    blob = encrypt(code, open(os.path.join(here, src), "rb").read())
    open(os.path.join(site, "d", out), "w").write(json.dumps(blob, separators=(",", ":")))

# 2) trang
boot = read("tpl_boot.html").replace("__ITER__", str(ITER))

# @font-face chỉ sinh cho file font THẬT SỰ có trong docs/fonts/ — tránh 404 vô ích
AVERTA = [("Averta-Regular.woff2",       "normal", 400),
          ("Averta-Semibold.woff2",      "normal", 500),
          ("Averta-Semibold.woff2",      "normal", 600),
          ("Averta-Bold.woff2",          "normal", 700),
          ("Averta-Extrabold.woff2",     "normal", 800),
          ("Averta-RegularItalic.woff2", "italic", 400)]
faces, seen = [], set()
for fn, style, wt in AVERTA:
    if not os.path.exists(os.path.join(fonts, fn)):
        continue
    faces.append('@font-face{font-family:"Averta";font-style:%s;font-weight:%d;'
                 'font-display:swap;src:url("fonts/%s") format("woff2")}' % (style, wt, fn))
    seen.add(fn)
face_css = ("/* Averta — sinh tự động từ file có trong docs/fonts/ */\n" + "\n".join(faces)
            if faces else
            "/* Chưa có file Averta trong docs/fonts/ — đang dùng Plus Jakarta Sans thay thế. */")
print("  font Averta tìm thấy: %d file (%s)"
      % (len(seen), ", ".join(sorted(seen)) if seen else "chưa có — dùng font dự phòng"))
html = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow">'
        '<title>Arena — Bảng theo dõi vận hành</title>'
        '</head><body>'
        + read("tpl_head.html").replace("<title>Arena Daily</title>", "")
                        .replace("__AVERTA_FACES__", face_css)
        + read("tpl_gate.html")
        + read("tpl_body.html")
        + boot
        + read("tpl_js.html")
        + '</body></html>')
open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(html)
open(os.path.join(site, ".nojekyll"), "w").write("")

for root, _, files in sorted(os.walk(site)):
    for f in sorted(files):
        p = os.path.join(root, f)
        print(f"  {os.path.relpath(p, site):26} {os.path.getsize(p)/1024:8.0f} KB")
print("\nCả hai payload đều là ciphertext AES-256-GCM. Repo không chứa mã, không chứa hash,")
print("không chứa tên khách hay số doanh thu ở dạng đọc được.")
