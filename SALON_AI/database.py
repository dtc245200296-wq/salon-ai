import os
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
import math
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "salon_system.db"


def get_current_db_path() -> Path:
    """Return the active SQLite database path, honoring SALON_DATABASE_PATH if set."""
    custom_path = os.getenv("SALON_DATABASE_PATH")
    if custom_path:
        return Path(custom_path)
    return DEFAULT_DB_PATH


# Module-level variable kept for backward compatibility
DB_PATH = get_current_db_path()


def set_db_path(path):
    """Explicitly switch database path (used by test fixtures)."""
    global DB_PATH
    DB_PATH = Path(path)
    os.environ["SALON_DATABASE_PATH"] = str(DB_PATH)


def get_db_connection():
    """Create a SQLite connection with foreign-key checks enabled."""
    current_path = get_current_db_path()

    # CRITICAL TEST SAFETY CHECK:
    # If test mode is active, reject any connection resolving to default production db.
    if os.getenv("SALON_TESTING") == "1":
        if current_path.resolve() == DEFAULT_DB_PATH.resolve():
            raise RuntimeError(
                f"SAFETY VIOLATION: Test suite attempted to connect to real database at {DEFAULT_DB_PATH}!"
            )

    conn = sqlite3.connect(current_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _upsert_default_accounts(conn):
    password_hash = generate_password_hash("123456")
    accounts = [
        ("khach01", "Nguyễn Chí Duy", "customer", "0100000000", "chiduy01@gmail.com"),
        ("tho01", "Trần Quốc Tuấn", "stylist", "0200000000", "tuan01@gmail.com"),
        ("tho02", "Đỗ Hoàng Yến", "stylist", "0300000000", "hoangyen02@gmail.com"),
        ("letan01", "Lễ Tân", "receptionist", "0377463225", "letan@gmail.com"),
        ("admin", "Trần Quang Trường", "admin", "0377463226", "admin.hairstudio@gmail.com"),
    ]
    conn.executemany(
        """INSERT INTO users(username, password_hash, full_name, role, phone, email)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(username) DO UPDATE SET
               password_hash = excluded.password_hash,
               full_name = excluded.full_name,
               role = excluded.role,
               phone = COALESCE(excluded.phone, users.phone),
               email = COALESCE(excluded.email, users.email)""",
        [
            (username, password_hash, full_name, role, phone, email)
            for username, full_name, role, phone, email in accounts
        ],
    )


def _ensure_default_stylist_profiles(conn):
    stylist_profiles = [
        ("tho01", "Trần Quốc Tuấn", "0901000001", "Cắt tạo kiểu", "5 năm", 5,
         "Uốn Textured Perm, Nhuộm Khói / Balayage, Sidepart Layer Hàn Quốc, Massage Cổ Vai Gáy",
         "Tập trung vào tạo kiểu nam hiện đại, kỹ thuật uốn nhuộm và chăm sóc thư giãn.", "male", 4.9, 128, 1450,
         "🏆 Top 5 Stylist Xuất Sắc HairStudio 2025 · 📜 Chứng chỉ Vidal Sassoon Academy",
         "Luôn chú trọng form dáng tự nhiên và sức khỏe của tóc. Lắng nghe mong muốn của khách hàng để tạo nên phong cách chuẩn gu nhất."),
        ("tho02", "Đỗ Hoàng Yến", "0901000002", "Nhuộm và tạo kiểu", "7 năm", 7,
         "Uốn sóng nữ, Nhuộm Balayage, Phục hồi tóc, Cắt Layer nữ",
         "Chuyên uốn nhuộm nữ, phục hồi tóc hư tổn và tạo kiểu Layer theo khuôn mặt.", "female", 5.0, 96, 1180,
         "🏆 Stylist được khách hàng yêu thích 2025 · 📜 Chứng chỉ phục hồi tóc chuyên sâu",
         "Mỗi mái tóc đều có cá tính riêng. Tôi ưu tiên sức khỏe sợi tóc và lựa chọn kiểu dáng giúp khách tự tin, dễ chăm sóc mỗi ngày."),
    ]
    for username, full_name, phone, specialty, experience, years, specialties, bio, gender_focus, rating, review_count, total_customers, awards, philosophy in stylist_profiles:
        user = conn.execute(
            "SELECT id FROM users WHERE username = ? AND role = 'stylist'",
            (username,),
        ).fetchone()
        if not user:
            continue

        barber = conn.execute(
            "SELECT id FROM barbers WHERE user_id = ? LIMIT 1", (user["id"],)
        ).fetchone()
        if not barber:
            barber = conn.execute(
                """SELECT id FROM barbers
                   WHERE user_id IS NULL AND phone = ? ORDER BY id LIMIT 1""",
                (phone,),
            ).fetchone()

        if barber:
            conn.execute(
                """UPDATE barbers SET user_id = ?, full_name = ?, phone = ?,
                       specialty = ?, experience = ?, experience_years = COALESCE(NULLIF(experience_years, 0), ?),
                       specialties = CASE WHEN specialties IS NULL OR specialties = ''
                                                OR specialties IN ('Uốn tóc nam, Nhuộm tóc nam, Massage dưỡng sinh', 'Phục hồi tóc, Cắt Layer nữ')
                                          THEN ? ELSE specialties END,
                       bio = COALESCE(NULLIF(bio, ''), ?),
                       gender_focus = COALESCE(NULLIF(gender_focus, ''), ?),
                       rating = COALESCE(NULLIF(rating, 0), ?),
                       review_count = COALESCE(NULLIF(review_count, 0), ?),
                       total_customers = COALESCE(NULLIF(total_customers, 0), ?),
                       awards = COALESCE(NULLIF(awards, ''), ?),
                       philosophy = COALESCE(NULLIF(philosophy, ''), ?), status = 'active'
                   WHERE id = ?""",
                (user["id"], full_name, phone, specialty, experience, years, specialties, bio, gender_focus,
                 rating, review_count, total_customers, awards, philosophy, barber["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO barbers(
                       user_id, full_name, phone, specialty, experience, experience_years,
                       specialties, bio, gender_focus, rating, review_count, total_customers,
                       awards, philosophy, status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                (user["id"], full_name, phone, specialty, experience, years, specialties, bio,
                 gender_focus, rating, review_count, total_customers, awards, philosophy),
            )


STANDARD_SERVICES = [
    ("Gội dưỡng tóc", "shampoo_natural", "Dầu gội bồ kết thiên nhiên.", 45, 150000,
     "Dầu gội bồ kết, Tinh dầu bưởi organic", "Tóc tự nhiên",
     "Không yêu cầu độ dài tối thiểu", "Giữ nguyên độ dài tóc",
     "Gội xả → Massage da đầu → Sấy khô"),
    ("Gội đầu Dưỡng sinh", "shampoo_herbal", "Gội đầu thư giãn bằng thảo dược.", 40, 150000,
     "Thảo mộc Đông y, Bồ kết organic", "Phù hợp thư giãn",
     "Không yêu cầu độ dài tối thiểu", "Giữ nguyên độ dài tóc",
     "Khai thông huyệt đạo → Gội thảo dược → Massage cổ vai gáy"),
    ("Cắt tóc Nam", "haircut_men_classic", "Cắt tóc nam và hoàn thiện tạo kiểu.", 30, 100000,
     "Sáp vuốt tóc cao cấp", "Undercut, Side Part, Ivy League",
     "Tóc tối thiểu khoảng 5 cm", "Theo kiểu đã chọn; thường ngắn sát gáy 1–2 cm",
     "Tư vấn dáng mặt → Cắt tỉa → Gội xả → Vuốt sáp"),
    ("Cắt tóc nam (Stylist)", "haircut_men_modern", "Cắt tóc nam theo xu hướng hiện đại.", 45, 120000,
     "Sáp & Spray Komi", "Two-Block, Mullet hiện đại",
     "Tóc tối thiểu 5–7 cm", "Theo kiểu Two-Block hoặc Mullet đã thống nhất",
     "Cắt sấy tạo phồng → Vuốt kiểu"),
    ("Cắt & Tạo kiểu Nữ", "haircut_women", "Cắt và tạo kiểu phù hợp khuôn mặt.", 45, 200000,
     "Dầu dưỡng Moroccanoil", "Bob, Pixie, Layer nữ",
     "Tóc tối thiểu khoảng 7 cm", "Theo dáng Bob, Pixie hoặc Layer đã thống nhất",
     "Tạo phom → Cắt tầng → Sấy kiểu"),
    ("Cắt layer", "haircut_layer", "Tạo kiểu layer theo khuôn mặt.", 60, 180000,
     "Serum dưỡng phồng", "Layer tầng cao, Layer bay Hàn Quốc",
     "Tóc dài tối thiểu khoảng 10 cm", "Ngang vai tỉa tầng hoặc theo độ dài khách chọn",
     "Cắt tỉa từng lớp → Sấy bay"),
    ("Nhuộm tóc", "hair_color_loreal", "Nhuộm tóc bằng màu chuyên nghiệp.", 150, 650000,
     "Thuốc nhuộm L'Oreal Paris", "Nhuộm tone trầm / sáng",
     "Không yêu cầu độ dài tối thiểu", "Giữ nguyên độ dài tóc",
     "Tư vấn màu → Phủ thuốc → Xả xịt dưỡng"),
    ("Nhuộm tóc Thời trang", "hair_color_fashion", "Nhuộm màu thời trang cá tính.", 90, 600000,
     "Tẩy & Thuốc nhuộm Olaplex", "Balayage, Ombre, Pastel",
     "Khuyến nghị tóc dài trên 10 cm", "Giữ nguyên độ dài tóc",
     "Tẩy nền → Nhuộm màu → Hấp khóa màu"),
    ("Uốn tóc", "hair_perm", "Uốn lạnh hoặc nóng tạo kiểu.", 180, 850000,
     "Thuốc uốn lạnh/nóng Goldwell", "Uốn xoăn sóng nước, Uốn C-Fly",
     "Tóc dài tối thiểu khoảng 10 cm", "Giữ nguyên độ dài; nếp uốn có thể khiến tóc trông ngắn hơn",
     "Mềm hóa → Quấn trục → Định hình"),
    ("Phục hồi tóc", "hair_repair", "Chăm sóc và phục hồi tóc hư tổn.", 90, 450000,
     "Keratin & Collagen tươi", "Phục hồi hư tổn",
     "Không yêu cầu độ dài tối thiểu", "Giữ nguyên độ dài tóc",
     "Gội sạch → Hấp nhiệt Keratin → Phủ lụa"),
]


def _ensure_standard_services(conn):
    if not conn.execute("SELECT 1 FROM services LIMIT 1").fetchone():
        conn.execute("DELETE FROM services")
        conn.executemany(
            """INSERT INTO services(
                   name, category, description, duration_minutes, price,
                   products, styles, min_length, after_length, steps, status
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            STANDARD_SERVICES,
        )
        return

    for service in STANDARD_SERVICES:
        existing = conn.execute(
            "SELECT id FROM services WHERE name = ? ORDER BY id LIMIT 1",
            (service[0],),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE services SET category = ?, description = ?, duration_minutes = ?,
                       price = ?, products = ?, styles = ?, min_length = ?, after_length = ?,
                       steps = ?, status = 'active'
                   WHERE id = ?""",
                (*service[1:], existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO services(
                       name, category, description, duration_minutes, price,
                       products, styles, min_length, after_length, steps, status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                service,
            )


def update_all_services_rich_info(conn):
    """Populate the extended product, style and compliance details for every service."""
    rich_info = {
        "Nhuộm tóc Thời trang": ("Balayage / Highlight", "Tóc lỡ hoặc tóc dài", "L'Oréal", "Pháp 🇫🇷", "11824/20/CBMP-QLD"),
        "Nhuộm tóc": ("Phủ bạc / Đều màu", "Mọi độ dài", "Goldwell", "Đức 🇩🇪", "08912/19/CBMP-QLD"),
        "Uốn tóc": ("Xoăn sóng / Layer", "Tóc từ ngang vai trở lên", "Wella", "Mỹ 🇺🇸", "14201/21/CBMP-QLD"),
        "Uốn tóc Restyle": ("Restyle phồng chân", "Tóc lỡ hoặc tóc dài", "Schwarzkopf", "Đức 🇩🇪", "05512/20/CBMP-QLD"),
        "Phục hồi tóc": ("Phục hồi Olaplex No.1 & No.2 · Giảm xơ 95%", "Mọi độ dài", "Olaplex No.1 & No.2", "Mỹ 🇺🇸", "22091/22/CBMP-QLD"),
        "Cắt layer": ("Layer bay Hàn Quốc", "Tóc từ 10 cm trở lên", "Xịt dưỡng Davines", "Ý 🇮🇹", "10023/18/CBMP-QLD"),
        "Cắt tóc Nam": ("Undercut Fade / Sidepart", "Tối thiểu 5–7 cm", "Sáp Gatsby", "Nhật 🇯🇵", "33012/21/CBMP-QLD"),
        "Cắt tóc nam (Stylist)": ("Textured / Mullet", "Tối thiểu 7 cm", "Sáp Dapper Dan", "Anh 🇬🇧", "19082/22/CBMP-QLD"),
        "Cắt & Tạo kiểu Nữ": ("Sấy bồng bềnh đi tiệc", "Tóc từ ngang vai", "Tinh dầu Moroccanoil", "Israel 🇮🇱", "04512/19/CBMP-QLD"),
        "Gội đầu Dưỡng sinh": ("Gội bồ kết / hà thủ ô + Ấn huyệt Cổ Vai Gáy", "Mọi độ dài", "Dược liệu bồ kết, hà thủ ô", "Việt Nam 🇻🇳", "Đạt chuẩn OCOP 5 sao"),
        "Gội dưỡng tóc": ("Gội xả phục hồi ẩm Cocoon", "Mọi độ dài", "Cocoon", "Việt Nam 🇻🇳", "12044/21/CBMP-QLD"),
    }
    conn.executemany(
        """UPDATE services
           SET style_type = ?, suitable_length = ?, chemical_brands = ?,
               chemical_origin = ?, inspection_cert = ?
           WHERE name = ?""",
        [(style, length, brands, origin, cert, name)
         for name, (style, length, brands, origin, cert) in rich_info.items()],
    )


def _ensure_sample_customer_appointments(conn):
    # Keep an explicitly prepared dataset (for example from update_db.py) intact.
    if conn.execute("SELECT 1 FROM appointments LIMIT 1").fetchone():
        return
    customer_user = conn.execute(
        "SELECT full_name, phone FROM users WHERE username = 'khach01'"
    ).fetchone()
    if not customer_user or not customer_user["phone"]:
        return

    customer = conn.execute(
        "SELECT id FROM customers WHERE phone = ?", (customer_user["phone"],)
    ).fetchone()
    if customer:
        customer_id = customer["id"]
    else:
        customer_id = conn.execute(
            "INSERT INTO customers(full_name, phone) VALUES (?, ?)",
            (customer_user["full_name"], customer_user["phone"]),
        ).lastrowid

    restyle = conn.execute(
        "SELECT id FROM services WHERE name = 'Uốn tóc Restyle' ORDER BY id LIMIT 1"
    ).fetchone()
    if restyle:
        restyle_service_id = restyle["id"]
        conn.execute(
            """UPDATE services SET category = ?, description = ?, duration_minutes = ?,
                   price = ?, products = ?, styles = ?, min_length = ?, after_length = ?,
                   steps = ?, status = 'active'
               WHERE id = ?""",
            ("hair_perm", "Uốn tóc Restyle.", 120, 600000,
             "Thuốc uốn lạnh/nóng Goldwell", "Uốn Restyle",
             "Tóc dài tối thiểu khoảng 10 cm", "Giữ nguyên độ dài; nếp uốn có thể khiến tóc trông ngắn hơn",
             "Khảo sát chất tóc → Quấn trục → Định hình", restyle_service_id),
        )
    else:
        restyle_service_id = conn.execute(
            """INSERT INTO services(
                   name, category, description, duration_minutes, price,
                   products, styles, min_length, after_length, steps, status
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            ("Uốn tóc Restyle", "hair_perm", "Uốn tóc Restyle.", 120, 600000,
             "Thuốc uốn lạnh/nóng Goldwell", "Uốn Restyle",
             "Tóc dài tối thiểu khoảng 10 cm", "Giữ nguyên độ dài; nếp uốn có thể khiến tóc trông ngắn hơn",
             "Khảo sát chất tóc → Quấn trục → Định hình"),
        ).lastrowid

    sample_specs = [
        ("sample-1", "Cắt tóc Nam", "tho01", "2026-10-25", "09:00", "Pending", "Unpaid", "Salon"),
        ("sample-2", "Uốn tóc Restyle", "tho02", "2026-10-26", "11:00", "Pending", "Unpaid", "Salon"),
        ("sample-3", "Nhuộm tóc", "tho01", "2026-10-27", "10:00", "Pending", "Pending Verification", "VietQR"),
        ("sample-4", "Gội đầu Dưỡng sinh", "tho02", "2026-10-24", "13:00", "Confirmed", "Paid Online", "VietQR"),
        ("sample-5", "Cắt layer", "tho01", "2026-10-18", "09:30", "Completed", "Paid Online", "VietQR"),
        ("sample-6", "Phục hồi tóc", "tho02", "2026-10-20", "14:00", "Completed", "Paid Online", "VietQR"),
        ("sample-7", "Cắt & Tạo kiểu Nữ", "tho01", "2026-10-22", "15:00", "Cancelled", "Unpaid", "Salon"),
    ]
    for marker, service_name, stylist_username, appointment_date, start_time, status, payment_status, method in sample_specs:
        note = f"seed_data customer-history {marker}"
        existing_appointment = conn.execute(
            "SELECT id FROM appointments WHERE note = ? LIMIT 1", (note,)
        ).fetchone()

        if service_name == "Uốn tóc Restyle":
            service = conn.execute(
                "SELECT id, duration_minutes, price FROM services WHERE id = ?",
                (restyle_service_id,),
            ).fetchone()
        else:
            service = conn.execute(
                "SELECT id, duration_minutes, price FROM services WHERE name = ? ORDER BY id LIMIT 1",
                (service_name,),
            ).fetchone()
        stylist = conn.execute(
            """SELECT id FROM barbers WHERE user_id =
                   (SELECT id FROM users WHERE username = ?) LIMIT 1""",
            (stylist_username,),
        ).fetchone()
        if not service or not stylist:
            continue

        appointment_day = datetime.strptime(appointment_date, "%Y-%m-%d").date()
        start_dt = datetime.strptime(
            f"{appointment_day.isoformat()} {start_time}", "%Y-%m-%d %H:%M"
        )
        end_time = (start_dt + timedelta(minutes=int(service["duration_minutes"] or 30))).strftime("%H:%M")
        appointment_values = (
            customer_id, stylist["id"], appointment_day.isoformat(), start_time,
            end_time, status, note, method, payment_status,
        )
        if existing_appointment:
            appointment_id = existing_appointment["id"]
            conn.execute(
                """UPDATE appointments SET customer_id = ?, barber_id = ?, appointment_date = ?,
                       start_time = ?, end_time = ?, status = ?, note = ?, payment_method = ?,
                       payment_status = ?, status_before_cancel_request = NULL
                   WHERE id = ?""",
                (*appointment_values, appointment_id),
            )
        else:
            appointment_id = conn.execute(
                """INSERT INTO appointments(
                       customer_id, barber_id, appointment_date, start_time, end_time,
                       status, note, payment_method, payment_status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                appointment_values,
            ).lastrowid

        service_link = conn.execute(
            "SELECT id FROM appointment_services WHERE appointment_id = ? LIMIT 1",
            (appointment_id,),
        ).fetchone()
        if service_link:
            conn.execute(
                """UPDATE appointment_services SET service_id = ?, quantity = 1, price = ?
                   WHERE id = ?""",
                (service["id"], service["price"], service_link["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO appointment_services(appointment_id, service_id, quantity, price)
                   VALUES (?, ?, 1, ?)""",
                (appointment_id, service["id"], service["price"]),
            )


def _backfill_customer_codes(conn):
    # Keep account codes tied to the immutable users.id so registration and
    # profile views always agree, even when the CRM customer row predates it.
    conn.execute(
        """UPDATE customers
           SET customer_code = 'KH' || printf('%03d', id)"""
    )
    conn.execute(
        """UPDATE users
           SET customer_code = 'KH' || printf('%03d', users.id)
           WHERE role = 'customer'"""
    )


def init_db():
    """Create tables and seed demo data when the database is empty."""
    conn = get_db_connection()
    try:
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
                customer_code TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                customer_code TEXT UNIQUE,
                email TEXT,
                gender TEXT,
                birthday TEXT,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS barbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                phone TEXT,
                specialty TEXT,
                experience TEXT,
                experience_years INTEGER NOT NULL DEFAULT 0,
                specialties TEXT,
                bio TEXT,
                gender_focus TEXT,
                rating REAL NOT NULL DEFAULT 5.0,
                review_count INTEGER NOT NULL DEFAULT 0,
                total_customers INTEGER NOT NULL DEFAULT 0,
                awards TEXT,
                philosophy TEXT,
                base_salary REAL NOT NULL DEFAULT 5000000,
                commission_rate REAL NOT NULL DEFAULT 15,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                description TEXT,
                duration_minutes INTEGER NOT NULL DEFAULT 30,
                price REAL NOT NULL DEFAULT 0,
                products TEXT,
                styles TEXT,
                min_length TEXT,
                after_length TEXT,
                steps TEXT,
                style_type TEXT,
                suitable_length TEXT,
                chemical_brands TEXT,
                chemical_origin TEXT,
                inspection_cert TEXT,
                color_tone TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                barber_id INTEGER NOT NULL,
                appointment_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT NOT NULL DEFAULT 'Pending',
                status_before_cancel_request TEXT,
                note TEXT,
                hair_condition TEXT,
                style_request TEXT,
                payment_method TEXT NOT NULL DEFAULT 'Salon',
                payment_status TEXT NOT NULL DEFAULT 'Unpaid',
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                FOREIGN KEY(barber_id) REFERENCES barbers(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS appointment_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appointment_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                price REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
                FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appointment_id INTEGER UNIQUE NOT NULL,
                customer_id INTEGER NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                payment_method TEXT DEFAULT 'Cash',
                payment_status TEXT DEFAULT 'Paid',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE CASCADE,
                FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                amount REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
                FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS customer_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                appointment_id INTEGER,
                service_id INTEGER,
                hair_style TEXT,
                hair_color TEXT,
                customer_note TEXT,
                barber_note TEXT,
                result TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                FOREIGN KEY(appointment_id) REFERENCES appointments(id) ON DELETE SET NULL,
                FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS ai_chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                mode TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                user_id INTEGER,
                message TEXT,
                ai_response TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
            CREATE INDEX IF NOT EXISTS idx_appointments_barber_date ON appointments(barber_id, appointment_date, start_time);
            CREATE INDEX IF NOT EXISTS idx_history_customer ON customer_history(customer_id);
            CREATE INDEX IF NOT EXISTS idx_chat_history_customer ON chat_history(customer_id, created_at);
            """
        )
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(barbers)")
        columns = [col[1] for col in cursor.fetchall()]
        if "phone" not in columns:
            cursor.execute("ALTER TABLE barbers ADD COLUMN phone TEXT")

        # Migrate existing user tables to the current registration schema.
        user_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "phone" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        if "email" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "role" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'customer'")
        if "customer_code" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN customer_code TEXT")
        if "is_active" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        customer_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(customers)").fetchall()
        }
        if "customer_code" not in customer_columns:
            conn.execute("ALTER TABLE customers ADD COLUMN customer_code TEXT")
        service_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(services)").fetchall()
        }
        for column in ("products", "styles", "min_length", "after_length", "steps",
                       "style_type", "suitable_length", "chemical_brands",
                       "chemical_origin", "inspection_cert", "color_tone"):
            if column not in service_columns:
                conn.execute(f"ALTER TABLE services ADD COLUMN {column} TEXT")
        appointment_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(appointments)").fetchall()
        }
        if "hair_condition" not in appointment_columns:
            conn.execute("ALTER TABLE appointments ADD COLUMN hair_condition TEXT")
        if "style_request" not in appointment_columns:
            conn.execute("ALTER TABLE appointments ADD COLUMN style_request TEXT")
        if "payment_method" not in appointment_columns:
            conn.execute("ALTER TABLE appointments ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Salon'")
        if "payment_status" not in appointment_columns:
            conn.execute("ALTER TABLE appointments ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Unpaid'")
        if "status_before_cancel_request" not in appointment_columns:
            conn.execute("ALTER TABLE appointments ADD COLUMN status_before_cancel_request TEXT")
        if "user_id" not in appointment_columns:
            conn.execute("ALTER TABLE appointments ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
        # Migration for databases created before barbers were linked to login accounts.
        barber_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(barbers)").fetchall()
        }
        if "user_id" not in barber_columns:
            conn.execute(
                "ALTER TABLE barbers ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
            )
        if "base_salary" not in barber_columns:
            conn.execute("ALTER TABLE barbers ADD COLUMN base_salary REAL NOT NULL DEFAULT 5000000")
        if "commission_rate" not in barber_columns:
            conn.execute("ALTER TABLE barbers ADD COLUMN commission_rate REAL NOT NULL DEFAULT 15")
        for column, definition in (
            ("experience_years", "INTEGER NOT NULL DEFAULT 0"),
            ("specialties", "TEXT"),
            ("bio", "TEXT"),
            ("gender_focus", "TEXT"),
            ("rating", "REAL DEFAULT 5.0"),
            ("review_count", "INTEGER NOT NULL DEFAULT 0"),
            ("total_customers", "INTEGER NOT NULL DEFAULT 0"),
            ("awards", "TEXT"),
            ("philosophy", "TEXT"),
        ):
            if column not in barber_columns:
                try:
                    conn.execute(f"ALTER TABLE barbers ADD COLUMN {column} {definition}")
                except sqlite3.OperationalError:
                    # Another startup path may have added the column after PRAGMA
                    # inspected the table. Ignore only that duplicate-column case.
                    refreshed_columns = {
                        row["name"] for row in conn.execute("PRAGMA table_info(barbers)").fetchall()
                    }
                    if column not in refreshed_columns:
                        raise
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS monthly_expenses (
                month TEXT PRIMARY KEY,
                amount REAL NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS payroll_month_closings (
                month TEXT PRIMARY KEY,
                closed_by INTEGER,
                closed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(closed_by) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS payroll_settlements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                barber_id INTEGER NOT NULL,
                completed_appointments INTEGER NOT NULL DEFAULT 0,
                sales REAL NOT NULL DEFAULT 0,
                base_salary REAL NOT NULL DEFAULT 0,
                commission_rate REAL NOT NULL DEFAULT 0,
                commission REAL NOT NULL DEFAULT 0,
                total_salary REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(barber_id) REFERENCES barbers(id) ON DELETE RESTRICT,
                UNIQUE(month, barber_id)
            );
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_barbers_user_id "
            "ON barbers(user_id) WHERE user_id IS NOT NULL"
        )
        _upsert_default_accounts(conn)
        _ensure_default_stylist_profiles(conn)
        _ensure_standard_services(conn)
        update_all_services_rich_info(conn)
        conn.commit()
        try:
            seed_data(conn)
            # seed_data may add legacy services such as "Uốn tóc Restyle";
            # apply the rich metadata again so every service is covered.
            update_all_services_rich_info(conn)
            _backfill_customer_codes(conn)
            # Link legacy stylist accounts to their barber records by phone or name.
            conn.execute(
                """
                UPDATE barbers
                SET user_id = (
                    SELECT users.id FROM users
                    WHERE users.role IN ('stylist', 'barber')
                      AND ((users.phone IS NOT NULL AND users.phone = barbers.phone)
                           OR users.full_name = barbers.full_name)
                    ORDER BY CASE WHEN users.phone IS NOT NULL AND users.phone = barbers.phone THEN 0 ELSE 1 END
                    LIMIT 1
                )
                WHERE user_id IS NULL AND EXISTS (
                    SELECT 1 FROM users
                    WHERE users.role IN ('stylist', 'barber')
                      AND ((users.phone IS NOT NULL AND users.phone = barbers.phone)
                           OR users.full_name = barbers.full_name)
                )
                """
            )
            conn.execute(
                "UPDATE users SET full_name = 'Trần Quốc Tuấn' WHERE username = 'tho01'"
            )
            conn.execute(
                """UPDATE barbers
                   SET full_name = (SELECT full_name FROM users WHERE users.id = barbers.user_id)
                   WHERE user_id = (SELECT id FROM users WHERE username = 'tho01')"""
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"Database seed warning: optional sample data was skipped: {exc}")
        try:
            _ensure_sample_customer_appointments(conn)
            _backfill_customer_codes(conn)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"Database sample appointment warning: {exc}")
    finally:
        conn.close()


def seed_data(conn):
    sample_users = [
        ("khach01", "Lê Văn C", "customer", "0912345678", None),
        ("tho01", "Trần Quốc Tuấn", "stylist", "0901000001", None),
        ("admin", "Quản trị viên", "admin", None, "admin@hairstudio.vn"),
    ]
    sample_password_hash = generate_password_hash("123456")
    for username, full_name, role, phone, email in sample_users:
        conn.execute(
            """INSERT INTO users(username,password_hash,full_name,phone,email,role)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(username) DO UPDATE SET
                   password_hash = excluded.password_hash,
                   full_name = excluded.full_name,
                   phone = COALESCE(excluded.phone, users.phone),
                   email = COALESCE(excluded.email, users.email),
                   role = excluded.role""",
            (username, sample_password_hash, full_name, phone, email, role),
        )
    conn.execute(
        "INSERT OR IGNORE INTO users(username,password_hash,full_name,role) VALUES (?,?,?,?)",
        ("le_tan", sample_password_hash, "Lê Tân", "staff"),
    )

    if conn.execute("SELECT COUNT(*) FROM barbers").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO barbers(full_name,phone,specialty,experience,status) VALUES (?,?,?,?,?)",
            [
                ("Nguyễn Minh Quân", "0901000001", "Cắt tạo kiểu", "6 năm", "active"),
                ("Trần Duy Long", "0901000002", "Nhuộm", "5 năm", "active"),
                ("Lê Hoàng Nam", "0901000003", "Uốn và phục hồi", "7 năm", "active"),
            ],
        )

    standard_services = [
        ("Gội dưỡng tóc", "shampoo_natural", "Dầu gội bồ kết thiên nhiên, tinh dầu bưởi.", 45, 150000),
        ("Gội đầu Dưỡng sinh", "shampoo_herbal", "Dược liệu thảo mộc Đông y, dầu bồ kết organic.", 40, 150000),
        ("Nhuộm tóc", "hair_color_loreal", "Thuốc nhuộm L'Oreal cao cấp.", 150, 650000),
        ("Nhuộm tóc Thời trang", "hair_color_fashion", "Thuốc nhuộm Olaplex hỗ trợ khôi phục cấu trúc tóc.", 90, 600000),
        ("Cắt & Tạo kiểu Nữ", "haircut_women", "Tạo kiểu Bob, Pixie hoặc Layer nữ theo khuôn mặt.", 45, 200000),
        ("Cắt layer", "haircut_layer", "Layer tầng cao, Layer bay Hàn Quốc.", 60, 180000),
        ("Cắt tóc Nam", "haircut_men_classic", "Undercut, Side Part hoặc Ivy League.", 30, 100000),
        ("Cắt tóc nam (Stylist)", "haircut_men_modern", "Two-Block hoặc Mullet hiện đại.", 45, 120000),
        ("Uốn tóc", "hair_perm", "Thuốc uốn lạnh/nóng Goldwell.", 180, 850000),
        ("Phục hồi tóc", "hair_repair", "Dược liệu Keratin và Collagen tươi.", 90, 450000),
    ]
    for service in standard_services:
        existing = conn.execute(
            "SELECT id FROM services WHERE name = ? ORDER BY id LIMIT 1",
            (service[0],),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE services SET category = ?, description = ?,
                       duration_minutes = ?, price = ?, status = 'active'
                   WHERE id = ?""",
                (*service[1:], existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO services(name, category, description, duration_minutes, price)
                   VALUES (?, ?, ?, ?, ?)""",
                service,
            )

    if conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO customers(full_name,phone,email,note) VALUES (?,?,?,?)",
            [
                ("Nguyễn Văn An", "0912000001", "an@example.com", "Thích kiểu layer, màu nâu."),
                ("Trần Thị Bình", "0912000002", "binh@example.com", "Ưa tóc ngắn và dễ chăm sóc."),
                ("Lê Minh Châu", "0912000003", "chau@example.com", "Từng nhuộm tóc, tóc hơi khô."),
            ],
        )


def authenticate_user(username, password):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row and row["is_active"] and check_password_hash(row["password_hash"], password) else None


def register_user(username, password, full_name, phone, role="customer", email=None):
    """Create an account and assign a customer code to customer accounts."""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO users(username,password_hash,full_name,phone,email,role) VALUES (?,?,?,?,?,?)",
            (username, generate_password_hash(password), full_name, phone, email, role),
        )
        user_id = cursor.lastrowid
        if role == "customer":
            customer = conn.execute(
                "SELECT id FROM customers WHERE phone = ?", (phone,)
            ).fetchone()
            if customer:
                customer_id = customer["id"]
                conn.execute(
                    "UPDATE customers SET full_name = ?, email = COALESCE(?, email) WHERE id = ?",
                    (full_name, email, customer_id),
                )
            else:
                customer_id = conn.execute(
                    "INSERT INTO customers(full_name, phone, email) VALUES (?, ?, ?)",
                    (full_name, phone, email),
                ).lastrowid
            customer_code = f"KH{customer_id:03d}"
            conn.execute(
                "UPDATE users SET customer_code = ? WHERE id = ?",
                (customer_code, user_id),
            )
        conn.commit()
        return user_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


EMPLOYEE_ROLES = {"admin", "receptionist", "staff", "stylist"}


def list_employees():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT u.id, u.username, u.full_name, u.phone, u.email, u.role,
                      u.is_active, COALESCE(b.specialty, '') AS specialty,
                      COALESCE(b.experience_years, 0) AS experience_years,
                      COALESCE(b.specialties, b.specialty, '') AS specialties,
                      COALESCE(b.bio, '') AS bio,
                      COALESCE(b.gender_focus, 'both') AS gender_focus,
                      COALESCE(b.rating, 0) AS rating,
                      COALESCE(b.review_count, 0) AS review_count,
                      COALESCE(b.total_customers, 0) AS total_customers,
                      COALESCE(b.awards, '') AS awards,
                      COALESCE(b.philosophy, '') AS philosophy,
                      COALESCE(b.base_salary, 0) AS base_salary,
                      COALESCE(b.commission_rate, 0) AS commission_rate
               FROM users u LEFT JOIN barbers b ON b.user_id = u.id
               WHERE u.role IN ('admin', 'staff', 'receptionist', 'stylist')
               ORDER BY CASE u.role WHEN 'admin' THEN 0 WHEN 'receptionist' THEN 1
                                    WHEN 'staff' THEN 2 ELSE 3 END, u.full_name"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_employee(username, password, full_name, phone, email, role, specialty="",
                    base_salary=5000000, commission_rate=15, experience_years=0,
                    specialties="", bio="", gender_focus="both", rating=0,
                    review_count=0, total_customers=0, awards="", philosophy=""):
    username, full_name = (username or "").strip(), (full_name or "").strip()
    phone, email, specialty = (phone or "").strip(), (email or "").strip(), (specialty or "").strip()
    specialties, bio = (specialties or "").strip(), (bio or "").strip()
    awards, philosophy = (awards or "").strip(), (philosophy or "").strip()
    if len(username) < 4 or not password or len(password) < 6 or not full_name:
        raise ValueError("Nhập tên đăng nhập từ 4 ký tự, mật khẩu từ 6 ký tự và họ tên đầy đủ.")
    if role not in EMPLOYEE_ROLES:
        raise ValueError("Chức vụ không hợp lệ.")
    try:
        experience_years = max(0, int(experience_years or 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Số năm kinh nghiệm phải là số nguyên không âm.") from exc
    if gender_focus not in {"male", "female", "both"}:
        raise ValueError("Đối tượng chuyên tóc không hợp lệ.")
    try:
        rating = float(rating or 0)
        review_count = max(0, int(review_count or 0))
        total_customers = max(0, int(total_customers or 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Điểm đánh giá và số lượt khách phải là số hợp lệ.") from exc
    if not math.isfinite(rating) or not 0 <= rating <= 5:
        raise ValueError("Điểm đánh giá phải nằm trong khoảng 0 đến 5.")
    try:
        base_salary, commission_rate = float(base_salary), float(commission_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("Lương cứng và hoa hồng phải là số hợp lệ.") from exc
    if not math.isfinite(base_salary) or base_salary < 0 or not math.isfinite(commission_rate) or not 0 <= commission_rate <= 100:
        raise ValueError("Lương cứng phải không âm và hoa hồng từ 0 đến 100%.")
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO users(username, password_hash, full_name, phone, email, role, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (username, generate_password_hash(password), full_name, phone or None,
             email or None, role),
        )
        user_id = cursor.lastrowid
        if role == "stylist":
            conn.execute(
                """INSERT INTO barbers(
                       user_id, full_name, phone, specialty, experience, experience_years,
                       specialties, bio, gender_focus, rating, review_count, total_customers,
                       awards, philosophy, base_salary, commission_rate, status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                (user_id, full_name, phone or None, specialty or None,
                 f"{experience_years} năm" if experience_years else "", experience_years,
                 specialties or specialty or None, bio or None, gender_focus, rating,
                 review_count, total_customers, awards or None, philosophy or None,
                 base_salary, commission_rate),
            )
        conn.commit()
        return user_id
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Tên đăng nhập đã tồn tại hoặc thông tin nhân viên không hợp lệ.") from exc
    finally:
        conn.close()


def update_employee(employee_id, username, full_name, phone, email, role, specialty="",
                    base_salary=5000000, commission_rate=15, experience_years=0,
                    specialties="", bio="", gender_focus="both", rating=0,
                    review_count=0, total_customers=0, awards="", philosophy=""):
    username, full_name = (username or "").strip(), (full_name or "").strip()
    phone, email, specialty = (phone or "").strip(), (email or "").strip(), (specialty or "").strip()
    specialties, bio = (specialties or "").strip(), (bio or "").strip()
    awards, philosophy = (awards or "").strip(), (philosophy or "").strip()
    if len(username) < 4 or not full_name or role not in EMPLOYEE_ROLES:
        raise ValueError("Thông tin nhân viên không hợp lệ.")
    try:
        experience_years = max(0, int(experience_years or 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Số năm kinh nghiệm phải là số nguyên không âm.") from exc
    if gender_focus not in {"male", "female", "both"}:
        raise ValueError("Đối tượng chuyên tóc không hợp lệ.")
    try:
        rating = float(rating or 0)
        review_count = max(0, int(review_count or 0))
        total_customers = max(0, int(total_customers or 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Điểm đánh giá và số lượt khách phải là số hợp lệ.") from exc
    if not math.isfinite(rating) or not 0 <= rating <= 5:
        raise ValueError("Điểm đánh giá phải nằm trong khoảng 0 đến 5.")
    try:
        base_salary, commission_rate = float(base_salary), float(commission_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("Lương cứng và hoa hồng phải là số hợp lệ.") from exc
    if not math.isfinite(base_salary) or base_salary < 0 or not math.isfinite(commission_rate) or not 0 <= commission_rate <= 100:
        raise ValueError("Lương cứng phải không âm và hoa hồng từ 0 đến 100%.")
    conn = get_db_connection()
    try:
        current = conn.execute("SELECT role, is_active FROM users WHERE id = ?", (employee_id,)).fetchone()
        if not current:
            raise ValueError("Không tìm thấy tài khoản nhân viên.")
        if current["role"] == "admin" and role != "admin":
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise ValueError("Không thể hạ quyền quản trị viên cuối cùng đang hoạt động.")
        conn.execute(
            """UPDATE users SET username = ?, full_name = ?, phone = ?, email = ?, role = ?
               WHERE id = ?""",
            (username, full_name, phone or None, email or None, role, employee_id),
        )
        barber = conn.execute("SELECT id FROM barbers WHERE user_id = ?", (employee_id,)).fetchone()
        if role == "stylist":
            if barber:
                conn.execute(
                    """UPDATE barbers SET full_name = ?, phone = ?, specialty = ?,
                              experience = ?, experience_years = ?, specialties = ?, bio = ?,
                              gender_focus = ?, rating = ?, review_count = ?, total_customers = ?,
                              awards = ?, philosophy = ?, base_salary = ?, commission_rate = ?, status = ?
                       WHERE user_id = ?""",
                    (full_name, phone or None, specialty or None,
                     f"{experience_years} năm" if experience_years else "", experience_years,
                     specialties or specialty or None, bio or None, gender_focus, rating,
                     review_count, total_customers, awards or None, philosophy or None, base_salary,
                     commission_rate,
                     "active" if current["is_active"] else "inactive", employee_id),
                )
            else:
                conn.execute(
                    """INSERT INTO barbers(
                           user_id, full_name, phone, specialty, experience, experience_years,
                           specialties, bio, gender_focus, rating, review_count, total_customers,
                           awards, philosophy, base_salary, commission_rate, status
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (employee_id, full_name, phone or None, specialty or None,
                     f"{experience_years} năm" if experience_years else "", experience_years,
                     specialties or specialty or None, bio or None, gender_focus, rating,
                     review_count, total_customers, awards or None, philosophy or None,
                     base_salary, commission_rate,
                     "active" if current["is_active"] else "inactive"),
                )
        elif barber:
            conn.execute("UPDATE barbers SET status = 'inactive' WHERE user_id = ?", (employee_id,))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Tên đăng nhập đã tồn tại hoặc thông tin nhân viên không hợp lệ.") from exc
    finally:
        conn.close()


def change_employee_password(employee_id, password):
    if not password or len(password) < 6:
        raise ValueError("Mật khẩu mới phải có ít nhất 6 ký tự.")
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), employee_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Không tìm thấy tài khoản nhân viên.")
        conn.commit()
    finally:
        conn.close()


def set_employee_active(employee_id, active, acting_user_id=None):
    if acting_user_id is not None and int(employee_id) == int(acting_user_id) and not active:
        raise ValueError("Bạn không thể tự khóa tài khoản đang đăng nhập.")
    conn = get_db_connection()
    try:
        user = conn.execute("SELECT role FROM users WHERE id = ?", (employee_id,)).fetchone()
        if not user:
            raise ValueError("Không tìm thấy tài khoản nhân viên.")
        if user["role"] == "admin" and not active:
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise ValueError("Không thể khóa quản trị viên cuối cùng đang hoạt động.")
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, employee_id))
        conn.execute(
            "UPDATE barbers SET status = ? WHERE user_id = ?",
            ("active" if active and user["role"] == "stylist" else "inactive", employee_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_user(user_id):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def dashboard_stats():
    """Return current dashboard counters, completed-service revenue, and stylist activity."""
    conn = get_db_connection()
    try:
        today = datetime.now().date().isoformat()
        current_month = datetime.now().strftime("%Y-%m")
        stats = {
            "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
            "appointments_today": conn.execute(
                "SELECT COUNT(*) FROM appointments WHERE appointment_date = ? AND status != 'Cancelled'",
                (today,),
            ).fetchone()[0],
            "pending": conn.execute(
                """SELECT COUNT(*) FROM appointments
                   WHERE status IN ('Pending', 'Cancel Requested')
                      OR payment_status = 'Pending Verification'"""
            ).fetchone()[0],
            "revenue_month": conn.execute(
                """SELECT COALESCE(SUM(aps.quantity * aps.price), 0)
                   FROM appointments a
                   JOIN appointment_services aps ON aps.appointment_id = a.id
                   WHERE a.status = 'Completed'
                     AND substr(a.appointment_date, 1, 7) = ?""",
                (current_month,),
            ).fetchone()[0],
            "top_stylists": [dict(row) for row in conn.execute(
                """SELECT COALESCE(NULLIF(u.full_name, ''), b.full_name) AS name,
                          COUNT(DISTINCT a.id) AS completed
                   FROM barbers b
                   LEFT JOIN users u ON u.id = b.user_id
                   LEFT JOIN appointments a ON a.barber_id = b.id AND a.status = 'Completed'
                   GROUP BY b.id, b.full_name, u.full_name
                   ORDER BY completed DESC, name COLLATE NOCASE
                   LIMIT 5"""
            ).fetchall()],
        }
        stats["total_revenue"] = stats["revenue_month"]
        return stats
    finally:
        conn.close()


def get_admin_dashboard_summary():
    """Return a compact, real-time data snapshot for the admin AI assistant."""
    conn = get_db_connection()
    try:
        today = datetime.now().date().isoformat()
        row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN LOWER(status) IN ('pending','chờ xác nhận','chờ thực hiện') THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN LOWER(status) IN ('completed','đã hoàn thành','hoàn thành') THEN 1 ELSE 0 END) AS completed
               FROM appointments WHERE appointment_date = ?""",
            (today,),
        ).fetchone()
        stylist_rows = conn.execute(
            """SELECT username, COALESCE(NULLIF(full_name, ''), username) AS full_name
               FROM users WHERE role = 'stylist' ORDER BY username"""
        ).fetchall()
        return {
            "total_customers": int(conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] or 0),
            "today_appointments": int(row["total"] or 0),
            "pending_count": int(row["pending"] or 0),
            "completed_count": int(row["completed"] or 0),
            "total_revenue": float(conn.execute("SELECT COALESCE(SUM(total), 0) FROM invoices").fetchone()[0] or 0),
            "stylists": [dict(item) for item in stylist_rows],
        }
    finally:
        conn.close()


def _normalize_report_month(month=None):
    month = (month or datetime.now().strftime("%Y-%m")).strip()
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Tháng báo cáo không hợp lệ.") from exc
    if parsed.strftime("%Y-%m") != month:
        raise ValueError("Tháng báo cáo không hợp lệ.")
    return month


def _monthly_payroll_rows(conn, month):
    rows = conn.execute(
        """SELECT b.id AS barber_id, b.full_name AS name,
                  COALESCE(ps.completed_appointments, COUNT(DISTINCT a.id)) AS completed,
                  COALESCE(ps.sales, SUM(COALESCE(aps.quantity * aps.price, 0)), 0) AS sales,
                  COALESCE(ps.base_salary, b.base_salary, 0) AS base_salary,
                  COALESCE(ps.commission_rate, b.commission_rate, 0) AS commission_rate,
                  COALESCE(ps.commission,
                      COALESCE(SUM(COALESCE(aps.quantity * aps.price, 0)), 0)
                      * COALESCE(b.commission_rate, 0) / 100.0) AS commission,
                  COALESCE(ps.total_salary,
                      COALESCE(b.base_salary, 0) +
                      COALESCE(SUM(COALESCE(aps.quantity * aps.price, 0)), 0)
                      * COALESCE(b.commission_rate, 0) / 100.0) AS total_salary
           FROM barbers b
           LEFT JOIN appointments a ON a.barber_id = b.id
                AND a.status = 'Completed' AND substr(a.appointment_date, 1, 7) = ?
           LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
           LEFT JOIN payroll_settlements ps ON ps.barber_id = b.id AND ps.month = ?
           GROUP BY b.id, b.full_name, b.base_salary, b.commission_rate,
                    ps.completed_appointments, ps.sales, ps.base_salary,
                    ps.commission_rate, ps.commission, ps.total_salary
           ORDER BY total_salary DESC, b.full_name""",
        (month, month),
    ).fetchall()
    return [dict(row) for row in rows]


def admin_revenue_report(month=None):
    """Aggregate verified revenue, daily tenders, and monthly stylist payroll."""
    month = _normalize_report_month(month)
    conn = get_db_connection()
    today = datetime.now().date()
    first_day = (today - timedelta(days=6)).isoformat()
    last_day = today.isoformat()
    try:
        totals = conn.execute(
            """WITH appointment_totals AS (
                   SELECT a.id, a.status,
                          COALESCE((SELECT SUM(aps.quantity * aps.price)
                                    FROM appointment_services aps
                                    WHERE aps.appointment_id = a.id), 0) AS amount,
                          CASE WHEN a.payment_status IN ('Paid Online', 'Paid') OR EXISTS(
                              SELECT 1 FROM invoices i
                              WHERE i.appointment_id = a.id AND i.payment_status = 'Paid'
                          ) THEN 1 ELSE 0 END AS is_paid
                   FROM appointments a
               )
               SELECT COALESCE(SUM(CASE WHEN is_paid = 1 AND status != 'Cancelled'
                                        THEN amount ELSE 0 END), 0) AS revenue,
                      SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed,
                      SUM(CASE WHEN status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled
               FROM appointment_totals"""
        ).fetchone()
        revenue = float(totals["revenue"] or 0)
        completed = int(totals["completed"] or 0)
        cancelled = int(totals["cancelled"] or 0)

        day_totals = conn.execute(
            """WITH daily_orders AS (
                   SELECT a.id, a.status, a.payment_status,
                          COALESCE(i.payment_method, a.payment_method, '') AS method,
                          COALESCE((SELECT SUM(aps.quantity * aps.price)
                                    FROM appointment_services aps
                                    WHERE aps.appointment_id = a.id), 0) AS amount,
                          COALESCE(i.payment_status, '') AS invoice_status
                   FROM appointments a
                   LEFT JOIN invoices i ON i.appointment_id = a.id
                   WHERE a.appointment_date = ?
               )
               SELECT SUM(CASE WHEN status != 'Cancelled' THEN 1 ELSE 0 END) AS order_count,
                      COALESCE(SUM(CASE WHEN status = 'Completed'
                          AND (payment_status = 'Paid Online' OR method LIKE '%QR%')
                          AND (payment_status != 'Pending Verification' OR invoice_status = 'Paid')
                          THEN amount ELSE 0 END), 0) AS vietqr,
                      COALESCE(SUM(CASE WHEN status = 'Completed'
                          AND method NOT LIKE '%QR%'
                          AND (payment_status != 'Pending Verification' OR invoice_status = 'Paid')
                          THEN amount ELSE 0 END), 0) AS cash
               FROM daily_orders""",
            (today.isoformat(),),
        ).fetchone()

        monthly_revenue = conn.execute(
            """SELECT COALESCE(SUM(CASE
                      WHEN a.payment_status IN ('Paid Online', 'Paid') OR i.payment_status = 'Paid'
                      THEN ap.amount ELSE 0 END), 0)
               FROM appointments a
               LEFT JOIN invoices i ON i.appointment_id = a.id
               JOIN (SELECT appointment_id, SUM(quantity * price) AS amount
                     FROM appointment_services GROUP BY appointment_id) ap
                 ON ap.appointment_id = a.id
               WHERE substr(a.appointment_date, 1, 7) = ? AND a.status != 'Cancelled'""",
            (month,),
        ).fetchone()[0]
        expense = conn.execute(
            "SELECT amount FROM monthly_expenses WHERE month = ?", (month,)
        ).fetchone()
        payroll = _monthly_payroll_rows(conn, month)
        closing = conn.execute(
            "SELECT closed_at FROM payroll_month_closings WHERE month = ?", (month,)
        ).fetchone()

        daily_rows = conn.execute(
            """SELECT a.appointment_date AS day, SUM(aps.quantity * aps.price) AS revenue
               FROM appointments a
               JOIN appointment_services aps ON aps.appointment_id = a.id
               WHERE a.appointment_date BETWEEN ? AND ?
                 AND a.status != 'Cancelled'
                 AND (a.payment_status IN ('Paid Online', 'Paid') OR EXISTS(
                     SELECT 1 FROM invoices i
                     WHERE i.appointment_id = a.id AND i.payment_status = 'Paid'
                 ))
               GROUP BY a.appointment_date""",
            (first_day, last_day),
        ).fetchall()
        daily_map = {row["day"]: float(row["revenue"] or 0) for row in daily_rows}
        days = [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]

        service_rows = conn.execute(
            """SELECT s.name, SUM(aps.quantity) AS bookings
               FROM appointment_services aps
               JOIN services s ON s.id = aps.service_id
               JOIN appointments a ON a.id = aps.appointment_id
               WHERE a.status != 'Cancelled'
               GROUP BY s.id, s.name
               ORDER BY bookings DESC, s.name
               LIMIT 8"""
        ).fetchall()
        service_revenue_rows = conn.execute(
            """SELECT s.name, SUM(aps.quantity * aps.price) AS revenue
               FROM appointment_services aps
               JOIN services s ON s.id = aps.service_id
               JOIN appointments a ON a.id = aps.appointment_id
               WHERE a.status != 'Cancelled'
                 AND (a.payment_status IN ('Paid Online', 'Paid') OR EXISTS(
                     SELECT 1 FROM invoices i
                     WHERE i.appointment_id = a.id AND i.payment_status = 'Paid'
                 ))
               GROUP BY s.id, s.name
               ORDER BY revenue DESC, s.name
               LIMIT 8"""
        ).fetchall()
        stylist_rows = conn.execute(
            """SELECT COALESCE(NULLIF(u.full_name, ''), b.full_name) AS name,
                      COUNT(DISTINCT a.id) AS completed,
                      COALESCE(SUM((SELECT SUM(aps.quantity * aps.price)
                                    FROM appointment_services aps
                                    WHERE aps.appointment_id = a.id)), 0) AS revenue
               FROM appointments a
               JOIN barbers b ON b.id = a.barber_id
               LEFT JOIN users u ON u.id = b.user_id
               WHERE a.status = 'Completed'
               GROUP BY b.id, u.full_name, b.full_name
               ORDER BY completed DESC, revenue DESC
               LIMIT 5"""
        ).fetchall()
        return {
            "revenue": revenue,
            "completed": completed,
            "average": revenue / completed if completed else 0,
            "cancelled": cancelled,
            "month": month,
            "monthly_revenue": float(monthly_revenue or 0),
            "monthly_expense": float(expense["amount"] if expense else 0),
            "net_profit": float(monthly_revenue or 0) - float(expense["amount"] if expense else 0),
            "today_vietqr": float(day_totals["vietqr"] or 0),
            "today_cash": float(day_totals["cash"] or 0),
            "today_orders": int(day_totals["order_count"] or 0),
            "payroll": payroll,
            "payroll_closed": bool(closing),
            "payroll_closed_at": closing["closed_at"] if closing else None,
            "daily_labels": days,
            "daily_values": [daily_map.get(day, 0) for day in days],
            "service_labels": [row["name"] for row in service_revenue_rows],
            "service_values": [float(row["revenue"] or 0) for row in service_revenue_rows],
            "top_stylists": [dict(row) for row in stylist_rows],
            "top_services": [dict(row) for row in service_rows],
        }
    finally:
        conn.close()


def set_monthly_expense(month, amount):
    month = _normalize_report_month(month)
    try:
        amount = float(amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("Chi phí tháng phải là số hợp lệ.") from exc
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("Chi phí tháng phải là số không âm.")
    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT INTO monthly_expenses(month, amount) VALUES (?, ?)
               ON CONFLICT(month) DO UPDATE SET amount = excluded.amount,
                                                updated_at = CURRENT_TIMESTAMP""",
            (month, amount),
        )
        conn.commit()
    finally:
        conn.close()


def close_monthly_payroll(month, admin_user_id):
    month = _normalize_report_month(month)
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute(
            "SELECT 1 FROM payroll_month_closings WHERE month = ?", (month,)
        ).fetchone():
            raise ValueError("Bảng lương tháng này đã được chốt.")
        rows = conn.execute(
            """SELECT b.id AS barber_id, b.base_salary, b.commission_rate,
                      COUNT(DISTINCT a.id) AS completed,
                      COALESCE(SUM(aps.quantity * aps.price), 0) AS sales
               FROM barbers b
               LEFT JOIN appointments a ON a.barber_id = b.id
                    AND a.status = 'Completed' AND substr(a.appointment_date, 1, 7) = ?
               LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
               GROUP BY b.id, b.base_salary, b.commission_rate""",
            (month,),
        ).fetchall()
        for row in rows:
            commission = float(row["sales"] or 0) * float(row["commission_rate"] or 0) / 100
            conn.execute(
                """INSERT INTO payroll_settlements(
                       month, barber_id, completed_appointments, sales, base_salary,
                       commission_rate, commission, total_salary
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (month, row["barber_id"], row["completed"], row["sales"],
                 row["base_salary"], row["commission_rate"], commission,
                 float(row["base_salary"] or 0) + commission),
            )
        conn.execute(
            "INSERT INTO payroll_month_closings(month, closed_by) VALUES (?, ?)",
            (month, admin_user_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_customer(customer_id):
    conn = get_db_connection()
    try:
        cursor = conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        if cursor.rowcount == 0:
            raise ValueError("Không tìm thấy khách hàng.")
        conn.commit()
    finally:
        conn.close()


def create_customer(p):
    full_name = (p.get("full_name") or "").strip()
    phone = (p.get("phone") or "").strip()
    if not full_name or not phone:
        raise ValueError("Họ tên và số điện thoại là bắt buộc.")
    conn = get_db_connection()
    try:
        exists = conn.execute("SELECT 1 FROM customers WHERE phone = ?", (phone,)).fetchone()
        if exists:
            raise ValueError("Số điện thoại này đã được sử dụng cho khách hàng khác.")
        cursor = conn.execute(
            "INSERT INTO customers(full_name, phone, email, gender, birthday, note) VALUES (?, ?, ?, ?, ?, ?)",
            (full_name, phone, (p.get("email") or "").strip() or None,
             (p.get("gender") or "").strip() or None,
             (p.get("birthday") or "").strip() or None,
             (p.get("note") or "").strip() or None),
        )
        customer_id = cursor.lastrowid
        conn.execute(
            "UPDATE customers SET customer_code = ? WHERE id = ?",
            (f"KH{customer_id:03d}", customer_id),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Không thể lưu khách hàng. Hãy kiểm tra số điện thoại có bị trùng không.") from exc
    finally:
        conn.close()


def list_customers(q=""):
    conn = get_db_connection()
    try:
        sql = """SELECT c.*,
                    COALESCE((SELECT u.customer_code FROM users u
                              WHERE u.role = 'customer' AND u.phone = c.phone
                              ORDER BY u.id DESC LIMIT 1), c.customer_code) AS customer_code,
                    (SELECT COUNT(*) FROM appointments a
                     WHERE a.customer_id = c.id) AS total_appointments,
                    (SELECT COALESCE(SUM(i.total), 0) FROM invoices i
                     WHERE i.customer_id = c.id AND i.payment_status = 'Paid') AS total_spent
             FROM customers c WHERE 1 = 1"""
        params = []
        if q:
            sql += " AND (c.full_name LIKE ? OR c.phone LIKE ? OR c.email LIKE ? OR c.customer_code LIKE ?)"
            params.extend([f"%{q}%"] * 4)
        sql += " ORDER BY c.id DESC"
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def get_customer_by_code(customer_code):
    code = (customer_code or "").strip().upper()
    if not code:
        return None
    conn = get_db_connection()
    try:
        row = conn.execute(
            """SELECT c.*,
                      COALESCE((SELECT u.customer_code FROM users u
                                WHERE u.role = 'customer' AND u.phone = c.phone
                                ORDER BY u.id DESC LIMIT 1), c.customer_code) AS customer_code
               FROM customers c
               WHERE UPPER(COALESCE((SELECT u.customer_code FROM users u
                                     WHERE u.role = 'customer' AND u.phone = c.phone
                                     ORDER BY u.id DESC LIMIT 1), c.customer_code)) = ?
               ORDER BY c.id DESC LIMIT 1""",
            (code,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_customer_by_phone(phone):
    phone = (phone or "").strip()
    if not phone:
        return None
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM customers WHERE phone = ?", (phone,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def latest_booked_customer():
    conn = get_db_connection()
    try:
        row = conn.execute(
            """SELECT c.* FROM appointments a
               JOIN customers c ON c.id = a.customer_id
               ORDER BY a.id DESC LIMIT 1"""
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_customer(customer_id):
    conn = get_db_connection(); row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone(); conn.close(); return dict(row) if row else None


def update_customer(customer_id, full_name, phone, email, gender, birthday, note):
    full_name = (full_name or "").strip()
    phone = (phone or "").strip()
    if not full_name or not phone:
        raise ValueError("Họ tên và số điện thoại là bắt buộc.")
    conn = get_db_connection()
    try:
        customer = conn.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not customer:
            raise ValueError("Không tìm thấy khách hàng cần cập nhật.")
        duplicate = conn.execute(
            "SELECT 1 FROM customers WHERE phone = ? AND id != ?", (phone, customer_id)
        ).fetchone()
        if duplicate:
            raise ValueError("Số điện thoại này đã thuộc về khách hàng khác.")
        conn.execute(
            "UPDATE customers SET full_name = ?, phone = ?, email = ?, gender = ?, birthday = ?, note = ? WHERE id = ?",
            (full_name, phone, (email or "").strip() or None,
             (gender or "").strip() or None, (birthday or "").strip() or None,
             (note or "").strip() or None, customer_id),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Không thể cập nhật khách hàng do dữ liệu bị trùng hoặc không hợp lệ.") from exc
    finally:
        conn.close()


def list_barbers(active_only=False):
    conn = get_db_connection()
    try:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM barbers WHERE status = 'active' ORDER BY full_name"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM barbers ORDER BY full_name").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_booked_slots(barber_id, appointment_date):
    """Return occupied stylist intervals for one date, excluding cancelled requests."""
    try:
        barber_id = int(barber_id)
        appointment_date = datetime.strptime(str(appointment_date), "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError("Thợ hoặc ngày hẹn không hợp lệ.") from exc
    conn = get_db_connection()
    try:
        barber = conn.execute(
            "SELECT id FROM barbers WHERE id = ? AND status = 'active'", (barber_id,)
        ).fetchone()
        if not barber:
            raise ValueError("Không tìm thấy Stylist đang hoạt động.")
        rows = conn.execute(
            """SELECT a.id, a.start_time, a.end_time,
                      COALESCE(SUM(COALESCE(s.duration_minutes, 0) * COALESCE(aps.quantity, 1)), 0) AS duration_minutes
               FROM appointments a
               LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
               LEFT JOIN services s ON s.id = aps.service_id
               WHERE a.barber_id = ? AND a.appointment_date = ?
                 AND a.status NOT IN ('Cancelled', 'Cancel Requested')
               GROUP BY a.id ORDER BY a.start_time""",
            (barber_id, appointment_date),
        ).fetchall()
        intervals = []
        def parse_time(value):
            for fmt in ("%H:%M", "%H:%M:%S"):
                try:
                    return datetime.strptime(value, fmt).time()
                except (TypeError, ValueError):
                    continue
            raise ValueError("Giờ lịch đã lưu không hợp lệ.")
        for row in rows:
            start = parse_time(row["start_time"])
            end = parse_time(row["end_time"]) if row["end_time"] else None
            start_dt = datetime.combine(datetime.strptime(appointment_date, "%Y-%m-%d").date(), start)
            end_dt = datetime.combine(start_dt.date(), end) if end else start_dt + timedelta(minutes=int(row["duration_minutes"] or 30))
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(minutes=int(row["duration_minutes"] or 30))
            intervals.append({"appointment_id": row["id"], "start_time": start_dt.strftime("%H:%M"), "end_time": end_dt.strftime("%H:%M")})
        return intervals
    finally:
        conn.close()


def create_barber(full_name, phone, specialty, experience, status):
    conn=get_db_connection(); conn.execute("INSERT INTO barbers(full_name,phone,specialty,experience,status) VALUES (?,?,?,?,?)",(full_name,phone,specialty,experience,status)); conn.commit(); conn.close()


def get_barber_for_user(user_id):
    """Return the barber record linked to a login account, if any."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM barbers WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_appointment(appointment_id):
    """Return one appointment record or None."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_customers_for_barber(user_id):
    """Return only customers with non-cancelled appointments assigned to this barber."""
    barber = get_barber_for_user(user_id)
    if not barber:
        return []
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT c.*
            FROM customers c
            JOIN appointments a ON a.customer_id = c.id
            WHERE a.barber_id = ? AND a.status != 'Cancelled'
            ORDER BY c.full_name
            """,
            (barber["id"],),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def barber_can_access_customer(user_id, customer_id):
    barber = get_barber_for_user(user_id)
    if not barber:
        return False
    conn = get_db_connection()
    try:
        return conn.execute(
            "SELECT 1 FROM appointments WHERE barber_id = ? AND customer_id = ? AND status != 'Cancelled' LIMIT 1",
            (barber["id"], customer_id),
        ).fetchone() is not None
    finally:
        conn.close()


def get_all_services():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM services ORDER BY category, name"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_services(active_only=False):
    services = get_all_services()
    if active_only:
        return [service for service in services if service.get("status") == "active"]
    return services


def create_service(name, category, description, duration_minutes, price,
                   style_type="", suitable_length="", color_tone="",
                   chemical_brands="", chemical_origin="", inspection_cert=""):
    name = (name or "").strip()
    category = (category or "").strip() or None
    description = (description or "").strip() or None
    style_type, suitable_length, color_tone = (style_type or "").strip() or None, (suitable_length or "").strip() or None, (color_tone or "").strip() or None
    chemical_brands, chemical_origin, inspection_cert = (chemical_brands or "").strip() or None, (chemical_origin or "").strip() or None, (inspection_cert or "").strip() or None
    try:
        duration_minutes = int(duration_minutes)
        price = float(price)
    except (TypeError, ValueError) as exc:
        raise ValueError("Thời lượng và giá dịch vụ phải là số hợp lệ.") from exc
    if not name:
        raise ValueError("Tên dịch vụ là bắt buộc.")
    if duration_minutes <= 0:
        raise ValueError("Thời lượng dịch vụ phải lớn hơn 0 phút.")
    if not math.isfinite(price) or price < 0:
        raise ValueError("Giá dịch vụ phải là số hợp lệ và không âm.")
    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT INTO services(name, category, description, duration_minutes, price,
               style_type, suitable_length, color_tone, chemical_brands, chemical_origin, inspection_cert)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, category, description, duration_minutes, price, style_type, suitable_length, color_tone,
             chemical_brands, chemical_origin, inspection_cert),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Không thể lưu dịch vụ. Vui lòng kiểm tra lại dữ liệu.") from exc
    finally:
        conn.close()


def update_service(service_id, name, category, description, duration_minutes, price,
                   style_type="", suitable_length="", color_tone="",
                   chemical_brands="", chemical_origin="", inspection_cert=""):
    name = (name or "").strip()
    category = (category or "").strip() or None
    description = (description or "").strip() or None
    style_type, suitable_length, color_tone = (style_type or "").strip() or None, (suitable_length or "").strip() or None, (color_tone or "").strip() or None
    chemical_brands, chemical_origin, inspection_cert = (chemical_brands or "").strip() or None, (chemical_origin or "").strip() or None, (inspection_cert or "").strip() or None
    try:
        duration_minutes, price = int(duration_minutes), float(price)
    except (TypeError, ValueError) as exc:
        raise ValueError("Thời lượng và giá dịch vụ phải là số hợp lệ.") from exc
    if not name or duration_minutes <= 0 or not math.isfinite(price) or price < 0:
        raise ValueError("Thông tin dịch vụ không hợp lệ.")
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """UPDATE services SET name = ?, category = ?, description = ?,
                      duration_minutes = ?, price = ?, style_type = ?, suitable_length = ?,
                      color_tone = ?, chemical_brands = ?, chemical_origin = ?, inspection_cert = ?
                      WHERE id = ?""",
            (name, category, description, duration_minutes, price, style_type, suitable_length, color_tone,
             chemical_brands, chemical_origin, inspection_cert, service_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Không tìm thấy dịch vụ.")
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Không thể cập nhật dịch vụ.") from exc
    finally:
        conn.close()


def delete_service(service_id):
    conn = get_db_connection()
    try:
        cursor = conn.execute("DELETE FROM services WHERE id = ?", (service_id,))
        if cursor.rowcount == 0:
            raise ValueError("Không tìm thấy dịch vụ.")
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Dịch vụ đã được sử dụng trong lịch hẹn nên không thể xóa.") from exc
    finally:
        conn.close()


def create_appointment(customer_id, barber_id, appointment_date, start_time, end_time, note, service_ids, user_id=None):
    """Create an appointment, calculate its end time and prevent barber overlaps."""
    conn = get_db_connection()

    def parse_time(value):
        value = str(value or "").strip()
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
        raise ValueError("Giờ hẹn không hợp lệ. Hãy chọn giờ theo định dạng HH:MM.")

    try:
        # Serialize writes while checking overlaps, reducing race conditions.
        conn.execute("BEGIN IMMEDIATE")
        try:
            customer_id = int(customer_id)
            barber_id = int(barber_id)
            service_ids = list(dict.fromkeys(int(value) for value in (service_ids or [])))
            appointment_day = datetime.strptime(
                str(appointment_date or "").strip(), "%Y-%m-%d"
            ).date()
        except (TypeError, ValueError) as exc:
            raise ValueError("Khách hàng, thợ, ngày hẹn hoặc dịch vụ không hợp lệ.") from exc

        if not service_ids:
            raise ValueError("Hãy chọn ít nhất một dịch vụ.")
        if appointment_day < datetime.now().date():
            raise ValueError("Không thể đặt lịch vào ngày đã qua.")

        start_clock = parse_time(start_time)
        start_dt = datetime.combine(appointment_day, start_clock)
        now = datetime.now().replace(second=0, microsecond=0)
        if appointment_day == now.date() and start_dt <= now:
            raise ValueError("Giờ hẹn phải nằm trong tương lai.")

        if not conn.execute("SELECT 1 FROM customers WHERE id = ?", (customer_id,)).fetchone():
            raise ValueError("Không tìm thấy khách hàng đã chọn.")

        barber = conn.execute(
            "SELECT id, status FROM barbers WHERE id = ?", (barber_id,)
        ).fetchone()
        if not barber:
            raise ValueError("Không tìm thấy thợ đã chọn.")
        if barber["status"] != "active":
            raise ValueError("Thợ đã ngừng hoạt động. Hãy chọn thợ khác.")

        placeholders = ",".join("?" for _ in service_ids)
        rows = conn.execute(
            f"SELECT id, name, duration_minutes, price, status FROM services WHERE id IN ({placeholders})",
            service_ids,
        ).fetchall()
        service_map = {int(row["id"]): row for row in rows}
        if len(service_map) != len(service_ids):
            raise ValueError("Có dịch vụ không tồn tại.")

        total_duration = 0
        for service_id in service_ids:
            service = service_map[service_id]
            if service["status"] != "active":
                raise ValueError(f"Dịch vụ '{service['name']}' đã ngừng kinh doanh.")
            duration = int(service["duration_minutes"] or 0)
            price = float(service["price"] or 0)
            if duration <= 0:
                raise ValueError(f"Thời lượng dịch vụ '{service['name']}' không hợp lệ.")
            if not math.isfinite(price) or price < 0:
                raise ValueError(f"Giá dịch vụ '{service['name']}' không hợp lệ.")
            total_duration += duration

        end_dt = start_dt + timedelta(minutes=total_duration)
        if end_dt.date() != appointment_day:
            raise ValueError("Lịch hẹn vượt sang ngày hôm sau. Hãy chọn giờ bắt đầu khác.")
        calculated_end_time = end_dt.strftime("%H:%M")

        existing = conn.execute(
            """
            SELECT a.id, a.start_time, a.end_time,
                   COALESCE(SUM(COALESCE(s.duration_minutes, 0) * COALESCE(aps.quantity, 1)), 0) AS duration_minutes
            FROM appointments a
            LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
            LEFT JOIN services s ON s.id = aps.service_id
            WHERE a.barber_id = ? AND a.appointment_date = ?
              AND a.status != 'Cancelled'
              AND a.status != 'Cancel Requested'
            GROUP BY a.id
            """,
            (barber_id, appointment_day.isoformat()),
        ).fetchall()

        for old in existing:
            old_start = datetime.combine(appointment_day, parse_time(old["start_time"]))
            if old["end_time"]:
                old_end_time = parse_time(old["end_time"])
                old_end = datetime.combine(appointment_day, old_end_time)
            else:
                old_end = old_start
            if old_end <= old_start:
                old_duration = int(old["duration_minutes"] or 0) or 30
                old_end = old_start + timedelta(minutes=old_duration)
            if start_dt < old_end and end_dt > old_start:
                raise ValueError(
                    f"Thợ đã có lịch #{old['id']} trong khoảng giờ này. Hãy chọn giờ khác hoặc thợ khác."
                )

        cursor = conn.execute(
            """
            INSERT INTO appointments(
                customer_id, barber_id, appointment_date, start_time, end_time, status, note, user_id
            ) VALUES (?, ?, ?, ?, ?, 'Pending', ?, ?)
            """,
            (customer_id, barber_id, appointment_day.isoformat(),
             start_dt.strftime("%H:%M"), calculated_end_time, (note or "").strip() or None,
             user_id),
        )
        appointment_id = cursor.lastrowid

        for service_id in service_ids:
            service = service_map[service_id]
            conn.execute(
                "INSERT INTO appointment_services(appointment_id, service_id, quantity, price) VALUES (?, ?, 1, ?)",
                (appointment_id, service_id, float(service["price"])),
            )

        conn.commit()
        return appointment_id
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Không thể lưu lịch hẹn do dữ liệu không hợp lệ. Hãy kiểm tra lại các lựa chọn.") from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_appointments(date_filter=None, status=None, customer_id=None, barber_id=None):
    conn = get_db_connection()
    try:
        sql = """SELECT a.*, c.full_name customer_name, c.phone customer_phone,
                 COALESCE((SELECT customer_user.customer_code FROM users customer_user
                           WHERE customer_user.role = 'customer' AND customer_user.phone = c.phone
                           ORDER BY customer_user.id DESC LIMIT 1), c.customer_code) customer_code,
                 COALESCE(NULLIF(stylist_user.full_name, ''), b.full_name) barber_name,
                 COALESCE((SELECT SUM(aps.quantity * aps.price)
                           FROM appointment_services aps
                           WHERE aps.appointment_id = a.id), 0) amount,
                 COALESCE((SELECT GROUP_CONCAT(s.name, ', ')
                             FROM appointment_services aps
                             JOIN services s ON s.id = aps.service_id
                             WHERE aps.appointment_id = a.id), '') service_names,
                 COALESCE((SELECT GROUP_CONCAT(aps.service_id, ',')
                             FROM appointment_services aps
                             WHERE aps.appointment_id = a.id), '') service_ids
                 FROM appointments a
                 JOIN customers c ON c.id = a.customer_id
                 JOIN barbers b ON b.id = a.barber_id
                 LEFT JOIN users stylist_user ON stylist_user.id = b.user_id
                 WHERE 1 = 1"""
        params = []
        if date_filter:
            sql += " AND a.appointment_date = ?"
            params.append(date_filter)
        if status:
            sql += " AND a.status = ?"
            params.append(status)
        if customer_id:
            sql += " AND a.customer_id = ?"
            params.append(customer_id)
        if barber_id is not None:
            sql += " AND a.barber_id = ?"
            params.append(barber_id)
        sql += " ORDER BY a.id DESC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_appointment_details(appointment_id, service_ids, barber_id, appointment_date, start_time):
    """Atomically update an appointment's services, stylist, time, and derived end time."""
    try:
        appointment_id = int(appointment_id)
        barber_id = int(barber_id)
        service_ids = list(dict.fromkeys(int(value) for value in (service_ids or [])))
        day = datetime.strptime(str(appointment_date or "").strip(), "%Y-%m-%d").date()
        start_clock = datetime.strptime(str(start_time or "").strip(), "%H:%M").time()
    except (TypeError, ValueError) as exc:
        raise ValueError("Lịch hẹn, ngày giờ hoặc dịch vụ chưa hợp lệ.") from exc
    if not service_ids:
        raise ValueError("Hãy chọn ít nhất một dịch vụ.")
    if day < datetime.now().date():
        raise ValueError("Không thể cập nhật lịch hẹn về ngày đã qua.")
    start_dt = datetime.combine(day, start_clock)
    now = datetime.now().replace(second=0, microsecond=0)
    if day == now.date() and start_dt <= now:
        raise ValueError("Giờ hẹn phải nằm trong tương lai.")

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        appointment = conn.execute("SELECT status FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        if not appointment:
            raise ValueError("Không tìm thấy lịch hẹn.")
        if appointment["status"] in {"Completed", "Cancelled", "Cancel Requested"}:
            raise ValueError("Lịch đã hoàn thành hoặc đang bị hủy nên không thể sửa.")
        barber = conn.execute("SELECT status FROM barbers WHERE id = ?", (barber_id,)).fetchone()
        if not barber or barber["status"] != "active":
            raise ValueError("Không tìm thấy thợ đang hoạt động.")
        placeholders = ",".join("?" for _ in service_ids)
        services = conn.execute(
            f"SELECT id, name, duration_minutes, price, status FROM services WHERE id IN ({placeholders})",
            service_ids,
        ).fetchall()
        service_map = {int(row["id"]): row for row in services}
        if len(service_map) != len(service_ids):
            raise ValueError("Có dịch vụ không tồn tại.")
        duration = 0
        for service_id in service_ids:
            service = service_map[service_id]
            if service["status"] != "active":
                raise ValueError(f"Dịch vụ '{service['name']}' đã ngừng kinh doanh.")
            minutes = int(service["duration_minutes"] or 0)
            if minutes <= 0:
                raise ValueError(f"Thời lượng dịch vụ '{service['name']}' không hợp lệ.")
            duration += minutes
        end_dt = start_dt + timedelta(minutes=duration)
        if end_dt.date() != day:
            raise ValueError("Lịch hẹn vượt sang ngày hôm sau.")

        conflicts = conn.execute(
            """SELECT a.id, a.start_time, a.end_time,
                      COALESCE(SUM(COALESCE(s.duration_minutes, 0) * COALESCE(aps.quantity, 1)), 0) AS duration_minutes
               FROM appointments a
               LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
               LEFT JOIN services s ON s.id = aps.service_id
               WHERE a.barber_id = ? AND a.appointment_date = ? AND a.id != ?
                 AND a.status NOT IN ('Cancelled', 'Cancel Requested')
               GROUP BY a.id""",
            (barber_id, day.isoformat(), appointment_id),
        ).fetchall()
        for conflict in conflicts:
            conflict_start = datetime.strptime(conflict["start_time"], "%H:%M").time()
            conflict_end = datetime.strptime(conflict["end_time"], "%H:%M").time() if conflict["end_time"] else conflict_start
            if conflict_end <= conflict_start:
                conflict_end = (datetime.combine(day, conflict_start) + timedelta(minutes=int(conflict["duration_minutes"] or 30))).time()
            if start_dt < datetime.combine(day, conflict_end) and end_dt > datetime.combine(day, conflict_start):
                raise ValueError(f"Thợ đã có lịch #{conflict['id']} trong khoảng giờ này.")

        conn.execute(
            "UPDATE appointments SET barber_id = ?, appointment_date = ?, start_time = ?, end_time = ? WHERE id = ?",
            (barber_id, day.isoformat(), start_dt.strftime("%H:%M"), end_dt.strftime("%H:%M"), appointment_id),
        )
        conn.execute("DELETE FROM appointment_services WHERE appointment_id = ?", (appointment_id,))
        conn.executemany(
            "INSERT INTO appointment_services(appointment_id, service_id, quantity, price) VALUES (?, ?, 1, ?)",
            [(appointment_id, service_id, float(service_map[service_id]["price"])) for service_id in service_ids],
        )
        conn.commit()
        return sum(float(service_map[service_id]["price"] or 0) for service_id in service_ids)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def dashboard_latest_appointments(limit=5):
    """Load recent shared appointments with customer, stylist, and service data."""
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 5
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """SELECT a.id, a.appointment_date, a.start_time, a.status,
                      a.payment_status, a.payment_method,
                      c.full_name AS customer_name,
                      COALESCE((SELECT customer_user.customer_code FROM users customer_user
                                WHERE customer_user.role = 'customer' AND customer_user.phone = c.phone
                                ORDER BY customer_user.id DESC LIMIT 1), c.customer_code) AS customer_code,
                      COALESCE(NULLIF(u.full_name, ''), b.full_name) AS stylist_name,
                      GROUP_CONCAT(DISTINCT s.name) AS service_names,
                      COALESCE(SUM(aps.quantity * aps.price), 0) AS amount
               FROM appointments a
               JOIN customers c ON c.id = a.customer_id
               JOIN barbers b ON b.id = a.barber_id
               LEFT JOIN users u ON u.id = b.user_id
               LEFT JOIN appointment_services aps ON aps.appointment_id = a.id
               LEFT JOIN services s ON s.id = aps.service_id
               GROUP BY a.id
               ORDER BY a.id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_appointment_status(appointment_id, status):
    """Update a valid appointment state and record each service once when completed."""
    allowed_statuses = {"Pending", "Confirmed", "Completed", "Cancelled"}
    if status not in allowed_statuses:
        raise ValueError("Trạng thái lịch hẹn không hợp lệ.")
    try:
        appointment_id = int(appointment_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mã lịch hẹn không hợp lệ.") from exc

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        appt = conn.execute(
            "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
        if not appt:
            raise ValueError("Không tìm thấy lịch hẹn.")

        current_status = appt["status"]
        transitions = {
            "Pending": {"Pending", "Confirmed", "Cancelled"},
            "Confirmed": {"Confirmed", "Pending", "Completed", "Cancelled"},
            "Completed": {"Completed"},
            "Cancelled": {"Cancelled"},
        }
        if status not in transitions.get(current_status, set()):
            raise ValueError(
                "Luồng trạng thái không hợp lệ. Lịch chờ cần được xác nhận trước khi hoàn thành; "
                "lịch đã hoàn thành hoặc đã hủy không thể mở lại."
            )

        service_rows = conn.execute(
            "SELECT service_id FROM appointment_services WHERE appointment_id = ?",
            (appointment_id,),
        ).fetchall()
        if status == "Completed" and not service_rows:
            raise ValueError("Không thể hoàn thành lịch hẹn chưa có dịch vụ.")

        conn.execute(
            "UPDATE appointments SET status = ? WHERE id = ?", (status, appointment_id)
        )

        if status == "Completed":
            for service_row in service_rows:
                service_id = service_row["service_id"]
                exists = conn.execute(
                    "SELECT 1 FROM customer_history WHERE appointment_id = ? AND service_id = ? LIMIT 1",
                    (appointment_id, service_id),
                ).fetchone()
                if not exists:
                    conn.execute(
                        """
                        INSERT INTO customer_history(
                            customer_id, appointment_id, service_id, customer_note, barber_note, result
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (appt["customer_id"], appointment_id, service_id,
                         appt["note"], None, "Hoàn thành dịch vụ"),
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_invoice(appointment_id, discount=0, payment_method="Cash", payment_status="Paid"):
    """Create an invoice only for a completed appointment and validate payment data."""
    try:
        appointment_id = int(appointment_id)
        discount = float(discount or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mã lịch hẹn hoặc số tiền giảm giá không hợp lệ.") from exc

    allowed_methods = {"Cash", "Banking", "Card"}
    allowed_payment_statuses = {"Paid", "Unpaid"}
    if not math.isfinite(discount) or discount < 0:
        raise ValueError("Giảm giá phải là số hợp lệ và không âm.")
    if payment_method not in allowed_methods:
        raise ValueError("Phương thức thanh toán không hợp lệ.")
    if payment_status not in allowed_payment_statuses:
        raise ValueError("Trạng thái thanh toán không hợp lệ.")

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        appt = conn.execute(
            "SELECT id, customer_id, status FROM appointments WHERE id = ?", (appointment_id,)
        ).fetchone()
        if not appt:
            raise ValueError("Không tìm thấy lịch hẹn.")
        if appt["status"] != "Completed":
            raise ValueError("Chỉ được lập hóa đơn cho lịch hẹn đã hoàn thành.")
        existing_invoice = conn.execute(
            "SELECT id FROM invoices WHERE appointment_id = ?", (appointment_id,)
        ).fetchone()
        if existing_invoice:
            raise ValueError(f"Lịch hẹn này đã có hóa đơn #{existing_invoice['id']}.")

        items = conn.execute(
            """
            SELECT aps.service_id, aps.quantity, aps.price
            FROM appointment_services aps
            WHERE aps.appointment_id = ?
            """,
            (appointment_id,),
        ).fetchall()
        if not items:
            raise ValueError("Lịch hẹn chưa có dịch vụ, không thể lập hóa đơn.")

        subtotal = round(sum(float(item["price"]) * int(item["quantity"]) for item in items), 2)
        if discount > subtotal:
            raise ValueError("Số tiền giảm giá không được lớn hơn tổng tiền dịch vụ.")
        total = round(subtotal - discount, 2)

        cursor = conn.execute(
            """
            INSERT INTO invoices(
                appointment_id, customer_id, subtotal, discount, total,
                payment_method, payment_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (appointment_id, appt["customer_id"], subtotal, discount, total,
             payment_method, payment_status),
        )
        invoice_id = cursor.lastrowid
        for item in items:
            quantity = int(item["quantity"])
            unit_price = float(item["price"])
            conn.execute(
                """
                INSERT INTO invoice_items(invoice_id, service_id, quantity, unit_price, amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                (invoice_id, item["service_id"], quantity, unit_price,
                 round(unit_price * quantity, 2)),
            )
        conn.commit()
        return invoice_id
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Hóa đơn chưa được tạo. Lịch hẹn có thể đã có hóa đơn hoặc dữ liệu không hợp lệ.") from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_billable_appointments():
    """Return completed appointments which do not yet have an invoice."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT a.id, a.appointment_date, a.start_time, a.end_time,
                   c.full_name AS customer_name, b.full_name AS barber_name,
                   COALESCE((
                       SELECT SUM(aps.quantity * aps.price)
                       FROM appointment_services aps
                       WHERE aps.appointment_id = a.id
                   ), 0) AS amount
            FROM appointments a
            JOIN customers c ON c.id = a.customer_id
            JOIN barbers b ON b.id = a.barber_id
            LEFT JOIN invoices i ON i.appointment_id = a.id
            WHERE a.status = 'Completed' AND i.id IS NULL
            ORDER BY a.appointment_date DESC, a.start_time DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def mark_invoice_paid(invoice_id):
    """Mark an existing unpaid invoice as paid; do not alter already-paid invoices."""
    try:
        invoice_id = int(invoice_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mã hóa đơn không hợp lệ.") from exc
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        invoice = conn.execute(
            "SELECT id, payment_status FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if not invoice:
            raise ValueError("Không tìm thấy hóa đơn.")
        if invoice["payment_status"] == "Paid":
            raise ValueError("Hóa đơn này đã được thanh toán.")
        conn.execute(
            "UPDATE invoices SET payment_status = 'Paid' WHERE id = ?", (invoice_id,)
        )
        conn.commit()
        return invoice_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_invoice(invoice_id):
    conn = get_db_connection()
    try:
        cursor = conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        if cursor.rowcount == 0:
            raise ValueError("Không tìm thấy hóa đơn.")
        conn.commit()
    finally:
        conn.close()


def list_invoices():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT i.*, c.full_name AS customer_name,
                   a.appointment_date, a.start_time, a.end_time
            FROM invoices i
            JOIN customers c ON c.id = i.customer_id
            JOIN appointments a ON a.id = i.appointment_id
            ORDER BY i.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def customer_history(customer_id):
    conn=get_db_connection(); rows=conn.execute("""SELECT h.*, s.name service_name, a.appointment_date FROM customer_history h LEFT JOIN services s ON s.id=h.service_id LEFT JOIN appointments a ON a.id=h.appointment_id WHERE h.customer_id=? ORDER BY h.created_at DESC""",(customer_id,)).fetchall(); conn.close(); return [dict(r) for r in rows]


def search_history(q=""):
    conn=get_db_connection()
    if q:
        rows=conn.execute("""SELECT h.*, c.full_name customer_name, COALESCE((SELECT u.customer_code FROM users u WHERE u.role='customer' AND u.phone=c.phone ORDER BY u.id DESC LIMIT 1), c.customer_code) customer_code, s.name service_name FROM customer_history h JOIN customers c ON c.id=h.customer_id LEFT JOIN services s ON s.id=h.service_id WHERE c.full_name LIKE ? OR s.name LIKE ? OR h.hair_style LIKE ? OR h.hair_color LIKE ? ORDER BY h.created_at DESC""",(f"%{q}%",f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    else:
        rows=conn.execute("""SELECT h.*, c.full_name customer_name, COALESCE((SELECT u.customer_code FROM users u WHERE u.role='customer' AND u.phone=c.phone ORDER BY u.id DESC LIMIT 1), c.customer_code) customer_code, s.name service_name FROM customer_history h JOIN customers c ON c.id=h.customer_id LEFT JOIN services s ON s.id=h.service_id ORDER BY h.created_at DESC""").fetchall()
    conn.close(); return [dict(r) for r in rows]


def popular_services(limit=5):
    try:
        limit = max(1, min(int(limit), 20))
    except (TypeError, ValueError):
        limit = 5
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT s.name, SUM(aps.quantity) AS count
            FROM appointment_services aps
            JOIN services s ON s.id = aps.service_id
            JOIN appointments a ON a.id = aps.appointment_id
            WHERE a.status != 'Cancelled'
            GROUP BY s.id, s.name
            ORDER BY count DESC, s.name ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_ai_chat(user_id, message, response, mode):
    conn=get_db_connection(); conn.execute("INSERT INTO ai_chat_history(user_id,message,response,mode) VALUES (?,?,?,?)",(user_id,message,response,mode)); conn.commit(); conn.close()


def save_customer_chat(customer_id, user_id, message, ai_response):
    conn = get_db_connection()
    try:
        conn.execute(
            """INSERT INTO chat_history(customer_id, user_id, message, ai_response)
               VALUES (?, ?, ?, ?)""",
            (customer_id, user_id, message, ai_response),
        )
        conn.commit()
    finally:
        conn.close()


def customer_chat_history(customer_id, limit=None):
    conn = get_db_connection()
    try:
        sql = """SELECT h.*, u.full_name AS user_name, u.username
                 FROM chat_history h
                 LEFT JOIN users u ON u.id = h.user_id
                 WHERE h.customer_id = ?
                 ORDER BY h.id ASC"""
        params = [customer_id]
        if limit is not None:
            try:
                limit = max(1, min(int(limit), 100))
            except (TypeError, ValueError):
                limit = 20
            sql = sql.replace("ORDER BY h.id ASC", "ORDER BY h.id DESC LIMIT ?")
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in reversed(rows)]
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def customer_recommendation_context(customer_id):
    conn = get_db_connection()
    try:
        favorite_services = conn.execute(
            """SELECT s.name, SUM(aps.quantity) AS bookings,
                      MAX(a.appointment_date) AS last_date
               FROM appointments a
               JOIN appointment_services aps ON aps.appointment_id = a.id
               JOIN services s ON s.id = aps.service_id
               WHERE a.customer_id = ? AND a.status != 'Cancelled'
               GROUP BY s.id, s.name
               ORDER BY bookings DESC, last_date DESC
               LIMIT 5""",
            (customer_id,),
        ).fetchall()
        latest_visit = conn.execute(
            """SELECT MAX(appointment_date) FROM appointments
               WHERE customer_id = ? AND status = 'Completed'""",
            (customer_id,),
        ).fetchone()[0]
        return {
            "favorite_services": [dict(row) for row in favorite_services],
            "latest_visit": latest_visit,
            "chat_history": customer_chat_history(customer_id, limit=10),
        }
    finally:
        conn.close()


def dashboard_notification_data(limit=5):
    conn = get_db_connection()
    try:
        pending_count = conn.execute(
            """SELECT COUNT(*) FROM appointments
               WHERE status IN ('Pending', 'Cancel Requested')
                  OR payment_status = 'Pending Verification'"""
        ).fetchone()[0]
        return {
            "count": int(pending_count or 0),
            "appointments": dashboard_latest_appointments(limit),
        }
    finally:
        conn.close()
