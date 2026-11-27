"""Voiceover synthesis (edge-tts) and subtitle (SRT) generation."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from app.core.state import get_settings


def pick_voice(language: str) -> str:
    vcfg = get_settings().get("video", {})
    lang = (language or "uz").lower()[:2]
    defaults = {
        "uz": vcfg.get("voice_uz", "uz-UZ-MadinaNeural"),
        "ru": vcfg.get("voice_ru", "ru-RU-SvetlanaNeural"),
        "en": vcfg.get("voice_en", "en-US-JennyNeural"),
    }
    return defaults.get(lang, defaults["uz"])


def probe_duration(media_path: Path) -> float:
    """Return media duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        try:
            data = json.loads(proc.stdout)
            return float(data["format"]["duration"])
        except Exception:
            pass
    return 0.0


def _fmt_srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    hh, rem = divmod(ms, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def build_srt(scene_timings: list[tuple[float, float, str]], out_path: Path) -> Path:
    """Write a clean SRT subtitle file from (start_sec, end_sec, text) tuples."""
    blocks = []
    for idx, (start, end, text) in enumerate(scene_timings, 1):
        clean = " ".join(text.strip().split())
        if not clean:
            continue
        blocks.append(f"{idx}\n{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}\n{clean}\n")
    out_path.write_text("\n".join(blocks), encoding="utf-8")
    return out_path


async def synthesize_scene_audio(text: str, out_mp3: Path, *, voice: str) -> float:
    """Synthesize speech with edge-tts and return its duration in seconds."""
    import edge_tts

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    comm = edge_tts.Communicate(text=text.strip(), voice=voice)
    await comm.save(str(out_mp3))
    dur = await asyncio.to_thread(probe_duration, out_mp3)
    return max(dur, 1.5)


async def synthesize_silent_fallback(duration_sec: float, out_mp3: Path) -> float:
    """Generate silent audio track via ffmpeg (used in offline tests or if TTS fails)."""
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", f"{duration_sec:.2f}", "-q:a", "9", "-acodec", "libmp3lame", str(out_mp3),
    ]
    await asyncio.to_thread(subprocess.run, cmd, capture_output=True, check=True)
    return duration_sec
