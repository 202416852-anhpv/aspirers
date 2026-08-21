import sys

# ⚠️ Fix tận gốc 1 bug thật phát hiện qua test: nhiều print() trong compliance_checker/*.py
# (agents.py/csv_batch.py/trademark_resolver.py/knowledge_loader.py) dùng emoji (⚠️/❌/⏳) làm
# tiền tố log lỗi — trên Windows, khi chạy `python main.py` bình thường (không set
# PYTHONIOENCODING), stdout mặc định là codepage cp1252, KHÔNG encode được các ký tự này.
# Hậu quả: print() TỰ NÓ ném UnicodeEncodeError, NUỐT MẤT thông báo lỗi gốc thật (row batch
# hiện "charmap codec can't encode..." thay vì lý do thật khiến LLM/parse lỗi) — cực kỳ khó
# debug vì tưởng đâu app chạy đúng nhưng log vô dụng. Reconfigure stdout/stderr sang UTF-8
# NGAY tại điểm khởi động app, sửa 1 chỗ áp dụng cho toàn bộ log thay vì sửa rải rác từng print().
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # môi trường không hỗ trợ reconfigure (hiếm) -> bỏ qua, không chặn app khởi động

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings

# BUP-02: AI Design Compliance Checker — toàn bộ app hiện tại chỉ phục vụ đề bài này.
# Hệ chat/marketing-copy cũ (audit bài viết/campaign/gen video-ảnh) đã được archive vào
# _archive_old_system/ (không còn import/route nào trỏ tới nó) — xem docs.md.
# (2026-08-21) main.py giờ CHỈ lo app bootstrap (CORS, startup check, include_router) —
# 4 route thật + logic handler đã chuyển sang compliance_checker/api/routes.py, phần còn
# lại của compliance_checker/ chia thành engine/ (agents/black_box/opencv/trademark) và
# ingestion/ (file_loader/pdf_processor/link_normalizer/csv_batch) — xem docs.md mục 9.
from compliance_checker.api.routes import router as compliance_router

app = FastAPI(title="BUP-02 AI Design Compliance Checker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # Lưu ý: "*" + allow_credentials=True là tổ hợp không hợp lệ theo chuẩn CORS
    # (trình duyệt sẽ tự chặn) — app này chưa dùng cookie/session nên để False.
    # Nếu sau này thêm auth qua cookie, phải đổi allow_origins sang domain cụ thể.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _warn_if_missing_api_key() -> None:
    """
    Cảnh báo sớm ngay lúc khởi động nếu .env chưa cấu hình API key thật, thay vì để
    lỗi âm thầm rơi vào fallback report/message chung chung ở lần gọi LLM đầu tiên.
    """
    settings = get_settings()
    if not settings.gemini_api_key or settings.gemini_api_key.strip() in ("", "----"):
        print("⚠️  [CONFIG WARNING] gemini_api_key chưa được cấu hình trong .env (đang là placeholder). "
              "Mọi lệnh gọi LLM sẽ lỗi cho đến khi bạn set key thật.")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# =====================================================================
# BUP-02: AI Design Compliance Checker — 3 cách nhập bắt buộc theo brief: upload file /
# import link / import CSV batch — 4 route thật (định nghĩa đầy đủ ở compliance_checker/
# api/routes.py, cùng đổ vào chung compliance_checker/orchestrator.py). Xem docs.md mục
# 1-4 để biết gửi gì/nhận gì.
# =====================================================================

app.include_router(compliance_router)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=(settings.environment == "development"),
    )
