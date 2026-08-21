// components/result/FixSuggestions.tsx — gợi ý sửa cụ thể cho từng vi phạm (Agent 3).

import type { FixSuggestion } from "../../api/types";

export function FixSuggestions({ items }: { items: FixSuggestion[] }) {
  if (items.length === 0) {
    return <p className="empty-note">Không có gợi ý sửa (verdict SAFE hoặc chưa có evidence).</p>;
  }
  return (
    <div>
      {items.map((f, i) => (
        <div key={i} className="fix-item">
          <span className="fix-violation">{f.violation}:</span> {f.suggestion}
        </div>
      ))}
    </div>
  );
}
