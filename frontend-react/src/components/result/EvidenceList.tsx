// components/result/EvidenceList.tsx — liệt kê category vi phạm (evidence dict) — KHÔNG hiện
// confidence số/% (đúng quy tắc đã chốt, evidence[].confidence CHỈ dùng nội bộ backend).

import type { CategoryResult, Verdict } from "../../api/types";
import { VerdictBadge } from "./VerdictHeader";

export interface EvidenceListProps {
  evidence: Record<string, CategoryResult>;
}

export function EvidenceList({ evidence }: EvidenceListProps) {
  const entries = Object.entries(evidence);
  if (entries.length === 0) {
    return <p className="empty-note">Không có category nào bị flag — hoàn toàn SAFE.</p>;
  }

  return (
    <div>
      {entries.map(([category, ev]) => (
        <div key={category} className={`evidence-item tag-${ev.tag}`}>
          <div className="evidence-cat">
            {category} — <VerdictBadge verdict={ev.tag as Verdict} />
          </div>
          <div className="evidence-detail">{ev.detail}</div>
        </div>
      ))}
    </div>
  );
}
