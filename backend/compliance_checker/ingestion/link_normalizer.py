"""
compliance_checker/ingestion/link_normalizer.py — normalize_url_to_bytes: biến bất kỳ URL nào
(Google Drive / Dropbox / S3 / direct URL) thành bytes THÔ tải về (ảnh, PDF, hay PSD đều được
— module này KHÔNG quan tâm/không cần biết nội dung là gì, chỉ lo đúng 1 việc: viết lại URL
cho đúng dạng tải trực tiếp rồi fetch). Đây là lớp adapter MỎNG duy nhất — sau bước này,
orchestrator.py tự nhận diện loại file thật (DesignFileLoader.sniff_extension) rồi mọi nguồn
(dù đến từ Drive/Dropbox/direct) hội tụ về CÙNG 1 pipeline như file upload.

pip install httpx
"""

import re
from urllib.parse import urlparse, parse_qs

import httpx

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_UA_HEADERS = {"User-Agent": "Mozilla/5.0 (compliance-checker/1.0)"}

_GDRIVE_ID_PATTERNS = [
    re.compile(r"/d/([a-zA-Z0-9_-]+)"),           # .../file/d/{id}/view
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),        # ...?id={id}
]


def _extract_gdrive_file_id(url: str) -> "str | None":
    for pattern in _GDRIVE_ID_PATTERNS:
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


def _classify_and_rewrite(url: str) -> str:
    """
    Trả về URL đã chuẩn hoá để fetch trực tiếp được — KHÔNG tự fetch ở đây (tách rõ 2 việc:
    "biết cách viết lại URL" và "thực sự tải file", dễ test riêng từng phần).
    """
    host = urlparse(url).netloc.lower()

    if "drive.google.com" in host:
        file_id = _extract_gdrive_file_id(url)
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}"
        return url  # không tách được id -> để nguyên, thử fetch thẳng (có thể vẫn fail, chấp nhận được)

    if "docs.google.com" in host and "/spreadsheets/" in url:
        # (2026-08-21) Google Sheets — KHÁC hẳn Drive (file tĩnh): URL "edit" mặc định trả về
        # HTML app 200-300KB (đã verify thật), KHÔNG phải data. Viết lại về export CSV của
        # ĐÚNG sheet (gid) đang xem — verify thật: link mẫu BGK
        # (docs.google.com/spreadsheets/d/.../edit?gid=256492005) rewrite đúng cách này trả về
        # CHÍNH XÁC 30 dòng data thật khớp design_samples_template.xlsx.
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
        if m:
            sheet_id = m.group(1)
            gid_match = re.search(r"[?&#]gid=([0-9]+)", url)
            gid = gid_match.group(1) if gid_match else "0"  # không có gid -> sheet đầu tiên
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        return url  # không tách được sheet id -> để nguyên, thử fetch thẳng (chấp nhận có thể fail)

    if "dropbox.com" in host:
        if "dl=0" in url:
            return url.replace("dl=0", "dl=1")
        if "dl=1" not in url:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}dl=1"
        return url

    # S3 / direct image URL / mọi URL khác — dùng thẳng, không rewrite
    return url


async def normalize_url_to_bytes(url: str) -> bytes:
    """
    Luôn follow_redirects=True (bắt buộc cho GDrive/Dropbox — cả 2 đều redirect trước khi
    ra file thật). Raise lỗi RÕ RÀNG (không nuốt exception ở tầng này) — orchestrator là nơi
    catch để đánh dấu ERROR cho đúng row, giữ nguyên nguyên tắc row-level fault isolation.

    ⚠️ Giới hạn đã biết (chấp nhận được cho hackathon): file Google Drive lớn (~>25MB) có
    thể trả về 1 trang HTML cảnh báo virus-scan thay vì file thật — trường hợp này sẽ khiến
    response không phải bytes ảnh hợp lệ, lỗi sẽ lộ ra ở bước decode ảnh phía sau (file_loader.py),
    KHÔNG cố xử lý thêm token xác nhận virus-scan ở bản này (ROI thấp so với công sức).
    """
    fetch_url = _classify_and_rewrite(url)
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True, headers=_UA_HEADERS) as client:
        resp = await client.get(fetch_url)
        resp.raise_for_status()
        return resp.content


def classify_link_type(url: str) -> str:
    """Tiện ích cho batch report / debug: biết link thuộc loại nào trước khi fetch."""
    host = urlparse(url).netloc.lower()
    if "drive.google.com" in host:
        return "google_drive"
    if "docs.google.com" in host and "/spreadsheets/" in url:
        return "google_sheets"
    if "dropbox.com" in host:
        return "dropbox"
    if "amazonaws.com" in host or "s3." in host:
        return "s3"
    if any(url.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        return "direct_image"
    return "unknown_marketplace_or_other"
