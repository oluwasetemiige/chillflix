import { api, requireUser, currentProfile, applyTheme, logout, setToken } from "./api.js";
import { mountShell, $, $$, esc, card, emptyState, errorBox, toast, fmtDate, hideLoader, skeletonGrid } from "./ui.js";

await requireUser();
const user0 = await mountShell();
let profile = await currentProfile();
const root = $("#profile");
const TABS = [["overview", "Overview"], ["history", "Watch history"], ["saved", "Saved"], ["preferences", "Preferences"], ["account", "Account"]];
const initial = (u) => esc(u.username[0].toUpperCase());

function head() {
  const u = profile.user, sub = u.subscription;
  $("#phead").innerHTML = `<div class="avatar ${sub.is_premium ? "premium" : ""}">${u.avatar_url ? `<img src="${esc(u.avatar_url)}" alt="">` : initial(u)}</div>
    <div><h1>${esc(u.username)}</h1><p class="muted">${esc(u.email)} · ${sub.is_premium ? `Premium until ${fmtDate(sub.ends_at)}` : "Free plan"}</p></div>`;
}
const panels = {
  async overview(el) {
    const c = profile.counts, sub = profile.user.subscription;
    const cont = await api("/history?continue=1&limit=12");
    el.innerHTML = `<div class="stats"><div class="stat"><b>${c.watchlist}</b><span>Saved titles</span></div><div class="stat"><b>${c.history}</b><span>Watched or started</span></div>
      <div class="stat"><b>${profile.preferences.favorite_genres.length}</b><span>Favourite genres</span></div><div class="stat"><b>${sub.is_premium ? "Premium" : "Free"}</b><span>Membership</span></div></div>
      <div class="panel"><h2>Membership</h2><p>${sub.is_premium ? `Your ${esc(sub.plan)} plan runs until ${fmtDate(sub.ends_at)}.` : "You're on the Free plan."}</p><p style="margin-top:14px"><a class="btn btn-primary btn-sm" href="premium.html">${sub.is_premium ? "Manage Premium" : "See Premium"}</a></p></div>
      <h2 style="margin:8px 0 14px">Continue watching</h2>${cont.items.length ? `<div class="grid">${cont.items.map((h) => card(h, { progress: h.duration ? Math.round((h.position / h.duration) * 100) : 0 })).join("")}</div>` : emptyState("Nothing in progress", "Start something and it will show up here.", `<a class="btn btn-primary" href="index.html">Browse titles</a>`)}`;
  },
  async history(el) {
    const { items } = await api("/history?limit=60");
    el.innerHTML = items.length ? `<div class="table-wrap"><table><thead><tr><th>Title</th><th>Progress</th><th>Last watched</th><th></th></tr></thead><tbody>${items.map((h) => `<tr>
      <td><a href="details.html?type=${h.media_type}&id=${h.id}"><strong>${esc(h.title)}</strong></a>${h.episode_label ? ` <span class="muted">${esc(h.episode_label)}</span>` : ""}</td>
      <td>${h.completed ? "Finished" : h.duration ? Math.round((h.position / h.duration) * 100) + "%" : "—"}</td><td>${fmtDate(h.updated_at)}</td>
      <td class="row-actions"><a class="btn btn-ghost btn-sm" href="watch.html?type=${h.media_type}&id=${h.id}${h.episode_id ? "&episode=" + h.episode_id : ""}">${h.completed ? "Watch again" : "Resume"}</a>
      <button class="btn btn-danger btn-sm" data-del="${h.history_id}">Remove</button></td></tr>`).join("")}</tbody></table></div>`
      : emptyState("No history yet", "Titles you watch appear here.");
    el.onclick = async (e) => { const b = e.target.closest("[data-del]"); if (!b) return; try { await api(`/history/${b.dataset.del}`, { method: "DELETE" }); toast("Removed"); show("history"); } catch (err) { toast(err.message, "error"); } };
  },
  async saved(el) {
    const { items } = await api("/watchlist");
    el.innerHTML = items.length ? `<div class="grid">${items.map((i) => card(i, { removable: i.watchlist_id })).join("")}</div>` : emptyState("Nothing saved", "Add titles to your watchlist from any details page.", `<a class="btn btn-primary" href="index.html">Discover titles</a>`);
    el.onclick = async (e) => { const b = e.target.closest("[data-remove]"); if (!b) return; e.preventDefault(); try { await api(`/watchlist/${b.dataset.remove}`, { method: "DELETE" }); toast("Removed from watchlist"); show("saved"); } catch (err) { toast(err.message, "error"); } };
  },
  async preferences(el) {
    const { items: genres } = await api("/genres");
    const p = profile.preferences, premium = profile.user.subscription.is_premium;
    const lock = premium ? "" : " (Premium)";
    el.innerHTML = `<form class="panel" id="prefForm"><h2>Favourite genres</h2><div class="genre-pick">${genres.map((g) => `<label><input type="checkbox" name="genre" value="${esc(g)}" ${p.favorite_genres.includes(g) ? "checked" : ""}><span>${esc(g)}</span></label>`).join("")}</div>
      <h2 style="margin-top:26px">Viewing</h2>
      <div class="switch-row"><label for="autoplay">Play the next episode automatically</label><input type="checkbox" id="autoplay" ${p.autoplay_next ? "checked" : ""}></div>
      <div class="field"><label for="subs">Subtitle language</label><select id="subs">${[["off", "Off"], ["en", "English"], ["ko", "Korean"], ["ja", "Japanese"], ["zh", "Chinese"], ["fr", "French"], ["es", "Spanish"]].map(([v, l]) => `<option value="${v}" ${p.subtitle_language === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div class="field"><label for="quality">Preferred quality</label><select id="quality">${["auto", "480p", "720p", "1080p"].map((q) => `<option value="${q}" ${p.default_quality === q ? "selected" : ""} ${q === "1080p" && !premium ? "disabled" : ""}>${q}${q === "1080p" ? lock : ""}</option>`).join("")}</select></div>
      <div class="field"><label for="theme">Colour theme</label><select id="theme">${[["violet", "Violet"], ["rose", "Rose"], ["azure", "Azure"], ["emerald", "Emerald"]].map(([v, l]) => `<option value="${v}" ${p.accent_theme === v ? "selected" : ""} ${v !== "violet" && !premium ? "disabled" : ""}>${l}${v !== "violet" ? lock : ""}</option>`).join("")}</select></div>
      <p class="form-error" id="prefErr"></p><button class="btn btn-primary">Save preferences</button></form>`;
    $("#prefForm").onsubmit = async (e) => {
      e.preventDefault();
      try {
        const r = await api("/users/preferences", { method: "PUT", body: { favorite_genres: $$("[name=genre]:checked", el).map((i) => i.value), autoplay_next: $("#autoplay").checked,
          subtitle_language: $("#subs").value, default_quality: $("#quality").value, accent_theme: $("#theme").value } });
        profile = await currentProfile(true); applyTheme(r.preferences.accent_theme); toast("Preferences saved", "success");
      } catch (err) { $("#prefErr").textContent = err.message; }
    };
  },
  async account(el) {
    el.innerHTML = `<form class="panel" id="nameForm"><h2>Profile</h2><div class="field"><label for="uname">Username</label><input id="uname" value="${esc(profile.user.username)}" maxlength="24" autocomplete="username"></div>
      <div class="field"><label for="avatar">Profile picture</label><input id="avatar" type="file" accept="image/jpeg,image/png,image/webp"><span class="hint">JPEG, PNG or WebP, up to 300 KB.</span></div>
      <p class="form-error" id="nameErr"></p><div style="display:flex;gap:10px;flex-wrap:wrap"><button class="btn btn-primary">Save profile</button>${profile.user.avatar_url ? `<button type="button" class="btn btn-ghost" id="rmAvatar">Remove picture</button>` : ""}</div></form>
      <form class="panel" id="pwForm"><h2>Change password</h2><div class="field"><label for="cur">Current password</label><input id="cur" type="password" autocomplete="current-password"></div>
      <div class="field"><label for="new">New password</label><input id="new" type="password" autocomplete="new-password"><span class="hint">At least 8 characters with letters and numbers.</span></div>
      <p class="form-error" id="pwErr"></p><button class="btn btn-primary">Update password</button></form>
      <div class="panel"><h2>Sign out</h2><p class="muted" style="margin-bottom:14px">This signs you out on every device.</p><button class="btn btn-danger" id="out">Log out</button></div>`;
    const dataUrl = (file) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = no; r.readAsDataURL(file); });
    $("#nameForm").onsubmit = async (e) => {
      e.preventDefault(); $("#nameErr").textContent = "";
      try {
        const body = { username: $("#uname").value.trim() };
        const f = $("#avatar").files[0];
        if (f) { if (f.size > 300 * 1024) throw new Error("That picture is over 300 KB. Pick a smaller one."); body.avatar = await dataUrl(f); }
        await api("/users/profile", { method: "PUT", body }); profile = await currentProfile(true); head(); toast("Profile saved", "success");
      } catch (err) { $("#nameErr").textContent = err.message; }
    };
    $("#rmAvatar")?.addEventListener("click", async () => { await api("/users/profile", { method: "PUT", body: { avatar: "" } }); profile = await currentProfile(true); head(); show("account"); });
    $("#pwForm").onsubmit = async (e) => {
      e.preventDefault(); $("#pwErr").textContent = "";
      try { await api("/users/password", { method: "POST", body: { current_password: $("#cur").value, new_password: $("#new").value } }); setToken(null); toast("Password changed. Please log in again.", "success"); setTimeout(() => (location.href = "login.html"), 900); }
      catch (err) { $("#pwErr").textContent = err.message; }
    };
    $("#out").onclick = logout;
  },
};

async function show(name) {
  if (!panels[name]) name = "overview";
  history.replaceState(null, "", "#" + name);
  $$("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  const el = $("#panel"); el.onclick = null;
  el.innerHTML = `<div class="grid">${skeletonGrid(4)}</div>`;
  try { await panels[name](el); } catch (e) { el.innerHTML = errorBox(e); }
}
head();
$("#tabs").innerHTML = TABS.map(([k, l]) => `<button data-tab="${k}">${l}</button>`).join("");
$("#tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) show(b.dataset.tab); });
hideLoader();
show(location.hash.slice(1) || "overview");
