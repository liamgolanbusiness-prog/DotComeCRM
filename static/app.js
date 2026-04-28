const STATUS_LABELS = {};
document.querySelectorAll("#d-status option").forEach(o => STATUS_LABELS[o.value] = o.textContent);

const SORT_FIELDS = [
  ["updated_at",    "עודכן לאחרונה"],
  ["created_at",    "נוצר"],
  ["name",          "שם"],
  ["city",          "עיר"],
  ["status",        "סטטוס"],
  ["next_followup", "תאריך מעקב"],
  ["last_contacted","שיחה אחרונה"],
  ["rating",        "דירוג"],
  ["reviews",       "ביקורות"],
  ["price_total",   "מחיר כולל"],
  ["price_paid",    "שולם"],
  ["phone",         "טלפון"],
];
const DEFAULT_SORT = [{field:"updated_at", dir:"desc"}];
let state = {
  q:"", status:"", city:"", category:"", owner:"", leads:[], current:null, view:"list",
  sort: JSON.parse(localStorage.getItem("sort") || "null") || DEFAULT_SORT.slice(),
  me: null, users: [],
};

const $ = s => document.querySelector(s);

async function loadMe() {
  const r = await fetch("/api/me").then(r => r.json());
  state.me = r.user;
  state.users = r.users || [];
  $("#me-name").textContent = state.me || "?";
  // Owner filter list (sidebar)
  const ol = $("#owner-list");
  ol.innerHTML = `<li data-owner="" class="active">הכל <span class="cnt" id="ocnt-"></span></li>`;
  for (const u of state.users) {
    const li = document.createElement("li");
    li.dataset.owner = u;
    li.innerHTML = `${u}${u === state.me ? " (אני)" : ""} <span class="cnt" id="ocnt-${u}"></span>`;
    ol.appendChild(li);
  }
  ol.querySelectorAll("li").forEach(li => {
    li.onclick = () => {
      ol.querySelectorAll("li").forEach(x => x.classList.remove("active"));
      li.classList.add("active");
      state.owner = li.dataset.owner;
      loadLeads();
    };
  });
  // Owner selects (detail + new lead)
  const ownerOpts = state.users.map(u => `<option value="${u}">${u}</option>`).join("");
  $("#d-owner").innerHTML = ownerOpts;
  $("#nl-owner").innerHTML = ownerOpts;
  $("#nl-owner").value = state.me || state.users[0];
}

async function loadLeads() {
  const params = new URLSearchParams();
  if (state.q)        params.set("q", state.q);
  if (state.city)     params.set("city", state.city);
  if (state.category) params.set("category", state.category);
  if (state.owner)    params.set("owner", state.owner);
  if (state.view === "kanban") {
    params.set("active", "1");
    params.set("limit", "1000");
  } else {
    if (state.status) params.set("status", state.status);
    params.set("sort", state.sort.map(s => `${s.field}:${s.dir}`).join(","));
  }
  const r = await fetch("/api/leads?" + params).then(r => r.json());
  state.leads = r.leads;
  if (state.view === "kanban") renderKanban(r);
  else                          renderList(r);
  updateCounts(r.counts);
  updateOwnerCounts(r.owner_counts || {});
  populateCities(r.cities);
  populateCategories(r.categories || []);
}

function renderList(r) {
  $("#result-count").textContent = `${r.leads.length} מתוך ${r.total} לידים`;
  const list = $("#lead-list");
  list.innerHTML = "";
  for (const L of r.leads) {
    const div = document.createElement("div");
    div.className = "lead" + (state.current === L.id ? " selected" : "") + (L.status === "not_relevant" ? " sunk" : "");
    div.innerHTML = `
      <div>
        <div class="name">${escapeHtml(L.name || "(ללא שם)")}</div>
        <div class="sub">${escapeHtml(L.category || "")} · ${escapeHtml(L.city || "")} ${L.rating ? "· ⭐" + L.rating : ""}</div>
      </div>
      <div class="phone">${escapeHtml(L.phone || "")}</div>
      ${ownerBadgeHtml(L.owner)}
      <div class="status ${L.status}">${STATUS_LABELS[L.status] || L.status}</div>`;
    div.onclick = () => openDetail(L.id);
    list.appendChild(div);
  }
}

function ownerBadgeHtml(owner) {
  if (!owner) return `<div></div>`;
  const mine = owner === state.me ? " owner-mine" : "";
  return `<div class="owner-badge owner-${escapeHtml(owner)}${mine}">${escapeHtml(owner)}</div>`;
}

function renderKanban(r) {
  $("#result-count").textContent = `${r.leads.length} לידים פעילים`;
  document.querySelectorAll(".kcol-body").forEach(b => b.innerHTML = "");
  const byStatus = {};
  for (const L of r.leads) (byStatus[L.status] = byStatus[L.status] || []).push(L);
  document.querySelectorAll(".kcol").forEach(col => {
    const status = col.dataset.status;
    const items = byStatus[status] || [];
    document.getElementById("kcnt-" + status).textContent = items.length;
    const body = col.querySelector(".kcol-body");
    for (const L of items) {
      const card = document.createElement("div");
      card.className = "kcard";
      card.draggable = true;
      card.dataset.id = L.id;
      card.innerHTML = `
        <div class="kname">${escapeHtml(L.name || "(ללא שם)")}</div>
        <div class="ksub">${escapeHtml(L.city || "")} · ${escapeHtml(L.phone || "")}</div>
        ${L.owner ? ownerBadgeHtml(L.owner) : ""}
        ${L.next_followup ? `<div class="kfollow">📅 ${L.next_followup}</div>` : ""}`;
      card.onclick = () => openDetail(L.id);
      card.addEventListener("dragstart", e => {
        card.classList.add("dragging");
        e.dataTransfer.setData("text/plain", L.id);
        e.dataTransfer.effectAllowed = "move";
      });
      card.addEventListener("dragend", () => card.classList.remove("dragging"));
      body.appendChild(card);
    }
  });
}

function updateCounts(counts) {
  let total = 0;
  for (const k in counts) {
    const el = document.getElementById("cnt-" + k);
    if (el) el.textContent = counts[k];
    total += counts[k];
  }
  document.getElementById("cnt-").textContent = total;
}

function updateOwnerCounts(counts) {
  let total = 0;
  for (const u of state.users) {
    const el = document.getElementById("ocnt-" + u);
    const n = counts[u] || 0;
    if (el) el.textContent = n;
    total += n;
  }
  const t = document.getElementById("ocnt-");
  if (t) t.textContent = total;
}

function populateCities(cities) {
  const sel = $("#city-filter");
  if (sel.options.length > 1) return;
  for (const c of cities) {
    const o = document.createElement("option");
    o.value = c; o.textContent = c;
    sel.appendChild(o);
  }
}

function populateCategories(categories) {
  const sel = $("#category-filter");
  if (sel.options.length > 1) return;
  for (const c of categories) {
    const o = document.createElement("option");
    o.value = c; o.textContent = c;
    sel.appendChild(o);
  }
}

let loadingDetail = false;
async function openDetail(id) {
  loadingDetail = true;
  state.current = id;
  document.querySelectorAll(".lead").forEach(l => l.classList.remove("selected"));
  const L = await fetch("/api/leads/" + id).then(r => r.json());
  $("#detail").classList.remove("hidden");
  $("#d-name").textContent = L.name || "(ללא שם)";
  $("#d-meta").innerHTML = `
    ${escapeHtml(L.category || "")} · ${escapeHtml(L.city || "")}<br>
    ${escapeHtml(L.address || "")}<br>
    ${L.rating ? "⭐ " + L.rating + " (" + (L.reviews || 0) + " ביקורות)" : ""}
  `;
  $("#d-call").href = L.phone_intl ? "tel:+" + L.phone_intl : "#";
  $("#d-call").textContent = "📞 " + (L.phone || "אין מספר");
  $("#d-call").onclick = () => {
    if (!L.phone_intl) return;
    fetch("/api/leads/" + id + "/log-call", {method:"POST"})
      .then(() => { if (state.current === id) loadEvents(id); });
  };
  $("#d-maps").href = L.maps_url || "#";
  $("#d-status").value = L.status || "new";
  $("#d-owner").value = L.owner || state.me || "";
  $("#d-followup").value = L.next_followup || "";
  $("#d-demo").value = L.demo_url || "";
  $("#d-final").value = L.final_url || "";
  $("#d-total").value = L.price_total || "";
  $("#d-paid").value = L.price_paid || "";
  $("#d-notes").value = L.notes || "";
  $("#d-times").textContent = `נוצר: ${L.created_at || "-"} · עודכן: ${L.updated_at || "-"} · שיחה אחרונה: ${L.last_contacted || "-"}`;
  $("#d-saved").textContent = "שינויים נשמרים אוטומטית";
  loadEvents(id);
  loadingDetail = false;
  document.querySelectorAll(".lead").forEach(el => {
    if (el.querySelector(".name").textContent === (L.name || "(ללא שם)")) el.classList.add("selected");
  });
}

let saveTimer = null;
async function patchField(fields) {
  if (!state.current) return;
  $("#d-saved").textContent = "שומר...";
  try {
    const r = await fetch("/api/leads/" + state.current, {
      method:"PATCH",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify(fields),
    });
    if (!r.ok) throw new Error(await r.text());
    $("#d-saved").textContent = "נשמר ✓ " + new Date().toLocaleTimeString("he-IL");
    loadLeads();
  } catch (e) {
    $("#d-saved").textContent = "שגיאה בשמירה ⚠";
    console.error(e);
  }
}
function autoSaveDetail() {
  if (!state.current) return;
  clearTimeout(saveTimer);
  $("#d-saved").textContent = "ממתין...";
  const id = state.current;
  saveTimer = setTimeout(async () => {
    await patchField({
      status:        $("#d-status").value,
      owner:         $("#d-owner").value,
      next_followup: $("#d-followup").value || null,
      demo_url:      $("#d-demo").value || null,
      final_url:     $("#d-final").value || null,
      price_total:   parseFloat($("#d-total").value) || null,
      price_paid:    parseFloat($("#d-paid").value) || null,
      notes:         $("#d-notes").value,
    });
    loadEvents(id);
  }, 500);
}

async function loadEvents(id) {
  const ul = $("#d-events");
  ul.innerHTML = `<li class="empty">טוען...</li>`;
  let events;
  try {
    events = await fetch(`/api/leads/${id}/events`).then(r => r.json());
  } catch { ul.innerHTML = `<li class="empty">שגיאה בטעינה</li>`; return; }
  if (state.current !== id) return; // detail switched while we were loading
  if (!events.length) { ul.innerHTML = `<li class="empty">אין פעולות עדיין</li>`; return; }
  ul.innerHTML = "";
  for (const ev of events) {
    const li = document.createElement("li");
    li.innerHTML = `
      <span class="ev-user">${escapeHtml(ev.user)}</span>
      <span class="ev-text">${escapeHtml(formatEvent(ev))}</span>
      <span class="ev-time">${escapeHtml(ev.created_at || "")}</span>`;
    ul.appendChild(li);
  }
}

function formatEvent(ev) {
  const d = ev.details || {};
  switch (ev.action) {
    case "created":       return `יצר ליד${d.owner ? ` (אחראי: ${d.owner})` : ""}`;
    case "status_change": return `שינה סטטוס${d.from ? ` מ-${STATUS_LABELS[d.from] || d.from}` : ""} ל-${STATUS_LABELS[d.to] || d.to}`;
    case "owner_change":  return `העביר אחריות${d.from ? ` מ-${d.from}` : ""} ל-${d.to}`;
    case "called":        return d && d.channel === "whatsapp" ? "שלח WhatsApp" : "תיעד שיחה";
    case "updated":       return `עדכן: ${(d.fields || []).join(", ")}`;
    default:              return ev.action;
  }
}

/* WhatsApp modal */
async function openWhatsApp() {
  if (!state.current) return;
  $("#wa-stage").value = $("#d-status").value;
  await loadWhatsAppPreview();
  $("#wa-modal").classList.remove("hidden");
}
async function loadWhatsAppPreview() {
  const stage = $("#wa-stage").value;
  const r = await fetch(`/api/leads/${state.current}/whatsapp?stage=${stage}`).then(r => r.json());
  if (r.error) { $("#wa-text").value = "(אין מספר טלפון)"; $("#wa-send").disabled = true; return; }
  $("#wa-text").value = r.message;
  $("#wa-send").disabled = false;
  $("#wa-send").dataset.url = r.url.split("?text=")[0];
}
function sendWhatsApp() {
  const base = $("#wa-send").dataset.url;
  const text = encodeURIComponent($("#wa-text").value);
  window.open(`${base}?text=${text}`, "_blank");
  const id = state.current;
  fetch("/api/leads/" + id + "/log-call", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({channel:"whatsapp"}),
  }).then(() => { if (state.current === id) loadEvents(id); });
  $("#wa-modal").classList.add("hidden");
}

function renderSortBar() {
  const box = $("#sort-rules");
  box.innerHTML = "";
  state.sort.forEach((rule, i) => {
    const el = document.createElement("div");
    el.className = "sort-rule";
    const opts = SORT_FIELDS.map(([k,l]) => `<option value="${k}" ${rule.field===k?"selected":""}>${l}</option>`).join("");
    el.innerHTML = `
      <select class="sr-field" data-i="${i}">${opts}</select>
      <button class="sr-dir dir" data-i="${i}" title="הפוך כיוון">${rule.dir === "asc" ? "↑" : "↓"}</button>
      <button class="sr-remove remove" data-i="${i}" title="הסר">✕</button>`;
    box.appendChild(el);
  });
  box.querySelectorAll(".sr-field").forEach(s => s.onchange = e => {
    state.sort[+e.target.dataset.i].field = e.target.value;
    persistSort(); loadLeads();
  });
  box.querySelectorAll(".sr-dir").forEach(b => b.onclick = e => {
    const i = +e.currentTarget.dataset.i;
    state.sort[i].dir = state.sort[i].dir === "asc" ? "desc" : "asc";
    persistSort(); renderSortBar(); loadLeads();
  });
  box.querySelectorAll(".sr-remove").forEach(b => b.onclick = e => {
    const i = +e.currentTarget.dataset.i;
    state.sort.splice(i, 1);
    if (!state.sort.length) state.sort = DEFAULT_SORT.slice();
    persistSort(); renderSortBar(); loadLeads();
  });
}
function persistSort() { localStorage.setItem("sort", JSON.stringify(state.sort)); }

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

/* Wire up */
let searchTimer;
$("#search").oninput = e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.q = e.target.value; loadLeads(); }, 250);
};
$("#city-filter").onchange = e => { state.city = e.target.value; loadLeads(); };
$("#category-filter").onchange = e => { state.category = e.target.value; loadLeads(); };
document.querySelectorAll("#status-list li").forEach(li => {
  li.onclick = () => {
    document.querySelectorAll("#status-list li").forEach(x => x.classList.remove("active"));
    li.classList.add("active");
    state.status = li.dataset.status;
    loadLeads();
  };
});
$("#reload").onclick = loadLeads;

$("#new-lead").onclick = () => {
  ["nl-name","nl-category","nl-city","nl-phone","nl-address","nl-notes"].forEach(id => document.getElementById(id).value = "");
  $("#new-modal").classList.remove("hidden");
  $("#nl-name").focus();
};
$("#nl-cancel").onclick = () => $("#new-modal").classList.add("hidden");
$("#nl-save").onclick = async () => {
  const body = {
    name:     $("#nl-name").value,
    category: $("#nl-category").value,
    city:     $("#nl-city").value,
    phone:    $("#nl-phone").value,
    address:  $("#nl-address").value,
    owner:    $("#nl-owner").value,
    notes:    $("#nl-notes").value,
  };
  const r = await fetch("/api/leads", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify(body),
  });
  if (!r.ok) { alert("שגיאה ביצירת הליד"); return; }
  const L = await r.json();
  $("#new-modal").classList.add("hidden");
  await loadLeads();
  openDetail(L.id);
};

document.querySelectorAll(".view-btn").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll(".view-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state.view = btn.dataset.view;
    if (state.view === "kanban") {
      $("#lead-list").classList.add("hidden");
      $("#sort-bar").classList.add("hidden");
      $("#kanban").classList.remove("hidden");
    } else {
      $("#lead-list").classList.remove("hidden");
      $("#sort-bar").classList.remove("hidden");
      $("#kanban").classList.add("hidden");
    }
    loadLeads();
  };
});

document.querySelectorAll(".kcol-body").forEach(body => {
  body.addEventListener("dragover", e => { e.preventDefault(); body.classList.add("drag-over"); });
  body.addEventListener("dragleave", () => body.classList.remove("drag-over"));
  body.addEventListener("drop", async e => {
    e.preventDefault();
    body.classList.remove("drag-over");
    const id = e.dataTransfer.getData("text/plain");
    const newStatus = body.dataset.status;
    if (!id) return;
    await fetch("/api/leads/" + id, {
      method:"PATCH",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({status: newStatus}),
    });
    loadLeads();
  });
});
$("#close-detail").onclick = () => { $("#detail").classList.add("hidden"); state.current = null; };
// Auto-save on any detail field change (debounced, skipped while loading a lead)
["d-status","d-owner","d-followup","d-demo","d-final","d-total","d-paid","d-notes"].forEach(id => {
  const el = document.getElementById(id);
  const ev = el.tagName === "SELECT" ? "change" : "input";
  el.addEventListener(ev, () => { if (!loadingDetail) autoSaveDetail(); });
});
$("#d-wa").onclick = openWhatsApp;
$("#sort-add").onclick = () => {
  const used = new Set(state.sort.map(s => s.field));
  const next = SORT_FIELDS.find(([k]) => !used.has(k));
  if (next) { state.sort.push({field:next[0], dir:"desc"}); persistSort(); renderSortBar(); loadLeads(); }
};
$("#sort-reset").onclick = () => { state.sort = DEFAULT_SORT.slice(); persistSort(); renderSortBar(); loadLeads(); };
$("#wa-stage").onchange = loadWhatsAppPreview;
$("#wa-send").onclick = sendWhatsApp;
$("#wa-cancel").onclick = () => $("#wa-modal").classList.add("hidden");

renderSortBar();
loadMe().then(loadLeads);
