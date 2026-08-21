# Frontend — BUP-02 Design Compliance Checker

Frontend test dạng chat (kiểu ChatGPT/Claude — sidebar lịch sử + bong bóng hội thoại + composer
đính kèm file), **vanilla HTML/CSS/JS, không cần Node/npm, không cần build step**.

## Chạy backend trước

```bash
cd ../backend
python main.py   # hoặc: uvicorn main:app --reload
```

Mặc định backend chạy ở `http://localhost:8000` (xem `backend/config.py`).

## Mở frontend — chọn 1 trong 2 cách

**Cách 1 — mở thẳng file (nhanh nhất):** double-click `index.html`.

**Cách 2 — serve qua static server (khuyên dùng nếu Cách 1 gặp lỗi CORS/fetch trên trình duyệt của bạn):**
```bash
cd frontend
python -m http.server 5500
```
Rồi mở `http://localhost:5500`.

## Giao diện

- **Sidebar trái**: nút "+ Kiểm tra mới", lịch sử các lượt kiểm tra trong phiên (chấm màu = verdict — bấm vào để cuộn tới), nút ⚙️ Cài đặt (backend URL/platform/country/niche hint), đèn trạng thái kết nối backend.
- **Khung chat giữa**: mỗi lượt kiểm tra hiện thành 1 cặp tin nhắn — tin nhắn của bạn (file/link đã gửi) và phản hồi (verdict badge + toàn bộ breakdown).
- **Composer dưới cùng**: 2 tab — **💬 Kiểm tra 1 design** (đính kèm file bằng nút 📎, hoặc gõ thẳng link rồi Enter/bấm gửi) và **📊 Batch CSV/XLSX** (đính kèm file CSV hoặc XLSX).

## Dùng thử

1. Bấm ⚙️ **Cài đặt**, kiểm tra **Backend URL** đúng chưa (mặc định `http://localhost:8000`, được nhớ lại cho lần mở sau), bấm **Kiểm tra kết nối backend**.
2. Tab **Kiểm tra 1 design**: bấm 📎 để chọn file (có sẵn ảnh mẫu ở `backend/compliance_checker/test_pdf_images_link/Gen.G-banner.jpg`), gõ niche hint tuỳ chọn, bấm ➤ hoặc Enter. Hoặc gõ thẳng 1 link Google Drive/Dropbox/URL ảnh (không đính kèm file) rồi gửi.
3. Tab **Batch CSV/XLSX**: đính kèm 1 file `.csv` HOẶC `.xlsx`, bấm gửi. Bấm vào 1 dòng trong bảng kết quả để xem chi tiết. Nút **Tải CSV báo cáo** xuất `csv_export` backend trả về.
   - Có sẵn file mẫu **THẬT của ban giám khảo** ở `backend/compliance_checker/test_pdf_images_link/design_samples_template.xlsx` (30 test case kèm đáp án mẫu) — thử upload file này để xem tính năng **self-grading**: nếu input có cột `expected_verdict`, hệ thống tự so verdict thật với đáp án, hiện `verdict_accuracy` + cột ✅/❌ trong bảng. Lưu ý: file gốc cột "design" (ảnh) đang trống nên mọi dòng sẽ báo lỗi "thiếu input" cho tới khi điền path/link ảnh thật vào.

Mỗi lần gửi (single hoặc batch) tốn API key thật — không bấm lặp lại nhiều lần khi không cần.

## Giới hạn đã biết (nhìn thấy ngay trên UI, không phải bug frontend)

- Phần logo/nhân vật khớp bằng ẢNH (OpenCV embedding) vẫn là placeholder ở backend — nhưng khớp bằng TÊN (Vision tự nêu + đối chiếu danh sách) đã hoạt động, xem `backend/docs.md` mục 5.
- `market_suggestion` có thể `null` nếu nhánh đó lỗi tạm thời — frontend tự hiện ghi chú thay vì crash.
- Không có trang loading đẹp — chỉ chấm nhảy + text, vì mỗi lượt Agent 1-4 chạy thật có thể mất vài chục giây.
- Lịch sử trong sidebar chỉ tồn tại trong phiên trình duyệt hiện tại (không lưu, không đồng bộ — backend hoàn toàn stateless).
