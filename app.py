"""
Edge TTS Web App - FastAPI Backend
Free Microsoft Neural TTS with beautiful UI
"""

import asyncio
import os
import tempfile
import uuid
from pathlib import Path

import aiofiles
import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")


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


if __name__ == "__main__":
    import uvicorn
    print("🎙️  Edge TTS Studio running at http://localhost:8000")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
