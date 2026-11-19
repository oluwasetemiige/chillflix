// Small fetch wrapper + login session helpers. Every page talks to the backend through here.
import { API_BASE } from "./config.js";

const TOKEN_KEY = "chillflix_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

export class ApiError extends Error {
  constructor(message, status, code, details) { super(message); this.status = status; this.code = code; this.details = details; }
}

/** api("/movies?limit=5")  or  api("/watchlist", { method: "POST", body: {...} })  ->  resolves to response.data */
export async function api(path, { method = "GET", body, auth = true, raw = false } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(API_BASE + path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError("Cannot reach the CHILLFLIX server. Check your connection and the API_BASE in js/config.js.", 0, "network");
  }
  let json = null;
  try { json = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok || !json || json.success === false) {
    if (res.status === 401 && token) { setToken(null); sessionProfile = undefined; }
    throw new ApiError(json?.error?.message || `Request failed (${res.status})`, res.status, json?.error?.code, json?.error?.details);
  }
  return raw ? json : json.data;
}

// ---- session ---------------------------------------------------------------
let sessionProfile; // undefined = not loaded yet, null = logged out
/** The full /users/profile payload: { user, preferences, counts }. */
export async function currentProfile(force = false) {
  if (!getToken()) return null;
  if (sessionProfile !== undefined && !force) return sessionProfile;
  try { sessionProfile = await api("/users/profile"); } catch { sessionProfile = null; }
  if (sessionProfile?.preferences) applyTheme(sessionProfile.preferences.accent_theme);
  return sessionProfile;
}
/** The signed-in user (or null). `is_premium` is added for convenience. */
export async function currentUser(force = false) {
  const p = await currentProfile(force);
  return p ? { ...p.user, is_premium: !!p.user.subscription?.is_premium } : null;
}
export function applyTheme(theme) {
  const name = theme && theme !== "violet" ? theme : "";
  name ? localStorage.setItem("chillflix_theme", name) : localStorage.removeItem("chillflix_theme");
  document.documentElement.dataset.theme = name;
}
applyTheme(localStorage.getItem("chillflix_theme") || "");
export async function logout() {
  try { await api("/auth/logout", { method: "POST" }); } catch { /* token may already be invalid */ }
  setToken(null); sessionProfile = undefined; applyTheme("");
  location.href = "index.html";
}
export function loginUrl(next = location.pathname.split("/").pop() + location.search) {
  return `login.html?next=${encodeURIComponent(next)}`;
}
/** Redirects to the login page when logged out. Returns the user otherwise. */
export async function requireUser({ admin = false } = {}) {
  const user = await currentUser();
  if (!user) { location.replace(loginUrl()); return new Promise(() => {}); }
  if (admin && user.role !== "admin") { location.replace("index.html"); return new Promise(() => {}); }
  return user;
}
