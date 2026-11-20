// AskSE frontend - plain JavaScript + Bootstrap 5

// ---------- fixed app messages (shown by the app, not the AI) ----------
const MSG_INVALID   = "Message must be 1 to 300 characters.";
const MSG_NOT_FOUND = "Sorry, I could not find this in the department FAQ. Please email helpdesk@se.example.edu or visit Room 210.";
const MSG_AI_DOWN   = "AI service unavailable. Check your connection or API key and try again.";
const MAX_CHARS = 300;
const CHAT_KEY = "askse_chat_history";
const STATS_KEY = "askse_stats";
const THEME_KEY = "askse_theme";
const SUGGESTIONS = [
  "What are the library timings?",
  "When do the university buses leave?",
  "What is the attendance requirement?",
  "How do I submit my FYP proposal?",
  "Fee kab tak jama karni hai?",
];
const CLIENT_TIMEOUT_MS = 35000; // backend gives up after 30 s; this is a safety net

const $ = (id) => document.getElementById(id);

// =====================================================================
// Tabs
// =====================================================================
function showTab(name) {
  document.querySelectorAll(".tab-section").forEach((s) => s.classList.add("d-none"));
  $("tab-" + name).classList.remove("d-none");
  document.querySelectorAll("#mainTabs .nav-link").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name)
  );
  if (name === "faqs") loadFaqs();
  if (name === "stats") loadFaqs().then(renderStats);
  if (name === "chat") $("chatInput").focus();
}
document.querySelectorAll("[data-tab]").forEach((el) =>
  el.addEventListener("click", (e) => { e.preventDefault(); showTab(el.dataset.tab); })
);

// =====================================================================
// Reusable confirmation modal (instead of window.confirm)
// =====================================================================
const confirmModal = new bootstrap.Modal($("confirmModal"));
let confirmAction = null;

function askConfirm(text, okLabel, onOk) {
  $("confirmText").textContent = text;
  $("confirmOk").textContent = okLabel;
  confirmAction = onOk;
  confirmModal.show();
}
$("confirmOk").addEventListener("click", () => {
  const action = confirmAction;
  confirmAction = null;
  confirmModal.hide();
  if (action) action();
});
$("confirmModal").addEventListener("hidden.bs.modal", () => { confirmAction = null; });

// =====================================================================
// Chat history (localStorage)
// =====================================================================
function loadHistory() {
  try { return JSON.parse(localStorage.getItem(CHAT_KEY)) || []; }
  catch { return []; }
}
function saveHistory(history) {
  try { localStorage.setItem(CHAT_KEY, JSON.stringify(history)); } catch { /* storage full/blocked */ }
}
let chatHistory = loadHistory();

function timeNow() {
  const d = new Date();
  let h = d.getHours();
  const ampm = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return String(h).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") + " " + ampm;
}

// msg = { role: "user" | "bot", text, refs?: ["FAQ-03"], kind?: "error", time }
function renderMessage(msg) {
  $("chatEmpty").classList.add("d-none");
  const row = document.createElement("div");
  row.className = "msg " + msg.role + (msg.kind === "error" ? " error" : "");

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = msg.text; // textContent = safe, no HTML injection

  if (msg.refs && msg.refs.length) {
    const ref = document.createElement("span");
    ref.className = "faq-ref";
    ref.textContent = " [" + msg.refs.join(", ") + "]";
    bubble.appendChild(ref);
  }

  const time = document.createElement("div");
  time.className = "time";
  time.textContent = msg.time;
  bubble.appendChild(time);

  // "Helpful / Not helpful" on every bot answer (not on "AI unavailable" errors)
  if (msg.role === "bot" && msg.kind !== "error") bubble.appendChild(feedbackButtons(msg));

  row.appendChild(bubble);
  $("chatBody").appendChild(row);
  scrollChat();
}

// msg.feedback is "up", "down" or undefined. It is saved with the message in localStorage.
function feedbackButtons(msg) {
  const box = document.createElement("div");
  box.className = "feedback";
  const options = [
    ["up", "Helpful", "bi-hand-thumbs-up", "success"],
    ["down", "Not helpful", "bi-hand-thumbs-down", "danger"],
  ];
  const buttons = options.map(([value, label, icon, color]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<i class="bi ${icon}"></i> `;
    b.append(label);
    b.addEventListener("click", () => {
      const old = msg.feedback;
      msg.feedback = old === value ? undefined : value;   // click again = undo
      changeFeedbackStats(old, msg.feedback);
      saveHistory(chatHistory);
      paint();
    });
    b.paint = () => {
      const on = msg.feedback === value;
      b.className = "btn " + (on ? "btn-" + color : "btn-outline-secondary");
      b.setAttribute("aria-pressed", on);
    };
    return b;
  });
  const paint = () => buttons.forEach((b) => b.paint());
  paint();
  box.append(...buttons);
  return box;
}

function addMessage(msg) {
  msg.time = timeNow();
  chatHistory.push(msg);
  saveHistory(chatHistory);
  renderMessage(msg);
}

function scrollChat() { $("chatBody").scrollTop = $("chatBody").scrollHeight; }

function showTyping() {
  const row = document.createElement("div");
  row.className = "msg bot";
  row.id = "typingRow";
  row.innerHTML = '<div class="bubble typing" aria-label="AskSE is typing"><span></span><span></span><span></span></div>';
  $("chatBody").appendChild(row);
  scrollChat();
}
function hideTyping() { const t = $("typingRow"); if (t) t.remove(); }

// restore saved chat on page load
chatHistory.forEach(renderMessage);

// =====================================================================
// Chat input, counter, validation, sending
// =====================================================================
const chatInput = $("chatInput");

function updateCounter() {
  const n = chatInput.value.length;
  $("charCounter").textContent = n + "/" + MAX_CHARS;
  $("charCounter").classList.toggle("text-danger", n > MAX_CHARS);
  $("charCounter").classList.toggle("text-muted", n <= MAX_CHARS);
  if ($("chatError").textContent && n <= MAX_CHARS && chatInput.value.trim()) $("chatError").textContent = "";
}
chatInput.addEventListener("input", updateCounter);

let waiting = false;

$("chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (waiting) return;

  const text = chatInput.value;
  if (text.trim().length === 0 || text.length > MAX_CHARS) {
    $("chatError").textContent = MSG_INVALID;   // not sent
    return;
  }
  $("chatError").textContent = "";

  addMessage({ role: "user", text: text.trim() });
  setWaiting(true);
  showTyping();

  let data = null;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), CLIENT_TIMEOUT_MS);
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    data = await res.json();
  } catch {
    data = { status: "error" }; // server down / network / timeout
  }

  hideTyping();
  setWaiting(false);

  stats.asked++;
  if (data.status === "found") {
    addMessage({ role: "bot", text: data.answer, refs: data.faq_ids });
    chatInput.value = "";          // clear only on success
    stats.answered++;
    data.faq_ids.forEach((id) => { stats.cited[id] = (stats.cited[id] || 0) + 1; });
  } else if (data.status === "not_found") {
    addMessage({ role: "bot", text: MSG_NOT_FOUND });
    chatInput.value = "";
    stats.notFound++;
  } else {
    addMessage({ role: "bot", text: MSG_AI_DOWN, kind: "error" });
    // keep the typed message in the input box so the user can retry
    stats.errors++;
  }
  saveStats();
  updateCounter();
  chatInput.focus();
});

function setWaiting(on) {
  waiting = on;
  $("sendBtn").disabled = on;
  chatInput.readOnly = on;
  document.querySelectorAll("#suggestions .btn").forEach((b) => (b.disabled = on));
}

// Suggested-question chips: click = put the question in the box and send it
SUGGESTIONS.forEach((q) => {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "btn btn-sm btn-outline-secondary";
  chip.textContent = q;
  chip.addEventListener("click", () => {
    if (waiting) return;
    chatInput.value = q;
    updateCounter();
    $("chatForm").requestSubmit();
  });
  $("suggestions").appendChild(chip);
});

$("clearChatBtn").addEventListener("click", () => {
  askConfirm("Clear all messages?", "Clear", () => {
    chatHistory = [];
    saveHistory(chatHistory);                       // only chat is removed, never FAQs
    $("chatBody").querySelectorAll(".msg").forEach((m) => m.remove());
    $("chatEmpty").classList.remove("d-none");
  });
});

// =====================================================================
// FAQ list
// =====================================================================
let categories = [];
let faqList = [];

async function loadFaqs() {
  const body = $("faqTableBody");
  try {
    const res = await fetch("/api/faqs");
    const data = await res.json();
    categories = data.categories;
    faqList = data.faqs;
    fillCategoryDropdown();
    body.innerHTML = "";
    data.faqs.forEach((f) => {
      const tr = document.createElement("tr");
      [["faq-id", f.id], ["", f.category], ["fw-semibold", f.question], ["", f.answer]].forEach(([cls, val]) => {
        const td = document.createElement("td");
        if (cls) td.className = cls;
        td.textContent = val;
        tr.appendChild(td);
      });
      tr.children[1].innerHTML = "";
      const badge = document.createElement("span");
      badge.className = "badge rounded-pill bg-body-tertiary text-body border";
      badge.textContent = f.category;
      tr.children[1].appendChild(badge);
      body.appendChild(tr);
    });
    $("faqCount").textContent = data.faqs.length + " FAQs";
  } catch {
    body.innerHTML = '<tr><td colspan="4" class="text-danger">Could not load FAQs.</td></tr>';
  }
}

function fillCategoryDropdown() {
  const sel = $("faqCategory");
  if (sel.options.length > 1) return;
  categories.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    sel.appendChild(opt);
  });
}

// =====================================================================
// Admin
// =====================================================================
let adminPin = null; // kept in memory only

$("pinForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pin = $("pinInput").value;
  try {
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });
    if (!res.ok) throw new Error("bad pin");
    adminPin = pin;
    $("pinError").textContent = "";
    $("pinInput").value = "";
    $("adminLogin").classList.add("d-none");
    $("adminPanel").classList.remove("d-none");
    loadFaqs(); // fills the category dropdown
  } catch {
    $("pinError").textContent = "Incorrect PIN";
  }
});

$("lockBtn").addEventListener("click", () => {
  adminPin = null;
  $("adminPanel").classList.add("d-none");
  $("adminLogin").classList.remove("d-none");
});

// live counters for the admin form
$("faqQuestion").addEventListener("input", () => { $("qCounter").textContent = $("faqQuestion").value.trim().length + "/150"; });
$("faqAnswer").addEventListener("input", () => { $("aCounter").textContent = $("faqAnswer").value.trim().length + "/400"; });

function setFieldError(inputId, errId, message) {
  $(inputId).classList.toggle("is-invalid", !!message);
  $(errId).textContent = message || "";
}

function validateFaqForm() {
  const cat = $("faqCategory").value;
  const q = $("faqQuestion").value.trim();
  const a = $("faqAnswer").value.trim();
  const errors = {};
  if (!categories.includes(cat)) errors.category = "Please choose a category.";
  if (q.length < 10 || q.length > 150) errors.question = "Question must be 10 to 150 characters.";
  if (a.length < 10 || a.length > 400) errors.answer = "Answer must be 10 to 400 characters.";
  return errors;
}

function showFaqErrors(errors) {
  setFieldError("faqCategory", "errCategory", errors.category);
  setFieldError("faqQuestion", "errQuestion", errors.question);
  setFieldError("faqAnswer", "errAnswer", errors.answer);
}

$("faqForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("faqSaveMsg").textContent = "";
  const errors = validateFaqForm();
  showFaqErrors(errors);
  if (Object.keys(errors).length) return;

  try {
    const res = await fetch("/api/faqs", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-PIN": adminPin },
      body: JSON.stringify({
        category: $("faqCategory").value,
        question: $("faqQuestion").value,
        answer: $("faqAnswer").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (data.errors) showFaqErrors(data.errors);
      else showSaveMsg(data.error || "Could not save FAQ.", false);
      return;
    }
    $("faqForm").reset();
    $("qCounter").textContent = "0/150";
    $("aCounter").textContent = "0/400";
    showSaveMsg("Saved as " + data.id + ". The bot can use it now.", true);
    loadFaqs();
  } catch {
    showSaveMsg("Could not reach the server.", false);
  }
});

function showSaveMsg(text, ok) {
  $("faqSaveMsg").textContent = text;
  $("faqSaveMsg").className = "ms-2 small " + (ok ? "text-success" : "text-danger");
}

$("resetBtn").addEventListener("click", () => {
  askConfirm("Reset all FAQs to the 8 starter FAQs? FAQs you added will be deleted.", "Reset", async () => {
    try {
      const res = await fetch("/api/faqs/reset", { method: "POST", headers: { "X-Admin-PIN": adminPin } });
      if (!res.ok) throw new Error();
      $("resetMsg").className = "small mt-2 text-success";
      $("resetMsg").textContent = "FAQs restored to starter data.";
      loadFaqs();
    } catch {
      $("resetMsg").className = "small mt-2 text-danger";
      $("resetMsg").textContent = "Reset failed.";
    }
  });
});

// =====================================================================
// Stats (localStorage, separate from chat so "Clear chat" keeps them)
// =====================================================================
function emptyStats() {
  return { asked: 0, answered: 0, notFound: 0, errors: 0, helpful: 0, notHelpful: 0, cited: {} };
}
function loadStats() {
  try { return { ...emptyStats(), ...JSON.parse(localStorage.getItem(STATS_KEY)) }; }
  catch { return emptyStats(); }
}
function saveStats() {
  try { localStorage.setItem(STATS_KEY, JSON.stringify(stats)); } catch { /* ignore */ }
  renderStats();
}
let stats = loadStats();

function changeFeedbackStats(oldValue, newValue) {
  if (oldValue === "up") stats.helpful--;
  if (oldValue === "down") stats.notHelpful--;
  if (newValue === "up") stats.helpful++;
  if (newValue === "down") stats.notHelpful++;
  saveStats();
}

function renderStats() {
  $("statAsked").textContent = stats.asked;
  $("statAnswered").textContent = stats.answered;
  $("statNotFound").textContent = stats.notFound;
  $("statErrors").textContent = stats.errors;
  $("statHelpful").textContent = stats.helpful;
  $("statNotHelpful").textContent = stats.notHelpful;

  // most-cited FAQ: highest count, ties -> lowest ID
  const top = Object.entries(stats.cited).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
  if (!top) {
    $("statTopFaq").textContent = "–";
    $("statTopFaqText").textContent = "No answers yet";
    return;
  }
  const faq = faqList.find((f) => f.id === top[0]);
  $("statTopFaq").textContent = top[0];
  $("statTopFaqText").textContent =
    (faq ? faq.question + " · " : "") + "cited " + top[1] + (top[1] === 1 ? " time" : " times");
}

$("resetStatsBtn").addEventListener("click", () => {
  askConfirm("Reset all stats to zero? Chat and FAQs are not affected.", "Reset", () => {
    stats = emptyStats();
    saveStats();
  });
});

// =====================================================================
// Dark mode (saved in localStorage; applied early in <head> to avoid a flash)
// =====================================================================
function applyTheme(theme) {
  document.documentElement.setAttribute("data-bs-theme", theme);
  $("themeIcon").className = theme === "dark" ? "bi bi-sun" : "bi bi-moon-stars";
  $("themeBtn").title = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
}
$("themeBtn").addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem(THEME_KEY, next); } catch { /* ignore */ }
});
applyTheme(document.documentElement.getAttribute("data-bs-theme") || "light");

// initial load
updateCounter();
loadFaqs().then(renderStats);
