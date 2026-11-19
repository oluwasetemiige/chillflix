import { api, currentUser, loginUrl, getToken } from "./api.js";
import { mountShell, $, esc, toast, fmtDate, errorBox, hideLoader } from "./ui.js";

await mountShell();
const root = $("#premium");
const fmtMoney = (amount, currency) => {
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(amount); }
  catch { return `${currency} ${amount}`; }
};

// Back from Paystack? Verify on the server before anything changes.
const ref = new URLSearchParams(location.search).get("reference") || new URLSearchParams(location.search).get("trxref");
if (ref && getToken()) {
  try {
    const r = await api(`/premium/verify?reference=${encodeURIComponent(ref)}`);
    toast(r.membership?.is_premium ? "Payment confirmed. Welcome to Premium!" : "Payment not confirmed yet.", r.membership?.is_premium ? "success" : "error");
  } catch (e) { toast(e.message, "error"); }
  history.replaceState(null, "", "premium.html");
}

async function render() {
  const user = await currentUser(true);
  const [plans, status, pays] = await Promise.all([
    api("/premium/plans"),
    user ? api("/premium/status") : null,
    user ? api("/premium/payments") : null,
  ]);
  hideLoader();
  const m = status?.membership;
  const statusText = !user ? "Log in to see your membership"
    : m.is_premium ? `Premium until ${fmtDate(m.ends_at)}` : "You're on the Free plan";
  const enabled = plans.payments_enabled;
  const perks = plans.features;

  root.innerHTML = `<section class="prem-hero"><h1>CHILLFLIX Premium</h1><p>Sharper playback, smarter recommendations and a look that's yours.</p>
    <div class="status-pill ${m?.is_premium ? "on" : ""}" id="status">${esc(statusText)}</div></section>
    <div class="wrap">
      <div class="plans">
        <article class="plan"><h2>Free</h2><div class="price">${fmtMoney(0, plans.currency)}<small> forever</small></div>
          <ul>${perks.free.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
          ${user ? `<button class="btn btn-ghost" disabled>${m.is_premium ? "Included" : "Your current plan"}</button>` : `<a class="btn btn-ghost" href="register.html">Create free account</a>`}</article>
        ${plans.plans.map((p, i) => `<article class="plan ${p.id === "yearly" ? "feat" : ""}">${p.id === "yearly" ? `<span class="tag">Best value</span>` : ""}
          <h2>${esc(p.name)}</h2><div class="price">${fmtMoney(p.price, p.currency)}<small> / ${p.days === 365 ? "year" : "month"}</small></div>
          <ul>${perks.premium.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
          <button class="btn btn-primary" data-plan="${p.id}" ${user && !enabled ? "disabled" : ""}>${m?.is_premium ? "Extend Premium" : "Upgrade"}</button></article>`).join("")}
      </div>
      ${user && !enabled ? `<p class="muted" style="text-align:center;margin:-30px 0 40px">Payments aren't switched on for this site yet. The administrator needs to add a Paystack key.</p>` : ""}
      <section class="section"><h2 style="margin-bottom:14px">Compare plans</h2><div class="table-wrap"><table><thead><tr><th>Feature</th><th>Free</th><th>Premium</th></tr></thead><tbody>
        ${[["Standard catalogue", 1, 1], ["Basic discovery and search", 1, 1], ["Personal watchlist and history", 1, 1],
           ["Colour themes", 0, 1], ["Advanced recommendations", 0, 1], ["1080p quality preference", 0, 1], ["Premium-only streams (where available)", 0, 1]]
          .map(([f, a, b]) => `<tr><td>${f}</td><td class="${a ? "yes" : "no"}">${a ? "✓" : "—"}</td><td class="${b ? "yes" : "no"}">${b ? "✓" : "—"}</td></tr>`).join("")}</tbody></table></div></section>
      ${user ? `<section class="section"><h2 style="margin-bottom:14px">Payment history</h2>${pays.items.length ? `<div class="table-wrap"><table><thead><tr><th>Date</th><th>Plan</th><th>Amount</th><th>Status</th><th>Reference</th></tr></thead><tbody>
        ${pays.items.map((p) => `<tr><td>${fmtDate(p.paid_at || p.created_at)}</td><td>${esc(p.plan)}</td><td>${fmtMoney(p.amount_major, p.currency)}</td><td><span class="pill ${esc(p.status)}">${esc(p.status)}</span></td><td><small>${esc(p.reference)}</small></td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No payments yet.</p>`}</section>` : ""}
    </div>`;

  root.querySelectorAll("[data-plan]").forEach((b) => b.addEventListener("click", async () => {
    if (!user) { location.href = loginUrl("premium.html"); return; }
    b.disabled = true;
    try {
      const r = await api("/premium/checkout", { method: "POST", body: { plan: b.dataset.plan } });
      location.href = r.authorization_url;
    } catch (e) { toast(e.message, "error"); b.disabled = false; }
  }));
}
try { await render(); } catch (e) { hideLoader(); root.innerHTML = `<div class="wrap page-top">${errorBox(e)}</div>`; }
