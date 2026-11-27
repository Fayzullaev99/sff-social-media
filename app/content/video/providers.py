"""Pluggable visual providers for the video factory:
- kinetic: always-available modern gradient + typography slides (zero API keys)
- stock: Pexels HD stock footage + caption overlay (falls back to kinetic)
- ai_veo: Gemini Veo generative video (falls back to stock/kinetic)
- avatar: HeyGen AI spokesperson avatar (falls back to stock/kinetic)
"""
from __future__ import annotations

import asyncio
import math
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.config import env
from app.core import runtime
from app.core.state import log_activity

PALETTES = [
    ((22, 16, 56), (94, 43, 180), (6, 182, 212)),
    ((15, 23, 42), (49, 46, 129), (236, 72, 153)),
    ((12, 28, 44), (17, 94, 89), (56, 189, 248)),
    ((30, 15, 45), (126, 34, 206), (245, 158, 11)),
    ((17, 24, 39), (30, 64, 175), (16, 185, 129)),
]


def resolution_for(aspect_ratio: str) -> tuple[int, int]:
    return (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _gradient_bg(w: int, h: int, c1: tuple[int, int, int], c2: tuple[int, int, int], accent: tuple[int, int, int]) -> Image.Image:
    # Fast vertical gradient via 1px strip scaled up + subtle radial accent glow
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        px[0, y] = (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )
    img = strip.resize((w, h), Image.Resampling.BILINEAR).convert("RGBA")
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    r = int(min(w, h) * 0.45)
    cx, cy = int(w * 0.78), int(h * 0.22)
    for step in range(8, 0, -1):
        rad = int(r * step / 8)
        alpha = int(28 * (1 - step / 9))
        draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=(*accent, alpha))
    return Image.alpha_composite(img, glow)


def render_kinetic_slide(
    out_png: Path,
    *,
    caption: str,
    narration: str,
    scene_idx: int,
    total_scenes: int,
    aspect_ratio: str = "9:16",
    brand: str = "Social Agent",
) -> Path:
    w, h = resolution_for(aspect_ratio)
    c1, c2, accent = PALETTES[scene_idx % len(PALETTES)]
    img = _gradient_bg(w, h, c1, c2, accent)
    draw = ImageDraw.Draw(img)

    pad = int(w * 0.08)
    # Progress bar at top
    bar_y = int(h * 0.06)
    bar_w = w - 2 * pad
    seg_w = (bar_w - (total_scenes - 1) * 12) / max(total_scenes, 1)
    for i in range(total_scenes):
        x0 = pad + i * (seg_w + 12)
        color = (*accent, 235) if i <= scene_idx else (255, 255, 255, 65)
        draw.rounded_rectangle((x0, bar_y, x0 + seg_w, bar_y + 10), radius=5, fill=color)

    # Scene badge
    badge_font = _load_font(int(min(w, h) * 0.032), bold=True)
    badge_txt = f"{brand}  ·  {scene_idx + 1}/{total_scenes}"
    draw.text((pad, bar_y + 34), badge_txt, font=badge_font, fill=(255, 255, 255, 190))

    # Main headline card
    title_size = int(min(w, h) * (0.072 if aspect_ratio == "9:16" else 0.064))
    title_font = _load_font(title_size, bold=True)
    sub_font = _load_font(int(min(w, h) * 0.038), bold=False)

    wrap_chars = 18 if aspect_ratio == "9:16" else 34
    lines = textwrap.wrap(caption.strip() or narration[:60], width=wrap_chars)[:5]
    sub_lines = textwrap.wrap(narration.strip(), width=30 if aspect_ratio == "9:16" else 56)[:5]

    line_h = int(title_size * 1.24)
    block_h = len(lines) * line_h
    y_start = int(h * 0.33) - block_h // 4

    # Accent bar left of headline
    draw.rounded_rectangle((pad, y_start, pad + 12, y_start + block_h), radius=6, fill=(*accent, 255))
    y = y_start
    for line in lines:
        draw.text((pad + 34, y + 3), line, font=title_font, fill=(0, 0, 0, 120))
        draw.text((pad + 32, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += line_h

    # Narration subtitle card at bottom
    sub_y = int(h * 0.68)
    sub_lh = int(min(w, h) * 0.052)
    card_h = max(120, len(sub_lines) * sub_lh + 56)
    draw.rounded_rectangle(
        (pad, sub_y, w - pad, min(h - 60, sub_y + card_h)),
        radius=28,
        fill=(10, 12, 28, 175),
        outline=(*accent, 140),
        width=2,
    )
    sy = sub_y + 28
    for line in sub_lines:
        draw.text((pad + 32, sy), line, font=sub_font, fill=(235, 240, 255, 245))
        sy += sub_lh

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_png, "PNG")
    return out_png


def render_caption_overlay(out_png: Path, *, caption: str, aspect_ratio: str = "9:16") -> Path:
    """Transparent PNG with styled caption pill for overlaying on real/AI footage."""
    w, h = resolution_for(aspect_ratio)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = int(w * 0.07)
    font = _load_font(int(min(w, h) * 0.052), bold=True)
    lines = textwrap.wrap(caption.strip(), width=22 if aspect_ratio == "9:16" else 42)[:3]
    if lines:
        lh = int(min(w, h) * 0.068)
        box_h = len(lines) * lh + 48
        y0 = int(h * 0.74)
        draw.rounded_rectangle((pad, y0, w - pad, y0 + box_h), radius=26, fill=(10, 12, 26, 185))
        y = y0 + 24
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(((w - tw) // 2, y), line, font=font, fill=(255, 255, 255, 255))
            y += lh
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, "PNG")
    return out_png


def _ffmpeg_image_to_clip(img_path: Path, duration: float, out_mp4: Path, aspect_ratio: str) -> Path:
    w, h = resolution_for(aspect_ratio)
    fps = 25
    frames = max(25, int(math.ceil(duration * fps)))
    # Subtle slow zoom-in for dynamic kinetic feel
    vf = f"scale={w}:{h},zoompan=z='min(zoom+0.0008,1.08)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},format=yuv420p"
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
        "-t", f"{duration:.2f}", "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-an", str(out_mp4),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_mp4


def _ffmpeg_fit_and_overlay(raw_clip: Path, overlay_png: Path, duration: float, out_mp4: Path, aspect_ratio: str) -> Path:
    w, h = resolution_for(aspect_ratio)
    fc = (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps=25,format=yuv420p[bg];"
        f"[bg][1:v]overlay=0:0:shortest=1,format=yuv420p[v]"
    )
    cmd = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(raw_clip), "-i", str(overlay_png),
        "-t", f"{duration:.2f}", "-filter_complex", fc, "-map", "[v]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-an", str(out_mp4),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_mp4


async def _fetch_pexels_video(query: str, orientation: str, out_raw: Path) -> Path | None:
    if not env.pexels_api_key:
        return None
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": env.pexels_api_key}
    params = {"query": query or "business technology", "orientation": orientation, "per_page": 3}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            videos = r.json().get("videos", [])
            if not videos:
                return None
            files = videos[0].get("video_files", [])
            mp4s = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
            if not mp4s:
                return None
            # Prefer ~720p-1080p to keep downloads fast
            mp4s.sort(key=lambda f: abs((f.get("width") or 1080) - 1080))
            dl = await client.get(mp4s[0]["link"], follow_redirects=True, timeout=60)
            dl.raise_for_status()
            out_raw.write_bytes(dl.content)
            return out_raw
    except Exception as e:
        log_activity("video", f"Pexels stok video topilmadi ({query}): {e}", "warning")
        return None


async def _generate_veo_clip(prompt: str, aspect_ratio: str, out_raw: Path) -> Path | None:
    if not runtime.llm:
        return None
    try:
        from google.genai import types

        op = await asyncio.to_thread(
            runtime.llm.client.models.generate_videos,
            model=env.gemini_veo_model,
            prompt=prompt,
            config=types.GenerateVideosConfig(aspect_ratio=aspect_ratio, number_of_videos=1),
        )
        # Poll up to 4 minutes
        for _ in range(48):
            if getattr(op, "done", False):
                break
            await asyncio.sleep(5)
            op = await asyncio.to_thread(runtime.llm.client.operations.get, op)
        resp = getattr(op, "response", None) or getattr(op, "result", None)
        vids = getattr(resp, "generated_videos", None) or []
        if not vids:
            return None
        vid = vids[0].video
        data = await asyncio.to_thread(runtime.llm.client.files.download, file=vid)
        out_raw.write_bytes(data)
        return out_raw
    except Exception as e:
        log_activity("video", f"Veo AI video ishlamadi, zaxira usulga o'tildi: {e}", "warning")
        return None


async def _generate_heygen_full_video(script_text: str, aspect_ratio: str, out_mp4: Path) -> Path | None:
    """Generate a full talking-avatar video via HeyGen API v2 (when configured)."""
    if not (env.heygen_api_key and env.heygen_avatar_id):
        return None
    w, h = resolution_for(aspect_ratio)
    headers = {"X-Api-Key": env.heygen_api_key, "Content-Type": "application/json"}
    body = {
        "video_inputs": [
            {
                "character": {"type": "avatar", "avatar_id": env.heygen_avatar_id, "avatar_style": "normal"},
                "voice": {"type": "text", "input_text": script_text[:1500]},
            }
        ],
        "dimension": {"width": w, "height": h},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.heygen.com/v2/video/generate", headers=headers, json=body)
            r.raise_for_status()
            video_id = r.json()["data"]["video_id"]
            for _ in range(60):
                await asyncio.sleep(5)
                st = await client.get(
                    "https://api.heygen.com/v1/video_status.get", headers=headers, params={"video_id": video_id}
                )
                data = st.json().get("data", {})
                if data.get("status") == "completed" and data.get("video_url"):
                    dl = await client.get(data["video_url"], timeout=120)
                    dl.raise_for_status()
                    out_mp4.write_bytes(dl.content)
                    return out_mp4
                if data.get("status") == "failed":
                    return None
    except Exception as e:
        log_activity("video", f"HeyGen avatar xatosi, zaxira usulga o'tildi: {e}", "warning")
    return None


async def build_scene_clip(
    scene: dict[str, Any],
    *,
    scene_idx: int,
    total_scenes: int,
    duration: float,
    style: str,
    aspect_ratio: str,
    work_dir: Path,
    brand: str,
) -> Path:
    """Create a single rendered H.264 scene clip using the selected style with clean fallbacks."""
    out_mp4 = work_dir / f"scene_{scene_idx:02d}.mp4"
    caption = scene.get("on_screen_text") or scene.get("narration", "")[:60]
    narration = scene.get("narration", "")
    orientation = "portrait" if aspect_ratio == "9:16" else "landscape"

    raw_clip: Path | None = None
    if style == "ai_veo":
        raw_clip = await _generate_veo_clip(
            scene.get("visual_prompt") or scene.get("visual_query") or caption,
            aspect_ratio,
            work_dir / f"veo_{scene_idx:02d}.mp4",
        )
    if raw_clip is None and style in ("stock", "ai_veo", "avatar"):
        raw_clip = await _fetch_pexels_video(
            scene.get("visual_query", "modern workspace"),
            orientation,
            work_dir / f"pexels_{scene_idx:02d}.mp4",
        )

    if raw_clip is not None:
        overlay = await asyncio.to_thread(
            render_caption_overlay, work_dir / f"cap_{scene_idx:02d}.png", caption=caption, aspect_ratio=aspect_ratio
        )
        await asyncio.to_thread(_ffmpeg_fit_and_overlay, raw_clip, overlay, duration, out_mp4, aspect_ratio)
        return out_mp4

    # Kinetic slide (always works, zero external keys required)
    slide = await asyncio.to_thread(
        render_kinetic_slide,
        work_dir / f"slide_{scene_idx:02d}.png",
        caption=caption,
        narration=narration,
        scene_idx=scene_idx,
        total_scenes=total_scenes,
        aspect_ratio=aspect_ratio,
        brand=brand,
    )
    await asyncio.to_thread(_ffmpeg_image_to_clip, slide, duration, out_mp4, aspect_ratio)
    return out_mp4


async def try_avatar_full_video(script_text: str, aspect_ratio: str, out_mp4: Path) -> Path | None:
    return await _generate_heygen_full_video(script_text, aspect_ratio, out_mp4)
