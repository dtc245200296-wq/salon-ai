"""Seed demo accounts, services, customers, stylists, and appointments."""

import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path


DB_PATH = Path(__file__).resolve().with_name("salon_system.db")


def generate_password_hash(password):
    salt = secrets.token_urlsafe(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=32768,
        r=8,
        p=1,
        dklen=64,
        maxmem=64 * 1024 * 1024,
    ).hex()
    return f"scrypt:32768:8:1${salt}${digest}"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            role TEXT NOT NULL DEFAULT 'customer',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT, gender TEXT, birthday TEXT, note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS barbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL, phone TEXT, specialty TEXT, experience TEXT,
            status TEXT DEFAULT 'active', created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, category TEXT, description TEXT,
            duration_minutes INTEGER NOT NULL DEFAULT 30,
            price REAL NOT NULL DEFAULT 0, status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL, barber_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT,
            status TEXT NOT NULL DEFAULT 'Pending', note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            FOREIGN KEY(barber_id) REFERENCES barbers(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS appointment_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER NOT NULL, service_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1, price REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE RESTRICT
        );
        """
    )
    user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "phone" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    if "email" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "role" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'customer'")
    barber_columns = {row["name"] for row in conn.execute("PRAGMA table_info(barbers)")}
    if "user_id" not in barber_columns:
        conn.execute("ALTER TABLE barbers ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_barbers_user_id "
        "ON barbers(user_id) WHERE user_id IS NOT NULL"
    )
    return conn


def seed():
    conn = get_connection()
    try:
        accounts = [
            ("admin", "Quản trị viên", None, "admin", "admin@hairstudio.vn"),
            ("le_tan", "Lê Tân", None, "staff", None),
            ("tho01", "Nguyễn Văn b", "0901000001", "stylist", None),
            ("tho02", "Trần Thị E", "0901000002", "stylist", None),
            ("khach01", "Lê Văn C", "0912345678", "customer", None),
            ("khach02", "Phạm Thị Hoàng", "0987654321", "customer", None),
        ]
        password_hash = generate_password_hash("123456")
        for username, full_name, phone, role, email in accounts:
            conn.execute(
                """INSERT INTO users(username, password_hash, full_name, phone, role, email)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(username) DO UPDATE SET
                     password_hash = excluded.password_hash,
                     full_name = excluded.full_name,
                     phone = excluded.phone,
                     role = excluded.role,
                     email = COALESCE(excluded.email, users.email)""",
                (username, password_hash, full_name, phone, role, email),
            )

        stylist_accounts = [
            ("tho01", "Nguyễn Văn b", "0901000001", "Cắt tạo kiểu", "6 năm"),
            ("tho02", "Trần Thị Hair", "0901000002", "Nhuộm và tạo kiểu", "5 năm"),
        ]
        stylist_ids = {}
        for username, full_name, phone, specialty, experience in stylist_accounts:
            user_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()[0]
            barber = conn.execute(
                "SELECT id FROM barbers WHERE user_id = ?", (user_id,)
            ).fetchone()
            if barber:
                barber_id = barber[0]
                conn.execute(
                    """UPDATE barbers SET full_name = ?, phone = ?, specialty = ?,
                       experience = ?, status = 'active' WHERE id = ?""",
                    (full_name, phone, specialty, experience, barber_id),
                )
            else:
                conn.execute(
                    """INSERT INTO barbers(full_name, phone, specialty, experience, status, user_id)
                       VALUES (?, ?, ?, ?, 'active', ?)""",
                    (full_name, phone, specialty, experience, user_id),
                )
                barber_id = conn.execute(
                    "SELECT id FROM barbers WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
            stylist_ids[username] = barber_id

        customer_accounts = [
            ("khach01", "Lê Văn Khách", "0912345678"),
            ("khach02", "Phạm Thị Hoàng", "0987654321"),
        ]
        customer_ids = {}
        for username, full_name, phone in customer_accounts:
            customer = conn.execute(
                "SELECT id FROM customers WHERE phone = ?", (phone,)
            ).fetchone()
            if customer:
                customer_id = customer[0]
                conn.execute(
                    "UPDATE customers SET full_name = ? WHERE id = ?",
                    (full_name, customer_id),
                )
            else:
                conn.execute(
                    "INSERT INTO customers(full_name, phone) VALUES (?, ?)",
                    (full_name, phone),
                )
                customer_id = conn.execute(
                    "SELECT id FROM customers WHERE phone = ?", (phone,)
                ).fetchone()[0]
            customer_ids[username] = customer_id

        services = [
            ("Cắt tóc Nam", "Haircut", "Cắt tóc nam cơ bản", 30, 100000),
            ("Cắt & Tạo kiểu Nữ", "Haircut", "Cắt và tạo kiểu nữ", 45, 200000),
            ("Nhuộm tóc Thời trang", "Color", "Nhuộm tóc theo màu yêu cầu", 90, 500000),
            ("Uốn tóc Restyle", "Styling", "Uốn tóc tạo kiểu Restyle", 120, 600000),
            ("Gội đầu Dưỡng sinh", "Care", "Gội đầu thư giãn dưỡng sinh", 40, 150000),
        ]
        service_ids = {}
        for name, category, description, duration, price in services:
            row = conn.execute(
                "SELECT id FROM services WHERE name = ? ORDER BY id LIMIT 1", (name,)
            ).fetchone()
            if row:
                service_id = row[0]
                conn.execute(
                    """UPDATE services SET category = ?, description = ?,
                       duration_minutes = ?, price = ?, status = 'active' WHERE id = ?""",
                    (category, description, duration, price, service_id),
                )
            else:
                conn.execute(
                    """INSERT INTO services(name, category, description, duration_minutes, price)
                       VALUES (?, ?, ?, ?, ?)""",
                    (name, category, description, duration, price),
                )
                service_id = conn.execute(
                    "SELECT id FROM services WHERE name = ? ORDER BY id DESC LIMIT 1", (name,)
                ).fetchone()[0]
            service_ids[name] = service_id

        sample_appointments = [
            ("seed_data sample 1", "khach01", "tho01", "2026-10-25", "09:00", "09:30", "Pending", "Cắt tóc Nam"),
            ("seed_data sample 2", "khach01", "tho02", "2026-10-26", "11:00", "13:00", "Pending", "Uốn tóc Restyle"),
            ("seed_data sample 3", "khach01", "tho01", "2026-10-27", "10:00", "12:30", "Pending", "Nhuộm tóc"),
            ("seed_data sample 4", "khach01", "tho02", "2026-10-24", "13:00", "13:40", "Confirmed", "Gội đầu Dưỡng sinh"),
            ("seed_data sample 5", "khach01", "tho01", "2026-10-22", "15:00", "15:45", "Cancelled", "Cắt & Tạo kiểu Nữ"),
            ("seed_data sample 6", "khach01", "tho02", "2026-10-20", "14:00", "15:30", "Completed", "Phục hồi tóc"),
            ("seed_data sample 7", "khach01", "tho01", "2026-10-18", "09:30", "10:30", "Completed", "Cắt layer"),
        ]
        for marker, customer_key, stylist_key, appt_date, start_time, end_time, status, service_name in sample_appointments:
            existing = conn.execute(
                "SELECT id FROM appointments WHERE note = ?", (marker,)
            ).fetchone()
            if existing:
                appointment_id = existing[0]
                conn.execute(
                    """UPDATE appointments SET customer_id = ?, barber_id = ?, appointment_date = ?,
                       start_time = ?, end_time = ?, status = ? WHERE id = ?""",
                    (customer_ids[customer_key], stylist_ids[stylist_key], appt_date,
                     start_time, end_time, status, appointment_id),
                )
                conn.execute(
                    "DELETE FROM appointment_services WHERE appointment_id = ?",
                    (appointment_id,),
                )
            else:
                cursor = conn.execute(
                    """INSERT INTO appointments(
                       customer_id, barber_id, appointment_date, start_time, end_time, status, note
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (customer_ids[customer_key], stylist_ids[stylist_key], appt_date,
                     start_time, end_time, status, marker),
                )
                appointment_id = cursor.lastrowid
            price = next(item[4] for item in services if item[0] == service_name)
            conn.execute(
                """INSERT INTO appointment_services(appointment_id, service_id, quantity, price)
                   VALUES (?, ?, 1, ?)""",
                (appointment_id, service_ids[service_name], price),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    seed()
    print("Đã thêm/cập nhật dữ liệu mẫu trong salon_system.db.")
