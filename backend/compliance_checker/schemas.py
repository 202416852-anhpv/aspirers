"""
compliance_checker/schemas.py — Pydantic models cho MỌI input/output giữa các agent/module
của BUP-02 (AI Design Compliance Checker).

Tách biệt HOÀN TOÀN khỏi schemas.py ở root (hệ marketing-copy cũ) — không import/không
tái sử dụng model nào từ đó, đúng nguyên tắc "triển khai tách biệt" trong CLAUDE.md mục 0.

⚠️ Kiểu dữ liệu confidence PHẢI đúng chính xác theo bảng contract trong CLAUDE.md mục 3 —
đây là điểm dễ nhầm nhất khi code: float ở nơi có so khớp số thật (OpenCV/live trademark),
string ("low"/"medium"/"high") ở nơi chỉ là cảm nhận định tính (Vision, font).
"""

from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]
Verdict = Literal["SAFE", "RISKY", "BLOCKED"]


# =====================================================================
# 1. AGENT 1 — CLASSIFY (Vision, có ảnh)
# =====================================================================

class SuspectedLogo(BaseModel):
    """confidence là STRING — cảm nhận định tính của Vision, KHÔNG phải số đo thật."""
    brand_name: str = Field(..., description="Tên brand Vision nghi ngờ nhận diện được")
    confidence: Confidence = Field(..., description="Độ tự tin định tính của Vision: low/medium/high")


class SuspectedCharacter(BaseModel):
    name: str = Field(..., description="Tên nhân vật hoạt hình/truyện tranh nghi ngờ")
    confidence: Confidence = Field(...)


class SuspectedCelebrity(BaseModel):
    name: str = Field(..., description="Tên người nổi tiếng/celeb/athlete/chính trị gia nghi ngờ")
    confidence: Confidence = Field(...)


class Agent1ClassifyResult(BaseModel):
    niche: str = Field(..., description="Niche chính detect được — KHÔNG giới hạn trong niche_taxonomy.json")
    style: str = Field(..., description="Style/phong cách thiết kế")
    motifs: List[str] = Field(default_factory=list, description="Chủ đề phụ/motif phát hiện được (kể cả global_dangerous_motifs)")
    OCR_text: str = Field(default="", description="Toàn bộ text OCR được bởi Vision (không dùng Tesseract/PaddleOCR)")
    suspected_logos: List[SuspectedLogo] = Field(default_factory=list, description="TOP 5 logo/brand nghi ngờ, ưu tiên confidence cao nhất")
    suspected_characters: List[SuspectedCharacter] = Field(
        default_factory=list,
        description="(2026-08-21) TOP 5 nhân vật nghi ngờ — CHUYỂN từ Agent 2 sang đây, cùng logic candidate-generation với suspected_logos. Agent 2 giờ chỉ verify lại list này."
    )
    suspected_celebrities: List[SuspectedCelebrity] = Field(
        default_factory=list,
        description="(2026-08-21) TOP 5 người nổi tiếng nghi ngờ — CHUYỂN từ Agent 2 sang đây, tương tự suspected_characters."
    )
    text_source: Literal["vision_ocr", "pdf_native"] = Field(
        default="vision_ocr",
        description="Nguồn gốc OCR_text — 'pdf_native' nếu lấy từ text layer PDF thật (chính xác hơn), 'vision_ocr' nếu Vision tự đọc ảnh"
    )


# =====================================================================
# 2. AGENT 2 — VERIFY CANDIDATES (Vision, có ảnh)
# =====================================================================
# ⚠️ (2026-08-21) THIẾT KẾ LẠI: Agent 2 KHÔNG còn tự detect character/celebrity từ đầu (việc
# đó dời sang Agent 1 — xem Agent1ClassifyResult ở trên). Agent 2 giờ là bước VERIFY: nhận
# đúng list candidate Agent 1 đã nêu (logo+character+celebrity gộp chung), nhìn lại ảnh và trả
# lời CÓ/KHÔNG cho từng mục — giảm false positive từ việc Agent 1 đoán rộng tay (top 5 luôn
# liệt kê kể cả không chắc). Kết quả nhị phân "present" — KHÔNG phải %, xem black_box.py
# ::_apply_verification_filter() và frontend/app.js (chỉ hiện ✅/❌, không hiện số).

class VerificationItem(BaseModel):
    category: Literal["logo", "character", "celebrity"]
    name: str = Field(..., description="Echo lại ĐÚNG tên candidate Agent 1 đã nêu (brand_name/name)")
    present: bool = Field(..., description="Agent 2 xác nhận: mục này CÓ THẬT SỰ xuất hiện trong ảnh hay không — quyết định nhị phân, KHÔNG phải điểm số")
    reasoning: str = Field(default="", description="1 câu giải thích ngắn cho phán đoán trực quan")


# (2026-08-21) FACE IDENTIFICATION — nhánh MỚI, độc lập với verifications ở trên. Ảnh mặt do
# engine/opencv_modules.py::detect_and_crop_faces() (BlazeFace, chỉ DETECT vị trí mặt, không
# định danh) cắt ra được gửi thẳng cho Agent 2 — Agent 2 tự nhận diện DANH TÍNH trực tiếp
# bằng vision zero-shot, theo đúng quyết định của nhóm "không so khớp database nữa, tin vào
# Claude" (khác hẳn suspected_celebrities/VerificationItem ở trên, vốn có cross-reference với
# celebrity_list.md — xem black_box.py::score_celebrity_likeness_from_faces()).
class FaceIdentification(BaseModel):
    face_index: int = Field(..., description="Vị trí ảnh crop trong danh sách gửi cho Agent 2 (0-based)")
    suspected_name: Optional[str] = Field(
        default=None,
        description="Agent 2 tự nhận diện — tên người nghi ngờ, hoặc None nếu KHÔNG nhận ra đây là ai (đa số mặt trong ảnh KHÔNG phải người nổi tiếng, Agent 2 được yêu cầu thành thật thay vì đoán bừa)"
    )
    confidence: Optional[Confidence] = Field(default=None, description="Độ tự tin ĐỊNH TÍNH của việc nhận diện — None nếu suspected_name None")
    reasoning: str = Field(default="", description="1 câu giải thích ngắn")


# (2026-08-21) TRADEMARK/SLOGAN SENSE-CHECK — nhánh MỚI thứ 3 của Agent 2, TEXT-ONLY (không
# cần ảnh — quyết định có chủ đích để tối ưu tốc độ/chi phí, xem agents.py::
# run_agent2_verify_candidates). Nhận text_blocks từ engine/opencv_modules.py::
# extract_text_blocks() (RapidOCR thật, có nội dung + bbox), Agent 2 tự ghép các block rời
# rạc + tự đánh giá bằng kiến thức riêng — KHÔNG giới hạn ở database tĩnh. Đây là nguồn THỨ 2,
# ĐỘC LẬP cho category trademark_text (nguồn 1 là match database THẬT, không đổi) — xem
# black_box.py::score_trademark_text_llm_sense(). Theo quyết định RÕ RÀNG của nhóm: suspicion
# "high" CÓ THỂ tự BLOCKED dù KHÔNG có bằng chứng database nào.
class TextTrademarkFlag(BaseModel):
    block_indexes: List[int] = Field(default_factory=list, description="block_index (trong text_blocks gửi cho Agent 2) mà Agent 2 dùng để ghép/nghi ngờ")
    phrase: str = Field(..., description="Cụm từ Agent 2 tự ghép nối/nghi ngờ — không nhất thiết verbatim từ 1 block duy nhất")
    suspicion: Confidence = Field(..., description="Mức nghi ngờ ĐỊNH TÍNH của riêng Agent 2 — KHÔNG phải kết quả tra database")
    reasoning: str = Field(default="")


class Agent2Result(BaseModel):
    verifications: List[VerificationItem] = Field(default_factory=list)
    face_identifications: List[FaceIdentification] = Field(default_factory=list)
    text_trademark_flags: List[TextTrademarkFlag] = Field(default_factory=list)


# =====================================================================
# 3. OPENCV MODULE CONTRACTS — xem opencv_modules.py (hiện là placeholder)
# =====================================================================

class CharacterMatch(BaseModel):
    """confidence là FLOAT — cosine similarity thật (khi module đã có thuật toán thật)."""
    character_name: str
    confidence: float = Field(..., ge=0.0, le=100.0)


class MatchCharacterResult(BaseModel):
    matches: List[CharacterMatch] = Field(default_factory=list, description="Luôn tối đa 3 phần tử, giảm dần theo confidence")


class LogoMatch(BaseModel):
    """confidence là FLOAT — cosine similarity thật (khi module đã có thuật toán thật)."""
    brand_name: str
    confidence: float = Field(..., ge=0.0, le=100.0)


class MatchLogoResult(BaseModel):
    matches: List[LogoMatch] = Field(default_factory=list)


class FontDetected(BaseModel):
    """confidence là STRING — không có ảnh reference để so khớp %."""
    font_family_guess: str
    sample_text: str
    confidence: Confidence


class ExtractFontsResult(BaseModel):
    fonts_detected: List[FontDetected] = Field(default_factory=list)


# =====================================================================
# 4. TRADEMARK TEXT RESOLVER
# =====================================================================

class TrademarkFlag(BaseModel):
    phrase: str
    source: Literal["static", "needs_live_check", "live_exact", "live_fuzzy", "live_failed_fallback_static"]
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    owner: Optional[str] = Field(default=None, description="Chủ sở hữu trademark nếu match được từ static DB/live API")
    nice_classes: List[int] = Field(default_factory=list)


class TrademarkResolutionResult(BaseModel):
    flagged: List[TrademarkFlag] = Field(default_factory=list)


# =====================================================================
# 5. BLACK BOX — threshold + aggregation (Python thuần, không LLM)
# =====================================================================

class CategoryResult(BaseModel):
    tag: Verdict
    confidence: float = Field(..., ge=0.0, le=100.0)
    detail: str = Field(default="", description="Bằng chứng cụ thể dẫn tới tag này (tên nhân vật/brand/phrase...)")


class BlackBoxVerdict(BaseModel):
    final_verdict: Verdict
    overall_confidence: float = Field(..., ge=0.0, le=100.0)
    evidence: dict[str, CategoryResult] = Field(default_factory=dict, description="MỌI category không SAFE, không chỉ 1 category")


# =====================================================================
# 6. NHÓM C — TỔNG HỢP + ĐỊNH VỊ
# =====================================================================

class PositioningNote(BaseModel):
    category: str = Field(..., description="Loại vi phạm (vd 'logo_similarity', 'character_similarity')")
    location_description: str = Field(..., description="Vị trí bằng lời (grid 3x3) hoặc bbox pixel thật nếu nguồn là PDF digital-native")
    citation: str = Field(..., description="Nguồn trích dẫn — KHÔNG BAO GIỜ là số đăng ký tự sinh nếu chưa tra cứu thật")

    bbox_norm: Optional[List[float]] = Field(
        default=None,
        description="[x0,y0,x1,y1] normalize 0-1 theo chiều rộng/cao ảnh — CHỈ có khi có toạ độ "
                    "thật (không phải LLM đoán), xem bbox_source. None nếu chỉ có location_description bằng lời."
    )
    bbox_source: Optional[Literal["opencv_mser", "pdf_native"]] = Field(
        default=None,
        description="Nguồn gốc bbox_norm: 'opencv_mser' = vùng chữ lớn nhất phát hiện bằng OpenCV "
                    "(hình học thuần, không đảm bảo đúng ĐÚNG cụm từ bị flag), 'pdf_native' = bbox "
                    "pixel thật trích từ text layer PDF digital-native. KHÔNG BAO GIỜ là toạ độ do LLM tự đoán."
    )


class SynthesisResult(BaseModel):
    positioning_notes: List[PositioningNote] = Field(default_factory=list)
    summary: str = Field(default="")


class TextRegion(BaseModel):
    """Vùng CÓ KHẢ NĂNG chứa chữ trên ảnh, phát hiện bằng opencv_modules.detect_text_regions()
    (MSER, thuần hình học — KHÔNG đọc nội dung chữ). Dùng để frontend vẽ overlay trực quan
    thay cho mô tả grid 3x3 bằng lời — xem CLAUDE.md phần định vị (mục 2.4)."""
    bbox_norm: List[float] = Field(..., description="[x0,y0,x1,y1] normalize 0-1")
    area_ratio: float = Field(..., ge=0.0, le=1.0, description="Diện tích vùng / diện tích ảnh")


class DetectedFace(BaseModel):
    """(2026-08-21) Merge của opencv_modules.detect_and_crop_faces() (bbox_norm) và
    Agent2Result.face_identifications (suspected_name + confidence) — orchestrator.py ghép 2
    nguồn theo face_index. Danh sách ĐẦY ĐỦ (kể cả mặt KHÔNG nhận diện được) để tham khảo/debug
    — FE KHÔNG hiện trực tiếp danh sách này nữa (không còn thumbnail crop), chỉ dùng
    flagged_regions bên dưới để vẽ overlay lên ảnh gốc. KHÔNG có field ảnh nào (face_base64 đã
    bỏ theo yêu cầu — không xuất khuôn mặt crop ra FE nữa)."""
    bbox_norm: List[float] = Field(..., description="[x0,y0,x1,y1] normalize 0-1 trên ảnh GỐC (chưa crop)")
    suspected_name: Optional[str] = Field(default=None, description="None nếu Agent 2 không nhận ra đây là ai cụ thể")
    confidence: Optional[Confidence] = Field(default=None, description="low/medium/high — KHÔNG có field số/% nào, đúng yêu cầu UI")
    reasoning: str = Field(default="")


class FlaggedRegion(BaseModel):
    """(2026-08-21) Danh sách RÚT GỌN, CHỈ gồm vùng ĐÁNG NGHI trên ảnh gốc (text nghi trademark
    HOẶC mặt Agent 2 nhận diện được) — để FE vẽ khung khoanh vùng thẳng lên ảnh gốc, KHÔNG còn
    hiện thumbnail crop riêng (theo đúng yêu cầu). Xây dựng THUẦN PYTHON (orchestrator.py) từ
    text_trademark_flags + detected_faces đã có bbox thật — KHÔNG phải LLM tự đoán toạ độ."""
    kind: Literal["text", "face"]
    bbox_norm: List[float] = Field(..., description="[x0,y0,x1,y1] normalize 0-1 trên ảnh GỐC")
    label: str = Field(..., description="kind=text: cụm từ bị nghi ngờ. kind=face: tên người bị nghi ngờ.")
    detail: str = Field(default="", description="Lý do/reasoning ngắn gọn")


# =====================================================================
# 7. AGENT 3 — REASONING + FIX SUGGESTION
# =====================================================================

class FixSuggestion(BaseModel):
    violation: str = Field(..., description="Mục vi phạm cụ thể đang được gợi ý sửa")
    suggestion: str = Field(..., description="Hành động sửa cụ thể, thực hiện được (vd 'Thay logo Nike bằng icon tự thiết kế khác')")


class Agent3Result(BaseModel):
    reasoning: str = Field(default="")
    fix_suggestions: List[FixSuggestion] = Field(default_factory=list)


# =====================================================================
# 8. AGENT 4 — MARKET/PLATFORM SUGGESTION (text-only)
# =====================================================================

class Agent4Result(BaseModel):
    top_country_suggestion: str = Field(default="", description="Gợi ý ĐỘC LẬP của Agent 4 — quốc gia tốt nhất theo Agent 4 tự đánh giá, KHÔNG nhất thiết trùng với target_country user chọn")
    top_platform_suggestion: str = Field(default="", description="Gợi ý ĐỘC LẬP — platform tốt nhất theo Agent 4 tự đánh giá, KHÔNG nhất thiết trùng với platform user chọn")
    rationale: str = Field(default="", description="Giải thích cho 2 field gợi ý độc lập ở trên")

    selected_platform_suitable: Optional[bool] = Field(
        default=None,
        description="Đánh giá RIÊNG cho đúng platform+target_country mà USER đã chọn (khác top_platform_suggestion — đây là thẩm định lựa chọn thật, không phải gợi ý). None nếu request không kèm platform (không có gì để thẩm định)."
    )
    selected_platform_rationale: str = Field(
        default="", description="Giải thích cho selected_platform_suitable — rỗng nếu selected_platform_suitable là None"
    )


# =====================================================================
# 9. OUTPUT CUỐI CÙNG CHO 1 DESIGN (merge toàn bộ pipeline)
# =====================================================================

class DesignComplianceResult(BaseModel):
    """
    [FE-FACING RESPONSE] Kết quả compliance-check hoàn chỉnh cho 1 design — trả về từ
    orchestrator.process_one_design(). FE render trực tiếp object này (verdict badge +
    breakdown + reasoning + fix suggestions).
    """
    niche: str = ""
    style: str = ""
    motifs: List[str] = Field(default_factory=list)
    OCR_text: str = ""
    suspected_logos: List[SuspectedLogo] = Field(default_factory=list)
    suspected_characters: List[SuspectedCharacter] = Field(default_factory=list)
    suspected_celebrities: List[SuspectedCelebrity] = Field(default_factory=list)
    verifications: List[VerificationItem] = Field(
        default_factory=list,
        description="(2026-08-21) Kết quả Agent 2 verify từng candidate ở trên — present true/false, "
                    "KHÔNG có field số nào. FE dùng để gắn ✅/❌ cạnh mỗi tên, tuyệt đối KHÔNG hiện %."
    )

    final_verdict: Verdict = "SAFE"
    overall_confidence: float = Field(default=95.0, ge=0.0, le=100.0)
    evidence: dict[str, CategoryResult] = Field(default_factory=dict)

    positioning_notes: List[PositioningNote] = Field(default_factory=list)
    detected_faces: List[DetectedFace] = Field(
        default_factory=list,
        description="(2026-08-21) Mọi khuôn mặt BlazeFace phát hiện được (kể cả không nhận diện "
                    "được), kèm Agent 2 tự nhận diện — danh sách ĐẦY ĐỦ, tham khảo/debug. FE dùng "
                    "flagged_regions bên dưới để vẽ overlay, KHÔNG render danh sách này trực tiếp."
    )
    flagged_regions: List[FlaggedRegion] = Field(
        default_factory=list,
        description="(2026-08-21) Danh sách RÚT GỌN vùng đáng nghi (text + face gộp chung) để FE "
                    "vẽ khung khoanh vùng lên ẢNH GỐC — thay thế hoàn toàn cách hiện thumbnail crop "
                    "riêng trước đây, đúng yêu cầu 'chỉ đưa ảnh gốc ra giao diện + khoanh vùng'."
    )
    reasoning: str = ""
    fix_suggestions: List[FixSuggestion] = Field(default_factory=list)

    market_suggestion: Optional[Agent4Result] = None

    font_disclaimer: str = Field(
        default="Font detection is best-effort. Recommend manual verification against font "
                "license databases (MyFonts, Adobe Fonts, Font Squirrel).",
        description="Disclaimer cố định, luôn kèm theo bất kể fonts_detected rỗng hay không"
    )

    source_type: Literal["image", "pdf_digital_native", "pdf_scanned", "psd", "unknown"] = "image"
    warnings: List[str] = Field(default_factory=list, description="Lỗi không nghiêm trọng xảy ra trong pipeline (vd 1 module OpenCV lỗi) — KHÔNG làm sập verdict chính")


# =====================================================================
# 10. BATCH (CSV / nhiều file)
# =====================================================================

class GradingInfo(BaseModel):
    """[FE-FACING] Self-grading — CHỈ có khi input kèm cột expected_verdict (vd file mẫu THẬT
    của BGK design_samples_template.xlsx, xem csv_batch.py). expected là dict thô các cột
    expected_*/notes đọc được từ file input, không ép kiểu cứng vì mỗi file mẫu có thể khác
    field một chút — verdict_match là bool duy nhất được tính tự động (so sánh chuỗi)."""
    expected: dict = Field(default_factory=dict)
    verdict_match: bool = False


class BatchRowResult(BaseModel):
    row_index: int
    input_ref: str = Field(..., description="file_path/url/tên file gốc của dòng này trong CSV/XLSX")
    status: Literal["OK", "ERROR"]
    result: Optional[DesignComplianceResult] = None
    error: Optional[str] = None
    grading: Optional[GradingInfo] = Field(default=None, description="Chỉ có nếu dòng input kèm cột expected_verdict")


class BatchReport(BaseModel):
    """[FE-FACING RESPONSE] Trả về từ orchestrator.process_batch() / route CSV/XLSX batch."""
    total: int = 0
    safe_count: int = 0
    risky_count: int = 0
    blocked_count: int = 0
    error_count: int = 0
    graded_count: int = Field(default=0, description="Số dòng có cột expected_verdict để tự so sánh")
    verdict_accuracy: Optional[float] = Field(default=None, description="% verdict khớp đáp án mẫu — None nếu graded_count=0 (batch không có đáp án mẫu)")
    rows: List[BatchRowResult] = Field(default_factory=list)


# =====================================================================
# 11. REQUEST SCHEMAS (FE gửi lên)
# =====================================================================

class ComplianceCheckRequest(BaseModel):
    """
    [FE-FACING REQUEST] Đúng 1 trong 3 field image_base64/file_path/url phải có giá trị —
    validate ở tầng orchestrator (không validate cứng ở Pydantic để giữ thông báo lỗi rõ
    ràng hơn "field required").
    """
    image_base64: Optional[str] = Field(default=None, description="Ảnh upload trực tiếp, base64 thuần hoặc kèm prefix data:image/...")
    file_path: Optional[str] = Field(default=None, description="Đường dẫn file server-side (PDF/PSD đã lưu sẵn, dùng cho test/CSV batch)")
    url: Optional[str] = Field(default=None, description="Link import — Google Drive/Dropbox/S3/direct image URL")
    platform: Optional[str] = Field(default=None, description="Platform bán (Etsy/Amazon/TikTok Shop/Shopify) — optional metadata")
    target_country: Optional[str] = Field(default="US", description="Thị trường target (US/EU/JP...) — optional metadata")
    niche_hint: Optional[str] = Field(default=None, description="Gợi ý niche nếu người dùng đã biết trước, không bắt buộc")


class ComplianceBatchRequest(BaseModel):
    """[FE-FACING REQUEST] Batch qua CSV — đúng 1 trong 2: FE đọc file CSV thành text rồi gửi
    nguyên văn lên (csv_content), HOẶC đưa link tới file batch để backend tự tải
    (batch_file_url, MỚI 2026-08-21) — validate ở tầng route (api/routes.py), không validate
    cứng ở Pydantic để giữ thông báo lỗi rõ ràng hơn "field required"."""
    csv_content: Optional[str] = Field(default=None, description="Nội dung file CSV dạng text thô (đọc bằng utf-8-sig phía backend)")
    batch_file_url: Optional[str] = Field(
        default=None,
        description="(MỚI) Link tới file batch — Google Drive (trỏ .xlsx/.csv tĩnh), Google Sheets "
                    "(link 'edit', tự rewrite về CSV export đúng sheet/gid), Dropbox, hoặc URL trực "
                    "tiếp .xlsx/.csv. Backend tự tải bằng httpx rồi tự nhận diện xlsx/csv qua magic "
                    "bytes (không dựa vào tên file vì link không luôn có đuôi rõ ràng)."
    )
    platform: Optional[str] = Field(default=None)
    target_country: Optional[str] = Field(default="US")
    max_concurrency: int = Field(default=5, ge=1, le=20)
