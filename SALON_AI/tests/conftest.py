import os
import sys
import tempfile
from pathlib import Path
import pytest

# Thiết lập đường dẫn thư mục SALON_AI vào sys.path
TESTS_DIR = Path(__file__).resolve().parent
SALON_AI_DIR = TESTS_DIR.parent
if str(SALON_AI_DIR) not in sys.path:
    sys.path.insert(0, str(SALON_AI_DIR))

# Tạo thư mục tạm thời và tệp cơ sở dữ liệu SQLite riêng cho test
_TEMP_DIR = tempfile.TemporaryDirectory(prefix="salon_ai_test_")
_TEST_DB_PATH = Path(_TEMP_DIR.name) / "test_salon_system.db"

# Đặt biến môi trường test TRƯỚC KHI import app hoặc database
os.environ["SALON_TESTING"] = "1"
os.environ["SALON_DATABASE_PATH"] = str(_TEST_DB_PATH)

import database
import app as flask_app_module

# Đảm bảo database module trỏ vào database test cô lập
database.set_db_path(_TEST_DB_PATH)

# Khởi tạo bảng và dữ liệu mẫu trên database test cô lập
database.init_db()


def pytest_sessionfinish(session, exitstatus):
    """Dọn dẹp thư mục tạm sau khi kết thúc phiên chạy kiểm thử."""
    try:
        _TEMP_DIR.cleanup()
    except Exception:
        pass


@pytest.fixture(scope="session")
def test_db_path():
    """Trả về đường dẫn tới database SQLite tạm thời của test."""
    return _TEST_DB_PATH


@pytest.fixture
def app():
    """Cung cấp Flask app đã bật chế độ TESTING."""
    flask_app = flask_app_module.app
    flask_app.config.update({
        "TESTING": True,
    })
    yield flask_app


@pytest.fixture
def client(app):
    """Cung cấp TestClient cho Flask app."""
    return app.test_client()
