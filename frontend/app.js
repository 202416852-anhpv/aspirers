// BUP-02 Design Compliance Checker — frontend chat-style UI, vanilla JS, không build step.
// Contract request/response khớp đúng compliance_checker/schemas.py + main.py (backend).

const STORAGE_KEY_BACKEND_URL = "bup02_backend_url";

let currentMode = "single"; // "single" | "batch"
let attachedFile = null; // File — cho mode single (ảnh/PDF/PSD)
let attachedBatchFile = null; // File — cho mode batch (CSV/XLSX)
let sessionCounter = 0;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getBackendUrl() {
  const val = document.getElementById("backend-url").value.trim().replace(/\/+$/, "");
  return val || "http://localhost:8000";
}

function getCommonFields() {
  return {
    platform: document.getElementById("platform").value || undefined,
    target_country: document.getElementById("target-country").value.trim() || "US",
  };
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function looksLikeUrl(str) {
  return /^https?:\/\//i.test((str || "").trim());
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  const saved = localStorage.getItem(STORAGE_KEY_BACKEND_URL);
  if (saved) document.getElementById("backend-url").value = saved;
  document.getElementById("backend-url").addEventListener("change", (e) => {
    localStorage.setItem(STORAGE_KEY_BACKEND_URL, e.target.value.trim());
  });

  document.getElementById("platform").addEventListener("change", updateTopbarBadges);
  document.getElementById("target-country").addEventListener("change", updateTopbarBadges);
  updateTopbarBadges();

  document.getElementById("sidebar-toggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("collapsed");
  });

  document.getElementById("settings-btn").addEventListener("click", () => toggleSettings(true));
  document.getElementById("settings-close-btn").addEventListener("click", () => toggleSettings(false));
  document.getElementById("settings-overlay").addEventListener("click", (e) => {
    if (e.target.id === "settings-overlay") toggleSettings(false);
  });
  document.getElementById("health-check-btn").addEventListener("click", checkHealth);

  document.getElementById("new-check-btn").addEventListener("click", resetComposer);

  document.querySelectorAll(".mode-tab").forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  });

  document.getElementById("attach-btn").addEventListener("click", () => {
    if (currentMode === "single") document.getElementById("file-input").click();
    else document.getElementById("batch-file-input").click();
  });
  document.getElementById("file-input").addEventListener("change", (e) => {
    if (e.target.files.length) setAttachedFile(e.target.files[0]);
  });
  document.getElementById("batch-file-input").addEventListener("change", (e) => {
    if (e.target.files.length) setAttachedBatchFile(e.target.files[0]);
  });

  document.getElementById("send-btn").addEventListener("click", handleSend);
  document.getElementById("composer-text").addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleSend();
  });

  document.querySelectorAll(".suggestion-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const type = chip.dataset.suggest;
      if (type === "upload") {
        setMode("single");
        document.getElementById("file-input").click();
      } else if (type === "link") {
        setMode("single");
        document.getElementById("composer-text").focus();
      } else if (type === "batch") {
        setMode("batch");
        document.getElementById("batch-file-input").click();
      }
    });
  });

  checkHealth();
  renderComposerChips();
});

function toggleSettings(open) {
  document.getElementById("settings-overlay").hidden = !open;
}

function updateTopbarBadges() {
  const platform = document.getElementById("platform").value;
  const country = document.getElementById("target-country").value.trim() || "US";
  document.getElementById("topbar-platform-badge").textContent = `platform: ${platform || "—"}`;
  document.getElementById("topbar-country-badge").textContent = country;
}

function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".mode-tab").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  const textInput = document.getElementById("composer-text");
  if (mode === "batch") {
    textInput.hidden = true;
    document.getElementById("composer-hint").textContent = "Upload file CSV/XLSX (cột file_path/url/design) để kiểm tra hàng loạt.";
  } else {
    textInput.hidden = false;
    document.getElementById("composer-hint").textContent = "Đúng 1 trong 2: đính kèm file HOẶC dán link. Mỗi lượt gửi tốn 1 lần gọi API thật.";
  }
  renderComposerChips();
  updateComposerPlaceholder();
}

function updateComposerPlaceholder() {
  const textInput = document.getElementById("composer-text");
  if (attachedFile) {
    textInput.placeholder = "Niche hint (tuỳ chọn) — vd: christmas_holiday";
  } else {
    textInput.placeholder = "Dán link Google Drive/Dropbox/URL ảnh, hoặc bấm 📎 để đính kèm file...";
  }
}

function setAttachedFile(file) {
  attachedFile = file;
  document.getElementById("composer-text").value = "";
  renderComposerChips();
  updateComposerPlaceholder();
}

function setAttachedBatchFile(file) {
  attachedBatchFile = file;
  renderComposerChips();
}

function renderComposerChips() {
  const container = document.getElementById("composer-chips");
  if (currentMode === "single" && attachedFile) {
    container.innerHTML = `<span class="composer-file-chip">📎 ${escapeHtml(attachedFile.name)} <button type="button" id="remove-file-chip">✕</button></span>`;
    document.getElementById("remove-file-chip").addEventListener("click", () => {
      attachedFile = null;
      document.getElementById("file-input").value = "";
      renderComposerChips();
      updateComposerPlaceholder();
    });
  } else if (currentMode === "batch" && attachedBatchFile) {
    container.innerHTML = `<span class="composer-file-chip">📊 ${escapeHtml(attachedBatchFile.name)} <button type="button" id="remove-batch-chip">✕</button></span>`;
    document.getElementById("remove-batch-chip").addEventListener("click", () => {
      attachedBatchFile = null;
      document.getElementById("batch-file-input").value = "";
      renderComposerChips();
    });
  } else {
    container.innerHTML = "";
  }
}

function resetComposer() {
  attachedFile = null;
  attachedBatchFile = null;
  document.getElementById("file-input").value = "";
  document.getElementById("batch-file-input").value = "";
  document.getElementById("composer-text").value = "";
  renderComposerChips();
  updateComposerPlaceholder();
  document.getElementById("composer-text").focus();
}

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------

async function checkHealth() {
  const dot = document.getElementById("health-dot");
  const text = document.getElementById("health-text");
  dot.className = "health-dot status-unknown";
  text.textContent = "đang kiểm tra...";
  try {
    const res = await fetch(`${getBackendUrl()}/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    await res.json();
    dot.className = "health-dot status-ok";
    text.textContent = "Backend OK";
  } catch (err) {
    dot.className = "health-dot status-fail";
    text.textContent = "Không kết nối được";
  }
}

// ---------------------------------------------------------------------------
// Send handling
// ---------------------------------------------------------------------------

function handleSend() {
  if (currentMode === "single") runSingleCheck();
  else runBatchCheck();
}

function hideEmptyState() {
  const el = document.getElementById("empty-state");
  if (el) el.remove();
}

function scrollThreadToBottom() {
  const thread = document.getElementById("message-thread");
  thread.scrollTop = thread.scrollHeight;
}

function addUserMessage(html) {
  hideEmptyState();
  const thread = document.getElementById("message-thread");
  const row = document.createElement("div");
  row.className = "msg-row msg-user";
  row.innerHTML = `<div class="msg-avatar">🧑</div><div class="msg-bubble">${html}</div>`;
  thread.appendChild(row);
  scrollThreadToBottom();
}

function addAssistantMessage(html) {
  hideEmptyState();
  const thread = document.getElementById("message-thread");
  const row = document.createElement("div");
  row.className = "msg-row msg-assistant";
  row.innerHTML = `<div class="msg-avatar">🛡️</div><div class="msg-bubble">${html}</div>`;
  thread.appendChild(row);
  scrollThreadToBottom();
  return row.querySelector(".msg-bubble");
}

function addLoadingBubble(label) {
  return addAssistantMessage(`<span class="loading-dots"><span></span><span></span><span></span></span> ${escapeHtml(label)}`);
}

function addSessionItem(label, dotClass) {
  const list = document.getElementById("session-list");
  const empty = list.querySelector(".session-list-empty");
  if (empty) empty.remove();
  sessionCounter += 1;
  const id = `session-${sessionCounter}`;
  const item = document.createElement("div");
  item.className = "session-item";
  item.id = id;
  item.innerHTML = `<span class="session-verdict-dot ${dotClass}"></span><span class="session-label">${escapeHtml(label)}</span>`;
  item.addEventListener("click", () => {
    const target = document.getElementById(`anchor-${id}`);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  list.appendChild(item);
  return id;
}

// ---------------------------------------------------------------------------
// Single check
// ---------------------------------------------------------------------------

async function runSingleCheck() {
  const textVal = document.getElementById("composer-text").value.trim();
  const common = getCommonFields();
  const nicheHintSetting = document.getElementById("niche-hint").value.trim();

  if (!attachedFile && !textVal) {
    addAssistantMessage(`<span class="error-note">Chưa có gì để gửi — đính kèm file hoặc dán link trước.</span>`);
    return;
  }
  if (!attachedFile && !looksLikeUrl(textVal)) {
    addAssistantMessage(`<span class="error-note">Chưa đính kèm file, và văn bản nhập vào không phải link hợp lệ (phải bắt đầu bằng http/https).</span>`);
    return;
  }

  // Ảnh preview để vẽ overlay toạ độ (renderPositioningOverlay) — lấy TỪ CLIENT (object URL
  // của file vừa chọn, hoặc chính link vừa dán), backend không trả ảnh về. Tính NGAY ở đây
  // (không đọc lại attachedFile lúc render) vì resetComposer() ở finally phía dưới sẽ null nó.
  // PDF/PSD không preview được bằng <img> nên bỏ qua (giữ null, overlay tự ẩn nếu không có ảnh).
  const previewUrl = attachedFile
    ? (attachedFile.type && attachedFile.type.startsWith("image/") ? URL.createObjectURL(attachedFile) : null)
    : (looksLikeUrl(textVal) ? textVal : null);

  const sendBtn = document.getElementById("send-btn");
  sendBtn.disabled = true;

  const anchorId = `anchor-session-${sessionCounter + 1}`;
  const thread = document.getElementById("message-thread");
  hideEmptyState();
  const anchor = document.createElement("div");
  anchor.id = anchorId;
  thread.appendChild(anchor);

  if (attachedFile) {
    addUserMessage(`<span class="msg-file-chip">📎 ${escapeHtml(attachedFile.name)}</span>${textVal ? `<div>Niche hint: ${escapeHtml(textVal)}</div>` : ""}`);
  } else {
    addUserMessage(`🔗 ${escapeHtml(textVal)}`);
  }

  const loadingBubble = addLoadingBubble("Đang chạy Agent 1-4 (có thể mất vài chục giây)...");

  try {
    let res;
    if (attachedFile) {
      const form = new FormData();
      form.append("file", attachedFile);
      if (common.platform) form.append("platform", common.platform);
      form.append("target_country", common.target_country);
      const nicheHint = textVal || nicheHintSetting;
      if (nicheHint) form.append("niche_hint", nicheHint);
      res = await fetch(`${getBackendUrl()}/api/compliance/check-upload`, { method: "POST", body: form });
    } else {
      const body = { url: textVal, target_country: common.target_country };
      if (common.platform) body.platform = common.platform;
      if (nicheHintSetting) body.niche_hint = nicheHintSetting;
      res = await fetch(`${getBackendUrl()}/api/compliance/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    }

    const data = await res.json();
    if (!res.ok) {
      loadingBubble.innerHTML = `<span class="error-note">Lỗi ${res.status}: ${escapeHtml(data.detail || JSON.stringify(data))}</span>`;
      addSessionItem(attachedFile ? attachedFile.name : textVal, "dot-ERROR");
      return;
    }
    loadingBubble.innerHTML = renderResultCard(data, null, previewUrl);
    const sid = addSessionItem(attachedFile ? attachedFile.name : textVal, `dot-${data.final_verdict}`);
    anchor.id = `anchor-${sid}`;
    scrollThreadToBottom();
  } catch (err) {
    loadingBubble.innerHTML = `<span class="error-note">Lỗi kết nối tới backend (${escapeHtml(getBackendUrl())}): ${escapeHtml(err.message)}. Kiểm tra server đã chạy chưa.</span>`;
    addSessionItem("Lỗi kết nối", "dot-ERROR");
  } finally {
    sendBtn.disabled = false;
    resetComposer();
  }
}

// ---------------------------------------------------------------------------
// Batch check
// ---------------------------------------------------------------------------

let _lastCsvExport = null;
let _lastBatchData = null;

async function runBatchCheck() {
  if (!attachedBatchFile) {
    addAssistantMessage(`<span class="error-note">Chưa chọn file CSV/XLSX.</span>`);
    return;
  }
  const common = getCommonFields();
  const sendBtn = document.getElementById("send-btn");
  sendBtn.disabled = true;

  const thread = document.getElementById("message-thread");
  hideEmptyState();
  const anchorId = `anchor-session-${sessionCounter + 1}`;
  const anchor = document.createElement("div");
  anchor.id = anchorId;
  thread.appendChild(anchor);

  addUserMessage(`<span class="msg-file-chip">📊 ${escapeHtml(attachedBatchFile.name)}</span>`);
  const loadingBubble = addLoadingBubble("Đang chạy batch (mỗi dòng 1 lượt Agent 1-4)...");

  try {
    const form = new FormData();
    form.append("file", attachedBatchFile);
    if (common.platform) form.append("platform", common.platform);
    form.append("target_country", common.target_country);

    const res = await fetch(`${getBackendUrl()}/api/compliance/batch-csv`, { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      loadingBubble.innerHTML = `<span class="error-note">Lỗi ${res.status}: ${escapeHtml(data.detail || JSON.stringify(data))}</span>`;
      addSessionItem(attachedBatchFile.name, "dot-ERROR");
      return;
    }
    _lastCsvExport = data.csv_export || null;
    _lastBatchData = data;
    loadingBubble.innerHTML = renderBatchResult(data);
    attachBatchRowHandlers(data, loadingBubble);
    const sid = addSessionItem(`${attachedBatchFile.name} (${data.total} dòng)`, "dot-BATCH");
    anchor.id = `anchor-${sid}`;
    scrollThreadToBottom();
  } catch (err) {
    loadingBubble.innerHTML = `<span class="error-note">Lỗi kết nối tới backend: ${escapeHtml(err.message)}</span>`;
    addSessionItem("Lỗi kết nối", "dot-ERROR");
  } finally {
    sendBtn.disabled = false;
    resetComposer();
  }
}

function renderBatchResult(data) {
  const accuracyPill = data.verdict_accuracy !== null && data.verdict_accuracy !== undefined
    ? `<div class="summary-pill"><b>${data.verdict_accuracy}%</b>Verdict accuracy (${data.graded_count} dòng có đáp án mẫu)</div>`
    : "";

  const rows = data.rows
    .map(
      (r) => `
    <tr class="row-clickable" data-row-index="${r.row_index}">
      <td>${r.row_index}</td>
      <td>${escapeHtml(r.input_ref)}</td>
      <td>${r.status}</td>
      <td>${r.result ? verdictBadge(r.result.final_verdict) : "—"}</td>
      <td>${r.grading ? (r.grading.verdict_match ? "✅" : "❌") + " " + escapeHtml(r.grading.expected.expected_verdict || "") : "—"}</td>
      <td class="empty-note">${r.error ? escapeHtml(r.error) : ""}</td>
    </tr>`
    )
    .join("");

  return `
    <div class="summary-row">
      <div class="summary-pill"><b>${data.total}</b>Tổng số</div>
      <div class="summary-pill"><b style="color:var(--safe)">${data.safe_count}</b>SAFE</div>
      <div class="summary-pill"><b style="color:var(--risky)">${data.risky_count}</b>RISKY</div>
      <div class="summary-pill"><b style="color:var(--blocked)">${data.blocked_count}</b>BLOCKED</div>
      <div class="summary-pill"><b>${data.error_count}</b>Lỗi</div>
      ${accuracyPill}
    </div>
    <div class="batch-table-wrap">
      <table class="batch-table">
        <thead><tr><th>#</th><th>Input</th><th>TT</th><th>Verdict</th><th>Đáp án mẫu</th><th>Lỗi</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="empty-note">Bấm vào 1 dòng để xem chi tiết.</p>
    ${_lastCsvExport ? `<button class="download-btn" id="download-csv-btn">⬇ Tải CSV báo cáo</button>` : ""}
    <div id="batch-row-detail"></div>
  `;
}

function attachBatchRowHandlers(data, bubbleEl) {
  bubbleEl.querySelectorAll("tr.row-clickable").forEach((tr) => {
    tr.addEventListener("click", () => {
      const idx = Number(tr.dataset.rowIndex);
      const row = data.rows.find((r) => r.row_index === idx);
      const detail = bubbleEl.querySelector("#batch-row-detail");
      if (!row || !row.result) {
        detail.innerHTML = `<div class="error-note">Dòng #${idx}: ${escapeHtml(row?.error || "không có kết quả")}</div>`;
        return;
      }
      // input_ref của batch chỉ là URL/tên file — CHỈ dùng làm ảnh preview khi thật sự là link
      // http(s) (browser load được trực tiếp); file_path server-side không truy cập được từ FE.
      const previewUrl = row.input_ref && /^https?:\/\//i.test(row.input_ref) ? row.input_ref : null;
      detail.innerHTML = renderResultCard(row.result, row.grading, previewUrl);
    });
  });
  const dlBtn = bubbleEl.querySelector("#download-csv-btn");
  if (dlBtn) dlBtn.addEventListener("click", downloadCsvExport);
}

function downloadCsvExport() {
  if (!_lastCsvExport) return;
  const blob = new Blob([_lastCsvExport], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "bup02_batch_report.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Render 1 DesignComplianceResult — dùng chung cho single check + batch row detail
// ---------------------------------------------------------------------------

function verdictBadge(verdict) {
  return `<span class="verdict-badge verdict-${verdict}">${verdict}</span>`;
}

// Confidence (low/medium/high hoặc %) CHỈ dùng nội bộ cho black box (xem black_box.py) —
// KHÔNG hiện ra giao diện nữa (nhóm đã bỏ hướng OpenCV classify thật, số liệu confidence
// hiện tại không đủ đáng tin để show cho người dùng cuối). UI chỉ hiện nhãn đã classify.

// (2026-08-21) Agent 2 giờ verify lại từng candidate Agent 1 nêu (logo/character/celebrity) —
// buildVerificationMap tra cứu nhanh theo "category:tên viết thường" -> true/false/undefined
// (undefined = chưa verify được, vd Agent 2 lỗi — KHÔNG hiện badge gì, coi như trung lập).
function buildVerificationMap(verifications) {
  const map = {};
  (verifications || []).forEach((v) => {
    map[`${v.category}:${(v.name || "").trim().toLowerCase()}`] = v.present;
  });
  return map;
}

// category: "logo"|"character"|"celebrity" — khớp đúng field "category" trong verifications
// (backend/schemas.py::VerificationItem). Badge CHỈ có ✅/❌ — tuyệt đối không có số/%.
function renderChipList(items, nameKey, category, verificationMap) {
  if (!items || !items.length) return `<span class="empty-note">Không phát hiện</span>`;
  return `<div class="chip-list">${items
    .map((i) => {
      const key = `${category}:${(i[nameKey] || "").trim().toLowerCase()}`;
      const present = verificationMap ? verificationMap[key] : undefined;
      const badge =
        present === true ? ` <span class="verify-badge verify-yes" title="Agent 2 xác nhận có trong ảnh">✅</span>` :
        present === false ? ` <span class="verify-badge verify-no" title="Agent 2 kiểm tra lại: không thấy trong ảnh">❌</span>` :
        "";
      return `<span class="chip">${escapeHtml(i[nameKey])}${badge}</span>`;
    })
    .join("")}</div>`;
}

// Vẽ overlay toạ độ THẬT lên ảnh preview — thay cho mô tả grid 3x3 bằng lời:
//   - Khung xanh (bbox-text-zone): text_regions — TOÀN BỘ vùng có khả năng chứa chữ, phát
//     hiện bằng OpenCV (MSER, opencv_modules.detect_text_regions), tín hiệu hình học chung.
//   - Khung đỏ có nhãn (bbox-flagged): positioning_notes có bbox_norm — category CỤ THỂ đã
//     khớp được toạ độ thật (opencv_mser hoặc pdf_native), xem orchestrator._inject_text_region_bbox.
// previewUrl: ảnh gốc phía client (object URL của file vừa upload, hoặc chính link URL đã
// nhập) — backend KHÔNG trả ảnh về, tránh phình payload. Không có previewUrl hoặc không có
// dữ liệu toạ độ nào -> không render gì (giữ nguyên UI cũ, chỉ còn mô tả bằng lời ở dưới).
function renderPositioningOverlay(r, previewUrl) {
  const textZones = r.text_regions || [];
  const flaggedNotes = (r.positioning_notes || []).filter((n) => Array.isArray(n.bbox_norm) && n.bbox_norm.length === 4);
  if (!previewUrl || (!textZones.length && !flaggedNotes.length)) return "";

  const pct = (v) => `${(v * 100).toFixed(2)}%`;
  const zoneBoxes = textZones
    .map(
      (tr) => `<div class="bbox-box bbox-text-zone" style="left:${pct(tr.bbox_norm[0])}; top:${pct(tr.bbox_norm[1])}; width:${pct(tr.bbox_norm[2] - tr.bbox_norm[0])}; height:${pct(tr.bbox_norm[3] - tr.bbox_norm[1])};"></div>`
    )
    .join("");
  const flaggedBoxes = flaggedNotes
    .map(
      (n) => `<div class="bbox-box bbox-flagged" style="left:${pct(n.bbox_norm[0])}; top:${pct(n.bbox_norm[1])}; width:${pct(n.bbox_norm[2] - n.bbox_norm[0])}; height:${pct(n.bbox_norm[3] - n.bbox_norm[1])};"><span class="bbox-label">${escapeHtml(n.category)}</span></div>`
    )
    .join("");

  return `
    <div class="section-title">Định vị trực quan (toạ độ thật, OpenCV)</div>
    <div class="image-preview-wrap">
      <img src="${escapeHtml(previewUrl)}" class="preview-img" onerror="this.parentElement.style.display='none'" />
      ${zoneBoxes}
      ${flaggedBoxes}
    </div>
    <p class="empty-note">Khung xanh: vùng có khả năng chứa chữ (OpenCV tự động, mang tính tham khảo hình học — không đọc nội dung). Khung đỏ có nhãn: category vi phạm đã khớp được toạ độ thật.</p>
  `;
}

function renderResultCard(r, grading, previewUrl) {
  const verificationMap = buildVerificationMap(r.verifications);

  const warningsHtml = r.warnings && r.warnings.length
    ? `<div class="warnings-banner">⚠️ ${r.warnings.map(escapeHtml).join(" | ")}</div>`
    : "";

  const gradingHtml = grading
    ? `<div class="grading-banner ${grading.verdict_match ? "grading-match" : "grading-mismatch"}">
         ${grading.verdict_match ? "✅ Khớp đáp án mẫu" : "❌ Lệch đáp án mẫu"} — expected: ${escapeHtml(grading.expected.expected_verdict || "")}
       </div>`
    : "";

  const evidenceEntries = Object.entries(r.evidence || {});
  const evidenceHtml = evidenceEntries.length
    ? evidenceEntries
        .map(
          ([cat, ev]) => `
      <div class="evidence-item tag-${ev.tag}">
        <div class="evidence-cat">${escapeHtml(cat)} — ${verdictBadge(ev.tag)}</div>
        <div class="evidence-detail">${escapeHtml(ev.detail || "")}</div>
      </div>`
        )
        .join("")
    : `<p class="empty-note">Không có category nào bị flag — hoàn toàn SAFE.</p>`;

  const positioningHtml = (r.positioning_notes || [])
    .map(
      (p) => `<div class="positioning-item"><b>${escapeHtml(p.category)}</b> — ${escapeHtml(p.location_description)}
        ${p.bbox_norm ? `<span class="bbox-source-tag">📍 toạ độ thật (${escapeHtml(p.bbox_source || "")})</span>` : ""}
        <br /><span class="empty-note">${escapeHtml(p.citation)}</span></div>`
    )
    .join("") || `<p class="empty-note">Không có ghi chú định vị.</p>`;

  const fixHtml = (r.fix_suggestions || [])
    .map((f) => `<div class="fix-item"><span class="fix-violation">${escapeHtml(f.violation)}:</span> ${escapeHtml(f.suggestion)}</div>`)
    .join("") || `<p class="empty-note">Không có gợi ý sửa (verdict SAFE hoặc chưa có evidence).</p>`;

  const market = r.market_suggestion;
  // selected_platform_suitable: null/undefined nghĩa là user không chọn platform -> không có gì
  // để thẩm định, KHÔNG hiện khối này (khác với false, vẫn phải hiện rõ dù là tin xấu).
  const hasSelectedAssessment = market && market.selected_platform_suitable !== null && market.selected_platform_suitable !== undefined;
  const selectedPlatformHtml = hasSelectedAssessment
    ? `<div class="platform-suitability-banner ${market.selected_platform_suitable ? "platform-suitability-yes" : "platform-suitability-no"}">
         <b>${market.selected_platform_suitable ? "✅ Platform bạn chọn: phù hợp" : "⚠️ Platform bạn chọn: có rủi ro"}</b>
         <div style="margin-top:0.3rem">${escapeHtml(market.selected_platform_rationale || "")}</div>
       </div>`
    : "";
  const marketHtml = market
    ? `<div class="market-box">
         <div><b>Quốc gia đề xuất (độc lập):</b> ${escapeHtml(market.top_country_suggestion || "—")}</div>
         <div><b>Platform đề xuất (độc lập):</b> ${escapeHtml(market.top_platform_suggestion || "—")}</div>
         <div style="margin-top:0.4rem">${escapeHtml(market.rationale || "")}</div>
         ${selectedPlatformHtml}
       </div>`
    : `<p class="empty-note">Không có gợi ý thị trường (nhánh Agent 4 có thể đã lỗi).</p>`;

  return `
    ${gradingHtml}
    ${warningsHtml}
    <div class="result-header">
      ${verdictBadge(r.final_verdict)}
      <span class="confidence-note">Nguồn: ${escapeHtml(r.source_type)}</span>
    </div>

    <div class="meta-grid">
      <div><div class="meta-label">Niche</div>${escapeHtml(r.niche)}</div>
      <div><div class="meta-label">Style</div>${escapeHtml(r.style)}</div>
      <div><div class="meta-label">Motifs</div>${(r.motifs || []).map(escapeHtml).join(", ") || "—"}</div>
    </div>

    ${renderPositioningOverlay(r, previewUrl)}

    <div class="section-title">Logo nghi ngờ <span class="empty-note">(✅/❌ = Agent 2 đã kiểm tra lại ảnh)</span></div>
    ${renderChipList(r.suspected_logos, "brand_name", "logo", verificationMap)}

    <div class="section-title">Nhân vật nghi ngờ <span class="empty-note">(✅/❌ = Agent 2 đã kiểm tra lại ảnh)</span></div>
    ${renderChipList(r.suspected_characters, "name", "character", verificationMap)}

    <div class="section-title">Người nổi tiếng nghi ngờ <span class="empty-note">(✅/❌ = Agent 2 đã kiểm tra lại ảnh)</span></div>
    ${renderChipList(r.suspected_celebrities, "name", "celebrity", verificationMap)}

    <div class="section-title">OCR text</div>
    <div class="ocr-box">${escapeHtml(r.OCR_text) || "(không có chữ)"}</div>

    <div class="section-title">Evidence (category vi phạm)</div>
    ${evidenceHtml}

    <div class="section-title">Định vị / citation</div>
    ${positioningHtml}

    <div class="section-title">Reasoning</div>
    <div class="reasoning-box">${escapeHtml(r.reasoning) || "(trống)"}</div>

    <div class="section-title">Gợi ý sửa</div>
    ${fixHtml}

    <div class="section-title">Gợi ý thị trường</div>
    ${marketHtml}

    <div class="font-disclaimer">${escapeHtml(r.font_disclaimer)}</div>
  `;
}
