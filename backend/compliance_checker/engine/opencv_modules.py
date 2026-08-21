"""
compliance_checker/engine/opencv_modules.py — 4 nhóm hàm khác trạng thái:

  1. PLACEHOLDER (match_character, match_logo, extract_fonts): cần embedding/model + ảnh
     reference thật (anime_character_refs/, logo_refs/) — nhóm đã QUYẾT ĐỊNH BỎ hướng này
     (quá khó trong thời gian hackathon, xem ghi chú trong từng hàm). KHÔNG tự ý code lại
     thuật toán bên trong 3 hàm này — giữ nguyên đúng contract shape của CLAUDE.md mục 3 để
     orchestrator.py vẫn gọi được, luôn trả rỗng.
  2. VẪN HOẠT ĐỘNG NHƯNG KHÔNG CÒN ĐƯỢC GỌI (detect_text_regions, 2026-08-21): MSER-based,
     chỉ khoanh vùng "trông giống chữ" (hình học thuần, KHÔNG đọc nội dung). Đã bị THAY THẾ
     bởi extract_text_blocks() bên dưới (OCR thật, có nội dung + bbox chính xác hơn hẳn) —
     giữ lại hàm này (không xoá, vẫn chạy đúng nếu gọi) phòng khi cần fallback không cần
     rapidocr_onnxruntime, nhưng orchestrator.py hiện KHÔNG còn gọi tới.
  3. ĐANG HOẠT ĐỘNG THẬT (detect_and_crop_faces, 2026-08-21): dùng model BlazeFace short-range
     (do người dùng tự thêm vào data/models/, xem manifest.json ở đó) để KHOANH VÙNG + CẮT mọi
     khuôn mặt trong ảnh — đây CHỈ là face DETECTION (tìm "có mặt người ở đâu"), KHÔNG phải
     face-recognition/embedding sinh trắc học nào. Ảnh mặt cắt ra được gửi cho Agent 2
     (Claude Vision) tự nhận diện trực tiếp — xem agents.py::run_agent2_verify_candidates.
     Toàn bộ threshold/config port NGUYÊN VẸN từ script gốc người dùng cung cấp
     (crop_face_blazeface.py, đã tự fine-tune trên nhiều ảnh thật) — KHÔNG chỉnh lại số.
  4. ĐANG HOẠT ĐỘNG THẬT (extract_text_blocks, 2026-08-21): OCR THẬT (RapidOCR/ONNX, khác hẳn
     detect_text_regions ở mục 2 — đọc được NỘI DUNG chữ, không chỉ khoanh vùng) + tự gộp các
     box chữ rời rạc thành block/line theo hình học (cùng font size, cùng hàng...). Port từ
     script gốc người dùng cung cấp (test_ocr.py) — bỏ phần ghi crop ảnh ra đĩa (không cần,
     pipeline chỉ cần TEXT + bbox, xem agents.py TASK 3 + lý do quyết định trong docs.md).

Nguyên tắc chung mọi hàm trong file: nhận image_path (string), trả dict JSON-serializable,
KHÔNG BAO GIỜ raise exception ra ngoài (đọc ảnh lỗi/thiếu file vẫn trả rỗng đúng shape).

pip install opencv-contrib-python numpy rapidocr_onnxruntime (đã có sẵn trong hệ thống hiện tại)
"""

import base64
import os

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

try:
    from rapidocr_onnxruntime import RapidOCR
    _RAPIDOCR_AVAILABLE = True
except ImportError:
    _RAPIDOCR_AVAILABLE = False

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


# =====================================================================
# FACE DETECTION (BlazeFace) — 2026-08-21, port NGUYÊN VẸN từ crop_face_blazeface.py
# (script do người dùng tự viết/fine-tune, cung cấp cùng model). Toàn bộ hằng số/thuật
# toán bên dưới GIỮ Y HỆT bản gốc — chỉ đổi input (file path -> image path đã có sẵn trong
# pipeline) và output (ghi file .jpg -> base64 string để gửi thẳng cho Agent 2 qua Vision).
# =====================================================================

_FACE_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "models", "blaze_face_short_range.tflite")
_FACE_INPUT_SIZE = 128  # BlazeFace short range nhận input 128x128

# Đã fine-tune bằng cách đo phân bố điểm tin cậy trên nhiều ảnh thật (ảnh 1-2 người lẫn ảnh
# đông người) — mặt thật luôn >= 0.83, box rác (hoạ tiết/nền/vật thể) rơi vào khoảng 0.5-0.68.
_FACE_SCORE_THRESH = 0.7
_FACE_IOU_THRESH = 0.3            # ngưỡng NMS (gộp box trùng nhau trong 1 window)
_FACE_GLOBAL_IOU_THRESH = 0.3     # ngưỡng NMS toàn cục (gộp box trùng từ nhiều window)
_FACE_MARGIN = 0.2                # nở rộng box thêm 20% mỗi cạnh cho dễ crop đẹp hơn

# Multi-scale tiling — BlazeFace short-range chỉ được train cho mặt lớn/gần camera, quét
# nhiều "cửa sổ" ở nhiều tỷ lệ chồng lấn để bắt được cả mặt nhỏ (ảnh đông người).
_FACE_WINDOW_SCALES = (1.0, 0.6, 0.4, 0.27, 0.18)
_FACE_WINDOW_OVERLAP = 0.5
_FACE_MIN_WINDOW_PX = 60

_FACE_MAX_CROPS = 5          # top N mặt điểm cao nhất gửi cho Agent 2 (kiểm soát chi phí/kích thước request)
_FACE_UPSCALE_MIN_SIDE = 160  # crop nhỏ hơn cạnh này (thường gặp, mặt xa) -> phóng to trước khi encode,
                              # giúp Agent 2 nhận diện dễ hơn — CHỈ ảnh hưởng bước encode, KHÔNG ảnh
                              # hưởng gì tới bbox/score/threshold detect (giữ nguyên như script gốc).

_FACE_NET_CACHE = None   # lazy-load 1 lần cho cả process, tránh đọc lại model từ đĩa mỗi lần gọi
_FACE_NET_LOAD_FAILED = False


def _get_face_net():
    global _FACE_NET_CACHE, _FACE_NET_LOAD_FAILED
    if _FACE_NET_CACHE is not None or _FACE_NET_LOAD_FAILED:
        return _FACE_NET_CACHE
    try:
        _FACE_NET_CACHE = cv2.dnn.readNetFromTFLite(_FACE_MODEL_PATH)
    except Exception:
        _FACE_NET_LOAD_FAILED = True
        _FACE_NET_CACHE = None
    return _FACE_NET_CACHE


def _face_generate_anchors(input_size=128, strides=(8, 16, 16, 16)):
    """Sinh anchor (x_center, y_center) chuẩn hoá [0,1] đúng cấu hình của BlazeFace short
    range (fixed_anchor_size=True, aspect_ratios=[1.0] + 1 interpolated scale => 2 anchor/vị trí)."""
    anchors = []
    layer_id = 0
    while layer_id < len(strides):
        last_same_stride = layer_id
        repeats = 0
        while (last_same_stride < len(strides) and
               strides[last_same_stride] == strides[layer_id]):
            last_same_stride += 1
            repeats += 2  # 1 aspect ratio + 1 interpolated scale
        stride = strides[layer_id]
        feat = input_size // stride
        for y in range(feat):
            for x in range(feat):
                x_center = (x + 0.5) / feat
                y_center = (y + 0.5) / feat
                for _ in range(repeats):
                    anchors.append((x_center, y_center))
        layer_id = last_same_stride
    return np.array(anchors, dtype=np.float32)  # (N, 2)


_FACE_ANCHORS = None  # lazy-init cùng lúc với net (tránh tính numpy khi chưa chắc cv2 sẵn sàng)


def _face_letterbox(image, size=128):
    """Resize giữ tỷ lệ rồi pad thành hình vuông size x size (pad giữa)."""
    h, w = image.shape[:2]
    scale = size / max(h, w)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_w, pad_h = size - new_w, size - new_h
    top, bottom = pad_h // 2, pad_h - pad_h // 2
    left, right = pad_w // 2, pad_w - pad_w // 2
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right,
                                 cv2.BORDER_CONSTANT, value=(0, 0, 0))
    return padded, scale, left, top


def _face_decode_boxes(regressors, anchors, input_size=128):
    """Giải mã 16 giá trị regressor (4 box + 6 keypoint*2) theo anchor.
    Trả về boxes chuẩn hoá [0,1]: (xmin, ymin, xmax, ymax)."""
    reg = regressors[0]  # (896, 16)
    dx, dy, dw, dh = reg[:, 0], reg[:, 1], reg[:, 2], reg[:, 3]

    anchor_x, anchor_y = anchors[:, 0], anchors[:, 1]

    x_center = dx / input_size + anchor_x
    y_center = dy / input_size + anchor_y
    w = dw / input_size
    h = dh / input_size

    xmin = x_center - w / 2
    ymin = y_center - h / 2
    xmax = x_center + w / 2
    ymax = y_center + h / 2
    return np.stack([xmin, ymin, xmax, ymax], axis=1)


def _face_detect_in_region(region, net, anchors):
    """Chạy BlazeFace trên 1 vùng ảnh (region), trả về box theo toạ độ CỦA CHÍNH VÙNG ĐÓ
    (chưa cộng offset), đã NMS trong phạm vi region."""
    padded, scale, pad_x, pad_y = _face_letterbox(region, _FACE_INPUT_SIZE)

    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = (rgb - 127.5) / 127.5
    blob = cv2.dnn.blobFromImage(rgb)  # -> (1, 3, 128, 128)

    net.setInput(blob)
    classificators, regressors = net.forward(["classificators", "regressors"])

    scores = classificators[0, :, 0]
    scores = np.clip(scores, -30, 30)  # giới hạn trước sigmoid để tránh tràn số
    scores = 1.0 / (1.0 + np.exp(-scores))

    keep = scores > _FACE_SCORE_THRESH
    if not np.any(keep):
        return []

    boxes_norm = _face_decode_boxes(regressors, anchors, _FACE_INPUT_SIZE)[keep]
    scores_kept = scores[keep]

    boxes_px = (boxes_norm * _FACE_INPUT_SIZE).astype(np.float32)
    nms_boxes = [[x1, y1, x2 - x1, y2 - y1] for x1, y1, x2, y2 in boxes_px]
    idxs = cv2.dnn.NMSBoxes(nms_boxes, scores_kept.tolist(), _FACE_SCORE_THRESH, _FACE_IOU_THRESH)
    if len(idxs) == 0:
        return []
    idxs = np.array(idxs).flatten()

    h_reg, w_reg = region.shape[:2]
    results = []
    for i in idxs:
        x1, y1, x2, y2 = boxes_px[i]
        x1 = (x1 - pad_x) / scale
        y1 = (y1 - pad_y) / scale
        x2 = (x2 - pad_x) / scale
        y2 = (y2 - pad_y) / scale

        x1 = max(0.0, x1); y1 = max(0.0, y1)
        x2 = min(float(w_reg), x2); y2 = min(float(h_reg), y2)
        if x2 > x1 and y2 > y1:
            results.append((x1, y1, x2, y2, float(scores_kept[i])))
    return results


def _face_generate_windows(h, w):
    """Sinh các cửa sổ vuông, chồng lấn, ở nhiều tỷ lệ (_FACE_WINDOW_SCALES) để phủ hết
    ảnh -> giúp bắt được cả mặt lớn lẫn mặt nhỏ."""
    short_side = min(h, w)
    seen = set()
    for scale in _FACE_WINDOW_SCALES:
        size = int(round(short_side * scale))
        size = min(size, h, w)
        if size < _FACE_MIN_WINDOW_PX:
            continue
        stride = max(1, int(round(size * (1 - _FACE_WINDOW_OVERLAP))))

        def positions(total, size, stride):
            if size >= total:
                return [0]
            pos = list(range(0, total - size + 1, stride))
            if pos[-1] != total - size:
                pos.append(total - size)
            return pos

        for y0 in positions(h, size, stride):
            for x0 in positions(w, size, stride):
                key = (x0, y0, size)
                if key in seen:
                    continue
                seen.add(key)
                yield x0, y0, size, size


def _face_detect_all(image, net, anchors):
    """Quét đa tỷ lệ trên toàn ảnh, gộp tất cả box lại rồi NMS toàn cục.
    Trả về list (x1, y1, x2, y2, score) theo toạ độ ảnh gốc."""
    h_orig, w_orig = image.shape[:2]

    all_boxes = []
    all_scores = []
    for x0, y0, win_w, win_h in _face_generate_windows(h_orig, w_orig):
        region = image[y0:y0 + win_h, x0:x0 + win_w]
        for x1, y1, x2, y2, score in _face_detect_in_region(region, net, anchors):
            all_boxes.append([x0 + x1, y0 + y1, x2 - x1, y2 - y1])  # xywh
            all_scores.append(score)

    if not all_boxes:
        return []

    idxs = cv2.dnn.NMSBoxes(all_boxes, all_scores, _FACE_SCORE_THRESH, _FACE_GLOBAL_IOU_THRESH)
    if len(idxs) == 0:
        return []
    idxs = np.array(idxs).flatten()

    results = []
    for i in idxs:
        x, y, bw, bh = all_boxes[i]
        x1, y1, x2, y2 = x, y, x + bw, y + bh

        x1 -= bw * _FACE_MARGIN / 2
        y1 -= bh * _FACE_MARGIN / 2
        x2 += bw * _FACE_MARGIN / 2
        y2 += bh * _FACE_MARGIN / 2

        x1 = int(max(0, x1)); y1 = int(max(0, y1))
        x2 = int(min(w_orig, x2)); y2 = int(min(h_orig, y2))
        if x2 > x1 and y2 > y1:
            results.append((x1, y1, x2, y2, float(all_scores[i])))
    return results


def detect_and_crop_faces(image_path: str, max_faces: int = _FACE_MAX_CROPS) -> dict:
    """
    Output: {"faces": [{"face_base64": str, "bbox_norm": [x0,y0,x1,y1], "detection_score": float}, ...]}
    Tối đa max_faces phần tử (mặc định 5), sắp xếp detection_score giảm dần. Ảnh lỗi/không
    đọc được/model chưa sẵn sàng/không phát hiện mặt nào: {"faces": []}.

    face_base64: JPEG của VÙNG ĐÃ CẮT (không phải cả ảnh) — nếu crop nhỏ hơn
    _FACE_UPSCALE_MIN_SIDE thì phóng to trước khi encode (CHỈ ảnh hưởng bước gửi cho Agent 2
    nhận diện, KHÔNG ảnh hưởng bbox/score/threshold — các số đó giữ nguyên như script gốc).
    bbox_norm: [x0,y0,x1,y1] normalize 0-1 theo ảnh GỐC (chưa crop) — để frontend vẽ overlay
    nếu cần, cùng shape với text_regions/positioning_notes.bbox_norm.
    detection_score: độ tin cậy CÓ-PHẢI-MẶT-NGƯỜI của BlazeFace (0-1) — chỉ dùng nội bộ để
    sắp xếp/chọn top N, KHÔNG phải độ tin cậy nhận diện DANH TÍNH (đó là việc của Agent 2,
    xem agents.py) — orchestrator.py KHÔNG đưa field này ra response cuối cùng.

    ⚠️ Đây CHỈ là face DETECTION (khoanh vùng "có mặt người ở đây") — KHÔNG so khớp/embedding
    sinh trắc học để định danh. Định danh (suspected_name) hoàn toàn do Agent 2 (Claude Vision)
    tự nhận diện trực tiếp trên ảnh crop, theo đúng quyết định của nhóm.
    """
    img = _safe_imread(image_path)
    if img is None:
        return {"faces": []}
    net = _get_face_net()
    if net is None:
        return {"faces": []}
    try:
        global _FACE_ANCHORS
        if _FACE_ANCHORS is None:
            _FACE_ANCHORS = _face_generate_anchors(_FACE_INPUT_SIZE)

        h_orig, w_orig = img.shape[:2]
        detections = _face_detect_all(img, net, _FACE_ANCHORS)
        if not detections:
            return {"faces": []}

        detections.sort(key=lambda d: d[4], reverse=True)  # score giảm dần
        out = []
        for (x1, y1, x2, y2, score) in detections[:max_faces]:
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            ch, cw = crop.shape[:2]
            if min(ch, cw) < _FACE_UPSCALE_MIN_SIDE:
                up_scale = _FACE_UPSCALE_MIN_SIDE / max(min(ch, cw), 1)
                crop = cv2.resize(crop, (max(int(cw * up_scale), 1), max(int(ch * up_scale), 1)), interpolation=cv2.INTER_CUBIC)
            ok, buf = cv2.imencode(".jpg", crop)
            if not ok:
                continue
            out.append({
                "face_base64": base64.b64encode(buf.tobytes()).decode("ascii"),
                "bbox_norm": [round(x1 / w_orig, 4), round(y1 / h_orig, 4), round(x2 / w_orig, 4), round(y2 / h_orig, 4)],
                "detection_score": round(score, 4),
            })
        return {"faces": out}
    except Exception:
        return {"faces": []}


# =====================================================================
# TEXT BLOCK EXTRACTION (RapidOCR) — 2026-08-21, port từ test_ocr.py (script do người dùng
# tự viết, cung cấp cùng yêu cầu). Khác detect_text_regions() (MSER, chỉ khoanh vùng): đây là
# OCR THẬT — đọc được NỘI DUNG chữ, dùng cho Agent 2 so khớp trademark + tự đánh giá "cảm
# nhận". Đã bỏ phần cv2.imwrite crop ra đĩa của script gốc (pipeline chỉ cần TEXT + bbox_norm,
# không cần lưu file ảnh — Agent 2 nhận TEXT chứ không nhận ảnh, xem quyết định trong docs.md).
# Cũng bỏ hàm same_block() của script gốc — định nghĩa nhưng KHÔNG được gọi ở đâu trong
# get_grouped_ocr_results() gốc (chỉ same_block_boxes() được dùng thật) — port đúng phần
# THẬT SỰ chạy, không port code chết.
# =====================================================================

_OCR_ENGINE_CACHE = None
_OCR_ENGINE_LOAD_FAILED = False
_OCR_MAX_BLOCKS = 30  # safety valve chống ảnh lỗi/nhiễu sinh quá nhiều block vụn, không phải giới hạn hành vi bình thường


def _get_ocr_engine():
    global _OCR_ENGINE_CACHE, _OCR_ENGINE_LOAD_FAILED
    if _OCR_ENGINE_CACHE is not None or _OCR_ENGINE_LOAD_FAILED:
        return _OCR_ENGINE_CACHE
    try:
        _OCR_ENGINE_CACHE = RapidOCR()
    except Exception:
        _OCR_ENGINE_LOAD_FAILED = True
        _OCR_ENGINE_CACHE = None
    return _OCR_ENGINE_CACHE


def _ocr_box_info(box, text="", score=0.0):
    pts = np.asarray(box, dtype=np.float32)
    x1, y1 = pts.min(axis=0)
    x2, y2 = pts.max(axis=0)
    return {
        "pts": pts,
        "x1": float(x1), "y1": float(y1), "x2": float(x2), "y2": float(y2),
        "cx": float((x1 + x2) / 2), "cy": float((y1 + y2) / 2),
        "w": float(x2 - x1), "h": float(y2 - y1),
        "text": text.strip(), "confidence": float(score),
    }


def _ocr_overlap(a, b, axis="x"):
    if axis == "x":
        inter = max(0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]))
        size = min(a["w"], b["w"])
    else:
        inter = max(0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
        size = min(a["h"], b["h"])
    return (inter / size) if size > 0 else 0


def _ocr_gap(a, b, axis="x"):
    if axis == "x":
        return max(0, max(a["x1"], b["x1"]) - min(a["x2"], b["x2"]))
    return max(0, max(a["y1"], b["y1"]) - min(a["y2"], b["y2"]))


def _ocr_same_line(a, b, block_h=None):
    """Không chỉ dựa vào Y: Y phải tương đối thẳng hàng, chiều cao chữ tương đối giống,
    khoảng cách X hợp lý."""
    a_h, b_h = a["h"], b["h"]
    h = (a_h + b_h) / 2
    ref_h = float(block_h) if block_h is not None else h
    h_sim = min(a_h, b_h) / max(a_h, b_h)
    if h_sim < 0.45:
        return False

    y_overlap = _ocr_overlap(a, b, "y")
    y_dist = abs(a["cy"] - b["cy"])
    x_gap = _ocr_gap(a, b, "x")

    if y_overlap < 0.15 and y_dist > ref_h * 0.8:
        return False
    if x_gap > ref_h * 3.5:
        return False

    y_score = max(0.0, 1.0 - y_dist / (ref_h * 0.9))
    x_score = max(0.0, 1.0 - x_gap / (ref_h * 3.5))
    score = 0.40 * y_score + 0.25 * y_overlap + 0.20 * h_sim + 0.15 * x_score
    return score >= 0.5


def _ocr_make_groups(items, relation):
    """Connected components bằng Union-Find."""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    has_geom = n > 0 and isinstance(items[0], dict) and "x1" in items[0]
    for i in range(n):
        a = items[i]
        for j in range(i + 1, n):
            b = items[j]
            if has_geom:
                if max(a.get("y1", 0), b.get("y1", 0)) - min(a.get("y2", 0), b.get("y2", 0)) > max(a.get("h", 0), b.get("h", 0)) * 10:
                    continue
            if relation(a, b):
                union(i, j)

    groups = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(items[i])
    return list(groups.values())


def _ocr_same_block_boxes(a, b):
    """Quyết định 2 box chữ có cùng 1 block hay không — dựa vào chiều cao box (font size)
    làm tín hiệu chính, để block hình thành theo đúng cỡ chữ + khoảng cách gần nhau."""
    a_h, b_h = a["h"], b["h"]
    h = (a_h + b_h) / 2
    if abs(a["cy"] - b["cy"]) > h * 6:
        return False
    x_overlap = max(0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"])) / max(1, min(a["w"], b["w"]))
    left_aligned = abs(a["x1"] - b["x1"]) <= h * 2
    if x_overlap >= 0.25 or left_aligned:
        return True
    if _ocr_gap(a, b, "x") <= h * 2.5:
        return True
    return False


def extract_text_blocks(image_path: str, min_confidence: float = 0.3) -> dict:
    """
    Output: {"text_blocks": [{"bbox": [x0,y0,x1,y1], "bbox_norm": [nx0,ny0,nx1,ny1],
             "text": str, "ocr_confidence": float}, ...]}
    Tối đa _OCR_MAX_BLOCKS phần tử (safety valve, không phải giới hạn hành vi bình thường).
    ocr_confidence: 0-100, độ tin cậy đọc chữ THẬT của RapidOCR — CHỈ dùng nội bộ (lọc
    junk/sort), KHÔNG phải "high/medium/low" định tính như các field confidence khác trong
    hệ thống, orchestrator.py KHÔNG đưa field này ra response cuối cùng.
    Ảnh lỗi/không đọc được/model chưa sẵn sàng/không có chữ nào: {"text_blocks": []}.

    text: NỘI DUNG chữ thật đã OCR (khác detect_text_regions() ở trên — hàm đó KHÔNG đọc nội
    dung). Mỗi block có thể gồm NHIỀU dòng (nối bằng "\\n") nếu OCR + gộp hình học xác định
    chúng cùng 1 khối văn bản (vd 1 đoạn slogan nhiều dòng) — Agent 2 (agents.py) được yêu cầu
    tự ghép nối thêm giữa CÁC block nếu cần (vd slogan bị tách rời 2 block do khoảng cách),
    hàm này chỉ gộp trong phạm vi hình học 1 block, không đoán ngữ nghĩa.
    """
    img = _safe_imread(image_path)
    if img is None or not _RAPIDOCR_AVAILABLE:
        return {"text_blocks": []}
    engine = _get_ocr_engine()
    if engine is None:
        return {"text_blocks": []}
    try:
        h_img, w_img = img.shape[:2]
        result, _ = engine(img)
        if not result:
            return {"text_blocks": []}

        detections = [
            _ocr_box_info(box, text, score)
            for box, text, score in result
            if float(score) >= min_confidence and text.strip()
        ]
        if not detections:
            return {"text_blocks": []}

        # Stage 1: box -> block (gộp theo font size + khoảng cách)
        blocks_raw = _ocr_make_groups(detections, _ocr_same_block_boxes)

        text_blocks = []
        for blk in blocks_raw:
            font_h = float(np.median([x["h"] for x in blk]))
            # Stage 2: trong 1 block, gộp box -> line (dòng), biased theo font_h của block
            lines_in_blk = _ocr_make_groups(blk, lambda a, b: _ocr_same_line(a, b, block_h=font_h))
            for line in lines_in_blk:
                line.sort(key=lambda x: x["x1"])  # trái sang phải
            lines_in_blk.sort(key=lambda line: min(x["y1"] for x in line))  # trên xuống dưới

            text = "\n".join(" ".join(x["text"] for x in line) for line in lines_in_blk)
            items = [x for line in lines_in_blk for x in line]

            pts = np.concatenate([x["pts"] for x in items])
            x1, y1 = pts.min(axis=0)
            x2, y2 = pts.max(axis=0)
            x1 = max(0, int(x1)); y1 = max(0, int(y1))
            x2 = min(w_img, int(x2)); y2 = min(h_img, int(y2))
            if x2 <= x1 or y2 <= y1:
                continue

            text_blocks.append({
                "bbox": [x1, y1, x2, y2],
                "bbox_norm": [round(x1 / w_img, 4), round(y1 / h_img, 4), round(x2 / w_img, 4), round(y2 / h_img, 4)],
                "text": text,
                "ocr_confidence": round(float(np.mean([x["confidence"] for x in items])) * 100, 1),
            })

        # Sort theo diện tích giảm dần (block lớn/nổi bật thường quan trọng hơn) rồi cap.
        text_blocks.sort(key=lambda b: (b["bbox"][2] - b["bbox"][0]) * (b["bbox"][3] - b["bbox"][1]), reverse=True)
        return {"text_blocks": text_blocks[:_OCR_MAX_BLOCKS]}
    except Exception:
        return {"text_blocks": []}
