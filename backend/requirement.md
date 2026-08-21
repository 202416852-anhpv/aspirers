Xử lí link: Dùng thư viện httpx của python. 
Direct image url: .jpg, .png… : trực tiếp httpx.get(url)

Google drive link: Chỉ có thể có bản xem trước.
https://drive.google.com/file/d/16wD-frbrKlrWdIBJ9ThkidCHBtriZa2u/view?usp=sharing
-> không thể đọc byte ảnh trực tiếp được.
đoạn sau /d/.. đến /view là ID ảnh. Tag /view nghĩa là preview.
Dựng lại 1 URL cho phép tải file này rồi fetch URL đó để ra bytes ảnh.

 drive.google.com/uc?export=download&id=16wD-frbrKlrWdIBJ9ThkidCHBtriZa2u

s3 link: Link của dịch vụ cloud storage aws -> httpx.get(url) luôn.

Dropbox link:
https://dropbox.com[random-id]/file-name.ext?rlkey=[security-key]&dl=0 
chỉ quan tâm đến phần dl=0. Nếu ng dùng chia sẻ link public -> đổi dl=0 thành dl=1 là xong, dropbox trả file thật như drive download link.

Và đưa vào pipeline:
Chuẩn hoá ảnh: base64.b64encode(image_file.read()).decode("utf-8") (opencv)
->
Agent 1:
Categorize vào từng niche, style,... OCR toàn bộ text phát hiện được (đọc data trong file json ra 1 biến, rồi inject vào prompt để categorize niche, style, sub niche, motifs). Cái này rất khó dùng OpenCV vì sẽ phải tải thêm model ~50MB (paddleocr)

-> output: Niche, style, motifs,... dạng json. Thêm 1 field “OCR_text”, top 5 logo nghi ngờ (thêm prompt về logo thôi).

Agent 2:
Nhân vật: Như giải thích trong tab data, sẽ dùng OpenCV và model anime_feature_extraction. Người nổi tiếng thì chỉ lấy tên và cho Claude kiểm tra được thôi.

Output ở giai đoạn này: Các nhân vật nổi tiếng mà claude nghi ngờ có trong đó -> Đối chiếu tên trong danh sách.. List các nhân vật alime thấy được qua model kia -> độ tin cậy (kiểu như model sẽ so khớp và xuất ra top 3 nhân vật có vẻ giống nhất). Đối chiếu text OCR với các cái tác phẩm nổi tiếng, câu nói trademark,... (file json) -> độ tin cậy
Yêu cầu claude tổng hợp và xuất thêm các yếu tố ‘định vị’. Tất cả mấy cái này cần phải có citation nguồn data (không cite cụ thể từ json)

1 check nữa: dùng OCR text và code python tách từ (kiểu sliding window) 1 số cụm, so khớp thẳng với top1000 trademark trong data sẵn có -> cái nào không có trong database thì live search (map ra nice-class trước)


“””
Agent 1 output (niche,..., OCR_text, suspected_logos) 
->
Agent2:
Claude vision lọc ra những tên nghi ngờ -> đối chiếu với danh sách tên celeb (code python)
Top 3 confidence từ model anime_feature_extraction
OpenCV so khớp top 5 kia với data logo (có ảnh)
// phần này dùng code python thuần
Dùng OCR text tách được từ agent1 -> sliding window đối chiếu các cụm với static data (top1000 trademark gì đó) -> nếu không có: map sang nice-class, live search, duyệt 2-3 trường hợp fuzzy
->
Yêu cầu claude tổng hợp và xuất thêm các yếu tố ‘định vị’. Tất cả mấy cái này cần phải có citation nguồn data (không cite cụ thể từ json)
-> Output agent 2 cho vào black box.
“””

Agent 3:
-> cho vào 1 agent: Thêm 1 feature để routing market: Tiêm cả policy, trend vào. Xuất ra 1 trường kiểu “top_country_suggestion” và “top_platform_suggestion”



Cho vào 1 ‘hộp đen’: Nếu cái top 3 kia có độ tin cậy vượt ngưỡng, hay text OCR trùng khớp hoàn toàn,... thì flag luôn là blocked. Nếu lưng chừng 50-80% thì risky. Gần như k có gì -> safe. -> xuất ra tag này.
Nhưng ngưỡng cũng phải tuỳ vào yếu tố.
Nếu độ tin cậy của phần NSFW / 18+ mà tầm 30% là block ngay.
Nhưng nếu claude vision xuất ra ngưỡng về giống nhân vật mà tầm 60-70% thì cũng chưa chắc. Trước hết cứ code sẵn bằng 1 vài con số tự nghĩ, rồi test mới biết được.

Agent 4: 
-> Agent cuối: Viết reasoning tổng hợp, mô tả vị trí bằng lời + ánh xạ cái top country với top platform kia ra. Nếu tag nhận được ở hộp đen kia là risky/block, gợi ý cách sửa.

Agent 2 và 3 chạy song song.


Xử lí PDF:
PDF sẽ được xử lý qua PyMuPDF, chia làm 2 nhánh dựa trên việc trang đầu có text layer thật hay không (page.get_text().strip() có nội dung > ~10 ký tự thì coi là "digital-native", ngược lại là "scanned/flat"). 
Với mọi loại PDF, luôn render trang đầu thành ảnh (page.get_pixmap() → PNG → base64) để đưa vào Agent 1/2 như một ảnh thường, phục vụ phân tích niche/style/motif/character/logo. Điểm khác biệt là nếu PDF thuộc loại digital-native, ta còn trích thêm text layer thật bằng page.get_text("blocks"), cho ra text kèm bounding box pixel chính xác — phần text này được dùng để đối chiếu trademark/OCR trực tiếp bằng Python (không cần Vision OCR lại, nhanh hơn và không có rủi ro đọc sai chữ), 
đồng thời bounding box thật này tốt hơn hẳn so với việc chỉ mô tả vị trí bằng lời/grid 3x3 mà ta đang dùng cho ảnh thường. 

Nếu là loại scanned/flat (không có text layer), PDF được coi hệt như ảnh JPG/PNG bình thường và để Vision tự OCR trong Agent 1. Cuối cùng, output của cả 2 nhánh đều được chuẩn hóa về cùng 1 shape (ảnh base64 + text kèm nguồn gốc "pdf_native" hoặc "vision_ocr") trước khi đi tiếp vào pipeline chung với CSV, upload, hay link — nên phần code còn lại của hệ thống không cần biết input gốc là PDF hay ảnh thường.


----


Logo - Brand:
1 thư mục ảnh: nike.png, adidas.png, kenchim.png,...
1 file JSON nhỏ ánh xạ tên↔đường dẫn file.
Khi người dùng ném vào 1 ảnh, claude vision truy cập file json kia (tiêm vào prompt) và xem xét là có sự xuất hiện của mấy cái trong thư mục ảnh kia trong cái ảnh ng dùng gửi không.

Danh sách tên những nhân vật alime/cartoon nổi tiếng (disney, pixar, dc,...)

Danh sách tên những người nổi tiếng.

Chỗ này có 2 cách: dùng OpenCV DNN: (deep neural networks) cho nhân vật anime
net = cv2.dnn.readNetFromONNX("anime_feature_extractor.onnx")
 # Thiết lập backend tối ưu hiệu năng net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV) net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU) # hoặc DNN_TARGET_CUDA ref_emb = extract_embedding(net, "character_ref.png") 
input_emb = extract_embedding(net, "scene_input.png")
score = compute_similarity(ref_emb, input_emb) 
print(f"Confidence: {score:.2f}%") -> cái này với bài toán của mình, phải trả về thêm toạ độ chính xác tìm thấy sự xuất hiện ở đâu.
Nhưng embedding model không thể trả về toạ độ -> dùng kĩ thuật sliding window hoặc YOLO pretrained cho phát hiện nhân vật hoạt hình.
Phần này khó quá thì thôi - dùng tên thôi cũng được.

Hoặc chỉ tin vào claude vision và tạo 1 file .md tên nhân vật.
Người nổi tiếng cũng có thể dùng model ArcFace, nhưng chắc chắn sẽ không thể chính xác -> t nghĩ đối với phần check nhân vật thì với anime này kia thì áp dụng OpenCV còn người thật thì chỉ để tên thôi. Nếu không sẽ ko khác gì xử lí bài toán face recognition & classification

Nội dung 18+/vũ khí/cấm: Claude vision làm rất tốt rồi, chỉ dùng prompt engineering và tổng hợp 1 file riêng (nếu cần)

Nhóm rủi ro: Câu chữ trademark ("Just Do It"...)
Data cần: Database trademark thật
Nguồn khả thi: USPTO có bulk data + API công khai (TESS/Trademark Case Files) — nguồn thật, hợp lệ theo yêu cầu "không
hardcode/không bịa". EUIPO eSearch tương tự cho EU
@vanh cái này chắc phải đi tìm từ API thật, tìm 1 lần rồi tổng hợp vào file, embedding nếu cần -> nói chung chỉ chạy 1 lần rồi cho LLM sử dụng làm context. Nên lấy tầm top 500-1000 thôi, không thì hàng triệu dòng.

Tác phẩm nghệ thuật bản quyền: Có thể liệt kê tên hoặc trích 1 số đoạn ngắn vào 1 file .md.

Font,... cái này thg tuấn anh confirm


Để xử lí ý về  
 Metadata tùy chọn kèm theo mỗi design
Thị trường target: US, EU, JP… (mỗi thị trường có luật khác nhau)
Platform bán: Etsy, Amazon Merch, TikTok Shop, Shopify… (mỗi nền tảng có policy riêng)
: 
Tạo 1 bộ file như sau để tiêm vào prompt



–Niche recognition–
Có thể làm theo kiểu nested json như này:
(cố gắng chốt schema sớm)


{
  "niches": {
    "christmas": {
      "names": [
        "christmas",
        "xmas",
        "holiday",
        "festive"
      ],
      "sub_niches": [
        "family_christmas",
        "religious",
        "commercial"
      ],
      "risky_motifs": [
        "violence",
        "guns"
      ],
      "verdict": "RISKY if guns detected"
    },
    "dog_lovers": {
      "names": [
        "dog",
        "dog mom",
        "puppy",
        "canine"
      ],
      "sub_niches": [
        "golden_retriever",
        "dachshund",
        "dog_mom"
      ],
      "risky_motifs": [],
      "verdict": "SAFE (no inherent risk)"
    },
    "nurse": {
      "names": [
        "nurse",
        "nursing",
        "RN",
        "medical",
        "healthcare"
      ],
      "sub_niches": [
        "ICU",
        "ER",
        "pediatric",
        "travel_nurse"
      ],
      "risky_motifs": [
        "guns",
        "weapons",
        "violence"
      ],
      "verdict": "BLOCKED if weapons"
    },
    "fishing": {
      "names": [
        "fishing",
        "angler",
        "fisher"
      ],
      "sub_niches": [
        "bass_fishing",
        "fly_fishing"
      ],
      "risky_motifs": [
        "guns",
        "violence"
      ],
      "verdict": "RISKY if guns (hunting ambiguity)"
    },
    "halloween": {
      "names": [
        "halloween",
        "spooky",
        "horror",
        "trick_or_treat"
      ],
      "sub_niches": [
        "gothic",
        "witches",
        "zombies"
      ],
      "risky_motifs": [
        "blood",
        "gore"
      ],
      "verdict": "CONTEXTUAL (blood = OK, excessive gore = RISKY)"
    },
    "anime": {
      "names": [
        "anime",
        "manga",
        "japanese_animation"
      ],
      "sub_niches": [
        "shounen",
        "shoujo",
        "slice_of_life"
      ],
      "risky_motifs": [],
      "verdict": "SAFE (check character copyright separately)"
    }
  },
  "styles": {
    "vintage": [
      "retro",
      "70s",
      "80s"
    ],
    "minimalist": [
      "clean",
      "simple",
      "zen"
    ],
    "cartoon": [
      "anime",
      "comic",
      "illustration"
    ],
    "retro_90s": [
      "y2k",
      "millennial"
    ]
  },
  "motifs": {
    "skulls": [
      "skull",
      "skeleton"
    ],
    "flowers": [
      "flower",
      "flora",
      "rose"
    ],
    "guns": [
      "gun",
      "rifle",
      "pistol",
      "weapon"
    ],
    "religious_symbols": [
      "cross",
      "crescent",
      "star of david"
    ]
  }
}


Mình có lẽ chỉ nên làm 1 số sub-niche cụ thể và phân loại nó vào đó,



---

từ 1 ảnh input (png, jpg,...) m cần tạo 1 module:
def match_character(image_path: str) -> dict:
    """
    Input: đường dẫn ảnh design
    Output: {"matches": [{"character_name": str, "confidence": float}, ...]}  # top 3
    """
nhân vật anime/cartoon:
{
  "matches": [
    {
      "character_name": "pikachu",
      "confidence": 89.5
    },
    {
      "character_name": "charizard",
      "confidence": 72.1
    },
    {
      "character_name": "naruto",
      "confidence": 45.3
    }
  ]
}
def match_logo(image_path: str, suspected_logos: dict) -> dict:
    """
    Input:
      - image_path: đường dẫn ảnh design
      - suspected_logos: kết quả từ Agent 1 (Vision), dạng
          {"suspected_logos": [{"brand_name": "nike", "confidence": str}, ...]}
        → module chỉ cần lấy list tên brand từ đây để biết CHẠY EMBEDDING CHO NHỮNG BRAND NÀO,
          không cần tự quét toàn bộ manifest
    Output: {"matches": [{"brand_name": str, "confidence": float}, ...]} # (KHÔNG giới hạn cứng ở 5 — input bao nhiêu, xử lý bấy nhiêu)    
 """
logo: từ 1 ảnh design và input:
{
  "suspected_logos": [
    {"brand_name": "nike", "confidence": “high”},
    {"brand_name": "adidas", "confidence": “medium”}
	….
  ]
}
(input bao nhiêu làm bấy nhiêu)  cần bắt được trong đó có sự xuất hiện của logo nào
{
  "matches": [
    {"brand_name": "nike", "confidence": 91.2},
    {"brand_name": "adidas", "confidence": 22.4},
    {"brand_name": "puma", "confidence": 15.0},
    {"brand_name": "reebok", "confidence": 8.3},
    {"brand_name": "disney", "confidence": 3.1}
  ]
}
(Ảnh logo mẫu sẽ có 1 folder đặt tên theo định dạng nike.png, adidas.png,...)
font chữ:
def extract_fonts(image_path: str) -> dict:
    """
    Input: đường dẫn ảnh design
    Output: {"fonts_detected": [{"font_family_guess": str, "sample_text": str, "confidence": str}, ...]}  # toàn bộ
confidence là low/medium/high 
    """
{
  "fonts_detected": [
    {"font_family_guess": "bold sans-serif condensed", "sample_text": "MERRY CHRISTMAS", "confidence": "medium"},
    {"font_family_guess": "script/cursive", "sample_text": "est. 2024", "confidence": "low"}
  ]
}
cần tất cả các font bắt được trong ảnh. Input 1 ảnh ra được như kia



