# Arena Dashboard

Bảng theo dõi vận hành cho hệ thống sân cầu lông **arena by lona&co** (3 hub, 23 sân, Đà Nẵng).
Đọc dữ liệu trực tiếp từ **Mewin Partner API** (nền tảng của G-Sport).

Trang online: <https://caraxces.github.io/arena-dashboard/> — cần mã truy cập, xem bảng bên dưới.

## Bảo mật — đọc trước khi sửa gì

Repo này công khai để dùng GitHub Pages miễn phí, nên **không có dữ liệu nào ở dạng đọc được**:

- `docs/d/a.json` và `docs/d/b.json` là **ciphertext AES-256-GCM**. Khoá dẫn xuất từ mã truy cập
  bằng PBKDF2-HMAC-SHA256, 600.000 vòng (khuyến nghị OWASP hiện hành), salt ngẫu nhiên mỗi lần build.
- Repo **không chứa mã truy cập, không chứa hash của mã**. Nhập sai thì giải mã thất bại — không có đường vòng.
- `data.json` (dữ liệu thô: doanh thu, tên khách, số điện thoại) nằm trong `.gitignore`.
  **Không bao giờ commit file này.**
- Token API đọc từ biến môi trường, không nằm trong mã nguồn.

Hai mã cho hai mức xem:

| Mã | Mở ra | Nội dung |
|---|---|---|
| Mã quản lý | Bản đầy đủ | Toàn bộ, gồm doanh thu và giá trị khách hàng |
| Mã team | Bản vận hành | **File không chứa số doanh thu** — bị lược bỏ lúc build, không phải ẩn bằng CSS |

Bản team bị lược sạch ở tầng dữ liệu: bảng giá, doanh thu theo ngày, giá trị hợp đồng
đều không có trong file. Xem `mask_data.py`.

## Cập nhật số liệu

```bash
export ARENA03_TOKEN='...'          # xin từ G-Sport, theo từng chi nhánh
# export ARENA01_TOKEN='...'        # bỏ dấu # khi có
# export ARENA02_TOKEN='...'

python3 build_data.py data.json                     # kéo API
python3 mask_data.py data.json data-team.json       # dựng bản không doanh thu
python3 build_site.py '<MÃ_QUẢN_LÝ>' '<MÃ_TEAM>'    # dựng docs/
git add docs && git commit -m "cập nhật số liệu" && git push
```

Đổi mã truy cập = chạy lại `build_site.py` với mã mới rồi push. Mã cũ hết tác dụng ngay
vì ciphertext được sinh lại.

Nên chạy 4 lần/ngày (06:00 · 10:00 · 16:00 · 22:00). Trên macOS thêm vào `crontab -e`:

```
0 6,10,16,22 * * * cd /ĐƯỜNG/DẪN/arena-dashboard && ARENA03_TOKEN='...' ./refresh.sh >> refresh.log 2>&1
```

## Cấu trúc

| File | Việc |
|---|---|
| `build_data.py` | Kéo Mewin Partner API → `data.json` |
| `mask_data.py` | Lược sạch mọi trường tiền → `data-team.json` |
| `crypt.py` | Mã hoá AES-256-GCM, khoá PBKDF2 |
| `build_site.py` | Dựng `docs/` cho GitHub Pages |
| `build_dash.py` | Ghép template + dữ liệu (bản chạy local, nhúng sẵn dữ liệu) |
| `engine.py` | Client API + phép tính metrics |
| `app.py` | Server local có tự làm mới — `python3 app.py` rồi mở localhost:8787 |
| `sync.py` | Bản gọn chỉ để kéo dữ liệu |
| `tpl_*.html` | Template giao diện: head/CSS, gate, body, boot, JS |
| `docs/fonts/` | Font Averta (thương mại — tự đặt file vào, xem README trong đó) |

## Font

Giao diện dùng **Averta**. Đây là font thương mại, không có trên Google Fonts, nên file
`.woff2` không nằm trong repo — đặt vào `docs/fonts/` theo hướng dẫn ở đó. Chưa có file
thì tự động dùng **Plus Jakarta Sans** (Google Fonts, đủ dấu tiếng Việt).

`build_site.py` chỉ sinh `@font-face` cho file thật sự tồn tại nên không có font cũng
không sinh lỗi 404, và thư mục `docs/fonts/` được giữ nguyên mỗi lần dựng lại.

## Nguồn dữ liệu

Base URL `https://api.quanlysan.vn/api`, header `Authorization: <TOKEN>`.
Toàn bộ chương trình **chỉ gọi endpoint đọc** — không có dòng nào gọi `AddContractSchedule`.

Vài điều tài liệu API không nói mà phải test mới biết:

- Thiếu header `User-Agent` → Cloudflare trả **403**.
- Thời gian là **số phút từ 00:00** (19:00 = 1140).
- `minTime = 60` → mọi khoảng trống dưới 60 phút không đặt được.
- Field `total` luôn trả `0` — đừng phân trang theo nó.
- `dateTimes` của các endpoint `Report/*` nhận **nhiều khoảng ngày trong một lời gọi**.
- Các endpoint `Report/*` nhận `shopID`, nên **một token đọc được doanh thu cả 3 hub**.
  Còn `GetScheduleView` và `GetContractScheduleBookedDatatable` thì khoá theo từng hub.
