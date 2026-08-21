# Frontend Integration Guide — BUP-02 Design Compliance Checker

Tài liệu này chỉ mô tả luồng hiện tại (BUP-02) — hệ chat/marketing-copy cũ (audit bài viết, sinh campaign, gen video/ảnh) không còn nằm trong phạm vi sử dụng của repo, không mô tả ở đây nữa.

Đọc file này + `compliance_checker/schemas.py` + `main.py` là đủ — không cần đọc `agents.py`/`orchestrator.py` (đó là "hộp đen" nội bộ).

**Nguyên tắc cốt lõi**: Backend **hoàn toàn stateless** — mỗi request độc lập, không cần giữ state gì giữa các lần gọi.

---

## 1. Danh sách endpoint

| Method | Path | Gửi lên | Nhận về |
|---|---|---|---|
| GET | `/health` | — | `{"status":"ok"}` |
| POST | `/api/compliance/check` | JSON: đúng 1 trong 3 `image_base64`/`file_path`/`url` | `DesignComplianceResult` (mục 3) |
| POST | `/api/compliance/check-upload` | multipart: `file` + form fields | `DesignComplianceResult` |
| POST | `/api/compliance/batch-csv` | multipart: `file` (CSV **hoặc XLSX**) + form fields | Batch report JSON + `csv_export` (text CSV) |
| POST | `/api/compliance/batch-json` | JSON: `csv_content` (text CSV thô) | Batch report JSON |

---

## 2. Gửi gì lên — 3 cách nhập

| Cách nhập | Endpoint | Khi nào dùng |
|---|---|---|
| Upload file trực tiếp (multipart) | `POST /api/compliance/check-upload` | Form upload thường (`<input type="file">`) — khuyên dùng mặc định |
| Base64 hoặc link (JSON) | `POST /api/compliance/check` | Đã có ảnh base64 sẵn trong JS, hoặc dán link Google Drive/Dropbox/URL ảnh trực tiếp |
| Batch nhiều ảnh (CSV) | `POST /api/compliance/batch-csv` (multipart) hoặc `POST /api/compliance/batch-json` (JSON) | Kiểm tra hàng loạt nhiều design 1 lần |

### 2.1 `check-upload` — form fields

```
file: <binary, bắt buộc>           // .png/.jpg/.jpeg/.webp/.bmp bắt buộc hỗ trợ; .pdf hỗ trợ; .psd hỗ trợ nếu server có cài psd-tools (mục 6)
platform: string, optional         // "etsy"/"amazon"/"tiktok"/"shopify" — chỉ ảnh hưởng market_suggestion, KHÔNG ảnh hưởng verdict
target_country: string, default "US"
niche_hint: string, optional       // gợi ý niche nếu FE/user đã biết trước
```

### 2.2 `check` — JSON body

```ts
{
  image_base64?: string,   // base64 thuần HOẶC kèm prefix "data:image/...;base64," — cả 2 đều nhận được
  file_path?: string,      // đường dẫn server-side, chỉ dùng test nội bộ, KHÔNG dùng cho FE thật
  url?: string,             // Google Drive / Dropbox / S3 / link ảnh trực tiếp
  platform?: string, target_country?: string, niche_hint?: string,
}
```

Đúng 1 trong 3 field `image_base64`/`file_path`/`url` — thiếu cả 3 → HTTP 422 `{"detail": "Cần ít nhất 1 trong 3: image_base64, file_path, url"}`.

---

## 3. Nhận về gì — `DesignComplianceResult`

```ts
{
  niche: string, style: string, motifs: string[],
  OCR_text: string,
  suspected_logos: { brand_name: string, confidence: "low"|"medium"|"high" }[],
  suspected_characters: { name: string, confidence: "low"|"medium"|"high" }[],
  suspected_celebrities: { name: string, confidence: "low"|"medium"|"high" }[],

  final_verdict: "SAFE" | "RISKY" | "BLOCKED",   // Python tính cứng theo threshold, KHÔNG phải LLM tự chấm
  overall_confidence: number,                     // 0-100
  evidence: {                                      // CHỈ chứa category KHÔNG SAFE — rỗng {} nghĩa là hoàn toàn an toàn
    [category: string]: { tag: "RISKY"|"BLOCKED", confidence: number, detail: string }
    // category có thể là: character_similarity, logo_similarity, trademark_text, nsfw, weapons_violence, celebrity_likeness
  },

  positioning_notes: { category: string, location_description: string, citation: string }[],
  reasoning: string,                // đoạn văn giải thích verdict, LLM viết dựa trên evidence (không tự đổi verdict)
  fix_suggestions: { violation: string, suggestion: string }[],   // 1 gợi ý sửa / 1 category vi phạm

  market_suggestion: { top_country_suggestion: string, top_platform_suggestion: string, rationale: string } | null,
  font_disclaimer: string,          // luôn có, text cố định — hiện kèm mọi kết quả

  source_type: "image" | "pdf_digital_native" | "pdf_scanned" | "psd" | "unknown",
  warnings: string[],               // 1 nhánh phụ lỗi tạm thời — verdict chính vẫn tin được, chỉ thiếu field phụ
}
```

**Render gợi ý:**
- Badge màu theo `final_verdict` (SAFE=xanh, RISKY=vàng, BLOCKED=đỏ).
- `evidence` rỗng → không cần hiện thêm gì. Không rỗng → liệt kê từng category kèm `detail`; mỗi category thường có 1 `fix_suggestions[i]` tương ứng (khớp qua chuỗi tên, không đảm bảo cùng thứ tự index).
- `warnings` không rỗng → hiện 1 dòng cảnh báo phụ nhỏ, KHÔNG chặn UI, verdict chính vẫn hiển thị bình thường.
- `market_suggestion` có thể `null` nếu bước đó lỗi — luôn check trước khi render.

---

## 4. Batch — `batch-csv` (multipart, CSV hoặc XLSX) / `batch-json` (JSON, CSV text)

`batch-csv` form fields: `file` (**CSV hoặc XLSX**, bắt buộc — tự nhận theo đuôi file) + `platform`/`target_country`/`max_concurrency` (optional). `batch-json` JSON body: `{csv_content: string, platform?, target_country?, max_concurrency?}` (chỉ nhận CSV text, không nhận XLSX vì XLSX là binary).

Cột input linh hoạt alias, không phân biệt hoa/thường: `file_path`/`path`/`url`/`link`/`image_url`/**`design`** (cột thật trong file mẫu BGK — tự nhận là url nếu bắt đầu `http`, ngược lại là file_path), `platform`, `target_country`/**`target_market`**, `niche_hint`.

### Self-grading — có file mẫu THẬT từ BGK

`backend/compliance_checker/test_pdf_images_link/design_samples_template.xlsx` là file batch mẫu THẬT ban giám khảo cung cấp — 30 test case, mỗi dòng có sẵn đáp án mẫu (`expected_niche`, `expected_sub_niche`, `expected_style`, `expected_motifs`, `expected_verdict`, `expected_violation_type`, `expected_violation_detail`, `expected_confidence`, `notes`). Cột `design` (ảnh/link thật) đang TRỐNG trong file gốc — cần điền ảnh thật vào cột này trước khi chạy để có kết quả thật.

**Điền ảnh vào cột `design` bằng CÁCH NÀO cũng được** — backend hỗ trợ cả 2 kiểu giám khảo hay dùng:
1. Gõ/dán 1 link ảnh hoặc đường dẫn file dạng TEXT vào cell (đọc qua giá trị cell bình thường).
2. **Dán ảnh trực tiếp vào cell** (Ctrl+C từ đâu đó rồi Ctrl+V thẳng vào Excel — cách BGK/giám khảo hay làm nhất khi thao tác thủ công) — Excel lưu kiểu này thành 1 "hình nổi" neo tại vị trí ô, KHÔNG phải giá trị text của cell, nên phải đọc riêng qua `ws._images` (đã cài, xem `csv_batch.py::_extract_embedded_images_by_row`) — **đã test thật, hoạt động đúng** (mục 7).

Nếu input có cột `expected_verdict`, backend **tự so sánh** verdict thật với đáp án mẫu — đây chính là công cụ đo false positive/negative rate thật mà CLAUDE.md mục 9.1 yêu cầu ("PHẢI chạy thử trên ≥20-30 ảnh thật... để tune threshold"), giờ có sẵn khung câu hỏi, chỉ cần điền ảnh.

```ts
{
  total: number, safe_count: number, risky_count: number, blocked_count: number, error_count: number,
  graded_count: number,              // số dòng có cột expected_verdict VÀ đã chạy ra verdict (không tính dòng ERROR)
  verdict_accuracy: number | null,   // % verdict khớp đáp án mẫu — null nếu graded_count=0 (batch không có đáp án mẫu)
  rows: {
    row_index: number, input_ref: string,       // input_ref = file_path/url/design gốc của dòng, để đối chiếu ngược
    status: "OK" | "ERROR",
    result: DesignComplianceResult | null,       // null nếu status="ERROR"
    error: string | null,                         // 1 dòng lỗi KHÔNG làm hỏng cả batch
    grading?: {                                   // CHỈ có nếu input kèm cột expected_verdict (kể cả dòng ERROR — vẫn giữ đáp án mẫu để tham khảo, không tính vào verdict_accuracy)
      expected: { expected_verdict?: string, expected_niche?: string, ... },  // dict thô các cột expected_*/notes đọc được
      verdict_match: boolean,
    },
  }[],
  csv_export?: string,   // CHỈ có ở batch-csv — text CSV báo cáo (kèm 2 cột expected_verdict/verdict_match), FE tạo Blob rồi cho user tải xuống
}
```

⚠️ Đây LÀ file mẫu thật từ BGK nhưng là bộ **câu hỏi + đáp án** (dùng để BGK tự chấm/để nhóm tự tune), không chắc chắn là ĐÚNG format "file nộp bài" nhắc tới ở brief mục 4.4 (link Google Sheet riêng, vẫn chưa fetch được vì cần đăng nhập) — nếu 2 file khác nhau, tên cột `csv_export` có thể vẫn cần đối chiếu lại lần nữa trước khi nộp bài chính thức.

---

## 5. Giới hạn cần biết khi render kết quả

Phần so khớp ẢNH bằng embedding thật (`opencv_modules.py::match_character`/`match_logo`) **vẫn là placeholder** — đang chờ 1 thành viên hoàn thiện. Nhưng verdict KHÔNG còn phụ thuộc 100% vào phần đó nữa: Python đã đối chiếu TÊN brand/nhân vật/celeb (Vision tự nêu) với danh sách tham chiếu tĩnh (`logo_refs/manifest.json`, `character_list.md`, `celebrity_list.md`) — brand/tên **có** trong danh sách + Vision tự tin cao → có thể lên tới `BLOCKED`; brand/tên **lạ** (không có trong danh sách, vd đa số logo tài trợ/thương hiệu nhỏ) → tối đa `RISKY`, không tự động `BLOCKED` (tránh false positive từ 1 lần LLM đoán chưa xác nhận chéo). Ngoài ra: (b) khớp cụm từ trademark trong text, (c) từ khoá/motif nhạy cảm (kể cả quét OCR_text qua `blacklist_hardcoded.json`, không chỉ dựa vào motif Vision tự gắn). Một logo/nhân vật RÕ trong ảnh nhưng Vision không tự tin nêu tên vẫn có thể ra `SAFE` (chưa có xác nhận thị giác thật) — **đừng coi verdict là tuyệt đối**, luôn hiện kèm `reasoning`, không chỉ mỗi badge màu. Threshold hiện tại là số khởi điểm, có thể còn tinh chỉnh — không hardcode logic FE dựa trên giả định threshold cụ thể.

---

## 6. Thư viện backend cần cài thêm

**Đã có sẵn:** `fastapi`, `uvicorn`, `pydantic`/`pydantic-settings`, `openai`, `httpx`, `pymupdf` (`fitz`), `opencv-python`, `numpy`, `pillow`, `json-repair`, **`openpyxl`** (giờ CẦN THẬT — đọc file XLSX batch, xem mục 4; trước đây tưởng không cần vì output vẫn xuất CSV thuần, nhưng input giờ hỗ trợ XLSX) — đã kiểm tra import OK trên máy.

**Còn thiếu (optional, chỉ cần cho bonus PSD):**
```
pip install psd-tools
```

Không cần `pandas`/`pytrends` — trend đọc từ `.md` tĩnh, không gọi Google Trends API.

---

## 7. Trạng thái triển khai — đã test thật (2026-08-20)

Toàn bộ `compliance_checker/` (10 module + `data/`) đã code, compile, chạy test thật với API key thật trên ảnh/PDF/link mẫu thật, kể cả gọi qua HTTP (`TestClient`) cho cả 4 route.

**Bug/khoảng trống đã phát hiện + sửa trong quá trình test:**
1. `black_box.py::score_trademark_text` từng gắn `RISKY` cho MỌI cụm chữ viết hoa 2-6 từ dù chưa verify được với DB thật — sửa lại chỉ tính RISKY khi có bằng chứng fuzzy-match thật.
2. `character_list.md`/`celebrity_list.md` được tạo sẵn nhưng chưa có code đối chiếu — Agent 2 phát hiện đúng tên nhân vật/celeb nhưng KHÔNG ảnh hưởng verdict. Đã nối dây: Python đối chiếu tên, có trong danh sách + tự tin cao → có thể BLOCKED; tên lạ → tối đa RISKY. Verify bằng ảnh thật (nhân vật "Yuna" không có trong danh sách → đúng RISKY kèm giải thích).
3. `blacklist_hardcoded.json` (keyword NSFW/vũ khí/ma tuý/hate speech) chưa được đọc — giờ dùng làm lớp quét bổ sung trên `OCR_text`.
4. `marketing_copy/evaluator.py` — bug import có sẵn từ trước khiến `main.py` không chạy được, đã sửa 1 dòng (file này không còn dùng nữa nếu nhóm chốt bỏ hệ cũ — xem phần dọn dẹp bên dưới).
5. **(2026-08-20, phiên sau)** `logo_refs/manifest.json` — CÙNG lỗ hổng như #2 nhưng cho logo: `suspected_logos` (Agent 1) chưa từng được đối chiếu vào verdict, chỉ OpenCV placeholder (luôn rỗng) mới ảnh hưởng `logo_similarity`. Phát hiện thật: ảnh banner Gen.G có 3 logo tài trợ "high" confidence (LG UltraGear, Monster Energy, Logitech) nhưng verdict vẫn ra `SAFE`. Đã vá — `score_logo_identity()` đối chiếu brand_name với `logo_refs/manifest.json` (10 brand curated), cùng cơ chế cap-nếu-chưa-xác-nhận như character/celeb. Verify lại bằng đúng ảnh đó: verdict giờ đúng ra `RISKY` (logo lạ, chưa xác nhận — không tự động `BLOCKED`).
6. **(2026-08-20, phiên sau)** Thêm hỗ trợ đọc file `.xlsx` cho batch (`csv_batch.py::parse_xlsx_rows`) + tính năng self-grading khi input có cột `expected_verdict` (`verdict_accuracy`/`graded_count`/`grading` — xem mục 4) — dùng ngay được với file mẫu thật `design_samples_template.xlsx` do BGK cung cấp.
7. **(2026-08-20, phiên sau)** Thêm hỗ trợ ảnh **dán trực tiếp vào cell Excel** (Ctrl+C/Ctrl+V, không phải link/path text) — `values_only=True` (cách đọc cũ) bỏ sót hoàn toàn kiểu này vì ảnh dán là "hình nổi" neo tại vị trí ô, không phải giá trị cell. `parse_xlsx_rows()` giờ đọc thêm `ws._images`, khớp ảnh với đúng hàng qua toạ độ neo, tự dùng làm `image_base64` nếu cell không có text. Quá trình test phát hiện + vá thêm 2 bug THẬT không liên quan trực tiếp tính năng này nhưng chặn nó hoàn toàn:
   - **Bug che giấu lỗi thật**: nhiều `print()` log lỗi dùng emoji (⚠️/❌/⏳) làm tiền tố — trên Windows chạy `python main.py` bình thường (không set `PYTHONIOENCODING`), `print()` với emoji tự nó ném `UnicodeEncodeError` (console mặc định cp1252), NUỐT MẤT thông báo lỗi gốc (batch row hiện `"charmap codec can't encode..."` vô nghĩa thay vì lý do thật). Đã fix tận gốc 1 chỗ (`main.py`, đầu file): `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` — áp dụng cho toàn bộ log của app, không phải sửa rải rác từng `print()`.
   - **Bug MIME type sai**: `agents.py::_build_messages()` từng HARDCODE `"image/png"` cho mọi base64 không có prefix — "tình cờ đúng" bấy lâu vì upload/link đều đi qua `DesignFileLoader.to_base64()` (luôn re-encode PNG). Ảnh dán từ Excel giữ nguyên bytes gốc (JPEG), Anthropic API trả lỗi 400 "the image appears to be a image/jpeg image". Đã fix: `_sniff_image_mime()` tự nhận diện định dạng thật qua magic bytes (JPEG/PNG/WEBP/GIF/BMP) — sửa này áp dụng cho MỌI đường `image_base64`, không riêng ảnh dán Excel (bảo vệ luôn trường hợp FE gửi thẳng JPEG base64 thuần qua `/api/compliance/check`, trước đây cũng sẽ lỗi tương tự nếu gặp).
   - Đã verify lại bằng đúng ảnh Gen.G thật dán vào 1 file xlsx test: parse đúng, Vision đọc đúng, verdict `RISKY` đúng như qua đường file_path, self-grading khớp.
8. **(2026-08-20, phiên sau) PDF nhiều trang giờ được phân tích ĐẦY ĐỦ** — trước đây `pdf_processor.py` chỉ render/đọc trang ĐẦU TIÊN (`doc[0]`), các trang sau bị bỏ qua HOÀN TOÀN và không có cảnh báo gì (verdict trông như đã xem hết file). Đã sửa theo quyết định của nhóm (chấp nhận tốn thêm token/request để không bỏ sót vi phạm):
   - `PDFProcessor.process()` render MỌI trang (tới trần `_MAX_PAGES_TO_RENDER = 10`, tránh PDF quá dài làm request nặng — vượt trần vẫn xử lý được, chỉ cảnh báo qua `warnings` số trang bị bỏ qua).
   - TẤT CẢ ảnh trang được gửi CÙNG 1 lần gọi Agent 1/2/3 (nhiều `image_url` content-block/message, Anthropic hỗ trợ) — **KHÔNG tăng số lần gọi API theo số trang**, chỉ tăng kích thước/token của mỗi request. Mỗi ảnh có text marker `"--- Trang N/M ---"` để model biết thứ tự.
   - Text digital-native nối từ MỌI trang (`all_pages_native_text`, có đánh dấu trang) dùng để quét trademark, thay vì chỉ trang 1 (`native_text`, vẫn giữ lại để tương thích ngược).
   - `text_blocks_with_bbox` giờ có thêm field `"page"` (1-indexed) mỗi block — Nhóm C biết chính xác vi phạm text nằm trang nào khi định vị.
   - Ảnh dùng cho `opencv_modules.py` (OpenCV local_path) **vẫn chỉ là trang 1** — giữ đúng contract "1 image_path" đã chốt (CLAUDE.md mục 3), không đổi vì module đó vẫn là placeholder.
   - **Đã verify bằng test thật mô phỏng đúng rủi ro nhóm lo ngại**: tạo 1 PDF 2 trang (trang 1 = thiết kế an toàn thuần text, trang 2 = ảnh banner Gen.G có nhiều logo tài trợ) — verdict đúng ra `RISKY`, và `reasoning` trích dẫn rõ ràng "the second page shows a photograph... including 'LG UltraGear'" — chứng minh hệ thống thật sự nhìn thấy và phân tích cả trang 2, điều code cũ chắc chắn bỏ sót.
9. **(2026-08-21) Nhóm quyết định BỎ hướng `match_character`/`match_logo` embedding thật** (quá khó/tốn thời gian trong khung hackathon — cần model + curate ảnh reference `anime_character_refs/`/`logo_refs/`). 2 hàm đó giữ nguyên placeholder vĩnh viễn (không phải "chờ" nữa). Thay vào đó:
   - **Confidence không còn hiện ra UI** — `frontend/app.js` (`renderChipList`, evidence list, header) bỏ mọi hiển thị `%`/`(low|medium|high)`; số liệu confidence vẫn được tính và dùng nội bộ trong `black_box.py` như cũ, chỉ ngừng hiển thị cho người dùng cuối.
   - **`opencv_modules.py::detect_text_regions()` (MỚI, ĐANG HOẠT ĐỘNG THẬT)** — thay thế hướng embedding bằng kỹ thuật cổ điển MSER + morphological dilation + contour, KHÔNG cần model/dataset, khoanh vùng CÓ KHẢ NĂNG chứa chữ trên ảnh raster. Verify thật bằng ảnh tổng hợp (slogan "JUST DO IT" + text nhỏ) — merge đúng thành cụm theo dòng, không vỡ vụn theo từng ký tự; ảnh trắng/file lỗi trả rỗng đúng contract, không raise.
   - `orchestrator.py` gọi hàm này song song với các nhánh khác, gắn `bbox_norm` (toạ độ THẬT, Python tính — không phải LLM đoán) vào `positioning_note` category `trademark_text` (vùng chữ lớn nhất phát hiện được) — best-effort, không đảm bảo đúng CHÍNH XÁC cụm bị flag nếu ảnh có nhiều dòng chữ khác nhau.
   - `DesignComplianceResult` có thêm field `text_regions` (toàn bộ vùng chữ phát hiện, không gắn category) và `PositioningNote.bbox_norm`/`bbox_source` (chỉ có giá trị khi toạ độ THẬT, không phải ước lượng bằng lời).
   - `frontend/app.js` (`renderPositioningOverlay`) vẽ overlay khung lên ảnh preview phía client (object URL của file vừa upload, hoặc chính link đã nhập — backend không trả ảnh về): khung xanh = `text_regions` (tham khảo hình học chung), khung đỏ có nhãn = category đã khớp `bbox_norm` thật. PDF/PSD không preview được bằng `<img>` nên tự ẩn overlay (fallback về mô tả `location_description` bằng lời như cũ).
10. **(2026-08-21) Agent 1/Agent 2 THIẾT KẾ LẠI — tách "đoán" khỏi "xác nhận":**
    - **Agent 1** giờ xuất TOP 5 mỗi loại: `suspected_logos` + `suspected_characters` (MỚI, chuyển từ Agent 2) + `suspected_celebrities` (MỚI, chuyển từ Agent 2) — logic/prompt style giữ nguyên như `suspected_logos` cũ (candidate-generation rộng tay, không sợ đoán sai vì có bước verify sau).
    - **Agent 2** KHÔNG còn tự detect character/celebrity từ đầu nữa — giờ là bước VERIFY: nhận đúng danh sách candidate Agent 1 nêu (gộp cả 3 loại), nhìn lại ảnh, trả lời `present: true/false` + `reasoning` cho TỪNG mục (`run_agent2_verify_candidates`). Không có candidate nào -> khỏi gọi LLM (tiết kiệm 1 call cho ảnh sạch hoàn toàn).
    - `black_box.py::_apply_verification_filter()` lọc bỏ mục Agent 2 xác nhận `present=False` TRƯỚC khi cross-reference với danh sách tham chiếu (character_list.md/celebrity_list.md/logo_refs/manifest.json) — giảm false positive từ việc Agent 1 đoán rộng tay. Mục không có verification tương ứng (Agent 2 lỗi, hoặc đặt tên khác — xem ghi chú dưới) -> GIỮ NGUYÊN, fail-open.
    - `DesignComplianceResult` có thêm field `verifications` — FE (`buildVerificationMap`/`renderChipList`) gắn badge ✅/❌ cạnh mỗi tên nghi ngờ, **tuyệt đối không hiện số/%** (đúng yêu cầu của nhóm — mọi confidence chỉ dùng nội bộ cho black box).
    - **Verify thật bằng ảnh Gen.G banner** (`process_one_design` + validate qua `DesignComplianceResult` Pydantic): Agent 1 ra đúng 5 logo (LG UltraGear/Monster Energy/Logitech/GS/GENG), 0 character/celebrity (đúng — ảnh này không có). Agent 2 verify cả 5, verdict cuối vẫn `RISKY` đúng như hành vi cũ (không có gì bị mất oan).
    - ⚠️ **Hạn chế phát hiện được qua test thật**: Agent 2 đôi khi KHÔNG echo lại tên candidate y hệt (vd Agent 1 nêu `"GS (Korean brand)"`, Agent 2 lại verify `"YOUR.GG"` — 1 brand nó tự thấy rõ hơn thay vì trả lời đúng/sai cho tên đã cho) — vi phạm nhẹ chỉ dẫn "verify-only, không tự thêm mục mới" trong prompt. Hệ quả THỰC TẾ vô hại nhờ fail-open (`_apply_verification_filter`): mục không khớp tên đơn giản không có badge ✅/❌, KHÔNG bị lọc oan, KHÔNG crash — nhưng badge có thể thiếu ở 1 số case tên bị diễn đạt khác. Chưa fix (ngoài phạm vi yêu cầu hôm nay) — có thể cải thiện sau bằng fuzzy name-match thay vì exact-match nếu cần.
    - ⚠️ **Gap liên quan phát hiện thêm (KHÔNG phải do thay đổi hôm nay, có từ trước)**: Nhóm C tự đặt tên `category` cho `positioning_notes` tự do (vd thấy `"trademark_text_phrases"` thay vì đúng string `"trademark_text"` mà `orchestrator._inject_text_region_bbox()` đang so khớp CHÍNH XÁC) — nghĩa là tính năng gắn `bbox_norm` thật vào positioning_note (mục 9 ở trên) có thể ÍT KHI kích hoạt hơn dự kiến nếu Nhóm C không dùng đúng tên category. Chưa fix, cần ràng buộc rõ vocabulary category trong prompt Nhóm C nếu muốn tăng tỷ lệ khớp.

### Giới hạn còn lại — cần biết trước khi demo

1. `match_character`/`match_logo` vẫn là placeholder — **quyết định CUỐI, không triển khai nữa** (xem mục 9 ở trên). `detect_text_regions()` đã hoạt động thật, không phải placeholder.
2. `logo_refs/`/`anime_character_refs/` chưa có ảnh thật, chỉ có manifest/README mô tả cấu trúc.
3. `trademark_top1000.json` mới có ~90 phrase thật (curated thủ công), chưa đạt quy mô 500-1000.
4. Live USPTO lookup chưa test với API key thật (`USPTO_API_KEY`) — chưa có key thì tự động bỏ qua an toàn.
5. PSD chưa test được (thiếu `psd-tools` trên máy hiện tại).
6. Cột CSV output đã đối chiếu 1 phần với file mẫu THẬT từ BGK (`design_samples_template.xlsx`, mục 4) — nhưng chưa chắc đây là ĐÚNG format "file nộp bài" ở brief mục 4.4 (link Google Sheet riêng, vẫn chưa fetch được).
7. Threshold trong `black_box.py` chưa tune trên bộ ảnh thật đa dạng (≥20-30 ảnh, có đáp án đúng).
8. Batch chưa cache trademark query giữa các design cùng batch (hàm đã viết sẵn nhưng chưa được gọi).
---

## 8. Chạy thử nhanh

```bash
pip install psd-tools   # optional, chỉ cần cho PSD

python main.py          # hoặc: uvicorn main:app --reload

curl -X POST http://localhost:8000/api/compliance/check-upload \
  -F "file=@compliance_checker/test_pdf_images_link/Gen.G-banner.jpg" \
  -F "platform=etsy" -F "target_country=US"

curl -X POST http://localhost:8000/api/compliance/batch-csv -F "file=@your_batch.csv"

# Test với file mẫu THẬT của BGK (30 test case, cần điền cột "design" = path/link ảnh thật
# trước để có kết quả — hiện tại cột đó trống nên mọi dòng sẽ ERROR "thiếu input", đúng dự kiến)
curl -X POST http://localhost:8000/api/compliance/batch-csv \
  -F "file=@compliance_checker/test_pdf_images_link/design_samples_template.xlsx"
```

Có frontend test đơn giản (chat-style UI, không cần build) ở `../frontend/` — xem `frontend/README.md` để chạy.

---

## 9. Cấu trúc thư mục `compliance_checker/` (refactor 2026-08-21)

Refactor THUẦN cấu trúc thư mục (di chuyển/đổi tên file, gộp `main.py`'s route vào 1
`APIRouter`) — **KHÔNG đổi 1 dòng logic nào**: mọi prompt, threshold, algorithm, route
path, request/response schema giữ NGUYÊN 100%. Verify bằng cách so sánh `app.openapi()`
(toàn bộ path + request/response schema) TRƯỚC và SAU refactor — **byte-for-byte giống
hệt nhau** — cộng với `TestClient` smoke test (`/health`, lỗi 422 khi thiếu input).

```
backend/
├── main.py                        # CHỈ app bootstrap: CORS, startup check, include_router
├── config.py / knowledge_loader.py    # dùng chung, không đổi
└── compliance_checker/
    ├── schemas.py                 # data contract — giữ FLAT ở root (import xuyên suốt mọi module)
    ├── orchestrator.py            # process_one_design()/process_batch() — điểm vào chính,
    │                              #   giữ ở root (điều phối engine/ + ingestion/ bên dưới)
    ├── api/
    │   └── routes.py              # 4 route thật (thân hàm giữ nguyên 100%, chỉ đổi
    │                              #   @app.xxx("/api/compliance/...") -> @router.xxx("/...")
    │                              #   qua APIRouter(prefix="/api/compliance") — cùng URL cuối)
    ├── engine/                    # các module orchestrator.py điều phối (gọi LLM + tính toán)
    │   ├── agents.py              #   Agent 1-4 + Nhóm C
    │   ├── black_box.py           #   threshold + aggregation, thuần Python
    │   ├── opencv_modules.py      #   OpenCV cổ điển (detect_text_regions + 3 placeholder)
    │   └── trademark_resolver.py  #   tra cứu trademark 2 lớp
    ├── ingestion/                 # chuẩn hoá MỌI input về 1 shape chung
    │   ├── file_loader.py         #   entrypoint chính — PNG/JPG/PSD/PDF -> 1 ảnh PIL
    │   ├── pdf_processor.py       #   nhánh PDF riêng (digital-native vs scanned)
    │   ├── link_normalizer.py     #   URL (GDrive/Dropbox/S3/direct) -> bytes thô
    │   └── csv_batch.py           #   parser CSV/XLSX batch
    ├── data/                      # KHÔNG đổi (ngoại lệ ghi tự do, xem CLAUDE.md)
    └── test_pdf_images_link/      # KHÔNG đổi (fixture test/BGK)
```

**Vì sao `schemas.py`/`orchestrator.py` KHÔNG có subfolder riêng**: `schemas.py` được import
xuyên suốt gần như mọi module khác (agents/black_box/orchestrator/api routes) — gói riêng 1
folder chỉ thêm độ sâu import mà không tăng rõ ràng. `orchestrator.py` là "mặt tiền" của cả
package (thứ duy nhất `api/routes.py` gọi trực tiếp) — giữ nổi bật ở root, giống pattern
service/entrypoint ở root + internal collaborators trong subfolder của nhiều codebase FastAPI
production khác.

**Import cross-reference đã cập nhật** (chỉ những dòng này đổi, KHÔNG đổi gì trong thân hàm):
- `orchestrator.py`: `from compliance_checker.engine import agents/black_box/opencv_modules/trademark_resolver as ...`, `from compliance_checker.ingestion.file_loader/link_normalizer import ...`.
- `ingestion/file_loader.py`: `from compliance_checker.ingestion.pdf_processor import PDFProcessor`.
- `main.py`: `from compliance_checker.api.routes import router as compliance_router` (thay 3 import cũ + 4 hàm route).
- `engine/agents.py` (config.py/knowledge_loader.py): KHÔNG đổi — 2 import này resolve qua
  `sys.path` (chạy từ `backend/`), không phụ thuộc `agents.py` nằm sâu bao nhiêu cấp.
