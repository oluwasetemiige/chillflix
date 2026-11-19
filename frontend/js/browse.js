// Powers movies / series / kdrama / cdrama / anime pages.
// The page's <body data-section="kdrama"> decides which catalogue slice is listed.
import { api } from "./api.js";
import { mountShell, $, esc, card, skeletonGrid, emptyState, errorBox } from "./ui.js";

await mountShell();

const SECTIONS = {
  movies: { path: "/movies" },
  series: { path: "/series" },
  kdrama: { path: "/series", category: "k-drama" },
  cdrama: { path: "/series", category: "c-drama" },
  anime: { path: "/catalog", category: "anime" },
};
const section = SECTIONS[document.body.dataset.section] || SECTIONS.movies;
const grid = $("#grid"), more = $("#more"), count = $("#count");
const params = new URLSearchParams(location.search);
const category = section.category || params.get("category") || "";
const state = { genre: params.get("genre") || "", sort: params.get("sort") || "" };
let page = 1, loading = false;

try {
  const { items } = await api("/genres");
  $("#genre").innerHTML = `<option value="">All genres</option>` + items.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join("");
  $("#genre").value = state.genre;
} catch { /* the page still works without the genre filter */ }
$("#sort").value = state.sort;

async function load(reset) {
  if (loading) return;
  loading = true;
  if (reset) { page = 1; grid.innerHTML = skeletonGrid(12); more.innerHTML = ""; }
  try {
    const qs = new URLSearchParams({ page, limit: 24 });
    if (category) qs.set("category", category);
    if (state.genre) qs.set("genre", state.genre);
    if (state.sort) qs.set("sort", state.sort);
    const res = await api(`${section.path}?${qs}`);
    if (reset) grid.innerHTML = "";
    if (!res.items.length && reset) {
      grid.innerHTML = emptyState("Nothing here yet", state.genre
        ? "No titles match this genre. Try another one."
        : "This section fills up after an administrator synchronizes the catalogue.");
    } else {
      grid.insertAdjacentHTML("beforeend", res.items.map((i) => card(i)).join(""));
    }
    count.textContent = res.total ? `${res.total} titles` : "";
    more.innerHTML = page < res.pages ? `<button class="btn btn-ghost" id="moreBtn">Load more</button>` : "";
    $("#moreBtn")?.addEventListener("click", () => { page++; load(false); });
  } catch (e) {
    grid.innerHTML = errorBox(e);
  }
  loading = false;
}

for (const id of ["genre", "sort"]) {
  $("#" + id).addEventListener("change", (e) => {
    state[id] = e.target.value;
    const u = new URL(location);
    for (const k of ["genre", "sort"]) state[k] ? u.searchParams.set(k, state[k]) : u.searchParams.delete(k);
    history.replaceState(null, "", u);
    load(true);
  });
}
load(true);
