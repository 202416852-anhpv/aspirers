# Character List — Nhân vật hoạt hình/truyện tranh có bản quyền phổ biến trong rủi ro POD

*Source: tổng hợp thủ công từ kiến thức phổ biến về sở hữu trí tuệ (Disney, Nintendo, Warner Bros/DC, Marvel/Disney, Shonen Jump/Shueisha, Studio Ghibli...) — KHÔNG phải crawl tự động. Dùng làm danh sách ĐỐI CHIẾU (Python) sau khi Agent 2 (Vision, zero-shot) tự nêu tên nghi ngờ — KHÔNG dùng để "nhận diện" (việc đó do Vision model đảm nhiệm dựa trên kiến thức đã huấn luyện sẵn). Last updated: 2026-08-20.*

⚠️ Danh sách này KHÔNG giới hạn phạm vi nhận diện của Agent 2 — Vision vẫn phải tự do nêu tên bất kỳ nhân vật nào nó nhận ra, kể cả không có trong danh sách dưới (đúng nguyên tắc `CLAUDE.md` mục 2.2 "liệt kê MỌI tên nghi ngờ").

## Disney / Pixar
Mickey Mouse, Minnie Mouse, Donald Duck, Goofy, Winnie the Pooh, Elsa, Anna (Frozen), Simba (Lion King), Moana, Buzz Lightyear, Woody (Toy Story), Stitch, Ariel (Little Mermaid), Cinderella, Snow White.

## Marvel / DC
Spider-Man, Iron Man, Captain America, Hulk, Thor, Black Panther, Deadpool, Batman, Superman, Wonder Woman, Joker, Harley Quinn.

## Nintendo / Video Game
Pikachu, Mario, Luigi, Princess Peach, Sonic the Hedgehog, Kirby, Link (Zelda), Among Us character, Minecraft Steve/Creeper.

## Anime / Manga
Naruto Uzumaki, Sasuke Uchiha, Goku (Dragon Ball), Luffy (One Piece), Tanjiro/Nezuko (Demon Slayer), Eren Yeager (Attack on Titan), Sailor Moon, Totoro/Studio Ghibli characters, Chainsaw Man, Gojo Satoru (Jujutsu Kaisen), Doraemon, Hello Kitty (Sanrio).

## Warner Bros / Looney Tunes / Sesame Street
Bugs Bunny, Tweety, Tom and Jerry, Elmo, Cookie Monster, Scooby-Doo.

## Peanuts / Classic Comics
Snoopy, Charlie Brown, Garfield, Hello Kitty (đã liệt kê ở trên).

## Ghi chú sử dụng
Đây là danh sách "đối chiếu" — Python code (`compliance_checker/agents.py` sau bước gọi Agent 2) so tên Vision nêu ra (case-insensitive, fuzzy match nhẹ cho lỗi chính tả) với danh sách này để quyết định mức độ tin cậy trong `black_box.py`. Match được → độ tin cậy cao hơn (có căn cứ đối chiếu). Không match nhưng Vision vẫn nghi ngờ → giữ nguyên RISKY, note "chưa xác nhận trong danh sách tham chiếu, cần review thủ công".
