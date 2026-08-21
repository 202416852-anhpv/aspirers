// components/result/MarketSuggestion.tsx — Agent 4: 2 phần TÁCH BIỆT rõ ràng (đúng thiết kế
// backend, không được gộp lẫn): gợi ý ĐỘC LẬP (top_country/top_platform_suggestion, Agent 4 tự
// chọn) vs đánh giá RIÊNG cho platform+country người dùng đã CHỌN (selected_platform_suitable).

import type { MarketSuggestion as MarketSuggestionType } from "../../api/types";

export function MarketSuggestion({ market }: { market: MarketSuggestionType | null }) {
  if (!market) {
    return <p className="empty-note">Không có gợi ý thị trường (nhánh Agent 4 có thể đã lỗi).</p>;
  }

  // null = user không chọn platform -> không có gì để thẩm định. KHÁC false (vẫn phải hiện rõ
  // dù là tin xấu) — đúng phân biệt đã chốt ở backend.
  const hasSelectedAssessment = market.selected_platform_suitable !== null;

  return (
    <div className="market-box">
      <div>
        <b>Quốc gia đề xuất (độc lập):</b> {market.top_country_suggestion || "—"}
      </div>
      <div>
        <b>Platform đề xuất (độc lập):</b> {market.top_platform_suggestion || "—"}
      </div>
      <div>{market.rationale}</div>

      {hasSelectedAssessment && (
        <div className={`platform-suitability-banner ${market.selected_platform_suitable ? "yes" : "no"}`}>
          <b>{market.selected_platform_suitable ? "✅ Platform bạn chọn: phù hợp" : "⚠️ Platform bạn chọn: có rủi ro"}</b>
          <div>{market.selected_platform_rationale}</div>
        </div>
      )}
    </div>
  );
}
