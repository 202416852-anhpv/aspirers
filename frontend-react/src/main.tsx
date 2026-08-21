import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App.tsx";

// 1 QueryClient cho toàn app — app này gần như 100% server-state (xem báo cáo kiến trúc),
// không cần Redux/Zustand, TanStack Query lo hết loading/error/cache cho các mutation.
const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>
);
