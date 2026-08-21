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
    Không truyền -> giữ NGUYÊN hành vi cũ: nhiều ảnh không nhãn -> tự đánh "Page N/M", 1 ảnh
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
            content.append({"type": "text", "text": f"--- Page {i + 1}/{len(images)} ---"})
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


def _get_text_reference(filename: str) -> str:
    """Đọc nguyên văn 1 file .md trong data/ để tiêm vào prompt dạng prose (giống cách Agent 4
    tiêm policy_blocks) — dùng cho font_watchlist.md/artwork_list.md (2026-08-22, MỚI): 2 file
    này là prose, KHÔNG có cấu trúc tên sạch để Python parse như character_list.md/
    celebrity_list.md, nên tiêm nguyên văn để LLM tự đọc hiểu ngữ cảnh/ví dụ, không cố parse
    thành list tên. Fallback rỗng, không raise (đúng nguyên tắc chung mọi loader trong module)."""
    path = os.path.join(_DATA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


# =====================================================================
# AGENT 1 — CLASSIFY (Vision, có ảnh)
# =====================================================================

def _build_agent1_prompt(
    niche_taxonomy: dict, brand_names: list[str], font_reference: str = "", artwork_reference: str = ""
) -> tuple[str, str]:
    niches_text = ", ".join(n["slug"] for n in niche_taxonomy.get("niches", []))
    styles_text = ", ".join(s["slug"] for s in niche_taxonomy.get("styles", []))
    motifs_text = ", ".join(niche_taxonomy.get("global_dangerous_motifs", {}).get("motifs", []))
    brands_text = ", ".join(brand_names) if brand_names else "(chưa có danh sách brand tham chiếu)"
    # sub_niches: gộp phẳng ví dụ của MỌI niche thành 1 list tham khảo — Agent 1 tự chọn cái
    # khớp nhất với niche đã detect, KHÔNG bắt buộc đúng niche đang chọn phải khớp 1-1 với
    # sub_niche (vd niche lạ ngoài taxonomy vẫn được tự do đề xuất sub_niche tương ứng).
    sub_niches_text = ", ".join(
        sn for n in niche_taxonomy.get("niches", []) for sn in n.get("sub_niches", [])
    ) or "(chưa có danh sách sub_niche tham khảo)"
    # (2026-08-22, MỚI) motif_examples: ví dụ motif CHUNG CHUNG (khác global_dangerous_motifs —
    # đó là nhóm an toàn/nguy hiểm riêng) — trích thật từ file mẫu BGK (design_samples_template.xlsx),
    # giúp field `motifs` bám sát đúng những gì giám khảo mong đợi thay vì Agent 1 tự bịa loại motif.
    motif_examples_text = ", ".join(niche_taxonomy.get("motif_examples", {}).get("motifs", [])) or "(chưa có ví dụ motif tham khảo)"

    system_prompt = f"""You are a Senior IP Compliance Vision Analyst for a Print-on-Demand marketplace.
Analyze the uploaded design image and classify it — you are NOT limited to the reference lists below, always classify freely even for niches/styles outside them.

📌 If MULTIPLE images are provided (marked "--- Page N/M ---", i.e. pages of a multi-page PDF/document), treat them as ONE single design submission — analyze ALL pages together and consolidate everything (OCR_text, motifs, suspected_logos) into ONE JSON response covering the whole document, do NOT answer per page.

📌 REFERENCE NICHE LIST (not exhaustive, use if it fits, otherwise propose your own): {niches_text}
📌 REFERENCE SUB-NICHE EXAMPLES (not exhaustive, illustrative only — pick/propose whatever actually fits the niche above): {sub_niches_text}
📌 REFERENCE STYLE LIST (not exhaustive): {styles_text}
📌 REFERENCE MOTIF EXAMPLES (general, not exhaustive — illustrative only, propose your own if nothing here fits): {motif_examples_text}
📌 UNIVERSAL DANGEROUS MOTIFS to always scan for regardless of niche: {motifs_text}
📌 KNOWN BRAND NAMES to check against (or any other famous brand you recognize outside this list): {brands_text}
📌 FONT-RISK REFERENCE (background context — commercial fonts commonly used without a license in POD, NOT an exhaustive/confirmable list):
{font_reference or "(no font reference on file)"}
📌 ARTWORK-RISK REFERENCE (background context — commonly copyrighted artwork/franchises, NOT an exhaustive/confirmable list):
{artwork_reference or "(no artwork reference on file)"}

TASK:
1. `niche`: the main niche/theme of this design.
2. `sub_niche`: a more specific sub-category within that niche (e.g. niche="christmas_holiday" -> sub_niche="ugly_christmas_sweater"). Propose your own if nothing in the reference examples fits.
3. `style`: the visual style.
4. `motifs`: list of sub-themes/motifs detected, including ANY of the universal dangerous motifs above if present.
5. `OCR_text`: transcribe ALL visible text in the image, verbatim, in its original language.
6. `suspected_logos`: TOP 5 suspected brand logos (fewer if genuinely fewer plausible candidates), each with "brand_name" and "confidence" ("low"/"medium"/"high").
7. `suspected_characters`: TOP 5 suspected copyrighted cartoon/comic/anime characters (fewer if fewer candidates), each with "name" and "confidence" — list EVERY suspicion even if uncertain, do NOT self-filter.
8. `suspected_celebrities`: TOP 5 suspected real-world celebrities/athletes/politicians (fewer if fewer candidates), each with "name" and "confidence" — judge ONLY from visible cues (a printed name, a highly iconic/unmistakable likeness); when unsure, still list with "low" confidence rather than omitting.
9. `suspected_fonts`: TOP 5 suspected commercial/branded fonts used in the design (fewer if fewer candidates), each with "font_name_guess" (a specific font name ONLY if highly distinctive, otherwise a general style description like "bold condensed sans-serif") and "confidence".
10. `suspected_artworks`: TOP 5 suspected copyrighted artworks/illustrations/franchise key-art the design may be reproducing or closely deriving from (fewer if fewer candidates), each with "artwork_name" (the specific work/franchise, e.g. "Studio Ghibli movie poster style") and "confidence".

📌 All 5 candidate lists above (logos/characters/celebrities/fonts/artworks) are a broad CANDIDATE-GENERATION pass only — a downstream Agent will look at the image again and verify each candidate one by one. So err on the side of listing a plausible guess rather than omitting it; being wrong here is cheap, omitting a real violation is not.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, no text outside it, exact keys only.

REQUIRED JSON SHAPE (fill in real values):
{{
  "niche": "christmas_holiday",
  "sub_niche": "ugly_christmas_sweater",
  "style": "vintage_retro",
  "motifs": ["motif1"],
  "OCR_text": "exact text seen in the image, or empty string if none",
  "suspected_logos": [{{"brand_name": "nike", "confidence": "medium"}}],
  "suspected_characters": [{{"name": "Mickey Mouse", "confidence": "high"}}],
  "suspected_celebrities": [{{"name": "Taylor Swift", "confidence": "low"}}],
  "suspected_fonts": [{{"font_name_guess": "bold condensed sans-serif", "confidence": "low"}}],
  "suspected_artworks": [{{"artwork_name": "Studio Ghibli movie poster style", "confidence": "medium"}}]
}}"""
    user_prompt = "Classify this design image per the instructions above."
    return system_prompt, user_prompt


def run_agent1_classify(
    image_base64: "str | list[str]",
    niche_taxonomy: "dict | None" = None,
    brand_names: "list[str] | None" = None,
    font_reference: "str | None" = None,
    artwork_reference: "str | None" = None,
) -> dict:
    niche_taxonomy = niche_taxonomy if niche_taxonomy is not None else _get_niche_taxonomy()
    brand_names = brand_names if brand_names is not None else _get_logo_brand_names()
    font_reference = font_reference if font_reference is not None else _get_text_reference("font_watchlist.md")
    artwork_reference = artwork_reference if artwork_reference is not None else _get_text_reference("artwork_list.md")
    system_prompt, user_prompt = _build_agent1_prompt(niche_taxonomy, brand_names, font_reference, artwork_reference)
    raw = _call_llm_json(system_prompt, user_prompt, image_base64=image_base64, temperature=0.2)

    niche = str(raw.get("niche") or "unknown")
    sub_niche = str(raw.get("sub_niche") or "")
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
    # (2026-08-22) suspected_fonts/suspected_artworks dùng CHUNG helper này — cùng lý do KHÔNG
    # tự lọc sớm (font/artwork khó nhận diện chắc chắn hơn cả character/celeb, tự lọc sớm dễ
    # mất evidence thật trước khi Agent 2 kịp verify).
    def _clean_items(lst, key: str) -> list:
        return [
            {key: str(i.get(key, "")).strip(), "confidence": i.get("confidence", "low")}
            for i in lst if isinstance(i, dict) and str(i.get(key, "")).strip()
        ][:5]

    raw_chars = raw.get("suspected_characters") if isinstance(raw.get("suspected_characters"), list) else []
    raw_celebs = raw.get("suspected_celebrities") if isinstance(raw.get("suspected_celebrities"), list) else []
    raw_fonts = raw.get("suspected_fonts") if isinstance(raw.get("suspected_fonts"), list) else []
    raw_artworks = raw.get("suspected_artworks") if isinstance(raw.get("suspected_artworks"), list) else []

    return {
        "niche": niche, "sub_niche": sub_niche, "style": style, "motifs": [str(m) for m in motifs],
        "OCR_text": ocr_text, "suspected_logos": suspected_logos,
        "suspected_characters": _clean_items(raw_chars, "name"),
        "suspected_celebrities": _clean_items(raw_celebs, "name"),
        "suspected_fonts": _clean_items(raw_fonts, "font_name_guess"),
        "suspected_artworks": _clean_items(raw_artworks, "artwork_name"),
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

def _build_agent2_prompt(candidates: dict, num_face_crops: int, ocr_text: "str | None" = None) -> tuple[str, str]:
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
    for item in candidates.get("fonts", []) or []:
        name = str(item.get("font_name_guess", "")).strip()
        if name:
            lines.append(f'- category="font", name="{name}"')
    for item in candidates.get("artworks", []) or []:
        name = str(item.get("artwork_name", "")).strip()
        if name:
            lines.append(f'- category="artwork", name="{name}"')
    candidates_text = "\n".join(lines) if lines else "(no candidates)"

    verify_task = ""
    verify_shape = ""
    if lines:
        verify_task = f"""
TASK 1 — VERIFY CANDIDATES: A prior detector (Agent 1) examined the design image(s) above and
produced a list of CANDIDATE items it suspects might be present — logos, copyrighted characters,
celebrities, fonts, and artworks/illustrations. Your job is to look at the design image(s)
carefully and verify, for EACH candidate below, whether it is ACTUALLY visibly present or not.

🚨 This is a VERIFICATION pass, NOT a fresh detection pass — do NOT add any item that is not in
the candidate list below, even if you notice something else. Only judge the exact items given.

🚨 IMPORTANT — your reasoning carries real weight downstream: for any candidate you confirm
"present": true, a separate deterministic check will try to cross-reference the name against our
internal reference lists — but many real logos/characters/fonts/artworks are NOT in those lists
yet. If you are genuinely confident this is a real, recognizable IP violation (not just "it's
technically there"), your "reasoning" MUST clearly explain WHY (what it resembles, what makes you
confident) — a detailed, well-justified "reasoning" here CAN be enough on its own to get the
design BLOCKED even with zero match in our reference lists (same policy as the trademark-text
sense-check below). A vague reasoning like "it's visible" is NOT enough for that — be specific.

📌 CANDIDATES TO VERIFY:
{candidates_text}

For each candidate, decide:
- "present": true if you can genuinely see this specific item in the image, false if you look
  carefully and it is NOT actually there (Agent 1 may have over-guessed — it is fine and
  expected to say false when in doubt, that is the whole point of this check).
- "reasoning": one short sentence.

Echo the "name" and "category" fields EXACTLY as given above (do not rephrase/translate them)."""
        verify_shape = '"verifications": [{"category": "logo", "name": "nike", "present": true, "reasoning": "Logo dấu swoosh hiện rõ ở phần ngực áo."}]'

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
        face_shape = '"face_identifications": [{"face_index": 0, "suspected_name": "Cristiano Ronaldo", "confidence": "medium", "reasoning": "Gương mặt giống rõ, là vận động viên nổi tiếng."}]'

    text_task = ""
    text_shape = ""
    if ocr_text and ocr_text.strip():
        text_task = f"""

TASK 3 — TRADEMARK / SLOGAN SENSE-CHECK (TEXT ONLY, no image needed for this task): below is the
OCR text transcribed from the design by Agent 1 (may contain transcription noise/misreads).

1. Read through the full text below.
2. Using your OWN knowledge (you are NOT limited to any fixed database — a separate deterministic
   database check already runs independently in Python against a static/live trademark database;
   this is purely YOUR judgment as a second, independent opinion, and it runs BEFORE that database
   check's result is known — you cannot see whether the database will find a match or not), judge
   whether any phrase in it is a well-known trademarked slogan, brand name, or copyrighted phrase
   that would cause real IP risk if sold on a Print-on-Demand product.
3. Flag anything you are genuinely suspicious of — including a phrase that closely imitates/
   references a famous brand even if you can't pin the exact source. Skip clearly generic/safe
   text (plain product descriptions, random words) — only flag what's genuinely suspicious.

🚨 IMPORTANT: even if this phrase turns out to have NO match in our trademark database, your
"high" suspicion ALONE is enough to get this design BLOCKED downstream (a deliberate policy of
this system — an obvious real-world trademark should not slip through just because our database
doesn't happen to list it). Precisely BECAUSE this may be your judgment alone with no database
confirmation, for ANY item you flag as "high", your "reasoning" MUST: (a) clearly state WHICH
real brand/slogan/work you believe this matches or closely resembles and WHY, and (b) explicitly
recommend a quick manual double-check (e.g. against USPTO/EUIPO or a web search) before treating
it as fully certain, since it is an AI judgment call rather than a confirmed database hit.

📌 OCR TEXT:
\"\"\"
{ocr_text.strip()}
\"\"\"

For each flagged item, output:
- "phrase": the exact phrase/text you are flagging (verbatim from the OCR text above where possible)
- "suspicion": "high"/"medium"/"low" — "high" means you are quite confident this is a real,
  recognizable trademarked phrase/slogan (this will be treated as seriously as a real database
  match, even with zero database evidence — so only use "high" when you are genuinely sure)
- "reasoning": your justification — for "high", follow the (a)/(b) rule above"""
        text_shape = '"text_trademark_flags": [{"phrase": "Just Do It", "suspicion": "high", "reasoning": "Trùng khớp nguyên văn slogan nổi tiếng toàn cầu của Nike. Chưa có kết quả khớp trong database — nên kiểm chứng nhanh thủ công qua USPTO/EUIPO trước khi kết luận chắc chắn."}]'

    all_shapes = ",\n  ".join(s for s in (verify_shape, face_shape, text_shape) if s)

    system_prompt = f"""You are a Verification Specialist for a Print-on-Demand IP compliance system.
{verify_task}{face_task}{text_task}

📌 If multiple design images are provided (marked "--- Page N/M ---", i.e. pages of a multi-page PDF/document), treat them as ONE single design submission covering all pages.

🌐 OUTPUT LANGUAGE: write every "reasoning" value in professional, standard commercial Vietnamese
(tiếng Việt chuẩn thương mại — clear, formal business tone, no slang, no literal word-for-word
translation-ese). Do NOT translate: "name"/"category" (echo exactly as given), "suspected_name"
(a real person's name, proper noun), "confidence"/"suspicion" (fixed enum values), or "phrase"
(quote it verbatim in whatever language it appears in the design — do not translate the quote itself).

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
    ocr_text: "str | None" = None,
) -> dict:
    """
    candidates: {"logos": [{"brand_name","confidence"}], "characters": [{"name","confidence"}],
    "celebrities": [{"name","confidence"}], "fonts": [{"font_name_guess","confidence"}],
    "artworks": [{"artwork_name","confidence"}]} — lấy trực tiếp từ suspected_logos/
    suspected_characters/suspected_celebrities/suspected_fonts/suspected_artworks của
    run_agent1_classify() (2 field cuối MỚI thêm 2026-08-22, cùng pattern candidate-generation).

    face_crops: (2026-08-21) output opencv_modules.detect_and_crop_faces()["faces"] —
    [{"face_base64","bbox_norm","detection_score"}, ...]. Model BlazeFace CHỈ detect vị trí mặt,
    KHÔNG định danh — ảnh crop được gửi thẳng cho Agent 2 (Claude Vision) tự nhận diện trực
    tiếp, KHÔNG đối chiếu database (quyết định của nhóm, xem docs.md).

    ocr_text: (2026-08-22, ĐỔI từ text_blocks) TRƯỚC dùng opencv_modules.extract_text_blocks()
    (RapidOCR, indexed blocks + bbox thật) cho task này — RapidOCR đã bị RÚT khỏi flow thật (nghi
    OOM crash trên Render, xem orchestrator.py). Giờ dùng THẲNG classify["OCR_text"] (Vision tự
    OCR, 1 chuỗi text thô, không có bbox) — vẫn đủ cho task này vì đánh giá "đây có phải
    trademark/slogan nổi tiếng không" là bài toán NGÔN NGỮ thuần tuý, không cần bbox/không cần
    nhìn lại ảnh. Cái mất: text_trademark_flags giờ KHÔNG còn bbox để khoanh vùng trên ảnh gốc
    (_build_flagged_regions ở orchestrator.py), chỉ còn ảnh hưởng verdict/reasoning — chấp nhận
    được, đổi lấy việc bỏ hẳn model ONNX ra khỏi request path.

    Không có candidate/face_crop/ocr_text NÀO -> khỏi tốn 1 lần gọi LLM, trả rỗng luôn.
    """
    candidates = candidates or {}
    face_crops = face_crops or []
    ocr_text = ocr_text or ""
    has_candidates = any(candidates.get(k) for k in ("logos", "characters", "celebrities", "fonts", "artworks"))
    if not has_candidates and not face_crops and not ocr_text.strip():
        return {"verifications": [], "face_identifications": [], "text_trademark_flags": []}

    system_prompt, user_prompt = _build_agent2_prompt(candidates, len(face_crops), ocr_text)

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
        if not name or category not in ("logo", "character", "celebrity", "font", "artwork"):
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
        clean_text_flags.append({
            # "block_indexes" giữ rỗng cố định — không còn nguồn bbox (RapidOCR đã rút khỏi
            # flow, xem ghi chú run_agent2_verify_candidates ở trên). Giữ key để khớp shape
            # schemas.TextTrademarkFlag (default_factory=list), KHÔNG xoá field khỏi contract.
            "block_indexes": [],
            "phrase": phrase,
            "suspicion": suspicion,
            "reasoning": str(item.get("reasoning", "")),
        })

    return {"verifications": clean_verifications, "face_identifications": clean_faces, "text_trademark_flags": clean_text_flags}


# =====================================================================
# NHÓM C — TỔNG HỢP + ĐỊNH VỊ (1 LLM call)
# ⚠️ (2026-08-22) KHÔNG còn được orchestrator.py gọi trực tiếp nữa — đã GỘP với Agent 3 thành
# run_synthesis_and_reasoning() (xem bên dưới, sau khối Agent 3) để cắt 1 round-trip LLM tuần
# tự khỏi critical path (đo thật: pipeline 1 design đang mất 40-50s, phần lớn do 4 lần gọi LLM
# nối tiếp nhau). Giữ NGUYÊN 2 hàm _build_group_c_prompt/run_group_c_synthesis ở đây — KHÔNG
# xoá — để dễ tách trở lại nếu cần, và để hàm run_synthesis_and_reasoning() bên dưới có thể đối
# chiếu logic gốc khi cần sửa sau này.
# =====================================================================

def _build_group_c_prompt(evidence_bundle: dict, pdf_text_blocks: "list | None") -> tuple[str, str]:
    bbox_note = (
        "This design comes from a digital-native PDF — real pixel bounding boxes are provided "
        "below for text elements; use them directly instead of estimating a grid position for text."
        if pdf_text_blocks else
        "Describe WHERE each issue appears using a 3x3 grid, written in Vietnamese (e.g. "
        "\"góc trên-trái\"/\"trên-giữa\"/\"góc trên-phải\"/\"giữa-trái\"/\"chính giữa\"/\"giữa-phải\"/"
        "\"góc dưới-trái\"/\"dưới-giữa\"/\"góc dưới-phải\") — do NOT attempt precise pixel "
        "coordinates, vision models are not reliable at that."
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
- OK: cite as "đối chiếu với cơ sở dữ liệu tham chiếu đã biên soạn sẵn (cập nhật lần cuối {{date}})".
- OK to cite a specific registration number ONLY if it is present in the evidence bundle above (i.e. came from a real lookup).
- NEVER invent/hallucinate a registration or case number that is not in the evidence bundle.

TASK: for each non-empty evidence item, write one positioning_note: {{"category", "location_description", "citation"}}. Then write a short neutral "summary".

🌐 OUTPUT LANGUAGE: write "location_description", "citation", and "summary" in professional,
standard commercial Vietnamese (tiếng Việt chuẩn thương mại — clear, formal business tone). Keep
"category" EXACTLY as it appears as a key in the evidence bundle above (English, e.g.
"logo_similarity") — do NOT translate it, downstream Python code matches on this exact string.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, exact keys only.

REQUIRED JSON SHAPE:
{{
  "positioning_notes": [{{"category": "logo_similarity", "location_description": "góc trên-giữa thiết kế", "citation": "đối chiếu với cơ sở dữ liệu tham chiếu đã biên soạn sẵn"}}],
  "summary": "tóm tắt trung lập, ngắn gọn về toàn bộ bằng chứng phát hiện được"
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
# ⚠️ (2026-08-22) KHÔNG còn được orchestrator.py gọi trực tiếp nữa — xem ghi chú ở khối NHÓM C
# phía trên + run_synthesis_and_reasoning() bên dưới. Giữ NGUYÊN 2 hàm dưới đây, không xoá.
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
2. `fix_suggestions`: if evidence is non-empty, one entry PER violation category, each with a concrete, actionable fix (e.g. "Thay logo Nike bằng icon tự thiết kế riêng"). If evidence is empty (fully SAFE), return an empty list.

🌐 OUTPUT LANGUAGE: write "reasoning" and every "suggestion" in professional, standard commercial
Vietnamese (tiếng Việt chuẩn thương mại — clear, formal business tone, no slang). Keep "violation"
EXACTLY as the category key it corresponds to in the evidence above (English, e.g.
"logo_similarity") — do NOT translate it, downstream code/UI matches on this exact string.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, exact keys only.

REQUIRED JSON SHAPE:
{{
  "reasoning": "đoạn giải thích lý do ra verdict, viết bằng tiếng Việt",
  "fix_suggestions": [{{"violation": "logo_similarity", "suggestion": "cách sửa cụ thể, làm được ngay, viết bằng tiếng Việt"}}]
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
# NHÓM C + AGENT 3 GỘP LÀM 1 (2026-08-22) — tối ưu latency
# =====================================================================
# Lý do gộp: đo thật pipeline 1 design đang mất 40-50s, phần lớn từ 4 lần gọi LLM NỐI TIẾP nhau
# (Agent 1 -> [Agent 2 + nhánh song song] -> Nhóm C -> Agent 3). Nhóm C (viết positioning_notes)
# và Agent 3 (viết reasoning/fix_suggestions) có input CHỒNG LẤN gần hoàn toàn (evidence bundle,
# black_box_result) và Agent 3 TRƯỚC ĐÂY chỉ dùng output Nhóm C làm CONTEXT ĐỌC (không có phụ
# thuộc 2 chiều nào) -> gộp an toàn thành 1 call, cắt hẳn 1 round-trip tuần tự khỏi critical
# path (~8-15s/design tuỳ độ dài phản hồi).
#
# GIỮ NGUYÊN 100% logic/quy tắc của cả 2 hàm gốc — citation rule, positioning rule (grid 3x3
# tiếng Việt hoặc bbox PDF thật), "verdict đã quyết định sẵn bởi Python, LLM chỉ giải thích
# KHÔNG được tự đổi" (CLAUDE.md mục 10), output language tiếng Việt cho field prose/giữ nguyên
# category-key tiếng Anh. Output SHAPE giữ NGUYÊN — orchestrator.py/schemas.py KHÔNG cần đổi gì,
# chỉ đổi ĐIỂM GỌI (1 hàm thay vì 2 hàm tuần tự).
#
# Khác biệt DUY NHẤT so với trước: phần "positioning" giờ CŨNG thấy được ảnh gốc (Nhóm C cũ là
# text-only, không có ảnh) vì dùng chung 1 message với phần Agent 3 (vốn cần ảnh) — CHỈ có thể
# giúp positioning_notes chính xác hơn (nhìn ảnh thật thay vì chỉ đọc lại text evidence), không
# làm giảm chất lượng hay đổi ý nghĩa field nào.

def _build_synthesis_and_reasoning_prompt(
    evidence_bundle: dict, black_box_result: dict, pdf_text_blocks: "list | None",
    platform: "str | None", target_country: str,
) -> tuple[str, str]:
    bbox_note = (
        "This design comes from a digital-native PDF — real pixel bounding boxes are provided "
        "below for text elements; use them directly instead of estimating a grid position for text."
        if pdf_text_blocks else
        "Describe WHERE each issue appears using a 3x3 grid, written in Vietnamese (e.g. "
        "\"góc trên-trái\"/\"trên-giữa\"/\"góc trên-phải\"/\"giữa-trái\"/\"chính giữa\"/\"giữa-phải\"/"
        "\"góc dưới-trái\"/\"dưới-giữa\"/\"góc dưới-phải\") — do NOT attempt precise pixel "
        "coordinates, vision models are not reliable at that."
    )
    bbox_data = json.dumps(pdf_text_blocks, ensure_ascii=False) if pdf_text_blocks else "(not available — use grid description)"

    # (2026-08-22, MỚI) TASK C — thẩm định platform+country user ĐÃ CHỌN, giờ chuyển về ĐÂY
    # (từ run_agent4_market_suggestion cũ) vì CHỈ ở đây mới có verdict/evidence thật để trả lời
    # trung thực — xem ghi chú đầy đủ trong run_agent4_market_suggestion(). Chỉ hỏi khi platform
    # thật sự được truyền vào.
    platform_clean = (platform or "").lower().strip()
    country_clean = (target_country or "US").lower().strip()
    task_c = ""
    task_c_json = ""
    if platform_clean:
        selected_policy = load_compliance_policy_context(platform_clean, country_clean) or "(no local policy snapshot on file for this market yet)"
        task_c = f"""

TASK C — SELECTED PLATFORM SUITABILITY: the user has chosen to list this design on
platform="{platform_clean}", country="{country_clean.upper()}". Its policy (for reference):
[{platform_clean.upper()}, {country_clean.upper()}]
{selected_policy}

Given the FINAL VERDICT and its triggering evidence above, decide:
- `selected_platform_suitable` (true/false): is THIS specific platform+country combo actually
  suitable to list this design AS-IS?
- `selected_platform_rationale`: explain why, in 1-2 sentences.

🚨 BE DIRECT, do not hedge to be polite:
- If the verdict is BLOCKED because of a clear, unambiguous real IP element (an exact/near-exact
  real logo, a real character, a real celebrity's likeness/name, a real trademarked phrase, a
  reproduction of real copyrighted artwork) — say `false` PLAINLY, and state that this is a
  content problem, not a platform-choice problem: this exact design would likely be rejected on
  ANY of the four platforms (Etsy/Amazon/TikTok Shop/Shopify), not just this one — the fix is to
  change the design (see fix_suggestions), not to switch platforms.
- If the verdict is RISKY, weigh the SPECIFIC platform's own policy strictness above — `false` is
  still the right answer if that platform is known to be strict about this category, `true` with
  a caveat is fine if the risk is genuinely minor for that platform.
- If the verdict is SAFE, `selected_platform_suitable` is `true` unless the platform's own policy
  above raises a real, specific concern beyond the compliance check itself.
- This question is INDEPENDENT from what you'd recommend as the "best" platform elsewhere in the
  system — the user did not ask "what's best", they asked "is what I picked okay". Answer THAT
  question honestly, even if the honest answer is "no"."""
        task_c_json = ', "selected_platform_suitable": true, "selected_platform_rationale": "lý do ngắn gọn, thẳng thắn, viết bằng tiếng Việt"'

    system_prompt = f"""You are a Senior Compliance Advisor for a Print-on-Demand IP compliance system,
doing related tasks in ONE pass over the same evidence — all grounded in a FINAL VERDICT already
decided by deterministic Python code downstream, NOT by you.

📌 EVIDENCE BUNDLE (from Agent 2 vision + OpenCV modules + trademark text resolver):
{json.dumps(evidence_bundle, ensure_ascii=False)}

📌 FINAL VERDICT (already decided by deterministic code, do NOT change it, only explain it): {black_box_result.get("final_verdict")}
📌 EVIDENCE THAT TRIGGERED THIS VERDICT (all non-SAFE categories): {json.dumps(black_box_result.get("evidence", {}), ensure_ascii=False)}

📌 POSITIONING RULE: {bbox_note}
📌 PDF TEXT BLOCKS WITH REAL BBOX (if available): {bbox_data}

🚨 CITATION RULE (mandatory):
- OK: cite as "đối chiếu với cơ sở dữ liệu tham chiếu đã biên soạn sẵn (cập nhật lần cuối {{date}})".
- OK to cite a specific registration number ONLY if it is present in the evidence bundle above (i.e. came from a real lookup).
- NEVER invent/hallucinate a registration or case number that is not in the evidence bundle.

TASK A — POSITIONING: for each non-empty item in the EVIDENCE BUNDLE above, write one
positioning_note: {{"category", "location_description", "citation"}}. Then write a short neutral
"summary" of all evidence found.

TASK B — REASONING + FIX: using the FINAL VERDICT and its triggering evidence above, write:
1. `reasoning`: a clear paragraph explaining WHY this verdict was reached, referencing the evidence.
2. `fix_suggestions`: if the triggering evidence is non-empty, one entry PER violation category,
   each with a concrete, actionable fix (e.g. "Thay logo Nike bằng icon tự thiết kế riêng"). If
   empty (fully SAFE), return an empty list.{task_c}

🌐 OUTPUT LANGUAGE: write "location_description", "citation", "summary", "reasoning",
"selected_platform_rationale", and every "suggestion" in professional, standard commercial
Vietnamese (tiếng Việt chuẩn thương mại — clear, formal business tone, no slang). Keep "category"
(Task A) and "violation" (Task B) EXACTLY as the category key they correspond to in the evidence
above (English, e.g. "logo_similarity") — do NOT translate them, downstream code/UI matches on
this exact string.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, exact keys only.

REQUIRED JSON SHAPE:
{{
  "positioning_notes": [{{"category": "logo_similarity", "location_description": "góc trên-giữa thiết kế", "citation": "đối chiếu với cơ sở dữ liệu tham chiếu đã biên soạn sẵn"}}],
  "summary": "tóm tắt trung lập, ngắn gọn về toàn bộ bằng chứng phát hiện được",
  "reasoning": "đoạn giải thích lý do ra verdict, viết bằng tiếng Việt",
  "fix_suggestions": [{{"violation": "logo_similarity", "suggestion": "cách sửa cụ thể, làm được ngay, viết bằng tiếng Việt"}}]{task_c_json}
}}"""
    user_prompt = "Complete the task(s) above — positioning synthesis, reasoning/fix suggestions, and (if asked) selected-platform suitability — based on the design image and the evidence/verdict above."
    return system_prompt, user_prompt


def run_synthesis_and_reasoning(
    image_base64: "str | list[str] | None",
    evidence_bundle: dict,
    black_box_result: dict,
    pdf_text_blocks: "list | None" = None,
    platform: "str | None" = None,
    target_country: str = "US",
) -> dict:
    """Điểm vào MỚI orchestrator.py gọi thay cho run_group_c_synthesis() + run_agent3_reasoning()
    tuần tự — xem ghi chú khối trên. Output shape GIỮ NGUYÊN 4 field gốc, CỘNG THÊM (2026-08-22)
    selected_platform_suitable/selected_platform_rationale — chuyển từ run_agent4_market_suggestion()
    sang đây vì đây là nơi DUY NHẤT đã biết verdict/evidence thật để thẩm định trung thực."""
    system_prompt, user_prompt = _build_synthesis_and_reasoning_prompt(
        evidence_bundle, black_box_result, pdf_text_blocks, platform, target_country
    )
    raw = _call_llm_json(system_prompt, user_prompt, image_base64=image_base64, temperature=0.25)

    notes = raw.get("positioning_notes") if isinstance(raw.get("positioning_notes"), list) else []
    clean_notes = [
        {"category": str(n.get("category", "")), "location_description": str(n.get("location_description", "")),
         "citation": str(n.get("citation", ""))}
        for n in notes if isinstance(n, dict)
    ]
    fixes = raw.get("fix_suggestions") if isinstance(raw.get("fix_suggestions"), list) else []
    clean_fixes = [
        {"violation": str(f.get("violation", "")), "suggestion": str(f.get("suggestion", ""))}
        for f in fixes if isinstance(f, dict)
    ]
    result = {
        "positioning_notes": clean_notes,
        "summary": str(raw.get("summary", "")),
        "reasoning": str(raw.get("reasoning", "")),
        "fix_suggestions": clean_fixes,
        "selected_platform_suitable": None,
        "selected_platform_rationale": "",
    }
    if (platform or "").strip():
        suitable = raw.get("selected_platform_suitable")
        result["selected_platform_suitable"] = bool(suitable) if isinstance(suitable, bool) else None
        result["selected_platform_rationale"] = str(raw.get("selected_platform_rationale", ""))
    return result


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

    ⚠️ (2026-08-22, THIẾT KẾ LẠI) selected_platform_suitable/selected_platform_rationale ĐÃ RỜI
    khỏi hàm này — CHUYỂN sang run_synthesis_and_reasoning() (chạy SAU black box). Lý do: Agent 4
    chạy SONG SONG cùng Agent 2/OpenCV/trademark (TRƯỚC khi verdict được quyết định), nên KHÔNG
    THỂ biết design có thật sự vi phạm hay không khi trả lời câu "platform user chọn có phù hợp
    không" — phát hiện thật qua rà file mẫu BGK (design_samples_template.xlsx): phần lớn test
    case là sao chép TRỰC TIẾP tour poster/album cover/logo thật (BLOCKED chắc chắn) nhưng nếu
    hỏi câu thẩm định platform ở ĐÂY, Agent 4 mù verdict nên dễ trả lời chung chung/né tránh thay
    vì thẳng thắn "KHÔNG phù hợp — vì đây là bản sao logo/ảnh thật, sẽ bị từ chối ở BẤT KỲ
    platform nào, không phải vấn đề chọn sai platform". Giờ hàm này CHỈ còn làm ĐÚNG 1 việc: gợi
    ý ĐỘC LẬP (top_country_suggestion/top_platform_suggestion/rationale) dựa trên niche/style —
    không thẩm định platform user đã chọn nữa.
    """
    country_clean = (target_country or "US").lower().strip()
    platform_clean = (platform or "").lower().strip()
    platforms = ["etsy", "amazon", "tiktok", "shopify"]
    policy_blocks = "\n\n".join(
        f"[{p.upper()}]\n{load_compliance_policy_context(p, country_clean) or '(no local policy snapshot on file for this market yet)'}"
        for p in platforms
    )
    trend_block = load_trend_context(country_clean) or "(no local trend snapshot on file for this market yet)"

    # (2026-08-22) Tiêu chí phân biệt 4 platform — thêm vào để chống thiên hướng LLM cứ mặc
    # định gợi ý Etsy (bias huấn luyện phổ biến: "POD" ~ "Etsy" trong dữ liệu training, bất kể
    # niche thật sự phù hợp platform nào hơn). Cho model 1 bộ tiêu chí CỤ THỂ để tự so sánh thay
    # vì chỉ đoán theo pattern quen thuộc — xem PLATFORM_FIT_CRITERIA + câu cấm mặc định bên dưới.
    platform_fit_criteria = """
📌 PLATFORM FIT CRITERIA (use these to reason, do NOT just default to the platform most stereotypically associated with "print-on-demand"):
- ETSY: best for handmade-look, vintage/retro, niche-hobby, whimsical/artistic designs aimed at gift-buyers seeking something unique. Lower volume, higher price tolerance, curated/aesthetic-driven discovery.
- AMAZON MERCH ON DEMAND: best for broad mass-market, evergreen keyword-driven designs (profession/hobby/holiday sayings) that buyers find via search rather than browsing. Highest volume potential, but the strictest and most aggressive automated IP/trademark enforcement of the four.
- TIKTOK SHOP: best for trend-driven, meme/pop-culture-adjacent, youth-skewing designs riding a short, fast-moving trend cycle. Highest reach for viral content, but also highest risk of unlicensed meme/character IP.
- SHOPIFY: best when the seller wants to build their OWN brand/store rather than rely on marketplace discovery — requires the seller to drive their own traffic (ads/social/influencers). Best fit for niches with strong repeat-purchase or brand-building potential, not a one-off marketplace impulse buy.
Weigh the ACTUAL niche/style described below against these four profiles and pick whichever is the genuinely strongest fit — do not default to Etsy just because it is the platform most commonly discussed for POD sellers in general.
"""

    country_reasoning_note = """
📌 COUNTRY REASONING: the policy/trend snapshots injected above are only the ones we currently have
on file for the requested country — that is a data-coverage limitation, NOT evidence that other
countries are worse markets. When recommending `top_country_suggestion`, feel free to name a
different country than the one requested if it is genuinely a stronger commercial fit, drawing on
your own general e-commerce/market knowledge for that reasoning. Just be transparent in `rationale`
about which parts are grounded in the injected policy/trend snapshot above (only available for the
requested country right now) versus your own general knowledge of other markets — do not imply a
country has verified local policy data when it does not.
"""

    selected_note = (
        f'\n📌 FOR CONTEXT ONLY (NOT a question to answer here — a separate, verdict-aware check '
        f'elsewhere handles "is the user\'s chosen platform suitable"): the user has already '
        f'selected platform="{platform_clean}", country="{country_clean.upper()}" for this design. '
        f'Feel free to compare against it in your rationale if relevant, but you are NOT being asked '
        f'to judge it here.\n'
        if platform_clean else ""
    )

    system_prompt = f"""You are a Market/Platform Advisor for Print-on-Demand sellers, specializing in
IP compliance risk per platform.
{selected_note}
📌 TARGET COUNTRY REQUESTED: {country_clean.upper()}
📌 NICHE: {niche} | STYLE: {style}
📌 PLATFORM IP POLICIES (for {country_clean.upper()}):
{policy_blocks}
📌 MARKET TREND CONTEXT (for {country_clean.upper()}):
{trend_block}
{platform_fit_criteria}{country_reasoning_note}
TASK:
1. `top_country_suggestion`/`top_platform_suggestion`: your OWN independent recommendation of the
   single best country+platform to launch this niche/style on (commercial fit + IP-compliance
   risk) — this does NOT need to match what the user already selected, if any.
2. `rationale`: short rationale for #1.

If policy/trend context above is marked as missing, say so honestly instead of inventing details.

🌐 OUTPUT LANGUAGE: write "rationale" in professional, standard commercial Vietnamese (tiếng Việt
chuẩn thương mại — clear, formal business tone, no slang). Keep "top_country_suggestion" as a
plain 2-letter ISO country code and "top_platform_suggestion" as the platform's identifier
(etsy/amazon/tiktok/shopify) — do NOT translate either of those two.

🚨 OUTPUT RULES: ONE valid JSON object only, no markdown fences, exact keys only. Base your
answer on the ACTUAL context above — do NOT copy the example values below verbatim, they are
placeholders only.

REQUIRED JSON SHAPE (keys only, fill in real values from the context above):
{{"top_country_suggestion": "<2-letter country code>", "top_platform_suggestion": "<platform name>", "rationale": "lý do ngắn gọn, viết bằng tiếng Việt, có trích dẫn policy/trend context ở trên, hoặc nêu rõ nếu thiếu data"}}"""
    user_prompt = f"Recommend the best country/platform for a '{niche}' niche, '{style}' style design targeting {country_clean.upper()}."
    raw = _call_llm_json(system_prompt, user_prompt, temperature=0.4)
    return {
        "top_country_suggestion": str(raw.get("top_country_suggestion", "")),
        "top_platform_suggestion": str(raw.get("top_platform_suggestion", "")),
        "rationale": str(raw.get("rationale", "")),
    }
