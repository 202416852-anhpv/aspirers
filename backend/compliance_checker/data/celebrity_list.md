# Celebrity List — Tên người nổi tiếng hay bị dùng sai trong thiết kế POD

*Source: tổng hợp thủ công, chỉ liệt kê TÊN (KHÔNG kèm ảnh/dữ liệu sinh trắc học — xem ràng buộc đạo đức ở `CLAUDE.md` mục 2.2: "KHÔNG làm face-recognition/biometric matching cho người nổi tiếng, chỉ đối chiếu TÊN"). Last updated: 2026-08-20.*

⚠️ Việc đối chiếu ở đây CHỈ áp dụng cho TÊN xuất hiện qua OCR text trong thiết kế (vd in chữ "Betty White" lên áo) — KHÔNG áp dụng cho việc nhận diện khuôn mặt trong ảnh. Nếu Agent 2 (Vision) tự nhận ra "khuôn mặt này giống 1 người nổi tiếng" chỉ qua hình ảnh (không có tên chữ đi kèm), hệ thống vẫn ghi nhận nhưng KHÔNG được tự tin định danh chính xác — verdict tối đa dừng ở RISKY với note "nghi ngờ khuôn mặt người nổi tiếng, cần review thủ công", không bao giờ tự động BLOCKED chỉ từ suy đoán khuôn mặt.

## Nghệ sĩ / Diễn viên hay bị in trái phép lên áo/poster POD
Taylor Swift, Beyoncé, Elvis Presley, Marilyn Monroe, Michael Jackson, Bob Marley, Tupac Shakur, Freddie Mercury, Prince, Johnny Depp, Betty White, Dolly Parton.

## Vận động viên (Athlete)
Michael Jordan, LeBron James, Cristiano Ronaldo, Lionel Messi, Serena Williams, Kobe Bryant, Muhammad Ali.

## Chính trị gia (Political Figure) — nhạy cảm cao, cần thận trọng kép
Đây là nhóm rủi ro pháp lý VÀ rủi ro chính sách nền tảng (Etsy/Amazon/TikTok đều có quy định riêng, nghiêm ngặt hơn cả celeb thường) — hệ thống nên gắn nhãn RISKY mặc định cho bất kỳ tên chính trị gia đương nhiệm/gần đây nào xuất hiện, kèm note rõ "chính sách nền tảng về nội dung chính trị cần review thủ công, không chỉ xét khía cạnh trademark".

## Ghi chú sử dụng
Python code đối chiếu tên OCR/tên Vision nêu ra (case-insensitive) với danh sách này. Danh sách này KHÔNG đầy đủ (không thể liệt kê hết mọi người nổi tiếng) — nên Agent 2 vẫn phải tự do nêu tên bất kỳ ai nó nghi ngờ, không giới hạn trong danh sách này (đúng `CLAUDE.md` mục 2.2).
