// components/result/VerdictHeader.tsx — badge SAFE/RISKY/BLOCKED + nguồn input. KHÔNG hiện
// overall_confidence (đúng quy tắc "không hiện confidence ra UI" đã chốt xuyên suốt backend).

import type { SourceType, Verdict } from "../../api/types";

const VERDICT_LABEL: Record<Verdict, string> = {
  SAFE: "SAFE",
  RISKY: "RISKY",
  BLOCKED: "BLOCKED",
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`verdict-badge verdict-${verdict}`}>{VERDICT_LABEL[verdict]}</span>;
}

export interface VerdictHeaderProps {
  verdict: Verdict;
  sourceType: SourceType;
  warnings: string[];
}

export function VerdictHeader({ verdict, sourceType, warnings }: VerdictHeaderProps) {
  return (
    <div>
      {warnings.length > 0 && <div className="warnings-banner">⚠️ {warnings.join(" | ")}</div>}
      <div className="result-header">
        <VerdictBadge verdict={verdict} />
        <span className="source-note">Nguồn: {sourceType}</span>
      </div>
    </div>
  );
}
