// components/batch/BatchRowMessage.tsx — 1 row batch = 1 message riêng (thay bảng-to-click-
// expand của bản cũ). Tái dùng thẳng ResultCard — đúng tư duy "dùng chung cho single + batch".
//
// ⚠️ (2026-08-22) Khoanh vùng ảnh (ImageOverlay, bbox text/face) CHỈ áp dụng cho 1 design đơn
// (upload file hoặc dán link) — batch KHÔNG hiện, theo đúng yêu cầu đã chốt. Truyền
// showOverlay={false} cho ResultCard — KHÔNG còn tính previewUrl ở đây nữa (dù input_ref là
// URL http(s) hợp lệ cũng không dùng tới, vì ResultCard bỏ qua ImageOverlay hoàn toàn khi
// showOverlay=false).

import type { BatchRowResult } from "../../api/types";
import { ResultCard } from "../result/ResultCard";

export function BatchRowMessage({ row }: { row: BatchRowResult }) {
  if (row.status === "ERROR" || !row.result) {
    return (
      <div className="batch-row-error">
        <b>Dòng #{row.row_index}</b> ({row.input_ref}): <span className="error-note">{row.error || "không có kết quả"}</span>
      </div>
    );
  }

  return (
    <div>
      <div className="batch-row-label">
        Dòng #{row.row_index} — {row.input_ref}
      </div>
      <ResultCard result={row.result} grading={row.grading} showOverlay={false} />
    </div>
  );
}
