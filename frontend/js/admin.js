// Admin dashboard. Every number and row comes from the backend; nothing here is hard-coded demo data.
import { api, requireUser } from "./api.js";
import { mountShell, $, $$, esc, toast, modal, fmtDate, errorBox, emptyState, hideLoader } from "./ui.js";

await requireUser({ admin: true });
await mountShell();
const TABS = [["overview", "Overview"], ["sync", "Synchronization"], ["catalogue", "Catalogue"], ["categories", "Categories"], ["users", "Users"], ["subscriptions", "Subscriptions"]];
const pill = (s) => `<span class="pill ${esc(s)}">${esc(String(s).replace("_", " "))}</span>`;
const money = (n, c) => { try { return new Intl.NumberFormat(undefined, { style: "currency", currency: c }).format(n); } catch { return `${c} ${n}`; } };
const table = (head, rows) => `<div class="table-wrap"><table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
const act = async (fn, ok) => { try { await fn(); if (ok) toast(ok, "success"); return true; } catch (e) { toast(e.message, "error"); return false; } };
let pollTimer;

const syncTable = (logs) => logs.length ? table(["Started", "Trigger", "Status", "Added", "Updated", "Duplicates", "Errors", "Note"],
  logs.map((l) => `<tr><td>${fmtDate(l.started_at)}</td><td>${esc(l.trigger_type)}</td><td>${pill(l.status)}</td><td>${l.titles_added}</td><td>${l.titles_updated}</td><td>${l.duplicates_skipped}</td><td>${l.errors}</td>
    <td><small>${esc(l.details?.message || (l.details?.errors || [])[0] || "")}</small></td></tr>`)) : emptyState("No synchronizations yet", "Run the first one from the Synchronization tab.");

const tabs = {
  async overview(el) {
    const s = await api("/admin/stats"), t = s.totals, h = s.health;
    const hc = (name, x) => `<div class="health"><strong>${name}</strong><div>${pill(x.status)}</div><small>${esc(x.detail || (x.latency_ms != null ? x.latency_ms + " ms" : "") || x.engine || "")}${x.engine ? " · " + esc(x.engine) : ""}</small></div>`;
    el.innerHTML = `<div class="stats">${[["Registered users", t.users], ["Movies", t.movies], ["Series", t.series], ["Premium subscribers", t.premium_subscribers], ["Playable titles", t.playable_titles]]
      .map(([l, n]) => `<div class="stat"><b>${n}</b><span>${l}</span></div>`).join("")}${s.revenue.map((r) => `<div class="stat"><b>${money(r.total_major, r.currency)}</b><span>Revenue (${r.payments} payments)</span></div>`).join("")}</div>
      <h2 style="margin-bottom:12px">Health</h2><div class="health-grid">${hc("Database", h.database)}${hc("TMDB", h.tmdb)}${h.providers.map((p) => hc("Provider: " + esc(p.name), p)).join("")}</div>
      <h2 style="margin-bottom:12px">Recent registrations</h2>${table(["User", "Email", "Role", "Joined"], s.recent_users.map((u) => `<tr><td>${esc(u.username)}</td><td>${esc(u.email)}</td><td>${esc(u.role)}</td><td>${fmtDate(u.created_at)}</td></tr>`))}
      <h2 style="margin:24px 0 12px">Latest synchronizations</h2>${syncTable(s.sync)}`;
  },
  async sync(el) {
    const draw = async () => {
      const s = await api("/admin/sync");
      el.innerHTML = `<div class="admin-bar"><button class="btn btn-primary" id="runSync" ${s.running || !s.tmdb_configured ? "disabled" : ""}>${s.running ? "Sync running…" : "Sync catalogue now"}</button>
        <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="force"> Refresh titles that are already up to date</label></div>
        <p class="muted" style="margin-bottom:16px">${s.tmdb_configured ? `Automatic sync: ${s.auto_sync_hours ? "every " + s.auto_sync_hours + " hours" : "off"}.` : "TMDB is not configured. Add TMDB_API_KEY to the backend environment to enable synchronization."}</p>${syncTable(s.logs)}`;
      $("#runSync")?.addEventListener("click", async () => { if (await act(() => api("/admin/sync", { method: "POST", body: { force: $("#force").checked } }), "Synchronization started")) draw(); });
      clearTimeout(pollTimer);
      if (s.running) pollTimer = setTimeout(() => location.hash === "#sync" && draw(), 4000);
    };
    await draw();
  },
  async catalogue(el) {
    let type = "movie", page = 1, q = "";
    const draw = async () => {
      const r = await api(`/admin/titles?type=${type}&page=${page}&q=${encodeURIComponent(q)}`);
      el.innerHTML = `<div class="admin-bar"><select id="ctype" aria-label="Type"><option value="movie" ${type === "movie" ? "selected" : ""}>Movies</option><option value="series" ${type === "series" ? "selected" : ""}>Series</option></select>
        <input type="search" id="cq" placeholder="Search title" value="${esc(q)}"><button class="btn btn-ghost btn-sm" id="cgo">Search</button><span style="flex:1"></span>
        <button class="btn btn-primary btn-sm" id="cadd">Add title</button><button class="btn btn-ghost btn-sm" id="cimp">Import from TMDB</button></div>
        <p class="muted" style="margin-bottom:12px">${r.total} ${type === "movie" ? "movies" : "series"}</p>
        ${r.items.length ? table(["", "Title", "Year", "Rating", "Source", "Playable", ""], r.items.map((t) => `<tr><td>${t.poster ? `<img class="thumb-sm" src="${esc(t.poster)}" alt="" loading="lazy">` : `<div class="thumb-sm"></div>`}</td><td>${esc(t.title)}</td><td>${t.year ?? "—"}</td><td>${t.rating ? Number(t.rating).toFixed(1) : "—"}</td><td>${esc(t.source || "")}</td><td>${t.has_sources ? pill("ok") : "—"}</td>
          <td class="row-actions"><button class="btn btn-ghost btn-sm" data-edit="${t.id}">Edit</button><button class="btn btn-ghost btn-sm" data-src="${t.id}">Sources</button><button class="btn btn-danger btn-sm" data-del="${t.id}">Delete</button></td></tr>`)) : emptyState("No titles", "Add one, import from TMDB or run a synchronization.")}
        <div class="more">${page > 1 ? `<button class="btn btn-ghost btn-sm" id="prev">Previous</button>` : ""}<span class="muted" style="margin:0 12px">Page ${r.page} of ${r.pages}</span>${page < r.pages ? `<button class="btn btn-ghost btn-sm" id="next">Next</button>` : ""}</div>`;
      $("#ctype").onchange = (e) => { type = e.target.value; page = 1; draw(); };
      const go = () => { q = $("#cq").value.trim(); page = 1; draw(); };
      $("#cgo").onclick = go; $("#cq").onkeydown = (e) => e.key === "Enter" && go();
      $("#prev")?.addEventListener("click", () => { page--; draw(); }); $("#next")?.addEventListener("click", () => { page++; draw(); });
      $("#cadd").onclick = () => titleForm(null, type, draw);
      $("#cimp").onclick = () => importForm(type, draw);
      el.onclick = async (e) => {
        const b = e.target.closest("button[data-edit],button[data-del],button[data-src]"); if (!b) return;
        const id = b.dataset.edit || b.dataset.del || b.dataset.src;
        if (b.dataset.edit) titleForm(r.items.find((t) => String(t.id) === id), type, draw);
        if (b.dataset.src) sourcesDialog(type, id);
        if (b.dataset.del && confirm("Delete this title and its sources, watchlist entries and history?")) { if (await act(() => api(`/admin/titles/${type}/${id}`, { method: "DELETE" }), "Deleted")) draw(); }
      };
    };
    await draw();
  },
  async categories(el) {
    const draw = async () => {
      const { items } = await api("/admin/categories");
      el.innerHTML = `<div class="admin-bar"><button class="btn btn-primary btn-sm" id="addCat">Add category</button></div>${table(["Order", "Name", "Slug", "Type", "Rule", "Home", ""], items.map((c) => `<tr><td>${c.position}</td><td>${esc(c.name)}</td><td>${esc(c.slug)}</td><td>${esc(c.media_type)}</td>
        <td><small>${[c.country && "country " + c.country, c.language && "lang " + c.language, c.genre && "genre " + c.genre, c.exclude_genre && "not " + c.exclude_genre, "sort " + c.sort].filter(Boolean).map(esc).join(", ")}</small></td><td>${c.show_on_home ? "✓" : "—"}</td>
        <td class="row-actions"><button class="btn btn-ghost btn-sm" data-edit="${c.id}">Edit</button><button class="btn btn-danger btn-sm" data-del="${c.id}">Delete</button></td></tr>`))}`;
      $("#addCat").onclick = () => categoryForm(null, draw);
      el.onclick = async (e) => {
        const b = e.target.closest("button[data-edit],button[data-del]"); if (!b) return;
        if (b.dataset.edit) categoryForm(items.find((c) => String(c.id) === b.dataset.edit), draw);
        else if (confirm("Delete this category?")) { if (await act(() => api(`/admin/categories/${b.dataset.del}`, { method: "DELETE" }), "Deleted")) draw(); }
      };
    };
    await draw();
  },
  async users(el) {
    let q = "", page = 1;
    const draw = async () => {
      const r = await api(`/admin/users?page=${page}&q=${encodeURIComponent(q)}`);
      el.innerHTML = `<div class="admin-bar"><input type="search" id="uq" placeholder="Search username or email" value="${esc(q)}"><button class="btn btn-ghost btn-sm" id="ugo">Search</button></div>
        <p class="muted" style="margin-bottom:12px">${r.total} users</p>${table(["User", "Email", "Role", "Status", "Premium", "Joined", ""], r.items.map((u) => `<tr><td>${esc(u.username)}</td><td>${esc(u.email)}</td><td>${esc(u.role)}</td><td>${pill(u.is_active ? "active" : "cancelled")}</td><td>${u.premium ? "✓" : "—"}</td><td>${fmtDate(u.created_at)}</td>
          <td class="row-actions"><button class="btn btn-ghost btn-sm" data-role="${u.id}" data-to="${u.role === "admin" ? "user" : "admin"}">Make ${u.role === "admin" ? "user" : "admin"}</button>
          <button class="btn btn-ghost btn-sm" data-active="${u.id}" data-to="${u.is_active ? 0 : 1}">${u.is_active ? "Disable" : "Enable"}</button><button class="btn btn-ghost btn-sm" data-grant="${u.id}">Give Premium</button></td></tr>`))}
        <div class="more">${page > 1 ? `<button class="btn btn-ghost btn-sm" id="prev">Previous</button>` : ""}<span class="muted" style="margin:0 12px">Page ${r.page} of ${r.pages}</span>${page < r.pages ? `<button class="btn btn-ghost btn-sm" id="next">Next</button>` : ""}</div>`;
      const go = () => { q = $("#uq").value.trim(); page = 1; draw(); };
      $("#ugo").onclick = go; $("#uq").onkeydown = (e) => e.key === "Enter" && go();
      $("#prev")?.addEventListener("click", () => { page--; draw(); }); $("#next")?.addEventListener("click", () => { page++; draw(); });
      el.onclick = async (e) => {
        const b = e.target.closest("button[data-role],button[data-active],button[data-grant]"); if (!b) return;
        if (b.dataset.grant) return grantForm(b.dataset.grant, draw);
        const body = b.dataset.role ? { role: b.dataset.to } : { is_active: b.dataset.to === "1" };
        if (await act(() => api(`/admin/users/${b.dataset.role || b.dataset.active}`, { method: "PUT", body }), "Updated")) draw();
      };
    };
    await draw();
  },
  async subscriptions(el) {
    const draw = async () => {
      const { items } = await api("/admin/subscriptions");
      el.innerHTML = items.length ? table(["User", "Plan", "Status", "Starts", "Ends", ""], items.map((s) => `<tr><td>${esc(s.username)}<br><small class="muted">${esc(s.email)}</small></td><td>${esc(s.plan)}</td><td>${pill(s.status)}</td><td>${fmtDate(s.starts_at)}</td><td>${fmtDate(s.ends_at)}</td>
        <td>${s.status === "active" ? `<button class="btn btn-danger btn-sm" data-cancel="${s.id}">Cancel</button>` : ""}</td></tr>`)) : emptyState("No subscriptions yet", "Paid and granted memberships appear here.");
      el.onclick = async (e) => { const b = e.target.closest("[data-cancel]"); if (b && confirm("Cancel this subscription?") && (await act(() => api(`/admin/subscriptions/${b.dataset.cancel}/cancel`, { method: "POST" }), "Cancelled"))) draw(); };
    };
    await draw();
  },
};

// ---- dialogs ---------------------------------------------------------------
const field = (id, label, value = "", attrs = "") => `<div class="field"><label for="${id}">${label}</label><input id="${id}" value="${esc(value)}" ${attrs}></div>`;
function titleForm(t, type, done) {
  const m = modal(`<h2 style="margin-bottom:14px">${t ? "Edit" : "Add"} ${type === "movie" ? "movie" : "series"}</h2><form id="tf"><div class="form-grid">
    ${field("f-title", "Title", t?.title, "required maxlength=200")}${field("f-year", "Release date (YYYY-MM-DD)", "", "placeholder='2024-05-31'")}${field("f-rating", "Rating (0 to 10)", t?.rating ?? "", "type=number step=0.1 min=0 max=10")}
    ${field("f-genres", "Genres (comma separated)", "")}${field("f-countries", "Country codes (comma separated)", "", "placeholder='KR, JP'")}${field("f-lang", "Language code", "", "maxlength=5 placeholder='ko'")}
    ${field("f-runtime", type === "movie" ? "Runtime (minutes)" : "Episode runtime (minutes)", "", "type=number min=0")}${field("f-poster", "Poster image link (https)", "", "type=url")}${field("f-backdrop", "Backdrop image link (https)", "", "type=url")}</div>
    <div class="field"><label for="f-over">Description</label><textarea id="f-over" rows="4" maxlength="4000"></textarea></div><p class="form-error" id="tfErr"></p>
    <button class="btn btn-primary">${t ? "Save changes" : "Add title"}</button>${t ? `<p class="hint" style="margin-top:8px">Only fields you fill in are changed.</p>` : ""}</form>`);
  $("#tf").onsubmit = async (e) => {
    e.preventDefault();
    const v = (id) => $("#" + id).value.trim(), body = {};
    if (v("f-title")) body.title = v("f-title");
    const map = { "f-year": "release_date", "f-genres": "genres", "f-countries": "countries", "f-lang": "original_language", "f-poster": "poster_url", "f-backdrop": "backdrop_url", "f-over": "overview" };
    for (const [id, key] of Object.entries(map)) if (v(id)) body[key] = v(id);
    if (v("f-rating")) body.rating = Number(v("f-rating"));
    if (v("f-runtime")) body[type === "movie" ? "runtime" : "episode_runtime"] = Number(v("f-runtime"));
    try {
      if (t) await api(`/admin/titles/${type}/${t.id}`, { method: "PUT", body }); else await api("/admin/titles", { method: "POST", body: { ...body, media_type: type } });
      m.close(); toast("Saved", "success"); done();
    } catch (err) { $("#tfErr").textContent = err.message; }
  };
}
function importForm(type, done) {
  const m = modal(`<h2 style="margin-bottom:6px">Import from TMDB</h2><p class="muted" style="margin-bottom:14px">Paste the number at the end of the title's TMDB page address.</p><form id="imp">${field("i-id", "TMDB ID", "", "type=number min=1 required")}<p class="form-error" id="impErr"></p><button class="btn btn-primary">Import ${type === "movie" ? "movie" : "series"}</button></form>`);
  $("#imp").onsubmit = async (e) => { e.preventDefault(); try { const r = await api("/admin/titles/import", { method: "POST", body: { media_type: type, tmdb_id: Number($("#i-id").value) } }); m.close(); toast(`Import ${r.outcome}`, "success"); done(); } catch (err) { $("#impErr").textContent = err.message; } };
}
async function sourcesDialog(type, id) {
  const m = modal(`<h2 style="margin-bottom:6px">Playback sources</h2><p class="muted" style="margin-bottom:14px">Only add links you are licensed to stream. CHILLFLIX never generates links.</p><div id="srcList"></div>
    <form id="sf" style="margin-top:16px"><div class="form-grid">${field("s-url", "Stream link (https)", "", "type=url required")}<div class="field"><label for="s-type">Type</label><select id="s-type"><option value="hls">HLS (.m3u8)</option><option value="mp4">MP4</option></select></div>
    ${field("s-q", "Quality", "auto", "maxlength=16")}${field("s-l", "Language", "original", "maxlength=16")}${type === "series" ? field("s-ep", "Episode ID", "", "type=number min=1 required") : ""}</div>
    <label style="display:flex;gap:8px;margin-bottom:10px"><input type="checkbox" id="s-prem"> Premium only</label><p class="form-error" id="sfErr"></p><button class="btn btn-primary btn-sm">Add source</button></form>`);
  const list = async () => {
    const { items } = await api(`/admin/titles/${type}/${id}/sources`);
    $("#srcList").innerHTML = items.length ? table(["Provider", "Type", "Quality", "Link", ""], items.map((s) => `<tr><td>${esc(s.provider)}</td><td>${esc(s.type)}</td><td>${esc(s.quality)}</td><td><small>${esc(s.url.slice(0, 48))}…</small></td><td><button class="btn btn-danger btn-sm" data-rm="${s.id}">Remove</button></td></tr>`)) : `<p class="muted">No sources yet. This title shows "Streaming source currently unavailable."</p>`;
  };
  $("#srcList").onclick = async (e) => { const b = e.target.closest("[data-rm]"); if (b && (await act(() => api(`/admin/sources/${b.dataset.rm}`, { method: "DELETE" }), "Removed"))) list(); };
  $("#sf").onsubmit = async (e) => {
    e.preventDefault();
    const body = { url: $("#s-url").value.trim(), type: $("#s-type").value, quality: $("#s-q").value.trim(), language: $("#s-l").value.trim(), premium_only: $("#s-prem").checked };
    if (type === "series") body.episode_id = Number($("#s-ep").value);
    try { await api(`/admin/titles/${type}/${id}/sources`, { method: "POST", body }); $("#s-url").value = ""; toast("Source added", "success"); list(); } catch (err) { $("#sfErr").textContent = err.message; }
  };
  list();
}
function categoryForm(c, done) {
  const sel = (id, label, opts, val) => `<div class="field"><label for="${id}">${label}</label><select id="${id}">${opts.map((o) => `<option ${o === val ? "selected" : ""}>${o}</option>`).join("")}</select></div>`;
  const m = modal(`<h2 style="margin-bottom:14px">${c ? "Edit" : "Add"} category</h2><form id="cf"><div class="form-grid">${field("c-name", "Name", c?.name, "required")}${field("c-slug", "Slug", c?.slug, "required pattern='[a-z0-9-]{2,40}'")}
    ${sel("c-type", "Content type", ["all", "movie", "series"], c?.media_type || "all")}${sel("c-sort", "Sort by", ["popularity", "rating", "recent", "trending"], c?.sort || "popularity")}
    ${field("c-country", "Country codes", c?.country || "", "placeholder='KR,JP'")}${field("c-lang", "Language codes", c?.language || "", "placeholder='ja'")}${field("c-genre", "Genres", c?.genre || "")}${field("c-ex", "Exclude genres", c?.exclude_genre || "")}
    ${field("c-pos", "Order", c?.position ?? 99, "type=number min=0")}</div><label style="display:flex;gap:8px;margin-bottom:10px"><input type="checkbox" id="c-home" ${c?.show_on_home !== false ? "checked" : ""}> Show on the home page</label><p class="form-error" id="cfErr"></p><button class="btn btn-primary">Save category</button></form>`);
  $("#cf").onsubmit = async (e) => {
    e.preventDefault();
    const body = { name: $("#c-name").value.trim(), slug: $("#c-slug").value.trim(), media_type: $("#c-type").value, sort: $("#c-sort").value, country: $("#c-country").value.trim(), language: $("#c-lang").value.trim(),
      genre: $("#c-genre").value.trim(), exclude_genre: $("#c-ex").value.trim(), position: Number($("#c-pos").value), show_on_home: $("#c-home").checked };
    try { await api(c ? `/admin/categories/${c.id}` : "/admin/categories", { method: c ? "PUT" : "POST", body }); m.close(); toast("Saved", "success"); done(); } catch (err) { $("#cfErr").textContent = err.message; }
  };
}
function grantForm(userId, done) {
  const m = modal(`<h2 style="margin-bottom:14px">Give Premium</h2><form id="gf"><div class="field"><label for="g-plan">Plan</label><select id="g-plan"><option value="monthly">Monthly (30 days)</option><option value="yearly">Yearly (365 days)</option></select></div>${field("g-days", "Days (optional, overrides the plan length)", "", "type=number min=1 max=3650")}<p class="form-error" id="gfErr"></p><button class="btn btn-primary">Grant</button></form>`);
  $("#gf").onsubmit = async (e) => { e.preventDefault(); const body = { user_id: Number(userId), plan: $("#g-plan").value }; if ($("#g-days").value) body.days = Number($("#g-days").value);
    try { await api("/admin/subscriptions", { method: "POST", body }); m.close(); toast("Premium granted", "success"); done(); } catch (err) { $("#gfErr").textContent = err.message; } };
}

async function show(name) {
  if (!tabs[name]) name = "overview";
  clearTimeout(pollTimer);
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  const el = $("#panel"); el.onclick = null;
  el.innerHTML = `<div class="skeleton" style="height:120px"></div>`;
  try { await tabs[name](el); } catch (e) { el.innerHTML = errorBox(e); }
}
$("#tabs").innerHTML = TABS.map(([k, l]) => `<button data-tab="${k}">${l}</button>`).join("");
$("#tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) show(b.dataset.tab); });
addEventListener("hashchange", () => show(location.hash.slice(1)));
hideLoader();
show(location.hash.slice(1) || "overview");
