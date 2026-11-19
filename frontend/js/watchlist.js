import { api, requireUser } from "./api.js";
import { mountShell, $, card, emptyState, errorBox, toast, skeletonGrid } from "./ui.js";

await requireUser();
await mountShell();
const box = $("#list");
box.innerHTML = `<div class="grid">${skeletonGrid(8)}</div>`;

async function load() {
  try {
    const { items } = await api("/watchlist");
    box.innerHTML = items.length
      ? `<div class="grid">${items.map((i) => card(i, { removable: i.watchlist_id })).join("")}</div>`
      : emptyState("Your watchlist is empty", "Tap “Add to Watchlist” on any title to save it here.", `<a class="btn btn-primary" href="index.html">Discover titles</a>`);
  } catch (e) { box.innerHTML = errorBox(e); }
}
box.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-remove]");
  if (!btn) return;
  e.preventDefault();
  try { await api(`/watchlist/${btn.dataset.remove}`, { method: "DELETE" }); toast("Removed from watchlist"); load(); }
  catch (err) { toast(err.message, "error"); }
});
load();
