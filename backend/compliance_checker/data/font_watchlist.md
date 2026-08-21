# Font Watchlist — Font thương mại hay bị dùng "chùa" trong POD

*Source: tổng hợp thủ công từ kiến thức phổ biến ngành thiết kế POD (không phải crawl tự động từ MyFonts/Adobe Fonts). Last updated: 2026-08-20.*

⚠️ **Giới hạn quan trọng** (đã thống nhất trong phiên brainstorm, xem `CLAUDE.md` mục 9.5): nhận diện CHÍNH XÁC tên font thương mại từ ảnh raster là bài toán chuyên biệt (kiểu WhatTheFont/Fontspring Matcherator), KHÔNG khả thi với Vision LLM thông thường ở mức tin cậy cao. Danh sách này chỉ dùng để agent viết `fix_suggestion` gợi ý đúng hướng ("có thể là 1 trong các font sau, cần kiểm tra license thủ công"), KHÔNG dùng để tự tin khẳng định đúng tên font.

## Nhóm font hay bị vi phạm license nhất trong thiết kế POD

- **Script/Handwritten cao cấp**: Mishka, Sloop Script, Bickham Script Pro — hay bị dùng "chùa" cho thiệp/mug personalized.
- **Display/Branding**: Gotham, Proxima Nova, Futura PT — thường yêu cầu license thương mại trả phí, hay bị nhầm là "free" vì trông giống các bản miễn phí (Montserrat, Poppins).
- **Font gắn với 1 thương hiệu cụ thể** (rủi ro kép — vừa vi phạm font-license vừa gợi liên tưởng thương hiệu): kiểu chữ Disney (Waltograph), kiểu chữ Harry Potter (Harry P), kiểu chữ Coca-Cola script.
- **Font "quote/motivational" phổ biến trên Etsy**: Amsterdam, Sweet Sunday Script — nhiều bản trôi nổi không rõ nguồn gốc license.

## Cách agent nên xử lý (không phải nhận diện chính xác)

1. Mô tả kiểu chữ chung chung (vd "bold condensed sans-serif", "elegant script với đuôi chữ dài") — KHÔNG khẳng định tên font cụ thể trừ khi cực kỳ đặc trưng và rõ ràng.
2. Luôn kèm disclaimer cố định (tiêm ở tầng orchestrator, xem `CLAUDE.md` mục 3): *"Font detection is best-effort. Recommend manual verification against font license databases (MyFonts, Adobe Fonts, Font Squirrel)."*
3. Verdict do font gây ra tối đa dừng ở `RISKY`, không tự động `BLOCKED` (rủi ro false positive quá cao nếu chỉ dựa vào "trông giống").
