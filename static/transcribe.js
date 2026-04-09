/* ============================================================
   Edge Transcriber — transcribe.js
   ============================================================ */

const API = "";

// ── Elements ──────────────────────────────────────────────────────────────
const uploadZone = document.getElementById("uploadZone");
const fileInput  = document.getElementById("fileInput");
const fileName   = document.getElementById("fileName");
const audioPlayer = document.getElementById("audioPlayer");
const transcriptArea = document.getElementById("transcriptArea");

// ── Upload Logic ──────────────────────────────────────────────────────────
uploadZone.addEventListener("click", () => fileInput.click());

uploadZone.addEventListener("dragover", e => {
    e.preventDefault();
    uploadZone.classList.add("dragover");
});

uploadZone.addEventListener("dragleave", () => {
    uploadZone.classList.remove("dragover");
});

uploadZone.addEventListener("drop", e => {
    e.preventDefault();
    uploadZone.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        updateFileInfo();
    }
});

fileInput.addEventListener("change", updateFileInfo);

function updateFileInfo() {
    const file = fileInput.files[0];
    if (file) {
        fileName.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    }
}

// ── Transcription ─────────────────────────────────────────────────────────
async function uploadAndTranscribe() {
    const file = fileInput.files[0];
    if (!file) {
        showToast("⚠️ Please select an audio file first.", "warn");
        return;
    }

    const btn = document.getElementById("transcribeBtn");
    const btnText = document.getElementById("btnText");
    btn.disabled = true;
    btnText.textContent = "Transcribing (this may take a minute)...";

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch(`${API}/api/transcribe`, {
            method: "POST",
            body: formData
        });

        if (!res.ok) throw new Error("Transcription failed");

        const data = await res.json();
        
        // Update Audio
        audioPlayer.src = data.url;
        audioPlayer.style.display = "block";
        document.getElementById("playerPlaceholder").style.display = "none";
        document.getElementById("customControls").style.display = "block";
        
        // Update Transcript
        transcriptArea.textContent = data.text;
        transcriptArea.classList.add("ready");
        
        showToast("✅ Transcription complete!", "success");

    } catch (e) {
        showToast(`❌ Error: ${e.message}`, "error");
        console.error(e);
    } finally {
        btn.disabled = false;
        btnText.textContent = "Start Transcription";
    }
}

// ── Player Controls ───────────────────────────────────────────────────────
function togglePlay() {
    const btn = document.getElementById("playBtn");
    if (audioPlayer.paused) {
        audioPlayer.play();
        btn.textContent = "Pause";
    } else {
        audioPlayer.pause();
        btn.textContent = "Play";
    }
}

function skip(seconds) {
    audioPlayer.currentTime += seconds;
    showToast(`${seconds > 0 ? "+" : ""}${seconds}s`, "info");
}

function updateSpeed(val) {
    audioPlayer.playbackRate = parseFloat(val);
    document.getElementById("speedVal").textContent = `${val}x`;
    
    // Update slider fill
    const slider = document.getElementById("speedSlider");
    const pct = ((val - 0.5) / (2 - 0.5)) * 100;
    slider.style.background = `linear-gradient(to right, var(--primary) ${pct}%, rgba(255,255,255,0.1) ${pct}%)`;
}

// ── Helpers ────────────────────────────────────────────────────────────────
function copyTranscript() {
    const text = transcriptArea.textContent;
    if (text === "Transcript will appear here...") return;
    
    navigator.clipboard.writeText(text);
    showToast("📋 Copied to clipboard!", "success");
}

function showToast(msg, type = "info") {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.className = "toast show";
    setTimeout(() => toast.classList.remove("show"), 3000);
}
