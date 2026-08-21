from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    """
    Quản lý tập trung toàn bộ cấu hình hệ thống và API Keys.
    Các giá trị mặc định sẽ bị ghi đè nếu tìm thấy biến tương ứng trong file .env
    """
    # 1. Kệ đoạn này đi cứ biết là mình đang dùng claude haiku rồi
    # ⚠️ (2026-08-21) Default gemini_model/gemini_base_url TỪNG là của Groq/Llama (sai hoàn
    # toàn với hệ thống thật đang dùng Claude Haiku 4.5 qua Anthropic) — nếu deploy (Render)
    # mà quên set 2 biến này, app sẽ ÂM THẦM gọi nhầm provider, không có cảnh báo nào (khác
    # gemini_api_key đã có check ở main.py::_warn_if_missing_api_key). Sửa default về ĐÚNG giá
    # trị thật (khớp example_env.txt) — thiếu biến giờ chỉ còn thiếu API key (đã có cảnh báo),
    # không còn thiếu ĐÚNG PROVIDER nữa.
    gemini_api_key: str = "----"
    gemini_model: str = "claude-haiku-4-5-20251001"
    gemini_base_url: str = "https://api.anthropic.com/v1/"

    # 2. Cấu hình Server FastAPI Gateway
    port: int = 8000
    environment: str = "development"

    # Nạp cấu hình từ file .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Bỏ qua nếu trong .env có các biến thừa khác
    )

@lru_cache
def get_settings() -> Settings:
    """
    Hàm Singleton sử dụng lru_cache để chỉ đọc file .env một lần duy nhất,
    giúp tối ưu hiệu năng khi gọi ở nhiều nơi.
    """
    return Settings()