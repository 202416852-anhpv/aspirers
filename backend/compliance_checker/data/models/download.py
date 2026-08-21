"""download.py — Tai model embedding ONNX (~9.2MB) dung cho
compliance_checker/opencv_modules.py (match_character / match_logo).

Model: ShuffleNet V2 x1.0, pretrained tren ImageNet-1000, export tu
ONNX Model Zoo chinh thuc (onnx/models). Day la model TONG QUAT (khong
train rieng cho anime/logo) - dung output 1000-d truoc softmax lam
"embedding" xap xi de tinh cosine similarity. Load duoc thang qua
cv2.dnn.readNetFromONNX() - dung yeu cau "chi can cv2.dnn, khong can
torch" o CLAUDE.md muc 7.

Da verify thuc te truoc khi ban giao script nay (khong doan suong):
  - URL tra ve dung file nhi phan ONNX that (content-type application/octet-stream),
    KHONG phai text pointer cua git-lfs (loi thuong gap voi raw.githubusercontent.com).
  - Content-Length header = 9,218,554 bytes, khop file tai ve thuc te.
  - cv2.dnn.readNetFromONNX() load thanh cong, forward() ra dung shape (1, 1000).

Chay: python download.py [--force]
Output: shufflenet-v2-10.onnx (~9.2MB) + manifest.json (source/last_updated
        theo dung quy dinh bat buoc cua CLAUDE.md cho moi file trong data/).
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import httpx

MODEL_URL = (
    "https://media.githubusercontent.com/media/onnx/models/main/"
    "validated/vision/classification/shufflenet/model/shufflenet-v2-10.onnx"
)
MODEL_NAME = "shufflenet-v2-10.onnx"
SOURCE_REPO = "https://github.com/onnx/models/tree/main/validated/vision/classification/shufflenet"
# Verify qua HEAD request thuc te luc viet script nay (2026-08-21) - neu file goc
# tren GitHub doi kich thuoc sau nay, script van tai duoc nhung se in canh bao.
EXPECTED_SIZE_BYTES = 9_218_554

MODELS_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODELS_DIR / MODEL_NAME
MANIFEST_PATH = MODELS_DIR / "manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_model(force: bool = False) -> Path:
    if MODEL_PATH.exists() and not force:
        size = MODEL_PATH.stat().st_size
        if size == EXPECTED_SIZE_BYTES:
            print(f"[skip] {MODEL_NAME} da ton tai va dung kich thuoc ({size:,} bytes).")
            return MODEL_PATH
        print(f"[warn] {MODEL_NAME} da ton tai nhung sai kich thuoc "
              f"({size:,} != {EXPECTED_SIZE_BYTES:,}) - tai lai.")

    print(f"Dang tai {MODEL_NAME} tu ONNX Model Zoo...")
    print(f"  URL: {MODEL_URL}")

    tmp_path = MODEL_PATH.with_suffix(".onnx.part")
    downloaded = 0
    with httpx.stream("GET", MODEL_URL, follow_redirects=True, timeout=60.0) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", EXPECTED_SIZE_BYTES))
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                pct = downloaded / total * 100 if total else 0
                print(f"\r  {downloaded:,}/{total:,} bytes ({pct:5.1f}%)", end="", flush=True)
    print()

    tmp_path.replace(MODEL_PATH)

    final_size = MODEL_PATH.stat().st_size
    if final_size != EXPECTED_SIZE_BYTES:
        print(f"[warn] Kich thuoc tai ve ({final_size:,}) khac kich thuoc da verify luc viet "
              f"script ({EXPECTED_SIZE_BYTES:,}) - file goc tren GitHub co the da doi, "
              f"kiem tra lai thu cong truoc khi dung.")

    sha256 = _sha256(MODEL_PATH)
    manifest = {
        "source": SOURCE_REPO,
        "download_url": MODEL_URL,
        "last_updated": date.today().isoformat(),
        "model_file": MODEL_NAME,
        "size_bytes": final_size,
        "sha256": sha256,
        "architecture": "ShuffleNet V2 x1.0 (ImageNet-1000 pretrained classifier, dung lam feature extractor)",
        "input_contract": "NCHW float32 [1,3,224,224], RGB, normalize theo chuan torchvision "
                           "ImageNet (mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])",
        "output_contract": "[1, 1000] float32 - dung truc tiep lam embedding xap xi 1000-d "
                            "cho cosine similarity (xem test.py de biet cach dung)",
        "note": "Model ImageNet tong quat, KHONG train rieng cho anime/logo. Day la diem "
                "khoi dau de dev OpenCV co san pipeline chay duoc ngay; co the thay bang "
                "model khac (vd CLIP embedding) mien giu dung contract "
                "match_character()/match_logo() da chot o CLAUDE.md muc 3.",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[ok] Da tai xong: {MODEL_PATH} ({final_size:,} bytes, sha256={sha256[:16]}...)")
    print(f"[ok] Ghi manifest: {MANIFEST_PATH}")
    return MODEL_PATH


if __name__ == "__main__":
    download_model(force="--force" in sys.argv)
