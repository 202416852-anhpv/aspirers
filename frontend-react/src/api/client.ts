// api/client.ts — fetch wrapper cho 5 route thật của backend (xem backend/compliance_checker/
// api/routes.py + main.py /health). KHÔNG dùng thư viện HTTP ngoài (axios...) — fetch() thuần
// đã đủ cho scope này, giữ bundle nhẹ.

// (2026-08-21) Vite CÓ build step thật (khác frontend/ vanilla JS cũ — xem frontend/api/config.js
// cho cách xử lý ở đó) — biến env tiền tố VITE_ được Vite tự inject vào import.meta.env lúc BUILD,
// Vercel tự chạy `npm run build` cho project Vite nên cơ chế này hoạt động ngay, không cần
// serverless function nào thêm. ⚠️ TÊN BIẾN KHÁC frontend/ cũ (NEXT_PUBLIC_BACKEND_URL) — đây là
// quy ước riêng của Vite, cần set THÊM 1 biến Vercel tên VITE_BACKEND_URL (cùng giá trị URL
// backend) khi deploy project này, không dùng chung tên với project frontend/ cũ được.
const VITE_BACKEND_URL = (
  import.meta.env.VITE_BACKEND_URL as string | undefined
)
  ?.trim()
  .replace(/\/+$/, "");

// (2026-08-22) BỎ localStorage — trước đây setBackendUrl() ghi đè xuống trình duyệt, sống sót
// qua mọi lần deploy sau đó và ưu tiên cao hơn cả VITE_BACKEND_URL, nên mỗi lần push code mới
// phải tự tay xoá cache/site data mới thấy đúng giá trị mới (gây nhầm lẫn suốt quá trình debug
// deploy Vercel/Render). Giờ dùng biến in-memory: chỉ tồn tại trong phiên tab đang mở (gõ tay
// để test 1 backend khác vẫn dùng được), reload/mở tab mới -> mất, tự quay về VITE_BACKEND_URL —
// đúng nghĩa "mỗi lần mở là 1 lần load" từ build hiện tại, không còn giá trị cache cũ lẫn vào.
let sessionOverrideUrl = "";

export function getBackendUrl(): string {
  return sessionOverrideUrl || VITE_BACKEND_URL || "http://localhost:8000";
}

export function setBackendUrl(url: string): void {
  sessionOverrideUrl = url.trim().replace(/\/+$/, "");
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return data.detail ? String(data.detail) : JSON.stringify(data);
  } catch {
    return `HTTP ${res.status}`;
  }
}

// ---------------------------------------------------------------------------
// GET /health
// ---------------------------------------------------------------------------

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${getBackendUrl()}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// POST /api/compliance/check | /check-upload — 1 design, đúng 1 trong 2 cách gửi
// ---------------------------------------------------------------------------

import type {
  ComplianceCheckRequest,
  DesignComplianceResult,
  ComplianceBatchRequest,
  BatchReport,
  BatchRowResult,
} from "./types";

export interface CheckByFileArgs {
  file: File;
  platform?: string;
  target_country: string;
  niche_hint?: string;
}

export async function checkDesignByFile(
  args: CheckByFileArgs,
): Promise<DesignComplianceResult> {
  const form = new FormData();
  form.append("file", args.file);
  if (args.platform) form.append("platform", args.platform);
  form.append("target_country", args.target_country);
  if (args.niche_hint) form.append("niche_hint", args.niche_hint);

  const res = await fetch(`${getBackendUrl()}/api/compliance/check-upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

export async function checkDesignByUrl(
  req: ComplianceCheckRequest,
): Promise<DesignComplianceResult> {
  const res = await fetch(`${getBackendUrl()}/api/compliance/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

// ---------------------------------------------------------------------------
// POST /api/compliance/batch-csv | /batch-json — batch nhiều design
// ---------------------------------------------------------------------------

export interface BatchByFileArgs {
  file: File; // .csv hoặc .xlsx — backend tự nhận theo đuôi file
  platform?: string;
  target_country: string;
  max_concurrency?: number;
}

export async function runBatchByFile(
  args: BatchByFileArgs,
): Promise<BatchReport> {
  const form = new FormData();
  form.append("file", args.file);
  if (args.platform) form.append("platform", args.platform);
  form.append("target_country", args.target_country);
  if (args.max_concurrency)
    form.append("max_concurrency", String(args.max_concurrency));

  const res = await fetch(`${getBackendUrl()}/api/compliance/batch-csv`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

/** Batch qua link (Google Sheets/Drive/Dropbox/URL trực tiếp) — dùng batch_file_url, KHÔNG
 * cần upload file. Backend tự tải + tự sniff xlsx/csv (xem docs.md mục 4.1, đã verify thật). */
export async function runBatchByUrl(
  req: ComplianceBatchRequest,
): Promise<BatchReport> {
  const res = await fetch(`${getBackendUrl()}/api/compliance/batch-json`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

// ---------------------------------------------------------------------------
// (2026-08-22, MỚI) POST /api/compliance/batch-csv-stream | /batch-json-stream — biến thể
// STREAMING (NDJSON) của batch — mỗi dòng trả về NGAY khi backend xử lý xong, thay vì đợi cả
// batch rồi mới có 1 response. Lý do: batch nhiều dòng nặng thật (7-16 phút/10 dòng) dễ vượt
// idle-read-timeout của gateway/proxy trước Render (~1 phút, xác nhận thật — xem docs.md) —
// route batch-csv/batch-json GỐC vẫn giữ nguyên, KHÔNG xoá, chỉ không dùng ở FE nữa.
// ---------------------------------------------------------------------------

export interface BatchStreamHandlers {
  /** Gọi NGAY sau mỗi dòng NDJSON nhận được (1 design xử lý xong) — dùng để hiện "Progress". */
  onRow?: (row: BatchRowResult) => void;
}

/** Đọc response body dạng NDJSON (mỗi dòng 1 JSON object, ngăn cách bằng "\n") qua
 * ReadableStream — gọi onRow() cho MỌI dòng, TRỪ dòng cuối cùng (nhận diện bằng key "summary")
 * dùng để build BatchReport trả về cuối cùng. KHÔNG dùng thư viện ngoài (fetch + TextDecoder
 * thuần đã đủ, đúng tinh thần "giữ bundle nhẹ" của file này). */
async function consumeNdjsonBatchStream(
  res: Response,
  handlers: BatchStreamHandlers,
): Promise<BatchReport> {
  if (!res.body) {
    // Môi trường/browser không hỗ trợ ReadableStream cho response.body (rất hiếm ở browser hiện
    // đại) — báo lỗi rõ ràng thay vì treo im lặng chờ mãi không có gì xảy ra.
    throw new Error("Trình duyệt không hỗ trợ đọc streaming response (thiếu response.body).");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const rows: BatchRowResult[] = [];
  let summary: Omit<BatchReport, "rows"> | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newlineIndex: number;
    while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newlineIndex).trim();
      buffer = buffer.slice(newlineIndex + 1);
      if (!line) continue;
      const parsed = JSON.parse(line);
      if ("summary" in parsed) {
        if (parsed.summary?.error) throw new Error(parsed.summary.error);
        summary = parsed.summary;
      } else {
        const row = parsed as BatchRowResult;
        rows.push(row);
        handlers.onRow?.(row);
      }
    }
  }
  if (!summary) throw new Error("Stream kết thúc nhưng không nhận được dòng tóm tắt cuối cùng — kết quả có thể chưa đầy đủ.");
  return { ...summary, rows };
}

export async function runBatchByFileStreaming(
  args: BatchByFileArgs,
  handlers: BatchStreamHandlers = {},
): Promise<BatchReport> {
  const form = new FormData();
  form.append("file", args.file);
  if (args.platform) form.append("platform", args.platform);
  form.append("target_country", args.target_country);
  if (args.max_concurrency) form.append("max_concurrency", String(args.max_concurrency));

  const res = await fetch(`${getBackendUrl()}/api/compliance/batch-csv-stream`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return consumeNdjsonBatchStream(res, handlers);
}

export async function runBatchByUrlStreaming(
  req: ComplianceBatchRequest,
  handlers: BatchStreamHandlers = {},
): Promise<BatchReport> {
  const res = await fetch(`${getBackendUrl()}/api/compliance/batch-json-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return consumeNdjsonBatchStream(res, handlers);
}
