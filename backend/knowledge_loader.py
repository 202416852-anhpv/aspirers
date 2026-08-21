import os


def load_trend_context(country: str) -> str:
    """
    Mở rộng cho compliance_checker (BUP-02, xem CLAUDE.md mục 5) — Y HỆT pattern
    load_policy_context ở trên: fallback rỗng, KHÔNG raise. Dùng bởi
    compliance_checker/agents.py::run_agent4_market_suggestion() để tiêm ngữ cảnh xu hướng
    thị trường (dùng CHUNG cho mọi platform, khác load_policy_context vốn theo từng platform
    riêng — lý do tách xem compliance_checker/data/trends/us_trends.md).

    Đường dẫn trỏ vào compliance_checker/data/trends/ (không phải knowledge_base/trends/ ở
    mục 5 bản nháp ban đầu) — khớp đúng cấu trúc thư mục cuối cùng đã chốt trong CLAUDE.md
    ("Ngoại lệ cố định: compliance_checker/data/").
    """
    country_clean = (country or "us").lower().strip()
    file_path = os.path.join("compliance_checker", "data", "trends", f"{country_clean}_trends.md")

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception as e:
            print(f"⚠️ [KnowledgeLoader] Lỗi đọc tệp {file_path}: {e}")

    return ""