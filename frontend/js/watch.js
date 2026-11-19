// The player page. Plays only what the backend reports as an authorised source. Nothing is ever invented.
import { api, currentUser, loginUrl } from "./api.js";
import { mountShell, $, esc, icon, fmtTime, errorBox, hideLoader, posterOr } from "./ui.js";

const user = await mountShell();
const params = new URLSearchParams(location.search);
const type = params.get("type") === "series" ? "series" : "movie";
const id = params.get("id");
const root = $("#watch");
const PAUSE = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>`;
const HLS_CDN = "https://cdn.jsdelivr.net/npm/hls.js@1.5.13/dist/hls.min.js";

let info;
try { info = await api(`/watch/${type}/${encodeURIComponent(id)}?episode=${encodeURIComponent(params.get("episode") || 0)}`); }
catch (e) { hideLoader(); root.innerHTML = `<div class="wrap">${errorBox(e)}<p style="margin-top:16px"><a class="btn btn-ghost" href="index.html">Back home</a></p></div>`; throw e; }
hideLoader();

const t = info.title, ep = info.episode;
const heading = ep ? `${t.title} · S${ep.season_number} E${ep.episode_number}${ep.name ? " · " + ep.name : ""}` : t.title;
document.title = `${heading} · CHILLFLIX`;
const watchUrl = (e) => `watch.html?type=series&id=${encodeURIComponent(t.id)}&episode=${e.id}`;

const sidePanel = info.episodes.length
  ? `<aside class="ep-panel" aria-label="Episodes">${info.episodes.map((e) => `<button data-ep="${e.id}" class="${ep && e.id === ep.id ? "on" : ""}">${e.episode_number}. ${esc(e.name || "Episode " + e.episode_number)}</button>`).join("")}</aside>` : "";
const nav = `<div class="watch-nav"><a class="btn btn-ghost btn-sm" href="details.html?type=${type}&id=${encodeURIComponent(t.id)}">${icon("info")} Details</a>
  ${info.previous_episode ? `<a class="btn btn-ghost btn-sm" href="${watchUrl(info.previous_episode)}">Previous episode</a>` : ""}
  ${info.next_episode ? `<a class="btn btn-ghost btn-sm" id="nextEp" href="${watchUrl(info.next_episode)}">Next episode</a>` : ""}</div>`;

root.innerHTML = `<div class="wrap"><div class="watch-grid ${sidePanel ? "" : "solo"}"><div><div id="stage"></div>
  <h1 class="watch-title">${esc(heading)}</h1>${nav}</div>${sidePanel}</div></div>`;
$("#watch").addEventListener("click", (e) => { const b = e.target.closest("[data-ep]"); if (b) location.href = watchUrl({ id: b.dataset.ep }); });

const stage = $("#stage");
if (!info.available) {
  const locked = info.locked_count > 0;
  stage.innerHTML = `<div class="unavailable" style="background-image:linear-gradient(#08080Dcc,#08080Dcc),url('${esc(t.backdrop || posterOr(t.poster))}')"><div>
    <h2>${locked ? "This title is a Premium stream" : "Streaming source currently unavailable."}</h2>
    <p class="muted">${locked ? "Upgrade to watch higher-quality sources." : "We don't have an authorised stream for this title yet. Check back later."}</p>
    ${locked ? `<p style="margin-top:14px"><a class="btn btn-primary" href="premium.html">See Premium</a></p>` : ""}</div></div>`;
} else {
  await startPlayer();
}

async function loadHls() {
  if (window.Hls) return window.Hls;
  await new Promise((ok, no) => { const s = document.createElement("script"); s.src = HLS_CDN; s.onload = ok; s.onerror = no; document.head.append(s); });
  return window.Hls;
}

async function startPlayer() {
  const sources = info.sources;
  const prefs = user ? (await api("/users/profile").catch(() => null))?.preferences : null;
  const languages = [...new Set(sources.map((s) => s.language))];
  let current = sources.find((s) => s.quality === prefs?.default_quality) || sources[0];
  stage.innerHTML = `<div class="player" id="player"><video id="vid" playsinline preload="metadata" poster="${esc(t.backdrop || "")}"></video>
    <div class="pl-center"><button class="pl-big" id="big" aria-label="Play">${icon("play")}</button></div><div class="pl-msg hidden" id="msg"></div>
    <div class="pl-ctrl" id="ctrl"><div class="pl-bar" id="bar" role="slider" aria-label="Seek" tabindex="0"><div class="pl-track"><div class="buf" id="buf"></div><div class="played" id="played"></div><div class="thumb" id="thumb"></div></div></div>
      <div class="pl-row"><button class="pl-btn" id="pp" aria-label="Play or pause">${icon("play")}</button>
        <button class="pl-btn" id="mute" aria-label="Mute"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H3v6h3l5 4zM16 9a4 4 0 0 1 0 6"/></svg></button>
        <input class="pl-vol" id="vol" type="range" min="0" max="1" step="0.05" value="1" aria-label="Volume">
        <span class="pl-time" id="time">0:00 / 0:00</span><span class="sp"></span>
        <button class="pl-btn" id="settings" aria-label="Settings" aria-haspopup="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2-1.2L14.2 3h-4l-.4 2.6a7 7 0 0 0-2 1.2l-2.3-.9-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-.9c.6.5 1.3.9 2 1.2l.4 2.6h4l.4-2.6c.7-.3 1.4-.7 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/></svg></button>
        <button class="pl-btn" id="fs" aria-label="Fullscreen"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button></div></div></div>`;
  const player = $("#player"), v = $("#vid");
  let hls = null, idleTimer, lastSave = 0, savedAt = 0;
  const flash = (text) => { const m = $("#msg"); m.textContent = text; m.classList.remove("hidden"); clearTimeout(flash.t); flash.t = setTimeout(() => m.classList.add("hidden"), 2200); };

  async function attach(source, startAt = 0) {
    if (hls) { hls.destroy(); hls = null; }
    v.querySelectorAll("track").forEach((n) => n.remove());
    for (const sub of source.subtitles || []) {
      const tr = document.createElement("track");
      Object.assign(tr, { kind: "subtitles", label: sub.label, srclang: sub.lang, src: sub.url });
      if (prefs?.subtitle_language === sub.lang) tr.default = true;
      v.append(tr);
    }
    const seek = () => { if (startAt) v.currentTime = startAt; };
    v.addEventListener("loadedmetadata", seek, { once: true });
    try {
      if (source.type === "hls" && !v.canPlayType("application/vnd.apple.mpegurl")) {
        const Hls = await loadHls();
        if (!Hls.isSupported()) throw new Error("HLS is not supported in this browser.");
        hls = new Hls(); hls.loadSource(source.url); hls.attachMedia(v);
        hls.on(Hls.Events.ERROR, (_, data) => { if (data.fatal) flash("Playback error. Try another quality."); });
      } else v.src = source.url;
    } catch (err) { flash(err.message || "Could not start playback."); }
  }

  const resume = user ? await api(`/history/position?media_type=${type}&media_id=${t.id}&episode_id=${ep ? ep.id : 0}`).catch(() => null) : null;
  await attach(current, resume?.position || 0);
  if (resume?.position > 10) flash(`Resuming from ${fmtTime(resume.position)}`);

  const toggle = () => (v.paused ? v.play().catch(() => flash("Tap play to start.")) : v.pause());
  $("#big").onclick = $("#pp").onclick = toggle;
  v.addEventListener("click", toggle);
  v.addEventListener("play", () => { $("#big").parentElement.classList.add("hidden"); $("#pp").innerHTML = PAUSE; });
  v.addEventListener("pause", () => { $("#big").parentElement.classList.remove("hidden"); $("#pp").innerHTML = icon("play"); save(true); });
  v.addEventListener("ended", () => { save(true); if (prefs?.autoplay_next !== false && info.next_episode) location.href = watchUrl(info.next_episode); });
  $("#vol").oninput = (e) => { v.volume = +e.target.value; v.muted = v.volume === 0; };
  $("#mute").onclick = () => { v.muted = !v.muted; };
  $("#fs").onclick = () => (document.fullscreenElement ? document.exitFullscreen() : (player.requestFullscreen || player.webkitRequestFullscreen)?.call(player));
  document.addEventListener("fullscreenchange", () => player.classList.toggle("fs", !!document.fullscreenElement));

  const bar = $("#bar");
  const seekTo = (clientX) => { const r = bar.getBoundingClientRect(); v.currentTime = Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * (v.duration || 0); };
  bar.addEventListener("pointerdown", (e) => { bar.setPointerCapture(e.pointerId); seekTo(e.clientX); bar.onpointermove = (m) => seekTo(m.clientX); });
  bar.addEventListener("pointerup", () => { bar.onpointermove = null; });
  bar.addEventListener("keydown", (e) => { if (e.key === "ArrowRight") v.currentTime += 5; if (e.key === "ArrowLeft") v.currentTime -= 5; });
  v.addEventListener("timeupdate", () => {
    const d = v.duration || 0, p = d ? (v.currentTime / d) * 100 : 0;
    $("#played").style.width = p + "%"; $("#thumb").style.left = p + "%";
    $("#time").textContent = `${fmtTime(v.currentTime)} / ${fmtTime(d)}`;
    bar.setAttribute("aria-valuenow", Math.round(p));
    if (Date.now() - lastSave > 15000) save();
  });
  v.addEventListener("progress", () => { if (v.buffered.length && v.duration) $("#buf").style.width = (v.buffered.end(v.buffered.length - 1) / v.duration) * 100 + "%"; });
  v.addEventListener("waiting", () => flash("Buffering…"));

  async function save(force) {
    if (!user || !v.duration || (!force && Date.now() - savedAt < 5000)) return;
    lastSave = savedAt = Date.now();
    api("/history", { method: "POST", body: { media_type: type, media_id: t.id, episode_id: ep ? ep.id : 0, position: Math.floor(v.currentTime), duration: Math.floor(v.duration) } }).catch(() => {});
  }
  addEventListener("pagehide", () => save(true));
  document.addEventListener("visibilitychange", () => document.hidden && save(true));

  // settings menu: speed, quality, language, subtitles
  const menuBtn = $("#settings");
  menuBtn.onclick = (e) => {
    e.stopPropagation();
    const open = $(".pl-menu", player); if (open) return open.remove();
    const speeds = [0.5, 0.75, 1, 1.25, 1.5, 2];
    const qualities = sources.filter((s) => s.language === current.language);
    const tracks = [...v.textTracks];
    const m = document.createElement("div"); m.className = "pl-menu"; m.addEventListener("click", (ev) => ev.stopPropagation());
    m.innerHTML = `<h4>Speed</h4>${speeds.map((s) => `<button data-speed="${s}" class="${v.playbackRate === s ? "on" : ""}">${s === 1 ? "Normal" : s + "×"}</button>`).join("")}
      <h4>Quality</h4>${qualities.length > 1 ? qualities.map((s) => `<button data-src="${s.id}" class="${s.id === current.id ? "on" : ""}">${esc(s.quality)}</button>`).join("") : `<button disabled>${esc(current.quality)} (only option)</button>`}
      ${languages.length > 1 ? `<h4>Language</h4>${languages.map((l) => `<button data-lang="${esc(l)}" class="${l === current.language ? "on" : ""}">${esc(l)}</button>`).join("")}` : ""}
      <h4>Subtitles</h4>${tracks.length ? `<button data-sub="-1">Off</button>` + tracks.map((tr, i) => `<button data-sub="${i}" class="${tr.mode === "showing" ? "on" : ""}">${esc(tr.label)}</button>`).join("") : `<button disabled>None available</button>`}`;
    m.addEventListener("click", async (ev) => {
      const b = ev.target.closest("button"); if (!b || b.disabled) return;
      if (b.dataset.speed) v.playbackRate = +b.dataset.speed;
      if (b.dataset.src || b.dataset.lang) {
        const pick = b.dataset.src ? sources.find((s) => String(s.id) === b.dataset.src)
          : sources.find((s) => s.language === b.dataset.lang && s.quality === current.quality) || sources.find((s) => s.language === b.dataset.lang);
        if (pick && pick.id !== current.id) { const at = v.currentTime, wasPaused = v.paused; current = pick; await attach(pick, at); if (!wasPaused) v.play().catch(() => {}); }
      }
      if (b.dataset.sub !== undefined) [...v.textTracks].forEach((tr, i) => { tr.mode = i === +b.dataset.sub ? "showing" : "disabled"; });
      m.remove();
    });
    player.append(m);
  };
  document.addEventListener("click", () => $(".pl-menu", player)?.remove());

  const wake = () => { player.classList.remove("idle"); clearTimeout(idleTimer); idleTimer = setTimeout(() => !v.paused && player.classList.add("idle"), 2800); };
  ["mousemove", "touchstart", "keydown"].forEach((ev) => player.addEventListener(ev, wake, { passive: true }));
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
    if (e.key === " " ) { e.preventDefault(); toggle(); }
    if (e.key === "f") $("#fs").click();
    if (e.key === "m") $("#mute").click();
  });
  if (!user) flash("Log in to save your place.");
}
