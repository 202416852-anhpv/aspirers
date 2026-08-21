// api/client.ts — fetch wrapper cho 5 route thật của backend (xem backend/compliance_checker/
// api/routes.py + main.py /health). KHÔNG dùng thư viện HTTP ngoài (axios...) — fetch() thuần
// đã đủ cho scope này, giữ bundle nhẹ.

const STORAGE_KEY_BACKEND_URL = "bup02_backend_url";

// (2026-08-21) Vite CÓ build step thật (khác frontend/ vanilla JS cũ — xem frontend/api/config.js
// cho cách xử lý ở đó) — biến env tiền tố VITE_ được Vite tự inject vào import.meta.env lúc BUILD,
// Vercel tự chạy `npm run build` cho project Vite nên cơ chế này hoạt động ngay, không cần
// serverless function nào thêm. ⚠️ TÊN BIẾN KHÁC frontend/ cũ (NEXT_PUBLIC_BACKEND_URL) — đây là
// quy ước riêng của Vite, cần set THÊM 1 biến Vercel tên VITE_BACKEND_URL (cùng giá trị URL
// backend) khi deploy project này, không dùng chung tên với project frontend/ cũ được.
const ENV_BACKEND_URL = (import.meta.env.VITE_BACKEND_URL as string | undefined)?.trim().replace(/\/+$/, "");

export function getBackendUrl(): string {
  const override = (localStorage.getItem(STORAGE_KEY_BACKEND_URL) || "").trim().replace(/\/+$/, "");
  return override || ENV_BACKEND_URL || "http://localhost:8000";
}

export function setBackendUrl(url: string): void {
  localStorage.setItem(STORAGE_KEY_BACKEND_URL, url.trim());
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

import type { ComplianceCheckRequest, DesignComplianceResult, ComplianceBatchRequest, BatchReport } from "./types";

export interface CheckByFileArgs {
  file: File;
  platform?: string;
  target_country: string;
  niche_hint?: string;
}

export async function checkDesignByFile(args: CheckByFileArgs): Promise<DesignComplianceResult> {
  const form = new FormData();
  form.append("file", args.file);
  if (args.platform) form.append("platform", args.platform);
  form.append("target_country", args.target_country);
  if (args.niche_hint) form.append("niche_hint", args.niche_hint);

  const res = await fetch(`${getBackendUrl()}/api/compliance/check-upload`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

export async function checkDesignByUrl(req: ComplianceCheckRequest): Promise<DesignComplianceResult> {
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

export async function runBatchByFile(args: BatchByFileArgs): Promise<BatchReport> {
  const form = new FormData();
  form.append("file", args.file);
  if (args.platform) form.append("platform", args.platform);
  form.append("target_country", args.target_country);
  if (args.max_concurrency) form.append("max_concurrency", String(args.max_concurrency));

  const res = await fetch(`${getBackendUrl()}/api/compliance/batch-csv`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}

/** Batch qua link (Google Sheets/Drive/Dropbox/URL trực tiếp) — dùng batch_file_url, KHÔNG
 * cần upload file. Backend tự tải + tự sniff xlsx/csv (xem docs.md mục 4.1, đã verify thật). */
export async function runBatchByUrl(req: ComplianceBatchRequest): Promise<BatchReport> {
  const res = await fetch(`${getBackendUrl()}/api/compliance/batch-json`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}
