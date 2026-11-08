# Font Averta

Averta là font **thương mại** (Kostas Bartsokas / Intelligent Design) — không có trên
Google Fonts, phải mua license webfont mới được nhúng lên site công khai.

Đặt các file `.woff2` vào đúng thư mục này, đúng tên:

```
Averta-Regular.woff2
Averta-Semibold.woff2
Averta-Bold.woff2
Averta-Extrabold.woff2
Averta-RegularItalic.woff2      (tuỳ chọn)
```

Rồi commit và push — không cần sửa gì trong code. `build_site.py` được viết để **giữ lại
thư mục này** khi dựng lại, nên cập nhật số liệu không làm mất font.

Khi chưa có file, trình duyệt tự rơi xuống **Plus Jakarta Sans** (Google Fonts, có đủ
dấu tiếng Việt). Trang chạy bình thường, không lỗi, không ô vuông.

## Kiểm tra đã ăn font chưa

Mở dashboard → DevTools → Console:

```js
[...document.fonts].map(f => f.family + " " + f.weight)
```

Có dòng `Averta ...` là font đã nạp. Danh sách rỗng hoặc không có Averta là đang chạy
font dự phòng.

Đừng dùng `document.fonts.check('16px Averta')` để kiểm tra — hàm đó trả `true` cả khi
Averta không tồn tại, vì nó tính cả font dự phòng.

## Lưu ý license

Repo này công khai nên file font trong đây ai cũng tải được. Kiểm tra license Averta của
cậu có cho phép nhúng webfont trên site công khai không — loại license này thường giới
hạn theo lượt xem mỗi tháng. Nếu không cho, phương án an toàn là để repo Private rồi trả
phí GitHub Pro cho Pages, hoặc dùng dịch vụ CDN font có license riêng.
