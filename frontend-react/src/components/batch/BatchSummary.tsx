// components/batch/BatchSummary.tsx — 1 message TÓM TẮT đầu batch (X safe/Y risky/Z blocked +
// verdict_accuracy nếu có đáp án mẫu + nút tải CSV) — RIÊNG biệt với N message chi tiết từng
// row (BatchRowMessage). Đây là thay đổi UX chính so với bản cũ (1 bảng to + click expand) —
// xem báo cáo UX turn trước.

import type { BatchReport } from "../../api/types";

export interface BatchSummaryProps {
  data: BatchReport;
}

function downloadCsv(csvExport: string) {
  const blob = new Blob([csvExport], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "bup02_batch_report.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function BatchSummary({ data }: BatchSummaryProps) {
  return (
    <div className="summary-row">
      <div className="summary-pill">
        <b>{data.total}</b>Tổng số
      </div>
      <div className="summary-pill">
        <b className="safe">{data.safe_count}</b>SAFE
      </div>
      <div className="summary-pill">
        <b className="risky">{data.risky_count}</b>RISKY
      </div>
      <div className="summary-pill">
        <b className="blocked">{data.blocked_count}</b>BLOCKED
      </div>
      <div className="summary-pill">
        <b>{data.error_count}</b>Lỗi
      </div>
      {data.verdict_accuracy !== null && (
        <div className="summary-pill">
          <b>{data.verdict_accuracy}%</b>Verdict accuracy ({data.graded_count} dòng có đáp án mẫu)
        </div>
      )}
      {data.csv_export && (
        <button type="button" onClick={() => downloadCsv(data.csv_export!)}>
          ⬇ Tải CSV báo cáo
        </button>
      )}
      <p className="empty-note batch-detail-hint">Chi tiết từng dòng (niche, evidence, reasoning, fix suggestion...) có đầy đủ trong file CSV tải về.</p>
    </div>
  );
}
