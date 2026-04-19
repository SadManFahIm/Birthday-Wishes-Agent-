/**
 * content.js
 * ──────────
 * Birthday Wishes Agent — LinkedIn Content Script
 *
 * Runs on every LinkedIn page.
 * When a profile page is detected:
 *   1. Extracts the contact's name, job title, company
 *   2. Sends it to the local FastAPI backend
 *   3. Receives contact data (notes, wish history, health score)
 *   4. Injects a sidebar panel into the LinkedIn page
 */

const API_BASE = "http://localhost:8000";
const PANEL_ID = "bwa-sidebar-panel";

// ── PROFILE DETECTION ────────────────────────
function isProfilePage() {
  return location.href.includes("/in/") || location.href.includes("/pub/");
}

function extractProfileData() {
  const name = (
    document.querySelector("h1.text-heading-xlarge")?.innerText ||
    document.querySelector(".pv-top-card--list h1")?.innerText ||
    document.querySelector("h1")?.innerText ||
    ""
  ).trim();

  const jobTitle = (
    document.querySelector(".text-body-medium.break-words")?.innerText ||
    document.querySelector(".pv-top-card--experience-list-item")?.innerText ||
    ""
  ).trim();

  const company = (
    document.querySelector(
      '.pv-top-card--experience-list-item span[aria-hidden="true"]',
    )?.innerText || ""
  ).trim();

  const location = (
    document.querySelector(".text-body-small.inline.t-black--light.break-words")
      ?.innerText || ""
  ).trim();

  const profileUrl = location.href.split("?")[0];

  return { name, jobTitle, company, location, profileUrl };
}

// ── API CALLS ────────────────────────────────
async function getAuthToken() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["bwa_token"], (r) => resolve(r.bwa_token || ""));
  });
}

async function fetchContactData(name) {
  if (!name) return null;
  const token = await getAuthToken();
  if (!token) return null;

  try {
    const [historyRes, notesRes, healthRes, memoryRes] = await Promise.all([
      fetch(`${API_BASE}/api/activity?limit=5`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${API_BASE}/api/contact/notes?name=${encodeURIComponent(name)}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${API_BASE}/api/contact/health?name=${encodeURIComponent(name)}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      fetch(`${API_BASE}/api/contact/memory?name=${encodeURIComponent(name)}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
    ]);

    const allActivity = historyRes.ok ? await historyRes.json() : [];
    const history = allActivity.filter((a) =>
      a.contact?.toLowerCase().includes(name.split(" ")[0].toLowerCase()),
    );
    const notes = notesRes.ok ? await notesRes.json() : [];
    const health = healthRes.ok ? await healthRes.json() : null;
    const memory = memoryRes.ok ? await memoryRes.json() : null;

    return { history, notes, health, memory };
  } catch (e) {
    return null;
  }
}

async function saveNote(name, noteText, tags) {
  const token = await getAuthToken();
  if (!token) return false;
  try {
    const res = await fetch(`${API_BASE}/api/contact/notes`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ contact: name, note: noteText, tags }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ── SIDEBAR INJECTION ────────────────────────
function removeSidebar() {
  document.getElementById(PANEL_ID)?.remove();
}

function injectSidebar(profile, data) {
  removeSidebar();

  const panel = document.createElement("div");
  panel.id = PANEL_ID;

  const healthScore = data?.health?.health_score ?? null;
  const healthLevel = data?.health?.health_level ?? "Unknown";
  const healthEmoji =
    healthScore >= 75
      ? "🟢"
      : healthScore >= 50
        ? "🟡"
        : healthScore >= 25
          ? "🟠"
          : "🔴";

  const memory = data?.memory;
  const notes = data?.notes || [];
  const history = data?.history || [];
  const firstName = profile.name.split(" ")[0];

  const notesHTML =
    notes.length > 0
      ? notes
          .slice(0, 3)
          .map(
            (n) => `
        <div class="bwa-note-item">
          <div class="bwa-note-text">${escHtml(n.note || n)}</div>
          ${(n.tags || []).map((t) => `<span class="bwa-tag">#${escHtml(t)}</span>`).join("")}
        </div>
      `,
          )
          .join("")
      : '<p class="bwa-empty">No notes yet.</p>';

  const historyHTML =
    history.length > 0
      ? history
          .slice(0, 4)
          .map(
            (h) => `
        <div class="bwa-history-item">
          <span class="bwa-hist-icon">${h.task?.includes("Birthday") ? "🎂" : "💬"}</span>
          <div>
            <div class="bwa-hist-task">${escHtml(h.task || "")}</div>
            <div class="bwa-hist-date">${h.date || ""}</div>
          </div>
        </div>
      `,
          )
          .join("")
      : '<p class="bwa-empty">No wish history yet.</p>';

  const memoryHTML = memory
    ? `<div class="bwa-memory-box">
        ${memory.job_title ? `<div>💼 ${escHtml(memory.job_title)} @ ${escHtml(memory.company || "")}</div>` : ""}
        ${memory.life_event ? `<div>📌 ${escHtml(memory.life_event)}</div>` : ""}
        ${(memory.interests || []).length > 0 ? `<div>🎯 ${memory.interests.slice(0, 3).map(escHtml).join(", ")}</div>` : ""}
       </div>`
    : '<p class="bwa-empty">No memory saved yet.</p>';

  panel.innerHTML = `
    <div class="bwa-header">
      <div class="bwa-header-left">
        <span class="bwa-logo">🎂</span>
        <span class="bwa-title">Birthday Agent</span>
      </div>
      <button class="bwa-close" id="bwaClose">✕</button>
    </div>

    <div class="bwa-body">

      <!-- CONTACT INFO -->
      <div class="bwa-section">
        <div class="bwa-contact-name">${escHtml(profile.name || "Unknown")}</div>
        ${profile.jobTitle ? `<div class="bwa-contact-job">${escHtml(profile.jobTitle)}</div>` : ""}
        ${profile.company ? `<div class="bwa-contact-company">@ ${escHtml(profile.company)}</div>` : ""}
      </div>

      <!-- HEALTH SCORE -->
      ${
        healthScore !== null
          ? `
      <div class="bwa-section">
        <div class="bwa-section-title">💚 Relationship Health</div>
        <div class="bwa-health-row">
          <span class="bwa-health-emoji">${healthEmoji}</span>
          <div class="bwa-health-bar-wrap">
            <div class="bwa-health-bar" style="width:${healthScore}%"></div>
          </div>
          <span class="bwa-health-score">${healthScore}/100</span>
        </div>
        <div class="bwa-health-level">${healthLevel}</div>
      </div>
      `
          : ""
      }

      <!-- MEMORY -->
      <div class="bwa-section">
        <div class="bwa-section-title">🧠 Memory</div>
        ${memoryHTML}
      </div>

      <!-- WISH HISTORY -->
      <div class="bwa-section">
        <div class="bwa-section-title">🎂 Wish History (${history.length})</div>
        ${historyHTML}
      </div>

      <!-- NOTES -->
      <div class="bwa-section">
        <div class="bwa-section-title">📝 Notes (${notes.length})</div>
        ${notesHTML}
        <div class="bwa-add-note">
          <textarea id="bwaNoteInput" placeholder="Add a note about ${escHtml(firstName)}..." rows="2"></textarea>
          <input id="bwaTagInput" placeholder="Tags: e.g. work, personal" />
          <button id="bwaSaveNote" class="bwa-btn">Save Note</button>
          <div id="bwaNoteMsg" class="bwa-note-msg"></div>
        </div>
      </div>

    </div>
  `;

  document.body.appendChild(panel);

  // Close button
  document.getElementById("bwaClose").onclick = removeSidebar;

  // Save note
  document.getElementById("bwaSaveNote").onclick = async () => {
    const noteText = document.getElementById("bwaNoteInput").value.trim();
    const tagsRaw = document.getElementById("bwaTagInput").value.trim();
    const tags = tagsRaw ? tagsRaw.split(",").map((t) => t.trim()) : [];

    if (!noteText) return;

    const ok = await saveNote(profile.name, noteText, tags);
    const msg = document.getElementById("bwaNoteMsg");
    if (ok) {
      msg.textContent = "✅ Note saved!";
      msg.style.color = "#4CAF50";
      document.getElementById("bwaNoteInput").value = "";
      document.getElementById("bwaTagInput").value = "";
    } else {
      msg.textContent = "❌ Failed. Is the agent running?";
      msg.style.color = "#F44336";
    }
    setTimeout(() => {
      msg.textContent = "";
    }, 3000);
  };
}

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── MAIN FLOW ────────────────────────────────
let lastUrl = "";

async function run() {
  if (!isProfilePage()) return;
  if (location.href === lastUrl) return;
  lastUrl = location.href;

  // Wait for page to render
  await new Promise((r) => setTimeout(r, 1500));

  const profile = extractProfileData();
  if (!profile.name) return;

  // Inject loading state
  removeSidebar();
  const loadingPanel = document.createElement("div");
  loadingPanel.id = PANEL_ID;
  loadingPanel.innerHTML = `
    <div class="bwa-header">
      <div class="bwa-header-left">
        <span class="bwa-logo">🎂</span>
        <span class="bwa-title">Birthday Agent</span>
      </div>
      <button class="bwa-close" onclick="document.getElementById('${PANEL_ID}').remove()">✕</button>
    </div>
    <div class="bwa-body">
      <div style="text-align:center;padding:30px;color:#888;">
        <div style="font-size:1.5rem;margin-bottom:8px;">⏳</div>
        Loading ${escHtml(profile.name.split(" ")[0])}'s data...
      </div>
    </div>
  `;
  document.body.appendChild(loadingPanel);

  const data = await fetchContactData(profile.name);
  injectSidebar(profile, data || {});
}

// Watch for URL changes (LinkedIn is a SPA)
const observer = new MutationObserver(() => {
  if (location.href !== lastUrl) run();
});
observer.observe(document.body, { childList: true, subtree: true });

run();
