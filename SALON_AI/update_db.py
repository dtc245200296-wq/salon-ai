import hashlib
import secrets
import sqlite3

try:
    from werkzeug.security import generate_password_hash
except ModuleNotFoundError:
    def generate_password_hash(password):
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
        return f"pbkdf2:sha256:600000${salt}${digest.hex()}"


DB_PATH = "salon_system.db"
# Canonical database values; the UI maps these case-insensitively to Vietnamese labels.
STATUS = {"pending": "Pending", "confirmed": "Confirmed", "completed": "Completed", "cancelled": "Cancelled"}
CUSTOMERS = [
    (1, "khach01", "Nguyễn Chí Duy", "0100000000", "chiduy01@gmail.com", "Nam"),
    (2, "khach02", "Trần Thị Mai", "0200000000", "thimai02@gmail.com", "Nữ"),
    (3, "khach03", "Lê Hoàng Anh", "0300000000", "hoanganh03@gmail.com", "Nam"),
    (4, "khach04", "Phạm Phương Thảo", "0400000000", "phuongthao04@gmail.com", "Nữ"),
    (5, "khach05", "Đặng Minh Tiến", "0500000000", "minhtien05@gmail.com", "Nam"),
]


SERVICE_DEFAULTS = {
    "Cắt tóc nam Stylist": ("haircut_men_modern", 45, 150000),
    "Combo Cắt Gội & Nhuộm Nam": ("hair_men_combo", 120, 450000),
    "Cắt tóc Nam Basic": ("haircut_men_classic", 30, 100000),
    "Uốn tóc Restyle & Phục hồi": ("hair_perm_repair_combo", 150, 600000),
    "Nhuộm màu thời trang & Phục hồi Keratin": ("hair_color_repair_combo", 90, 200000),
}


def service_id(conn, name):
    row = conn.execute("SELECT id FROM services WHERE name = ? ORDER BY id LIMIT 1", (name,)).fetchone()
    if not row:
        category, duration, price = SERVICE_DEFAULTS[name]
        row_id = conn.execute(
            """INSERT INTO services(name, category, description, duration_minutes, price, status)
               VALUES (?, ?, ?, ?, ?, 'active')""",
            (name, category, f"Dịch vụ mẫu {name}", duration, price),
        ).lastrowid
        return row_id
    return row[0]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("BEGIN")
        # Clear dependent records before removing customer/booking data.
        conn.execute("DELETE FROM invoice_items")
        conn.execute("DELETE FROM invoices")
        conn.execute("DELETE FROM appointment_services")
        conn.execute("DELETE FROM customer_history")
        conn.execute("DELETE FROM appointments")
        conn.execute("DELETE FROM customers")
        conn.execute("DELETE FROM users WHERE role = 'customer'")
        conn.execute("UPDATE sqlite_sequence SET seq = 0 WHERE name IN ('customers', 'appointments', 'invoices')")

        # Normalize all staff contact details to a dedicated, non-customer range.
        staff = [
            ("admin", "Trần Quang Trường", "0901111111", "admin@hairstudio.com", "admin"),
            ("letan01", "Lê Tân 01", "0111111111", "letan01@gmail.com", "receptionist"),
            ("letan02", "Lê Tân 02", "0111122222", "letan02@gmail.com", "receptionist"),
            ("tho01", "Trần Quốc Tuấn", "0111133333", "tuan01@gmail.com", "stylist"),
            ("tho02", "Đỗ Hoàng Yến", "0111144444", "hoangyen02@gmail.com", "stylist"),
        ]
        for username, full_name, phone, email, role in staff:
            conn.execute(
                "UPDATE users SET full_name=?, phone=?, email=?, role=? WHERE username=?",
                (full_name, phone, email, role, username),
            )
            conn.execute(
                "UPDATE barbers SET full_name=?, phone=? WHERE user_id=(SELECT id FROM users WHERE username=?)",
                (full_name, phone, username),
            )

        password_hash = generate_password_hash("123456")
        for customer_id, username, full_name, phone, email, gender in CUSTOMERS:
            conn.execute(
                """INSERT INTO customers(id, full_name, phone, customer_code, email, gender, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, '2026-10-29 09:00:00')""",
                (customer_id, full_name, phone, f"KH{customer_id:03d}", email, gender),
            )
            conn.execute(
                """INSERT INTO users(username, password_hash, full_name, phone, email, role, customer_code, is_active)
                   VALUES (?, ?, ?, ?, ?, 'customer', ?, 1)""",
                (username, password_hash, full_name, phone, email, f"KH{customer_id:03d}"),
            )
        conn.execute("UPDATE sqlite_sequence SET seq = 5 WHERE name = 'customers'")

        # Keep the login accounts and link their barber profiles to the seeded appointments.
        barber_ids = {}
        for username, display_name in (("tho01", "Trần Quốc Tuấn"), ("tho02", "Đỗ Hoàng Yến")):
            user = conn.execute("SELECT id FROM users WHERE username = ? AND role = 'stylist'", (username,)).fetchone()
            if not user:
                raise RuntimeError(f"Thiếu tài khoản Stylist hệ thống: {username}")
            barber = conn.execute("SELECT id FROM barbers WHERE user_id = ? LIMIT 1", (user[0],)).fetchone()
            if not barber:
                raise RuntimeError(f"Chưa liên kết hồ sơ barber cho {username}")
            barber_ids[username] = barber[0]
            conn.execute("UPDATE users SET full_name = ? WHERE id = ?", (display_name, user[0]))
            conn.execute("UPDATE barbers SET full_name = ? WHERE id = ?", (display_name, barber[0]))

        samples = [
            (1, barber_ids["tho01"], "09:00", "09:45", STATUS["completed"], "Cắt tóc nam Stylist", 150000),
            (2, barber_ids["tho02"], "10:30", "13:00", STATUS["confirmed"], "Uốn tóc Restyle & Phục hồi", 600000),
            (3, barber_ids["tho01"], "14:00", "16:00", STATUS["pending"], "Combo Cắt Gội & Nhuộm Nam", 450000),
            (4, barber_ids["tho02"], "15:30", "17:00", STATUS["completed"], "Nhuộm màu thời trang & Phục hồi Keratin", 200000),
            (5, barber_ids["tho01"], "17:00", "17:30", STATUS["cancelled"], "Cắt tóc Nam Basic", 100000),
        ]
        appointment_ids = []
        for customer_id, barber_id, start, end, status, service_name, expected_total in samples:
            appointment_id = conn.execute(
                """INSERT INTO appointments(customer_id, barber_id, appointment_date, start_time, end_time,
                   status, payment_method, payment_status, note)
                   VALUES (?, ?, '2026-10-29', ?, ?, ?, 'Salon', 'Unpaid', 'Dữ liệu mẫu dashboard')""",
                (customer_id, barber_id, start, end, status),
            ).lastrowid
            appointment_ids.append(appointment_id)
            selected = [service_id(conn, service_name)]
            for sid in selected:
                price = conn.execute("SELECT price FROM services WHERE id = ?", (sid,)).fetchone()[0]
                conn.execute(
                    "INSERT INTO appointment_services(appointment_id, service_id, quantity, price) VALUES (?, ?, 1, ?)",
                    (appointment_id, sid, price),
                )

        # Two completed invoices: cash for appointment 1 and bank transfer for appointment 4.
        invoice_data = [(appointment_ids[0], 150000, 0, 150000, "Cash"),
                        (appointment_ids[3], 200000, 20000, 180000, "Banking")]
        for appointment_id, subtotal, discount, total, method in invoice_data:
            invoice_id = conn.execute(
                """INSERT INTO invoices(appointment_id, customer_id, subtotal, discount, total, payment_method, payment_status)
                   SELECT ?, customer_id, ?, ?, ?, ?, 'Paid' FROM appointments WHERE id = ?""",
                (appointment_id, subtotal, discount, total, method, appointment_id),
            ).lastrowid
            rows = conn.execute("SELECT service_id, quantity, price FROM appointment_services WHERE appointment_id = ?", (appointment_id,)).fetchall()
            for sid, quantity, price in rows:
                conn.execute("INSERT INTO invoice_items(invoice_id, service_id, quantity, unit_price, amount) VALUES (?, ?, ?, ?, ?)", (invoice_id, sid, quantity, price, price * quantity))

        conn.execute("UPDATE sqlite_sequence SET seq = 5 WHERE name = 'appointments'")
        conn.execute("UPDATE sqlite_sequence SET seq = 2 WHERE name = 'invoices'")
        conn.commit()
        print("Da reset CSDL va nap 5 khach hang, 5 lich hen, 2 hoa don mau.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
