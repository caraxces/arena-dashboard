#!/bin/bash
# Cập nhật số liệu dashboard rồi đẩy lên GitHub Pages.
# Chạy tự động 4 kỳ/ngày qua LaunchAgent com.arena.dashboard.
# Bí mật (token API + 2 mã truy cập) đọc từ ~/.config/arena/env — ngoài repo, chmod 600.
set -uo pipefail

cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

ENVF="$HOME/.config/arena/env"
[ -r "$ENVF" ] || { echo "Không đọc được $ENVF"; exit 1; }
# shellcheck disable=SC1090
. "$ENVF"
export ARENA01_TOKEN ARENA02_TOKEN ARENA03_TOKEN

ts() { date '+%F %T'; }
echo "=== $(ts) bắt đầu ==="

# API hay timeout giữa chừng và trả về chuỗi ngày cụt. Thử tối đa 3 lần,
# chỉ publish khi validate.py xác nhận dữ liệu đủ.
ok=0
for try in 1 2 3; do
  echo "-- lần $try --"
  if python3 build_data.py data.json && python3 validate.py data.json; then
    ok=1; break
  fi
  [ "$try" -lt 3 ] && sleep 45
done

if [ "$ok" -ne 1 ]; then
  echo "$(ts) BỎ QUA kỳ này — dữ liệu API không đủ sau 3 lần thử."
  exit 1
fi

set -e
python3 mask_data.py data.json data-team.json
python3 build_site.py "$CODE_FULL" "$CODE_TEAM" >/dev/null

git add docs
if git diff --cached --quiet; then
  echo "$(ts) không có thay đổi — bỏ qua"
  exit 0
fi

git commit -q -m "auto: số liệu $(date '+%F %H:%M')"
git push origin main

echo "=== $(ts) xong: $(git rev-parse --short HEAD) ==="
