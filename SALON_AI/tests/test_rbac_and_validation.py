from datetime import date, timedelta
import pytest
import database


def login_as(client, username, role, user_id=None, full_name=None):
    """Helper to simulate an authenticated session."""
    with client.session_transaction() as sess:
        sess["user_id"] = user_id or 1
        sess["username"] = username
        sess["role"] = role
        sess["full_name"] = full_name or username


# =========================================================================
# 1. PHÂN QUYỀN DỊCH VỤ (RBAC SERVICES)
# =========================================================================

def test_all_roles_can_view_services(client):
    """Admin, Receptionist và Barber đều xem được danh sách dịch vụ (GET 200)."""
    for role in ("admin", "receptionist", "barber"):
        login_as(client, f"user_{role}", role)
        res = client.get("/services")
        assert res.status_code == 200
        assert "Dịch vụ" in res.data.decode("utf-8")


def test_barber_and_receptionist_cannot_create_service(client):
    """Barber và Receptionist gửi POST /services đều bị từ chối; không tạo được dịch vụ."""
    services_before = len(database.list_services())

    for role in ("barber", "receptionist"):
        login_as(client, f"user_{role}", role)
        res = client.post(
            "/services",
            data={
                "name": f"Hacked Service by {role}",
                "category": "Test",
                "description": "Exploit attempt",
                "duration_minutes": "30",
                "price": "999000",
            },
            follow_redirects=True,
        )
        assert res.status_code == 200
        assert "Bạn không có quyền thực hiện thao tác này" in res.data.decode("utf-8")

    services_after = len(database.list_services())
    assert services_after == services_before


def test_admin_can_create_service(client):
    """Admin gửi POST /services được phép và tạo dịch vụ thành công."""
    login_as(client, "admin", "admin")
    service_name = "Uốn phồng chân tóc VIP"
    res = client.post(
        "/services",
        data={
            "name": service_name,
            "category": "Styling",
            "description": "Uốn VIP cho Admin",
            "duration_minutes": "60",
            "price": "500000",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Đã thêm dịch vụ" in res.data.decode("utf-8")

    all_services = [s["name"] for s in database.list_services()]
    assert service_name in all_services


# =========================================================================
# 2. PHÂN QUYỀN KHÁCH HÀNG (RBAC CUSTOMERS)
# =========================================================================

def test_barber_cannot_create_or_edit_customer(client):
    """Barber gửi POST trực tiếp để tạo hoặc sửa thông tin khách hàng đều bị chặn."""
    login_as(client, "tho01", "barber", user_id=3)

    # Thử tạo khách hàng
    res_create = client.post(
        "/customers",
        data={
            "full_name": "Khách Test Barber",
            "phone": "0988776655",
        },
        follow_redirects=True,
    )
    assert "Bạn không có quyền thực hiện thao tác này" in res_create.data.decode("utf-8")

    # Thử sửa khách hàng #1
    res_edit = client.post(
        "/customers/1/edit",
        data={
            "full_name": "Khách Bị Đổi Tên",
            "phone": "0912000001",
        },
        follow_redirects=True,
    )
    assert "Bạn không có quyền thực hiện thao tác này" in res_edit.data.decode("utf-8")

    # Kiểm tra dữ liệu khách #1 không bị đổi tên
    cust = database.get_customer(1)
    assert cust["full_name"] != "Khách Bị Đổi Tên"


def test_admin_and_receptionist_can_edit_customer(client):
    """Admin và Receptionist được phép sửa thông tin khách hàng."""
    for role in ("admin", "receptionist"):
        login_as(client, f"staff_{role}", role)
        new_note = f"Ghi chú mới từ {role}"
        res = client.post(
            "/customers/1/edit",
            data={
                "full_name": "Nguyễn Văn An",
                "phone": "0912000001",
                "note": new_note,
            },
            follow_redirects=True,
        )
        assert res.status_code == 200
        assert "Đã cập nhật khách hàng" in res.data.decode("utf-8")
        cust = database.get_customer(1)
        assert cust["note"] == new_note


# =========================================================================
# 3. PHÂN QUYỀN LỊCH HẸN (RBAC APPOINTMENTS)

# Additional tests for Barber dashboard and appointment visibility

def test_barber_dashboard_no_global_stats(client):
    """Barber should not see global stats or other barber's appointments on dashboard."""
    # Get a linked barber user (ensure user_id links to a barber record)
    barbers = database.list_barbers()
    linked = next(b for b in barbers if b.get("user_id"))
    login_as(client, "linked_barber", "barber", user_id=linked["user_id"])  # simulate session
    res = client.get("/dashboard")
    html = res.data.decode("utf-8")
    # Stats block is hidden for barber
    assert "Khách hàng" not in html
    assert "Doanh thu tháng" not in html
    # Ensure only his own appointments are listed (if any)
    # Create an appointment for another barber to ensure it does NOT appear
    other = next(b for b in barbers if b["id"] != linked["id"])
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    sid = [database.list_services()[0]["id"]]
    appt_other = database.create_appointment(1, other["id"], tomorrow, "09:00", "", "Other barber appt", sid)
    # Refresh dashboard after creating other appointment
    res2 = client.get("/dashboard")
    html2 = res2.data.decode("utf-8")
    assert "Other barber appt" not in html2

def test_barber_appointments_page_shows_only_own(client):
    """Barber sees only his own appointments on /appointments page."""
    barbers = database.list_barbers()
    linked = next(b for b in barbers if b.get("user_id"))
    other = next(b for b in barbers if b["id"] != linked["id"])
    login_as(client, "linked_barber", "barber", user_id=linked["user_id"]) 
    # Create appointments for both barbers
    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    sid = [database.list_services()[0]["id"]]
    appt_own = database.create_appointment(1, linked["id"], tomorrow, "10:00", "", "Own appt", sid)
    appt_other = database.create_appointment(2, other["id"], tomorrow, "11:00", "", "Other appt", sid)
    res = client.get("/appointments")
    html = res.data.decode("utf-8")
    assert "Own appt" in html
    assert "Other appt" not in html

def test_barber_customer_detail_own_appointments_only(client):
    """Barber sees only appointments belonging to him on customer detail page."""
    barbers = database.list_barbers()
    linked = next(b for b in barbers if b.get("user_id"))
    other = next(b for b in barbers if b["id"] != linked["id"])
    login_as(client, "linked_barber", "barber", user_id=linked["user_id"]) 
    tomorrow = (date.today() + timedelta(days=3)).isoformat()
    sid = [database.list_services()[0]["id"]]
    # appointment for this barber
    own_appt = database.create_appointment(1, linked["id"], tomorrow, "12:00", "", "Own customer appt", sid)
    # appointment for other barber but same customer
    other_appt = database.create_appointment(1, other["id"], tomorrow, "13:00", "", "Other barber appt", sid)
    res = client.get("/customers/1")
    html = res.data.decode("utf-8")
    assert "Own customer appt" in html
    assert "Other barber appt" not in html

# Tests for AI API validation

def _api_post(client, endpoint, payload):
    return client.post(endpoint, json=payload, follow_redirects=True)

@pytest.mark.parametrize("endpoint", ["/api/ai/recommend", "/api/ai/message", "/api/ai/summary"])
def test_ai_api_missing_customer_id_returns_400(client, endpoint):
    login_as(client, "admin", "admin")
    res = _api_post(client, endpoint, {})
    assert res.status_code == 400
    data = res.get_json()
    assert data is not None and data.get("error")

@pytest.mark.parametrize("endpoint", ["/api/ai/recommend", "/api/ai/message", "/api/ai/summary"])
def test_ai_api_invalid_customer_id_returns_400(client, endpoint):
    login_as(client, "admin", "admin")
    res = _api_post(client, endpoint, {"customer_id": "not-an-int"})
    assert res.status_code == 400
    data = res.get_json()
    assert data.get("error")

@pytest.mark.parametrize("endpoint", ["/api/ai/recommend", "/api/ai/message", "/api/ai/summary"])
def test_ai_api_nonexistent_customer_returns_404(client, endpoint):
    login_as(client, "admin", "admin")
    # Assuming 9999 does not exist in test data
    res = _api_post(client, endpoint, {"customer_id": 9999})
    assert res.status_code == 404
    data = res.get_json()
    assert data.get("error")

def test_ai_chat_error_hides_detail(client):
    """When the AI service raises an exception, the response must not contain a 'detail' field."""
    login_as(client, "admin", "admin")
    # Force an error by sending a message that triggers exception in ai_service (e.g., missing required key)
    # The chat endpoint expects JSON with 'message' field; omit it.
    res = client.post("/api/ai/chat", json={}, follow_redirects=True)
    # Should be 500 internal error but with generic message
    assert res.status_code == 500
    data = res.get_json()
    # The response should contain a generic 'error' key but no 'detail'
    assert data.get("error")
    assert "detail" not in data

# =========================================================================

def test_barber_sees_only_own_appointments(client):
    """Barber chỉ nhìn thấy lịch hẹn của chính mình trên giao diện /appointments."""
    barbers = database.list_barbers()
    assert len(barbers) >= 2
    # Tìm thợ có tài khoản đăng nhập liên kết (user_id IS NOT NULL)
    linked_barber = next(b for b in barbers if b.get("user_id"))
    other_barber = next(b for b in barbers if b["id"] != linked_barber["id"])

    # Tạo lịch cho thợ liên kết và thợ khác vào ngày mai
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    services = database.list_services()
    sid = [services[0]["id"]]

    appt1 = database.create_appointment(1, linked_barber["id"], tomorrow, "09:00", "", "Lịch thợ chính", sid)
    appt2 = database.create_appointment(2, other_barber["id"], tomorrow, "11:00", "", "Lịch thợ khác", sid)

    # Đăng nhập bằng tài khoản liên kết với Thợ chính
    login_as(client, "tho01", "barber", user_id=linked_barber["user_id"])
    res = client.get("/appointments")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert linked_barber["full_name"] in html
    # Lịch của thợ khác không được xuất hiện trong bảng lịch của thợ chính
    assert "Lịch thợ khác" not in html


def test_barber_cannot_update_other_barbers_appointment(client):
    """Barber không thể cập nhật trạng thái lịch hẹn thuộc về Barber khác."""
    barbers = database.list_barbers()
    linked_barber = next(b for b in barbers if b.get("user_id"))
    other_barber = next(b for b in barbers if b["id"] != linked_barber["id"])

    tomorrow = (date.today() + timedelta(days=2)).isoformat()
    sid = [database.list_services()[0]["id"]]
    appt_of_other = database.create_appointment(1, other_barber["id"], tomorrow, "14:00", "", "Khách thợ khác", sid)

    # Thợ chính cố tình gửi POST đổi trạng thái lịch của Thợ khác
    login_as(client, "tho01", "barber", user_id=linked_barber["user_id"])
    res = client.post(
        f"/appointments/{appt_of_other}/status",
        data={"status": "Confirmed"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Bạn chỉ có quyền cập nhật lịch hẹn của chính mình" in res.data.decode("utf-8")

    # Kiểm tra trạng thái lịch của thợ khác vẫn là Pending
    appt = database.get_appointment(appt_of_other)
    assert appt["status"] == "Pending"


def test_unlinked_barber_account_handled_gracefully(client):
    """Tài khoản Barber chưa liên kết hồ sơ thợ không làm ứng dụng crash."""
    login_as(client, "unlinked_tho", "barber", user_id=9999)
    res = client.get("/appointments")
    assert res.status_code == 200
    assert "chưa được liên kết" in res.data.decode("utf-8")


# =========================================================================
# 4. XỬ LÝ LỖI NGHIỆP VỤ & VALIDATION (KHÔNG CRASH 500)
# =========================================================================

def test_create_appointment_validation_errors_return_flash_not_500(client):
    """Tạo lịch hẹn với dữ liệu sai (quá khứ, trùng lịch, thiếu dịch vụ) không gây crash 500."""
    login_as(client, "receptionist", "receptionist")

    # 1. Thiếu dịch vụ
    res1 = client.post(
        "/appointments/create",
        data={
            "customer_id": "1",
            "barber_id": "1",
            "appointment_date": (date.today() + timedelta(days=3)).isoformat(),
            "start_time": "10:00",
        },
        follow_redirects=True,
    )
    assert res1.status_code == 200
    assert "Hãy chọn ít nhất một dịch vụ" in res1.data.decode("utf-8")

    # 2. Ngày trong quá khứ
    res2 = client.post(
        "/appointments/create",
        data={
            "customer_id": "1",
            "barber_id": "1",
            "appointment_date": "2020-01-01",
            "start_time": "10:00",
            "service_ids": ["1"],
        },
        follow_redirects=True,
    )
    assert res2.status_code == 200
    assert "Không thể đặt lịch vào ngày đã qua" in res2.data.decode("utf-8")

    # 3. Trùng giờ thợ
    target_date = (date.today() + timedelta(days=4)).isoformat()
    # Tạo lịch thứ nhất
    client.post(
        "/appointments/create",
        data={
            "customer_id": "1",
            "barber_id": "1",
            "appointment_date": target_date,
            "start_time": "09:00",
            "service_ids": ["1"],
        },
        follow_redirects=True,
    )
    # Cố tình tạo lịch thứ 2 trùng giờ
    res3 = client.post(
        "/appointments/create",
        data={
            "customer_id": "2",
            "barber_id": "1",
            "appointment_date": target_date,
            "start_time": "09:15",
            "service_ids": ["1"],
        },
        follow_redirects=True,
    )
    assert res3.status_code == 200
    assert "Thợ đã có lịch" in res3.data.decode("utf-8")


def test_create_invoice_validation_errors_return_flash_not_500(client):
    """Tạo hóa đơn với dữ liệu sai (lịch chưa hoàn thành, giảm giá quá mức, trùng) không gây crash 500."""
    login_as(client, "receptionist", "receptionist")

    # 1. Nhập mã lịch không hợp lệ
    res1 = client.post(
        "/invoices/create",
        data={"appointment_id": "abc"},
        follow_redirects=True,
    )
    assert res1.status_code == 200
    assert "Mã lịch hẹn" in res1.data.decode("utf-8")

    # 2. Lập hóa đơn cho lịch chưa xong (Pending)
    sid = [database.list_services()[0]["id"]]
    future_date = (date.today() + timedelta(days=5)).isoformat()
    pending_appt = database.create_appointment(1, 1, future_date, "15:00", "", "", sid)

    res2 = client.post(
        "/invoices/create",
        data={"appointment_id": str(pending_appt)},
        follow_redirects=True,
    )
    assert res2.status_code == 200
    assert "Chỉ được lập hóa đơn cho lịch hẹn đã hoàn thành" in res2.data.decode("utf-8")

    # 3. Hoàn thành lịch và thử giảm giá vượt quá tổng tiền
    database.update_appointment_status(pending_appt, "Confirmed")
    database.update_appointment_status(pending_appt, "Completed")

    res3 = client.post(
        "/invoices/create",
        data={
            "appointment_id": str(pending_appt),
            "discount": "999999999",
        },
        follow_redirects=True,
    )
    assert res3.status_code == 200
    assert "không được lớn hơn tổng tiền" in res3.data.decode("utf-8")


def test_update_appointment_status_invalid_transition_not_500(client):
    """Cập nhật trạng thái không hợp lệ (ví dụ nhảy từ Pending sang Completed) không gây crash 500."""
    login_as(client, "admin", "admin")

    sid = [database.list_services()[0]["id"]]
    future_date = (date.today() + timedelta(days=6)).isoformat()
    pending_appt = database.create_appointment(1, 1, future_date, "16:00", "", "", sid)

    # Pending không thể nhảy thẳng lên Completed mà phải qua Confirmed
    res = client.post(
        f"/appointments/{pending_appt}/status",
        data={"status": "Completed"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Luồng trạng thái không hợp lệ" in res.data.decode("utf-8")
