"""
compliance_checker/orchestrator.py — process_one_design(), process_batch(): nơi
asyncio.gather THẬT SỰ nằm (tách khỏi agents.py vì khác trách nhiệm, CLAUDE.md mục 0).

Thứ tự thực thi bám sát ĐÚNG mục 8 (concrete pseudocode) của CLAUDE.md, không phải sơ đồ
ASCII ở mục 2 (2 chỗ có khác biệt nhỏ về vị trí Agent 4/Nhóm C — mục 8 là pseudocode chạy
được nên được coi là nguồn xác thực hơn):
  Call 1 (Agent 1 classify) -> [Agent 2 + match_logo + match_character + trademark_resolver
  + Agent 4, chạy SONG SONG] -> Black Box (Python, tức thời) -> Nhóm C + Agent 3 (GỘP 1 call,
  2026-08-22 — xem agents.py::run_synthesis_and_reasoning, tối ưu latency, chạy SAU black box
  vì cần biết verdict) -> merge -> trả kết quả.
"""

import asyncio
import base64
import os
import tempfile
import uuid

from compliance_checker.engine import agents as cc_agents
from compliance_checker.engine import black_box as cc_black_box
from compliance_checker.engine import opencv_modules as cc_opencv
from compliance_checker.engine import trademark_resolver as cc_trademark
from compliance_checker.ingestion.file_loader import DesignFileLoader, DesignFileLoaderError
from compliance_checker.ingestion.link_normalizer import normalize_url_to_bytes

_loader = DesignFileLoader()
_RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def _write_temp_image(img_bytes: bytes, ext: str = ".png") -> str:
    """OpenCV modules (opencv_modules.py) cần 1 image_path thật (string) theo đúng contract
    CLAUDE.md mục 3 — dù nguồn gốc là base64/link/PDF-render, vẫn cần lưu tạm ra đĩa 1 lần.
    ext mặc định .png (trường hợp phổ biến nhất — ảnh đã render/convert); truyền ext khác khi
    cần ghi tạm bytes GỐC (vd .pdf/.psd tải từ link) để DesignFileLoader.load_as_image() tự
    dispatch đúng nhánh xử lý theo phần mở rộng."""
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, f"compliance_check_{uuid.uuid4().hex}{ext}")
    with open(tmp_path, "wb") as f:
        f.write(img_bytes)
    return tmp_path


def _safe_or_default(value, default, label: str, warnings: list):
    """return_exceptions=True trả Exception object thay vì raise — chặn ở đây, KHÔNG để lỗi
    1 nhánh làm sập cả pipeline (CLAUDE.md mục 10: mọi asyncio.gather phải return_exceptions=True
    VÀ có xử lý fallback tương ứng, không chỉ đơn thuần bật cờ)."""
    if isinstance(value, Exception):
        warnings.append(f"{label} lỗi, dùng giá trị mặc định: {value}")
        return default
    return value if value is not None else default


def _merge_detected_faces(face_crops: list, face_identifications: list) -> list:
    """(2026-08-21) Ghép opencv_modules.detect_and_crop_faces()["faces"] (bbox_norm, theo thứ
    tự index gửi cho Agent 2) với agents.py::run_agent2_verify_candidates()["face_identifications"]
    (face_index/suspected_name/confidence/reasoning) thành shape CUỐI cho FE (schemas.DetectedFace).
    CỐ Ý bỏ "face_base64" (không xuất khuôn mặt crop ra FE nữa, chỉ dùng nội bộ để gửi Agent 2 —
    xem run_agent2_verify_candidates, KHÔNG lộ ra response cuối) và "detection_score" (độ tin
    cậy CÓ-PHẢI-MẶT của BlazeFace, khác hẳn "confidence" nhận diện danh tính của Agent 2, giữ 2
    khái niệm lẫn nhau sẽ gây hiểu nhầm — detection_score chỉ dùng nội bộ opencv_modules.py)."""
    by_index = {f["face_index"]: f for f in (face_identifications or []) if "face_index" in f}
    out = []
    for i, crop in enumerate(face_crops or []):
        ident = by_index.get(i, {})
        out.append({
            "bbox_norm": crop.get("bbox_norm", []),
            "suspected_name": ident.get("suspected_name"),
            "confidence": ident.get("confidence"),
            "reasoning": ident.get("reasoning", ""),
        })
    return out


def _build_flagged_regions(text_blocks: list, trademark_flags: list, text_trademark_flags: list, detected_faces: list) -> list:
    """
    (2026-08-21) Xây dựng schemas.FlaggedRegion — danh sách RÚT GỌN, CHỈ gồm vùng đáng nghi để
    FE vẽ khung khoanh vùng lên ẢNH GỐC (thay thế hoàn toàn cách hiện thumbnail crop riêng
    trước đây). THUẦN PYTHON, bbox_norm luôn lấy từ dữ liệu THẬT (text_blocks/detected_faces đã
    có toạ độ chính xác) — KHÔNG bao giờ để LLM tự đoán toạ độ.

    2 nguồn gộp chung (⚠️ 2026-08-22: bớt 1 nguồn — xem bên dưới):
    1. trademark_flags (Python match database THẬT, static/live — KHÔNG đổi) — tìm block chứa
       đúng phrase đã match (substring, case-insensitive) để lấy bbox; không tìm được thì bỏ
       qua (KHÔNG đoán bbox — thà thiếu box còn hơn box sai). text_blocks giờ LUÔN rỗng (RapidOCR
       đã rút khỏi flow, xem orchestrator.process_one_design) nên nhánh này hiện KHÔNG sinh box
       nào — giữ nguyên code (không phải dead code thật, chỉ đang thiếu nguồn bbox) để tự động
       hoạt động lại nếu sau này bật lại RapidOCR.
    2. detected_faces đã merge (Agent 2 TASK 2) — (2026-08-22, ĐỔI) giờ khoanh TOÀN BỘ khuôn mặt
       BlazeFace phát hiện được, KỂ CẢ mặt Agent 2 KHÔNG nhận diện được danh tính — trước đây chỉ
       khoanh mục có suspected_name, bỏ sót phần lớn crop thật (đa số mặt trong ảnh thường KHÔNG
       phải người nổi tiếng). Theo yêu cầu: hiện đúng những gì BlazeFace THẬT SỰ crop được, không
       ẩn bớt — label phân biệt rõ "đã nhận diện được tên" vs "chưa xác định được là ai".

    text_trademark_flags (Agent 2 TASK 3, "cảm nhận" riêng) KHÔNG còn góp bbox ở đây nữa — từ
    khi TASK 3 chuyển sang dùng OCR_text thô (agents.py::run_agent2_verify_candidates, không còn
    text_blocks có index/bbox), Agent 2 không còn cách nào trỏ về toạ độ cụ thể. Vẫn ảnh hưởng
    verdict/reasoning bình thường qua black_box.py, chỉ KHÔNG khoanh được vùng trên ảnh gốc nữa.
    """
    out = []
    for f in trademark_flags or []:
        phrase = (f.get("phrase") or "").strip().lower()
        if not phrase or f.get("source") not in ("static", "live_exact", "live_fuzzy"):
            continue
        for block in text_blocks or []:
            block_text = (block.get("text") or "").lower().replace("\n", " ")
            if phrase in block_text:
                out.append({
                    "kind": "text",
                    "bbox_norm": block["bbox_norm"],
                    "label": f.get("phrase", ""),
                    "detail": "Trùng khớp database" + (f" (chủ sở hữu: {f.get('owner')})" if f.get("owner") else ""),
                })
                break  # 1 block khớp đầu tiên là đủ, tránh box trùng lặp cho cùng 1 phrase

    for face in detected_faces or []:
        bbox = face.get("bbox_norm")
        if not bbox:
            continue  # thiếu toạ độ thật -> bỏ qua, KHÔNG đoán (nguyên tắc chung của hàm này)
        suspected_name = face.get("suspected_name")
        out.append({
            "kind": "face",
            "bbox_norm": bbox,
            "label": suspected_name or "Khuôn mặt phát hiện (chưa xác định danh tính)",
            "detail": face.get("reasoning", "") or "BlazeFace phát hiện có khuôn mặt tại đây — Agent 2 không xác định được đây là ai cụ thể.",
        })
    return out


async def _resolve_input_to_image(image_base64: "str | None", file_path: "str | None", url: "str | None"):
    """
    Chuẩn hoá 1 trong 3 cách nhập (upload base64 / file_path cục bộ / url) về CÙNG 1 shape:
    (base64_str, local_image_path_cho_opencv, pdf_metadata_hoac_None, source_type).
    """
    if image_base64:
        raw = image_base64.split(",", 1)[-1] if image_base64.startswith("data:image") else image_base64
        img_bytes = base64.b64decode(raw)
        tmp_path = _write_temp_image(img_bytes)
        return image_base64, tmp_path, None, "image", True  # True = tmp_path cần tự xoá sau

    if url:
        raw_bytes = await normalize_url_to_bytes(url)
        # ⚠️ FIX khoảng trống thật: trước đây LUÔN giả định link trỏ tới ảnh thuần — nếu link
        # (Google Drive/Dropbox/S3/bất kỳ, không riêng loại nào) trỏ tới PDF/PSD, decode sẽ lỗi
        # thay vì tự nhận ra. Sniff magic bytes trước (DesignFileLoader.sniff_extension), CHỈ
        # đi nhánh ghi-tạm-ra-đĩa-rồi-dispatch khi THẬT SỰ không phải ảnh raster — giữ nguyên
        # đường đi nhẹ (memory-only, không ghi đĩa 2 lần) cho case phổ biến nhất là ảnh.
        ext = _loader.sniff_extension(raw_bytes)
        if ext in (".pdf", ".psd"):
            raw_tmp_path = _write_temp_image(raw_bytes, ext=ext)
            try:
                img = _loader.load_as_image(raw_tmp_path)  # tái dùng dispatcher có sẵn — PDF nhiều trang/PSD đều đúng
            finally:
                if os.path.exists(raw_tmp_path):
                    os.remove(raw_tmp_path)
            b64 = _loader.to_base64(img)
            pdf_meta = getattr(img, "_pdf_metadata", None)
            if pdf_meta:
                source_type = "pdf_digital_native" if pdf_meta.get("pdf_type") == "digital_native" else "pdf_scanned"
            else:
                source_type = "psd"
            tmp_path = _write_temp_image(base64.b64decode(b64))
            return b64, tmp_path, pdf_meta, source_type, True

        img = _loader.load_bytes_as_image(raw_bytes)
        b64 = _loader.to_base64(img)
        tmp_path = _write_temp_image(base64.b64decode(b64))
        return b64, tmp_path, None, "image", True

    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        img = _loader.load_as_image(file_path)
        b64 = _loader.to_base64(img)
        pdf_meta = getattr(img, "_pdf_metadata", None)
        if pdf_meta:
            source_type = "pdf_digital_native" if pdf_meta.get("pdf_type") == "digital_native" else "pdf_scanned"
        elif ext == ".psd":
            source_type = "psd"
        else:
            source_type = "image"

        if ext in _RASTER_EXTENSIONS:
            # Ảnh raster gốc đã đúng định dạng OpenCV đọc được trực tiếp -> dùng luôn file
            # gốc, không cần re-save (đỡ tốn I/O), và KHÔNG được tự xoá file gốc của user.
            return b64, file_path, pdf_meta, source_type, False
        tmp_path = _write_temp_image(base64.b64decode(b64))
        return b64, tmp_path, pdf_meta, source_type, True

    raise ValueError("Cần cung cấp ít nhất 1 trong 3: image_base64, file_path, url")


async def process_one_design(
    image_base64: "str | None" = None,
    file_path: "str | None" = None,
    url: "str | None" = None,
    platform: "str | None" = None,
    target_country: str = "US",
    niche_hint: "str | None" = None,
) -> dict:
    """Điểm vào chính cho 1 design — trả về dict đúng shape schemas.DesignComplianceResult."""
    warnings: list[str] = []

    img_b64, local_path, pdf_meta, source_type, should_cleanup = await _resolve_input_to_image(
        image_base64, file_path, url
    )

    # PDF nhiều trang: pdf_processor.py giờ render/phân tích TẤT CẢ trang (tới trần
    # _MAX_PAGES_TO_RENDER) và gửi cùng lúc cho Vision trong 1 message — chỉ cảnh báo nếu PDF
    # thật sự VƯỢT trần đó (số ít trường hợp), để không có trang nào bị bỏ qua trong im lặng.
    total_pages = (pdf_meta or {}).get("total_pages", 1)
    pages_rendered = (pdf_meta or {}).get("pages_rendered", total_pages)
    if total_pages and pages_rendered < total_pages:
        warnings.append(
            f"PDF có {total_pages} trang, chỉ {pages_rendered} trang đầu được phân tích "
            f"(giới hạn để tránh request quá nặng) — {total_pages - pages_rendered} trang cuối CHƯA được xử lý."
        )

    # Nhiều trang -> gửi cả list ảnh cho Vision trong 1 message (xem agents.py::_build_messages).
    # Ảnh dùng cho OpenCV (local_path) vẫn CHỈ là trang 1 — giữ đúng contract "1 image_path"
    # của opencv_modules.py (CLAUDE.md mục 3), không đổi khi vẫn còn là placeholder.
    vision_images = (pdf_meta or {}).get("page_images_base64") or img_b64

    try:
        # ---- Call 1: Agent 1 Classify (TUẦN TỰ bắt buộc — Call 2 cần niche/OCR từ đây) ----
        # detect_and_crop_faces (BlazeFace, 2026-08-21 BẬT LẠI): KHÔNG phụ thuộc classify (chỉ
        # cần local_path, đã có sẵn) -> kick off CONCURRENT với Agent 1 để không cộng dồn
        # latency (xong trước khi Agent 2 cần tới, bên dưới).
        # ⚠️ extract_text_blocks (RapidOCR) VẪN TẮT — nghi ngờ đây mới là model tốn RAM nhất
        # (3 model ONNX detect+classify+recognize cùng lúc, so với BlazeFace chỉ 1 model nhẹ) —
        # tái hiện thật OOM 502 trên Render khi cả 2 cùng chạy. OCR text vẫn dùng Vision (Agent 1
        # bên dưới) làm nguồn duy nhất cho tới khi xác nhận RapidOCR an toàn để bật lại riêng.
        face_crop_task = asyncio.create_task(asyncio.to_thread(cc_opencv.detect_and_crop_faces, local_path))
        classify = await asyncio.to_thread(cc_agents.run_agent1_classify, vision_images)

        if pdf_meta and pdf_meta.get("pdf_type") == "digital_native" and pdf_meta.get("all_pages_native_text"):
            # PDF digital-native: text layer THẬT (MỌI trang đã render, không chỉ trang 1) chính
            # xác hơn Vision OCR -> ưu tiên dùng thay thế để match trademark trực tiếp bằng
            # Python (CLAUDE.md mục 1.3) — dùng all_pages_native_text thay vì native_text (chỉ
            # trang 1) để không bỏ sót trademark nằm ở trang 2+.
            classify["OCR_text"] = pdf_meta["all_pages_native_text"]
            classify["text_source"] = "pdf_native"

        niche = niche_hint or classify["niche"]

        # ---- Mọi nhánh KHÔNG phụ thuộc lẫn nhau trong CÙNG 1 design -> chạy SONG SONG ----
        # Agent 2 (2026-08-21, THIẾT KẾ LẠI): không còn tự detect character/celebrity — giờ
        # verify lại đúng candidate Agent 1 đã nêu (logo+character+celebrity gộp chung, xem
        # agents.py::run_agent2_verify_candidates). Vẫn chạy song song ở đây vì chỉ phụ thuộc
        # classify (đã có), không phụ thuộc bất kỳ nhánh nào khác trong gather này.
        candidates_for_verify = {
            "logos": classify["suspected_logos"],
            "characters": classify["suspected_characters"],
            "celebrities": classify["suspected_celebrities"],
            "fonts": classify["suspected_fonts"],
            "artworks": classify["suspected_artworks"],
        }
        # face_crop_task đã chạy song song từ lúc classify bắt đầu — await ở đây để lấy dữ
        # liệu THẬT (crop mặt) truyền cho Agent 2. Lỗi ở nhánh này KHÔNG được làm sập cả design
        # (fail-open, giống mọi nhánh khác).
        try:
            face_crops_result = await face_crop_task
        except Exception as e:
            face_crops_result = e
        face_crops_result = _safe_or_default(face_crops_result, {"faces": []}, "detect_and_crop_faces", warnings)

        # ⚠️ text_blocks VẪN đặt cứng RỖNG — extract_text_blocks (RapidOCR) vẫn tắt (xem ghi
        # chú phía trên). Chỉ còn dùng để truyền cho _build_flagged_regions() (khoanh vùng bbox
        # thật cho FE, hiện không sinh box nào vì thiếu nguồn — xem docstring hàm đó), KHÔNG còn
        # truyền cho Agent 2 nữa.
        text_blocks = []

        # Trademark matching (Python, database THẬT) quay lại dùng THẲNG OCR_text của Vision
        # (Agent 1) — nguồn OCR duy nhất bây giờ, đúng như trước khi có RapidOCR. Agent 2 TASK 3
        # (agents.py::run_agent2_verify_candidates, "cảm nhận" riêng của LLM) dùng CHUNG chuỗi
        # này — KHÔNG còn indexed block nào để truyền, chỉ còn raw text (đủ cho task ngôn ngữ
        # thuần tuý này, xem ghi chú trong agents.py).
        trademark_source_text = classify["OCR_text"]

        agent2_result, logo_match, char_match, trademark_flags, market = await asyncio.gather(
            asyncio.to_thread(cc_agents.run_agent2_verify_candidates, vision_images, candidates_for_verify, face_crops_result["faces"], trademark_source_text),
            asyncio.to_thread(cc_opencv.match_logo, local_path, {"suspected_logos": classify["suspected_logos"]}),
            asyncio.to_thread(cc_opencv.match_character, local_path),
            cc_trademark.resolve_trademark_phrases(trademark_source_text, niche),
            asyncio.to_thread(cc_agents.run_agent4_market_suggestion, niche, classify["style"], target_country, platform),
            return_exceptions=True,
        )

        agent2_result = _safe_or_default(
            agent2_result, {"verifications": [], "face_identifications": [], "text_trademark_flags": []}, "Agent 2", warnings
        )
        logo_match = _safe_or_default(logo_match, {"matches": []}, "match_logo", warnings)
        char_match = _safe_or_default(char_match, {"matches": []}, "match_character", warnings)
        trademark_flags = _safe_or_default(trademark_flags, [], "trademark_resolver", warnings)
        market = _safe_or_default(
            market,
            {"top_country_suggestion": "", "top_platform_suggestion": "", "rationale": ""},
            "Agent 4", warnings
        )

        # ---- Black Box: Python thuần, tức thời, quyết định verdict ----
        # Truyền thêm suspected_logos/suspected_characters/suspected_celebrities (Agent 1/2) để
        # black_box tự đối chiếu tên với logo_refs/manifest.json + character_list.md/
        # celebrity_list.md — nếu không, verdict về logo/nhân vật/celeb sẽ luôn SAFE cho tới khi
        # opencv_modules có thuật toán thật (hiện là placeholder), vì Nhóm C chỉ dùng evidence để
        # VIẾT LỜI, không quyết định verdict (CLAUDE.md mục 10: LLM không được tự quyết GO/NO-GO).
        black_box_result = cc_black_box.run_black_box(
            char_match, logo_match, trademark_flags, niche, classify["motifs"],
            suspected_characters=classify["suspected_characters"],
            suspected_celebrities=classify["suspected_celebrities"],
            ocr_text=classify["OCR_text"],
            suspected_logos=classify["suspected_logos"],
            agent2_verifications=agent2_result["verifications"],
            face_identifications=agent2_result["face_identifications"],
            text_trademark_flags=agent2_result["text_trademark_flags"],
            suspected_fonts=classify["suspected_fonts"],
            suspected_artworks=classify["suspected_artworks"],
        )

        # ---- Nhóm C + Agent 3 GỘP LÀM 1 (2026-08-22, tối ưu latency — xem agents.py::
        # run_synthesis_and_reasoning) — CHẠY SAU black box (cần biết verdict để giải thích).
        # Output SHAPE giữ NGUYÊN như khi còn 2 hàm tuần tự (positioning_notes/summary/
        # reasoning/fix_suggestions), chỉ còn 1 round-trip LLM thay vì 2.
        evidence_bundle = {
            "suspected_logos": classify["suspected_logos"],
            "suspected_characters": classify["suspected_characters"],
            "suspected_celebrities": classify["suspected_celebrities"],
            "suspected_fonts": classify["suspected_fonts"],
            "suspected_artworks": classify["suspected_artworks"],
            "agent2_verifications": agent2_result["verifications"],
            "text_trademark_flags": agent2_result["text_trademark_flags"],
            "logo_match": logo_match, "char_match": char_match,
            "trademark_flags": trademark_flags,
        }
        # platform/target_country truyền vào ĐÂY (không phải Agent 4 nữa) để TASK C
        # (selected_platform_suitable) có verdict/evidence thật khi thẩm định — xem ghi chú
        # đầy đủ trong agents.py::run_agent4_market_suggestion + run_synthesis_and_reasoning.
        synthesis_result = await asyncio.to_thread(
            cc_agents.run_synthesis_and_reasoning, vision_images, evidence_bundle, black_box_result,
            pdf_meta.get("text_blocks_with_bbox") if pdf_meta else None,
            platform, target_country,
        )
        # market_suggestion cuối = gộp gợi ý ĐỘC LẬP (Agent 4, verdict-blind, chạy song song) +
        # thẩm định platform ĐÃ CHỌN (từ synthesis_result, verdict-aware, chạy sau black box) —
        # shape cuối GIỮ NGUYÊN y hệt Agent4Result cũ (schemas.py không cần đổi gì).
        market = {
            **market,
            "selected_platform_suitable": synthesis_result["selected_platform_suitable"],
            "selected_platform_rationale": synthesis_result["selected_platform_rationale"],
        }

        # flagged_regions: khoanh vùng THẬT (Python, KHÔNG LLM đoán toạ độ) cho cả text lẫn mặt
        # đáng nghi — thay thế hoàn toàn cách hiện thumbnail crop riêng trước đây.
        detected_faces_merged = _merge_detected_faces(face_crops_result["faces"], agent2_result["face_identifications"])
        flagged_regions = _build_flagged_regions(
            text_blocks, trademark_flags, agent2_result["text_trademark_flags"], detected_faces_merged
        )

        return {
            "niche": niche,
            "sub_niche": classify["sub_niche"],
            "style": classify["style"],
            "motifs": classify["motifs"],
            "OCR_text": classify["OCR_text"],
            "suspected_logos": classify["suspected_logos"],
            "suspected_characters": classify["suspected_characters"],
            "suspected_celebrities": classify["suspected_celebrities"],
            "suspected_fonts": classify["suspected_fonts"],
            "suspected_artworks": classify["suspected_artworks"],
            "verifications": agent2_result["verifications"],
            "final_verdict": black_box_result["final_verdict"],
            "overall_confidence": black_box_result["overall_confidence"],
            "evidence": black_box_result["evidence"],
            "positioning_notes": synthesis_result["positioning_notes"],
            "detected_faces": detected_faces_merged,
            "flagged_regions": flagged_regions,
            "reasoning": synthesis_result["reasoning"],
            "fix_suggestions": synthesis_result["fix_suggestions"],
            "market_suggestion": market,
            "font_disclaimer": (
                "Font detection is best-effort. Recommend manual verification against font "
                "license databases (MyFonts, Adobe Fonts, Font Squirrel)."
            ),
            "source_type": source_type,
            "warnings": warnings,
        }
    finally:
        if should_cleanup and local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


async def process_batch(rows: list[dict], platform: "str | None" = None, target_country: str = "US", max_concurrency: int = 1) -> dict:
    """
    rows: list dict đã chuẩn hoá từ csv_batch.parse_csv_rows() (có _row_index, _input_ref,
    file_path/url tuỳ dòng). Exception ở 1 design KHÔNG được làm hỏng cả batch — catch riêng
    từng cái trong with_limit(), KHÔNG chỉ dựa vào return_exceptions=True ở gather ngoài cùng.

    ⚠️ (2026-08-22) max_concurrency default ĐỔI 5 -> 1 (chạy TUẦN TỰ) — phát hiện thật qua batch
    10 link crash "Failed to fetch" ngay lập tức trên Render: N design chạy ĐỒNG THỜI (mỗi design
    tự tải ảnh + BlazeFace + giữ payload Vision trong RAM cùng lúc) nhân N lần áp lực bộ nhớ so
    với 1 design đơn — vốn ĐÃ từng tự crash process 1 mình (xem docs.md, mục OOM). Tuần tự loại
    bỏ hệ số nhân N-cùng-lúc, nhưng KHÔNG đảm bảo tuyệt đối hết OOM (1 design nặng đơn lẻ vẫn có
    thể chạm trần RAM gói Render đang dùng — vẫn cần xác nhận RAM thật của gói đó). Vẫn nhận
    tham số max_concurrency > 1 nếu caller CHỦ Ý truyền vào (route/schema cho phép 1-20), CHỈ đổi
    GIÁ TRỊ MẶC ĐỊNH khi không truyền gì.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def with_limit(row: dict) -> dict:
        async with semaphore:
            # Self-grading: nếu row đi kèm cột "expected_*" (vd file mẫu THẬT của BGK
            # design_samples_template.xlsx), so verdict thật với đáp án mẫu — KHÔNG bắt buộc
            # phải có, chỉ bật khi input thật sự cung cấp (csv_batch._EXPECTED_COLUMN_ALIASES).
            # Tính TRƯỚC try/except để dòng lỗi (vd file mẫu chưa điền cột "design") vẫn hiện
            # được đáp án mẫu cho team biết cần nguồn ảnh gì, thay vì mất trắng thông tin đó.
            expected = {k.lstrip("_"): v for k, v in row.items() if k in (
                "_expected_niche", "_expected_sub_niche", "_expected_style", "_expected_motifs",
                "_expected_verdict", "_expected_violation_type", "_expected_violation_detail",
                "_expected_confidence", "_notes",
            )}
            try:
                result = await process_one_design(
                    image_base64=row.get("image_base64"),  # ảnh dán trực tiếp trong Excel (csv_batch.parse_xlsx_rows)
                    file_path=row.get("file_path"),
                    url=row.get("url"),
                    platform=row.get("platform") or platform,
                    target_country=row.get("target_country") or target_country,
                    niche_hint=row.get("niche_hint"),
                )
                row_result = {"row_index": row["_row_index"], "input_ref": row["_input_ref"], "status": "OK", "result": result, "error": None}
                if expected:
                    row_result["grading"] = {
                        "expected": expected,
                        "verdict_match": expected.get("expected_verdict") == result["final_verdict"],
                    }
                return row_result
            except Exception as e:
                row_result = {"row_index": row["_row_index"], "input_ref": row["_input_ref"], "status": "ERROR", "result": None, "error": str(e)}
                if expected:
                    row_result["grading"] = {"expected": expected, "verdict_match": False}
                return row_result

    row_results = await asyncio.gather(*[with_limit(r) for r in rows], return_exceptions=True)

    clean_rows = []
    for i, r in enumerate(row_results):
        if isinstance(r, Exception):
            # Lưới an toàn kép — không nên xảy ra vì with_limit() đã tự catch, nhưng phòng
            # trường hợp lỗi xảy ra NGOÀI try/except (vd asyncio.CancelledError).
            clean_rows.append({"row_index": i, "input_ref": f"row_{i}", "status": "ERROR", "result": None, "error": str(r)})
        else:
            clean_rows.append(r)

    def _count(tag: "str | None" = None, status: "str | None" = None) -> int:
        if status == "ERROR":
            return sum(1 for r in clean_rows if r["status"] == "ERROR")
        return sum(1 for r in clean_rows if r["status"] == "OK" and r["result"]["final_verdict"] == tag)

    # verdict_accuracy: CHỈ tính trên dòng "OK" có "grading" (tức input có cột expected_verdict
    # VÀ pipeline thật sự chạy ra được verdict, vd file mẫu BGK design_samples_template.xlsx
    # nhưng đã có ảnh thật ở cột "design") — dòng ERROR (vd chưa điền ảnh) vẫn giữ "grading" để
    # hiện đáp án mẫu tham khảo trong CSV export, nhưng KHÔNG tính vào accuracy (lỗi thiếu input
    # không phải verdict sai, gộp chung sẽ làm số % hiểu nhầm là model tệ trong khi thực ra chỉ
    # là chưa có ảnh để chạy). None nếu batch này không có dòng OK+grading nào.
    graded_rows = [r for r in clean_rows if r["status"] == "OK" and r.get("grading")]
    verdict_accuracy = (
        round(100.0 * sum(1 for r in graded_rows if r["grading"]["verdict_match"]) / len(graded_rows), 1)
        if graded_rows else None
    )

    return {
        "total": len(clean_rows),
        "safe_count": _count(tag="SAFE"),
        "risky_count": _count(tag="RISKY"),
        "blocked_count": _count(tag="BLOCKED"),
        "error_count": _count(status="ERROR"),
        "graded_count": len(graded_rows),
        "verdict_accuracy": verdict_accuracy,
        "rows": clean_rows,
    }
