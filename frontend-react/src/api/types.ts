// api/types.ts — khớp 1:1 với backend/compliance_checker/schemas.py (nguồn sự thật DUY NHẤT).
// CHỈ định nghĩa type FE THẬT SỰ nhận/gửi (response/request) — không port các model nội bộ
// pipeline (Agent1ClassifyResult, Agent2Result, TrademarkFlag, SynthesisResult, TextRegion...)
// vì FE không bao giờ thấy chúng trực tiếp.
//
// ⚠️ Khi backend đổi schemas.py, sửa file NÀY trước tiên rồi mới sửa component — tránh lặp lại
// bug "component đọc field đã bị xoá" (face_base64/text_regions) từng xảy ra ở bản vanilla JS cũ.

export type Confidence = "low" | "medium" | "high";
export type Verdict = "SAFE" | "RISKY" | "BLOCKED";

export interface SuspectedLogo {
  brand_name: string;
  confidence: Confidence;
}

export interface SuspectedCharacter {
  name: string;
  confidence: Confidence;
}

export interface SuspectedCelebrity {
  name: string;
  confidence: Confidence;
}

/** (2026-08-22, MỚI) Cùng pattern candidate-generation với SuspectedLogo/Character/Celebrity. */
export interface SuspectedFont {
  font_name_guess: string;
  confidence: Confidence;
}

/** (2026-08-22, MỚI) Cùng pattern candidate-generation với SuspectedLogo/Character/Celebrity. */
export interface SuspectedArtwork {
  artwork_name: string;
  confidence: Confidence;
}

/** Agent 2 xác nhận CÓ/KHÔNG cho từng candidate Agent 1 nêu — nhị phân, KHÔNG có field số nào. */
export interface VerificationItem {
  category: "logo" | "character" | "celebrity" | "font" | "artwork";
  name: string;
  present: boolean;
  reasoning: string;
}

export interface CategoryResult {
  tag: Verdict;
  confidence: number; // 0-100 — CHỈ dùng nội bộ (sort/debug), KHÔNG render ra UI (đúng quy tắc đã chốt)
  detail: string;
}

export interface PositioningNote {
  category: string;
  location_description: string;
  citation: string;
  bbox_norm: [number, number, number, number] | null;
  bbox_source: "opencv_mser" | "pdf_native" | null;
}

/** Danh sách ĐẦY ĐỦ mọi khuôn mặt BlazeFace phát hiện (kể cả không nhận diện được) — tham
 * khảo/debug. KHÔNG có field ảnh nào (face_base64 đã bị xoá khỏi backend) — component KHÔNG
 * được tự ý render danh sách này trực tiếp, dùng flagged_regions để vẽ overlay. */
export interface DetectedFace {
  bbox_norm: [number, number, number, number];
  suspected_name: string | null;
  confidence: Confidence | null;
  reasoning: string;
}

/** Danh sách RÚT GỌN vùng đáng nghi (text + face gộp chung) — ĐÂY là nguồn ImageOverlay dùng
 * để vẽ khung lên ảnh gốc, thay thế hoàn toàn cách hiện thumbnail crop riêng trước đây. */
export interface FlaggedRegion {
  kind: "text" | "face";
  bbox_norm: [number, number, number, number];
  label: string;
  detail: string;
}

export interface FixSuggestion {
  violation: string;
  suggestion: string;
}

export interface MarketSuggestion {
  top_country_suggestion: string;
  top_platform_suggestion: string;
  rationale: string;
  /** null = user không chọn platform -> không có gì để thẩm định (KHÁC false, vẫn phải hiện). */
  selected_platform_suitable: boolean | null;
  selected_platform_rationale: string;
}

export type SourceType = "image" | "pdf_digital_native" | "pdf_scanned" | "psd" | "unknown";

/** [FE-FACING RESPONSE] 1 design compliance-check hoàn chỉnh — trả về từ
 * POST /api/compliance/check | /check-upload, hoặc BatchRowResult.result trong batch. */
export interface DesignComplianceResult {
  niche: string;
  /** (2026-08-22, MỚI) Niche con cụ thể hơn (vd niche="christmas_holiday" -> sub_niche="ugly_christmas_sweater"). */
  sub_niche: string;
  style: string;
  motifs: string[];
  OCR_text: string;
  suspected_logos: SuspectedLogo[];
  suspected_characters: SuspectedCharacter[];
  suspected_celebrities: SuspectedCelebrity[];
  suspected_fonts: SuspectedFont[];
  suspected_artworks: SuspectedArtwork[];
  verifications: VerificationItem[];

  final_verdict: Verdict;
  overall_confidence: number; // 0-100 — hiện KHÔNG render ở UI (xem báo cáo UX), chỉ giữ cho debug/sort
  evidence: Record<string, CategoryResult>;

  positioning_notes: PositioningNote[];
  detected_faces: DetectedFace[];
  flagged_regions: FlaggedRegion[];

  reasoning: string;
  fix_suggestions: FixSuggestion[];
  market_suggestion: MarketSuggestion | null;

  font_disclaimer: string;
  source_type: SourceType;
  warnings: string[];
}

/** [FE-FACING] Self-grading — CHỈ có khi input kèm cột expected_verdict (file mẫu BGK). */
export interface GradingInfo {
  expected: Record<string, string>; // expected_niche/expected_style/expected_violation_type/... + notes, thô, không ép kiểu cứng
  verdict_match: boolean;
}

export interface BatchRowResult {
  row_index: number;
  input_ref: string;
  status: "OK" | "ERROR";
  result: DesignComplianceResult | null;
  error: string | null;
  grading: GradingInfo | null;
}

/** [FE-FACING RESPONSE] Trả về từ /api/compliance/batch-csv | /batch-json. */
export interface BatchReport {
  total: number;
  safe_count: number;
  risky_count: number;
  blocked_count: number;
  error_count: number;
  graded_count: number;
  verdict_accuracy: number | null;
  rows: BatchRowResult[];
  /** CHỈ có ở batch-csv (route batch-json không tự thêm field này). */
  csv_export?: string;
}

/** [FE-FACING REQUEST] POST /api/compliance/check — đúng 1 trong 3: image_base64/file_path/url. */
export interface ComplianceCheckRequest {
  image_base64?: string;
  file_path?: string;
  url?: string;
  platform?: string;
  target_country?: string;
  niche_hint?: string;
}

/** [FE-FACING REQUEST] POST /api/compliance/batch-json — đúng 1 trong 2: csv_content HOẶC
 * batch_file_url (MỚI — link Google Sheets/Drive/Dropbox/URL trực tiếp, backend tự tải + tự
 * sniff xlsx/csv, xem docs.md mục 4.1). */
export interface ComplianceBatchRequest {
  csv_content?: string;
  batch_file_url?: string;
  platform?: string;
  target_country?: string;
  max_concurrency?: number;
}
