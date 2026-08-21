from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    """
    Quản lý tập trung toàn bộ cấu hình hệ thống và API Keys.
    Các giá trị mặc định sẽ bị ghi đè nếu tìm thấy biến tương ứng trong file .env
    """
    # 1. Kệ đoạn này đi cứ biết là mình đang dùng claude haiku rồi
    gemini_api_key: str = "----"
    gemini_model: str = "llama-3.1-8b-instant"
    gemini_base_url: str = "https://api.groq.com/openai/v1"

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