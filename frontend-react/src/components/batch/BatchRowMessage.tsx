// components/batch/BatchRowMessage.tsx — 1 row batch = 1 message riêng (thay bảng-to-click-
// expand của bản cũ). Tái dùng thẳng ResultCard — đúng tư duy "dùng chung cho single + batch".
//
// ⚠️ Giới hạn đã biết (kế thừa từ bản cũ, không phải bug mới): previewUrl CHỈ có khi
// input_ref là URL http(s) — batch dùng file_path (phổ biến khi test local) sẽ KHÔNG có ảnh
// preview/overlay, chỉ hiện phần text (verdict/evidence/reasoning...) vẫn đầy đủ.

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

  const previewUrl = /^https?:\/\//i.test(row.input_ref) ? row.input_ref : null;

  return (
    <div>
      <div className="batch-row-label">
        Dòng #{row.row_index} — {row.input_ref}
      </div>
      <ResultCard result={row.result} grading={row.grading} previewUrl={previewUrl} />
    </div>
  );
}
