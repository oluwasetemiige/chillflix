// Shared interface pieces: navigation, footer, cards, rows, toasts, modals.
import { api, currentUser, logout, loginUrl } from "./api.js";
import { TAGLINE } from "./config.js";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const LOGO = `<svg viewBox="0 0 64 64" aria-hidden="true"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8B5CF6"/><stop offset="1" stop-color="#A855F7"/></linearGradient></defs><path d="M50 14.5A25 25 0 1 0 50 49.5" fill="none" stroke="url(#lg)" stroke-width="9" stroke-linecap="round"/><path d="M27 22.5v19a1.5 1.5 0 0 0 2.3 1.3l15-9.5a1.5 1.5 0 0 0 0-2.6l-15-9.5A1.5 1.5 0 0 0 27 22.5z" fill="#fff"/></svg>`;
const ICON = {
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`,
  play: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13a1 1 0 0 0 1.5.9l10.5-6.5a1 1 0 0 0 0-1.8L9.5 4.6A1 1 0 0 0 8 5.5z"/></svg>`,
  info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>`,
  share: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/></svg>`,
  film: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/></svg>`,
  x: `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>`,
};
export const icon = (name) => ICON[name] || "";

const LINKS = [["index.html", "Home"], ["movies.html", "Movies"], ["series.html", "Series"], ["kdrama.html", "K-Drama"], ["cdrama.html", "C-Drama"],
  ["anime.html", "Anime"], ["search.html", "Search"], ["premium.html", "Premium"], ["profile.html", "Profile"]];

const POSTER_FALLBACK = "data:image/svg+xml;utf8," + encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 300'><rect width='200' height='300' fill='#181824'/><g fill='none' stroke='#3b3b55' stroke-width='6' stroke-linecap='round'><circle cx='100' cy='140' r='28'/><path d='M92 128v24l20-12z' fill='#3b3b55'/></g></svg>`);
export const posterOr = (url) => url || POSTER_FALLBACK;

// ---------- page shell -------------------------------------------------------
export async function mountShell() {
  document.body.insertAdjacentHTML("afterbegin", `<div class="loader" id="loader">${LOGO}</div>`);
  const page = location.pathname.split("/").pop() || "index.html";
  const user = await currentUser();
  const initial = user ? esc(user.username[0].toUpperCase()) : "";
  const nav = `<header class="nav" id="nav"><div class="wrap nav-inner">
    <a class="brand" href="index.html" aria-label="CHILLFLIX home">${LOGO}<span>CHILLFLIX</span></a>
    <nav class="nav-links" id="navLinks" aria-label="Main">${LINKS.map(([h, t]) => `<a href="${h}" class="${page === h ? "active" : ""}">${t}</a>`).join("")}
      ${user?.role === "admin" ? `<a href="admin.html" class="${page === "admin.html" ? "active" : ""}">Admin</a>` : ""}</nav>
    <div class="nav-end">
      <form class="nav-search" id="navSearch" role="search"><input type="search" name="q" placeholder="Search titles" aria-label="Search titles" autocomplete="off"><button aria-label="Search">${ICON.search}</button></form>
      ${user ? `<a href="profile.html" class="avatar ${user.is_premium ? "premium" : ""}" aria-label="Your profile" title="${esc(user.username)}">${user.avatar_url ? `<img src="${esc(user.avatar_url)}" alt="">` : initial}</a>`
             : `<a class="btn btn-primary btn-sm" href="${loginUrl()}">Log in</a>`}
      <button class="burger" id="burger" aria-label="Menu" aria-expanded="false" aria-controls="navLinks"><span></span><span></span><span></span></button>
    </div></div></header>`;
  document.body.insertAdjacentHTML("afterbegin", nav);
  $("#navSearch").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = new FormData(e.target).get("q").trim();
    if (q) location.href = `search.html?q=${encodeURIComponent(q)}`;
  });
  $("#burger").addEventListener("click", (e) => {
    const open = $("#navLinks").classList.toggle("open");
    e.currentTarget.setAttribute("aria-expanded", open);
  });
  const onScroll = () => $("#nav").classList.toggle("solid", scrollY > 30);
  addEventListener("scroll", onScroll, { passive: true }); onScroll();

  document.body.insertAdjacentHTML("beforeend", `<footer class="footer"><div class="wrap footer-in">
    <div><a class="brand" href="index.html">${LOGO}<span>CHILLFLIX</span></a><p style="margin-top:8px">${esc(TAGLINE)}</p></div>
    <nav aria-label="Footer"><a href="movies.html">Movies</a><a href="series.html">Series</a><a href="kdrama.html">K-Drama</a><a href="cdrama.html">C-Drama</a><a href="anime.html">Anime</a><a href="premium.html">Premium</a><a href="watchlist.html">Watchlist</a></nav>
    <p>Metadata by TMDB. This product uses the TMDB API but is not endorsed or certified by TMDB.</p></div></footer><div class="toasts" id="toasts" aria-live="polite"></div>`);
  setTimeout(() => $("#loader")?.classList.add("done"), 250);
  setTimeout(() => $("#loader")?.remove(), 900);
  return user;
}
export const hideLoader = () => $("#loader")?.classList.add("done");

// ---------- toasts + modal -----------------------------------------------------
export function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`; el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4200);
}
export function modal(html) {
  const el = document.createElement("div");
  el.className = "modal"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
  el.innerHTML = `<div class="modal-box"><button class="modal-close" aria-label="Close">×</button>${html}</div>`;
  const close = () => { el.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => e.key === "Escape" && close();
  el.addEventListener("click", (e) => { if (e.target === el || e.target.classList.contains("modal-close")) close(); });
  document.addEventListener("keydown", onKey);
  document.body.append(el);
  $(".modal-close", el).focus();
  return { el, close };
}

// ---------- cards and rows -------------------------------------------------------
export const detailsUrl = (item) => `details.html?type=${item.media_type}&id=${encodeURIComponent(item.id)}`;
export function card(item, { progress, removable } = {}) {
  return `<a class="card" href="${detailsUrl(item)}" aria-label="${esc(item.title)}">
    <div class="poster"><img src="${esc(posterOr(item.poster))}" alt="${esc(item.title)} poster" loading="lazy" decoding="async" width="342" height="513">
      ${item.media_type === "series" ? `<span class="badge">Series</span>` : ""}
      ${progress ? `<div class="card-progress"><i style="width:${Math.max(3, progress)}%"></i></div>` : ""}</div>
    ${removable ? `<button class="card-x" data-remove="${esc(removable)}" aria-label="Remove ${esc(item.title)}">${ICON.x}</button>` : ""}
    <div class="card-title">${esc(item.title)}</div>
    <div class="card-sub"><span>${item.year ?? "—"}</span>${item.rating ? `<span class="rating">★ ${item.rating}</span>` : ""}</div></a>`;
}
const SEE_ALL = { trending: "movies.html?sort=trending", "k-drama": "kdrama.html", "c-drama": "cdrama.html", anime: "anime.html",
  "japanese-movies": "movies.html?category=japanese-movies", "top-rated-movies": "movies.html?sort=rating", recent: "movies.html?sort=recent" };
export function row({ title, items, slug, see_all }) {
  const link = see_all || SEE_ALL[slug];
  return `<section class="row" ${slug ? `id="row-${esc(slug)}"` : ""} aria-label="${esc(title)}"><div class="row-head"><h2>${esc(title)}</h2>${link ? `<a href="${esc(link)}">See all</a>` : ""}</div>
    <div class="scroller-wrap"><button class="arrow prev" aria-label="Scroll left">‹</button><div class="scroller">${items.map((i) => card(i)).join("")}</div><button class="arrow next" aria-label="Scroll right">›</button></div></section>`;
}
export function wireScrollers(root = document) {
  $$(".scroller-wrap", root).forEach((w) => {
    const s = $(".scroller", w);
    $(".prev", w)?.addEventListener("click", () => s.scrollBy({ left: -s.clientWidth * 0.85, behavior: "smooth" }));
    $(".next", w)?.addEventListener("click", () => s.scrollBy({ left: s.clientWidth * 0.85, behavior: "smooth" }));
  });
}
export const skeletonGrid = (n = 12) => Array.from({ length: n }, () => `<div class="skeleton sk-card"></div>`).join("");
export const skeletonRow = () => `<section class="row"><div class="skeleton" style="height:26px;width:200px;margin-bottom:14px"></div><div class="scroller">${skeletonGrid(8)}</div></section>`;
export const emptyState = (title, text, action = "") => `<div class="empty"><h3>${esc(title)}</h3><p>${text}</p>${action}</div>`;
export const errorBox = (e) => `<div class="error-box" role="alert">${esc(e.message || e)}</div>`;

export const minutes = (m) => (m ? `${Math.floor(m / 60) ? Math.floor(m / 60) + "h " : ""}${m % 60}m` : "");
export const fmtDate = (s) => {
  if (!s) return "—";
  const d = new Date(s.length > 10 ? s.replace(" ", "T") + (/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? "" : "Z") : s + "T00:00:00");
  return isNaN(d) ? "—" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};
export const fmtTime = (sec) => { sec = Math.max(0, Math.floor(sec || 0)); const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0"); };

// ---------- watchlist toggle used on the details page ----------------------------------
/** Pass the current watchlist id (or null). Returns the new id (or null when removed). */
export async function toggleWatchlist(item, watchlistId) {
  if (!(await currentUser())) { location.href = loginUrl(); return watchlistId; }
  if (watchlistId) { await api(`/watchlist/${watchlistId}`, { method: "DELETE" }); toast("Removed from watchlist"); return null; }
  const added = await api("/watchlist", { method: "POST", body: { media_type: item.media_type, media_id: item.id } });
  toast("Added to watchlist", "success");
  return added.watchlist_id;
}
