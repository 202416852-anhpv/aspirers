// frontend/api/config.js — Vercel Serverless Function, TỰ ĐỘNG nhận diện (Vercel coi MỌI file
// trong /api/*.js là 1 function, KHÔNG cần vercel.json/build step nào thêm cho phần static còn
// lại của site). Đây là cách ĐÚNG để 1 static site (không có build) đọc được biến môi trường đã
// set trên Vercel Project Settings — process.env ở đây thấy được MỌI biến đã set trong dashboard,
// KHÔNG bị giới hạn bởi tiền tố NEXT_PUBLIC_/VITE_ (tiền tố đó là quy ước riêng của Next.js/Vite
// lúc BUILD để quyết định biến nào được bundle vào code client, không áp dụng cho runtime của
// 1 serverless function chạy server-side như file này).
//
// app.js (frontend) gọi GET /api/config lúc load trang để lấy backend URL thật, thay vì hardcode
// "http://localhost:8000" trong file .js tĩnh — xem loadBackendUrlFromServerConfig() trong app.js.

module.exports = (req, res) => {
  res.status(200).json({
    backendUrl: process.env.NEXT_PUBLIC_BACKEND_URL || "",
  });
};
