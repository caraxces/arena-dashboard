#!/bin/bash
# Kéo dữ liệu mới và dựng lại dashboard. Chạy 3 lần/ngày.
cd "$(dirname "$0")" || exit 1
export ARENA03_TOKEN="${ARENA03_TOKEN:?Chưa đặt ARENA03_TOKEN}"
python3 build_data.py data.json  && python3 build_dash.py data.json dashboard.html \
  && echo "$(date '+%F %T') — đã cập nhật dashboard.html"
