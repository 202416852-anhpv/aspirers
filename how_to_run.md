# 1. Chạy backend
cd backend
python main.py          # http://localhost:8000

# 2. Mở frontend — cách nhanh nhất: double-click frontend/index.html
#    (nếu trình duyệt chặn CORS từ file://, dùng cách này thay thế:)
cd frontend
python -m http.server 5500   # rồi mở http://localhost:5500