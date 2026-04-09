/* ============================================================
   Edge TTS Studio — app.js
   ============================================================ */

const API = "";   // Same origin

// ── State ──────────────────────────────────────────────────────────────────
let allVoices = [];
let currentAudioUrl = null;
let currentFileId = null;
let isPlaying = false;
let waveAnimating = false;
let history = JSON.parse(localStorage.getItem("tts_history") || "[]");

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadVoices();
  renderHistory();
  setupTextCounter();
  updateSliders();
});

// ── Voices ─────────────────────────────────────────────────────────────────
async function loadVoices() {
  try {
    const res = await fetch(`${API}/api/voices`);
    const data = await res.json();
    allVoices = data.voices;
    document.getElementById("totalVoices").textContent = data.total;
    populateVoiceSelect(allVoices);
  } catch (e) {
    showToast("⚠️ Could not load voices — is the server running?", "error");
  }
}

function populateVoiceSelect(voices) {
  const sel = document.getElementById("voiceSelect");
  sel.innerHTML = "";
  voices.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v.name;
    opt.textContent = `${v.gender === "Female" ? "👩" : "👨"} ${v.display.replace("Microsoft ", "")}`;
    if (v.name === "en-US-JennyNeural") opt.selected = true;
    sel.appendChild(opt);
  });
  updateVoiceBadge();
}

function filterVoices() {
  const locale = document.getElementById("voiceFilter").value;
  const filtered = locale ? allVoices.filter(v => v.locale.startsWith(locale)) : allVoices;
  populateVoiceSelect(filtered);
}

function updateVoiceBadge() {
  const sel = document.getElementById("voiceSelect");
  const selected = allVoices.find(v => v.name === sel.value);
  const badge = document.getElementById("voiceGender");
  badge.textContent = selected?.gender === "Female" ? "F" : "M";
  badge.style.background = selected?.gender === "Female"
    ? "linear-gradient(135deg, #ec4899, #8b5cf6)"
    : "linear-gradient(135deg, #3b82f6, #06b6d4)";
}
document.getElementById("voiceSelect")?.addEventListener("change", updateVoiceBadge);

// ── Text counter ───────────────────────────────────────────────────────────
function setupTextCounter() {
  const input = document.getElementById("textInput");
  const counter = document.getElementById("charCount");
  input.addEventListener("input", () => {
    const len = input.value.length;
    counter.textContent = len;
    counter.style.color = len > 4500 ? "var(--warning)" : len > 4900 ? "var(--danger)" : "inherit";
  });
}

// ── Quick sample texts ─────────────────────────────────────────────────────
const quickTexts = {
  hello: "Hello there! My name is Jenny and I'm powered by Microsoft's neural text-to-speech technology. It's completely free to use and sounds incredibly natural!",
  news: "Good morning! Here are today's top headlines: Scientists have made a groundbreaking discovery in renewable energy, claiming it could power entire cities with minimal environmental impact. In other news, the global economy shows signs of steady recovery as technology sectors continue to lead growth.",
  story: "Once upon a time, in a small village nestled between mist-covered mountains, there lived a young inventor named Clara. Every morning, she would wake before dawn, her mind already buzzing with ideas. One rainy autumn day, she discovered a peculiar blueprint hidden beneath the floorboards of her grandfather's workshop — and everything changed."
};
function setQuickText(key) {
  document.getElementById("textInput").value = quickTexts[key];
  document.getElementById("charCount").textContent = quickTexts[key].length;
}

// ── Sliders ────────────────────────────────────────────────────────────────
function updateSliders() {
  updateRate(0); updatePitch(0); updateVolume(0);
}

function updateRate(v) {
  v = parseInt(v);
  const label = v === 0 ? "Normal" : v > 0 ? `+${v}% Faster` : `${v}% Slower`;
  document.getElementById("rateVal").textContent = label;
  updateSliderFill("rate", v, -50, 100);
}
function updatePitch(v) {
  v = parseInt(v);
  const label = v === 0 ? "Normal" : v > 0 ? `+${v}Hz Higher` : `${v}Hz Lower`;
  document.getElementById("pitchVal").textContent = label;
  updateSliderFill("pitch", v, -20, 20);
}
function updateVolume(v) {
  v = parseInt(v);
  const label = v === 0 ? "Normal" : v > 0 ? `+${v}% Louder` : `${v}% Quieter`;
  document.getElementById("volumeVal").textContent = label;
  updateSliderFill("volume", v, -50, 50);
}
function updateSliderFill(id, value, min, max) {
  const pct = ((value - min) / (max - min)) * 100;
  document.getElementById(id).style.background =
    `linear-gradient(to right, var(--primary) ${pct}%, rgba(255,255,255,0.1) ${pct}%)`;
}

// Get formatted values for API
function getRateStr()   { const v = parseInt(document.getElementById("rate").value);   return v >= 0 ? `+${v}%` : `${v}%`; }
function getPitchStr()  { const v = parseInt(document.getElementById("pitch").value);  return v >= 0 ? `+${v}Hz` : `${v}Hz`; }
function getVolumeStr() { const v = parseInt(document.getElementById("volume").value); return v >= 0 ? `+${v}%` : `${v}%`; }

// ── Synthesize ─────────────────────────────────────────────────────────────
async function synthesize() {
  const text = document.getElementById("textInput").value.trim();
  if (!text) { showToast("⚠️ Please enter some text first", "warn"); return; }

  const voice = document.getElementById("voiceSelect").value;
  if (!voice) { showToast("⚠️ Please select a voice", "warn"); return; }

  // Set loading state
  const btn = document.getElementById("generateBtn");
  const btnText = document.getElementById("btnText");
  btn.disabled = true;
  btn.classList.add("loading");
  btn.querySelector(".btn-icon").innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>`;
  btnText.textContent = "Generating...";

  try {
    const res = await fetch(`${API}/api/synthesize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text, voice,
        rate: getRateStr(),
        pitch: getPitchStr(),
        volume: getVolumeStr(),
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Synthesis failed");
    }

    const data = await res.json();
    currentAudioUrl = data.url;
    currentFileId = data.file_id;

    // Update player
    const audio = document.getElementById("audioPlayer");
    audio.src = data.url + "?t=" + Date.now();
    audio.style.display = "block";
    document.getElementById("playerActions").style.display = "flex";
    document.getElementById("audioMeta").style.display = "grid";
    document.getElementById("metaVoice").textContent = data.voice.replace("en-", "").replace("Neural", "").replace("-", " ");
    document.getElementById("metaChars").textContent = `${data.chars} chars`;

    // Show waveform idle
    showWaveIdle();
    audio.play();

    // Add to history
    addToHistory({ text, voice: data.voice, url: data.url, fileId: data.file_id, chars: data.chars, time: new Date().toLocaleTimeString() });

    showToast("✅ Speech generated successfully!", "success");

  } catch (e) {
    showToast(`❌ ${e.message}`, "error");
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.querySelector(".btn-icon").innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
    btnText.textContent = "Generate Speech";
  }
}

// ── Audio player ───────────────────────────────────────────────────────────
function togglePlay() {
  const audio = document.getElementById("audioPlayer");
  if (audio.paused) audio.play(); else audio.pause();
  updatePlayBtn();
}
function updatePlayBtn() {
  const audio = document.getElementById("audioPlayer");
  const btn = document.getElementById("playPauseBtn");
  btn.innerHTML = audio.paused
    ? `<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play`
    : `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg> Pause`;
}

document.getElementById("audioPlayer")?.addEventListener("play",  updatePlayBtn);
document.getElementById("audioPlayer")?.addEventListener("pause", updatePlayBtn);
document.getElementById("audioPlayer")?.addEventListener("ended", () => { stopWave(); updatePlayBtn(); });

function downloadAudio() {
  if (!currentAudioUrl) return;
  const a = document.createElement("a");
  a.href = currentAudioUrl;
  a.download = `tts_${Date.now()}.mp3`;
  a.click();
  showToast("⬇️ Downloading...", "success");
}

// ── Waveform animation ─────────────────────────────────────────────────────
function showWaveIdle() {
  document.querySelector(".wave-idle").style.display = "none";
  document.getElementById("waveBars").style.display = "flex";
}
function startWave() {
  document.querySelector(".wave-idle").style.display = "none";
  document.getElementById("waveBars").style.display = "flex";
  document.querySelectorAll(".bar").forEach(b => b.style.animationPlayState = "running");
}
function stopWave() {
  document.querySelectorAll(".bar").forEach(b => {
    b.style.animationPlayState = "paused";
    b.style.height = "8px";
  });
}

// ── History ─────────────────────────────────────────────────────────────────
function addToHistory(item) {
  history.unshift(item);
  if (history.length > 20) history.pop();
  localStorage.setItem("tts_history", JSON.stringify(history));
  renderHistory();
}

function renderHistory() {
  const list = document.getElementById("historyList");
  if (history.length === 0) {
    list.innerHTML = '<div class="history-empty">No generations yet. Create your first audio above!</div>';
    return;
  }
  list.innerHTML = history.map((item, i) => `
    <div class="history-item" onclick="playHistoryItem(${i})">
      <div class="history-thumb">🎙️</div>
      <div class="history-info">
        <div class="history-text">${escHtml(item.text.substring(0, 60))}${item.text.length > 60 ? "…" : ""}</div>
        <div class="history-meta">${item.voice.replace("Neural","").replace("en-","").replace(/-/g," ")} · ${item.chars} chars · ${item.time}</div>
      </div>
      <button class="history-play" title="Play">
        <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      </button>
    </div>
  `).join("");
}

function playHistoryItem(i) {
  const item = history[i];
  const audio = document.getElementById("audioPlayer");
  audio.src = item.url + "?t=" + Date.now();
  audio.style.display = "block";
  document.getElementById("playerActions").style.display = "flex";
  document.getElementById("audioMeta").style.display = "grid";
  document.getElementById("metaVoice").textContent = item.voice.replace("en-","").replace("Neural","").replace("-"," ");
  document.getElementById("metaChars").textContent = `${item.chars} chars`;
  document.getElementById("textInput").value = item.text;
  document.getElementById("charCount").textContent = item.text.length;
  audio.play();
}

function clearHistory() {
  if (history.length === 0) return;
  history = [];
  localStorage.removeItem("tts_history");
  renderHistory();
  showToast("🗑️ History cleared", "success");
}

// ── Toast ──────────────────────────────────────────────────────────────────
let toastTimer;
function showToast(msg, type = "info") {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.className = "toast show";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3500);
}

// ── Helpers ────────────────────────────────────────────────────────────────
function escHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// Keyboard shortcut: Ctrl+Enter to generate
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") synthesize();
});
