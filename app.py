"""
Edge TTS Web App - FastAPI Backend
Free Microsoft Neural TTS + Local Transcription (Chunked + Progress)
"""

import asyncio
import os
import uuid
import shutil
import whisper
import torch
import time
import json
from pathlib import Path
from pydub import AudioSegment
import imageio_ffmpeg as ff

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import edge_tts

# Robustly set ffmpeg paths for pydub to avoid "ffmpeg not found" on Windows
ffmpeg_path = ff.get_ffmpeg_exe()
AudioSegment.converter = ffmpeg_path
AudioSegment.ffmpeg = ffmpeg_path
ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe.exe")
if os.path.exists(ffprobe_path):
    AudioSegment.ffprobe = ffprobe_path

app = FastAPI(title="Edge TTS Studio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

OUTPUT_DIR = Path(__file__).parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Lazy load whisper model
whisper_model = None

def get_whisper():
    global whisper_model
    if whisper_model is None:
        print("📥 Loading Whisper 'tiny' model (resource-efficient)...")
        # Use CPU by default to save VRAM/resources
        whisper_model = whisper.load_model("tiny", device="cpu")
    return whisper_model


# ─── Models ───────────────────────────────────────────────────────────────────

class SynthRequest(BaseModel):
    text: str
    voice: str = "en-US-JennyNeural"
    rate: str = "+0%"     # e.g., "+10%", "-20%"
    pitch: str = "+0Hz"   # e.g., "+5Hz", "-10Hz"
    volume: str = "+0%"   # e.g., "+10%", "-5%"


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = Path(__file__).parent / "index.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


@app.get("/transcribe", response_class=HTMLResponse)
async def transcribe_page():
    html_file = Path(__file__).parent / "transcribe.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


@app.get("/api/voices")
async def get_voices():
    """Get all available English voices from edge-tts."""
    all_voices = await edge_tts.list_voices()
    en_voices = [
        {
            "name": v["ShortName"],
            "display": v["FriendlyName"],
            "gender": v["Gender"],
            "locale": v["Locale"],
            "style": v.get("StyleList", []),
        }
        for v in all_voices
        if v["Locale"].startswith("en-")
    ]
    # Sort by locale then name
    en_voices.sort(key=lambda x: (x["locale"], x["name"]))
    return {"voices": en_voices, "total": len(en_voices)}


@app.post("/api/synthesize")
async def synthesize(req: SynthRequest):
    """Convert text to speech, return audio file URL."""
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")
    if len(req.text) > 5000:
        raise HTTPException(400, "Text too long (max 5000 characters)")

    file_id = uuid.uuid4().hex[:12]
    output_path = OUTPUT_DIR / f"{file_id}.mp3"

    try:
        communicate = edge_tts.Communicate(
            text=req.text,
            voice=req.voice,
            rate=req.rate,
            pitch=req.pitch,
            volume=req.volume,
        )
        await communicate.save(str(output_path))
    except Exception as e:
        raise HTTPException(500, f"TTS synthesis failed: {str(e)}")

    return {
        "url": f"/outputs/{file_id}.mp3",
        "file_id": file_id,
        "voice": req.voice,
        "chars": len(req.text),
    }


@app.delete("/api/cleanup/{file_id}")
async def cleanup(file_id: str):
    """Delete a generated audio file."""
    # Sanitize to prevent path traversal
    if not file_id.isalnum():
        raise HTTPException(400, "Invalid file ID")
    path = OUTPUT_DIR / f"{file_id}.mp3"
    if path.exists():
        path.unlink()
    return {"deleted": True}


@app.post("/api/transcribe")
async def api_transcribe(file: UploadFile = File(...)):
    """Upload audio, split into chunks, and transcribe with progress updates."""
    file_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix.lower() or ".mp3"
    temp_file = UPLOAD_DIR / f"{file_id}{ext}"

    async def generate_progress():
        try:
            # 1. Save uploaded file
            with temp_file.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            yield json.dumps({"status": "processing", "message": "Analyzing audio..."}) + "\n"
            
            # 2. Load audio and split into chunks
            audio = AudioSegment.from_file(str(temp_file))
            duration_ms = len(audio)
            chunk_length_ms = 30000  # 30 seconds
            chunks = []
            for i in range(0, duration_ms, chunk_length_ms):
                chunks.append(audio[i : i + chunk_length_ms])
            
            total_chunks = len(chunks)
            yield json.dumps({
                "status": "processing", 
                "message": f"Split into {total_chunks} segments",
                "total_chunks": total_chunks
            }) + "\n"
            
            # 3. Transcribe chunks
            model = get_whisper()
            full_transcript = []
            start_time = time.time()
            
            for idx, chunk in enumerate(chunks):
                chunk_idx = idx + 1
                chunk_path = UPLOAD_DIR / f"{file_id}_chunk_{idx}.wav"
                chunk.export(str(chunk_path), format="wav")
                
                # Estimate remaining time based on previous chunks
                elapsed = time.time() - start_time
                avg_time_per_chunk = elapsed / chunk_idx if idx > 0 else 5.0 # assume 5s for first
                remaining_est = avg_time_per_chunk * (total_chunks - chunk_idx)
                
                yield json.dumps({
                    "status": "progress",
                    "current": chunk_idx,
                    "total": total_chunks,
                    "remaining": round(remaining_est, 1),
                    "message": f"Transcribing part {chunk_idx}/{total_chunks}..."
                }) + "\n"
                
                # Run transcription (force CPU and FP32 for Windows/stability)
                result = model.transcribe(str(chunk_path), fp16=False)
                full_transcript.append(result["text"].strip())
                
                # Close file handle and clean up chunk
                if chunk_path.exists():
                    try:
                        chunk_path.unlink()
                    except: pass # Ignore if still locked, will clean later
            
            yield json.dumps({
                "status": "complete",
                "text": " ".join(full_transcript),
                "url": f"/uploads/{temp_file.name}",
                "duration": duration_ms / 1000
            }) + "\n"

        except Exception as e:
            if temp_file.exists(): 
                try: temp_file.unlink()
                except: pass
            yield json.dumps({"status": "error", "message": str(e)}) + "\n"

    return StreamingResponse(generate_progress(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn
    print("🎙️  Edge TTS Studio running at http://localhost:8000")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
