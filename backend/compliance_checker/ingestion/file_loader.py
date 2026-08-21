"""
compliance_checker/ingestion/file_loader.py — DesignFileLoader: hợp nhất PNG/JPG/PSD/PDF về 1
ảnh PIL trước khi vào pipeline, gọi tới pdf_processor.py khi cần. Đây là điểm hội tụ DUY NHẤT
của mọi loại input (upload/link/CSV batch đều đi qua đây sau khi đã có bytes/đường dẫn file
cục bộ) — phần còn lại của hệ thống chỉ làm việc với 1 ảnh PIL + base64, không cần biết
định dạng gốc là gì.

Bắt buộc: PNG/JPG. Bonus: PDF/PSD. Deprioritize: AI/EPS/SVG (ROI thấp, xem CLAUDE.md mục 1.2).

pip install pillow pymupdf psd-tools
"""

import base64
import io
import os

from PIL import Image

from compliance_checker.ingestion.pdf_processor import PDFProcessor

try:
    from psd_tools import PSDImage
    _PSD_TOOLS_AVAILABLE = True
except ImportError:
    _PSD_TOOLS_AVAILABLE = False

_RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class DesignFileLoaderError(Exception):
    """Lỗi rõ ràng khi không load được file — orchestrator catch để đánh dấu ERROR đúng row,
    KHÔNG để lỗi này tự bò lên làm sập cả batch."""


class DesignFileLoader:
    def __init__(self):
        self._pdf_processor = PDFProcessor()

    def load_as_image(self, file_path: str) -> "Image.Image":
        """
        Trả về PIL Image, hoặc raise DesignFileLoaderError với thông báo rõ ràng — KHÔNG
        bao giờ để exception gốc (KeyError/IOError...) lộ ra ngoài mơ hồ.
        """
        if not file_path or not os.path.exists(file_path):
            raise DesignFileLoaderError(f"File không tồn tại: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        if ext in _RASTER_EXTENSIONS:
            try:
                img = Image.open(file_path)
                img.load()  # ép decode ngay để bắt lỗi file hỏng sớm, không lazy-fail sau này
                return img.convert("RGB")
            except Exception as e:
                raise DesignFileLoaderError(f"Không đọc được ảnh {file_path}: {e}")

        if ext == ".pdf":
            result = self._pdf_processor.process(file_path)
            if result.get("error"):
                raise DesignFileLoaderError(f"Lỗi xử lý PDF {file_path}: {result['error']}")
            img = self._pdf_processor.to_pil_image(result)
            if img is None:
                raise DesignFileLoaderError(f"PDF xử lý xong nhưng không render được ảnh: {file_path}")
            # .convert("RGB") trả về 1 OBJECT MỚI (không giữ attribute tự gắn trên ảnh gốc) —
            # phải gắn _pdf_metadata SAU convert, không phải trước, nếu không orchestrator sẽ
            # không lấy lại được native_text/text_blocks_with_bbox (mất silently, khó debug).
            img_rgb = img.convert("RGB")
            img_rgb._pdf_metadata = result
            return img_rgb

        if ext == ".psd":
            if not _PSD_TOOLS_AVAILABLE:
                raise DesignFileLoaderError(
                    "psd-tools chưa được cài — chạy `pip install psd-tools` để xử lý file .psd."
                )
            try:
                psd = PSDImage.open(file_path)
                composite = psd.composite()
                if composite is None:
                    raise DesignFileLoaderError(f"Không composite được ảnh từ PSD: {file_path}")
                return composite.convert("RGB")
            except DesignFileLoaderError:
                raise
            except Exception as e:
                raise DesignFileLoaderError(f"Lỗi xử lý PSD {file_path}: {e}")

        raise DesignFileLoaderError(
            f"Định dạng '{ext}' chưa được hỗ trợ (deprioritize theo thiết kế — AI/EPS/SVG "
            f"không nằm trong phạm vi bắt buộc). Chỉ hỗ trợ: {sorted(_RASTER_EXTENSIONS)} + .pdf + .psd."
        )

    def to_base64(self, image: "Image.Image") -> str:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def load_bytes_as_image(self, raw_bytes: bytes) -> "Image.Image":
        """Dùng cho nhánh link-import khi ĐÃ biết chắc là ảnh raster thuần (xem sniff_extension
        bên dưới để tự nhận diện PDF/PSD trước khi gọi hàm này)."""
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            img.load()
            return img.convert("RGB")
        except Exception as e:
            raise DesignFileLoaderError(f"Không decode được bytes tải về thành ảnh: {e}")

    def sniff_extension(self, raw_bytes: bytes) -> str:
        """
        Đoán extension file THẬT từ magic bytes đầu file — dùng cho nhánh link-import
        (link_normalizer.py chỉ tải bytes thô về, không biết/không quan tâm đó là ảnh hay
        PDF/PSD, xem docstring link_normalizer.py).

        ⚠️ FIX khoảng trống thật: trước đây link-import LUÔN giả định link trỏ tới ảnh thuần
        (gọi thẳng load_bytes_as_image() -> PIL.Image.open()) — nếu link (Google Drive/Dropbox/
        S3/bất kỳ, KHÔNG riêng Google Drive) trỏ tới PDF/PSD, bước decode sẽ lỗi rõ ràng
        ("Không decode được bytes tải về thành ảnh") thay vì tự nhận ra và xử lý đúng như PDF
        nhiều trang/PSD. Cùng cơ chế sniff magic bytes như agents.py::_sniff_image_mime (ảnh).

        Không nhận diện được -> mặc định ".png" (coi là ảnh, giữ đúng hành vi cũ, an toàn nhất
        cho các định dạng ảnh hiếm không nằm trong danh sách dưới).
        """
        if raw_bytes[:5] == b"%PDF-":
            return ".pdf"
        if raw_bytes[:4] == b"8BPS":
            return ".psd"
        if raw_bytes[:3] == b"\xff\xd8\xff":
            return ".jpg"
        if raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return ".png"
        if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
            return ".webp"
        if raw_bytes[:2] == b"BM":
            return ".bmp"
        return ".png"
