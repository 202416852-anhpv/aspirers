# BUP-02: AI Design Compliance Checker — Prompt bàn giao cho Claude Code

*Tài liệu này tổng hợp toàn bộ quyết định thiết kế đã chốt qua phiên brainstorm trước khi code. Đọc kỹ trước khi viết bất kỳ dòng code nào — mọi quyết định ở đây đã được cân nhắc trade-off, không phải giả định tùy tiện.*

---

## 0. Bối cảnh & ràng buộc dự án

- Đây là 1 trong các đề hackathon (BUP-02), triển khai **tách biệt** khỏi hệ thống marketing-copy multi-agent đã có sẵn trong repo.
- **Tái dùng từ hệ cũ**: `config.py`, `knowledge_loader.py` (pattern `load_policy_context(platform, country)` — fallback-safe, không raise), FastAPI app structure, client gọi Claude qua OpenAI-compatible endpoint.
- **KHÔNG đụng vào**: `marketing_copy/agents.py`, `cv_service.py`, `media_services.py` — giữ nguyên, không liên quan tới bài toán này.
- **Cấu trúc thư mục bắt buộc**:
```
project/
├── config.py                    # tái dùng
├── knowledge_loader.py          # tái dùng + mở rộng thêm load_trend_context()
├── main.py                      # thêm route mới, giữ route cũ
├── marketing_copy/              # KHÔNG ĐỘNG VÀO
└── compliance_checker/          # code mới hoàn toàn cho BUP-02
    ├── schema.py              # Pydantic models cho MỌI input/output giữa các agent —
    │                          # bắt buộc, để giữ đúng kiểu dữ liệu đã chốt (vd confidence:
    │                          # float ở output OpenCV vs string ở suspected_logos từ Vision)
    ├── agents.py              # CHỈ định nghĩa Agent 1-4: prompt + gọi LLM.
    │                          # KHÔNG chứa asyncio.gather ghép nối — xem orchestrator.py
    ├── orchestrator.py        # process_one_design(), process_batch() — nơi asyncio.gather
    │                          # thật sự nằm (mục 8), tách khỏi agents.py vì khác trách nhiệm
    ├── opencv_modules.py      # match_character, match_logo, extract_fonts
    ├── black_box.py           # threshold theo category + aggregation
    ├── trademark_resolver.py  # flag_suspicious_phrases, query 2-lớp exact→fuzzy, cache batch
    │                          # (mục 4) — thuần Python/HTTP, tách khỏi agents.py
    ├── file_loader.py         # DesignFileLoader — hợp nhất PNG/JPG/PSD/PDF về 1 ảnh PIL,
    │                          # gọi tới pdf_processor.py khi cần
    ├── pdf_processor.py       # PDFProcessor — CHỈ lo nhánh PDF (digital-native vs scanned)
    ├── link_normalizer.py     # normalize_url_to_bytes — GDrive/Dropbox/S3/direct
    ├── csv_batch.py           # Parser CSV theo file mẫu BGK + row-level fault isolation
    └── knowledge_base/
        ├── niche_taxonomy.json
        ├── blacklist_hardcoded.json
        ├── niche_to_nice_class.json
        ├── trademark_top1000.json
        ├── character_list.md
        ├── celebrity_list.md
        ├── artwork_list.md
        ├── font_watchlist.md
        ├── logo_refs/{brand}.png + manifest
        ├── anime_character_refs/{character}/*.png
        ├── policies/{platform}_{country}.md
        └── trends/{country}.md
```
- Nguyên tắc CLAUDE.md của repo: chỉ sửa file đã có, KHÔNG tự tạo file/folder mới trừ khi người dùng waive tường minh. Với nhánh `compliance_checker/`, **người dùng đã waive tường minh** — được phép tạo toàn bộ cấu trúc trên.
- ⚠️ Không hardcode/bịa data trademark — chỉ dùng nguồn thật (USPTO/EUIPO), có field `last_updated` + `source` trong mọi file data.

---

## 1. Input đầu vào — 3 cách bắt buộc + chuẩn hóa

### 1.1 Link normalization (dùng `httpx`)
```python
async def normalize_url_to_bytes(url: str) -> bytes:
    # Google Drive: parse file_id từ /d/{id}/view → https://drive.google.com/uc?export=download&id={id}
    # Dropbox: đổi dl=0 → dl=1
    # S3 / direct image URL: httpx.get(url) thẳng
    # follow_redirects=True bắt buộc cho GDrive/Dropbox
```

### 1.2 File loader đa format (chuẩn hóa mọi thứ về ảnh PIL trước khi vào pipeline)
```python
class DesignFileLoader:
    def load_as_image(self, file_path: str) -> Image.Image:
        # .png/.jpg/.jpeg/.webp/.bmp → Image.open() trực tiếp
        # .pdf → PDFProcessor (xem mục 1.3, xử lý đặc biệt)
        # .psd → psd_tools.PSDImage.open().composite()
        # .svg → cairosvg.svg2png() (chỉ nếu cần, bonus thấp)
    def to_base64(self, image: Image.Image) -> str
```
Bắt buộc: PNG/JPG. Bonus: PDF/PSD. Deprioritize: AI/EPS (quá phức tạp, ROI thấp).

### 1.3 PDF — xử lý 2 nhánh dựa trên loại
```python
def detect_pdf_type(page) -> str:
    text = page.get_text().strip()
    return "digital_native" if len(text) > 10 else "scanned_flat"

class PDFProcessor:
    def process(self, pdf_path: str) -> dict:
        # LUÔN render trang đầu → ảnh (fitz.Matrix(2,2) để nét) → dùng cho Vision
        # NẾU digital_native: trích thêm text layer thật qua page.get_text("blocks")
        #   → có bbox pixel CHÍNH XÁC (x0,y0,x1,y1), tốt hơn grid 3x3 của ảnh thường
        #   → dùng để match trademark trực tiếp bằng Python, KHÔNG cần Vision OCR lại
        # NẾU scanned_flat: coi như ảnh thường, để Vision tự OCR trong Agent 1
        return {
            "pdf_type": ..., "full_page_image": ..., 
            "native_text": ..., "text_blocks_with_bbox": ..., "embedded_images": ...
        }
```
Output cuối luôn merge về chung 1 shape (ảnh base64 + text kèm nguồn gốc `"pdf_native"` hoặc `"vision_ocr"`) để phần còn lại của pipeline không cần biết input gốc là gì.

### 1.4 CSV batch — theo file mẫu BGK (không phải schema tự do)
- ⚠️ **QUAN TRỌNG**: BGK có file mẫu cố định (Google Sheet đã cho link trong brief mục 4.4) — cần đọc file mẫu thật để map ĐÚNG tên cột output, không đoán.
- Input-side vẫn nên linh hoạt alias tên cột (`file_path`/`path`/`url`/`image_url`...) vì giám khảo test live có thể tự tạo CSV theo ý họ.
- **Row-level fault isolation bắt buộc**: 1 dòng lỗi (link chết, file 404) KHÔNG được làm sập cả batch — luôn try/except từng row, trả `{"status": "ERROR", "error": ...}` cho dòng đó, tiếp tục các dòng khác.
- Dùng `csv.DictReader`, encoding `utf-8-sig` (để đọc đúng file Excel xuất ra có BOM).

---

## 2. Kiến trúc Agent — 4 agent, dependency rõ ràng

### Sơ đồ tổng quan
```
Agent 1 (Vision, có ảnh)
    │  output: niche, style, motifs, OCR_text, suspected_logos[]
    ▼
    ├──────────────┬──────────────┬─────────────────┐
    ▼              ▼              ▼                 ▼
Agent 2         match_logo    match_character   trademark-text
(Vision:        (OpenCV,      (OpenCV,          resolver
character+      dùng          độc lập,          (Python + 
celebrity)      suspected_    không cần         live API,
                logos làm     suspect list)      xem mục 4)
                input)
    │              │              │                 │
    └──────────────┴──────────────┴─────────────────┘
                        ▼
              [Nhóm C — LLM tổng hợp]
              nhận toàn bộ evidence, viết "định vị" 
              (vị trí bằng lời) + citation nguồn
                        ▼
                   Black Box (Python, threshold cứng)
                   → tag: SAFE / RISKY / BLOCKED
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
      Agent 3 (reasoning +   Agent 4 (market suggestion,
      fix suggestion,        text-only KHÔNG cần ảnh,
      cần ảnh context)       chạy song song Agent 3,
                              PHẢI có return_exceptions
                              để không làm sập verdict)
              └─────────┬─────────┘
                        ▼
                  Merge → Output final
```

### 2.1 Agent 1 — Classify (Vision, có ảnh)
**Prompt phải yêu cầu output JSON gồm:**
- `niche`, `style`, `motifs` (đối chiếu với `niche_taxonomy.json` đã tiêm — 10 niche + 10 style hardcoded, nhưng Vision KHÔNG bị giới hạn chỉ 10 cái này, phải luôn tự do classify kể cả niche lạ ngoài danh sách)
- `OCR_text`: toàn bộ text OCR được (Vision tự OCR, KHÔNG dùng Tesseract/PaddleOCR — xem mục 6)
- `suspected_logos`: list `{"brand_name": str, "confidence": "low"|"medium"|"high"}` — tiêm `brand_names = list(logo_manifest.keys())` vào prompt dạng TEXT (chỉ tên, KHÔNG tiêm path ảnh vì Vision không tự mở file được), cộng thêm câu "hoặc brand nổi tiếng khác nếu nhận ra ngoài danh sách". Liệt kê tối đa ~5, ưu tiên confidence cao nhất — không ép cứng đúng 5.
- ⚠️ KHÔNG hỏi về character/celebrity ở Agent 1 — việc này dời hẳn sang Agent 2 để tránh trùng lặp.

**Python filter ngay sau khi nhận response Agent 1** (không cần thêm call):
```python
suspected_logos = [item for item in raw_vision_output if item["confidence"] in ("medium", "high")]
# Bỏ "low" — thường là nhiễu. Giữ cả "medium" + "high" (không chỉ "high") 
# vì logo cách điệu/1 phần dễ chỉ đạt "medium" trong đánh giá Vision — 
# bỏ sót ở đây là false negative nguy hiểm hơn false positive.
```

**Fallback niche ngoài hardcoded**: nếu `niche` detect ra không nằm trong `niche_taxonomy.json`, vẫn phải chạy check `global_dangerous_motifs` (universal, không phụ thuộc niche) — KHÔNG được "mù" chỉ vì niche lạ.

### 2.2 Agent 2 — Character + Celebrity (Vision, có ảnh, KHÔNG hỏi về logo nữa)
**Prompt yêu cầu:**
```
1. Nhân vật hoạt hình/truyện tranh có bản quyền: liệt kê MỌI tên nghi ngờ (kể cả không chắc)
2. Người nổi tiếng: liệt kê tên celeb/athlete/chính trị gia nghi ngờ
Với mỗi mục, ghi độ tự tin (high/medium/low) — KHÔNG tự lọc bỏ nếu chỉ medium/low, 
để bước sau (đối chiếu danh sách + embedding) quyết định.
```
Output: `suspected_characters[]`, `suspected_celebrities[]` → Python đối chiếu tên celeb với `celebrity_list.md`.

⚠️ KHÔNG làm face-recognition/biometric matching cho người nổi tiếng — chỉ đối chiếu TÊN. Rủi ro đạo đức/quyền riêng tư không đáng đánh đổi.

### 2.3 OpenCV modules — 3 hàm độc lập, xem mục 3 (contract chi tiết)

### 2.4 Nhóm C — Tổng hợp + định vị (1 LLM call)
Nhận toàn bộ evidence từ Agent 2 + 3 module OpenCV + kết quả trademark-text (mục 4).
Output: mô tả vị trí bằng LỜI, dùng grid 3x3 (`top-left`/`center`/`bottom-right`/...) — KHÔNG cố làm bounding box pixel chính xác qua Vision (Vision không đáng tin ở mức tọa độ pixel). NGOẠI LỆ: nếu nguồn là PDF digital-native, dùng bbox pixel thật đã trích ở mục 1.3, không cần grid ước lượng.

**Citation rule (bắt buộc)**:
- ✅ ĐƯỢC: cite theo dạng "matched against pre-compiled database (USPTO/EUIPO, last updated {date})"
- ✅ ĐƯỢC cite số đăng ký cụ thể CHỈ KHI live API trả về thật (data verify qua nguồn thật)
- ❌ KHÔNG BAO GIỜ để LLM tự sinh số đăng ký/case number nếu không tra cứu — vi phạm ràng buộc "không bịa data" của brief

### 2.5 Black Box — Threshold theo category (Python thuần, không LLM)
```python
CATEGORY_THRESHOLDS = {
    "nsfw":                  {"blocked_min": 30, "risky_min": 15},  # nhạy, safety-first
    "weapons_violence":      {"blocked_min": 40, "risky_min": 20},  # nhạy tương tự
    "character_similarity":  {"blocked_min": 88, "risky_min": 65},  # chặt, tránh false positive
    "logo_similarity":       {"blocked_min": 82, "risky_min": 55},
    "trademark_text":        {"blocked": "exact_match_only", "risky": "partial_match"},  # nhị phân
}
```
Nguyên tắc: category càng nguy hiểm khi BỎ SÓT (NSFW, vũ khí) → threshold thấp. Category càng dễ FALSE POSITIVE (character/logo similarity qua embedding) → threshold cao.
⚠️ Đây là số khởi điểm để CODE ĐƯỢC NGAY — PHẢI tune lại sau khi test trên ảnh thật (xem mục 9).

**Aggregation across nhiều category:**
```python
def aggregate_final_verdict(category_results: dict) -> dict:
    severity_order = {"SAFE": 0, "RISKY": 1, "BLOCKED": 2}
    final_tag = max(category_results.values(), key=lambda x: severity_order[x["tag"]])["tag"]
    triggering_evidence = {k: v for k, v in category_results.items() if v["tag"] != "SAFE"}
    return {"final_verdict": final_tag, "evidence": triggering_evidence}
    # evidence PHẢI giữ TẤT CẢ category không SAFE (không chỉ 1) — 
    # để Agent 3 viết fix_suggestion cho từng vi phạm riêng biệt nếu có nhiều
```

**Overall confidence score**: lấy confidence của category nghiêm trọng nhất đã quyết định verdict cuối; nếu evidence rỗng (toàn SAFE) → confidence mặc định cao (~95).

### 2.6 Agent 3 — Reasoning + fix suggestion (cần ảnh, chạy song song Agent 4)
Nhận toàn bộ `evidence` dict (không chỉ 1 tag) từ black box. Nếu verdict RISKY/BLOCKED, với MỖI mục vi phạm sinh `fix_suggestion` cụ thể, hành động được (vd: "Thay logo Nike bằng icon tự thiết kế khác"). Đây là gap đã phát hiện thiếu so với brief mục 4.3 ("gợi ý cách sửa") — bắt buộc phải có.

### 2.7 Agent 4 — Market/Platform suggestion (text-only, KHÔNG cần ảnh, độc lập hoàn toàn)
```python
async def call4_market(niche: str, style: str) -> dict:
    # KHÔNG gửi image_base64 — chỉ cần niche/style đã có từ Agent 1, rẻ hơn nhiều
    # Tiêm TOÀN BỘ policy + trend của các quốc gia/platform (US/EU/JP × Etsy/Amazon/TikTok/Shopify)
    # → phần tiêm này gần như KHÔNG đổi giữa các design trong batch → ứng viên tốt cho prompt caching
    # Output: {"top_country_suggestion": str, "top_platform_suggestion": str, "rationale": str}
```
Chạy song song Agent 3 qua `asyncio.gather(..., return_exceptions=True)` — nếu lỗi, verdict chính vẫn nguyên vẹn, chỉ thiếu field phụ này (KHÔNG được để lỗi ở đây làm sập pipeline chính).

Vị trí thực thi tối ưu: có thể bắt đầu Agent 4 ngay sau Agent 1 (chạy song song Agent 2), vì Agent 4 không phụ thuộc black box — nhưng do là text-only nên luôn nhanh hơn nhánh Vision, latency tổng không đổi dù đặt ở đâu trong 2 vị trí hợp lệ này.

---

## 3. OpenCV modules — Contract chính xác (bàn giao cho dev OpenCV, họ code độc lập ở workspace riêng)

**Nguyên tắc chung cho cả 3 hàm**: nhận `image_path` (string), trả `dict` JSON-serializable, KHÔNG BAO GIỜ raise exception ra ngoài (mọi lỗi phải catch, trả rỗng), field kiểu số/string đã chốt CHÍNH XÁC như dưới — không được lẫn lộn.

```python
def match_character(image_path: str) -> dict:
    """
    Output: {"matches": [{"character_name": str, "confidence": float}, ...]}
    LUÔN đúng 3 phần tử (top 3), sắp xếp confidence giảm dần, confidence là số 0-100.
    Nếu ảnh lỗi/không đọc được: {"matches": []}
    KHÔNG trả tọa độ/bounding box.
    """

def match_logo(image_path: str, suspected_logos: dict) -> dict:
    """
    Input suspected_logos: {"suspected_logos": [{"brand_name": str, "confidence": str}, ...]}
        confidence ở INPUT là STRING ("low"/"medium"/"high", từ Agent 1/Vision)
        → module CHỈ lấy brand_name, KHÔNG dùng field confidence này để tính toán gì
        → mỗi brand_name map tới file logo_refs/{brand_name_normalized}.png 
          (chuẩn hóa: lowercase, space→underscore, bỏ ký tự đặc biệt)
        → nếu 1 brand_name KHÔNG có ảnh reference trong manifest: bỏ qua, không raise lỗi
    Output: {"matches": [{"brand_name": str, "confidence": float}, ...]}
        confidence ở OUTPUT là FLOAT (0-100, cosine similarity module tự tính)
        Số lượng = số brand_name có ảnh reference hợp lệ — KHÔNG giới hạn cứng ở 5,
        input bao nhiêu xử lý bấy nhiêu (KHÔNG tự quét toàn manifest nếu input rỗng)
    """

def extract_fonts(image_path: str) -> dict:
    """
    Output: {"fonts_detected": [{"font_family_guess": str, "sample_text": str, "confidence": str}, ...]}
        confidence là STRING ("low"/"medium"/"high") — module này KHÔNG so khớp ảnh 
        reference nên không có số đo %, chỉ đánh giá định tính
        LIỆT KÊ TOÀN BỘ vùng chữ phát hiện được, KHÔNG giới hạn số lượng (khác 2 hàm trên)
        font_family_guess: mô tả kiểu chữ chung (vd "bold sans-serif"), KHÔNG cần tên 
        font thương mại chính xác tuyệt đối
    Nếu ảnh không có chữ: {"fonts_detected": []}
    Luôn kèm theo (ở tầng orchestrator, không phải trong hàm này) disclaimer cố định:
        "Font detection is best-effort. Recommend manual verification against 
        font license databases (MyFonts, Adobe Fonts, Font Squirrel)."
    """
```

Bảng quy tắc kiểu dữ liệu confidence (dễ nhớ khi bàn giao):
| Field | Kiểu | Vì sao |
|---|---|---|
| `match_character` output | float | Có cosine similarity thật |
| `match_logo` input (`suspected_logos`) | string | Từ Vision, chỉ cảm nhận định tính |
| `match_logo` output | float | OpenCV tự tính similarity thật |
| `extract_fonts` output | string | Không có reference để so khớp % |

Anime character reference dataset: `anime_character_refs/{character_name}/*.png` (2-3 ảnh/nhân vật — official art + anime still + merchandise, để embedding ổn định hơn 1 ảnh duy nhất).

---

## 4. Trademark text — 2 lớp: static trước, live search chỉ cho case nghi ngờ

### 4.1 Static base (luôn chạy trước, free, không phụ thuộc network)
`trademark_top1000.json` — top 500-1000 phrase phổ biến nhất, crawl 1 lần từ USPTO TESS bulk data + EUIPO eSearch TRƯỚC hackathon (không phải real-time lúc demo). Có field `last_updated`, `source`.

### 4.2 Tách cụm nghi ngờ từ OCR_text (Python thuần, KHÔNG cần LLM, chạy song song Agent 2)
```python
def flag_suspicious_phrases(ocr_text: str, static_trademark_db: dict) -> list:
    candidates = extract_candidate_phrases(ocr_text)  # tách câu, cụm 2-6 từ
    flagged = []
    for phrase in candidates:
        static_match = check_against_static_list(phrase, static_trademark_db)
        if static_match["confidence"] >= 80:
            flagged.append({"phrase": phrase, "source": "static", **static_match})
        elif looks_like_slogan(phrase):  # heuristic rẻ: 2-6 từ, có viết hoa, không có số
            flagged.append({"phrase": phrase, "source": "needs_live_check"})
    return flagged

def looks_like_slogan(phrase: str) -> bool:
    words = phrase.split()
    return 2 <= len(words) <= 6 and not phrase.islower() and not any(c.isdigit() for c in phrase)
```

### 4.3 Live search — CHỈ cho cụm "needs_live_check", map Nice Class trước khi query
```python
NICHE_TO_NICE_CLASS = {  # trong niche_to_nice_class.json
    "apparel_design": [25], "mug_sticker_design": [21], 
    "poster_wall_art": [16], "phone_case": [9],
}
async def query_trademark_precise(phrase: str, nice_classes: list) -> dict:
    # Lớp 1: exact match trước — nếu có hit, dừng, confidence cao (~95)
    # Lớp 2: CHỈ fallback sang fuzzy/phonetic nếu exact rỗng
    # Fuzzy match LUÔN map tối đa RISKY, KHÔNG BAO GIỜ tự động BLOCKED 
    # (tránh false positive từ trùng ngẫu nhiên)
```
Cache trong phạm vi 1 batch run (dict Python đơn giản, không cần Redis) để tránh query trùng phrase nhiều lần.
Timeout ngắn (2-3s) + fallback về static nếu live API fail/timeout — KHÔNG BAO GIỜ để cả pipeline phụ thuộc network để chạy được (đúng ràng buộc "phải chạy được trên máy giám khảo").

### 4.4 Ảnh trademark — ĐÃ QUYẾT ĐỊNH BỎ QUA live search
Không có nguồn public API miễn phí đáng tin cho visual trademark search (dịch vụ thật như Corsearch là trả phí). Chỉ dùng: `logo_refs/` manifest tĩnh (embedding, mục 3) + Vision zero-shot. Case không chắc chắn và không có trong manifest → dừng ở RISKY, note "cần review thủ công", KHÔNG cố tìm thêm nguồn xác nhận ảnh.

---

## 5. Policy + Trend — tách 2 trục độc lập, KHÔNG gộp chung file

```
knowledge_base/policies/{platform}_{country}.md   # vd: etsy_us.md, tiktok_us.md
knowledge_base/trends/{country}.md                # vd: us_trends.md — DÙNG CHUNG mọi platform
```
Lý do tách: policy và trend có chu kỳ update khác nhau, quan hệ nhiều-nhiều (1 trend US áp dụng như nhau dù bán trên Etsy hay Amazon — gộp theo platform sẽ trùng lặp vô nghĩa).
```python
def load_trend_context(country: str) -> str:
    # Y HỆT pattern load_policy_context đã có sẵn — fallback rỗng, KHÔNG raise
    path = f"knowledge_base/trends/{country.lower()}_trends.md"
    if not os.path.exists(path): return ""
    ...
```

---

## 6. OCR — Quyết định cuối: Claude Vision, KHÔNG dùng Tesseract/PaddleOCR

Lý do: 0 dependency deploy, gộp chung 1 call với niche/style/logo detection (không tốn call riêng), robust hơn với tiếng Việt và background phức tạp. PaddleOCR (~50MB model) chỉ đáng cân nhắc LÀM SAU (P2, nice-to-have) nếu còn dư thời gian, dùng làm lớp bổ trợ CHỈ để lấy bounding box pixel chính xác cho text (không dùng để OCR content lại — tránh trùng việc với Vision).

---

## 7. requirements.txt (đã trim từ pip freeze gốc)

```txt
# Web framework
fastapi==0.141.1
uvicorn==0.52.1
python-multipart==0.0.32
pydantic==2.13.4
pydantic-settings==2.15.0
python-dotenv==1.2.2
# LLM client
openai==2.53.0
anthropic==0.121.0
# HTTP / Link fetching
httpx==0.28.1
requests==2.34.2
# Image processing — CHỈ giữ 1 trong 2 opencv, khuyến nghị contrib (đủ module cv2.dnn)
opencv-contrib-python==4.10.0.84
numpy==2.3.5
pillow==12.2.0
# PDF
pymupdf==1.28.2
# PSD (nếu làm bonus)
psd-tools
# Batch report
openpyxl==3.1.5
pandas==3.0.5
# Trend (nếu dùng pytrends)
pytrends==4.9.2
# JSON utilities
json_repair==0.63.0
python-dateutil==2.9.0.post0
```
⚠️ ĐÃ LOẠI: toàn bộ chain `paddleocr`/`paddlex`/`pyclipper`/`shapely`/`python-bidi` (không dùng OCR ngoài Vision), `aistudio_sdk`/`bce-python-sdk`/`modelscope*` (kéo theo từ paddle, không dùng trực tiếp), `torch`/`torchvision`/`torchaudio` (không cần cho `cv2.dnn.readNetFromONNX` — CHỈ giữ lại torch nếu dev OpenCV xác nhận dùng hướng CLIP embedding thay vì ONNX thuần).
Test cài trên venv sạch với `--no-cache-dir`, đo thời gian bằng `Measure-Command` (PowerShell) hoặc `time` (bash) — brief yêu cầu README hướng dẫn chạy ≤10 phút, cover cả Windows lẫn Linux/Mac.

---

## 8. Concurrency & Batch

```python
async def process_one_design(image_base64, image_path):
    classify = await call1_classify(image_base64)
    
    # Mọi nhánh KHÔNG phụ thuộc lẫn nhau chạy song song trong CÙNG 1 design:
    agent2_result, logo_match, char_match, trademark_result, market = await asyncio.gather(
        call2_character_celebrity(image_base64),
        match_logo(image_path, classify["suspected_logos"]),      # OpenCV
        match_character(image_path),                               # OpenCV, độc lập hoàn toàn
        resolve_trademark_phrases(classify["OCR_text"], classify["niche"]),
        call4_market(classify["niche"], classify["style"]),        # text-only, rẻ
        return_exceptions=True
    )
    
    evidence = black_box_aggregate(agent2_result, logo_match, char_match, trademark_result)
    reasoning = await call3_reasoning(evidence)  # cần ảnh, chạy SAU black box
    
    return merge(evidence, reasoning, market)

async def process_batch(design_list, max_concurrency=5):
    semaphore = asyncio.Semaphore(max_concurrency)
    async def with_limit(item):
        async with semaphore:
            return await process_one_design(item)
    results = await asyncio.gather(*[with_limit(d) for d in design_list], return_exceptions=True)
    # Exception ở 1 design KHÔNG được làm hỏng cả batch — catch riêng từng cái
```
Quy tắc: Call 1 → Call 2 trong CÙNG 1 design bắt buộc TUẦN TỰ (Call 2 cần niche/OCR từ Call 1). Giữa CÁC design khác nhau trong batch: chạy SONG SONG (đã thiết kế `asyncio.gather` + `Semaphore` giới hạn concurrency, KHÔNG chạy tuần tự — brief ước tính batch 15-20 design cần ~20-60s nếu đúng, ~2-4 phút nếu tuần tự sai là quá chậm cho demo).

---

## 9. Điều CHƯA làm / cần làm ngay khi bắt tay code

1. **Threshold ở mục 2.5 là số khởi điểm tự nghĩ** — PHẢI chạy thử trên ≥20-30 ảnh thật đa dạng (không phải ảnh tự tạo) để đo false positive/negative rate thật rồi tune lại. Đây là bottleneck lớn nhất cho 40đ "độ chính xác verdict" — không phải logic aggregation (đã coi là ổn).
2. **File mẫu CSV thật của BGK** (link Google Sheet trong brief mục 4.4) — cần đọc trước khi code phần map cột output, không đoán tên cột.
3. **API USPTO/EUIPO thật** (mục 4.3) — cần tra docs xác nhận endpoint/format/rate-limit trước khi code `query_trademark_precise()`, vì hiểu biết hiện tại có thể đã lỗi thời.
4. **UI/Frontend** — do người khác trong nhóm phụ trách, giả định làm tốt, không nằm trong scope của Claude Code lần này trừ khi được giao thêm.
5. **Font module** (`extract_fonts`) và **2 module OpenCV còn lại** — do dev OpenCV code ở workspace riêng theo đúng contract mục 3, sau đó bàn giao file để refactor/tích hợp — KHÔNG tự ý code lại thuật toán bên trong các hàm này.
6. Xác nhận đã rotate API key bị lộ trong sự cố `sed` trước đó (nếu chưa, nhắc lại).

---

## 10. Nguyên tắc xuyên suốt cần Claude Code tuân thủ khi viết code

- Python quyết định số/threshold cứng, LLM chỉ giải thích/reasoning — KHÔNG để LLM tự quyết định GO/NO-GO nhị phân.
- Mọi module (OpenCV lẫn LLM call) không được raise exception phá pipeline — luôn catch, trả rỗng/error field, dùng `return_exceptions=True` trong mọi `asyncio.gather`.
- KHÔNG hardcode/bịa data trademark, KHÔNG để LLM tự sinh citation cụ thể (số đăng ký) trừ khi lấy từ nguồn thật.
- Ưu tiên false negative thấp cho category nguy hiểm (NSFW, vũ khí — threshold thấp), ưu tiên false positive thấp cho category dễ nhầm (character/logo similarity — threshold cao).
- Mọi field JSON kiểu dữ liệu phải nhất quán đúng như contract đã chốt (float vs string) — không tự ý đổi khi code.


### Ngoại lệ cố định: compliance_checker/data/

Ngoài tiền lệ "waive tường minh theo từng việc cụ thể" đã nêu ở trên, thư mục
`compliance_checker/data/` là NGOẠI LỆ CỐ ĐỊNH, không cần hỏi lại mỗi lần:

- Claude ĐƯỢC PHÉP tự tạo, ghi đè, cập nhật MỌI file bên trong
  `compliance_checker/data/` mà không cần xin phép từng lần — đây là khu vực
  chứa dữ liệu tham chiếu (niche taxonomy, blacklist, trademark list, policy,
  trend, logo/character reference...) và bản chất cần được Claude tự thu thập,
  refresh định kỳ.
- Phạm vi CHỈ giới hạn trong `compliance_checker/data/` và các thư mục con của
  nó. Không áp dụng ngoại lệ này cho bất kỳ nơi nào khác trong repo.
- Claude ĐƯỢC PHÉP dùng web_search/web_fetch để lấy thông tin thật (USPTO,
  EUIPO, Etsy/Amazon/TikTok/Shopify policy, danh sách nhân vật/celeb/logo phổ
  biến...) và ghi trực tiếp vào file trong thư mục này — không cần dán nội
  dung ra ngoài rồi chờ người dùng copy-paste thủ công.
- Mọi file dữ liệu được Claude tạo/cập nhật trong thư mục này PHẢI có 2 field
  bắt buộc: `"source"` (nguồn gốc thông tin, URL nếu có) và `"last_updated"`
  (ngày thu thập) — để tránh vi phạm ràng buộc "không hardcode/bịa data" của
  brief hackathon.
- Ràng buộc "không lệnh phá huỷ" vẫn áp dụng bình thường — được tạo/cập nhật,
  KHÔNG được xoá hàng loạt (`rm -rf`) trong thư mục này mà không xác nhận.



  ### Cấu trúc compliance_checker/ (BUP-02)

project/
├── config.py                    # dùng chung, không sửa logic cốt lõi
├── knowledge_loader.py          # dùng chung + mở rộng load_trend_context()
├── main.py                      # thêm route mới cho compliance_checker, giữ route cũ
├── marketing_copy/              # hệ thống cũ — KHÔNG ĐỘNG VÀO
└── compliance_checker/          # code mới cho BUP-02
    ├── schema.py
    ├── agents.py
    ├── orchestrator.py
    ├── opencv_modules.py
    ├── black_box.py
    ├── trademark_resolver.py
    ├── file_loader.py
    ├── pdf_processor.py
    ├── link_normalizer.py
    ├── csv_batch.py
    └── data/                    # ← NGOẠI LỆ tạo file tự do (xem mục 1 ở trên)
        ├── niche_taxonomy.json
        ├── blacklist_hardcoded.json
        ├── niche_to_nice_class.json
        ├── trademark_top1000.json
        ├── character_list.md
        ├── celebrity_list.md
        ├── artwork_list.md
        ├── font_watchlist.md
        ├── logo_refs/
        ├── anime_character_refs/
        ├── policies/
        └── trends/

Mọi file code (.py) bên ngoài compliance_checker/data/ vẫn tuân theo quy tắc
gốc: chỉ sửa file đã có trong danh sách trên, không tự thêm file/module mới
ngoài danh sách này nếu chưa được xác nhận.