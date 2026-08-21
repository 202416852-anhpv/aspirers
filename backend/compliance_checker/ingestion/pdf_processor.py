"""
compliance_checker/ingestion/pdf_processor.py — CHỈ lo nhánh PDF (digital-native vs scanned).

Dùng PyMuPDF (`fitz`) thay vì `pdf2image`: pure-Python, KHÔNG cần cài binary Poppler ở
tầng OS — quan trọng cho ràng buộc "cài đặt/chạy được trên máy giám khảo ≤10 phút".

Render TẤT CẢ các trang (không chỉ trang đầu) — quyết định sau khi thảo luận: PDF nhiều trang
mà chỉ xem trang 1 là rủi ro thật cho verdict (vi phạm có thể nằm ở bất kỳ trang nào). Giới hạn
_MAX_PAGES_TO_RENDER để tránh 1 PDF cực dài làm request Vision quá nặng/chậm — PDF vượt giới
hạn vẫn xử lý được, chỉ cảnh báo rõ số trang bị bỏ qua (xem orchestrator.py).

pip install pymupdf
"""

import base64
import io

try:
    import pymupdf as fitz  # PyMuPDF — tên import mới, tránh deprecation warning của `import fitz`
    _FITZ_AVAILABLE = True
except ImportError:
    try:
        import fitz  # bản PyMuPDF cũ hơn chưa có alias `pymupdf`
        _FITZ_AVAILABLE = True
    except ImportError:
        _FITZ_AVAILABLE = False

from PIL import Image

# Trần số trang thật sự render/gửi cho Vision trong 1 request — 10 trang là điểm cân bằng hợp
# lý giữa "đủ dùng cho hầu hết design portfolio/catalog thật" và "không làm request quá nặng"
# (mỗi trang ~144 DPI PNG, 10 ảnh/1 message vẫn trong giới hạn thực tế của Anthropic API).
_MAX_PAGES_TO_RENDER = 10


def detect_pdf_type(page) -> str:
    """
    "digital_native" nếu trang có text layer thật (PDF xuất từ Illustrator/Canva/Figma...),
    "scanned_flat" nếu trang chỉ là ảnh scan phẳng (không có text layer, hoặc quá ít).
    """
    try:
        text = page.get_text().strip()
        return "digital_native" if len(text) > 10 else "scanned_flat"
    except Exception:
        return "scanned_flat"


def _empty_error_result(error_msg: str) -> dict:
    return {
        "pdf_type": "error", "full_page_image_base64": None, "page_images_base64": [],
        "native_text": "", "all_pages_native_text": "", "text_blocks_with_bbox": [],
        "embedded_images": [], "total_pages": 0, "pages_rendered": 0, "error": error_msg,
    }


class PDFProcessor:
    """
    Render MỌI trang (tới giới hạn _MAX_PAGES_TO_RENDER) -> ảnh (fitz.Matrix(2,2) để nét,
    tương đương 144 DPI) -> dùng cho Vision, bất kể loại PDF gì. Nếu trang là digital_native,
    trích thêm text layer thật (có bbox pixel CHÍNH XÁC, gắn kèm số trang) để match trademark
    trực tiếp bằng Python, không cần Vision OCR lại.

    "pdf_type" tính theo trang ĐẦU TIÊN (đại diện cho cả file — hiếm khi 1 PDF trộn lẫn cả 2
    loại giữa các trang; nếu có, các trang scanned_flat vẫn được render ảnh bình thường, chỉ
    không có native_text/bbox riêng cho trang đó).
    """

    def __init__(self, render_scale: float = 2.0):
        self.render_scale = render_scale

    def process(self, pdf_path: str) -> dict:
        """
        Không bao giờ raise ra ngoài — mọi lỗi trả về dict với "error" field, orchestrator
        tự quyết định cách xử lý (đánh dấu ERROR cho đúng row trong batch, không sập cả batch).
        """
        if not _FITZ_AVAILABLE:
            return _empty_error_result("PyMuPDF (fitz) chưa được cài — chạy `pip install pymupdf` trước khi xử lý PDF.")
        try:
            doc = fitz.open(pdf_path)
            total_pages = doc.page_count
            if total_pages == 0:
                doc.close()
                return _empty_error_result("PDF không có trang nào.")

            pages_to_render = min(total_pages, _MAX_PAGES_TO_RENDER)
            matrix = fitz.Matrix(self.render_scale, self.render_scale)

            pdf_type = detect_pdf_type(doc[0])
            page_images_base64: list[str] = []
            native_text_parts: list[str] = []
            text_blocks_with_bbox: list[dict] = []

            for page_idx in range(pages_to_render):
                page = doc[page_idx]

                pix = page.get_pixmap(matrix=matrix)
                page_images_base64.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))

                page_type = detect_pdf_type(page)
                if page_type == "digital_native":
                    page_text = page.get_text().strip()
                    if page_text:
                        native_text_parts.append(f"--- Trang {page_idx + 1} ---\n{page_text}")
                    try:
                        for b in page.get_text("blocks"):
                            # fitz block tuple: (x0, y0, x1, y1, text, block_no, block_type)
                            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
                            text = (text or "").strip()
                            if text:
                                text_blocks_with_bbox.append({
                                    "page": page_idx + 1,  # 1-indexed, dễ đọc cho người + LLM
                                    "text": text,
                                    "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                                })
                    except Exception:
                        pass  # bbox tinh chỉnh chỉ là bonus — không có cũng không sao, native_text vẫn dùng được

            doc.close()
            return {
                "pdf_type": pdf_type,
                "full_page_image_base64": page_images_base64[0] if page_images_base64 else None,  # tương thích ngược — ảnh trang 1
                "page_images_base64": page_images_base64,  # MỚI — TẤT CẢ trang đã render (tới giới hạn), dùng cho Vision multi-image
                "native_text": native_text_parts[0].split("\n", 1)[-1] if native_text_parts and native_text_parts[0].startswith("--- Trang 1 ---") else "",  # tương thích ngược — text trang 1 riêng
                "all_pages_native_text": "\n\n".join(native_text_parts),  # MỚI — text NỐI mọi trang digital-native, có đánh dấu trang
                "text_blocks_with_bbox": text_blocks_with_bbox,  # MỞ RỘNG — mỗi block giờ có thêm field "page"
                "embedded_images": [],  # bonus thấp — không trích ảnh nhúng riêng lẻ trong PDF ở bản này
                "total_pages": total_pages,
                "pages_rendered": pages_to_render,  # < total_pages nếu vượt _MAX_PAGES_TO_RENDER — orchestrator dùng để cảnh báo
                "error": None,
            }
        except Exception as e:
            return _empty_error_result(f"Lỗi xử lý PDF: {e}")

    def to_pil_image(self, pdf_result: dict) -> "Image.Image | None":
        """Tiện ích: convert full_page_image_base64 (ảnh trang 1) trong kết quả process() về
        PIL Image — dùng cho local_path/OpenCV (contract vẫn nhận 1 ảnh, xem CLAUDE.md mục 3)."""
        b64 = pdf_result.get("full_page_image_base64")
        if not b64:
            return None
        try:
            return Image.open(io.BytesIO(base64.b64decode(b64)))
        except Exception:
            return None
