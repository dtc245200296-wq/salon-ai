# Hệ thống quản lý đặt lịch salon tóc có tích hợp AI

## Công nghệ
- Backend: Flask + Jinja2
- Database: SQLite
- AI Integration: Google Gemini API (Tích hợp cơ chế Fallback phản hồi cục bộ tự động)
- Tìm kiếm: Google Search grounding qua Gemini / DuckDuckGo Search (DDGS)
- Frontend: HTML5, CSS3, JavaScript, Tailwind CSS

---

## Chạy ứng dụng

### Bước 1: Di chuyển vào đúng thư mục dự án
Mở Terminal/PowerShell, nếu chưa đứng ở thư mục chứa tệp app.py, hãy dùng lệnh cd để di chuyển vào:
cd SALON_AI
*(Mẹo: Gõ dir hoặc ls để kiểm tra, đảm bảo thấy tệp app.py và update_db.py).*

### Bước 2: Cài đặt môi trường & thư viện (Dành cho lần đầu)
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env

### Bước 3: Khởi tạo & Cập nhật CSDL
python update_db.py

### Bước 4: Khởi chạy chương trình
python app.py

> Lưu ý xử lý lỗi đường dẫn:
> Nếu gặp thông báo can't open file 'app.py': [Errno 2] No such file or directory, nguyên nhân do bạn đang đứng ở thư mục bên ngoài. Hãy dùng lệnh cd SALON_AI rồi gõ lại python app.py.

Mở trình duyệt web và truy cập: http://127.0.0.1:5000

---

## Tài khoản Demo

> Mật khẩu chung cho tất cả tài khoản: 123456

- Quản trị viên (Admin): admin (SĐT: 0901111111)
- Lễ tân (Receptionist): letan01 hoặc letan02 (SĐT: 0111111111 / 0111122222)
- Stylist (Thợ cắt tóc): tho01 hoặc tho02 (SĐT: 0111133333 / 0111144444)
- Khách hàng (Customer): khach01 đến khach05 (SĐT: 0100000000 đến 0500000000)

---

## Tính năng AI

1. Chatbot Quản trị (Admin Assistant):
   - Tự động đọc dữ liệu CSDL thời gian thực (Số lượng khách hàng, Lịch hẹn hôm nay, Doanh thu hệ thống, Danh sách thợ).
   - Trợ lý đa năng: Hỗ trợ lập kế hoạch Marketing, viết bài PR, tính toán chi phí và giải đáp kiến thức tổng hợp.
2. Chatbot Khách hàng (Customer Assistant):
   - Tư vấn chuyên biệt các dịch vụ salon, kiểu tóc phù hợp, chăm sóc tóc và hướng dẫn đặt lịch.
3. Chức năng bổ trợ:
   - Gợi ý dịch vụ dựa trên lịch sử và nhu cầu của khách hàng.
   - Tóm tắt lịch sử khách hàng và tự động sinh tin nhắn chăm sóc.
   - Cơ chế Fallback Engine đảm bảo AI luôn phản hồi ngay cả khi gián đoạn kết nối API.

---

## Bảo mật & Cấu hình

- Mật khẩu được mã hóa lưu trữ dạng Hash an toàn.
- API Key được lưu độc lập trong file .env (không commit lên Git).
- Phân quyền truy cập chặt chẽ theo đúng vai trò (Admin, Lễ tân, Stylist, Khách hàng).