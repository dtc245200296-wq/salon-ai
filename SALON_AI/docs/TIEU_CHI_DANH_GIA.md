# Hệ thống quản lý đặt lịch salon tóc có tích hợp AI

## 1. Mô tả bài toán

Salon tóc cần quản lý khách hàng, thợ làm tóc, dịch vụ, lịch hẹn, hóa đơn và lịch sử chăm sóc. Khách cần tư vấn dịch vụ, còn salon cần nhắc lịch và chăm sóc khách. Hệ thống cần quản lý đặt lịch salon và tích hợp AI gợi ý dịch vụ, sinh tin nhắn nhắc lịch và tóm tắt lịch sử khách hàng.

## 2. Mục tiêu

- Quản lý khách hàng, thợ, dịch vụ, lịch hẹn, hóa đơn và lịch sử.
- Tích hợp AI để gợi ý dịch vụ, sinh tin nhắn, tóm tắt lịch sử.
- Sử dụng AI trong SDLC và kiểm thử chức năng quản lý/AI.

## 3. Yêu cầu chức năng

### 3.1. Chức năng quản lý

1. Đăng nhập và phân quyền quản lý, lễ tân, thợ.
2. Quản lý khách hàng và lịch sử dịch vụ.
3. Quản lý thợ, lịch làm việc.
4. Quản lý dịch vụ, giá, thời lượng.
5. Đặt lịch, đổi lịch, hủy lịch.
6. Lập hóa đơn và thanh toán.
7. Tra cứu lịch hẹn theo ngày, thợ, khách.
8. Thống kê doanh thu, dịch vụ phổ biến, khách quay lại.

### 3.2. Chức năng AI

1. AI gợi ý dịch vụ theo nhu cầu khách và lịch sử.
2. AI sinh tin nhắn nhắc lịch hoặc chăm sóc sau dịch vụ.
3. AI tóm tắt lịch sử làm tóc của khách cho thợ xem nhanh.

### 3.3. Yêu cầu kỹ thuật và dữ liệu

- Backend: FastAPI/Flask/Django; frontend: React/Vue/HTML.
- CSDL: SQLite/MySQL/PostgreSQL.
- AI Engine: OpenAI/Gemini/Claude/Hugging Face/Ollama.
- Có test cho lịch hẹn, hóa đơn, lịch sử và AI.
- Dữ liệu chính: khách hàng, thợ, dịch vụ, lịch hẹn, hóa đơn, lịch sử.
- Đầu vào AI: nhu cầu khách, lịch sử dịch vụ, danh sách dịch vụ.
- Đầu ra AI: gợi ý dịch vụ, tin nhắn, tóm tắt lịch sử.

### 3.4. Prompt mẫu trong yêu cầu

**System:** Bạn là trợ lý salon tóc. Chỉ gợi ý dịch vụ có trong danh sách, không cam kết kết quả ngoài dữ liệu.

**User:** Khách muốn thay đổi kiểu tóc, đã từng làm: `{{customer_history}}`. Dịch vụ hiện có: `{{services}}`. Hãy gợi ý dịch vụ phù hợp.

## 4. Tiêu chí Bài kiểm tra thường xuyên 1 — KT1: Phân tích và thiết kế

1. **Phân tích đúng bài toán quản lý:** Xác định rõ bối cảnh, người dùng, dữ liệu, quy trình nghiệp vụ và vấn đề cần giải quyết.
2. **Xác định đầy đủ yêu cầu chức năng:** Liệt kê chức năng quản lý cốt lõi phù hợp với đề tài, có mô tả đầu vào, xử lý và đầu ra.
3. **Xác định yêu cầu phi chức năng:** Nêu yêu cầu về bảo mật, hiệu năng, khả dụng, sao lưu, phân quyền và trải nghiệm người dùng.
4. **Thiết kế actor và use case:** Xác định actor chính, use case chính và có sơ đồ Use Case hoặc mô tả tương đương.
5. **Thiết kế cơ sở dữ liệu:** Có ERD, bảng dữ liệu, khóa chính/khóa ngoại, ràng buộc và giải thích quan hệ.
6. **Thiết kế kiến trúc hệ thống:** Mô tả kiến trúc frontend, backend, database, AI service và luồng dữ liệu chính.
7. **Xác định vị trí ứng dụng AI:** Chọn chức năng AI hợp lý, gắn với dữ liệu và nhu cầu thực tế của hệ thống.
8. **Thiết kế prompt và luồng gọi AI sơ bộ:** Có system/user prompt mẫu, input/output format, ràng buộc và giới hạn.
9. **Minh chứng sử dụng AI trong phân tích và thiết kế:** Lưu prompt, phản hồi AI và nhận xét cách sinh viên kiểm chứng/chỉnh sửa kết quả AI.
10. **Tài liệu phân tích thiết kế:** Tài liệu rõ ràng, có cấu trúc, có kế hoạch triển khai các giai đoạn tiếp theo.

## 5. Tiêu chí Bài kiểm tra thường xuyên 2 — KT2: Xây dựng chức năng quản lý

1. **Cấu trúc dự án hợp lý:** Dự án tổ chức rõ ràng theo frontend/backend/database/config/docs hoặc cấu trúc phù hợp framework.
2. **Đăng nhập và phân quyền:** Có xác thực người dùng, phân quyền vai trò và bảo vệ các chức năng quan trọng.
3. **Hoàn thiện CRUD nghiệp vụ chính:** Các chức năng thêm, xem, sửa, xóa dữ liệu chính hoạt động đúng.
4. **Tìm kiếm và lọc:** Cho phép tìm kiếm, lọc, sắp xếp dữ liệu theo tiêu chí phù hợp.
5. **Thống kê/báo cáo cơ bản:** Có báo cáo hoặc dashboard phục vụ nghiệp vụ của hệ thống.
6. **Giao diện rõ ràng, dễ sử dụng:** Giao diện nhất quán, dễ thao tác, có thông báo lỗi và phản hồi người dùng.
7. **Kết nối và thao tác CSDL ổn định:** Lưu, đọc, cập nhật, xóa dữ liệu chính xác; có dữ liệu mẫu để demo.
8. **Xử lý lỗi cơ bản:** Xử lý input sai, dữ liệu thiếu, lỗi truy vấn, lỗi phân quyền; không để ứng dụng crash.
9. **Minh chứng sử dụng AI khi lập trình:** Có nhật ký prompt, phản hồi AI, phần code được hỗ trợ và phần sinh viên đã kiểm tra/chỉnh sửa.
10. **Quản lý mã nguồn và tài liệu chạy thử:** Có README, hướng dẫn cài đặt/chạy, `.env.example`, commit rõ ràng.

## 6. Tiêu chí Bài kiểm tra thường xuyên 3 — KT3: Tích hợp AI và kiểm thử

1. **Tích hợp chức năng AI vào hệ thống:** Chức năng AI chạy trong hệ thống, phục vụ nghiệp vụ cụ thể, không tách rời sản phẩm.
2. **Kết nối API/model AI đúng cách:** Gọi được OpenAI/Gemini/Claude/Hugging Face/Ollama hoặc mô hình tương đương; bảo vệ API key.
3. **Thiết kế prompt có hệ thống:** Prompt tách khỏi code, có system/user prompt, ràng buộc output và hướng dẫn xử lý dữ liệu.
4. **Tối ưu prompt qua thử nghiệm:** Có ít nhất 3 vòng thử nghiệm hoặc so sánh prompt/model, ghi nhận kết quả và cải tiến.
5. **Sử dụng dữ liệu hệ thống trong chức năng AI:** AI khai thác dữ liệu phù hợp từ CSDL, file hoặc báo cáo; kiểm soát quyền truy cập dữ liệu.
6. **Hiển thị kết quả AI rõ ràng:** Kết quả AI được trình bày dễ hiểu, có định dạng phù hợp và cảnh báo khi cần.
7. **Xử lý lỗi và giới hạn:** Xử lý timeout, rate limit, response rỗng/sai định dạng, dữ liệu quá dài và lỗi model.
8. **Kiểm thử chức năng quản lý và AI:** Có test case, manual test hoặc script test; bao gồm trường hợp đúng, sai và biên.
9. **Review code và cải thiện chất lượng bằng AI:** Có minh chứng dùng AI để review code, phát hiện lỗi, refactor hoặc cải thiện bảo mật.
10. **Tích hợp chức năng AI với trải nghiệm người dùng:** Luồng sử dụng AI tự nhiên, hữu ích, không gây nhầm lẫn với chức năng quản lý chính.

## 7. Tiêu chí thi kết thúc học phần

1. **Hoàn thiện chức năng hệ thống:** Các chức năng quản lý và chức năng AI hoạt động đầy đủ, ổn định, đúng yêu cầu.
2. **Chất lượng kiến trúc và mã nguồn:** Code rõ ràng, module hóa, dễ bảo trì, tuân thủ quy ước framework/ngôn ngữ.
3. **Chất lượng cơ sở dữ liệu:** CSDL hợp lý, dữ liệu nhất quán, có ràng buộc, dữ liệu mẫu và khả năng sao lưu/khôi phục cơ bản.
4. **Chất lượng giao diện và trải nghiệm người dùng:** Giao diện dễ dùng, nhất quán, responsive ở mức phù hợp, có phản hồi thao tác và thông báo lỗi.
5. **Chất lượng chức năng AI:** Kết quả AI hữu ích, đúng ngữ cảnh, có kiểm soát sai lệch, có giới hạn và cảnh báo rõ.
6. **Bảo mật, quyền riêng tư và đạo đức AI:** Bảo vệ tài khoản, phân quyền dữ liệu, không lộ API key, cân nhắc dữ liệu nhạy cảm khi gọi AI.
7. **Hiệu năng và độ ổn định:** Ứng dụng phản hồi hợp lý, xử lý được dữ liệu demo, có cơ chế tránh lỗi lặp lại hoặc lỗi do AI.
8. **Triển khai và đóng gói:** Có hướng dẫn triển khai, cấu hình môi trường, dữ liệu mẫu; khuyến khích Docker hoặc cloud demo.
9. **Báo cáo kỹ thuật đầy đủ:** Báo cáo mô tả phân tích, thiết kế, triển khai, kiểm thử, chức năng AI và vai trò AI trong SDLC.
10. **Thuyết trình và demo:** Demo mạch lạc, trình bày rõ chức năng quản lý, chức năng AI, minh chứng sử dụng AI và trả lời câu hỏi tốt.

## 8. Yêu cầu phi chức năng trong tài liệu đặc tả

- **RNF-01 — Bảo mật:** Mã hóa mật khẩu bằng thuật toán an toàn (BCrypt), xác thực phiên làm việc qua JWT Token.
- **RNF-02 — Hiệu năng:** Phản hồi thao tác CRUD dưới 500 ms; thời gian gọi phản hồi AI dưới 3 giây.
- **RNF-03 — Độ tin cậy và khả dụng:** Mục tiêu hệ thống sẵn sàng 99,5% thời gian; sao lưu CSDL tự động hàng ngày.
- **RNF-04 — Tính dễ sử dụng:** Giao diện thân thiện, dễ nhìn, chuẩn hóa thao tác đặt lịch ngắn gọn.
- **RNF-05 — Khả năng tương thích:** Hiển thị tốt trên màn hình máy tính và thiết bị di động.

## 9. Quy tắc khi AI hỗ trợ sửa dự án

- Đối chiếu mã nguồn với yêu cầu và chỉ ra bằng chứng cụ thể trước khi sửa.
- Không đánh dấu một chức năng là hoàn thành nếu chưa chạy test.
- Không tự ý thay framework hoặc hệ quản trị cơ sở dữ liệu.
- Không đọc hoặc tiết lộ nội dung `.env` hay API key.
- Không xóa, reset hoặc ghi dữ liệu vào `salon_system.db` khi chưa được cho phép.
- Sửa từng nhóm chức năng nhỏ; giải thích file nào thay đổi và vì sao.
- Sau mỗi thay đổi, chạy kiểm thử phù hợp và ghi lại kết quả thực tế.

