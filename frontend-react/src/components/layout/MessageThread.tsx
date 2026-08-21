// components/layout/MessageThread.tsx — khung chat: user message (link/file đã gửi) xen kẽ
// assistant message (ResultCard | BatchSummary + N BatchRowMessage | loading | error). Bản
// thân component này KHÔNG biết nội dung cụ thể là gì — chỉ layout khung chat, nội dung do
// App.tsx quyết định (children).

import type { ReactNode } from "react";

export interface ThreadMessage {
  id: string;
  role: "user" | "assistant";
  content: ReactNode;
}

export interface MessageThreadProps {
  messages: ThreadMessage[];
}

export function MessageThread({ messages }: MessageThreadProps) {
  if (messages.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">🛡️</div>
        <h2>Kiểm tra 1 design hoặc cả batch</h2>
        <p>Đính kèm ảnh/PDF, dán link, hoặc chọn CSV/XLSX/link Google Sheets để kiểm tra hàng loạt.</p>
      </div>
    );
  }

  return (
    <div className="message-thread">
      {messages.map((m) => (
        <div key={m.id} id={m.id} className={`msg-row msg-${m.role}`}>
          <div className="msg-avatar">{m.role === "user" ? "🧑" : "🛡️"}</div>
          <div className="msg-bubble">{m.content}</div>
        </div>
      ))}
    </div>
  );
}
