"""
compliance_checker/engine/opencv_modules.py — 2 nhóm hàm khác trạng thái:

  1. PLACEHOLDER (match_character, match_logo, extract_fonts): cần embedding/model + ảnh
     reference thật (anime_character_refs/, logo_refs/) — nhóm đã QUYẾT ĐỊNH BỎ hướng này
     (quá khó trong thời gian hackathon, xem ghi chú trong từng hàm). KHÔNG tự ý code lại
     thuật toán bên trong 3 hàm này — giữ nguyên đúng contract shape của CLAUDE.md mục 3 để
     orchestrator.py vẫn gọi được, luôn trả rỗng.
  2. ĐANG HOẠT ĐỘNG THẬT (detect_text_regions): thay thế hướng trên bằng 1 kỹ thuật OpenCV
     cổ điển đơn giản hơn nhiều — KHÔNG cần model/dataset/ảnh reference, chỉ dùng MSER +
     morphological dilation + contour để khoanh vùng CÓ KHẢ NĂNG chứa chữ trên ảnh. Dùng để
     vẽ toạ độ thật lên giao diện thay cho mô tả grid 3x3 bằng lời (xem orchestrator.py +
     frontend/app.js).

Nguyên tắc chung mọi hàm trong file: nhận image_path (string), trả dict JSON-serializable,
KHÔNG BAO GIỜ raise exception ra ngoài (đọc ảnh lỗi/thiếu file vẫn trả rỗng đúng shape).

pip install opencv-contrib-python numpy (đã có sẵn trong hệ thống hiện tại)
"""

import os

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

FONT_DISCLAIMER = (
    "Font detection is best-effort. Recommend manual verification against font license "
    "databases (MyFonts, Adobe Fonts, Font Squirrel)."
)


def _safe_imread(image_path: str):
    """Đọc ảnh an toàn — trả None nếu lỗi thay vì raise, dùng chung cho cả 3 hàm dưới."""
    if not _CV2_AVAILABLE:
        return None
    try:
        if not image_path or not os.path.exists(image_path):
            return None
        img = cv2.imread(image_path)
        return img
    except Exception:
        return None


def match_character(image_path: str) -> dict:
    """
    Output: {"matches": [{"character_name": str, "confidence": float}, ...]}
    LUÔN đúng 3 phần tử (top 3), sắp xếp confidence giảm dần, confidence 0-100.
    Nếu ảnh lỗi/không đọc được: {"matches": []}. KHÔNG trả tọa độ/bounding box.

    ⚠️ PLACEHOLDER — chưa có thuật toán so khớp thật (cần anime_character_refs/ có ảnh
    thật + embedding model, xem compliance_checker/data/anime_character_refs/README.md).
    Luôn trả rỗng cho tới khi dev OpenCV bổ sung thuật toán thật vào đây.
    """
    img = _safe_imread(image_path)
    if img is None:
        return {"matches": []}
    # TODO(dev OpenCV): thay bằng embedding thật (vd CLIP) + cosine-similarity so với
    # anime_character_refs/{character}/*.png, trả đúng top-3 giảm dần theo confidence.
    return {"matches": []}


def match_logo(image_path: str, suspected_logos: dict) -> dict:
    """
    Input suspected_logos: {"suspected_logos": [{"brand_name": str, "confidence": str}, ...]}
    Output: {"matches": [{"brand_name": str, "confidence": float}, ...]}
    Số lượng = số brand_name có ảnh reference hợp lệ trong logo_refs/manifest.json —
    KHÔNG tự quét toàn manifest nếu input rỗng.

    ⚠️ PLACEHOLDER — logo_refs/ hiện chưa có ảnh thật (chỉ có manifest.json mô tả brand
    nào CẦN ảnh), nên hàm này luôn trả rỗng cho tới khi có ảnh + thuật toán so khớp thật.
    """
    img = _safe_imread(image_path)
    brand_list = (suspected_logos or {}).get("suspected_logos", [])
    if img is None or not brand_list:
        return {"matches": []}
    # TODO(dev OpenCV): với mỗi brand_name trong brand_list, chuẩn hoá tên (lowercase,
    # space->underscore, bỏ ký tự đặc biệt), tra logo_refs/manifest.json — nếu file ảnh
    # reference tồn tại thật, so khớp (CLIP embedding hoặc feature matching ORB/SIFT) và
    # trả confidence float 0-100. Brand không có ảnh reference -> bỏ qua, KHÔNG raise lỗi.
    return {"matches": []}


def extract_fonts(image_path: str) -> dict:
    """
    Output: {"fonts_detected": [{"font_family_guess": str, "sample_text": str, "confidence": str}, ...]}
    LIỆT KÊ TOÀN BỘ vùng chữ phát hiện được, KHÔNG giới hạn số lượng. Nếu ảnh không có chữ
    hoặc lỗi đọc: {"fonts_detected": []}.

    ⚠️ PLACEHOLDER — cần model/OpenCV để khoanh vùng chữ + phân loại kiểu chữ (dev
    OpenCV+model phụ trách riêng phần này theo như đã thống nhất trong nhóm). Disclaimer
    cố định (FONT_DISCLAIMER) được orchestrator.py tự thêm vào output cuối cùng, KHÔNG nằm
    trong hàm này (đúng nguyên tắc CLAUDE.md mục 3: disclaimer ở tầng orchestrator).
    """
    img = _safe_imread(image_path)
    if img is None:
        return {"fonts_detected": []}
    # TODO(dev OpenCV+model): khoanh vùng chữ (vd MSER/EAST text detector), với mỗi vùng
    # ước lượng font_family_guess (mô tả định tính, vd "bold sans-serif") + sample_text +
    # confidence "low"/"medium"/"high". Đây là agent RIÊNG do bạn phụ trách phần font đảm
    # nhiệm — output cuối chỉ cần khớp đúng shape ở trên để orchestrator.py tiêu thụ được.
    return {"fonts_detected": []}


def detect_text_regions(image_path: str, max_regions: int = 5) -> dict:
    """
    Output: {"text_regions": [{"bbox": [x0,y0,x1,y1], "bbox_norm": [nx0,ny0,nx1,ny1], "area_ratio": float}, ...]}
    bbox: toạ độ pixel int. bbox_norm: cùng toạ độ nhưng chia theo chiều rộng/cao ảnh (0-1) —
    để frontend vẽ overlay bằng % CSS, không cần biết kích thước ảnh gốc. area_ratio: diện
    tích vùng / diện tích ảnh (0-1). Sắp xếp giảm dần theo diện tích, tối đa max_regions phần
    tử. Ảnh lỗi/không đọc được hoặc không tìm thấy vùng nào giống chữ: {"text_regions": []}.

    ✅ ĐANG HOẠT ĐỘNG THẬT (khác 3 hàm placeholder phía trên) — MSER + morphological
    dilation + contour, thuật toán cổ điển, KHÔNG cần model/dataset/ảnh reference nào.
    Đây là tín hiệu HÌNH HỌC thuần tuý (khoanh vùng "trông giống có chữ") — KHÔNG đọc/hiểu
    nội dung chữ (việc đó do Vision OCR ở Agent 1 đảm nhiệm), nên KHÔNG thể khẳng định chắc
    chắn 1 vùng cụ thể chứa ĐÚNG cụm từ nào bị flag trademark — chỉ dùng làm gợi ý trực quan
    "chữ nằm khoảng đâu trên ảnh", thay cho mô tả grid 3x3 bằng lời của Nhóm C (orchestrator.py
    gắn bbox_norm của vùng lớn nhất vào positioning_note category="trademark_text" nếu có).
    """
    img = _safe_imread(image_path)
    if img is None:
        return {"text_regions": []}
    try:
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mser = cv2.MSER_create()
        regions, _ = mser.detectRegions(gray)
        if not regions:
            return {"text_regions": []}

        boxes = [cv2.boundingRect(r.reshape(-1, 1, 2)) for r in regions]
        # Lọc nhiễu: quá nhỏ, gần trùm cả ảnh (không phải glyph riêng lẻ), hoặc aspect ratio
        # phi thực tế cho chữ (quá dẹt/quá cao) — ngưỡng kinh nghiệm, không học từ data.
        filtered = [
            (x, y, bw, bh) for (x, y, bw, bh) in boxes
            if bw >= 4 and bh >= 4
            and not (bw > w * 0.98 and bh > h * 0.98)
            and 0.05 <= (bw / max(bh, 1)) <= 25
        ]
        if not filtered:
            return {"text_regions": []}

        # MSER trả hàng trăm/nghìn box nhỏ theo từng nét/ký tự -> merge thành cụm từ/dòng
        # bằng dilation ngang (kernel co giãn theo chiều cao chữ trung vị) rồi tìm contour.
        heights = sorted(bh for (_, _, _, bh) in filtered)
        med_h = float(heights[len(heights) // 2])
        kernel_w = max(int(med_h * 2.8), 9)
        kernel_h = max(int(med_h * 0.7), 3)
        mask = np.zeros((h, w), dtype="uint8")
        for (x, y, bw, bh) in filtered:
            cv2.rectangle(mask, (x, y), (x + bw, y + bh), 255, -1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, kernel_h))
        dilated = cv2.dilate(mask, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        merged = [cv2.boundingRect(c) for c in contours]
        merged.sort(key=lambda b: b[2] * b[3], reverse=True)

        out = []
        for (x, y, bw, bh) in merged[:max_regions]:
            out.append({
                "bbox": [int(x), int(y), int(x + bw), int(y + bh)],
                "bbox_norm": [round(x / w, 4), round(y / h, 4), round((x + bw) / w, 4), round((y + bh) / h, 4)],
                "area_ratio": round((bw * bh) / (w * h), 4),
            })
        return {"text_regions": out}
    except Exception:
        return {"text_regions": []}
