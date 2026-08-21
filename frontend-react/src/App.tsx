// App.tsx — điểm ghép nối: Sidebar + SettingsBar + MessageThread + Composer, dùng
// useCheckDesign/useBatchCheck (TanStack Query) để gọi backend. Thread là local state (list
// ThreadMessage) — mutation chỉ lo gọi API, App.tsx lo đẩy message vào thread khi resolve.

import { useState } from "react";
import { Sidebar, type SessionItem } from "./components/layout/Sidebar";
import { MessageThread, type ThreadMessage } from "./components/layout/MessageThread";
import { LoadingIndicator } from "./components/layout/LoadingIndicator";
import { SettingsBar, type SettingsValue } from "./components/composer/SettingsBar";
import { Composer, type ComposerIntent } from "./components/composer/Composer";
import { ResultCard } from "./components/result/ResultCard";
import { BatchSummary } from "./components/batch/BatchSummary";
import { BatchProgress } from "./components/batch/BatchProgress";
import { useCheckDesign } from "./hooks/useCheckDesign";
import { checkHealth, getBackendUrl, setBackendUrl, runBatchByFileStreaming, runBatchByUrlStreaming, PartialBatchStreamError } from "./api/client";
import type { BatchRowResult } from "./api/types";

let nextId = 0;
const uid = () => `msg-${nextId++}`;

function App() {
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [settings, setSettings] = useState<SettingsValue>({
    backendUrl: getBackendUrl(),
    platform: "",
    targetCountry: "US",
  });
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null);
  // (2026-08-22) batch giờ dùng route streaming (runBatchByFileStreaming/runBatchByUrlStreaming,
  // xem handleSubmit) thay vì useBatchCheck (TanStack Query mutation, xem hooks/useBatchCheck.ts
  // — GIỮ NGUYÊN file đó, không xoá, chỉ không dùng ở đây nữa). Lý do: streaming cần callback
  // onRow() bắn liên tục TRONG LÚC promise còn đang chạy để cập nhật Progress — không khớp tốt
  // với mô hình "1 mutation = 1 lần resolve" của useMutation, nên gọi thẳng hàm client.ts +
  // state pending riêng ở đây thay vì cố ép vào abstraction đó.
  const [batchPending, setBatchPending] = useState(false);

  const checkDesign = useCheckDesign();

  function pushMessage(msg: Omit<ThreadMessage, "id">) {
    const id = uid();
    setMessages((prev) => [...prev, { id, ...msg }]);
    return id;
  }

  function replaceMessage(id: string, content: ThreadMessage["content"]) {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, content } : m)));
  }

  async function handleCheckHealth() {
    setBackendUrl(settings.backendUrl);
    setBackendHealthy(await checkHealth());
  }

  function handleSubmit(intent: ComposerIntent) {
    setBackendUrl(settings.backendUrl);
    const common = { platform: settings.platform || undefined, target_country: settings.targetCountry };

    if (intent.kind === "single-file" || intent.kind === "single-url") {
      const label = intent.kind === "single-file" ? `📎 ${intent.file.name}` : `🔗 ${intent.url}`;
      pushMessage({ role: "user", content: label });
      const loadingId = pushMessage({ role: "assistant", content: <LoadingIndicator variant="single" /> });

      const previewUrl =
        intent.kind === "single-file"
          ? intent.file.type.startsWith("image/")
            ? URL.createObjectURL(intent.file)
            : null
          : intent.url;

      checkDesign.mutate(
        intent.kind === "single-file"
          ? { file: intent.file, niche_hint: intent.niche_hint, ...common }
          : { url: intent.url, ...common },
        {
          onSuccess: (result) => {
            replaceMessage(loadingId, <ResultCard result={result} previewUrl={previewUrl} />);
            setSessions((prev) => [...prev, { id: loadingId, label, verdict: result.final_verdict }]);
          },
          onError: (err) => {
            replaceMessage(loadingId, <span className="error-note">Lỗi: {err.message}</span>);
            setSessions((prev) => [...prev, { id: loadingId, label, verdict: "ERROR" }]);
          },
        }
      );
    } else {
      const label = intent.kind === "batch-file" ? `📊 ${intent.file.name}` : `📊 ${intent.url}`;
      pushMessage({ role: "user", content: label });
      const loadingId = pushMessage({ role: "assistant", content: <BatchProgress done={0} safe={0} risky={0} blocked={0} error={0} /> });

      // (2026-08-22) đếm cục bộ trong closure (KHÔNG phải useState) — đủ dùng vì chỉ cần
      // replaceMessage() ngay khi có dòng mới, không cần re-render component nào khác theo số
      // này; dùng useState ở đây chỉ tạo thêm 1 lần re-render thừa mỗi dòng mà không lợi gì thêm.
      const counts = { done: 0, safe: 0, risky: 0, blocked: 0, error: 0 };
      const onRow = (row: BatchRowResult) => {
        counts.done += 1;
        if (row.status === "ERROR") counts.error += 1;
        else if (row.result?.final_verdict === "SAFE") counts.safe += 1;
        else if (row.result?.final_verdict === "RISKY") counts.risky += 1;
        else if (row.result?.final_verdict === "BLOCKED") counts.blocked += 1;
        replaceMessage(loadingId, <BatchProgress {...counts} />);
      };

      setBatchPending(true);
      const streamPromise =
        intent.kind === "batch-file"
          ? runBatchByFileStreaming({ file: intent.file, ...common }, { onRow })
          : runBatchByUrlStreaming({ batch_file_url: intent.url, ...common }, { onRow });

      streamPromise
        .then((report) => {
          // (2026-08-22) Sau khi stream xong, CHỈ còn 1 message tóm tắt (BatchSummary —
          // thống kê + nút tải CSV) — KHÔNG còn render N ResultCard chi tiết từng dòng nữa (bản
          // cũ, xem components/batch/BatchRowMessage.tsx — vẫn giữ file đó, không xoá, chỉ
          // không dùng ở đây). Lý do: batch lớn (chục dòng) làm rối màn hình chat — chi tiết
          // từng dòng vẫn có đầy đủ trong CSV tải về (backend đã trả sẵn qua report.csv_export).
          replaceMessage(loadingId, <BatchSummary data={report} />);
          setSessions((prev) => [...prev, { id: loadingId, label: `${label} (${report.total} dòng)`, verdict: "BATCH" }]);
        })
        .catch((err: Error) => {
          if (err instanceof PartialBatchStreamError) {
            // (2026-08-22, MỚI) Stream đứt giữa chừng (thường do backend crash/hết bộ nhớ ở 1
            // dòng nặng) — vẫn hiện được kết quả CỦA NHỮNG DÒNG ĐÃ KỊP XONG (counts đã đếm sẵn
            // trong onRow ở trên) thay vì mất trắng chỉ vì vài dòng cuối chưa xử lý tới.
            const partialReport = {
              total: counts.done,
              safe_count: counts.safe,
              risky_count: counts.risky,
              blocked_count: counts.blocked,
              error_count: counts.error,
              graded_count: 0,
              verdict_accuracy: null,
              rows: err.rows,
            };
            replaceMessage(loadingId, <BatchSummary data={partialReport} partial partialMessage={err.message} />);
            setSessions((prev) => [...prev, { id: loadingId, label: `${label} (${counts.done} dòng, CHƯA hoàn tất)`, verdict: "ERROR" }]);
            return;
          }
          replaceMessage(loadingId, <span className="error-note">Lỗi: {err.message}</span>);
          setSessions((prev) => [...prev, { id: loadingId, label, verdict: "ERROR" }]);
        })
        .finally(() => setBatchPending(false));
    }
  }

  function handleSelectSession(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="app-shell">
      <Sidebar sessions={sessions} onSelectSession={handleSelectSession} onNewCheck={() => setMessages([])} backendHealthy={backendHealthy} />
      <main className="main-panel">
        <SettingsBar value={settings} onChange={setSettings} onCheckHealth={handleCheckHealth} />
        <MessageThread messages={messages} />
        <Composer onSubmit={handleSubmit} disabled={checkDesign.isPending || batchPending} />
      </main>
    </div>
  );
}

export default App;
