// components/result/ResultCard.tsx — SHELL, ghép mọi component con lại. Dùng chung cho single
// check VÀ mỗi batch row (xem BatchRowMessage) — đúng tư duy "1 hàm render, nhiều nơi gọi" của
// bản cũ, chỉ khác là giờ tách thành component thay vì 1 hàm string HTML dài 100 dòng.

import type { DesignComplianceResult, GradingInfo } from "../../api/types";
import { VerdictHeader } from "./VerdictHeader";
import { SuspectChipList } from "./SuspectChipList";
import { ImageOverlay } from "./ImageOverlay";
import { EvidenceList } from "./EvidenceList";
import { FixSuggestions } from "./FixSuggestions";
import { MarketSuggestion } from "./MarketSuggestion";

export interface ResultCardProps {
  result: DesignComplianceResult;
  grading?: GradingInfo | null;
  previewUrl?: string | null;
}

function GradingBanner({ grading }: { grading: GradingInfo }) {
  return (
    <div className={`grading-banner ${grading.verdict_match ? "match" : "mismatch"}`}>
      <div>
        {grading.verdict_match ? "✅ Khớp đáp án mẫu" : "❌ Lệch đáp án mẫu"} — expected: {grading.expected.expected_verdict}
      </div>
      {/* (Báo cáo UX) bản cũ chỉ hiện expected_verdict, bỏ phí violation_type/detail/confidence
          cũng có sẵn — hiện đủ ở đây để debug threshold nhanh hơn khi lệch đáp án. */}
      {!grading.verdict_match && (
        <div className="grading-expected-detail">
          {grading.expected.expected_violation_type && <div>Loại vi phạm mẫu: {grading.expected.expected_violation_type}</div>}
          {grading.expected.expected_violation_detail && <div>Chi tiết mẫu: {grading.expected.expected_violation_detail}</div>}
        </div>
      )}
    </div>
  );
}

export function ResultCard({ result: r, grading, previewUrl = null }: ResultCardProps) {
  return (
    <div className="result-card">
      {grading && <GradingBanner grading={grading} />}
      <VerdictHeader verdict={r.final_verdict} sourceType={r.source_type} warnings={r.warnings} />

      <div className="meta-grid">
        <div>
          <div className="meta-label">Niche</div>
          {r.niche}
        </div>
        <div>
          <div className="meta-label">Sub-niche</div>
          {r.sub_niche || "—"}
        </div>
        <div>
          <div className="meta-label">Style</div>
          {r.style}
        </div>
        <div>
          <div className="meta-label">Motifs</div>
          {r.motifs.join(", ") || "—"}
        </div>
      </div>

      <ImageOverlay previewUrl={previewUrl} flaggedRegions={r.flagged_regions} />

      <div className="section-title">
        Logo nghi ngờ <span className="empty-note">(✅/❌ = Agent 2 đã kiểm tra lại ảnh)</span>
      </div>
      <SuspectChipList items={r.suspected_logos.map((l) => ({ name: l.brand_name, confidence: l.confidence }))} category="logo" verifications={r.verifications} />

      <div className="section-title">
        Nhân vật nghi ngờ <span className="empty-note">(✅/❌ = Agent 2 đã kiểm tra lại ảnh)</span>
      </div>
      <SuspectChipList items={r.suspected_characters} category="character" verifications={r.verifications} />

      <div className="section-title">
        Người nổi tiếng nghi ngờ <span className="empty-note">(✅/❌ = Agent 2 đã kiểm tra lại ảnh)</span>
      </div>
      <SuspectChipList items={r.suspected_celebrities} category="celebrity" verifications={r.verifications} />

      <div className="section-title">
        Font nghi ngờ <span className="empty-note">(✅/❌ = Agent 2 đã kiểm tra lại ảnh — best-effort, xem font_disclaimer)</span>
      </div>
      <SuspectChipList items={r.suspected_fonts.map((f) => ({ name: f.font_name_guess, confidence: f.confidence }))} category="font" verifications={r.verifications} />

      <div className="section-title">
        Tác phẩm/franchise nghi ngờ <span className="empty-note">(✅/❌ = Agent 2 đã kiểm tra lại ảnh)</span>
      </div>
      <SuspectChipList items={r.suspected_artworks.map((a) => ({ name: a.artwork_name, confidence: a.confidence }))} category="artwork" verifications={r.verifications} />

      <div className="section-title">OCR text</div>
      <div className="ocr-box">{r.OCR_text || "(không có chữ)"}</div>

      <div className="section-title">Evidence (category vi phạm)</div>
      <EvidenceList evidence={r.evidence} />

      <div className="section-title">Reasoning</div>
      <div className="reasoning-box">{r.reasoning || "(trống)"}</div>

      <div className="section-title">Gợi ý sửa</div>
      <FixSuggestions items={r.fix_suggestions} />

      <div className="section-title">Gợi ý thị trường</div>
      <MarketSuggestion market={r.market_suggestion} />

      <div className="font-disclaimer">{r.font_disclaimer}</div>
    </div>
  );
}
