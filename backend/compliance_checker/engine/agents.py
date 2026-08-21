"""
compliance_checker/engine/agents.py — CHỈ định nghĩa Agent 1-4 + Nhóm C: prompt + gọi LLM.
KHÔNG chứa asyncio.gather ghép nối — xem orchestrator.py.

Tự chứa (self-contained) hoàn toàn về phần gọi LLM — KHÔNG import từ marketing_copy/agents.py,
đúng nguyên tắc "triển khai tách biệt" (CLAUDE.md mục 0). Chỉ tái dùng config.py (client/API
key) và knowledge_loader.py (load_trend_context, xem cách dùng ở Agent 4 bên dưới).

Model đang dùng: Claude Haiku 4.5 qua endpoint tương thích OpenAI của Anthropic — CÓ vision
gốc. Content-block ảnh dùng đúng format chuẩn OpenAI ({"type":"image_url","image_url":{"url":
"data:image/png;base64,..."}}) — ⚠️ CẦN TEST THẬT với API key thật trước demo, vì đây là lớp
tương thích (compat layer), không phải Anthropic Messages API gốc (xem docs.md phần rủi ro).
"""

import base64
import json
import os
import re
import time

from openai import OpenAI

from config import get_settings
from knowledge_loader import load_trend_context

try:
    from json_repair import repair_json
except ImportError:
    def repair_json(s: str) -> str:  # fallback tối thiểu nếu chưa cài json_repair
        return s

# File này nằm ở compliance_checker/engine/ (2 cấp dưới compliance_checker/) — data/ là
# thư mục CON của compliance_checker/, không phải của engine/, nên cần dirname() 2 LẦN.
# ⚠️ Bug thật đã xảy ra: refactor thư mục trước đó chỉ dùng dirname() 1 lần (đúng lúc file
# còn nằm phẳng ở compliance_checker/), quên cập nhật khi dời vào engine/ -> mọi file data/
# (niche_taxonomy.json, character_list.md, policies/...) load rỗng TRONG IM LẶNG (có try/except
# fallback nên không crash, nhưng mất hết context tiêm vào prompt) — phát hiện + vá lại đây.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


# =====================================================================
# LLM CALL PRIMITIVE — tự chứa, hỗ trợ vision (image_base64 optional)
# =====================================================================

def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "429" in msg or "rate_limit" in msg or "rate limit" in msg


def _sniff_image_mime(image_base64: str) -> str:
    """
    Đoán MIME type THẬT từ magic bytes đầu ảnh (decode 1 đoạn base64 nhỏ, không cần giải mã
    toàn bộ). ⚠️ FIX bug thật phát hiện qua test: trước đây _build_messages() HARDCODE
    "image/png" cho mọi base64 thuần không có prefix — "tình cờ đúng" bấy lâu vì mọi luồng
    khác (upload/link) đều đi qua DesignFileLoader.to_base64() (luôn re-encode về PNG trước).
    Nhưng ảnh dán trực tiếp từ Excel (csv_batch.parse_xlsx_rows, ảnh nhúng KHÔNG qua
    DesignFileLoader) giữ nguyên bytes gốc — nếu là JPEG mà khai "image/png", Anthropic API trả
    lỗi 400 "the image appears to be a image/jpeg image" (đã thấy lỗi này thật khi test).
    Đây cũng là rủi ro tiềm ẩn cho bất kỳ ai gửi thẳng image_base64 JPEG không kèm prefix qua
    /api/compliance/check (docs.md nói base64 thuần được chấp nhận, không giới hạn chỉ PNG).
    """
    try:
        raw_prefix = base64.b64decode(image_base64[:32])
    except Exception:
        return "image/png"
    if raw_prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw_prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw_prefix[:4] == b"RIFF" and raw_prefix[8:12] == b"WEBP":
        return "image/webp"
    if raw_prefix.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if raw_prefix.startswith(b"BM"):
        return "image/bmp"
    return "image/png"  # không nhận diện được -> giữ hành vi mặc định cũ, an toàn nhất


def _to_data_uri(image_base64: str) -> str:
    """1 ảnh base64 (thuần hoặc đã có prefix data:image/...) -> data URI hoàn chỉnh, tự nhận
    diện MIME thật thay vì hardcode (xem _sniff_image_mime)."""
    if image_base64.startswith("data:image"):
        return image_base64
    return f"data:{_sniff_image_mime(image_base64)};base64,{image_base64}"


def _build_messages(system_prompt: str, user_prompt: str, image_base64: "str | list[str] | None", labels: "list[str] | None" = None) -> list:
    """
    image_base64: 1 ảnh (str), NHIỀU ảnh (list[str] — vd mọi trang của 1 PDF nhiều trang, xem
    pdf_processor.py), hoặc None (text-only). Nhiều ảnh được gửi CÙNG 1 message (Anthropic hỗ
    trợ nhiều image content-block/message) — vẫn chỉ 1 lần gọi API, không nhân số lần gọi theo
    số trang. Mỗi ảnh được đánh dấu bằng 1 text block ngay trước nó để model biết thứ tự/vai
    trò khi mô tả vị trí phát hiện (Nhóm C dùng lại thông tin này).

    labels: (2026-08-21, optional) nhãn TỰ ĐỊNH NGHĨA cho từng ảnh theo đúng thứ tự trong
    image_base64, dùng khi cần phân biệt NHIỀU LOẠI ảnh khác nhau trong CÙNG 1 message (vd
    Agent 2 gửi ảnh thiết kế gốc + nhiều ảnh mặt đã crop — xem run_agent2_verify_candidates).
    Không truyền -> giữ NGUYÊN hành vi cũ: nhiều ảnh không nhãn -> tự đánh "Trang N/M", 1 ảnh
    -> không nhãn gì (backward compatible 100%).
    """
    images = image_base64 if isinstance(image_base64, list) else ([image_base64] if image_base64 else [])
    images = [img for img in images if img]  # loại None/rỗng lẫn vào list
    if not images:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    content = [{"type": "text", "text": user_prompt}]
    multi = len(images) > 1
    for i, img in enumerate(images):
        if labels and i < len(labels) and labels[i]:
            content.append({"type": "text", "text": f"--- {labels[i]} ---"})
        elif multi:
            content.append({"type": "text", "text": f"--- Trang {i + 1}/{len(images)} ---"})
        content.append({"type": "image_url", "image_url": {"url": _to_data_uri(img)}})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def _call_llm_json(
    system_prompt: str,
    user_prompt: str,
    image_base64: "str | list[str] | None" = None,
    temperature: float = 0.3,
    max_retries: int = 2,
    labels: "list[str] | None" = None,
) -> dict:
    """KHÔNG BAO GIỜ raise ra ngoài — mọi lỗi trả về {} (đúng nguyên tắc CLAUDE.md mục 10)."""
    settings = get_settings()
    client = OpenAI(api_key=settings.gemini_api_key, base_url=str(settings.gemini_base_url).rstrip("/") + "/")
    messages = _build_messages(system_prompt, user_prompt, image_base64, labels=labels)

    content = "{}"
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.gemini_model,
                messages=messages,
                temperature=temperature,
            )
            content = response.choices[0].message.content or "{}"
            break
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < max_retries:
                wait_s = 2 * (attempt + 1)
                print(f"⏳ [COMPLIANCE LLM RATE LIMIT] Thử lại {attempt + 1}/{max_retries} sau {wait_s}s...")
                time.sleep(wait_s)
                continue
            print(f"❌ [COMPLIANCE LLM ERROR]: {e}")
            return {}

    cleaned = content.strip()
    match_codeblock = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match_codeblock:
        cleaned = match_codeblock.group(1).strip()
    try:
        repaired = repair_json(cleaned)
        data = json.loads(repaired)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"❌ [COMPLIANCE JSON PARSE ERROR]: {e}")
        return {}


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ [compliance_checker.engine.agents] Không đọc được {path}: {e}")
        return {}


def load_compliance_policy_context(platform: "str | None", country: "str | None") -> str:
    """
    Bản riêng cho compliance_checker — đọc compliance_checker/data/policies/{platform}_{country}.md
    (KHÁC với knowledge_loader.load_policy_context vốn đọc knowledge_base/ của hệ marketing-copy
    cũ) — cùng PATTERN fallback-safe, không raise, nhưng tách dữ liệu riêng theo đúng nguyên
    tắc "triển khai tách biệt" (CLAUDE.md mục 0).
    """
    platform_clean = (platform or "").lower().strip()
    country_clean = (country or "us").lower().strip()
    if not platform_clean:
        return ""
    path = os.path.join(_DATA_DIR, "policies", f"{platform_clean}_{country_clean}.md")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception as e:
            print(f"⚠️ [compliance_checker.engine.agents] Lỗi đọc {path}: {e}")
    return ""


def _get_niche_taxonomy() -> dict:
    return _load_json(os.path.join(_DATA_DIR, "niche_taxonomy.json"))


def _get_logo_brand_names() -> list[str]:
    manifest = _load_json(os.path.join(_DATA_DIR, "logo_refs", "manifest.json"))
    return [b["brand_name"] for b in manifest.get("brands", [])]


# =====================================================================
# AGENT 1 — CLASSIFY (Vision, có ảnh)
# =====================================================================

def _build_agent1_prompt(niche_taxonomy: dict, brand_names: list[str]) -> tuple[str, str]:
    niches_text = ", ".join(n["slug"] for n in niche_taxonomy.get("niches", []))
    styles_text = ", ".join(s["slug"] for s in niche_taxonomy.get("styles", []))
    motifs_text = ", ".join(niche_taxonomy.get("global_dangerous_motifs", {}).get("motifs", []))
    brands_text = ", ".join(brand_names) if brand_names else "(chưa có danh sách brand tham chiếu)"

    system_prompt = f"""You are a Senior IP Compliance Vision Analyst for a Print-on-Demand marketplace.
Analyze the uploaded design image and classify it — you are NOT limited to the reference lists below, always classify freely even for niches/styles outside them.

📌 If MULTIPLE images are provided (marked "--- Trang N/M ---", i.e. pages of a multi-page PDF/document), treat them as ONE single design submission — analyze ALL pages together and consolidate everything (OCR_text, motifs, suspected_logos) into ONE JSON response covering the whole document, do NOT answer per page.

📌 REFERENCE NICHE LIST (not exhaustive, use if it fits, otherwise propose your own): {niches_text}
📌 REFERENCE STYLE LIST (not exhaustive): {styles_text}
📌 UNIVERSAL DANGEROUS MOTIFS to always scan for regardless of niche: {motifs_text}
📌 KNOWN BRAND NAMES to check against (or any other famous brand you recognize outside this list): {brands_text}

TASK:
1. `niche`: the main niche/theme of this design.
2. `style`: the visual style.
3. `motifs`: list of sub-themes/motifs detected, including ANY of the universal dangerous motifs above if present.
4. `OCR_text`: transcribe ALL visible text in the image, verbatim, in its original language.
5. `suspected_logos`: TOP 5 suspected brand logos (fewer if genuinely fewer plausible candidates), each with "brand_name" and "confidence" ("low"/"medium"/"high").
6. `suspected_characters`: TOP 5 suspected copyrighted cartoon/comic/anime characters (fewer if fewer candidates), each with "name" and "confidence" — list EVERY suspicion even if uncertain, do NOT self-filter.
7. `suspected_celebrities`: TOP 5 suspected real-world celebrities/athletes/politicians (fewer if fewer candidates), each with "name" and "confidence" — judge ONLY from visible cues (a printed name, a highly iconic/unmistakable likeness); when unsure, still list with "low" confidence rather than omitting.

📌 All 3 lists above are a broad CANDIDATE-GENERATION pass only — a downstream Agent will look at the image again and verify each candidate one by one. So err on the side of listing a plausible guess rather than omitting it; being wrong here is cheap, omitting a real violation is not.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, no text outside it, exact keys only.

REQUIRED JSON SHAPE (fill in real values):
{{
  "niche": "christmas_holiday",
  "style": "vintage_retro",
  "motifs": ["motif1"],
  "OCR_text": "exact text seen in the image, or empty string if none",
  "suspected_logos": [{{"brand_name": "nike", "confidence": "medium"}}],
  "suspected_characters": [{{"name": "Mickey Mouse", "confidence": "high"}}],
  "suspected_celebrities": [{{"name": "Taylor Swift", "confidence": "low"}}]
}}"""
    user_prompt = "Classify this design image per the instructions above."
    return system_prompt, user_prompt


def run_agent1_classify(image_base64: "str | list[str]", niche_taxonomy: "dict | None" = None, brand_names: "list[str] | None" = None) -> dict:
    niche_taxonomy = niche_taxonomy if niche_taxonomy is not None else _get_niche_taxonomy()
    brand_names = brand_names if brand_names is not None else _get_logo_brand_names()
    system_prompt, user_prompt = _build_agent1_prompt(niche_taxonomy, brand_names)
    raw = _call_llm_json(system_prompt, user_prompt, image_base64=image_base64, temperature=0.2)

    niche = str(raw.get("niche") or "unknown")
    style = str(raw.get("style") or "unknown")
    motifs = raw.get("motifs") if isinstance(raw.get("motifs"), list) else []
    ocr_text = str(raw.get("OCR_text") or "")

    raw_logos = raw.get("suspected_logos") if isinstance(raw.get("suspected_logos"), list) else []
    # Python filter NGAY sau khi nhận response — bỏ "low" (nhiễu), giữ "medium"+"high"
    # (bỏ sót logo cách điệu ở "medium" nguy hiểm hơn false positive — CLAUDE.md mục 2.1).
    # Cap [:5] phòng model trả nhiều hơn yêu cầu dù đã ghi rõ "TOP 5" trong prompt.
    suspected_logos = [
        {"brand_name": str(item.get("brand_name", "")).strip(), "confidence": item.get("confidence", "low")}
        for item in raw_logos
        if isinstance(item, dict) and item.get("confidence") in ("medium", "high") and str(item.get("brand_name", "")).strip()
    ][:5]

    # ⚠️ (2026-08-21) suspected_characters/suspected_celebrities CHUYỂN từ Agent 2 sang đây —
    # Agent 2 giờ KHÔNG còn tự detect từ đầu nữa, chỉ verify lại đúng list này (xem
    # run_agent2_verify_candidates bên dưới). KHÔNG tự lọc "low" ở đây (khác suspected_logos)
    # — giữ nguyên policy cũ của Agent 2: để bước cross-reference + verify quyết định, tự lọc
    # sớm ở đây dễ bỏ sót false negative hơn (character/celeb khó nhận diện hơn logo nhiều).
    clean_names = lambda lst: [
        {"name": str(i.get("name", "")).strip(), "confidence": i.get("confidence", "low")}
        for i in lst if isinstance(i, dict) and str(i.get("name", "")).strip()
    ][:5]
    raw_chars = raw.get("suspected_characters") if isinstance(raw.get("suspected_characters"), list) else []
    raw_celebs = raw.get("suspected_celebrities") if isinstance(raw.get("suspected_celebrities"), list) else []

    return {
        "niche": niche, "style": style, "motifs": [str(m) for m in motifs],
        "OCR_text": ocr_text, "suspected_logos": suspected_logos,
        "suspected_characters": clean_names(raw_chars),
        "suspected_celebrities": clean_names(raw_celebs),
        "text_source": "vision_ocr",
    }


# =====================================================================
# AGENT 2 — VERIFY CANDIDATES (Vision, có ảnh)
# =====================================================================
# ⚠️ (2026-08-21) THIẾT KẾ LẠI theo quyết định của nhóm: Agent 2 KHÔNG còn tự detect
# character/celebrity từ đầu (việc đó dời sang Agent 1, top 5 mỗi loại — cùng logic với
# suspected_logos). Agent 2 giờ là 1 bước VERIFY riêng: nhận đúng list candidate Agent 1 đã
# nêu (logo + character + celebrity gộp chung), nhìn lại ảnh và trả lời CÓ/KHÔNG cho từng
# mục — mục đích giảm false positive từ việc Agent 1 đoán rộng tay (top 5 luôn liệt kê kể cả
# không chắc). Đây KHÔNG phải 1 lượt detect mới — prompt cấm tự thêm mục ngoài danh sách.

def _build_agent2_prompt(candidates: dict, num_face_crops: int, text_blocks: "list[dict] | None" = None) -> tuple[str, str]:
    lines = []
    for item in candidates.get("logos", []) or []:
        name = str(item.get("brand_name", "")).strip()
        if name:
            lines.append(f'- category="logo", name="{name}"')
    for item in candidates.get("characters", []) or []:
        name = str(item.get("name", "")).strip()
        if name:
            lines.append(f'- category="character", name="{name}"')
    for item in candidates.get("celebrities", []) or []:
        name = str(item.get("name", "")).strip()
        if name:
            lines.append(f'- category="celebrity", name="{name}"')
    candidates_text = "\n".join(lines) if lines else "(no candidates)"

    verify_task = ""
    verify_shape = ""
    if lines:
        verify_task = f"""
TASK 1 — VERIFY CANDIDATES: A prior detector (Agent 1) examined the design image(s) above and
produced a list of CANDIDATE items it suspects might be present — logos, copyrighted characters,
celebrities. Your job is to look at the design image(s) carefully and verify, for EACH candidate
below, whether it is ACTUALLY visibly present or not.

🚨 This is a VERIFICATION pass, NOT a fresh detection pass — do NOT add any item that is not in
the candidate list below, even if you notice something else. Only judge the exact items given.

📌 CANDIDATES TO VERIFY:
{candidates_text}

For each candidate, decide:
- "present": true if you can genuinely see this specific item in the image, false if you look
  carefully and it is NOT actually there (Agent 1 may have over-guessed — it is fine and
  expected to say false when in doubt, that is the whole point of this check).
- "reasoning": one short sentence.

Echo the "name" and "category" fields EXACTLY as given above (do not rephrase/translate them)."""
        verify_shape = '"verifications": [{"category": "logo", "name": "nike", "present": true, "reasoning": "The swoosh logo is clearly visible on the chest."}]'

    face_task = ""
    face_shape = ""
    if num_face_crops > 0:
        face_task = f"""

TASK 2 — IDENTIFY FACE CROPS: after the design image(s) above, you are also shown {num_face_crops}
CROPPED FACE image(s), each labeled "Suspected face crop #N" — extracted automatically by a face
DETECTOR (BlazeFace) from the same design. The detector only found WHERE faces are, it has NO
idea WHO they are. For EACH face crop (in the exact order shown), look closely and decide: do
you recognize this specific person as a real, identifiable public figure (celebrity/athlete/
politician/public personality/etc)?

🚨 This is YOUR OWN visual judgment — you are NOT checking against any database or reference
list. Most faces in most photos are NOT celebrities — be honest: if you do not recognize the
person, say so (null), do NOT force a guess just to fill the field.

For each face crop, output:
- "face_index": the crop's 0-based position, matching the order shown (0 = first face crop)
- "suspected_name": your best guess of who this is, or null if you do not recognize them
- "confidence": "high"/"medium"/"low" — how sure you are of the identification itself (only
  meaningful when suspected_name is not null)
- "reasoning": one short sentence"""
        face_shape = '"face_identifications": [{"face_index": 0, "suspected_name": "Cristiano Ronaldo", "confidence": "medium", "reasoning": "Strong facial resemblance, well-known athlete."}]'

    text_task = ""
    text_shape = ""
    if text_blocks:
        blocks_text = "\n".join(f'{i}: "{b.get("text", "")}"' for i, b in enumerate(text_blocks))
        text_task = f"""

TASK 3 — TRADEMARK / SLOGAN SENSE-CHECK (TEXT ONLY, no image needed for this task): below is a
list of TEXT BLOCKS extracted by an OCR engine from the design. OCR grouping is geometric and
imperfect — a single slogan may have been split across multiple blocks, or blocks may contain
OCR noise/misreads.

1. Read through ALL blocks together. If fragments across DIFFERENT blocks look like they form
   one phrase/slogan when joined, mentally reconstruct it yourself.
2. Using your OWN knowledge (you are NOT limited to any fixed database — a separate deterministic
   database check already runs independently in Python, this is purely YOUR judgment as a second,
   independent opinion), judge whether any reconstructed phrase is a well-known trademarked
   slogan, brand name, or copyrighted phrase that would cause real IP risk if sold on a
   Print-on-Demand product.
3. Flag anything you are genuinely suspicious of — including a phrase that closely imitates/
   references a famous brand even if you can't pin the exact source. Skip clearly generic/safe
   text (plain product descriptions, random words) — do NOT enumerate every block, only flagged ones.

📌 TEXT BLOCKS (block_index: text):
{blocks_text}

For each flagged item, output:
- "block_indexes": list of the block_index value(s) involved (usually just one; multiple only
  if you joined fragments across blocks)
- "phrase": the reconstructed phrase/text you are flagging (your best reconstruction, not
  necessarily verbatim from one block)
- "suspicion": "high"/"medium"/"low" — "high" means you are quite confident this is a real,
  recognizable trademarked phrase/slogan (this will be treated as seriously as a real database
  match, even with zero database evidence — so only use "high" when you are genuinely sure)
- "reasoning": one short sentence"""
        text_shape = '"text_trademark_flags": [{"block_indexes": [0], "phrase": "Just Do It", "suspicion": "high", "reasoning": "Iconic Nike slogan, globally recognizable."}]'

    all_shapes = ",\n  ".join(s for s in (verify_shape, face_shape, text_shape) if s)

    system_prompt = f"""You are a Verification Specialist for a Print-on-Demand IP compliance system.
{verify_task}{face_task}{text_task}

📌 If multiple design images are provided (marked "--- Trang N/M ---", i.e. pages of a multi-page PDF/document), treat them as ONE single design submission covering all pages.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, no text outside it, exact keys only.

REQUIRED JSON SHAPE:
{{
  {all_shapes}
}}"""
    user_prompt = "Complete the task(s) above against the image(s) shown, in order."
    return system_prompt, user_prompt


def run_agent2_verify_candidates(
    image_base64: "str | list[str]",
    candidates: dict,
    face_crops: "list[dict] | None" = None,
    text_blocks: "list[dict] | None" = None,
) -> dict:
    """
    candidates: {"logos": [{"brand_name","confidence"}], "characters": [{"name","confidence"}],
    "celebrities": [{"name","confidence"}]} — lấy trực tiếp từ suspected_logos/suspected_characters/
    suspected_celebrities của run_agent1_classify().

    face_crops: (2026-08-21) output opencv_modules.detect_and_crop_faces()["faces"] —
    [{"face_base64","bbox_norm","detection_score"}, ...]. Model BlazeFace CHỈ detect vị trí mặt,
    KHÔNG định danh — ảnh crop được gửi thẳng cho Agent 2 (Claude Vision) tự nhận diện trực
    tiếp, KHÔNG đối chiếu database (quyết định của nhóm, xem docs.md).

    text_blocks: (2026-08-21, MỚI) output opencv_modules.extract_text_blocks()["text_blocks"] —
    [{"bbox_norm","text","ocr_confidence"}, ...]. CHỈ gửi TEXT (không gửi ảnh crop cho task
    này) — quyết định có chủ đích để tối ưu tốc độ/chi phí: đánh giá "đây có phải trademark/
    slogan nổi tiếng không" là bài toán NGÔN NGỮ thuần tuý, không cần nhìn ảnh (khác face
    identification — việc đó THẬT SỰ cần nhìn). Agent 2 tự ghép các block rời rạc thành câu
    + vừa so khớp cảm nhận riêng, vừa để Python (trademark_resolver.py, không đổi) so khớp
    database độc lập — 2 nguồn gộp qua black_box.py::_combine_category_results.

    Không có candidate/face_crop/text_block NÀO -> khỏi tốn 1 lần gọi LLM, trả rỗng luôn.
    """
    candidates = candidates or {}
    face_crops = face_crops or []
    text_blocks = text_blocks or []
    has_candidates = any(candidates.get(k) for k in ("logos", "characters", "celebrities"))
    if not has_candidates and not face_crops and not text_blocks:
        return {"verifications": [], "face_identifications": [], "text_trademark_flags": []}

    system_prompt, user_prompt = _build_agent2_prompt(candidates, len(face_crops), text_blocks)

    # Ảnh thiết kế gốc (1 hoặc nhiều trang) đi TRƯỚC, ảnh mặt crop đi SAU — nhãn riêng cho từng
    # loại để Agent 2 không nhầm "trang thiết kế" với "ảnh mặt cắt" (xem _build_messages labels).
    design_images = image_base64 if isinstance(image_base64, list) else ([image_base64] if image_base64 else [])
    design_images = [img for img in design_images if img]
    design_labels = (
        [f"Design page {i + 1}/{len(design_images)}" for i in range(len(design_images))]
        if len(design_images) > 1 else [None] * len(design_images)
    )
    face_images = [f["face_base64"] for f in face_crops if f.get("face_base64")]
    face_labels = [f"Suspected face crop #{i} (detector confidence {face_crops[i].get('detection_score', 0):.2f})" for i in range(len(face_images))]

    all_images = design_images + face_images
    all_labels = design_labels + face_labels

    raw = _call_llm_json(system_prompt, user_prompt, image_base64=all_images, temperature=0.1, labels=all_labels)

    raw_verifications = raw.get("verifications") if isinstance(raw.get("verifications"), list) else []
    clean_verifications = []
    for item in raw_verifications:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        category = item.get("category")
        if not name or category not in ("logo", "character", "celebrity"):
            continue
        clean_verifications.append({
            "category": category,
            "name": name,
            # Thiếu field "present" (JSON lỗi/model bỏ sót) -> mặc định True (fail-open, KHÔNG
            # tự ý loại bỏ evidence chỉ vì lỗi parse — đúng nguyên tắc CLAUDE.md mục 10).
            "present": bool(item.get("present", True)),
            "reasoning": str(item.get("reasoning", "")),
        })

    raw_faces = raw.get("face_identifications") if isinstance(raw.get("face_identifications"), list) else []
    clean_faces = []
    for item in raw_faces:
        if not isinstance(item, dict):
            continue
        try:
            face_index = int(item.get("face_index"))
        except (TypeError, ValueError):
            continue
        name = item.get("suspected_name")
        name = str(name).strip() if name else None
        conf = item.get("confidence") if name else None  # không có tên -> confidence vô nghĩa, bỏ qua
        clean_faces.append({
            "face_index": face_index,
            "suspected_name": name or None,
            "confidence": conf if conf in ("low", "medium", "high") else None,
            "reasoning": str(item.get("reasoning", "")),
        })

    raw_text_flags = raw.get("text_trademark_flags") if isinstance(raw.get("text_trademark_flags"), list) else []
    clean_text_flags = []
    for item in raw_text_flags:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase", "")).strip()
        suspicion = item.get("suspicion")
        if not phrase or suspicion not in ("low", "medium", "high"):
            continue
        raw_indexes = item.get("block_indexes")
        indexes = [int(i) for i in raw_indexes if isinstance(i, (int, float))] if isinstance(raw_indexes, list) else []
        clean_text_flags.append({
            "block_indexes": indexes,
            "phrase": phrase,
            "suspicion": suspicion,
            "reasoning": str(item.get("reasoning", "")),
        })

    return {"verifications": clean_verifications, "face_identifications": clean_faces, "text_trademark_flags": clean_text_flags}


# =====================================================================
# NHÓM C — TỔNG HỢP + ĐỊNH VỊ (1 LLM call)
# =====================================================================

def _build_group_c_prompt(evidence_bundle: dict, pdf_text_blocks: "list | None") -> tuple[str, str]:
    bbox_note = (
        "This design comes from a digital-native PDF — real pixel bounding boxes are provided "
        "below for text elements; use them directly instead of estimating a grid position for text."
        if pdf_text_blocks else
        "Use a 3x3 grid description (top-left/top-center/top-right/center-left/center/center-right/"
        "bottom-left/bottom-center/bottom-right) to describe WHERE each issue appears — do NOT "
        "attempt precise pixel coordinates, vision models are not reliable at that."
    )
    bbox_data = json.dumps(pdf_text_blocks, ensure_ascii=False) if pdf_text_blocks else "(not available — use grid description)"

    system_prompt = f"""You are a Compliance Evidence Synthesizer. You receive raw evidence from multiple
independent detectors and must produce a neutral positioning summary — NOT a final verdict
(that is decided by deterministic Python code downstream, not you).

📌 EVIDENCE BUNDLE (from Agent 2 vision + OpenCV modules + trademark text resolver):
{json.dumps(evidence_bundle, ensure_ascii=False)}

📌 POSITIONING RULE: {bbox_note}
📌 PDF TEXT BLOCKS WITH REAL BBOX (if available): {bbox_data}

🚨 CITATION RULE (mandatory):
- OK: cite as "matched against pre-compiled reference database (last updated {{date}})".
- OK to cite a specific registration number ONLY if it is present in the evidence bundle above (i.e. came from a real lookup).
- NEVER invent/hallucinate a registration or case number that is not in the evidence bundle.

TASK: for each non-empty evidence item, write one positioning_note: {{"category", "location_description", "citation"}}. Then write a short neutral "summary".

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, exact keys only.

REQUIRED JSON SHAPE:
{{
  "positioning_notes": [{{"category": "logo_similarity", "location_description": "top-center", "citation": "matched against pre-compiled reference database"}}],
  "summary": "short neutral summary of all evidence found"
}}"""
    user_prompt = "Synthesize the evidence bundle above per the instructions."
    return system_prompt, user_prompt


def run_group_c_synthesis(evidence_bundle: dict, pdf_text_blocks: "list | None" = None) -> dict:
    system_prompt, user_prompt = _build_group_c_prompt(evidence_bundle, pdf_text_blocks)
    raw = _call_llm_json(system_prompt, user_prompt, temperature=0.2)
    notes = raw.get("positioning_notes") if isinstance(raw.get("positioning_notes"), list) else []
    clean_notes = [
        {"category": str(n.get("category", "")), "location_description": str(n.get("location_description", "")),
         "citation": str(n.get("citation", ""))}
        for n in notes if isinstance(n, dict)
    ]
    return {"positioning_notes": clean_notes, "summary": str(raw.get("summary", ""))}


# =====================================================================
# AGENT 3 — REASONING + FIX SUGGESTION (cần ảnh)
# =====================================================================

def _build_agent3_prompt(black_box_result: dict, positioning: dict) -> tuple[str, str]:
    system_prompt = f"""You are a Senior Compliance Advisor writing the final human-readable reasoning
for a design's compliance verdict, and — if RISKY/BLOCKED — a concrete, actionable fix for EVERY
violation found (not just one).

📌 FINAL VERDICT (already decided by deterministic code, do NOT change it, only explain it): {black_box_result.get("final_verdict")}
📌 EVIDENCE (all non-SAFE categories): {json.dumps(black_box_result.get("evidence", {}), ensure_ascii=False)}
📌 POSITIONING NOTES: {json.dumps(positioning, ensure_ascii=False)}

TASK:
1. `reasoning`: a clear paragraph explaining WHY this verdict was reached, referencing the evidence above.
2. `fix_suggestions`: if evidence is non-empty, one entry PER violation category, each with a concrete, actionable fix (e.g. "Replace the Nike logo with a custom-designed icon"). If evidence is empty (fully SAFE), return an empty list.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, exact keys only.

REQUIRED JSON SHAPE:
{{
  "reasoning": "explanation text",
  "fix_suggestions": [{{"violation": "logo_similarity", "suggestion": "concrete actionable fix"}}]
}}"""
    user_prompt = "Write the reasoning and fix suggestions based on the design image and the verdict/evidence above."
    return system_prompt, user_prompt


def run_agent3_reasoning(image_base64: "str | list[str] | None", black_box_result: dict, positioning: dict) -> dict:
    system_prompt, user_prompt = _build_agent3_prompt(black_box_result, positioning)
    raw = _call_llm_json(system_prompt, user_prompt, image_base64=image_base64, temperature=0.3)
    fixes = raw.get("fix_suggestions") if isinstance(raw.get("fix_suggestions"), list) else []
    clean_fixes = [
        {"violation": str(f.get("violation", "")), "suggestion": str(f.get("suggestion", ""))}
        for f in fixes if isinstance(f, dict)
    ]
    return {"reasoning": str(raw.get("reasoning", "")), "fix_suggestions": clean_fixes}


# =====================================================================
# AGENT 4 — MARKET/PLATFORM SUGGESTION (text-only, KHÔNG cần ảnh, độc lập)
# =====================================================================

def run_agent4_market_suggestion(niche: str, style: str, target_country: str = "US", platform: "str | None" = None) -> dict:
    """
    KHÔNG gửi image_base64 — chỉ cần niche/style từ Agent 1, rẻ hơn nhiều. Tiêm policy (4
    platform) + trend context — phần tiêm này gần như KHÔNG đổi giữa các design trong batch,
    ứng viên tốt cho prompt caching (chưa bật caching ở bản này, ghi nhận làm TODO).

    ⚠️ FIX #1 (bug thật): trước đây hàm này KHÔNG nhận target_country, luôn hardcode "us" khi
    tiêm policy/trend — dù request gửi target_country nào, Agent 4 vẫn chỉ thấy được context US.
    Giờ dùng target_country thật — CHƯA có data policy/trend ngoài US nên với quốc gia khác,
    load_compliance_policy_context()/load_trend_context() trả rỗng (fallback-safe, không lỗi).

    ⚠️ FIX #2 (khoảng trống thiết kế, không phải bug): top_country_suggestion/top_platform_suggestion
    là gợi ý ĐỘC LẬP của Agent 4 (đúng đặc tả CLAUDE.md gốc — "gợi ý", không phải "thẩm định"),
    KHÔNG hề biết/không quan tâm user đã tự chọn platform gì — nên dù bạn chọn Amazon, Agent 4
    vẫn có thể gợi ý Etsy nếu nó thật sự tốt hơn, và điều đó KHÔNG trả lời được câu hỏi "platform
    tôi chọn có ổn không". Thêm 2 field MỚI, RIÊNG biệt: selected_platform_suitable (bool) +
    selected_platform_rationale (str) — thẩm định đúng platform+country user ĐÃ CHỌN, hỏi trong
    CÙNG 1 lần gọi LLM (không tốn thêm API call). Chỉ hỏi khi platform thật sự được truyền vào
    (None nếu user không chọn platform — không có gì để thẩm định).
    """
    country_clean = (target_country or "US").lower().strip()
    platform_clean = (platform or "").lower().strip()
    platforms = ["etsy", "amazon", "tiktok", "shopify"]
    policy_blocks = "\n\n".join(
        f"[{p.upper()}]\n{load_compliance_policy_context(p, country_clean) or '(chưa có data policy cho thị trường này)'}"
        for p in platforms
    )
    trend_block = load_trend_context(country_clean) or "(chưa có data trend cho thị trường này)"

    selected_combo_header = ""
    selected_combo_task = ""
    selected_combo_json = ""
    if platform_clean:
        selected_combo_header = (
            f'\n📌 USER ĐÃ TỰ CHỌN SẴN (không phải gợi ý của bạn): platform="{platform_clean}", '
            f'country="{country_clean.upper()}"\n'
        )
        selected_combo_task = f"""
3. `selected_platform_suitable` (true/false): THẨM ĐỊNH RIÊNG platform+country user ĐÃ CHỌN
   ("{platform_clean}" tại "{country_clean.upper()}") — combo NÀY có phù hợp/an toàn để đăng
   design này không, dựa trên IP-compliance risk của CHÍNH platform đó (KHÔNG phải platform bạn
   gợi ý ở mục 1 — 2 câu trả lời có thể khác nhau, ví dụ user chọn Amazon nhưng bạn gợi ý Etsy
   tốt hơn, vẫn phải trả lời trung thực Amazon có ổn hay không, không né tránh).
4. `selected_platform_rationale`: giải thích ngắn cho câu trả lời #3, trích dẫn đúng policy của
   CHÍNH platform "{platform_clean}" ở trên (nếu policy đó bị đánh dấu thiếu data, nói thật)."""
        selected_combo_json = (
            ', "selected_platform_suitable": true, '
            '"selected_platform_rationale": "short rationale for the user\'s ACTUAL selected platform/country, citing its own policy"'
        )

    system_prompt = f"""You are a Market/Platform Advisor for Print-on-Demand sellers, specializing in
IP compliance risk per platform.
{selected_combo_header}
📌 TARGET COUNTRY REQUESTED: {country_clean.upper()}
📌 NICHE: {niche} | STYLE: {style}
📌 PLATFORM IP POLICIES (for {country_clean.upper()}):
{policy_blocks}
📌 MARKET TREND CONTEXT (for {country_clean.upper()}):
{trend_block}

TASK:
1. `top_country_suggestion`/`top_platform_suggestion`: your OWN independent recommendation of the
   single best country+platform to launch this niche/style on (commercial fit + IP-compliance
   risk) — this does NOT need to match what the user already selected, if any.
2. `rationale`: short rationale for #1.{selected_combo_task}

If policy/trend context above is marked "(chưa có data...)" (missing), say so honestly instead
of inventing details.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, exact keys only. Base your
answer on the ACTUAL context above — do NOT copy the example values below verbatim, they are
placeholders only.

REQUIRED JSON SHAPE (keys only, fill in real values from the context above):
{{"top_country_suggestion": "<2-letter country code>", "top_platform_suggestion": "<platform name>", "rationale": "short rationale citing the policy/trend context above, or noting missing data"{selected_combo_json}}}"""
    user_prompt = f"Recommend the best country/platform for a '{niche}' niche, '{style}' style design targeting {country_clean.upper()}."
    raw = _call_llm_json(system_prompt, user_prompt, temperature=0.4)
    result = {
        "top_country_suggestion": str(raw.get("top_country_suggestion", "")),
        "top_platform_suggestion": str(raw.get("top_platform_suggestion", "")),
        "rationale": str(raw.get("rationale", "")),
        "selected_platform_suitable": None,
        "selected_platform_rationale": "",
    }
    if platform_clean:
        suitable = raw.get("selected_platform_suitable")
        result["selected_platform_suitable"] = bool(suitable) if isinstance(suitable, bool) else None
        result["selected_platform_rationale"] = str(raw.get("selected_platform_rationale", ""))
    return result
