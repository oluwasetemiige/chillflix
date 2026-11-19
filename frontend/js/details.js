import { api } from "./api.js";
import { mountShell, $, esc, icon, posterOr, minutes, fmtDate, toast, modal, errorBox, toggleWatchlist, wireScrollers, hideLoader, row } from "./ui.js";

await mountShell();
const params = new URLSearchParams(location.search);
const type = params.get("type") === "series" ? "series" : "movie";
const id = params.get("id");
const root = $("#detail");

async function init() {
  let d;
  try { d = await api(`/${type === "movie" ? "movies" : "series"}/${encodeURIComponent(id)}`); }
  catch (e) {
    hideLoader();
    root.innerHTML = `<div class="wrap page-top">${errorBox(e)}<p style="margin-top:16px"><a class="btn btn-ghost" href="index.html">Back home</a></p></div>`;
    return;
  }
  hideLoader();
  document.title = `${d.title} · CHILLFLIX`;
  let watchlistId = d.watchlist_id;
  const resume = d.progress && !d.progress.completed && d.progress.position > 10;
  const watchUrl = `watch.html?type=${type}&id=${encodeURIComponent(d.id)}${resume && d.progress.episode_id ? `&episode=${d.progress.episode_id}` : ""}`;
  const runtime = type === "movie" ? d.runtime : d.episode_runtime;
  const facts = [
    ["Release", d.release_date ? fmtDate(d.release_date) : d.year],
    ["Country", (d.countries || []).join(", ")],
    ["Language", d.language ? d.language.toUpperCase() : ""],
    [type === "movie" ? "Director" : "Created by", (d.directors || []).join(", ")],
    ["Runtime", runtime ? minutes(runtime) + (type === "series" ? " / episode" : "") : ""],
    ...(type === "series" ? [["Seasons", d.number_of_seasons], ["Episodes", d.number_of_episodes], ["Status", d.status]] : []),
  ].filter(([, v]) => v);

  root.innerHTML = `<section class="d-hero"><div class="bg"><img src="${esc(d.backdrop || posterOr(d.poster))}" alt=""></div>
    <div class="wrap d-grid"><div class="d-poster"><img src="${esc(posterOr(d.poster))}" alt="${esc(d.title)} poster"></div>
    <div class="d-info"><h1>${esc(d.title)}</h1>
      <div class="meta">${d.rating ? `<span class="rating">★ ${d.rating}</span>` : ""}${d.year ? `<span>${d.year}</span>` : ""}${(d.countries || []).length ? `<span>${esc(d.countries.join(", "))}</span>` : ""}${runtime ? `<span>${minutes(runtime)}</span>` : ""}${d.genres.map((g) => `<span class="chip">${esc(g)}</span>`).join("")}</div>
      <p class="synopsis">${esc(d.overview || "No description available.")}</p>
      <div class="actions"><a class="btn btn-primary" href="${watchUrl}">${icon("play")} ${resume ? "Resume" : "Watch Now"}</a>
        <button class="btn btn-ghost" id="wl">${icon(watchlistId ? "check" : "plus")} <span>${watchlistId ? "In Watchlist" : "Add to Watchlist"}</span></button>
        ${d.trailer ? `<button class="btn btn-ghost" id="trailer">${icon("film")} Trailer</button>` : ""}
        <button class="btn btn-ghost" id="share">${icon("share")} Share</button></div>
      ${type === "movie" && !d.playable ? `<p class="muted" style="margin-top:12px">Streaming source currently unavailable.</p>` : ""}</div></div></section>
    <div class="wrap"><dl class="facts">${facts.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
      ${type === "series" ? `<section class="section" id="seasonBox"></section>` : ""}
      ${d.cast.length ? `<section class="section"><h2>Cast</h2><div class="cast">${d.cast.map((c) => `<figure>${c.photo ? `<img src="${esc(c.photo)}" alt="" loading="lazy">` : `<div class="noimg" aria-hidden="true">${esc((c.name || "?")[0])}</div>`}<strong>${esc(c.name)}</strong><span>${esc(c.character || "")}</span></figure>`).join("")}</div></section>` : ""}
      ${d.similar.length ? row({ title: "Similar titles", items: d.similar, slug: "similar" }) : ""}</div>`;
  wireScrollers(root);

  $("#wl").addEventListener("click", async (e) => {
    const b = e.currentTarget; b.disabled = true;
    try {
      watchlistId = await toggleWatchlist(d, watchlistId);
      b.innerHTML = `${icon(watchlistId ? "check" : "plus")} <span>${watchlistId ? "In Watchlist" : "Add to Watchlist"}</span>`;
    } catch (err) { toast(err.message, "error"); }
    b.disabled = false;
  });
  $("#trailer")?.addEventListener("click", () => modal(`<iframe src="${esc(d.trailer.embed_url)}?autoplay=1" title="Trailer" allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe>`));
  $("#share").addEventListener("click", async () => {
    const data = { title: d.title, text: `Watch ${d.title} on CHILLFLIX`, url: location.href };
    try {
      if (navigator.share) await navigator.share(data);
      else { await navigator.clipboard.writeText(location.href); toast("Link copied", "success"); }
    } catch (err) { if (err.name !== "AbortError") toast("Could not share. Copy the link from the address bar.", "error"); }
  });
  if (type === "series") renderSeasons(d);
}

function renderSeasons(d) {
  const box = $("#seasonBox");
  if (!d.seasons.length) { box.innerHTML = `<h2>Episodes</h2><p class="muted">Season information is not available yet.</p>`; return; }
  const saved = Number(sessionStorage.getItem("season:" + d.id));
  const initial = d.seasons.some((s) => s.season_number === saved) ? saved : d.seasons.find((s) => s.season_number > 0)?.season_number ?? d.seasons[0].season_number;
  box.innerHTML = `<h2>Episodes</h2><div class="season-bar"><label class="sr-only" for="seasonSel">Season</label><select id="seasonSel">${d.seasons.map((s) => `<option value="${s.season_number}" ${s.season_number === initial ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></div><div class="episodes" id="eps"></div>`;
  const load = async () => {
    const n = $("#seasonSel").value; sessionStorage.setItem("season:" + d.id, n);
    $("#eps").innerHTML = `<div class="skeleton" style="height:90px"></div>`;
    try {
      const { episodes } = await api(`/series/${d.id}/seasons/${n}`);
      $("#eps").innerHTML = episodes.length ? episodes.map((e) => `<article class="ep"><div class="still">${e.still ? `<img src="${esc(e.still)}" alt="" loading="lazy">` : ""}</div>
        <div><h3>${e.episode_number}. ${esc(e.name)}</h3><p>${esc(e.overview)}</p><p style="margin-top:4px">${e.air_date ? fmtDate(e.air_date) : ""}${e.runtime ? " · " + e.runtime + " min" : ""}</p></div>
        <a class="btn btn-ghost btn-sm" href="watch.html?type=series&id=${encodeURIComponent(d.id)}&episode=${e.id}">${icon("play")} Watch</a></article>`).join("")
        : `<p class="muted">Episode details for this season are not available yet.</p>`;
    } catch (err) { $("#eps").innerHTML = errorBox(err); }
  };
  $("#seasonSel").addEventListener("change", load); load();
}
init();
