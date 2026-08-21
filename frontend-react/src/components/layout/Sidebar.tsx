// components/layout/Sidebar.tsx — lịch sử các lượt kiểm tra trong phiên (session list) +
// health indicator. KHÔNG còn nút "Cài đặt" mở modal (xem báo cáo UX) — SettingsBar đã thay thế,
// luôn hiện trên composer thay vì giấu trong overlay.

export interface SessionItem {
  id: string;
  label: string;
  verdict: "SAFE" | "RISKY" | "BLOCKED" | "BATCH" | "ERROR";
}

export interface SidebarProps {
  sessions: SessionItem[];
  onSelectSession: (id: string) => void;
  onNewCheck: () => void;
  backendHealthy: boolean | null; // null = chưa kiểm tra
}

const DOT_CLASS: Record<SessionItem["verdict"], string> = {
  SAFE: "dot-safe",
  RISKY: "dot-risky",
  BLOCKED: "dot-blocked",
  BATCH: "dot-batch",
  ERROR: "dot-error",
};

export function Sidebar({ sessions, onSelectSession, onNewCheck, backendHealthy }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="brand">
          <span className="brand-icon">🛡️</span>
          <span className="brand-name">BUP-02 Checker</span>
        </div>
        <button type="button" onClick={onNewCheck}>
          + Kiểm tra mới
        </button>
      </div>

      <div className="session-list">
        {sessions.length === 0 ? (
          <p className="session-list-empty">Lịch sử các lượt kiểm tra trong phiên này sẽ hiện ở đây.</p>
        ) : (
          sessions.map((s) => (
            <div key={s.id} className="session-item" onClick={() => onSelectSession(s.id)}>
              <span className={`session-verdict-dot ${DOT_CLASS[s.verdict]}`} />
              <span className="session-label">{s.label}</span>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-footer">
        <div className="health-indicator">
          <span className={`health-dot ${backendHealthy === null ? "status-unknown" : backendHealthy ? "status-ok" : "status-fail"}`} />
          <span>{backendHealthy === null ? "chưa kiểm tra" : backendHealthy ? "Backend OK" : "Không kết nối được"}</span>
        </div>
      </div>
    </aside>
  );
}
