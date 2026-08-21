// components/layout/LoadingIndicator.tsx — thay thế 1 dòng text tĩnh "Đang chạy Agent 1-4..."
// bằng vài dòng LUÂN PHIÊN mỗi 5s, cho cảm giác có tiến triển thay vì 1 câu đứng yên suốt vài
// chục giây chờ backend. Tự quản lý state/interval riêng (không cần App.tsx replaceMessage()
// theo thời gian) — push 1 lần <LoadingIndicator /> vào thread, component tự cycle bên trong.

import { useEffect, useState } from "react";

const SINGLE_MESSAGES = ["🧠 AI đang suy nghĩ...", "🔍 AI đang trích xuất dữ liệu (logo, chữ, khuôn mặt...)...", "⚖️ AI đang đối chiếu bằng chứng & viết nhận xét..."];

const BATCH_MESSAGES = ["🧠 AI đang suy nghĩ...", "🔍 AI đang trích xuất dữ liệu từng dòng...", "📊 AI đang tổng hợp kết quả batch..."];

export interface LoadingIndicatorProps {
  variant?: "single" | "batch";
}

export function LoadingIndicator({ variant = "single" }: LoadingIndicatorProps) {
  const messages = variant === "batch" ? BATCH_MESSAGES : SINGLE_MESSAGES;
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((i) => (i + 1) % messages.length);
    }, 5000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- messages là hằng số theo variant, không đổi giữa các lần render
  }, [variant]);

  return (
    <span className="loading-indicator">
      <span key={index} className="loading-text">
        {messages[index]}
      </span>
      <span className="loading-hint"> (có thể mất vài chục giây)</span>
    </span>
  );
}
