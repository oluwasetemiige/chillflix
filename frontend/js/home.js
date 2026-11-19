import { api, currentUser } from "./api.js";
import { mountShell, $, esc, icon, row, card, wireScrollers, skeletonRow, emptyState, errorBox, detailsUrl, posterOr, hideLoader } from "./ui.js";

const user = await mountShell();
const rowsEl = $("#rows");
rowsEl.innerHTML = skeletonRow() + skeletonRow();

function heroHTML(items) {
  return `${items.map((it, i) => `<div class="hero-slide ${i ? "" : "active"}" data-i="${i}"><img src="${esc(it.backdrop || posterOr(it.poster))}" alt="" ${i ? 'loading="lazy"' : 'fetchpriority="high"'}></div>`).join("")}
  <div class="wrap hero-body"><div id="heroText"></div>
    <div class="reel" role="tablist" aria-label="Featured titles">${items.map((it, i) => `<button role="tab" data-i="${i}" aria-label="${esc(it.title)}" aria-selected="${i === 0}" class="${i ? "" : "active"}"><img src="${esc(it.backdrop_small || it.backdrop || posterOr(it.poster))}" alt=""><i></i></button>`).join("")}</div></div>`;
}

function startHero(items) {
  const hero = $("#hero"); hero.innerHTML = heroHTML(items);
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let idx = 0, timer;
  const show = (i) => {
    idx = (i + items.length) % items.length; const it = items[idx];
    hero.querySelectorAll(".hero-slide").forEach((s) => s.classList.toggle("active", +s.dataset.i === idx));
    hero.querySelectorAll(".reel button").forEach((b) => { const on = +b.dataset.i === idx; b.classList.remove("active"); void b.offsetWidth; b.classList.toggle("active", on); b.setAttribute("aria-selected", on); });
    $("#heroText").innerHTML = `<h1>${esc(it.title)}</h1>
      <div class="meta">${it.rating ? `<span class="rating">★ ${it.rating}</span>` : ""}${it.year ? `<span>${it.year}</span>` : ""}${(it.genres || []).slice(0, 3).map((g) => `<span class="chip">${esc(g)}</span>`).join("")}${it.media_type === "series" ? `<span class="chip">Series</span>` : ""}</div>
      <p class="synopsis">${esc(it.overview || "")}</p>
      <div class="actions"><a class="btn btn-primary" href="watch.html?type=${it.media_type}&id=${encodeURIComponent(it.id)}">${icon("play")} Watch Now</a>
      <a class="btn btn-ghost" href="${detailsUrl(it)}">${icon("info")} More Information</a></div>`;
  };
  const schedule = () => { clearTimeout(timer); if (!reduced && items.length > 1) timer = setTimeout(() => { show(idx + 1); schedule(); }, 7000); };
  hero.querySelectorAll(".reel button").forEach((b) => b.addEventListener("click", () => { show(+b.dataset.i); schedule(); }));
  hero.addEventListener("mouseenter", () => { hero.classList.add("paused"); clearTimeout(timer); });
  hero.addEventListener("mouseleave", () => { hero.classList.remove("paused"); schedule(); });
  document.addEventListener("visibilitychange", () => (document.hidden ? clearTimeout(timer) : schedule()));
  show(0); schedule();
}

try {
  const home = await api("/home");
  hideLoader();
  if (home.hero.length) startHero(home.hero); else { $("#hero").remove(); rowsEl.classList.add("page-top"); }
  const personal = [];
  if (user) {
    const [cont, rec] = await Promise.allSettled([api("/history?continue=1&limit=20"), api("/recommendations")]);
    if (cont.status === "fulfilled" && cont.value.items.length) {
      const pct = (h) => (h.duration ? Math.round((h.position / h.duration) * 100) : 0);
      personal.push(`<section class="row" id="row-continue" aria-label="Continue Watching"><div class="row-head"><h2>Continue Watching</h2><a href="profile.html#history">History</a></div><div class="scroller-wrap"><button class="arrow prev" aria-label="Scroll left">‹</button><div class="scroller">${cont.value.items.map((h) => card(h, { progress: pct(h) })).join("")}</div><button class="arrow next" aria-label="Scroll right">›</button></div></section>`);
    }
    if (rec.status === "fulfilled" && rec.value.items?.length) {
      personal.push(row({ title: "Recommended For You", items: rec.value.items, slug: "recommended" }));
    }
  }
  const trending = home.rows.find((r) => r.slug === "trending");
  const html = [];
  if (trending) html.push(row(trending));
  html.push(...personal);
  html.push(...home.rows.filter((r) => r.slug !== "trending").map(row));
  if (!html.length) {
    rowsEl.innerHTML = emptyState("The catalogue is empty", user?.role === "admin"
      ? `Run your first synchronization to import titles from TMDB.<br><a class="btn btn-primary" href="admin.html#sync">Open admin dashboard</a>`
      : `Titles will appear here once an administrator synchronizes the catalogue.`);
    $("#hero")?.remove(); rowsEl.classList.add("page-top");
  } else {
    rowsEl.innerHTML = html.join(""); wireScrollers(rowsEl);
  }
} catch (e) {
  hideLoader(); $("#hero")?.remove(); rowsEl.classList.add("page-top"); rowsEl.innerHTML = errorBox(e);
}
