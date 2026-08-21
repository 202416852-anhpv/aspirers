"""test.py — Test nhanh pipeline embedding: load model ONNX (tu download.py),
trich embedding cho mot tap anh, luu ra file de xem thu kich thuoc/hanh vi
thuc te truoc khi cam vao opencv_modules.py that.

Uu tien dung anh THAT trong data/anime_character_refs/{character}/*.png neu
da co; neu thu muc do con rong (mac dinh luc viet script nay - moi chi co
README.md placeholder), tu sinh anh test tong hop (hinh khoi mau, moi
"nhan vat gia" co nhieu bien the) de script chay duoc ngay khong phu thuoc
du lieu anh that.

QUAN TRONG: anh tong hop CHI de test pipeline (load model / preprocess /
forward / luu file dung shape), KHONG dung de danh gia do chinh xac that
cua match_character() - do can anh nhan vat that.

Chay: python test.py
Output: test_output/embeddings.npy         (~vai MB, xem NUM_SYNTHETIC_CHARACTERS)
        test_output/embeddings_meta.json   (label + metadata di kem)
"""
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import cv2
import numpy as np

MODELS_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODELS_DIR / "shufflenet-v2-10.onnx"
REFS_DIR = MODELS_DIR.parent / "anime_character_refs"
OUT_DIR = MODELS_DIR / "test_output"
INPUT_SIZE = 224

# Chuan torchvision ImageNet - xem manifest.json (ghi boi download.py) de biet
# vi sao mean o day la 0-255 scale (blobFromImage tru mean TRUOC khi nhan scalefactor).
IMAGENET_MEAN_RGB = (123.675, 116.28, 103.53)  # = (0.485, 0.456, 0.406) * 255
IMAGENET_STD_RGB = (0.229, 0.224, 0.225)

# Dieu chinh 2 so nay de doi kich thuoc file .npy khi CHUA co du anh that:
# embedding_dim(1000) x 4 byte(float32) x N anh = kich thuoc .npy.
# Mac dinh 250 nhan vat x 3 bien the = 750 anh -> ~750*4000 byte = ~2.9MB ("vai MB").
NUM_SYNTHETIC_CHARACTERS = 250
VARIANTS_PER_CHARACTER = 3  # dung contract "2-3 anh/nhan vat" o CLAUDE.md muc 3


def _preprocess(img_bgr: np.ndarray) -> np.ndarray:
    """anh BGR uint8 (kich thuoc bat ky) -> NCHW float32 blob dung input contract cua model.
    blobFromImage tu resize ve INPUT_SIZE nen khong can resize thu cong truoc."""
    blob = cv2.dnn.blobFromImage(
        img_bgr, scalefactor=1.0 / 255.0, size=(INPUT_SIZE, INPUT_SIZE),
        mean=IMAGENET_MEAN_RGB, swapRB=True, crop=False,
    )
    std = np.array(IMAGENET_STD_RGB, dtype=np.float32).reshape(1, 3, 1, 1)
    blob = blob / std
    return blob.astype(np.float32)


def _load_real_images() -> list:
    """Doc anh that trong anime_character_refs/{character}/*.{png,jpg} neu da co.
    Tra ve [(label, bgr_image), ...]."""
    out = []
    if not REFS_DIR.exists():
        return out
    for char_dir in sorted(p for p in REFS_DIR.iterdir() if p.is_dir()):
        paths = sorted(char_dir.glob("*.png")) + sorted(char_dir.glob("*.jpg")) + sorted(char_dir.glob("*.jpeg"))
        for img_path in paths:
            img = cv2.imread(str(img_path))
            if img is not None:
                out.append((char_dir.name, img))
    return out


def _make_synthetic_images() -> list:
    """Sinh anh tong hop (khoi mau + hinh dang, seed co dinh theo chi so nhan vat) mo
    phong N nhan vat x M bien the - CHI de test pipeline, KHONG phai data that."""
    out = []
    for i in range(NUM_SYNTHETIC_CHARACTERS):
        rng = np.random.default_rng(seed=i)
        base_color = rng.integers(0, 255, size=3)
        base_shape = int(rng.integers(0, 4))  # 0=circle,1=rect,2=triangle,3=lines
        for v in range(VARIANTS_PER_CHARACTER):
            img = np.full((INPUT_SIZE, INPUT_SIZE, 3), 30, dtype=np.uint8)
            jitter = rng.integers(-20, 20, size=3)
            color = tuple(int(c) for c in np.clip(base_color.astype(int) + jitter * v, 0, 255))
            if base_shape == 0:
                cv2.circle(img, (112, 112), 60 + v * 5, color, -1)
            elif base_shape == 1:
                cv2.rectangle(img, (40, 40), (184, 184 - v * 10), color, -1)
            elif base_shape == 2:
                pts = np.array([[112, 30 + v * 5], [30, 190], [194, 190]], np.int32)
                cv2.fillPoly(img, [pts], color)
            else:
                for k in range(5):
                    cv2.line(img, (0, k * 40 + v), (224, k * 40 + v), color, 8)
            out.append((f"synthetic_char_{i:03d}", img))
    return out


def main():
    if not MODEL_PATH.exists():
        print(f"[loi] Khong tim thay model: {MODEL_PATH}")
        print("Chay download.py truoc: python download.py")
        sys.exit(1)

    print(f"Dang load model: {MODEL_PATH.name}")
    net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))

    images = _load_real_images()
    if images:
        source = "anh that (anime_character_refs/)"
    else:
        print(f"[info] anime_character_refs/ dang rong -> sinh {NUM_SYNTHETIC_CHARACTERS} "
              f"nhan vat gia (x{VARIANTS_PER_CHARACTER} bien the) de test pipeline.")
        images = _make_synthetic_images()
        source = "anh tong hop (synthetic, KHONG phai data that)"

    print(f"Nguon anh: {source} - tong {len(images)} anh.")

    t0 = time.time()
    embeddings = []
    labels = []
    for idx, (label, img_bgr) in enumerate(images):
        blob = _preprocess(img_bgr)
        net.setInput(blob)
        out = net.forward()  # shape (1, 1000)
        embeddings.append(out.flatten().astype(np.float32))
        labels.append(label)
        if (idx + 1) % 50 == 0 or idx == len(images) - 1:
            print(f"\r  {idx + 1}/{len(images)} anh da embed...", end="", flush=True)
    print()
    elapsed = time.time() - t0

    emb_matrix = np.stack(embeddings)  # (N, 1000) float32
    print(f"Xong: {emb_matrix.shape[0]} embedding, dim={emb_matrix.shape[1]}, "
          f"thoi gian {elapsed:.1f}s ({elapsed / len(images) * 1000:.1f} ms/anh).")

    OUT_DIR.mkdir(exist_ok=True)
    npy_path = OUT_DIR / "embeddings.npy"
    meta_path = OUT_DIR / "embeddings_meta.json"
    np.save(npy_path, emb_matrix)
    meta_path.write_text(json.dumps({
        "source": source,
        "model": MODEL_PATH.name,
        "labels": labels,
        "embedding_dim": int(emb_matrix.shape[1]),
        "note": "File .npy nay chi de TEST kich thuoc/pipeline, KHONG phai manifest that "
                "dung cho match_character()/match_logo() trong opencv_modules.py.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    size_mb = npy_path.stat().st_size / (1024 * 1024)
    print(f"Da ghi: {npy_path} ({size_mb:.2f} MB)")
    print(f"Da ghi: {meta_path}")

    # Sanity check: cosine similarity giua 2 bien the CUNG 1 "nhan vat" phai cao hon
    # giua 2 nhan vat KHAC nhau -> xac nhan embedding co y nghia phan biet duoc.
    if len(images) >= 2 and labels[0] == labels[1]:
        v0, v1 = emb_matrix[0], emb_matrix[1]
        sim_same = float(np.dot(v0, v1) / (np.linalg.norm(v0) * np.linalg.norm(v1) + 1e-9))
        other_idx = next((i for i in range(len(labels)) if labels[i] != labels[0]), None)
        if other_idx is not None:
            v2 = emb_matrix[other_idx]
            sim_diff = float(np.dot(v0, v2) / (np.linalg.norm(v0) * np.linalg.norm(v2) + 1e-9))
            print("\nSanity check cosine similarity:")
            print(f"  cung nhan vat  ({labels[0]} vs {labels[1]}):         {sim_same:.4f}")
            print(f"  khac nhan vat  ({labels[0]} vs {labels[other_idx]}): {sim_diff:.4f}")
            if sim_same > sim_diff:
                print("  -> OK: embedding phan biet duoc cung/khac nhan vat (sim_same > sim_diff).")
            else:
                print("  -> CANH BAO: sim_same <= sim_diff. Voi anh SYNTHETIC don gian dieu nay "
                      "co the xay ra binh thuong (hinh khoi qua don gian de phan biet) - "
                      "KHONG ket luan gi ve chat luong model tren anh that tu day.")


if __name__ == "__main__":
    main()
