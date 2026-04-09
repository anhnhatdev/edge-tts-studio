"""
Edge TTS Web App - FastAPI Backend
Free Microsoft Neural TTS + Local Transcription (Chunked)
"""

import asyncio
import os
import tempfile
import uuid
import shutil
from pathlib import Path

import aiofiles
import edge_tts
import whisper
import torch
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pydub import AudioSegment
import imageio_ffmpeg as ff

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
    """Upload audio, split into chunks, and transcribe."""
    file_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix.lower() or ".mp3"
    temp_file = UPLOAD_DIR / f"{file_id}{ext}"

    try:
        # 1. Save uploaded file
        with temp_file.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 2. Load audio and split into chunks to save resources/avoid errors
        print(f"📦 Processing {temp_file}...")
        audio = AudioSegment.from_file(str(temp_file))
        duration_ms = len(audio)
        chunk_length_ms = 30000  # 30 seconds
        
        chunks = []
        for i in range(0, duration_ms, chunk_length_ms):
            chunks.append(audio[i : i + chunk_length_ms])
        
        print(f"✂️  Split into {len(chunks)} chunks.")
        
        # 3. Transcribe chunks
        model = get_whisper()
        full_transcript = []
        
        for idx, chunk in enumerate(chunks):
            chunk_path = UPLOAD_DIR / f"{file_id}_chunk_{idx}.wav"
            chunk.export(str(chunk_path), format="wav")
            
            print(f"🎙️  Transcribing chunk {idx+1}/{len(chunks)}...")
            result = model.transcribe(str(chunk_path), fp16=False)
            full_transcript.append(result["text"].strip())
            
            # Clean up chunk
            if chunk_path.exists(): chunk_path.unlink()
        
        return {
            "text": " ".join(full_transcript),
            "url": f"/uploads/{temp_file.name}",
            "duration": duration_ms / 1000,
            "chunks": len(chunks)
        }
    except Exception as e:
        if temp_file.exists(): temp_file.unlink()
        print(f"❌ Error in transcription: {str(e)}")
        raise HTTPException(500, f"Transcription failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    print("🎙️  Edge TTS Studio running at http://localhost:8000")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
