import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Nạp biến môi trường từ file .env
load_dotenv()

# ============================================================
# Gemini SDK mới: google-genai
# ============================================================
use_new_sdk = False
try:
    from google import genai
    from google.genai import types
    use_new_sdk = True
except Exception:
    genai = None
    types = None

# ============================================================
# Gemini SDK cũ: google-generativeai (fallback)
# ============================================================
legacy_genai = None
if not use_new_sdk:
    try:
        import google.generativeai as legacy_genai
    except Exception:
        legacy_genai = None

# ============================================================
# DuckDuckGo Search fallback
# ============================================================
try:
    from ddgs import DDGS
except Exception:
    DDGS = None


BASE_DIR = Path(__file__).resolve().parent
SERVICES_DIR = BASE_DIR / "data" / "services"

# Số lần thử lại khi Gemini trả lỗi tạm thời.
MAX_RETRIES = 2
RETRY_DELAYS = (1.5, 3.0)

# Model fallback chỉ được dùng khi lỗi là lỗi tạm thời như 503/429.
# gemini-3.6-flash vẫn là model mặc định theo .env của bạn.
DEFAULT_FALLBACK_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
]


def _service_text(services):
    return "\n".join(
        f"- {s['name']} | {s.get('category', '')} | "
        f"{s.get('duration_minutes', 0)} phút | "
        f"{float(s.get('price', 0)):,.0f} VNĐ | "
        f"{s.get('description', '')}"
        for s in services
    ) or "Chưa có dịch vụ nào."


def _history_text(history):
    return "\n".join(
        f"- {h.get('appointment_date', '')}: "
        f"{h.get('service_name', '')} | "
        f"kiểu: {h.get('hair_style', '')} | "
        f"màu: {h.get('hair_color', '')} | "
        f"ghi chú: {h.get('customer_note', '')} | "
        f"kết quả: {h.get('result', '')}"
        for h in history
    ) or "Chưa có lịch sử dịch vụ."


def _parse_json(text, fallback):
    """Parse JSON kể cả khi model bọc JSON trong ```json ... ``` ."""
    if not text:
        return fallback

    cleaned = text.strip()

    # Bỏ markdown code fence nếu có.
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Tìm object JSON đầu tiên trong nội dung.
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return fallback

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback


def _normalize_model(raw_model):
    """Chuẩn hóa tên model nhưng không tự ý đổi model hợp lệ do người dùng cấu hình."""
    model = (raw_model or "").strip()
    model = model.replace("models/", "").replace('"', "").replace("'", "").strip()
    return model or "gemini-3.6-flash"


def _model_candidates(use_search=False):
    env_name = "GEMINI_WEB_MODEL" if use_search else "GEMINI_MODEL"
    primary = _normalize_model(os.getenv(env_name, "gemini-3.6-flash"))

    # Cho phép người dùng tự định nghĩa fallback trong .env.
    raw_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "")
    if raw_fallbacks:
        configured = [
            _normalize_model(item)
            for item in raw_fallbacks.split(",")
            if item.strip()
        ]
    else:
        configured = DEFAULT_FALLBACK_MODELS

    candidates = []
    for model in [primary, *configured]:
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def _is_transient_gemini_error(exc):
    """503/429/quá tải là lỗi có thể thử lại hoặc chuyển model."""
    message = str(exc).upper()
    transient_markers = (
        "503",
        "UNAVAILABLE",
        "429",
        "RESOURCE_EXHAUSTED",
        "TOO MANY REQUESTS",
        "HIGH DEMAND",
        "OVERLOADED",
        "RATE LIMIT",
        "TRY AGAIN LATER",
        "INTERNAL SERVER ERROR",
        "500",
    )
    return any(marker in message for marker in transient_markers)


def _extract_grounding_sources(result):
    sources = []

    # Một số phiên bản SDK đặt grounding_metadata ở response,
    # một số trường hợp truy cập được thông qua candidate.
    grounding = getattr(result, "grounding_metadata", None)

    if grounding is None:
        candidates = getattr(result, "candidates", None) or []
        if candidates:
            grounding = getattr(candidates[0], "grounding_metadata", None)

    if grounding:
        chunks = getattr(grounding, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if not web:
                continue

            uri = getattr(web, "uri", None)
            title = getattr(web, "title", None)
            if uri:
                sources.append({
                    "title": title or uri,
                    "url": uri,
                })

    # Loại trùng URL.
    unique = []
    seen = set()
    for item in sources:
        url = item.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(item)
    return unique


def _generate_with_new_sdk(client, model, prompt, use_search=False, system_instruction=None):
    config_args = {}

    if system_instruction and types:
        config_args["system_instruction"] = system_instruction

    if use_search and types:
        # Google Search grounding theo SDK google-genai mới.
        config_args["tools"] = [
            types.Tool(google_search=types.GoogleSearch())
        ]

    config = types.GenerateContentConfig(**config_args) if config_args else None

    if config:
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )

    return client.models.generate_content(
        model=model,
        contents=prompt,
    )


def _gemini_text(prompt, use_search=False, system_instruction=None):
    """
    Gọi Gemini với:
    - retry khi 503/429;
    - tự chuyển model khi model hiện tại đang quá tải;
    - giữ thông báo lỗi cụ thể thay vì luôn bảo người dùng kiểm tra API key.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return None, "Lỗi: Không tìm thấy GEMINI_API_KEY trong file .env", []

    models = _model_candidates(use_search=use_search)
    last_error = None

    # --------------------------------------------------------
    # SDK mới
    # --------------------------------------------------------
    if use_new_sdk and genai:
        try:
            client = genai.Client(api_key=api_key)
        except Exception as exc:
            return None, f"Lỗi khởi tạo Gemini SDK: {exc}", []

        for model_index, model in enumerate(models):
            for attempt in range(MAX_RETRIES + 1):
                try:
                    result = _generate_with_new_sdk(
                        client=client,
                        model=model,
                        prompt=prompt,
                        use_search=use_search,
                        system_instruction=system_instruction,
                    )

                    text = (getattr(result, "text", None) or "").strip()
                    sources = _extract_grounding_sources(result)

                    if text:
                        # mode vẫn là gemini; nếu dùng fallback model thì ghi rõ.
                        mode = "gemini" if model_index == 0 else f"gemini_fallback:{model}"
                        return text, mode, sources

                    last_error = "Gemini trả về phản hồi rỗng."
                    break

                except Exception as exc:
                    last_error = str(exc)

                    # Lỗi không mang tính tạm thời: không thử vô ích.
                    if not _is_transient_gemini_error(exc):
                        return None, f"Lỗi Gemini (SDK mới, model {model}): {exc}", []

                    # Còn lượt retry -> chờ rồi thử lại cùng model.
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                        continue

                    # Hết retry -> chuyển model kế tiếp.
                    break

        return None, (
            "Lỗi Gemini: các model hiện được cấu hình đều đang tạm thời quá tải "
            f"hoặc không khả dụng. Chi tiết cuối: {last_error}"
        ), []

    # --------------------------------------------------------
    # SDK cũ: chỉ dùng nếu máy chưa có google-genai
    # --------------------------------------------------------
    if legacy_genai:
        try:
            legacy_genai.configure(api_key=api_key)

            for model_index, model in enumerate(models):
                for attempt in range(MAX_RETRIES + 1):
                    try:
                        kwargs = {"model_name": model}
                        if system_instruction:
                            kwargs["system_instruction"] = system_instruction

                        gen_model = legacy_genai.GenerativeModel(**kwargs)
                        res = gen_model.generate_content(prompt)
                        text = (getattr(res, "text", None) or "").strip()

                        if text:
                            mode = "gemini_legacy" if model_index == 0 else f"gemini_legacy_fallback:{model}"
                            return text, mode, []

                        last_error = "Gemini trả về phản hồi rỗng."
                        break

                    except Exception as exc:
                        last_error = str(exc)
                        if not _is_transient_gemini_error(exc):
                            return None, f"Lỗi Gemini (SDK cũ, model {model}): {exc}", []

                        if attempt < MAX_RETRIES:
                            time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
                            continue
                        break

            return None, (
                "Lỗi Gemini: các model hiện được cấu hình đều đang tạm thời quá tải "
                f"hoặc không khả dụng. Chi tiết cuối: {last_error}"
            ), []

        except Exception as exc:
            return None, f"Lỗi Gemini (SDK cũ): {exc}", []

    return None, (
        "Lỗi: Chưa cài thư viện google-genai hoặc google-generativeai trong môi trường Python"
    ), []


def _web_fallback(query):
    if DDGS is None:
        return None, "ddgs_unavailable", []

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return None, "no_web_results", []

        lines = ["Kết quả tìm kiếm Internet:", ""]
        sources = []

        for i, item in enumerate(results, 1):
            title = item.get("title") or item.get("href") or f"Nguồn {i}"
            href = item.get("href") or item.get("url") or ""
            body = item.get("body") or item.get("snippet") or ""
            lines.append(f"{i}. {title}\n{body}\n{href}\n")

            if href:
                sources.append({"title": title, "url": href})

        return "\n".join(lines).strip(), "web_fallback", sources

    except Exception as exc:
        return None, f"web_error:{exc}", []


def _is_web_question(message):
    keywords = [
        "luật lao động",
        "pháp luật",
        "quy định mới",
        "quy định hiện hành",
        "năm 2026",
        "hiện nay",
        "mới nhất",
        "theo luật",
        "internet",
        "trên mạng",
    ]
    m = message.lower()
    return any(k in m for k in keywords)


def recommend_service(customer, history, services, customer_context=None):
    customer_context = customer_context or {}
    favorite_services = customer_context.get("favorite_services", [])
    favorite_text = "\n".join(
        f"- {item.get('name')}: {item.get('bookings', 0)} lượt; gần nhất {item.get('last_date') or 'chưa rõ'}"
        for item in favorite_services
    ) or "Chưa có dịch vụ được đặt trước đây."
    latest_visit = customer_context.get("latest_visit") or "Chưa có ca hoàn thành trước đây."
    chat_rows = customer_context.get("chat_history", [])
    chat_text = "\n".join(
        f"Khách: {row.get('message', '')}\nTrợ lý: {row.get('ai_response', '')}"
        for row in chat_rows[-8:]
    ) or "Chưa có lịch sử chat."
    prompt = f"""Bạn là trợ lý tư vấn salon tóc. Chỉ được đề xuất dịch vụ tồn tại trong danh sách.
KHÁCH HÀNG: {customer['full_name']}; ghi chú: {customer.get('note', '')}
LỊCH SỬ:
{_history_text(history)}
DỊCH VỤ ĐẶT NHIỀU NHẤT:
{favorite_text}
NGÀY LÀM GẦN NHẤT:
{latest_visit}
LỊCH SỬ CHAT AI:
{chat_text}
DỊCH VỤ HIỆN CÓ:
{_service_text(services)}
Trả về JSON gồm recommended_services, reason, warning."""

    text, mode, _ = _gemini_text(prompt, use_search=False)

    known_services = {service.get("name") for service in services}
    fallback_recommendations = [
        item.get("name") for item in favorite_services
        if item.get("name") in known_services
    ][:2]
    for service in services:
        if len(fallback_recommendations) >= 2:
            break
        if service.get("name") not in fallback_recommendations:
            fallback_recommendations.append(service.get("name"))
    fallback = {
        "recommended_services": fallback_recommendations,
        "reason": (
            "Ưu tiên các dịch vụ khách đã lựa chọn nhiều lần, kết hợp ngày làm gần nhất và lịch sử tư vấn."
            if favorite_services or latest_visit else "Gợi ý dựa trên danh sách dịch vụ hiện tại."
        ),
        "warning": "Nhân viên nên kiểm tra thực tế tóc trước khi thực hiện.",
        "mode": "rule_fallback",
    }

    # Gemini đôi khi trả lời văn bản thường thay vì JSON; giữ nguyên để giao diện
    # hiển thị đúng nội dung thay vì biến nó thành một chuỗi JSON khó đọc.
    parsed = _parse_json(text, None) if text else None
    result = parsed if isinstance(parsed, dict) else fallback
    if text and not isinstance(parsed, dict):
        result = {"reply": text, "recommended_services": [], "reason": "", "warning": ""}
    result["mode"] = mode
    return result


def generate_message(customer, history, services):
    prompt = f"""Viết một tin nhắn chăm sóc khách hàng ngắn, lịch sự cho salon tóc.
Khách: {customer['full_name']}
Lịch sử:
{_history_text(history)}
Dịch vụ:
{_service_text(services)}"""

    text, mode, _ = _gemini_text(prompt)
    reply = text or f"Chào {customer['full_name']}, salon rất vui được phục vụ bạn."
    return {"reply": reply, "mode": mode}


def summarize_customer(customer, history):
    prompt = f"""Tóm tắt lịch sử khách hàng salon trong 3-5 câu.
Khách: {customer['full_name']}
Lịch sử:
{_history_text(history)}"""

    text, mode, _ = _gemini_text(prompt)
    return {
        "summary": text or "Chưa có đủ lịch sử để tóm tắt.",
        "mode": mode,
    }


def chat_salon(message, context):
    services = context.get("services", [])
    if context.get("role") in {"admin", "receptionist", "staff"}:
        summary = context.get("admin_summary") or {}
        stylist_text = ", ".join(
            f"{item.get('full_name')} ({item.get('username')})"
            for item in summary.get("stylists", [])
        ) or "Chưa có dữ liệu stylist."
        system_instruction = (
            "Bạn là Trợ lý Quản lý Salon Đa năng cho HairStudio.\n"
            "DỮ LIỆU CSDL HIỆN TẠI TẠI SALON:\n"
            f"- Tổng khách hàng: {summary.get('total_customers', 0)}\n"
            f"- Lịch hẹn hôm nay: {summary.get('today_appointments', 0)} ca "
            f"({summary.get('pending_count', 0)} chờ xác nhận, "
            f"{summary.get('completed_count', 0)} đã xong)\n"
            f"- Tổng doanh thu hệ thống: {summary.get('total_revenue', 0):,.0f} VNĐ\n"
            f"- Đội ngũ Stylist: {stylist_text}\n\n"
            "QUY TẮC TRẢ LỜI:\n"
            "1. Nếu hỏi số liệu Salon, sử dụng đúng dữ liệu thực tế ở trên; trả lời ngắn gọn, chính xác.\n"
            "2. Được phép trả lời các câu hỏi khác về marketing, nội dung mạng xã hội, tính toán, nhân sự, email và kiến thức tổng hợp.\n"
            "3. Chuyên nghiệp, thông minh, đi thẳng vào vấn đề; trả lời bằng tiếng Việt."
        )
    else:
        system_instruction = (
            "Bạn là Trợ lý AI chuyên gia về tóc của Salon AI. Bạn CHỈ ĐƯỢC PHÉP tư vấn "
            "các chủ đề về tóc (kiểu tóc, chăm sóc tóc, nhuộm, uốn, dịch vụ salon). "
            "Nếu người dùng hỏi chủ đề ngoài ngành tóc, hãy từ chối nhẹ nhàng và hướng họ "
            "quay lại chủ đề làm đẹp tóc. Không trả lời câu hỏi ngoài phạm vi này, kể cả "
            "khi câu hỏi yêu cầu tra cứu Internet. Trả lời bằng tiếng Việt, không bịa giá "
            "hoặc dịch vụ ngoài danh sách salon."
        )
    conversation = []
    for item in (context.get("history") or [])[-8:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if isinstance(content, str) and content.strip():
            conversation.append({"role": item["role"], "content": " ".join(content.split())[:1000]})
    transcript = "\n".join(
        f"{'Khách' if item.get('role') == 'user' else 'Trợ lý'}: {item.get('content', '')}"
        for item in conversation
        if item.get("role") in {"user", "assistant"} and item.get("content")
    )
    customer = context.get("customer") or {}
    customer_profile = (
        f"Khách hàng đang được tư vấn: {customer.get('full_name')} "
        f"({customer.get('customer_code') or ''}), ghi chú: {customer.get('note') or 'không có'}"
        if customer else "Chưa chọn khách hàng cụ thể."
    )
    saved_chat = context.get("customer_chat_history", [])
    saved_transcript = "\n".join(
        f"Khách: {item.get('message', '')}\nTrợ lý: {item.get('ai_response', '')}"
        for item in saved_chat[-8:]
    ) or "Chưa có hội thoại lưu trước đó."
    prompt = (
        f"{system_instruction}\n\n{customer_profile}\n\n"
        f"LỊCH SỬ CHAT ĐÃ LƯU CỦA KHÁCH:\n{saved_transcript}\n\n"
        f"DỊCH VỤ SALON:\n{_service_text(services)}\n\n"
        f"HỘI THOẠI GẦN ĐÂY:\n{transcript or 'Chưa có.'}\n\n"
        f"CÂU HỎI MỚI:\n{message}"
    )
    text, mode, _ = _gemini_text(
        prompt,
        use_search=False,
        system_instruction=system_instruction,
    )
    if text:
        return {"reply": text, "mode": mode, "sources": [], "citations": []}
    return {
        "reply": "Hiện trợ lý AI chưa kết nối được. Bạn có thể thử lại sau ít phút.",
        "mode": mode,
        "sources": [],
        "citations": [],
    }


def advise_hairstyle(message, services, hair_condition="", style_request=""):
    """Give booking-time hair advice grounded in the salon's active services."""
    system_instruction = (
        "Bạn là trợ lý tư vấn kiểu tóc của salon. Trả lời bằng tiếng Việt, ngắn gọn, "
        "thân thiện; chỉ gợi ý dịch vụ có trong danh sách và không tự bịa giá hoặc thời lượng. "
        "Nếu khách mô tả tóc tẩy hoặc hư tổn, nhắc họ trao đổi với stylist trước khi làm."
    )
    prompt = (
        f"DỊCH VỤ SALON ĐANG CUNG CẤP:\n{_service_text(services)}\n\n"
        f"TÌNH TRẠNG TÓC: {hair_condition or 'chưa cung cấp'}\n"
        f"KIỂU/MÀU MONG MUỐN: {style_request or 'chưa cung cấp'}\n"
        f"CÂU HỎI: {message}"
    )
    text, mode, _ = _gemini_text(
        prompt,
        use_search=False,
        system_instruction=system_instruction,
    )
    if text:
        return {"reply": text, "mode": mode}
    suggestions = ", ".join(service["name"] for service in services[:3])
    return {
        "reply": (
            "Hiện trợ lý AI chưa kết nối được. Bạn có thể xem các dịch vụ đang có"
            + (f": {suggestions}." if suggestions else ".")
            + " Stylist sẽ tư vấn thêm sau khi kiểm tra tóc trực tiếp."
        ),
        "mode": "fallback",
    }
