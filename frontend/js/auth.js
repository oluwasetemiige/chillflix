// Login, register, forgot-password and reset-password pages. <body data-mode="login|register|forgot|reset">
import { api, setToken, currentUser } from "./api.js";
import { mountShell, $, esc } from "./ui.js";

await mountShell();
const mode = document.body.dataset.mode;
const form = $("#authForm"), errBox = $("#formError"), submit = $("#submit");
const next = new URLSearchParams(location.search).get("next");
const safeNext = next && /^[a-z0-9_-]+\.html(\?[^\s]*)?$/i.test(next) ? next : "index.html";

if ((mode === "login" || mode === "register") && (await currentUser())) location.replace(safeNext);

const showError = (msg, details = {}) => {
  errBox.textContent = msg || "";
  form.querySelectorAll("input").forEach((i) => i.setAttribute("aria-invalid", details[i.name] ? "true" : "false"));
};

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("");
  const f = Object.fromEntries(new FormData(form));
  if (mode === "register" && f.password !== f.confirm) return showError("The two passwords don't match.");
  if (mode === "reset" && f.password !== f.confirm) return showError("The two passwords don't match.");
  submit.disabled = true;
  const label = submit.textContent; submit.textContent = "Please wait…";
  try {
    if (mode === "login") {
      const r = await api("/auth/login", { method: "POST", body: { identifier: f.identifier, password: f.password }, auth: false });
      setToken(r.token); location.href = safeNext;
    } else if (mode === "register") {
      const r = await api("/auth/register", { method: "POST", body: { username: f.username, email: f.email, password: f.password }, auth: false });
      setToken(r.token); location.href = safeNext;
    } else if (mode === "forgot") {
      const r = await api("/auth/forgot", { method: "POST", body: { email: f.email }, auth: false });
      form.hidden = true;
      $("#done").hidden = false;
      $("#doneText").textContent = r.message;
      if (r.dev_reset_url) $("#devLink").innerHTML = `<a class="btn btn-ghost" href="${esc(r.dev_reset_url)}">Open the reset link (development only)</a>`;
    } else if (mode === "reset") {
      const token = new URLSearchParams(location.search).get("token") || "";
      const r = await api("/auth/reset", { method: "POST", body: { token, password: f.password }, auth: false });
      form.hidden = true; $("#done").hidden = false; $("#doneText").textContent = r.message;
    }
  } catch (err) {
    showError(err.message, err.details || {});
  }
  submit.disabled = false; submit.textContent = label;
});
