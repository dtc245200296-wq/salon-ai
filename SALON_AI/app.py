import os
import re
import sqlite3
import hmac
from datetime import datetime, date
from functools import wraps
from urllib.parse import quote, urlencode
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

import database
import ai_service

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-change-me"),
    JSON_AS_ASCII=False,
)


@app.template_filter("vnd")
def format_vnd(value):
    try:
        return f"{float(value or 0):,.0f}".replace(",", ".") + " đ"
    except (TypeError, ValueError):
        return "0 đ"


@app.template_filter("status_vi")
def status_vi(value):
    return {
        "pending": "Chờ xác nhận",
        "confirmed": "Đã xác nhận",
        "completed": "Đã hoàn thành",
        "cancelled": "Đã hủy",
    }.get(str(value or "").strip().lower(), str(value or "Đang cập nhật"))

if os.getenv("SALON_TESTING") != "1":
    database.init_db()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        account = database.get_user(session["user_id"])
        if (not account or not account.get("is_active", 1)
                or account.get("role") != session.get("role")):
            session.clear()
            flash("Tài khoản đã bị tạm khóa hoặc không còn tồn tại.", "danger")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login", next=request.path))
            account = database.get_user(session["user_id"])
            if (not account or not account.get("is_active", 1)
                    or account.get("role") != session.get("role")):
                session.clear()
                flash("Tài khoản đã bị tạm khóa hoặc không còn tồn tại.", "danger")
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("Bạn không có quyền thực hiện thao tác này.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("user_id"):
            account = database.get_user(session["user_id"])
            if (not account or not account.get("is_active", 1)
                    or account.get("role") != "admin"):
                session.clear()
                flash("Tài khoản đã bị tạm khóa hoặc không còn tồn tại.", "danger")
                return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Bạn không có quyền thực hiện thao tác này", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapper


def is_admin():
    return session.get("role") == "admin"


def is_receptionist():
    return session.get("role") == "receptionist"


def is_barber():
    return session.get("role") == "barber"


@app.context_processor
def inject_globals():
    role = session.get("role")
    notifications = (
        database.dashboard_notification_data(5)
        if role in {"admin", "receptionist", "staff"}
        else {"count": 0, "appointments": []}
    )
    return {
        "current_user": database.get_user(session["user_id"]) if session.get("user_id") else None,
        "ai_customers": database.list_customers(),
        "admin_notifications": notifications["appointments"],
        "admin_notification_count": notifications["count"],
        "role_display": {"admin": "Quản trị hệ thống", "receptionist": "Lễ tân", "staff": "Nhân viên", "stylist": "Stylist", "customer": "Khách hàng"}.get(role, "Tài khoản"),
        "is_admin": is_admin(),
        "is_receptionist": is_receptionist(),
        "is_barber": is_barber(),
        "now": datetime.now(),
    }


@app.route("/")
@login_required
def home():
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return _redirect_for_role(session.get("role"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password_input = request.form.get("password", "")
        conn = database.get_db_connection()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            user = dict(row) if row else None
        finally:
            conn.close()
        if user and user.get("is_active", 1) and check_password_hash(user["password_hash"], password_input):
            session.clear()
            session.update(
                user_id=user["id"],
                username=user["username"],
                role=user["role"],
                full_name=user["full_name"],
                user_name=user["full_name"],
            )
            return _redirect_for_role(user["role"])
        return render_template("login.html", error="Tên đăng nhập hoặc mật khẩu không đúng.")
    return render_template("login.html")


def _redirect_for_role(role):
    destinations = {
        "admin": "/dashboard",
        "staff": "/dashboard",
        "customer": "/customer/booking",
        "stylist": "/stylist/tasks",
    }
    return redirect(destinations.get(role, "/dashboard"))


def _customer_stylists():
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            """SELECT b.id, u.id AS stylist_user_id,
                      COALESCE(NULLIF(u.full_name, ''), b.full_name) AS full_name,
                      b.specialty, COALESCE(b.experience_years, 0) AS experience_years,
                      COALESCE(b.specialties, b.specialty, '') AS specialties,
                      COALESCE(b.bio, '') AS bio,
                      COALESCE(b.gender_focus, 'both') AS gender_focus,
                      COALESCE(b.rating, 0) AS rating,
                      COALESCE(b.review_count, 0) AS review_count,
                      COALESCE(b.total_customers, 0) AS total_customers,
                      COALESCE(b.awards, '') AS awards,
                      COALESCE(b.philosophy, '') AS philosophy
               FROM barbers b
               JOIN users u ON u.id = b.user_id
               WHERE u.role = 'stylist' AND b.status = 'active'
               ORDER BY u.full_name"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _get_or_create_customer(user):
    if not user.get("phone"):
        raise ValueError("Hồ sơ tài khoản cần có số điện thoại để đặt lịch.")
    conn = database.get_db_connection()
    try:
        customer = conn.execute(
            "SELECT id FROM customers WHERE phone = ?", (user["phone"],)
        ).fetchone()
        if customer:
            conn.execute(
                "UPDATE customers SET full_name = ?, email = ?, customer_code = COALESCE(customer_code, ?) WHERE id = ?",
                (user["full_name"], user.get("email"), f"KH{customer['id']:03d}", customer["id"]),
            )
            conn.commit()
            return customer["id"]
        cursor = conn.execute(
            "INSERT INTO customers(full_name, phone, email) VALUES (?, ?, ?)",
            (user["full_name"], user["phone"], user.get("email")),
        )
        conn.execute(
            "UPDATE customers SET customer_code = ? WHERE id = ?",
            (f"KH{cursor.lastrowid:03d}", cursor.lastrowid),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Không thể liên kết hồ sơ khách hàng. Hãy kiểm tra số điện thoại.") from exc
    finally:
        conn.close()


def _service_modal_details(service):
    category = (service.get("category") or "").strip().lower()
    name = (service.get("name") or "").strip().lower()
    standard_details = {
        "shampoo_natural": {
            "products": "Dầu gội bồ kết thiên nhiên, tinh dầu bưởi.",
            "styles": "Tóc tự nhiên, tóc cần làm sạch và dưỡng nhẹ.",
            "steps": ["Gội xả", "Massage da đầu", "Sấy khô"],
        },
        "shampoo_herbal": {
            "products": "Dược liệu thảo mộc Đông y, dầu bồ kết organic.",
            "styles": "Phù hợp thư giãn, chăm sóc da đầu và tóc yếu.",
            "steps": ["Khai thông huyệt đạo", "Gội thảo dược", "Massage cổ vai gáy"],
        },
        "hair_color_loreal": {
            "products": "Thuốc nhuộm L'Oreal cao cấp.",
            "styles": "Nhuộm tone trầm hoặc tone sáng theo tư vấn màu.",
            "steps": ["Tư vấn màu", "Phủ thuốc", "Xả và xịt dưỡng"],
        },
        "hair_color_fashion": {
            "products": "Thuốc nhuộm thời trang Olaplex hỗ trợ bảo vệ và khôi phục cấu trúc tóc.",
            "styles": "Balayage, Ombre, Pastel.",
            "steps": ["Đánh giá nền tóc", "Tư vấn và chốt màu", "Chia tóc, xử lý màu", "Xả sạch và dưỡng phục hồi", "Sấy tạo kiểu"],
        },
        "haircut_women": {
            "products": "Dầu gội, dầu xả và sáp tạo kiểu phù hợp với chất tóc.",
            "styles": "Bob, Pixie, Layer nữ.",
            "steps": ["Gội", "Thiết kế dáng tóc", "Cắt và hoàn thiện form", "Sấy sáp tạo kiểu"],
        },
        "haircut_layer": {
            "products": "Dầu gội, dầu xả và sản phẩm bảo vệ nhiệt.",
            "styles": "Layer tầng cao, Layer bay Hàn Quốc.",
            "steps": ["Tư vấn form Layer", "Cắt tỉa tạo khối", "Sấy tạo độ phồng"],
        },
        "haircut_men_classic": {
            "products": "Dầu gội và sáp vuốt tóc phù hợp.",
            "styles": "Undercut, Side Part, Ivy League.",
            "steps": ["Tư vấn kiểu", "Cắt chải", "Chải sáp vuốt kiểu"],
        },
        "haircut_men_modern": {
            "products": "Dầu gội và sản phẩm tạo kiểu dành cho tóc nam.",
            "styles": "Two-Block, Mullet hiện đại.",
            "steps": ["Tư vấn kiểu", "Cắt tạo form", "Sấy và hoàn thiện kiểu tóc"],
        },
        "hair_perm": {
            "products": "Thuốc uốn lạnh/nóng Goldwell và sản phẩm bảo vệ tóc.",
            "styles": "Uốn xoăn sóng nước, Uốn C-Fly.",
            "steps": ["Khảo sát chất tóc", "Gội và chia lọn", "Uốn định hình", "Trung hòa và dưỡng tóc", "Sấy hoàn thiện"],
        },
        "hair_repair": {
            "products": "Keratin và Collagen tươi.",
            "styles": "Phù hợp tóc khô xơ, hư tổn hoặc cần tăng độ bóng mượt.",
            "steps": ["Làm sạch tóc", "Thoa Keratin và Collagen", "Hấp nhiệt", "Phủ lụa khóa dưỡng chất", "Sấy hoàn thiện"],
        },
    }
    if category in standard_details:
        return {
            **standard_details[category],
            "before_length": "Không yêu cầu độ dài tóc cố định.",
            "after_length": "Theo kiểu tóc và mong muốn đã thống nhất với Stylist.",
        }
    if "color" in category or "nhuộm" in name:
        return {
            "products": "Thuốc nhuộm chuyên dụng (ví dụ L'Oréal Paris); Olaplex có thể được tư vấn bổ sung tùy nền tóc. Stylist xác nhận sản phẩm thực tế trước khi làm.",
            "styles": "Nâu lạnh, nâu socola, balayage hoặc màu theo tư vấn phù hợp với nền tóc và tông da.",
            "before_length": "Không yêu cầu độ dài cố định; tóc dài hơn có thể cần thêm sản phẩm và thời gian.",
            "after_length": "Không cắt tóc; độ dài giữ theo hiện trạng trừ khi khách yêu cầu tỉa.",
            "steps": ["Khảo sát nền tóc và thử lọn khi cần", "Tư vấn màu và thống nhất sản phẩm", "Chia tóc, pha và thoa màu", "Kiểm tra màu, xả sạch và dưỡng tóc", "Sấy, tạo kiểu và hướng dẫn chăm sóc"],
        }
    if "styling" in category or "uốn" in name or "duỗi" in name:
        return {
            "products": "Thuốc uốn/định hình chuyên dụng và sản phẩm bảo vệ tóc; Olaplex hoặc Collagen dưỡng có thể được đề xuất theo tình trạng tóc. Sản phẩm thực tế được xác nhận trước khi làm.",
            "styles": "Uốn lơi, sóng layer, xoăn lọn hoặc kiểu Restyle theo khuôn mặt và độ dài tóc.",
            "before_length": "Nên có độ dài từ ngang cằm để tạo nếp rõ; Stylist sẽ kiểm tra khả năng tạo kiểu theo mẫu.",
            "after_length": "Không cắt tóc; độ dài giữ theo hiện trạng, nếp uốn có thể làm tóc trông ngắn hơn.",
            "steps": ["Khảo sát chất tóc và tư vấn kiểu", "Gội, chia lọn và xử lý theo kỹ thuật", "Định hình nếp tóc", "Trung hòa/xả và dưỡng tóc", "Sấy tạo kiểu, hướng dẫn giữ nếp"],
        }
    if "care" in category or "treatment" in category or "gội" in name or "phục hồi" in name:
        return {
            "products": "Dầu gội, dầu xả và dưỡng chất phù hợp tình trạng tóc; có thể tham khảo Collagen tươi hoặc sản phẩm phục hồi chuyên dụng sau khi Stylist kiểm tra.",
            "styles": "Phù hợp mọi kiểu tóc; có thể sấy tự nhiên, sấy phồng hoặc tạo kiểu nhẹ sau chăm sóc.",
            "before_length": "Không yêu cầu độ dài tối thiểu.",
            "after_length": "Không cắt tóc; giữ nguyên độ dài và tạo kiểu nhẹ theo yêu cầu.",
            "steps": ["Kiểm tra da đầu và chất tóc", "Gội làm sạch", "Massage và thoa dưỡng chất", "Ủ/xả theo liệu trình", "Sấy hoàn thiện và tư vấn chăm sóc tại nhà"],
        }
    if "nữ" in name or "layer" in name:
        return {
            "products": "Dầu gội, dầu xả và sản phẩm bảo vệ nhiệt; sản phẩm tạo kiểu như L'Oréal Paris có thể dùng tùy lựa chọn của khách.",
            "styles": "Layer, Bob, U-cut hoặc kiểu phù hợp khuôn mặt và độ dày tóc.",
            "before_length": "Khuyến nghị tóc dài từ khoảng 5 cm để tạo dáng; kiểu cụ thể cần được xác nhận với Stylist.",
            "after_length": "Theo độ dài khách yêu cầu; Stylist trao đổi và xác nhận trước khi cắt.",
            "steps": ["Khảo sát chất tóc và khuôn mặt", "Gội xả", "Chia form, cắt và tạo kiểu", "Tỉa chỉnh các lớp tóc", "Sấy định hình và hướng dẫn tự chăm sóc"],
        }
    return {
        "products": "Dầu gội, dầu xả và sản phẩm tạo kiểu phù hợp; ví dụ L'Oréal Paris. Stylist xác nhận sản phẩm thực tế trước khi làm.",
        "styles": "Undercut, Side Part, Textured Crop hoặc kiểu được tư vấn theo khuôn mặt.",
        "before_length": "Khuyến nghị tóc dài từ khoảng 5 cm; độ dài phù hợp còn tùy kiểu khách chọn.",
        "after_length": "Theo kiểu tóc khách yêu cầu; Stylist xác nhận độ dài trước khi cắt.",
        "steps": ["Khảo sát chất tóc và thống nhất kiểu", "Gội xả", "Chia form và cắt/tạo kiểu", "Tỉa chỉnh và hoàn thiện", "Sấy định hình, hướng dẫn chăm sóc"],
    }


@app.route("/api/get-booked-slots")
@roles_required("customer")
def api_get_booked_slots():
    barber_id = request.args.get("barber_id", "").strip()
    appointment_date = request.args.get("date", "").strip()
    if not barber_id or not appointment_date:
        return jsonify({"error": "Vui lòng chọn Stylist và ngày hẹn."}), 400
    try:
        intervals = database.get_booked_slots(barber_id, appointment_date)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    busy_slots = []
    for hour in range(9, 20):
        for minute in (0, 30):
            start_minutes = hour * 60 + minute
            if start_minutes > 19 * 60 + 30:
                continue
            for interval in intervals:
                busy_start = sum(int(part) * factor for part, factor in zip(interval["start_time"].split(":"), (60, 1)))
                busy_end = sum(int(part) * factor for part, factor in zip(interval["end_time"].split(":"), (60, 1)))
                if start_minutes < busy_end and start_minutes + 30 > busy_start:
                    busy_slots.append(f"{hour:02d}:{minute:02d}")
                    break
    return jsonify(booked_slots=busy_slots, busy_intervals=intervals)


@app.route("/api/get-stylists")
@login_required
def api_get_stylists():
    """Return active accounts whose role is exactly stylist."""
    return jsonify([
        {"id": stylist["id"], "user_id": stylist.get("stylist_user_id"),
         "full_name": stylist["full_name"], "specialty": stylist.get("specialty") or "",
         "experience_years": stylist.get("experience_years", 0)}
        for stylist in _customer_stylists()
    ])


@app.route("/api/services")
@login_required
def api_services():
    return jsonify(database.list_services(active_only=True))


@app.route("/customer/booking", methods=["GET", "POST"])
@roles_required("customer")
def customer_booking():
    user = database.get_user(session["user_id"])
    services = database.get_all_services()
    stylists = _customer_stylists()

    if request.method == "POST":
        service_ids = request.form.getlist("service_ids")
        appointment_date = request.form.get("appointment_date", "").strip()
        start_time = request.form.get("start_time", "").strip()
        stylist_choice = request.form.get("stylist_id", "auto").strip() or "auto"
        note = request.form.get("note", "").strip()
        hair_condition = request.form.get("hair_condition", "").strip()
        style_request = request.form.get("style_request", "").strip()

        try:
            service_ids = list(dict.fromkeys(int(value) for value in service_ids))
            if not service_ids:
                raise ValueError("Vui lòng chọn ít nhất một dịch vụ.")
            customer_id = _get_or_create_customer(user)

            if stylist_choice == "auto":
                candidate_ids = [stylist["id"] for stylist in stylists]
                if not candidate_ids:
                    raise ValueError("Hiện chưa có Stylist nào sẵn sàng nhận lịch.")
            else:
                try:
                    candidate_id = int(stylist_choice)
                except ValueError as exc:
                    raise ValueError("Stylist đã chọn không hợp lệ.") from exc
                if candidate_id not in {stylist["id"] for stylist in stylists}:
                    raise ValueError("Stylist đã chọn không còn hoạt động.")
                candidate_ids = [candidate_id]

            last_error = None
            for candidate_id in candidate_ids:
                try:
                    appointment_id = database.create_appointment(
                        customer_id,
                        candidate_id,
                        appointment_date,
                        start_time,
                        "",
                        note,
                        service_ids,
                        user_id=session.get("user_id"),
                    )
                    conn = database.get_db_connection()
                    try:
                        conn.execute(
                            """UPDATE appointments SET hair_condition = ?, style_request = ?,
                               payment_method = 'Salon', payment_status = 'Unpaid' WHERE id = ?""",
                            (hair_condition or None, style_request or None, appointment_id),
                        )
                        conn.commit()
                    finally:
                        conn.close()
                    flash("Đặt lịch thành công! Vui lòng kiểm tra lịch hẹn và thanh toán.", "success")
                    return redirect(url_for("customer_history"))
                except ValueError as exc:
                    last_error = exc
                    if stylist_choice != "auto":
                        raise
            raise ValueError(str(last_error) if last_error else "Không thể xếp Stylist phù hợp.")
        except (TypeError, ValueError) as exc:
            flash(str(exc) or "Dữ liệu đặt lịch không hợp lệ.", "danger")

    return render_template(
        "booking.html",
        services=services,
        stylists=stylists,
        today=date.today().isoformat(),
    )


@app.route("/customer/history")
@roles_required("customer")
def customer_history():
    user = database.get_user(session["user_id"])
    appointments = []
    if user and user.get("phone"):
        conn = database.get_db_connection()
        try:
            appointments = [
                dict(row) for row in conn.execute(
                    """SELECT a.*, c.full_name AS customer_name,
                              COALESCE((SELECT customer_user.customer_code FROM users customer_user
                                        WHERE customer_user.role = 'customer' AND customer_user.phone = c.phone
                                        ORDER BY customer_user.id DESC LIMIT 1), c.customer_code) AS customer_code,
                              COALESCE(NULLIF(stylist_user.full_name, ''), b.full_name) AS stylist_name,
                              GROUP_CONCAT(s.name, ', ') AS service_names,
                              COALESCE(SUM(aps.quantity * aps.price), 0) AS amount
                       FROM appointments a
                       JOIN customers c ON c.id = a.customer_id
                       JOIN barbers b ON b.id = a.barber_id
                       LEFT JOIN users stylist_user ON stylist_user.id = b.user_id
                       LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
                       LEFT JOIN services s ON s.id = aps.service_id
                       WHERE c.phone = ?
                       GROUP BY a.id
                       ORDER BY CASE WHEN a.appointment_date = ? THEN 0
                                     WHEN a.status IN ('Completed', 'Cancelled') THEN 3
                                     WHEN a.payment_status IN ('Unpaid', 'Pending Verification') THEN 1
                                     WHEN a.status = 'Confirmed' THEN 2
                                     ELSE 2
                                END, a.id DESC""",
                    (user["phone"], date.today().isoformat()),
                ).fetchall()
            ]
        finally:
            conn.close()
    return render_template("customer_history.html", appointments=appointments)


@app.route("/reset_test_data", methods=["GET"])
@roles_required("customer")
def reset_test_data():
    user = database.get_user(session["user_id"])
    if not user or not user.get("phone"):
        flash("Không tìm thấy hồ sơ khách hàng để đặt lại lịch.", "danger")
        return redirect(url_for("customer_history"))

    conn = database.get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """UPDATE appointments
               SET status = 'Pending', payment_status = 'Unpaid',
                   status_before_cancel_request = NULL
               WHERE customer_id IN (SELECT id FROM customers WHERE phone = ?)""",
            (user["phone"],),
        )
        conn.commit()
        flash(f"Đã đặt lại {cursor.rowcount} lịch hẹn để kiểm thử.", "success")
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to reset current customer's test appointments")
        flash("Không thể đặt lại dữ liệu lịch hẹn.", "danger")
    finally:
        conn.close()
    return redirect(url_for("customer_history"))


@app.route("/customer/cancel/<int:appointment_id>", methods=["POST"])
@roles_required("customer")
def customer_cancel(appointment_id):
    user = database.get_user(session["user_id"])
    conn = database.get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """UPDATE appointments SET status = 'Cancelled', status_before_cancel_request = NULL
               WHERE id = ? AND payment_status = 'Unpaid'
                 AND status NOT IN ('Cancelled', 'Completed')
                 AND customer_id IN (SELECT id FROM customers WHERE phone = ?)""",
            (appointment_id, user.get("phone") if user else None),
        )
        if cursor.rowcount == 1:
            conn.commit()
            flash("Lịch hẹn đã được hủy.", "success")
        else:
            conn.rollback()
            flash("Chỉ có thể hủy lịch chưa thanh toán và chưa hoàn thành.", "danger")
    finally:
        conn.close()
    return redirect(url_for("customer_history"))


@app.route("/customer/confirm_payment/<int:appointment_id>", methods=["POST"])
@roles_required("customer")
def customer_confirm_payment(appointment_id):
    user = database.get_user(session["user_id"])
    conn = database.get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """UPDATE appointments SET payment_method = 'VietQR',
                       payment_status = 'Pending Verification'
               WHERE id = ? AND payment_status = 'Unpaid'
                 AND customer_id IN (SELECT id FROM customers WHERE phone = ?)""",
            (appointment_id, user.get("phone") if user else None),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            flash("Không thể gửi xác nhận thanh toán cho lịch hẹn này.", "danger")
        else:
            conn.commit()
            flash("Đã gửi xác nhận chuyển khoản. Salon sẽ kiểm tra giao dịch.", "success")
    finally:
        conn.close()
    return redirect(url_for("customer_history"))


@app.route("/customer/request_cancel/<int:appointment_id>", methods=["POST"])
@roles_required("customer")
def customer_request_cancel(appointment_id):
    user = database.get_user(session["user_id"])
    conn = database.get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        appointment = conn.execute(
            """SELECT a.id, a.status, a.payment_status FROM appointments a
               JOIN customers c ON c.id = a.customer_id
               WHERE a.id = ? AND c.phone = ?""",
            (appointment_id, user.get("phone") if user else None),
        ).fetchone()
        if not appointment:
            conn.rollback()
            flash("Lịch hẹn này không thể gửi yêu cầu hủy.", "danger")
        elif appointment["payment_status"] != "Unpaid":
            conn.rollback()
            flash("Lịch hẹn đã thanh toán hoặc đang chờ xác nhận. Vui lòng gọi Hotline: 0901111111.", "danger")
        elif appointment["status"] in {"Completed", "Cancelled", "Cancel Requested"}:
            conn.rollback()
            flash("Lịch hẹn này không thể gửi yêu cầu hủy.", "danger")
        else:
            conn.execute(
                """UPDATE appointments SET status_before_cancel_request = ?, status = 'Cancel Requested'
                   WHERE id = ?""",
                (appointment["status"], appointment_id),
            )
            conn.commit()
            flash("Đã gửi yêu cầu hủy lịch để Salon duyệt.", "success")
    finally:
        conn.close()
    return redirect(url_for("customer_history"))


def _admin_review_redirect():
    destination = request.form.get("return_to")
    if destination not in {"dashboard", "appointments"}:
        destination = "dashboard"
    return redirect(url_for(destination))


@app.route("/admin/verify_payment/<int:appointment_id>", methods=["POST"])
@roles_required("admin", "staff", "receptionist")
def admin_verify_payment(appointment_id):
    conn = database.get_db_connection()
    try:
        cursor = conn.execute(
            """UPDATE appointments SET payment_status = 'Paid Online'
               WHERE id = ? AND payment_status = 'Pending Verification'""",
            (appointment_id,),
        )
        conn.commit()
        if cursor.rowcount == 1:
            flash(f"Đã duyệt thanh toán cho lịch hẹn #{appointment_id}.", "success")
        else:
            flash("Lịch hẹn không ở trạng thái chờ xác minh thanh toán.", "warning")
    finally:
        conn.close()
    return _admin_review_redirect()


@app.route("/admin/approve_cancel/<int:appointment_id>", methods=["POST"])
@roles_required("admin", "staff", "receptionist")
def admin_approve_cancel(appointment_id):
    conn = database.get_db_connection()
    try:
        cursor = conn.execute(
            """UPDATE appointments
               SET status = 'Cancelled', status_before_cancel_request = NULL
               WHERE id = ? AND status = 'Cancel Requested'""",
            (appointment_id,),
        )
        conn.commit()
        if cursor.rowcount == 1:
            flash(f"Đã hủy lịch hẹn #{appointment_id}.", "success")
        else:
            flash("Không tìm thấy yêu cầu hủy đang chờ duyệt.", "warning")
    finally:
        conn.close()
    return _admin_review_redirect()


@app.route("/admin/reject_cancel/<int:appointment_id>", methods=["POST"])
@roles_required("admin", "staff", "receptionist")
def admin_reject_cancel(appointment_id):
    conn = database.get_db_connection()
    try:
        cursor = conn.execute(
            """UPDATE appointments
               SET status = COALESCE(NULLIF(status_before_cancel_request, ''), 'Pending'),
                   status_before_cancel_request = NULL
               WHERE id = ? AND status = 'Cancel Requested'""",
            (appointment_id,),
        )
        conn.commit()
        if cursor.rowcount == 1:
            flash(f"Đã từ chối yêu cầu hủy lịch #{appointment_id}.", "success")
        else:
            flash("Không tìm thấy yêu cầu hủy đang chờ duyệt.", "warning")
    finally:
        conn.close()
    return _admin_review_redirect()


@app.route("/customer/booking/<int:appointment_id>/payment", methods=["GET", "POST"])
@roles_required("customer")
def customer_payment(appointment_id):
    user = database.get_user(session["user_id"])
    if not user or not user.get("phone"):
        return "Không tìm thấy hồ sơ khách hàng.", 404

    conn = database.get_db_connection()
    try:
        appointment = conn.execute(
            """SELECT a.*, c.full_name AS customer_name,
                      COALESCE(NULLIF(stylist_user.full_name, ''), b.full_name) AS stylist_name,
                      GROUP_CONCAT(s.name, ', ') AS service_names,
                      COALESCE(SUM(aps.quantity * aps.price), 0) AS amount
               FROM appointments a
               JOIN customers c ON c.id = a.customer_id
               JOIN barbers b ON b.id = a.barber_id
               LEFT JOIN users stylist_user ON stylist_user.id = b.user_id
               LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
               LEFT JOIN services s ON s.id = aps.service_id
               WHERE a.id = ? AND c.phone = ?
               GROUP BY a.id""",
            (appointment_id, user["phone"]),
        ).fetchone()
        if not appointment:
            return "Không tìm thấy lịch hẹn.", 404

        if request.method == "POST":
            method = request.form.get("payment_method", "").strip()
            allowed_methods = {"Salon", "VietQR"}
            momo_template = os.getenv("MOMO_PAYMENT_URL_TEMPLATE", "").strip()
            if momo_template:
                allowed_methods.add("MoMo")
            if appointment["payment_status"] == "Paid Online":
                flash("Lịch hẹn này đã được thanh toán online.", "info")
            elif method not in allowed_methods:
                flash("Phương thức thanh toán không hợp lệ hoặc chưa được cấu hình.", "danger")
            else:
                conn.execute(
                    "UPDATE appointments SET payment_method = ? WHERE id = ?",
                    (method, appointment_id),
                )
                conn.commit()
                return redirect(url_for(
                    "customer_payment", appointment_id=appointment_id, method=method
                ))
    finally:
        conn.close()

    requested_method = request.args.get("method", "")
    available_methods = {"Salon", "VietQR"}
    if os.getenv("MOMO_PAYMENT_URL_TEMPLATE", "").strip():
        available_methods.add("MoMo")
    method = (
        requested_method if requested_method in available_methods
        else appointment["payment_method"] or "Salon"
    )
    vietqr_url = None
    momo_qr_url = None
    if method == "VietQR":
        bank_id = os.getenv("VIETQR_BANK_ID", "").strip()
        account_no = os.getenv("VIETQR_ACCOUNT_NO", "").strip()
        account_name = os.getenv("VIETQR_ACCOUNT_NAME", "").strip()
        if bank_id and account_no:
            params = {
                "amount": int(appointment["amount"]),
                "addInfo": f"Salon AI {appointment_id}",
            }
            if account_name:
                params["accountName"] = account_name
            vietqr_url = (
                f"https://img.vietqr.io/image/{quote(bank_id, safe='')}-"
                f"{quote(account_no, safe='')}-compact2.png?{urlencode(params)}"
            )
    elif method == "MoMo":
        momo_template = os.getenv("MOMO_PAYMENT_URL_TEMPLATE", "").strip()
        if momo_template:
            try:
                momo_link = momo_template.format(
                    amount=int(appointment["amount"]),
                    order_id=appointment_id,
                    order_info=quote(f"Salon AI {appointment_id}"),
                )
                momo_qr_url = "https://api.qrserver.com/v1/create-qr-code/?" + urlencode(
                    {"size": "260x260", "data": momo_link}
                )
            except (KeyError, ValueError, IndexError):
                flash("Cấu hình MOMO_PAYMENT_URL_TEMPLATE không hợp lệ.", "danger")

    return render_template(
        "customer_payment.html",
        appointment=dict(appointment),
        method=method,
        vietqr_url=vietqr_url,
        momo_qr_url=momo_qr_url,
        momo_enabled=bool(os.getenv("MOMO_PAYMENT_URL_TEMPLATE", "").strip()),
    )


@app.route("/api/customer/style-advice", methods=["POST"])
@roles_required("customer")
def customer_style_advice():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Vui lòng nhập câu hỏi tư vấn."}), 400
    if len(message) > 1500:
        return jsonify({"error": "Câu hỏi tối đa 1500 ký tự."}), 400
    result = ai_service.advise_hairstyle(
        message,
        database.list_services(active_only=True),
        hair_condition=(data.get("hair_condition") or "").strip(),
        style_request=(data.get("style_request") or "").strip(),
    )
    return jsonify(result)


@app.route("/api/payments/confirmed", methods=["POST"])
def payment_confirmed():
    """Accept a trusted payment-adapter callback after provider-side verification."""
    webhook_token = os.getenv("PAYMENT_WEBHOOK_TOKEN", "").strip()
    supplied_token = request.headers.get("X-Payment-Webhook-Token", "")
    if not webhook_token:
        return jsonify({"error": "Payment callback is not configured."}), 503
    if not hmac.compare_digest(supplied_token, webhook_token):
        return jsonify({"error": "Unauthorized."}), 401

    data = request.get_json(silent=True) or {}
    try:
        appointment_id = int(data.get("appointment_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid appointment_id."}), 400

    conn = database.get_db_connection()
    try:
        cursor = conn.execute(
            """UPDATE appointments SET payment_status = 'Paid Online'
               WHERE id = ? AND payment_method IN ('VietQR', 'MoMo')""",
            (appointment_id,),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"error": "Online appointment not found."}), 404
        conn.commit()
        return jsonify({"appointment_id": appointment_id, "payment_status": "Paid Online"})
    finally:
        conn.close()


@app.route("/stylist/tasks")
@roles_required("stylist", "admin")
def stylist_tasks():
    user_id = session.get("user_id")
    barber = database.get_barber_for_user(user_id)
    if session.get("role") == "stylist" and not barber:
        flash("Tài khoản Stylist chưa được liên kết với hồ sơ thợ.", "warning")
        appointments = []
    else:
        conn = database.get_db_connection()
        try:
            base_sql = """
                SELECT a.*, c.full_name AS customer_name, c.phone AS customer_phone,
                       b.full_name AS barber_name, GROUP_CONCAT(s.name, ', ') AS service_names,
                       COALESCE(SUM(aps.quantity * aps.price), 0) AS amount
                FROM appointments a
                JOIN customers c ON c.id = a.customer_id
                JOIN barbers b ON b.id = a.barber_id
                LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
                LEFT JOIN services s ON s.id = aps.service_id
            """
            where = " WHERE a.appointment_date = ?"
            params = [date.today().isoformat()]
            if barber:
                where += " AND a.barber_id = ?"
                params.append(barber["id"])
            appointments = [
                dict(row) for row in conn.execute(
                    base_sql + where + " GROUP BY a.id ORDER BY a.start_time ASC", params
                ).fetchall()
            ]
        finally:
            conn.close()

    stats = {
        "total": len(appointments),
        "in_progress": sum(item["status"] == "In Progress" for item in appointments),
        "completed": sum(item["status"] == "Completed" for item in appointments),
        "revenue": sum(
            float(item["amount"] or 0)
            for item in appointments
            if item["status"] != "Cancelled"
        ),
    }
    return render_template(
        "stylist_tasks.html",
        appointments=appointments,
        stats=stats,
        stylist_name=session.get("full_name", "Stylist"),
        today=date.today(),
    )


@app.route("/stylist/update_status/<int:appointment_id>", methods=["POST"])
@roles_required("stylist", "admin")
def stylist_update_status(appointment_id):
    new_status = request.form.get("status", "").strip()
    if new_status not in {"In Progress", "Completed", "Cancelled"}:
        flash("Trạng thái cập nhật không hợp lệ.", "danger")
        return redirect(url_for("stylist_tasks"))

    barber = database.get_barber_for_user(session.get("user_id"))
    if session.get("role") == "stylist" and not barber:
        flash("Tài khoản Stylist chưa được liên kết với hồ sơ thợ.", "danger")
        return redirect(url_for("stylist_tasks"))

    conn = database.get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        appointment = conn.execute(
            "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
        if not appointment or (barber and appointment["barber_id"] != barber["id"]):
            conn.rollback()
            flash("Không tìm thấy lịch hẹn được phân công cho bạn.", "danger")
            return redirect(url_for("stylist_tasks"))

        allowed_transitions = {
            "Pending": {"In Progress", "Cancelled"},
            "Confirmed": {"In Progress", "Cancelled"},
            "In Progress": {"Completed"},
        }
        if new_status not in allowed_transitions.get(appointment["status"], set()):
            conn.rollback()
            flash("Không thể chuyển lịch hẹn sang trạng thái này.", "danger")
            return redirect(url_for("stylist_tasks"))

        conn.execute(
            "UPDATE appointments SET status = ? WHERE id = ?",
            (new_status, appointment_id),
        )
        if new_status == "Completed":
            service_rows = conn.execute(
                "SELECT service_id FROM appointment_services WHERE appointment_id = ?",
                (appointment_id,),
            ).fetchall()
            for service_row in service_rows:
                exists = conn.execute(
                    """SELECT 1 FROM customer_history
                       WHERE appointment_id = ? AND service_id = ? LIMIT 1""",
                    (appointment_id, service_row["service_id"]),
                ).fetchone()
                if not exists:
                    conn.execute(
                        """INSERT INTO customer_history(
                           customer_id, appointment_id, service_id, customer_note, result
                           ) VALUES (?, ?, ?, ?, ?)""",
                        (appointment["customer_id"], appointment_id,
                         service_row["service_id"], appointment["note"],
                         "Hoàn thành dịch vụ"),
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    flash("Cập nhật trạng thái thành công!", "success")
    return redirect(url_for("stylist_tasks"))


@app.route("/stylist/history")
@roles_required("stylist", "admin")
def stylist_history():
    barber = database.get_barber_for_user(session.get("user_id"))
    if session.get("role") == "stylist" and not barber:
        flash("Tài khoản Stylist chưa được liên kết với hồ sơ thợ.", "warning")
        appointments = []
    else:
        date_filter = request.args.get("date", "").strip()
        search = request.args.get("q", "").strip()
        conn = database.get_db_connection()
        try:
            sql = """
                SELECT a.*, c.full_name AS customer_name, c.phone AS customer_phone,
                       b.full_name AS barber_name, GROUP_CONCAT(s.name, ', ') AS service_names,
                       COALESCE(SUM(aps.quantity * aps.price), 0) AS amount
                FROM appointments a
                JOIN customers c ON c.id = a.customer_id
                JOIN barbers b ON b.id = a.barber_id
                LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
                LEFT JOIN services s ON s.id = aps.service_id
                WHERE a.status IN ('Completed', 'Cancelled')
            """
            params = []
            if barber:
                sql += " AND a.barber_id = ?"
                params.append(barber["id"])
            if date_filter:
                sql += " AND a.appointment_date = ?"
                params.append(date_filter)
            if search:
                sql += " AND (c.full_name LIKE ? OR c.phone LIKE ? OR s.name LIKE ?)"
                params.extend([f"%{search}%"] * 3)
            sql += " GROUP BY a.id ORDER BY a.appointment_date DESC, a.start_time DESC"
            appointments = [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    return render_template(
        "stylist_history.html",
        appointments=appointments,
        selected_date=request.args.get("date", "").strip(),
        query=request.args.get("q", "").strip(),
    )


@app.route("/stylist/profile", methods=["GET", "POST"])
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = session["user_id"]
    user = database.get_user(user_id)
    if not user:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        new_password = request.form.get("new_password", "")
        if not full_name:
            flash("Họ và tên không được để trống.", "danger")
            return render_template("profile.html", user=user), 400
        if phone and not re.fullmatch(r"0\d{9}", phone):
            flash("Số điện thoại không hợp lệ.", "danger")
            return render_template("profile.html", user=user), 400
        if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            flash("Email không đúng định dạng.", "danger")
            return render_template("profile.html", user=user), 400

        conn = database.get_db_connection()
        try:
            linked_customer = None
            if user.get("phone"):
                linked_customer = conn.execute(
                    "SELECT id FROM customers WHERE phone = ?", (user["phone"],)
                ).fetchone()
            if new_password:
                conn.execute(
                    """UPDATE users SET full_name = ?, phone = ?, email = ?, password_hash = ?
                       WHERE id = ?""",
                    (full_name, phone or None, email or None,
                     generate_password_hash(new_password), user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET full_name = ?, phone = ?, email = ? WHERE id = ?",
                    (full_name, phone or None, email or None, user_id),
                )
            conn.execute(
                "UPDATE barbers SET full_name = ?, phone = ? WHERE user_id = ?",
                (full_name, phone or None, user_id),
            )
            if linked_customer:
                conn.execute(
                    "UPDATE customers SET full_name = ?, phone = ?, email = ? WHERE id = ?",
                    (full_name, phone, email or None, linked_customer["id"]),
                )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("Số điện thoại đã được sử dụng cho hồ sơ khách hàng khác.", "danger")
            return render_template("profile.html", user=user), 400
        finally:
            conn.close()

        session["full_name"] = full_name
        session["user_name"] = full_name
        flash("Đã cập nhật hồ sơ cá nhân.", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html", user=user)


@app.route("/admin/profile", methods=["GET", "POST"])
@roles_required("admin", "receptionist", "staff")
def admin_profile():
    user = database.get_user(session["user_id"])
    if not user:
        session.clear()
        return redirect(url_for("login"))
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not full_name:
            flash("Họ tên không được để trống.", "danger")
            return render_template("admin/profile.html", user=user), 400
        if new_password and len(new_password) < 6:
            flash("Mật khẩu mới cần ít nhất 6 ký tự.", "danger")
            return render_template("admin/profile.html", user=user), 400
        if new_password != confirm_password:
            flash("Mật khẩu xác nhận chưa khớp.", "danger")
            return render_template("admin/profile.html", user=user), 400
        conn = database.get_db_connection()
        try:
            if new_password:
                conn.execute(
                    "UPDATE users SET full_name = ?, password_hash = ? WHERE id = ?",
                    (full_name, generate_password_hash(new_password), user["id"]),
                )
            else:
                conn.execute(
                    "UPDATE users SET full_name = ? WHERE id = ?",
                    (full_name, user["id"]),
                )
            if user.get("role") in {"stylist", "barber"}:
                conn.execute(
                    "UPDATE barbers SET full_name = ? WHERE user_id = ?",
                    (full_name, user["id"]),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        session["full_name"] = full_name
        session["user_name"] = full_name
        flash("Đã cập nhật hồ sơ tài khoản.", "success")
        return redirect(url_for("admin_profile"))
    return render_template("admin/profile.html", user=user)


@app.route("/admin/accounts")
@roles_required("admin", "receptionist", "staff")
def admin_accounts():
    """Danh sách tài khoản; quyền lễ tân chỉ được xem."""
    conn = database.get_db_connection()
    try:
        accounts = [dict(row) for row in conn.execute(
            """SELECT u.id, u.username, u.full_name, u.phone, u.email, u.role, u.is_active,
                      CASE
                        WHEN u.role = 'customer' THEN COALESCE(c.customer_code, 'KH' || printf('%03d', c.id))
                        WHEN u.role = 'admin' THEN '#AD' || printf('%02d',
                          (SELECT COUNT(*) FROM users x WHERE x.role='admin' AND x.username <= u.username))
                        WHEN u.role IN ('receptionist','staff') THEN '#LT' || printf('%02d',
                          (SELECT COUNT(*) FROM users x WHERE x.role IN ('receptionist','staff') AND x.username <= u.username))
                        WHEN u.role = 'stylist' THEN '#ST' || printf('%02d',
                          (SELECT COUNT(*) FROM users x WHERE x.role='stylist' AND x.username <= u.username))
                        ELSE '#' || u.id END AS display_code,
                      CASE WHEN u.role='customer' THEN c.id ELSE NULL END AS customer_id
               FROM users u
               LEFT JOIN customers c ON c.phone = u.phone AND u.role = 'customer'
               ORDER BY CASE u.role WHEN 'admin' THEN 0 WHEN 'receptionist' THEN 1
                                    WHEN 'staff' THEN 2 WHEN 'stylist' THEN 3 ELSE 4 END,
                        u.username ASC"""
        ).fetchall()]
    finally:
        conn.close()
    return render_template(
        "admin/accounts.html",
        accounts=accounts,
        read_only=session.get("role") != "admin",
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        if not all((username, password, full_name, phone, email)):
            flash("Vui lòng điền đầy đủ thông tin.", "danger")
            return render_template("register.html"), 400
        if len(username) < 4:
            flash("Tên đăng nhập phải có ít nhất 4 ký tự.", "danger")
            return render_template("register.html"), 400
        email_pattern = r"[A-Za-z0-9](?:[A-Za-z0-9._%+-]*[A-Za-z0-9])?@gmail\.com"
        if not re.fullmatch(email_pattern, email, re.IGNORECASE) or ".." in email:
            flash("Email phải đúng định dạng @gmail.com", "danger")
            return render_template("register.html"), 400
        if not re.fullmatch(r"0\d{9}", phone):
            flash("Số điện thoại không hợp lệ", "danger")
            return render_template("register.html"), 400
        try:
            database.register_user(
                username, password, full_name, phone, role="customer", email=email
            )
        except sqlite3.IntegrityError:
            flash("Tên đăng nhập đã tồn tại.", "danger")
            return render_template("register.html"), 400
        except ValueError:
            flash("Thông tin đăng ký không hợp lệ.", "danger")
            return render_template("register.html"), 400
        flash("Đăng ký tài khoản thành công! Vui lòng đăng nhập.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/contact")
def contact():
    admin_email = "admin@hairstudio.com"
    conn = database.get_db_connection()
    try:
        admin = conn.execute(
            "SELECT email FROM users WHERE role = 'admin' OR username = 'admin' ORDER BY id LIMIT 1"
        ).fetchone()
        if admin and admin["email"] and admin["email"].strip():
            admin_email = admin["email"].strip()
    finally:
        conn.close()
    return render_template("contact.html", admin_email=admin_email)


@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "customer":
        return redirect(url_for("customer_booking"))
    if session.get("role") == "stylist":
        return redirect(url_for("stylist_tasks"))
    review_appointments = []
    latest_appointments = []
    # Role‑based data preparation
    if is_barber():
        # Find barber record linked to the logged‑in user
        barber = database.get_barber_for_user(session.get("user_id"))
        if barber:
            # Barber sees only his/her own appointments for today; no global stats
            today_appointments = database.list_appointments(date.today().isoformat(), barber_id=barber["id"])
            stats = {}
            popular = []
        else:
            flash("Tài khoản thợ của bạn chưa được liên kết với hồ sơ thợ.", "warning")
            today_appointments = []
            stats = {}
            popular = []
    else:
        # Admin / Receptionist – full dashboard
        stats = database.dashboard_stats()
        today_appointments = database.list_appointments(date.today().isoformat())
        today_appointments.sort(key=lambda appointment: appointment.get("start_time") or "")
        all_appointments = database.list_appointments()
        latest_appointments = database.dashboard_latest_appointments(5)
        popular = database.popular_services(limit=5)
        if session.get("role") in {"admin", "staff", "receptionist"}:
            review_appointments = all_appointments
    cancel_requests = [a for a in review_appointments if a["status"] == "Cancel Requested"]
    payment_verifications = [
        a for a in review_appointments
        if a.get("payment_status") == "Pending Verification"
    ]
    return render_template(
        "dashboard.html",
        stats=stats,
        today_appointments=today_appointments,
        popular=popular,
        cancel_requests=cancel_requests,
        payment_verifications=payment_verifications,
        latest_appointments=latest_appointments,
    )


@app.route("/api/admin/dashboard/appointments")
@roles_required("admin", "receptionist", "staff")
def api_dashboard_latest_appointments():
    """Provide the newest shared appointments for the live admin dashboard."""
    return jsonify(appointments=database.dashboard_latest_appointments(5))


@app.route("/admin/reports")
@roles_required("admin", "receptionist")
def admin_reports():
    month = request.args.get("month", "").strip() or None
    try:
        report = database.admin_revenue_report(month)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("admin_reports"))
    return render_template("admin/reports.html", report=report)


@app.route("/admin/reports/expenses", methods=["POST"])
@admin_required
def admin_report_expenses():
    month = request.form.get("month", "").strip()
    try:
        database.set_monthly_expense(month, request.form.get("amount", "0"))
        flash("Đã cập nhật chi phí vận hành của tháng.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin_reports", month=month))


@app.route("/admin/reports/payroll/close", methods=["POST"])
@admin_required
def admin_close_payroll():
    month = request.form.get("month", "").strip()
    try:
        database.close_monthly_payroll(month, session.get("user_id"))
        flash("Đã quyết toán và chốt lương tháng.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin_reports", month=month))


@app.route("/admin/employees", methods=["GET", "POST"])
@admin_required
def admin_employees():
    if request.method == "POST":
        try:
            database.create_employee(
                request.form.get("username", ""), request.form.get("password", ""),
                request.form.get("full_name", ""), request.form.get("phone", ""),
                request.form.get("email", ""), request.form.get("role", "receptionist"),
                request.form.get("specialty", ""), request.form.get("base_salary", 5000000),
                request.form.get("commission_rate", 15),
                request.form.get("experience_years", 0), request.form.get("specialties", ""),
                request.form.get("bio", ""), request.form.get("gender_focus", "both"),
                request.form.get("rating", 0), request.form.get("review_count", 0),
                request.form.get("total_customers", 0), request.form.get("awards", ""),
                request.form.get("philosophy", ""),
            )
            flash("Đã tạo tài khoản nhân viên.", "success")
        except ValueError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("admin_employees"))
    employees = database.list_employees()
    return render_template(
        "admin/employees.html",
        employees=employees,
        employee_stats={
            "total": len(employees),
            "stylists": sum(item.get("role") == "stylist" for item in employees),
            "management": sum(item.get("role") in {"admin", "receptionist", "staff"} for item in employees),
        },
    )


@app.route("/admin/employees/<int:employee_id>/edit", methods=["POST"])
@admin_required
def admin_employee_edit(employee_id):
    try:
        database.update_employee(
            employee_id, request.form.get("username", ""), request.form.get("full_name", ""),
            request.form.get("phone", ""), request.form.get("email", ""),
            request.form.get("role", "receptionist"), request.form.get("specialty", ""),
            request.form.get("base_salary", 5000000), request.form.get("commission_rate", 15),
            request.form.get("experience_years", 0), request.form.get("specialties", ""),
            request.form.get("bio", ""), request.form.get("gender_focus", "both"),
            request.form.get("rating", 0), request.form.get("review_count", 0),
            request.form.get("total_customers", 0), request.form.get("awards", ""),
            request.form.get("philosophy", ""),
        )
        flash("Đã cập nhật thông tin nhân viên.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin_employees"))


@app.route("/admin/employees/<int:employee_id>/password", methods=["POST"])
@admin_required
def admin_employee_password(employee_id):
    try:
        database.change_employee_password(employee_id, request.form.get("password", ""))
        flash("Đã đổi mật khẩu nhân viên.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin_employees"))


@app.route("/admin/employees/<int:employee_id>/toggle", methods=["POST"])
@admin_required
def admin_employee_toggle(employee_id):
    try:
        active = request.form.get("active") == "1"
        database.set_employee_active(employee_id, active, session.get("user_id"))
        flash("Đã cập nhật trạng thái tài khoản.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin_employees"))


@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    if request.method == "POST":
        if session.get("role") not in ("admin", "receptionist", "staff"):
            flash("Bạn không có quyền thực hiện thao tác này.", "danger")
            return redirect(url_for("customers"))
        payload = {
            "full_name": request.form.get("full_name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "gender": request.form.get("gender", "").strip(),
            "birthday": request.form.get("birthday", "").strip(),
            "note": request.form.get("note", "").strip(),
        }
        if not payload["full_name"] or not payload["phone"]:
            flash("Họ tên và số điện thoại là bắt buộc.", "danger")
        else:
            try:
                database.create_customer(payload)
                flash("Đã thêm khách hàng.", "success")
            except ValueError as exc:
                flash(str(exc), "danger")
        return redirect(url_for("customers"))

    q = request.args.get("q", "").strip()
    rows = database.list_customers(q)
    gender_counts = {
        "male": sum(1 for row in rows if row.get("gender") == "Nam"),
        "female": sum(1 for row in rows if row.get("gender") == "Nữ"),
    }
    new_customers_month = sum(
        1 for row in rows if str(row.get("created_at") or "").startswith("2026-10")
    )
    customer_appointments = {
        row["id"]: database.list_appointments(customer_id=row["id"])
        for row in rows
    }
    loyal_count = sum(1 for row in rows if int(row.get("total_appointments") or 0) >= 2)
    return render_template(
        "customers.html",
        customers=rows,
        query=q,
        gender_counts=gender_counts,
        new_customers_month=new_customers_month,
        loyal_count=loyal_count,
        customer_appointments=customer_appointments,
    )


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
@roles_required("admin", "receptionist", "staff")
def delete_customer(customer_id):
    try:
        database.delete_customer(customer_id)
        flash("Đã xóa khách hàng.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("customers"))


@app.route("/customers/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    customer = database.get_customer(customer_id)
    if not customer:
        return "Không tìm thấy khách hàng", 404
    # Determine appointments list based on role
    if is_barber():
        barber = database.get_barber_for_user(session.get("user_id"))
        if barber:
            appointments = database.list_appointments(customer_id=customer_id, barber_id=barber["id"])
        else:
            flash("Tài khoản thợ của bạn chưa được liên kết với hồ sơ thợ.", "warning")
            appointments = []
    else:
        # Admin / Receptionist – full list
        appointments = database.list_appointments(customer_id=customer_id)
    return render_template(
        "customer_detail.html",
        customer=customer,
        history=database.customer_history(customer_id),
        appointments=appointments,
    )


@app.route("/customers/<int:customer_id>/edit", methods=["POST"])
@roles_required("admin", "receptionist", "staff")
def edit_customer(customer_id):
    try:
        database.update_customer(
            customer_id,
            request.form.get("full_name", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("email", "").strip(),
            request.form.get("gender", "").strip(),
            request.form.get("birthday", "").strip(),
            request.form.get("note", "").strip(),
        )
        flash("Đã cập nhật khách hàng.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("customer_detail", customer_id=customer_id))


@app.route("/barbers")
@roles_required("admin", "receptionist")
def barbers():
    return render_template("barbers.html", barbers=database.list_barbers())


@app.route("/barbers", methods=["POST"])
@roles_required("admin")
def create_barber():
    try:
        database.create_barber(
            request.form.get("full_name", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("specialty", "").strip(),
            request.form.get("experience", "").strip(),
            request.form.get("status", "active"),
        )
        flash("Đã thêm thợ.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("barbers"))


@app.route("/services", methods=["GET", "POST"])
@admin_required
def services():
    if request.method == "POST":
        try:
            database.create_service(
                request.form.get("name", ""), request.form.get("category", ""),
                request.form.get("description", ""), request.form.get("duration_minutes", 30),
                request.form.get("price", 0),
                request.form.get("style_type", ""), request.form.get("suitable_length", ""),
                request.form.get("color_tone", ""), request.form.get("chemical_brands", ""),
                request.form.get("chemical_origin", ""), request.form.get("inspection_cert", ""),
            )
            flash("Đã thêm dịch vụ.", "success")
        except (TypeError, ValueError) as exc:
            flash(str(exc), "danger")
        return redirect(url_for("services"))
    return render_template("services.html", services=database.list_services())


@app.route("/admin/services/add", methods=["POST"])
@admin_required
def admin_service_add():
    try:
        database.create_service(
            request.form.get("name", ""), request.form.get("category", ""),
            request.form.get("description", ""), request.form.get("duration_minutes", 30),
            request.form.get("price", 0),
            request.form.get("style_type", ""), request.form.get("suitable_length", ""),
            request.form.get("color_tone", ""), request.form.get("chemical_brands", ""),
            request.form.get("chemical_origin", ""), request.form.get("inspection_cert", ""),
        )
        flash("Đã thêm dịch vụ.", "success")
    except (TypeError, ValueError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("services"))


@app.route("/admin/services/<int:service_id>/edit", methods=["POST"])
@admin_required
def admin_service_edit(service_id):
    try:
        database.update_service(
            service_id, request.form.get("name", ""), request.form.get("category", ""),
            request.form.get("description", ""), request.form.get("duration_minutes", 30),
            request.form.get("price", 0),
            request.form.get("style_type", ""), request.form.get("suitable_length", ""),
            request.form.get("color_tone", ""), request.form.get("chemical_brands", ""),
            request.form.get("chemical_origin", ""), request.form.get("inspection_cert", ""),
        )
        flash("Đã cập nhật dịch vụ.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("services"))


@app.route("/admin/services/<int:service_id>/delete", methods=["POST"])
@admin_required
def admin_service_delete(service_id):
    try:
        database.delete_service(service_id)
        flash("Đã xóa dịch vụ.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("services"))


@app.route("/admin/services/edit", methods=["POST"])
@admin_required
def admin_service_edit_form():
    try:
        database.update_service(
            int(request.form.get("service_id", "")), request.form.get("name", ""),
            request.form.get("category", ""), request.form.get("description", ""),
            request.form.get("duration_minutes", 30), request.form.get("price", 0),
            request.form.get("style_type", ""), request.form.get("suitable_length", ""),
            request.form.get("color_tone", ""), request.form.get("chemical_brands", ""),
            request.form.get("chemical_origin", ""), request.form.get("inspection_cert", ""),
        )
        flash("Đã cập nhật dịch vụ.", "success")
    except (TypeError, ValueError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("services"))


@app.route("/admin/services/delete", methods=["POST"])
@admin_required
def admin_service_delete_form():
    try:
        database.delete_service(int(request.form.get("service_id", "")))
        flash("Đã xóa dịch vụ.", "success")
    except (TypeError, ValueError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("services"))


@app.route("/appointments")
@login_required
def appointments():
    date_filter = request.args.get("date", "").strip()
    status = request.args.get("status", "").strip().lower()
    search_query = request.args.get("q", "").strip()
    if request.args.get("filter", "").strip().lower() == "today":
        date_filter = date.today().isoformat()
    barber_id = None
    # Prepare lists that will be passed to the template
    customers_list = []
    barbers_list = []
    if session.get("role") == "barber":
        barber = database.get_barber_for_user(session.get("user_id"))
        if not barber:
            flash("Tài khoản thợ của bạn chưa được liên kết với hồ sơ thợ.", "warning")
            return render_template(
                "appointments.html",
                appointments=[],
                customers=[],
                barbers=[],
                services=database.list_services(),
                selected_date=date_filter,
                selected_status=status,
                search_query=search_query,
                counts={"all": 0, "today": 0, "pending": 0, "confirmed": 0, "completed": 0, "cancelled": 0},
                today_value=date.today().isoformat(),
                cancel_requests=[],
            )
        barber_id = barber["id"]
        # Barber sees only own appointments; no need for full customer/barber lists
        customers_list = []
        barbers_list = []
    else:
        # Admin / Receptionist – full data for creating appointments
        customers_list = database.list_customers()
        barbers_list = database.list_barbers()

    all_appointments = database.list_appointments(barber_id=barber_id)
    counts = {
        "all": len(all_appointments),
        "today": sum(a.get("appointment_date") == date.today().isoformat() for a in all_appointments),
        "pending": sum(a.get("status") not in {"Completed", "Cancelled"} and (a.get("status") in {"Pending", "Cancel Requested"} or a.get("payment_status") in {"Unpaid", "Pending Verification"}) for a in all_appointments),
        "confirmed": sum(a.get("status") == "Confirmed" for a in all_appointments),
        "completed": sum(a.get("status") == "Completed" for a in all_appointments),
        "cancelled": sum(a.get("status") == "Cancelled" for a in all_appointments),
    }
    filtered_appointments = [a for a in all_appointments if not date_filter or a.get("appointment_date") == date_filter]
    if status == "pending":
        filtered_appointments = [a for a in filtered_appointments if a.get("status") not in {"Completed", "Cancelled"} and (a.get("status") in {"Pending", "Cancel Requested"} or a.get("payment_status") in {"Unpaid", "Pending Verification"})]
    elif status in {"confirmed", "completed", "cancelled"}:
        status_value = {"confirmed": "Confirmed", "completed": "Completed", "cancelled": "Cancelled"}[status]
        filtered_appointments = [a for a in filtered_appointments if a.get("status") == status_value]
    if search_query:
        needle = search_query.casefold()
        filtered_appointments = [a for a in filtered_appointments if needle in " ".join(str(a.get(key) or "") for key in ("id", "customer_code", "customer_name", "customer_phone", "barber_name", "service_names")).casefold()]
    cancel_requests = [a for a in all_appointments if a.get("status") == "Cancel Requested"]
    return render_template(
        "appointments.html",
        appointments=filtered_appointments,
        customers=customers_list,
        barbers=barbers_list,
        services=database.list_services(),
        selected_date=date_filter,
        selected_status=status,
        search_query=search_query,
        counts=counts,
        today_value=date.today().isoformat(),
        cancel_requests=cancel_requests,
    )


@app.route("/appointments/create", methods=["POST"])
@roles_required("admin", "receptionist", "staff")
def create_appointment():
    try:
        raw_cust = request.form.get("customer_id", "").strip()
        raw_barber = request.form.get("barber_id", "").strip()
        if not raw_cust or not raw_barber:
            flash("Khách hàng và thợ là bắt buộc.", "danger")
            return redirect(url_for("appointments"))
        try:
            customer_id = int(raw_cust)
            barber_id = int(raw_barber)
        except ValueError:
            flash("Khách hàng hoặc thợ không hợp lệ.", "danger")
            return redirect(url_for("appointments"))

        raw_service_ids = request.form.getlist("service_ids")
        if not raw_service_ids:
            flash("Hãy chọn ít nhất một dịch vụ.", "danger")
            return redirect(url_for("appointments"))
        try:
            service_ids = [int(x) for x in raw_service_ids]
        except ValueError:
            flash("Dịch vụ đã chọn không hợp lệ.", "danger")
            return redirect(url_for("appointments"))

        appointment_date = request.form.get("appointment_date", "").strip()
        start_time = request.form.get("start_time", "").strip()
        end_time = request.form.get("end_time", "").strip()
        note = request.form.get("note", "").strip()

        appt_id = database.create_appointment(
            customer_id,
            barber_id,
            appointment_date,
            start_time,
            end_time,
            note,
            service_ids,
            user_id=session.get("user_id"),
        )
        flash(f"Đã tạo lịch hẹn #{appt_id}.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("appointments"))


@app.route("/appointments/<int:appointment_id>/status", methods=["POST"])
@roles_required("admin", "receptionist", "staff", "barber")
def update_appointment_status(appointment_id):
    try:
        new_status = request.form.get("status", "").strip()
        if new_status not in {"Pending", "Confirmed", "Completed", "Cancelled"}:
            flash("Trạng thái không hợp lệ.", "danger")
            return redirect(url_for("appointments"))

        appt = database.get_appointment(appointment_id)
        if not appt:
            flash("Không tìm thấy lịch hẹn.", "danger")
            return redirect(url_for("appointments"))

        if session.get("role") == "barber":
            barber = database.get_barber_for_user(session.get("user_id"))
            if not barber or appt["barber_id"] != barber["id"]:
                flash("Bạn chỉ có quyền cập nhật lịch hẹn của chính mình.", "danger")
                return redirect(url_for("appointments"))

        database.update_appointment_status(appointment_id, new_status)
        flash("Đã cập nhật trạng thái lịch hẹn.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("appointments"))


@app.route("/appointments/<int:appointment_id>/reschedule", methods=["POST"])
@roles_required("admin", "receptionist", "staff")
def reschedule_appointment(appointment_id):
    new_barber_id = request.form.get("barber_id", type=int)
    new_date = request.form.get("appointment_date", "").strip()
    new_start = request.form.get("start_time", "").strip()
    service_ids = request.form.getlist("service_ids")
    try:
        total_price = database.update_appointment_details(
            appointment_id, service_ids, new_barber_id, new_date, new_start
        )
        flash(f"Đã cập nhật lịch #{appointment_id}. Tổng tiền mới: {format_vnd(total_price)}.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("appointments"))


@app.route("/appointments/<int:appointment_id>/collect", methods=["POST"])
@roles_required("admin", "receptionist", "staff")
def collect_appointment_payment(appointment_id):
    appointment = database.get_appointment(appointment_id)
    if not appointment or appointment.get("status") != "Completed":
        flash("Chỉ thu tiền tại quầy cho lịch đã hoàn thành.", "warning")
        return redirect(url_for("appointments"))
    try:
        database.create_invoice(appointment_id, payment_method="Cash", payment_status="Paid")
        conn = database.get_db_connection()
        try:
            conn.execute("UPDATE appointments SET payment_status = 'Paid' WHERE id = ?", (appointment_id,))
            conn.commit()
        finally:
            conn.close()
        flash(f"Đã thu tiền và tạo hóa đơn cho lịch #{appointment_id}.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("appointments"))


@app.route("/invoices")
@roles_required("admin", "receptionist", "staff")
def invoices():
    invoice_rows = database.list_invoices()
    completed_total = sum(float(row.get("total") or 0) for row in invoice_rows)
    payment_counts = {}
    for row in invoice_rows:
        method = (row.get("payment_method") or "Cash").strip().lower()
        key = "Chuyển khoản" if method in {"banking", "transfer", "bank", "online"} else ("Thẻ" if method == "card" else "Tiền mặt")
        payment_counts[key] = payment_counts.get(key, 0) + 1
    return render_template(
        "invoices.html",
        invoices=invoice_rows,
        billable_appointments=database.list_billable_appointments(),
        invoice_stats={
            "revenue": completed_total,
            "count": len(invoice_rows),
            "cash": payment_counts.get("Tiền mặt", 0),
            "transfer": payment_counts.get("Chuyển khoản", 0),
            "card": payment_counts.get("Thẻ", 0),
        },
    )


@app.route("/invoices/create", methods=["POST"])
@roles_required("admin", "receptionist", "staff")
def create_invoice():
    try:
        raw_appt_id = request.form.get("appointment_id", "").strip()
        if not raw_appt_id:
            flash("Mã lịch hẹn là bắt buộc.", "danger")
            return redirect(url_for("invoices"))
        try:
            appointment_id = int(raw_appt_id)
        except ValueError:
            flash("Mã lịch hẹn không hợp lệ. Vui lòng nhập số nguyên.", "danger")
            return redirect(url_for("invoices"))

        raw_discount = request.form.get("discount", "0").strip() or "0"
        try:
            discount = float(raw_discount)
        except ValueError:
            flash("Số tiền giảm giá không hợp lệ.", "danger")
            return redirect(url_for("invoices"))

        payment_method = request.form.get("payment_method", "Cash").strip()
        payment_status = request.form.get("payment_status", "Paid").strip()

        database.create_invoice(
            appointment_id,
            discount,
            payment_method,
            payment_status,
        )
        flash("Đã tạo hóa đơn.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("invoices"))


@app.route("/admin/invoices/<int:invoice_id>/delete", methods=["POST"])
@admin_required
def admin_invoice_delete(invoice_id):
    try:
        database.delete_invoice(invoice_id)
        flash("Đã xóa hóa đơn.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("invoices"))


@app.route("/admin/invoices/delete", methods=["POST"])
@admin_required
def admin_invoice_delete_form():
    try:
        database.delete_invoice(int(request.form.get("invoice_id", "")))
        flash("Đã xóa hóa đơn.", "success")
    except (TypeError, ValueError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("invoices"))


@app.route("/history")
@login_required
def history():
    q = request.args.get("q", "").strip()
    return render_template("history.html", rows=database.search_history(q), query=q)


@app.route("/ai/recommendation")
@login_required
def ai_recommendation_page():
    return render_template(
        "ai_recommendation.html",
        customers=database.list_customers(),
        services=database.list_services(),
    )


@app.route("/ai/message")
@login_required
def ai_message_page():
    return render_template("ai_message.html", customers=database.list_customers())


@app.route("/ai/summary")
@login_required
def ai_summary_page():
    return render_template("ai_summary.html", customers=database.list_customers())


@app.route("/chat")
@login_required
def chat_page():
    return render_template("chat.html")


@app.route("/admin/ai/history")
@roles_required("admin", "receptionist", "staff")
def admin_ai_history():
    customers = database.list_customers()
    raw_customer_id = request.args.get("customer_id", "").strip()
    customer = None
    chat_history = []
    if raw_customer_id:
        try:
            customer_id = int(raw_customer_id)
        except ValueError:
            flash("Mã khách hàng không hợp lệ.", "danger")
            return redirect(url_for("admin_ai_history"))
        customer = database.get_customer(customer_id)
        if not customer:
            flash("Không tìm thấy khách hàng.", "danger")
            return redirect(url_for("admin_ai_history"))
        chat_history = database.customer_chat_history(customer_id)
    return render_template(
        "admin/ai_history.html",
        customers=customers,
        selected_customer=customer,
        chat_history=chat_history,
    )


@app.route("/api/ai/chat/history")
@roles_required("admin", "receptionist", "staff")
def api_ai_chat_history():
    try:
        customer_id = int(request.args.get("customer_id", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "Mã khách hàng không hợp lệ."}), 400
    if not database.get_customer(customer_id):
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    return jsonify(history=database.customer_chat_history(customer_id))


@app.route("/admin/ai/recommend", methods=["POST"])
@app.route("/api/ai/recommend", methods=["POST"])
@login_required
def api_ai_recommend():
    data = request.get_json(silent=True) or {}
    raw_customer_code = data.get("customer_code")
    customer_code = raw_customer_code.strip().upper() if isinstance(raw_customer_code, str) else ""
    raw_customer_id = data.get("customer_id")
    if raw_customer_id not in (None, ""):
        try:
            customer = database.get_customer(int(raw_customer_id))
        except (TypeError, ValueError):
            return jsonify({"error": "Mã khách hàng không hợp lệ."}), 400
    elif customer_code:
        customer = database.get_customer_by_code(customer_code)
    else:
        return jsonify({"error": "Hãy chọn khách hàng hoặc nhập mã khách hàng."}), 400
    if not customer:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    history = database.customer_history(customer["id"])
    services = database.list_services(active_only=True)
    customer_context = database.customer_recommendation_context(customer["id"])
    return jsonify(ai_service.recommend_service(customer, history, services, customer_context))


@app.route("/api/ai/latest-customer")
@roles_required("admin", "receptionist", "staff")
def api_ai_latest_customer():
    customer = database.latest_booked_customer()
    if not customer:
        return jsonify({"error": "Chưa có lịch đặt nào để chọn khách hàng."}), 404
    return jsonify(
        customer_id=customer["id"],
        customer_code=customer.get("customer_code") or f"KH{customer['id']:03d}",
        full_name=customer["full_name"],
    )



@app.route("/api/ai/message", methods=["POST"])
@login_required
def api_ai_message():
    data = request.get_json(silent=True) or {}
    # Validate customer_id
    try:
        customer_id = int(data.get("customer_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid or missing customer_id"}), 400
    customer = database.get_customer(customer_id)
    if not customer:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    history = database.customer_history(customer_id)
    services = database.list_services(active_only=True)
    return jsonify(ai_service.generate_message(customer, history, services))



@app.route("/api/ai/summary", methods=["POST"])
@login_required
def api_ai_summary():
    data = request.get_json(silent=True) or {}
    # Validate customer_id
    try:
        customer_id = int(data.get("customer_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid or missing customer_id"}), 400
    customer = database.get_customer(customer_id)
    if not customer:
        return jsonify({"error": "Không tìm thấy khách hàng."}), 404
    return jsonify(ai_service.summarize_customer(customer, database.customer_history(customer_id)))



@app.route("/api/ai/chat", methods=["POST"])
@login_required
def api_ai_chat():
    try:
        data = request.get_json(silent=True) or {}
        message = data.get("message")
        if not isinstance(message, str):
            message = ""
        message = message.strip()
        if not message:
            return jsonify({"error": "Vui lòng nhập câu hỏi."}), 400
        if len(message) > 1500:
            return jsonify({"error": "Câu hỏi tối đa 1500 ký tự."}), 400
        customer_id = None
        customer = None
        saved_chat_history = []
        raw_customer_id = data.get("customer_id")
        if raw_customer_id not in (None, ""):
            if session.get("role") not in {"admin", "receptionist", "staff"}:
                return jsonify({"error": "Bạn không có quyền chọn hồ sơ khách hàng."}), 403
            try:
                customer_id = int(raw_customer_id)
            except (TypeError, ValueError):
                return jsonify({"error": "Mã khách hàng không hợp lệ."}), 400
            customer = database.get_customer(customer_id)
            if not customer:
                return jsonify({"error": "Không tìm thấy khách hàng."}), 404
            saved_chat_history = database.customer_chat_history(customer_id, limit=10)
        elif session.get("role") == "customer":
            account = database.get_user(session["user_id"])
            customer = database.get_customer_by_phone(account.get("phone") if account else None)
            if customer:
                customer_id = customer["id"]
                saved_chat_history = database.customer_chat_history(customer_id, limit=10)
        history = []
        raw_history = data.get("history", data.get("chat_history", []))
        if isinstance(raw_history, list):
            for item in raw_history[-8:]:
                if not isinstance(item, dict):
                    continue
                role = item.get("role")
                content = item.get("content")
                if role in {"user", "assistant"} and isinstance(content, str):
                    content = " ".join(content.strip().split())[:1000]
                    if content:
                        history.append({"role": role, "content": content})
        context = {
            "role": session.get("role"),
            "user_id": session.get("user_id"),
            "services": database.list_services(active_only=True),
            "history": history,
            "customer": customer,
            "customer_chat_history": saved_chat_history,
        }
        if session.get("role") in {"admin", "receptionist", "staff"}:
            context["admin_summary"] = database.get_admin_dashboard_summary()
        result = ai_service.chat_salon(message, context)
        database.save_ai_chat(session["user_id"], message, result.get("reply", ""), result.get("mode", "ai"))
        database.save_customer_chat(
            customer_id, session["user_id"], message, result.get("reply", "")
        )
        return jsonify(result)
    except Exception as exc:
        app.logger.exception("AI chat error")
        return jsonify({"error": "Máy chủ AI gặp lỗi."}), 500


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="Không tìm thấy trang."), 404


@app.errorhandler(500)
def server_error(error):
    app.logger.exception("Unhandled server error: %s", error)
    return render_template("error.html", code=500, message="Có lỗi xảy ra trên máy chủ."), 500


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
