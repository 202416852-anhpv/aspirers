// App.tsx — điểm ghép nối: Sidebar + SettingsBar + MessageThread + Composer, dùng
// useCheckDesign/useBatchCheck (TanStack Query) để gọi backend. Thread là local state (list
// ThreadMessage) — mutation chỉ lo gọi API, App.tsx lo đẩy message vào thread khi resolve.

import { useState } from "react";
import { Sidebar, type SessionItem } from "./components/layout/Sidebar";
import { MessageThread, type ThreadMessage } from "./components/layout/MessageThread";
import { SettingsBar, type SettingsValue } from "./components/composer/SettingsBar";
import { Composer, type ComposerIntent } from "./components/composer/Composer";
import { ResultCard } from "./components/result/ResultCard";
import { BatchSummary } from "./components/batch/BatchSummary";
import { BatchRowMessage } from "./components/batch/BatchRowMessage";
import { useCheckDesign } from "./hooks/useCheckDesign";
import { useBatchCheck } from "./hooks/useBatchCheck";
import { checkHealth, getBackendUrl, setBackendUrl } from "./api/client";

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

  const checkDesign = useCheckDesign();
  const batchCheck = useBatchCheck();

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
      const loadingId = pushMessage({ role: "assistant", content: "Đang chạy Agent 1-4 (có thể mất vài chục giây)..." });

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
      const loadingId = pushMessage({ role: "assistant", content: "Đang chạy batch (mỗi dòng 1 lượt Agent 1-4)..." });

      batchCheck.mutate(intent.kind === "batch-file" ? { file: intent.file, ...common } : { batch_file_url: intent.url, ...common }, {
        onSuccess: (report) => {
          replaceMessage(loadingId, <BatchSummary data={report} />);
          // Mỗi row = 1 message riêng (thay bảng-to-click-expand của bản cũ — xem báo cáo UX).
          setMessages((prev) => [
            ...prev,
            ...report.rows.map((row) => ({ id: uid(), role: "assistant" as const, content: <BatchRowMessage row={row} /> })),
          ]);
          setSessions((prev) => [...prev, { id: loadingId, label: `${label} (${report.total} dòng)`, verdict: "BATCH" }]);
        },
        onError: (err) => {
          replaceMessage(loadingId, <span className="error-note">Lỗi: {err.message}</span>);
          setSessions((prev) => [...prev, { id: loadingId, label, verdict: "ERROR" }]);
        },
      });
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
        <Composer onSubmit={handleSubmit} disabled={checkDesign.isPending || batchCheck.isPending} />
      </main>
    </div>
  );
}

export default App;
