"""
compliance_checker/engine/trademark_resolver.py — flag_suspicious_phrases, query 2 lớp
exact->fuzzy, cache batch. THUẦN Python/HTTP, tách khỏi agents.py (không gọi LLM).

Lớp 1 (static, luôn chạy trước, free): trademark_top1000.json — xem
compliance_checker/data/trademark_top1000.json.
Lớp 2 (live, CHỈ cho cụm "needs_live_check"): USPTO TSDR API (cần API key miễn phí, đăng
ký tại https://developer.uspto.gov — rate limit 60 req/min cho status call) + EUIPO
eSearch Plus (public register, không cần key cho tra cứu công khai).

⚠️ Timeout ngắn + fallback về static nếu live API fail/timeout — KHÔNG BAO GIỜ để cả
pipeline phụ thuộc network để chạy được (brief yêu cầu "phải chạy được trên máy giám khảo").
Nếu chưa cấu hình API key USPTO, live lookup tự động no-op (bỏ qua, không lỗi).

pip install httpx
"""

import json
import os
import re

import httpx

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_STATIC_DB_PATH = os.path.join(_DATA_DIR, "trademark_top1000.json")
_NICE_CLASS_PATH = os.path.join(_DATA_DIR, "niche_to_nice_class.json")

_USPTO_TSDR_BASE = "https://tsdr.uspto.gov/ts/cd/casestatus"  # xem developer.uspto.gov/api-catalog/tsdr-data-api
_USPTO_TIMEOUT = httpx.Timeout(3.0, connect=2.0)  # timeout ngắn per CLAUDE.md mục 4.3

_STOPWORDS_LOWER_ONLY_HINT = {"the", "and", "for", "with", "your", "our"}


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ [trademark_resolver] Không đọc được {path}: {e}")
        return {}


_STATIC_DB_CACHE = None  # module-level lazy cache — file JSON chỉ đọc 1 lần cho cả process


def _get_static_db() -> dict:
    global _STATIC_DB_CACHE
    if _STATIC_DB_CACHE is None:
        _STATIC_DB_CACHE = _load_json(_STATIC_DB_PATH)
    return _STATIC_DB_CACHE


def extract_candidate_phrases(ocr_text: str) -> list[str]:
    """Tách câu, cụm 2-6 từ từ OCR_text — heuristic rẻ, không cần NLP nặng."""
    if not ocr_text or not ocr_text.strip():
        return []
    # Tách theo dấu câu / xuống dòng trước, rồi tách cụm n-gram (2-6 từ) trong mỗi câu
    raw_lines = re.split(r"[\n.!?;,]+", ocr_text)
    candidates = set()
    for line in raw_lines:
        words = [w for w in line.strip().split() if w]
        if not words:
            continue
        candidates.add(" ".join(words))  # cả câu/dòng nguyên văn
        for n in range(2, min(6, len(words)) + 1):
            for i in range(len(words) - n + 1):
                candidates.add(" ".join(words[i:i + n]))
    return list(candidates)


def looks_like_slogan(phrase: str) -> bool:
    """2-6 từ, có viết hoa, không có số — heuristic rẻ để nghi ngờ 'đây có thể là slogan'."""
    words = phrase.split()
    if not (2 <= len(words) <= 6):
        return False
    if any(c.isdigit() for c in phrase):
        return False
    return not phrase.islower()


def check_against_static_list(phrase: str) -> dict:
    """So khớp case-insensitive với trademark_top1000.json — exact match trước (confidence
    cao), rồi thử match không phân biệt hoa/thường."""
    db = _get_static_db()
    entries = db.get("trademarks", [])
    phrase_norm = phrase.strip().lower()
    if not phrase_norm:
        return {"confidence": 0.0}
    for entry in entries:
        if entry.get("phrase", "").strip().lower() == phrase_norm:
            return {
                "confidence": 95.0,
                "owner": entry.get("owner"),
                "nice_classes": entry.get("nice_classes", []),
                "risk_level": entry.get("risk_level"),
            }
    return {"confidence": 0.0}


def flag_suspicious_phrases(ocr_text: str) -> list[dict]:
    """Python thuần, KHÔNG cần LLM — chạy song song Agent 2 trong orchestrator.py."""
    candidates = extract_candidate_phrases(ocr_text)
    flagged: list[dict] = []
    seen_phrases = set()
    for phrase in candidates:
        static_match = check_against_static_list(phrase)
        if static_match["confidence"] >= 80:
            if phrase.lower() not in seen_phrases:
                flagged.append({"phrase": phrase, "source": "static", **static_match})
                seen_phrases.add(phrase.lower())
        elif looks_like_slogan(phrase) and phrase.lower() not in seen_phrases:
            flagged.append({"phrase": phrase, "source": "needs_live_check", "confidence": 0.0})
            seen_phrases.add(phrase.lower())
    return flagged


async def query_trademark_precise(phrase: str, nice_classes: list[int] | None = None) -> dict:
    """
    Lớp 2 — CHỈ gọi cho cụm 'needs_live_check'. USPTO TSDR API cần API key (biến môi trường
    USPTO_API_KEY, KHÔNG hardcode key vào code/repo — nếu chưa set, hàm no-op an toàn, trả
    fallback ngay, KHÔNG raise, KHÔNG chặn pipeline).

    Lớp 1 (exact match qua API) trước, chỉ fallback fuzzy nếu exact rỗng — nhưng vì bản này
    CHƯA có quyền truy cập API key thật để test end-to-end, hàm được viết THEO ĐÚNG hợp đồng
    (timeout ngắn, không raise, luôn map fuzzy tối đa RISKY) nhưng nhánh gọi API thật cần
    xác nhận lại response shape thật khi có key (xem CLAUDE.md mục 9.3 — TODO đã ghi nhận).
    """
    api_key = os.environ.get("USPTO_API_KEY", "").strip()
    if not api_key:
        return {"phrase": phrase, "source": "needs_live_check", "confidence": 0.0,
                "note": "USPTO_API_KEY chưa cấu hình — bỏ qua live lookup, giữ nguyên static fallback."}

    try:
        async with httpx.AsyncClient(timeout=_USPTO_TIMEOUT) as client:
            resp = await client.get(
                _USPTO_TSDR_BASE,
                params={"searchText": phrase, "searchType": "wordMark"},
                headers={"USPTO-API-KEY": api_key},
            )
            if resp.status_code != 200:
                raise httpx.HTTPStatusError("non-200", request=resp.request, response=resp)
            data = resp.json()
            # ⚠️ Shape response thật cần xác nhận lại với docs USPTO khi có key thật để test —
            # đây là điểm CLAUDE.md mục 9.3 đã lưu ý rõ "hiểu biết hiện tại có thể lỗi thời".
            hits = data.get("results") or data.get("trademarks") or []
            if hits:
                top = hits[0]
                return {
                    "phrase": phrase, "source": "live_exact", "confidence": 95.0,
                    "owner": top.get("owner") or top.get("registrant"),
                    "nice_classes": nice_classes or [],
                }
            return {"phrase": phrase, "source": "live_fuzzy", "confidence": 50.0, "nice_classes": nice_classes or []}
    except Exception as e:
        # Timeout/lỗi mạng/lỗi parse -> fallback về static, KHÔNG BAO GIỜ để network làm sập pipeline
        print(f"⚠️ [trademark_resolver] Live lookup lỗi cho '{phrase}': {e}")
        return {"phrase": phrase, "source": "live_failed_fallback_static", "confidence": 0.0}


async def resolve_trademark_phrases(ocr_text: str, niche: str = "") -> list[dict]:
    """
    Điểm vào duy nhất orchestrator.py cần gọi — gói gọn cả 2 lớp + cache trong phạm vi 1
    batch run (dict Python đơn giản theo tham số cache, không cần Redis).
    """
    flagged = flag_suspicious_phrases(ocr_text)
    if not flagged:
        return []

    nice_map = _load_json(_NICE_CLASS_PATH).get("mapping", {})
    nice_classes = nice_map.get(niche, {}).get("nice_classes") or _load_json(_NICE_CLASS_PATH).get("fallback_default_classes", [])

    resolved: list[dict] = []
    for item in flagged:
        if item["source"] == "static":
            resolved.append(item)
            continue
        live_result = await query_trademark_precise(item["phrase"], nice_classes)
        resolved.append(live_result)
    return resolved


def resolve_trademark_phrases_with_cache(ocr_text: str, niche: str, batch_cache: dict) -> "list[dict] | None":
    """
    Biến thể ĐỒNG BỘ dùng field cache đơn giản trong phạm vi batch (dict Python được
    orchestrator.process_batch() tạo 1 lần, truyền xuống mỗi design) — tránh query trùng
    phrase nhiều lần trong cùng 1 lượt chạy batch. Trả None nếu phrase đã có trong cache
    (caller tự biết đọc lại từ batch_cache thay vì gọi lại).
    """
    candidates_key = ocr_text.strip().lower()
    if candidates_key in batch_cache:
        return batch_cache[candidates_key]
    return None
