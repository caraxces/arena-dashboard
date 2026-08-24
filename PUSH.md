# Đưa lên GitHub Pages — 3 bước

Repo đã commit sẵn (`git log` để xem). Chỉ cần tạo repo trống trên GitHub rồi push.

## 1. Tạo repo trống

Vào https://github.com/new → tên `arena-dashboard` → **không** tích "Add a README".
Để Public cũng an toàn: toàn bộ dữ liệu trong repo là ciphertext.

## 2. Push

```bash
cd đường/dẫn/tới/arena
git remote add origin https://github.com/caraxces/arena-dashboard.git
git branch -M main
git push -u origin main
```

## 3. Bật Pages

Repo → **Settings** → **Pages** → Source: `Deploy from a branch`
→ Branch: `main`, thư mục: **`/docs`** → Save.

Sau 1–2 phút link sẽ là:

```
https://caraxces.github.io/arena-dashboard/
```

Đó là link gửi cho team.

---

## Mã truy cập

Xem file `CODES.txt` (file này **không** nằm trong repo, đã bị `.gitignore` chặn).

Đổi mã bất cứ lúc nào:

```bash
python3 build_site.py 'MÃ_QUẢN_LÝ_MỚI' 'MÃ_TEAM_MỚI'
git add docs && git commit -m "đổi mã truy cập" && git push
```

Mã cũ mất tác dụng ngay, vì ciphertext được sinh lại với salt mới.

## Cập nhật số liệu

```bash
export ARENA03_TOKEN='...'
python3 build_data.py data.json
python3 mask_data.py data.json data-team.json
python3 build_site.py 'MÃ_QUẢN_LÝ' 'MÃ_TEAM'
git add docs && git commit -m "số liệu $(date +%F)" && git push
```

Muốn tự động 4 lần/ngày (06:00 · 10:00 · 16:00 · 22:00) thì cho khối lệnh trên vào một file `.sh` rồi thêm vào `crontab -e`:

```
0 6,10,16,22 * * * cd /ĐƯỜNG/DẪN/arena && ./deploy.sh >> deploy.log 2>&1
```

## Điều KHÔNG được làm

- Đừng bỏ `data.json` hay `data-team.json` khỏi `.gitignore`. Hai file đó chứa doanh thu,
  tên khách và số điện thoại ở dạng đọc được.
- Đừng viết token API vào bất kỳ file nào trong repo. Luôn truyền qua biến môi trường.
- **Mã quản lý chính là khoá giải mã AES.** Repo công khai nghĩa là ciphertext ai cũng
  tải được, và bẻ khoá chạy offline — không có giới hạn số lần thử nào chặn được. Mã toàn
  chữ số hoặc dễ đoán bị bẻ trong vài giây bằng từ điển mật khẩu. Mã đang dùng có 79 bit
  entropy; đừng thay bằng mã ngắn hơn.
