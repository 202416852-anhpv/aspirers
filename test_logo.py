"""
test.py
-------
Cho phép người dùng nhập đường dẫn ảnh (hoặc thư mục ảnh) từ bàn phím
để kiểm tra model YOLOv8n đã train phát hiện logo.

Cách chạy:
    python test.py

Sau đó chương trình sẽ hỏi:
    - Đường dẫn tới file weights (mặc định: runs_logo/yolov8n_logo/weights/best.pt)
    - Đường dẫn ảnh cần kiểm tra (có thể nhập nhiều lần liên tục)

Gõ "exit" hoặc "q" để thoát chương trình.
"""

import os
from ultralytics import YOLO


DEFAULT_WEIGHTS = "runs_logo/yolov8n_logo/weights/best.pt"
OUTPUT_DIR = "test_results"


def load_model(weights_path: str) -> YOLO:
    if not os.path.exists(weights_path):
        raise FileNotFoundError(f"Không tìm thấy file weights: {weights_path}")
    print(f"Đang tải model từ: {weights_path}")
    return YOLO(weights_path)


def test_image(model: YOLO, image_path: str, conf: float = 0.25):
    if not os.path.exists(image_path):
        print(f"❌ Không tìm thấy file: {image_path}\n")
        return

    results = model.predict(
        source=image_path,
        conf=conf,
        save=True,
        project=OUTPUT_DIR,
        name="predict",
        exist_ok=True,
    )

    for r in results:
        num_boxes = len(r.boxes)
        if num_boxes == 0:
            print(f"➡️  {os.path.basename(image_path)}: KHÔNG phát hiện logo nào.")
        else:
            print(f"➡️  {os.path.basename(image_path)}: phát hiện {num_boxes} logo")
            for i, box in enumerate(r.boxes):
                conf_score = float(box.conf[0])
                x1, y1, x2, y2 = [round(float(v), 1) for v in box.xyxy[0]]
                print(f"     - Logo {i+1}: confidence={conf_score:.2f}, "
                      f"toạ độ=({x1}, {y1}, {x2}, {y2})")

        print(f"     Ảnh kết quả đã lưu tại: {r.save_dir}\n")


def main():
    weights_path = input(
        f"Nhập đường dẫn file weights (Enter để dùng mặc định '{DEFAULT_WEIGHTS}'): "
    ).strip()
    if not weights_path:
        weights_path = DEFAULT_WEIGHTS

    conf_str = input("Nhập ngưỡng confidence (Enter để dùng mặc định 0.25): ").strip()
    conf = float(conf_str) if conf_str else 0.25

    model = load_model(weights_path)

    print("\nNhập đường dẫn ảnh cần kiểm tra (gõ 'exit' hoặc 'q' để thoát).")
    print("Có thể nhập đường dẫn tới 1 ảnh hoặc 1 thư mục chứa nhiều ảnh.\n")

    while True:
        image_path = input("Đường dẫn ảnh: ").strip().strip('"')

        if image_path.lower() in ("exit", "q", "quit"):
            print("Kết thúc chương trình.")
            break

        if not image_path:
            continue

        test_image(model, image_path, conf)


if __name__ == "__main__":
    main()
