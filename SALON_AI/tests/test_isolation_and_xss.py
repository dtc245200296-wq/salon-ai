import os
from pathlib import Path
import pytest
import database


def test_database_is_isolated_from_production(test_db_path):
    """Xác minh rằng môi trường test đang sử dụng database tạm riêng, không phải salon_system.db."""
    active_path = database.get_current_db_path()
    
    # 1. Database hiện tại phải là file test tạm thời
    assert active_path.resolve() == test_db_path.resolve()
    assert active_path.exists()

    # 2. Tuyệt đối không trùng với đường dẫn database thật
    assert active_path.resolve() != database.DEFAULT_DB_PATH.resolve()

    # 3. Kiểm tra trực tiếp từ SQLite PRAGMA để chắc chắn kết nối đang mở đúng file tạm
    conn = database.get_db_connection()
    try:
        db_list = conn.execute("PRAGMA database_list;").fetchall()
        # db_list gồm (seq, name, file)
        opened_file = Path(db_list[0]["file"]).resolve()
        assert opened_file == test_db_path.resolve()
        assert opened_file != database.DEFAULT_DB_PATH.resolve()
    finally:
        conn.close()


def test_safety_guard_blocks_connection_to_production_db(test_db_path):
    """Xác minh rằng chốt an toàn sẽ ngay lập tức ngắt và ném lỗi nếu ai đó cố tình trỏ về database thật."""
    assert os.getenv("SALON_TESTING") == "1"
    
    # Tạm thời ép đường dẫn về file database thật
    database.set_db_path(database.DEFAULT_DB_PATH)
    try:
        with pytest.raises(RuntimeError) as exc_info:
            database.get_db_connection()
        assert "SAFETY VIOLATION" in str(exc_info.value)
    finally:
        # Khôi phục ngay lại database test
        database.set_db_path(test_db_path)


def test_chat_template_has_no_inner_html_vulnerabilities():
    """Xác minh file chat.html không còn chứa đoạn mã gán innerHTML gây lỗi XSS."""
    chat_template_path = Path(__file__).resolve().parent.parent / "templates" / "chat.html"
    assert chat_template_path.exists()

    content = chat_template_path.read_text(encoding="utf-8")

    # Không được có bất kỳ lệnh gán innerHTML nào trong kịch bản gửi tin nhắn
    assert "box.innerHTML +=" not in content
    assert "box.innerHTML=" not in content
    assert ".innerHTML" not in content

    # Phải có hàm xử lý DOM an toàn
    assert "appendBotMessage" in content
    assert "textContent" in content
    assert "document.createTextNode" in content
    assert "^https?:\\/\\/" in content  # Kiểm tra lọc giao thức URL an toàn
