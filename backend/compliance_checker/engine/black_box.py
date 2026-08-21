"""
compliance_checker/engine/black_box.py — Threshold theo category + aggregation. THUẦN PYTHON,
KHÔNG LLM — đây là nơi duy nhất quyết định SAFE/RISKY/BLOCKED, đúng nguyên tắc xuyên suốt
"Python quyết định số/threshold cứng, LLM chỉ giải thích/reasoning" (CLAUDE.md mục 10).

⚠️ Các số trong CATEGORY_THRESHOLDS là số KHỞI ĐIỂM để code được ngay — PHẢI tune lại sau
khi test trên ảnh thật (xem CLAUDE.md mục 9.1, docs.md phần "Điều chưa làm").
"""

import json
import os

CATEGORY_THRESHOLDS = {
    "nsfw":                 {"blocked_min": 30, "risky_min": 15},   # nhạy, safety-first
    "weapons_violence":     {"blocked_min": 40, "risky_min": 20},   # nhạy tương tự
    "character_similarity": {"blocked_min": 88, "risky_min": 65},   # chặt, tránh false positive
    "logo_similarity":      {"blocked_min": 82, "risky_min": 55},
    "celebrity_likeness":   {"blocked_min": 90, "risky_min": 60},   # thêm sau CLAUDE.md gốc — xem
    # score_celebrity_likeness() bên dưới: mục 2.2 yêu cầu đối chiếu tên celeb với
    # celebrity_list.md nhưng bảng threshold gốc không có category riêng cho việc này —
    # bổ sung ở đây, chặt hơn character_similarity 1 chút vì thêm rủi ro chính sách nền
    # tảng/quyền riêng tư quanh người thật (không chỉ IP thuần tuý như nhân vật hư cấu).
    # trademark_text: nhị phân, xử lý riêng trong _score_trademark_text() bên dưới
    # (không dùng blocked_min/risky_min theo thang điểm số như 4 category trên)
}

_DEFAULT_CONFIDENCE_WHEN_ALL_SAFE = 95.0

# File này nằm ở compliance_checker/engine/ — data/ là con của compliance_checker/, cần
# dirname() 2 lần (xem ghi chú chi tiết trong engine/agents.py cùng dòng này — bug thật đã
# xảy ra 1 lần do quên chỗ này khi refactor thư mục).
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Quy đổi định tính (Vision) -> điểm số 0-100 CHỈ dùng cho 2 hàm cross-reference tên
# (score_character_identity/score_celebrity_likeness bên dưới) — KHÔNG áp dụng cho OpenCV
# (OpenCV đã trả confidence float thật, không cần quy đổi).
_NAME_CONFIDENCE_SCORE = {"high": 92, "medium": 72, "low": 45}
# Nếu tên KHÔNG có trong danh sách đối chiếu (character_list.md/celebrity_list.md) -> chặn
# không cho vượt ngưỡng BLOCKED dù Vision tự tin "high" (chỉ 1 LLM đoán chưa được xác nhận
# chéo, theo đúng ghi chú "cần review thủ công" trong 2 file .md nói trên).
_UNLISTED_NAME_SCORE_CAP = 75


def _score_numeric_category(category: str, raw_score: float) -> dict:
    """raw_score: 0-100 (từ Vision/OpenCV) -> {"tag":..., "confidence": raw_score, "detail":...}"""
    th = CATEGORY_THRESHOLDS.get(category, {"blocked_min": 85, "risky_min": 60})
    if raw_score >= th["blocked_min"]:
        tag = "BLOCKED"
    elif raw_score >= th["risky_min"]:
        tag = "RISKY"
    else:
        tag = "SAFE"
    return {"tag": tag, "confidence": round(raw_score, 1), "detail": ""}


def score_character_similarity(match_character_result: dict) -> dict:
    """Input: output thật của opencv_modules.match_character() -> {"matches":[...]}"""
    matches = (match_character_result or {}).get("matches", [])
    if not matches:
        return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": ""}
    top = max(matches, key=lambda m: m.get("confidence", 0))
    result = _score_numeric_category("character_similarity", float(top.get("confidence", 0)))
    if result["tag"] != "SAFE":
        result["detail"] = f"Giống nhân vật '{top.get('character_name')}' ({result['confidence']}%)"
    return result


def score_logo_similarity(match_logo_result: dict) -> dict:
    """Input: output thật của opencv_modules.match_logo() -> {"matches":[...]}"""
    matches = (match_logo_result or {}).get("matches", [])
    if not matches:
        return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": ""}
    top = max(matches, key=lambda m: m.get("confidence", 0))
    result = _score_numeric_category("logo_similarity", float(top.get("confidence", 0)))
    if result["tag"] != "SAFE":
        result["detail"] = f"Giống logo '{top.get('brand_name')}' ({result['confidence']}%)"
    return result


def score_trademark_text(trademark_flags: list) -> dict:
    """
    Nhị phân theo CLAUDE.md mục 2.5: exact_match_only -> BLOCKED, partial_match -> RISKY.
    Input: list các dict flag từ trademark_resolver.resolve_trademark_phrases().

    ⚠️ FIX (phát hiện qua test thật trên PDF bảng điểm tiếng Việt — mọi cụm 2-6 từ viết hoa
    không số đều bị looks_like_slogan() nghi ngờ, RẤT phổ biến trong text thường, không riêng
    slogan): "needs_live_check"/"live_failed_fallback_static" nghĩa là "CHƯA từng verify được"
    (do thiếu USPTO_API_KEY hoặc lỗi mạng — confidence luôn = 0.0, xem trademark_resolver.py),
    KHÔNG PHẢI bằng chứng fuzzy match thật. Coi 2 source này là RISKY (như code gốc) khiến
    HẦU HẾT thiết kế có chữ bị gắn RISKY sai — vi phạm chính nguyên tắc CLAUDE.md mục 2.5
    "Fuzzy match LUÔN map RISKY" (fuzzy match THẬT, tức có kết quả trả về, không phải "chưa
    hỏi được ai"). Chỉ "live_fuzzy" (đã thật sự query, có kết quả không khớp tuyệt đối) mới
    tính là partial_match -> RISKY. "needs_live_check" chưa verify -> giữ SAFE ở tầng verdict,
    nhưng KHÔNG mất dữ liệu: vẫn nằm trong evidence_bundle thô gửi Nhóm C để ghi chú "cần
    review thủ công" trong narrative (xem orchestrator.py).
    """
    if not trademark_flags:
        return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": ""}

    exact_hits = [f for f in trademark_flags if f.get("source") in ("static", "live_exact") and f.get("confidence", 0) >= 80]
    if exact_hits:
        top = max(exact_hits, key=lambda f: f.get("confidence", 0))
        return {
            "tag": "BLOCKED",
            "confidence": float(top.get("confidence", 90)),
            "detail": f"Trùng khớp trademark đã đăng ký: \"{top.get('phrase')}\"" + (f" (chủ sở hữu: {top.get('owner')})" if top.get("owner") else ""),
        }

    fuzzy_hits = [f for f in trademark_flags if f.get("source") == "live_fuzzy" and f.get("confidence", 0) > 0]
    if fuzzy_hits:
        top = max(fuzzy_hits, key=lambda f: f.get("confidence", 0))
        return {
            "tag": "RISKY",
            "confidence": float(top.get("confidence", 50)) or 50.0,
            "detail": f"Fuzzy match với trademark (chưa tuyệt đối trùng khớp): \"{top.get('phrase')}\"",
        }

    # Chỉ còn "needs_live_check"/"live_failed_fallback_static" (chưa từng verify được, thường
    # vì thiếu USPTO_API_KEY) -> KHÔNG đủ căn cứ tự tin RISKY, để SAFE ở verdict nhưng vẫn có
    # trong evidence_bundle thô cho Nhóm C ghi chú khuyến nghị review thủ công.
    return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": ""}


def _load_reference_names(filename: str) -> set:
    """Đọc character_list.md / celebrity_list.md, trích tên trong các dòng nội dung (bỏ heading
    '#', bullet '*', dòng cảnh báo '⚠️') -> set tên lowercase để so khớp case-insensitive.
    Ghi chú sử dụng ở cuối 2 file .md này mô tả đúng cơ chế đối chiếu được cài ở đây. Không
    raise nếu file thiếu/lỗi — trả set rỗng (đúng nguyên tắc fallback-safe chung của module)."""
    path = os.path.join(_DATA_DIR, filename)
    names = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("*") or line.startswith("⚠️"):
                    continue
                for part in line.split(","):
                    name = part.split("(")[0].strip().rstrip(".")  # "Anna (Frozen)" -> "Anna"
                    if name:
                        names.add(name.lower())
    except Exception:
        pass
    return names


def _score_name_cross_reference(entries: list, ref_names: set, category: str) -> dict:
    """Dùng chung cho score_character_identity/score_celebrity_likeness: Agent 2 (Vision) tự
    do nêu tên nghi ngờ (không giới hạn danh sách, đúng CLAUDE.md mục 2.2) -> Python đối
    chiếu case-insensitive với danh sách tham chiếu. Đây là tín hiệu DUY NHẤT ảnh hưởng verdict
    cho category character_similarity/celebrity_likeness cho tới khi opencv_modules.match_character
    (hiện là placeholder, xem opencv_modules.py) có thuật toán thật."""
    if not entries:
        return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": ""}

    best = None
    for item in entries or []:
        name = str((item or {}).get("name", "")).strip()
        if not name:
            continue
        conf_label = (item or {}).get("confidence", "low")
        listed = name.lower() in ref_names
        raw = _NAME_CONFIDENCE_SCORE.get(conf_label, 45)
        if not listed:
            raw = min(raw, _UNLISTED_NAME_SCORE_CAP)
        if best is None or raw > best["raw"]:
            best = {"raw": raw, "name": name, "listed": listed}

    if best is None:
        return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": ""}

    result = _score_numeric_category(category, best["raw"])
    if result["tag"] != "SAFE":
        listed_note = "có trong danh sách đối chiếu" if best["listed"] else "CHƯA có trong danh sách đối chiếu, cần review thủ công"
        result["detail"] = f"Nghi ngờ '{best['name']}' ({listed_note})"
    return result


_MANIFEST_JSON_CACHE = None  # module-level lazy cache


def _load_manifest_brand_names() -> set:
    """Đọc logo_refs/manifest.json (KHÁC .md nên tách hàm riêng, không dùng _load_reference_names)
    -> set brand_name lowercase để so khớp case-insensitive. Không raise nếu file thiếu/lỗi."""
    global _MANIFEST_JSON_CACHE
    if _MANIFEST_JSON_CACHE is None:
        path = os.path.join(_DATA_DIR, "logo_refs", "manifest.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _MANIFEST_JSON_CACHE = {b["brand_name"].lower() for b in data.get("brands", []) if b.get("brand_name")}
        except Exception:
            _MANIFEST_JSON_CACHE = set()
    return _MANIFEST_JSON_CACHE


def _apply_verification_filter(entries: list, verifications: "list | None", category: str, name_key: str) -> list:
    """(2026-08-21) Lọc entries (suspected_logos/characters/celebrities từ Agent 1) theo kết quả
    Agent 2 verify — Agent 2 giờ KHÔNG tự detect nữa, chỉ trả lời CÓ/KHÔNG cho từng candidate
    Agent 1 đã nêu (xem agents.py::run_agent2_verify_candidates). Loại bỏ mục Agent 2 xác nhận
    present=False (Agent 1 đoán nhầm, không thật sự có trong ảnh) TRƯỚC khi đối chiếu danh sách
    tham chiếu — giảm false positive từ việc Agent 1 cố tình đoán rộng tay (top 5, kể cả không
    chắc). Mục KHÔNG có verification tương ứng (Agent 2 lỗi/không gọi, hoặc tên không khớp do
    model diễn đạt khác) -> GIỮ NGUYÊN, fail-open, không mất evidence vì lỗi hạ tầng/parse
    (CLAUDE.md mục 10)."""
    if not verifications:
        return entries
    not_present = {
        v["name"].strip().lower()
        for v in verifications
        if v.get("category") == category and v.get("present") is False and v.get("name")
    }
    if not not_present:
        return entries
    return [e for e in entries if str(e.get(name_key, "")).strip().lower() not in not_present]


def score_logo_identity(suspected_logos: list) -> dict:
    """
    Cross-reference suspected_logos (Agent 1, tên brand Vision tự nêu) với logo_refs/manifest.json
    — CÙNG khoảng trống như character/celebrity: opencv_modules.match_logo() hiện là placeholder
    luôn trả rỗng, nên nếu không có hàm này, verdict logo_similarity SAI SÓT hoàn toàn bỏ qua
    những gì Agent 1 đã tự tin nhận diện được (vd nhiều logo tài trợ "high" confidence nhưng
    verdict vẫn ra SAFE — phát hiện thật qua test ảnh banner Gen.G, 3 logo "high" vẫn SAFE).
    Field input là {"brand_name": str, "confidence": "low"|"medium"|"high"} (List[SuspectedLogo]).
    """
    entries = [{"name": item.get("brand_name", ""), "confidence": item.get("confidence", "low")} for item in (suspected_logos or [])]
    return _score_name_cross_reference(entries, _load_manifest_brand_names(), "logo_similarity")


def score_character_identity(suspected_characters: list) -> dict:
    """Cross-reference suspected_characters (Agent 2) với character_list.md."""
    return _score_name_cross_reference(suspected_characters, _load_reference_names("character_list.md"), "character_similarity")


def score_celebrity_likeness(suspected_celebrities: list) -> dict:
    """Cross-reference suspected_celebrities (Agent 1) với celebrity_list.md. KHÔNG dùng
    face-recognition/biometric — chỉ đối chiếu TÊN (CLAUDE.md mục 2.2)."""
    return _score_name_cross_reference(suspected_celebrities, _load_reference_names("celebrity_list.md"), "celebrity_likeness")


def score_celebrity_likeness_from_faces(face_identifications: "list | None") -> dict:
    """
    (2026-08-21) Nguồn THỨ 2, ĐỘC LẬP cho celebrity_likeness — dùng ảnh mặt THẬT đã cắt riêng
    (BlazeFace detect vị trí, engine/opencv_modules.py::detect_and_crop_faces) rồi để Agent 2
    (Claude Vision) tự nhận diện TRỰC TIẾP trên từng ảnh crop — xem agents.py::
    run_agent2_verify_candidates(). KHÁC score_celebrity_likeness() ở trên (dùng
    suspected_celebrities từ Agent 1 đoán trên CẢ ảnh thiết kế + có cross-reference
    celebrity_list.md + cap nếu tên không có trong danh sách):

    ⚠️ Hàm này CỐ Ý KHÔNG đối chiếu celebrity_list.md, KHÔNG áp _UNLISTED_NAME_SCORE_CAP —
    theo đúng quyết định của nhóm "không so khớp database nữa, tin vào Claude" (input đã là
    ảnh mặt phóng to/cắt riêng gửi thẳng cho Agent 2, đáng tin hơn hẳn so với đoán trên cả
    ảnh thiết kế — nhưng đổi lại KHÔNG có lớp kiểm chứng độc lập nào nữa, rủi ro false
    positive nếu Agent 2 tự tin nhầm; xem docs.md phần rủi ro đã ghi nhận).
    """
    if not face_identifications:
        return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": ""}
    named = [f for f in face_identifications if (f or {}).get("suspected_name")]
    if not named:
        return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": ""}
    best = max(named, key=lambda f: _NAME_CONFIDENCE_SCORE.get(f.get("confidence") or "low", 45))
    raw = _NAME_CONFIDENCE_SCORE.get(best.get("confidence") or "low", 45)
    result = _score_numeric_category("celebrity_likeness", raw)
    if result["tag"] != "SAFE":
        result["detail"] = f"Agent 2 tự nhận diện trên ảnh mặt cắt riêng: nghi ngờ '{best.get('suspected_name')}' (không đối chiếu database, tin trực tiếp Claude)"
    return result


def _combine_category_results(a: dict, b: dict) -> dict:
    """Gộp 2 kết quả cùng 1 category (vd OpenCV match_character + name cross-reference) —
    lấy cái NẶNG hơn (severity cao hơn; nếu hoà thì lấy confidence cao hơn), giữ cả 2 detail
    nếu cả 2 đều không SAFE để không mất bằng chứng."""
    severity_order = {"SAFE": 0, "RISKY": 1, "BLOCKED": 2}
    if severity_order[a["tag"]] == severity_order[b["tag"]]:
        winner, loser = (a, b) if a["confidence"] >= b["confidence"] else (b, a)
    else:
        winner, loser = (a, b) if severity_order[a["tag"]] > severity_order[b["tag"]] else (b, a)
    if winner["tag"] == "SAFE":
        return winner
    detail = winner["detail"]
    if loser["tag"] != "SAFE" and loser["detail"] and loser["detail"] != detail:
        detail = f"{detail}; {loser['detail']}"
    return {"tag": winner["tag"], "confidence": winner["confidence"], "detail": detail}


_BLACKLIST_JSON_CACHE = None  # module-level lazy cache — đọc file 1 lần cho cả process


def _load_blacklist_categories() -> dict:
    global _BLACKLIST_JSON_CACHE
    if _BLACKLIST_JSON_CACHE is None:
        path = os.path.join(_DATA_DIR, "blacklist_hardcoded.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                _BLACKLIST_JSON_CACHE = json.load(f).get("categories", {})
        except Exception:
            _BLACKLIST_JSON_CACHE = {}
    return _BLACKLIST_JSON_CACHE


# blacklist_hardcoded.json có 4 nhóm (nsfw/weapons_violence/drugs/hate_discrimination) nhưng
# CATEGORY_THRESHOLDS chỉ định nghĩa 2 ngưỡng nhạy cảm (nsfw/weapons_violence) — "drugs" và
# "hate_discrimination" dùng chung ngưỡng weapons_violence (cùng tinh thần "safety-first,
# false negative tệ hơn false positive", chưa đủ lý do tách riêng thêm 1 ngưỡng nữa).
_BLACKLIST_CATEGORY_TO_THRESHOLD_KEY = {
    "nsfw": "nsfw", "weapons_violence": "weapons_violence",
    "drugs": "weapons_violence", "hate_discrimination": "weapons_violence",
}


def _scan_text_for_blacklist(ocr_text: str) -> "tuple[str, str] | None":
    """Quét OCR_text (KHÔNG phải ảnh — Vision đã tự lo phần hình ảnh qua motifs) tìm keyword
    cấm trong blacklist_hardcoded.json — lớp lưới an toàn bổ sung cho case text rõ ràng mà
    Agent 1 lỡ không gắn motif tương ứng. Trả (threshold_key, matched_keyword) hoặc None."""
    if not ocr_text or not ocr_text.strip():
        return None
    text_lower = ocr_text.lower()
    for cat, kw_groups in _load_blacklist_categories().items():
        threshold_key = _BLACKLIST_CATEGORY_TO_THRESHOLD_KEY.get(cat, "weapons_violence")
        for lang_key in ("keywords_en", "keywords_vi"):
            for kw in kw_groups.get(lang_key, []) or []:
                if kw and kw.lower() in text_lower:
                    return threshold_key, kw
    return None


def score_content_safety(niche: str, motifs: list, ocr_text: str = "") -> dict:
    """
    NSFW/weapons_violence — đánh giá dựa trên 2 nguồn ĐỘC LẬP, lấy nguồn NẶNG hơn:
    (1) motifs Agent 1 trả về (đối chiếu global_dangerous_motifs trong niche_taxonomy.json —
        tín hiệu từ HÌNH ẢNH, do Vision tự phân loại);
    (2) OCR_text đối chiếu keyword tĩnh trong blacklist_hardcoded.json (tín hiệu từ CHỮ —
        lưới an toàn bổ sung, bắt case rõ ràng mà Vision lỡ không gắn motif tương ứng).
    Category "bỏ sót nguy hiểm hơn false positive" nên threshold thấp (CATEGORY_THRESHOLDS).
    Vì cả 2 nguồn đều KHÔNG tự chấm điểm 0-100, quy đổi tất định: MỌI hit -> raw_score=100
    (chắc chắn), không có khái niệm "một phần" cho nhóm nội dung cấm.

    Trả kèm "_category_key" = "nsfw" hoặc "weapons_violence" — run_black_box() dùng để đặt
    ĐÚNG tên category trong evidence (thay vì gộp chung nhãn mơ hồ "content_safety").
    """
    dangerous_motifs = {
        "firearms_weapons", "knives_blades_as_main_subject", "drug_paraphernalia",
        "hate_symbols_extremist_iconography", "explicit_nudity_sexual_content",
        "graphic_gore_violence", "self_harm_suicide_imagery", "terrorist_extremist_slogans",
    }
    hit_motifs = [m for m in (motifs or []) if m in dangerous_motifs]
    text_hit = _scan_text_for_blacklist(ocr_text)

    if not hit_motifs and not text_hit:
        return {"tag": "SAFE", "confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "detail": "", "_category_key": "nsfw"}

    is_nsfw_from_motif = any(m == "explicit_nudity_sexual_content" for m in hit_motifs)
    is_nsfw_from_text = text_hit is not None and text_hit[0] == "nsfw"
    category = "nsfw" if (is_nsfw_from_motif or is_nsfw_from_text) else "weapons_violence"

    result = _score_numeric_category(category, 100.0)
    detail_parts = []
    if hit_motifs:
        detail_parts.append(f"Motif nhạy cảm phát hiện: {', '.join(hit_motifs)}")
    if text_hit:
        detail_parts.append(f"Từ khoá nhạy cảm trong text: \"{text_hit[1]}\"")
    result["detail"] = " | ".join(detail_parts)
    result["_category_key"] = category
    return result


def aggregate_final_verdict(category_results: dict) -> dict:
    """
    category_results: {"character_similarity": {...}, "logo_similarity": {...},
                        "trademark_text": {...}, "nsfw" | "weapons_violence": {...},
                        "celebrity_likeness": {...}}  # 2 category cuối chỉ có nếu có evidence
    """
    severity_order = {"SAFE": 0, "RISKY": 1, "BLOCKED": 2}
    if not category_results:
        return {"final_verdict": "SAFE", "overall_confidence": _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE, "evidence": {}}

    worst_category, worst_result = max(category_results.items(), key=lambda kv: severity_order[kv[1]["tag"]])
    final_tag = worst_result["tag"]

    triggering_evidence = {k: v for k, v in category_results.items() if v["tag"] != "SAFE"}

    if final_tag == "SAFE":
        overall_confidence = _DEFAULT_CONFIDENCE_WHEN_ALL_SAFE
    else:
        overall_confidence = worst_result["confidence"]

    return {
        "final_verdict": final_tag,
        "overall_confidence": overall_confidence,
        "evidence": triggering_evidence,  # giữ TẤT CẢ category không SAFE, không chỉ 1
    }


def run_black_box(
    match_character_result: dict,
    match_logo_result: dict,
    trademark_flags: list,
    niche: str,
    motifs: list,
    suspected_characters: "list | None" = None,
    suspected_celebrities: "list | None" = None,
    ocr_text: str = "",
    suspected_logos: "list | None" = None,
    agent2_verifications: "list | None" = None,
    face_identifications: "list | None" = None,
) -> dict:
    """
    Điểm vào duy nhất orchestrator.py cần gọi — gói gọn toàn bộ black box thành 1 hàm.

    suspected_characters/suspected_celebrities/suspected_logos (output Agent 1, optional để
    không phá API cũ) được đối chiếu tên với character_list.md/celebrity_list.md/
    logo_refs/manifest.json và GỘP vào category tương ứng (character_similarity + logo_similarity
    gộp với kết quả OpenCV, celebrity_likeness là category riêng) — xem score_character_identity/
    score_celebrity_likeness/score_logo_identity ở trên. Đây là fix cho khoảng trống: nếu không
    truyền các tham số này, Agent 1 detect được logo/nhân vật/celeb nhưng KHÔNG ảnh hưởng verdict
    (chỉ nằm trong evidence_bundle cho Nhóm C viết narrative) — verdict lúc đó chỉ phụ thuộc
    100% vào opencv_modules (hiện là placeholder luôn trả rỗng). Phát hiện thật qua test: ảnh
    banner Gen.G có 3 logo tài trợ "high" confidence vẫn ra SAFE trước khi vá lỗ hổng này.

    agent2_verifications: (2026-08-21, MỚI) output run_agent2_verify_candidates() — lọc BỚT
    3 list trên TRƯỚC khi cross-reference, loại mục Agent 2 xác nhận "không thật sự có trong
    ảnh" (Agent 1 đoán nhầm khi liệt kê top 5 rộng tay) — xem _apply_verification_filter().
    None/rỗng -> không lọc gì (fail-open, giữ hành vi cũ nếu chưa truyền tham số này).

    ocr_text: dùng thêm cho score_content_safety() quét blacklist_hardcoded.json (lớp lưới an
    toàn text bổ sung cho motif hình ảnh của Agent 1).

    face_identifications: (2026-08-21, MỚI) output Agent 2 nhận diện trên ảnh mặt crop
    (BlazeFace) — nguồn celebrity_likeness THỨ 2, ĐỘC LẬP với suspected_celebrities, KHÔNG
    đối chiếu database (xem score_celebrity_likeness_from_faces()). Gộp với nguồn cũ qua
    _combine_category_results (lấy tín hiệu nặng hơn), None/rỗng -> không đổi hành vi cũ.
    """
    suspected_characters = _apply_verification_filter(suspected_characters or [], agent2_verifications, "character", "name")
    suspected_celebrities = _apply_verification_filter(suspected_celebrities or [], agent2_verifications, "celebrity", "name")
    suspected_logos = _apply_verification_filter(suspected_logos or [], agent2_verifications, "logo", "brand_name")

    character_score = score_character_similarity(match_character_result)
    if suspected_characters:
        character_score = _combine_category_results(character_score, score_character_identity(suspected_characters))

    logo_score = score_logo_similarity(match_logo_result)
    if suspected_logos:
        logo_score = _combine_category_results(logo_score, score_logo_identity(suspected_logos))

    content_safety_result = score_content_safety(niche, motifs, ocr_text)
    # content_safety_result gắn "_category_key" (nsfw/weapons_violence) để dùng ĐÚNG tên
    # category thay vì nhãn gộp mơ hồ "content_safety" — pop ra trước khi đưa vào evidence,
    # KHÔNG để field nội bộ này lộ ra ngoài response (route batch-csv trả dict thô, không đi
    # qua Pydantic response_model để tự lọc field lạ).
    content_safety_key = content_safety_result.pop("_category_key", "weapons_violence")

    category_results = {
        "character_similarity": character_score,
        "logo_similarity": logo_score,
        "trademark_text": score_trademark_text(trademark_flags),
        content_safety_key: content_safety_result,
    }
    celebrity_score = score_celebrity_likeness(suspected_celebrities) if suspected_celebrities else None
    face_score = score_celebrity_likeness_from_faces(face_identifications) if face_identifications else None
    if celebrity_score and face_score:
        category_results["celebrity_likeness"] = _combine_category_results(celebrity_score, face_score)
    elif celebrity_score:
        category_results["celebrity_likeness"] = celebrity_score
    elif face_score:
        category_results["celebrity_likeness"] = face_score

    return aggregate_final_verdict(category_results)
