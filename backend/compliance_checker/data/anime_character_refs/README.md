# Anime Character Reference Dataset — placeholder cấu trúc

*Last updated: 2026-08-20. Source: khung thư mục theo đúng contract `CLAUDE.md` mục 3.*

## Cấu trúc mong đợi

```
anime_character_refs/
  {character_name}/
    official_art.png
    anime_still.png
    merchandise.png
```

2-3 ảnh/nhân vật (official art + anime still + merchandise) để embedding ổn định hơn 1 ảnh duy nhất — theo đúng thiết kế đã chốt.

## Trạng thái hiện tại

**Chưa có ảnh thật nào được thêm vào** — đây là dữ liệu nhị phân, Claude Code không tự tạo/tải được trong phiên này. `compliance_checker/data/character_list.md` (file text) đã liệt kê danh sách TÊN nhân vật hoạt hình có bản quyền phổ biến để Agent 2 (Vision, zero-shot) đối chiếu ngay — nhóm chỉ cần bổ sung ảnh reference vào đây nếu muốn nâng cấp `match_character()` trong `opencv_modules.py` từ placeholder lên so khớp ảnh thật (hiện đang chờ dev phụ trách OpenCV/model, xem `docs.md`).

## Danh sách nhân vật ưu tiên thu thập ảnh trước (rủi ro cao nhất trong POD)

Pikachu, Naruto Uzumaki, Goku, Luffy (One Piece), Sailor Moon, Totoro, Chainsaw Man, Demon Slayer (Tanjiro/Nezuko), Attack on Titan (Eren/Mikasa), Studio Ghibli characters nói chung.
