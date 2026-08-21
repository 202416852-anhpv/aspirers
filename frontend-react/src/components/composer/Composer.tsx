// components/composer/Composer.tsx — 1 ô input đa năng, TỰ ĐOÁN Ý ĐỊNH thay vì 2 tab cứng
// "single"/"batch" của bản cũ (xem báo cáo UX — giảm 1 bước quyết định thừa cho người dùng).
//
// Quy tắc đoán (đơn giản, có thể tinh chỉnh sau khi có UI thật để test):
//   - File .csv/.xlsx đính kèm  -> batch (upload)
//   - File khác (ảnh/pdf/psd)   -> single design (upload)
//   - Text nhập là URL:
//       + chứa "docs.google.com/spreadsheets" hoặc đuôi .csv/.xlsx -> batch (batch_file_url)
//       + còn lại                                                   -> single design (url)
//   - Text KHÔNG phải URL, có file đính kèm -> coi là niche_hint cho single check
//
// niche_hint không còn 2 nguồn nhập chồng chéo như bản cũ (ô settings + ô composer) — CHỈ có
// đúng 1 nơi: gõ kèm khi đã đính kèm file, đúng như hành vi hữu ích nhất của bản cũ.

import { useRef, useState } from "react";

export type ComposerIntent =
  | { kind: "single-file"; file: File; niche_hint?: string }
  | { kind: "single-url"; url: string }
  | { kind: "batch-file"; file: File }
  | { kind: "batch-url"; url: string };

export interface ComposerProps {
  onSubmit: (intent: ComposerIntent) => void;
  disabled?: boolean;
}

function looksLikeUrl(s: string): boolean {
  return /^https?:\/\//i.test(s.trim());
}

function looksLikeBatchUrl(s: string): boolean {
  const lower = s.trim().toLowerCase();
  return lower.includes("docs.google.com/spreadsheets") || lower.endsWith(".csv") || lower.endsWith(".xlsx");
}

function looksLikeBatchFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return name.endsWith(".csv") || name.endsWith(".xlsx");
}

export function Composer({ onSubmit, disabled }: ComposerProps) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleAttachClick() {
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.length) setFile(e.target.files[0]);
  }

  function handleSend() {
    const trimmed = text.trim();

    if (file) {
      const intent: ComposerIntent = looksLikeBatchFile(file)
        ? { kind: "batch-file", file }
        : { kind: "single-file", file, niche_hint: trimmed || undefined };
      onSubmit(intent);
    } else if (looksLikeUrl(trimmed)) {
      onSubmit(looksLikeBatchUrl(trimmed) ? { kind: "batch-url", url: trimmed } : { kind: "single-url", url: trimmed });
    } else {
      return; // chưa có gì gửi được — không làm gì, giữ nguyên input cho người dùng sửa
    }

    setText("");
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <footer className="composer-area">
      {file && (
        <div className="composer-chips">
          <span className="composer-file-chip">
            {looksLikeBatchFile(file) ? "📊" : "📎"} {file.name}
            <button type="button" onClick={() => setFile(null)}>
              ✕
            </button>
          </span>
        </div>
      )}

      <div className="composer-box">
        <button type="button" onClick={handleAttachClick} title="Đính kèm ảnh/PDF/PSD/AI/CSV/XLSX" disabled={disabled}>
          📎
        </button>
        <input ref={fileInputRef} type="file" hidden onChange={handleFileChange} accept=".png,.jpg,.jpeg,.webp,.bmp,.pdf,.psd,.ai,.csv,.xlsx" />

        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder={
            file
              ? "Niche hint (tuỳ chọn) — vd: christmas_holiday"
              : "Dán link ảnh, link Google Sheets/Drive cho batch, hoặc bấm 📎 để đính kèm file..."
          }
          disabled={disabled}
        />

        <button type="button" onClick={handleSend} title="Gửi" disabled={disabled}>
          ➤
        </button>
      </div>

      <div className="composer-hint">
        1 file ảnh/PDF/PSD/AI hoặc link ảnh → kiểm tra 1 design. File .csv/.xlsx hoặc link Google Sheets/Drive → batch. Mỗi lượt gửi tốn 1 lần gọi API thật.
      </div>
    </footer>
  );
}
