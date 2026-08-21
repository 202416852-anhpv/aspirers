"""
Crop TAT CA khuon mat trong anh bang model BlazeFace (short range) chay qua OpenCV DNN.

Model: blaze_face_short_range.tflite (MediaPipe BlazeFace)
Yeu cau: opencv-python >= 4.7 (co ho tro cv2.dnn.readNetFromTFLite)

BlazeFace short-range chi duoc train cho mat lon/gan camera (kieu selfie),
nen 1 lan chay 128x128 tren nguyen anh se bo sot cac mat nho (anh dong nguoi).
De bat duoc TAT CA mat du lon nho, script quet nhieu "cua so" (window) o
nhieu ty le chong lan (multi-scale tiling) roi gop + NMS toan cuc.

Cach dung:
    python crop_face_blazeface.py input.jpg
    (anh mat crop se duoc luu ra face_0.jpg, face_1.jpg, ...)
"""

import sys
import cv2
import numpy as np

MODEL_PATH = "blaze_face_short_range.tflite"
INPUT_SIZE = 128           # BlazeFace short range nhan input 128x128

# SCORE_THRESH: da fine-tune bang cach do phan bo diem tin cay tren nhieu anh
# that (anh 1-2 nguoi lan anh dong nguoi). Mat that luon >= 0.83, con box rac
# (hoa tiet, nen, vat the) roi vao khoang 0.5-0.68 -> 0.7 la nguong an toan
# cat sach box rac ma khong mat mat that trong da so truong hop.
#   0.5      -> nhay nhat, bat ca mat rat nho/mo nhung ra nhieu box rac
#   0.7-0.75 -> sach box rac tren anh thuong (1-vai nguoi), van du nhay
#   0.85+    -> rat sach nhung anh dong nguoi se mat dan cac mat mo/nho/khuat
SCORE_THRESH = 0.7
IOU_THRESH = 0.3           # nguong NMS (gop box trung nhau trong 1 window)
GLOBAL_IOU_THRESH = 0.3    # nguong NMS toan cuc (gop box trung tu nhieu window)
MARGIN = 0.2                # no rong box them 20% moi canh cho de crop dep hon

# --- cau hinh quet da ty le (multi-scale tiling) ---
WINDOW_SCALES = (1.0, 0.6, 0.4, 0.27, 0.18)  # ty le canh cua so / canh ngan cua anh
WINDOW_OVERLAP = 0.5                          # do chong lan giua cac cua so lien ke
MIN_WINDOW_PX = 60                            # bo qua cua so qua nho (khong con y nghia)


def generate_anchors(input_size=128, strides=(8, 16, 16, 16)):
    """Sinh anchor (x_center, y_center) chuan hoa [0,1] dung cau hinh
    cua BlazeFace short range (fixed_anchor_size=True, aspect_ratios=[1.0]
    + 1 interpolated scale => 2 anchor / vi tri)."""
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


def letterbox(image, size=128):
    """Resize giu ty le roi pad thanh hinh vuong size x size (pad giua)."""
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


def decode_boxes(regressors, anchors, input_size=128):
    """Giai ma 16 gia tri regressor (4 box + 6 keypoint*2) theo anchor.
    Tra ve boxes chuan hoa [0,1]: (xmin, ymin, xmax, ymax)."""
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


_ANCHORS = generate_anchors(INPUT_SIZE)


def detect_faces_in_region(region, net):
    """Chay BlazeFace tren 1 vung anh (region), tra ve box theo toa do
    CUA CHINH VUNG DO (chua cong offset), da NMS trong pham vi region."""
    padded, scale, pad_x, pad_y = letterbox(region, INPUT_SIZE)

    # BlazeFace input: RGB, chuan hoa ve [-1, 1]
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = (rgb - 127.5) / 127.5
    blob = cv2.dnn.blobFromImage(rgb)  # -> (1, 3, 128, 128)

    net.setInput(blob)
    classificators, regressors = net.forward(["classificators", "regressors"])

    scores = classificators[0, :, 0]
    # gioi han truoc khi qua sigmoid de tranh tran so (van bao hoa dung ve 0/1)
    scores = np.clip(scores, -30, 30)
    scores = 1.0 / (1.0 + np.exp(-scores))  # sigmoid

    keep = scores > SCORE_THRESH
    if not np.any(keep):
        return []

    boxes_norm = decode_boxes(regressors, _ANCHORS, INPUT_SIZE)[keep]
    scores_kept = scores[keep]

    # boxes theo pixel cua anh 128x128 (sau letterbox), dung cho NMS
    boxes_px = (boxes_norm * INPUT_SIZE).astype(np.float32)
    nms_boxes = [
        [x1, y1, x2 - x1, y2 - y1] for x1, y1, x2, y2 in boxes_px
    ]
    idxs = cv2.dnn.NMSBoxes(nms_boxes, scores_kept.tolist(),
                             SCORE_THRESH, IOU_THRESH)
    if len(idxs) == 0:
        return []
    idxs = np.array(idxs).flatten()

    h_reg, w_reg = region.shape[:2]
    results = []
    for i in idxs:
        x1, y1, x2, y2 = boxes_px[i]
        # bo pad + chia lai theo scale de ve toa do cua region
        x1 = (x1 - pad_x) / scale
        y1 = (y1 - pad_y) / scale
        x2 = (x2 - pad_x) / scale
        y2 = (y2 - pad_y) / scale

        x1 = max(0.0, x1); y1 = max(0.0, y1)
        x2 = min(float(w_reg), x2); y2 = min(float(h_reg), y2)
        if x2 > x1 and y2 > y1:
            results.append((x1, y1, x2, y2, float(scores_kept[i])))
    return results


def generate_windows(h, w):
    """Sinh cac cua so vuong, chong lan, o nhieu ty le (WINDOW_SCALES) de
    phu het anh -> giup bat duoc ca mat lon lan mat nho."""
    short_side = min(h, w)
    seen = set()
    for scale in WINDOW_SCALES:
        size = int(round(short_side * scale))
        size = min(size, h, w)
        if size < MIN_WINDOW_PX:
            continue
        stride = max(1, int(round(size * (1 - WINDOW_OVERLAP))))

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


def detect_faces(image, net):
    """Quet da ty le tren toan anh, gop tat ca box lai roi NMS toan cuc.
    Tra ve list (x1, y1, x2, y2, score) theo toa do anh goc."""
    h_orig, w_orig = image.shape[:2]

    all_boxes = []
    all_scores = []
    for x0, y0, win_w, win_h in generate_windows(h_orig, w_orig):
        region = image[y0:y0 + win_h, x0:x0 + win_w]
        for x1, y1, x2, y2, score in detect_faces_in_region(region, net):
            all_boxes.append([x0 + x1, y0 + y1, x2 - x1, y2 - y1])  # xywh
            all_scores.append(score)

    if not all_boxes:
        return []

    # NMS toan cuc de gop cac box trung nhau phat hien tu nhieu window
    idxs = cv2.dnn.NMSBoxes(all_boxes, all_scores, SCORE_THRESH, GLOBAL_IOU_THRESH)
    if len(idxs) == 0:
        return []
    idxs = np.array(idxs).flatten()

    results = []
    for i in idxs:
        x, y, bw, bh = all_boxes[i]
        x1, y1, x2, y2 = x, y, x + bw, y + bh

        # no rong them margin cho de crop dep hon
        x1 -= bw * MARGIN / 2
        y1 -= bh * MARGIN / 2
        x2 += bw * MARGIN / 2
        y2 += bh * MARGIN / 2

        x1 = int(max(0, x1)); y1 = int(max(0, y1))
        x2 = int(min(w_orig, x2)); y2 = int(min(h_orig, y2))
        if x2 > x1 and y2 > y1:
            results.append((x1, y1, x2, y2, float(all_scores[i])))
    return results


def main():
    if len(sys.argv) < 2:
        print("Cach dung: python crop_face_blazeface.py <duong_dan_anh>")
        sys.exit(1)

    img_path = sys.argv[1]
    image = cv2.imread(img_path)
    if image is None:
        print(f"Khong doc duoc anh: {img_path}")
        sys.exit(1)

    net = cv2.dnn.readNetFromTFLite(MODEL_PATH)
    faces = detect_faces(image, net)

    if not faces:
        print("Khong phat hien khuon mat nao.")
        return

    for i, (x1, y1, x2, y2, score) in enumerate(faces):
        crop = image[y1:y2, x1:x2]
        out_path = f"face_{i}.jpg"
        cv2.imwrite(out_path, crop)
        print(f"Face {i}: box=({x1},{y1},{x2},{y2}) score={score:.2f} -> {out_path}")


if __name__ == "__main__":
    main()
