"""
compliance_checker/orchestrator.py — process_one_design(), process_batch(): nơi
asyncio.gather THẬT SỰ nằm (tách khỏi agents.py vì khác trách nhiệm, CLAUDE.md mục 0).

Thứ tự thực thi bám sát ĐÚNG mục 8 (concrete pseudocode) của CLAUDE.md, không phải sơ đồ
ASCII ở mục 2 (2 chỗ có khác biệt nhỏ về vị trí Agent 4/Nhóm C — mục 8 là pseudocode chạy
được nên được coi là nguồn xác thực hơn):
  Call 1 (Agent 1 classify) -> [Agent 2 + match_logo + match_character + trademark_resolver
  + Agent 4, chạy SONG SONG] -> Black Box (Python, tức thời) -> Nhóm C (synthesis) -> Agent 3
  (reasoning, chạy SAU black box vì cần biết verdict) -> merge -> trả kết quả.
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


def _inject_text_region_bbox(positioning_notes: list, text_regions: list) -> list:
    """Gắn bbox_norm THẬT (Python, KHÔNG phải LLM đoán) vào positioning_note category=
    'trademark_text', dùng vùng chữ LỚN NHẤT phát hiện được bởi opencv_modules.detect_text_regions()
    (đã sort giảm dần theo area_ratio). Best-effort: nếu ảnh có nhiều dòng chữ khác nhau, vùng
    lớn nhất không chắc chắn là ĐÚNG cụm từ bị flag — vẫn hữu ích để định hướng trực quan, và
    trung thực hơn hẳn để LLM tự đoán toạ độ pixel (CLAUDE.md: Vision không đáng tin ở mức đó).
    Không có text_regions -> giữ nguyên location_description bằng lời, không thêm bbox."""
    if not text_regions:
        return positioning_notes
    largest = text_regions[0]
    for note in positioning_notes:
        if note.get("category") == "trademark_text":
            note["bbox_norm"] = largest["bbox_norm"]
            note["bbox_source"] = "opencv_mser"
    return positioning_notes


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
        # detect_text_regions: OpenCV cổ điển (MSER, không model/dataset) — thay hướng
        # match_character/match_logo embedding đã bị bỏ (quá khó trong thời gian hackathon),
        # dùng để khoanh vùng chữ THẬT trên ảnh thay cho mô tả grid 3x3 bằng lời của Nhóm C.
        # Agent 2 (2026-08-21, THIẾT KẾ LẠI): không còn tự detect character/celebrity — giờ
        # verify lại đúng candidate Agent 1 đã nêu (logo+character+celebrity gộp chung, xem
        # agents.py::run_agent2_verify_candidates). Vẫn chạy song song ở đây vì chỉ phụ thuộc
        # classify (đã có), không phụ thuộc bất kỳ nhánh nào khác trong gather này.
        candidates_for_verify = {
            "logos": classify["suspected_logos"],
            "characters": classify["suspected_characters"],
            "celebrities": classify["suspected_celebrities"],
        }
        agent2_result, logo_match, char_match, trademark_flags, market, text_regions_result = await asyncio.gather(
            asyncio.to_thread(cc_agents.run_agent2_verify_candidates, vision_images, candidates_for_verify),
            asyncio.to_thread(cc_opencv.match_logo, local_path, {"suspected_logos": classify["suspected_logos"]}),
            asyncio.to_thread(cc_opencv.match_character, local_path),
            cc_trademark.resolve_trademark_phrases(classify["OCR_text"], niche),
            asyncio.to_thread(cc_agents.run_agent4_market_suggestion, niche, classify["style"], target_country, platform),
            asyncio.to_thread(cc_opencv.detect_text_regions, local_path),
            return_exceptions=True,
        )

        agent2_result = _safe_or_default(agent2_result, {"verifications": []}, "Agent 2", warnings)
        logo_match = _safe_or_default(logo_match, {"matches": []}, "match_logo", warnings)
        char_match = _safe_or_default(char_match, {"matches": []}, "match_character", warnings)
        trademark_flags = _safe_or_default(trademark_flags, [], "trademark_resolver", warnings)
        market = _safe_or_default(
            market,
            {"top_country_suggestion": "", "top_platform_suggestion": "", "rationale": "",
             "selected_platform_suitable": None, "selected_platform_rationale": ""},
            "Agent 4", warnings
        )
        text_regions_result = _safe_or_default(text_regions_result, {"text_regions": []}, "detect_text_regions", warnings)

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
        )

        # ---- Nhóm C: tổng hợp + định vị (1 LLM call) ----
        evidence_bundle = {
            "suspected_logos": classify["suspected_logos"],
            "suspected_characters": classify["suspected_characters"],
            "suspected_celebrities": classify["suspected_celebrities"],
            "agent2_verifications": agent2_result["verifications"],
            "logo_match": logo_match, "char_match": char_match,
            "trademark_flags": trademark_flags,
        }
        positioning = await asyncio.to_thread(
            cc_agents.run_group_c_synthesis, evidence_bundle,
            pdf_meta.get("text_blocks_with_bbox") if pdf_meta else None,
        )
        # Gắn toạ độ THẬT (Python, không phải LLM đoán) vào positioning_note category=
        # trademark_text nếu OpenCV tìm được vùng chữ — best-effort (vùng LỚN NHẤT phát hiện
        # được), xem docstring opencv_modules.detect_text_regions() về giới hạn của cách này.
        positioning["positioning_notes"] = _inject_text_region_bbox(
            positioning["positioning_notes"], text_regions_result["text_regions"]
        )

        # ---- Agent 3: reasoning + fix suggestion — CHẠY SAU black box (cần biết verdict) ----
        agent3_result = await asyncio.to_thread(cc_agents.run_agent3_reasoning, vision_images, black_box_result, positioning)

        return {
            "niche": niche,
            "style": classify["style"],
            "motifs": classify["motifs"],
            "OCR_text": classify["OCR_text"],
            "suspected_logos": classify["suspected_logos"],
            "suspected_characters": classify["suspected_characters"],
            "suspected_celebrities": classify["suspected_celebrities"],
            "verifications": agent2_result["verifications"],
            "final_verdict": black_box_result["final_verdict"],
            "overall_confidence": black_box_result["overall_confidence"],
            "evidence": black_box_result["evidence"],
            "positioning_notes": positioning["positioning_notes"],
            "text_regions": text_regions_result["text_regions"],
            "reasoning": agent3_result["reasoning"],
            "fix_suggestions": agent3_result["fix_suggestions"],
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


async def process_batch(rows: list[dict], platform: "str | None" = None, target_country: str = "US", max_concurrency: int = 5) -> dict:
    """
    rows: list dict đã chuẩn hoá từ csv_batch.parse_csv_rows() (có _row_index, _input_ref,
    file_path/url tuỳ dòng). Exception ở 1 design KHÔNG được làm hỏng cả batch — catch riêng
    từng cái trong with_limit(), KHÔNG chỉ dựa vào return_exceptions=True ở gather ngoài cùng.
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
