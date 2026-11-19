import { api } from "./api.js";
import { mountShell, $, $$, esc, card, skeletonGrid, emptyState, errorBox } from "./ui.js";

await mountShell();
const input = $("#q"), results = $("#results"), summary = $("#summary");
const params = new URLSearchParams(location.search);
let type = params.get("type") || "", timer, seq = 0;
input.value = params.get("q") || "";

const syncChips = () => $$("#types button").forEach((b) => b.classList.toggle("on", b.dataset.type === type));

async function run() {
  const q = input.value.trim(), mine = ++seq;
  const u = new URL(location);
  q ? u.searchParams.set("q", q) : u.searchParams.delete("q");
  type ? u.searchParams.set("type", type) : u.searchParams.delete("type");
  history.replaceState(null, "", u);
  if (q.length < 2) {
    summary.textContent = "";
    results.innerHTML = emptyState("Search CHILLFLIX", "Type at least two letters of a title.");
    return;
  }
  results.innerHTML = `<div class="grid">${skeletonGrid(12)}</div>`;
  try {
    const qs = new URLSearchParams({ q }); if (type) qs.set("type", type);
    const res = await api(`/movies/search?${qs}`);
    if (mine !== seq) return;
    summary.textContent = `${res.total} result${res.total === 1 ? "" : "s"}`;
    results.innerHTML = res.items.length
      ? `<div class="grid">${res.items.map((i) => card(i)).join("")}</div>`
      : emptyState("No matches", `Nothing found for “${esc(q)}”. Check the spelling or try a shorter search.`);
  } catch (e) { if (mine === seq) results.innerHTML = errorBox(e); }
}
input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 300); });
$("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); run(); });
$$("#types button").forEach((b) => b.addEventListener("click", () => { type = b.dataset.type; syncChips(); run(); }));
syncChips(); run();
