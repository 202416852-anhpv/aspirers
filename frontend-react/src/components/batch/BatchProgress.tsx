// components/batch/BatchProgress.tsx — (2026-08-22, MỚI) hiện tiến độ batch REAL-TIME khi
// dùng route streaming (batch-csv-stream/batch-json-stream, xem api/client.ts) — cập nhật
// NGAY sau MỖI dòng NDJSON nhận được, thay vì 1 dòng "đang chạy..." đứng yên suốt cả batch
// (có thể vài phút với batch nhiều dòng nặng — xem docs.md phần timeout gateway).

export interface BatchProgressProps {
  done: number;
  safe: number;
  risky: number;
  blocked: number;
  error: number;
}

export function BatchProgress({ done, safe, risky, blocked, error }: BatchProgressProps) {
  return (
    <span className="batch-progress">
      ⏳ Progress: {done}...
      {done > 0 && (
        <span className="batch-progress-detail">
          {" "}
          ({safe} SAFE, {risky} RISKY, {blocked} BLOCKED{error > 0 ? `, ${error} lỗi` : ""})
        </span>
      )}
    </span>
  );
}
