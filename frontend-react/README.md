# BUP-02 Compliance Checker — frontend (React + Vite)

Bản viết lại của `../frontend/` (vanilla JS) sang React + TypeScript + Vite, theo báo cáo UX +
đề xuất kiến trúc đã thống nhất. **Chưa xoá `../frontend/` cũ** — 2 bản chạy song song, tự
quyết định khi nào swap.

## Chạy thử

```bash
npm install   # đã chạy sẵn khi scaffold, chỉ cần nếu clone lại
npm run dev   # http://localhost:5173
```

Cần backend BUP-02 chạy ở `http://localhost:8000` (hoặc đổi Backend URL trong SettingsBar).

## Deploy lên Vercel (production)

Khác `../frontend/` (vanilla JS, phải dùng Serverless Function `/api/config.js` — xem README ở
đó) — project này CÓ build step thật (Vite), nên dùng đúng quy ước Vite: set biến Vercel
**`VITE_BACKEND_URL`** = URL backend thật (vd `https://xxx.onrender.com`). Vite tự inject vào
`import.meta.env.VITE_BACKEND_URL` lúc `npm run build` (Vercel tự chạy build này cho project
Vite) — xem `src/api/client.ts`. ⚠️ **Tên biến KHÁC** `NEXT_PUBLIC_BACKEND_URL` của `frontend/`
cũ — nếu deploy cả 2 project, cần set 2 biến riêng (cùng giá trị URL) trên 2 Vercel project khác
nhau, không dùng chung tên được.

Đã verify thật: build với `VITE_BACKEND_URL` set → URL thật xuất hiện trong bundle production.

## Trạng thái: KHUNG (skeleton), chưa phải bản hoàn chỉnh

Đã có — biên dịch sạch (`npm run build`), dev server boot thật, khớp đúng
`backend/compliance_checker/schemas.py` hiện tại (không phải bản cũ):

- `src/api/types.ts` — type khớp 1:1 mọi field FE-facing (kể cả field mới: `verifications`,
  `detected_faces`, `flagged_regions`, `batch_file_url`).
- `src/api/client.ts` + `src/hooks/` — gọi thật cả 5 route (`/health`, `check`, `check-upload`,
  `batch-csv`, `batch-json`) qua TanStack Query.
- Component tree đầy đủ theo đề xuất kiến trúc: `ImageOverlay` (thay `renderDetectedFaces` +
  `renderPositioningOverlay` cũ — 2 hàm đó đọc field ĐÃ BỊ XOÁ khỏi backend), `SuspectChipList`,
  `EvidenceList`, `ResultCard` dùng chung cho single + batch, `BatchSummary`/`BatchRowMessage`
  (mỗi batch row = 1 message riêng thay vì bảng-to-click-expand).
- `SettingsBar` luôn hiện (thay settings MODAL cũ — từng có bug kẹt UI).
- `Composer` tự đoán ý định (single vs batch, file vs link) thay vì 2 tab cứng.

Chưa làm (cố ý để lại cho lượt sau — đây là "khung", không phải bản polish):
- CSS mới CHỈ đủ layout điều hướng được, chưa phải design system hoàn chỉnh.
- Chưa test bằng tay với backend thật (mới verify: build sạch + dev server boot đúng, chưa
  chạy 1 lượt check thật qua UI).
- Batch vẫn KHÔNG progressive thật (đợi cả batch xong mới thấy message) — backend chưa stream,
  đây là giới hạn đã biết từ trước, không phải thiếu sót của bản React này.
