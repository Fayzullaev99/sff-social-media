"""End-to-end video project orchestration: script -> TTS -> visuals -> FFmpeg render -> approval -> publish."""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from app.approvals import service as approvals
from app.config import DATA_DIR
from app.content.video import providers, script as script_mod, tts
from app.core import repo, runtime
from app.core.state import get_settings, log_activity
from app.db import VideoProject, session_scope, utcnow

VIDEOS_DIR = DATA_DIR / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


def video_to_dict(v: VideoProject) -> dict[str, Any]:
    return {
        "id": v.id,
        "topic": v.topic,
        "style": v.style,
        "aspect_ratio": v.aspect_ratio,
        "language": v.language,
        "title": v.title,
        "description": v.description,
        "tags": v.tags or [],
        "script": v.script,
        "scenes": v.scenes or [],
        "voice": v.voice,
        "video_path": v.video_path,
        "thumbnail_path": v.thumbnail_path,
        "subtitle_path": v.subtitle_path,
        "duration_sec": round(v.duration_sec or 0.0, 1),
        "status": v.status,
        "targets": v.targets or [],
        "published_urls": v.published_urls or {},
        "approval_id": v.approval_id,
        "error": v.error,
        "created_at": v.created_at.isoformat() + "Z" if v.created_at else None,
        "published_at": v.published_at.isoformat() + "Z" if v.published_at else None,
    }


def list_videos(limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as s:
        return [video_to_dict(v) for v in s.query(VideoProject).order_by(VideoProject.id.desc()).limit(limit).all()]


def get_video(video_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        v = s.get(VideoProject, video_id)
        return video_to_dict(v) if v else None


def _concat_and_mux(scene_clips: list[Path], scene_audios: list[Path], out_mp4: Path, out_thumb: Path) -> float:
    work_dir = out_mp4.parent
    v_list = work_dir / "v_list.txt"
    a_list = work_dir / "a_list.txt"
    v_list.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in scene_clips), encoding="utf-8")
    a_list.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in scene_audios), encoding="utf-8")

    merged_v = work_dir / "merged_v.mp4"
    merged_a = work_dir / "merged_a.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(v_list), "-c", "copy", str(merged_v)],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(a_list), "-c:a", "libmp3lame", "-q:a", "4", str(merged_a)],
        capture_output=True, check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(merged_v), "-i", str(merged_a),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", str(out_mp4),
        ],
        capture_output=True, check=True,
    )
    # Extract thumbnail frame at 1.0s (or 0s if shorter)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "00:00:00.8", "-i", str(out_mp4), "-vframes", "1", "-q:v", "3", str(out_thumb)],
        capture_output=True, check=False,
    )
    return tts.probe_duration(out_mp4)


async def create_and_render_video(
    *,
    topic: str | None = None,
    style: str = "auto",
    aspect_ratio: str | None = None,
    language: str | None = None,
    targets: list[str] | None = None,
    instructions: str = "",
    scenes_override: list[dict[str, Any]] | None = None,
    title_override: str | None = None,
    description_override: str | None = None,
    silent_audio: bool = False,
) -> dict[str, Any]:
    """Generate script (unless scenes_override given), render MP4, and queue for admin approval."""
    cfg = get_settings()
    vcfg = cfg.get("video", {})
    p = cfg.get("persona", {})

    aspect_ratio = aspect_ratio or vcfg.get("default_aspect_ratio", "9:16")
    language = language or p.get("default_language", "uz")
    targets = targets if targets is not None else list(vcfg.get("auto_publish_targets", ["youtube", "instagram"]))
    voice = tts.pick_voice(language)

    if scenes_override:
        chosen_style = "kinetic" if style == "auto" else style
        title = title_override or topic or "Test video"
        description = description_override or title
        tags = ["shorts", "video"]
        scenes = scenes_override
    else:
        vs = await script_mod.generate_video_script(
            topic, language=language, aspect_ratio=aspect_ratio, instructions=instructions
        )
        chosen_style = vs.recommended_style if style == "auto" else style
        title = title_override or vs.title
        description = description_override or vs.description
        tags = vs.tags
        scenes = [s.model_dump() for s in vs.scenes]

    full_script = "\n".join(s.get("narration", "") for s in scenes)
    with session_scope() as s:
        proj = VideoProject(
            topic=(topic or title)[:500],
            style=chosen_style,
            aspect_ratio=aspect_ratio,
            language=language,
            title=title[:500],
            description=description,
            tags=tags,
            script=full_script,
            scenes=scenes,
            voice=voice,
            targets=targets,
            status="rendering",
        )
        s.add(proj)
        s.flush()
        vid_id = proj.id

    work_dir = VIDEOS_DIR / f"video_{vid_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    final_mp4 = work_dir / f"final_{vid_id}.mp4"
    thumb_jpg = work_dir / f"thumb_{vid_id}.jpg"
    srt_path = work_dir / f"subtitles_{vid_id}.srt"

    try:
        log_activity("video", f"🎬 Video #{vid_id} tayyorlanmoqda ({chosen_style}, {aspect_ratio}): «{title}»")

        # Try full AI avatar first if requested & configured
        avatar_done = None
        if chosen_style == "avatar":
            avatar_done = await providers.try_avatar_full_video(full_script, aspect_ratio, final_mp4)

        if avatar_done:
            duration = await asyncio.to_thread(tts.probe_duration, final_mp4)
            await asyncio.to_thread(
                subprocess.run,
                ["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(final_mp4), "-vframes", "1", str(thumb_jpg)],
                capture_output=True, check=False,
            )
        else:
            scene_clips: list[Path] = []
            scene_audios: list[Path] = []
            timings: list[tuple[float, float, str]] = []
            cursor = 0.0
            brand = p.get("owner_name", "Social Agent")

            for i, sc in enumerate(scenes):
                narration = sc.get("narration", "").strip() or sc.get("on_screen_text", "...")
                audio_p = work_dir / f"audio_{i:02d}.mp3"
                if silent_audio:
                    dur = await tts.synthesize_silent_fallback(float(sc.get("duration_sec", 2.0)), audio_p)
                else:
                    try:
                        dur = await tts.synthesize_scene_audio(narration, audio_p, voice=voice)
                    except Exception as e:
                        log_activity("video", f"TTS xatosi, jim audio ishlatildi: {e}", "warning")
                        dur = await tts.synthesize_silent_fallback(3.5, audio_p)
                scene_audios.append(audio_p)
                timings.append((cursor, cursor + dur, narration))
                cursor += dur

                clip = await providers.build_scene_clip(
                    sc,
                    scene_idx=i,
                    total_scenes=len(scenes),
                    duration=dur,
                    style=chosen_style,
                    aspect_ratio=aspect_ratio,
                    work_dir=work_dir,
                    brand=brand,
                )
                scene_clips.append(clip)

            tts.build_srt(timings, srt_path)
            duration = await asyncio.to_thread(_concat_and_mux, scene_clips, scene_audios, final_mp4, thumb_jpg)

        with session_scope() as s:
            v = s.get(VideoProject, vid_id)
            v.video_path = str(final_mp4)
            v.thumbnail_path = str(thumb_jpg) if thumb_jpg.exists() else None
            v.subtitle_path = str(srt_path) if srt_path.exists() else None
            v.duration_sec = duration
            v.status = "pending"

        # Always request human approval before publishing (per user decision #7)
        approval_id = await approvals.request(
            "publish_video",
            f"Video #{vid_id}: {title} ({', '.join(targets) or 'faqat saqlash'})",
            {
                "video_id": vid_id,
                "title": title,
                "description": description[:600],
                "targets": targets,
                "style": chosen_style,
                "duration_sec": round(duration, 1),
                "video_path": str(final_mp4),
            },
        )
        with session_scope() as s:
            s.get(VideoProject, vid_id).approval_id = approval_id

        log_activity("video", f"✅ Video #{vid_id} tayyor ({duration:.1f}s) — tasdiqlashga yuborildi")
        return get_video(vid_id)  # type: ignore[return-value]
    except Exception as e:
        with session_scope() as s:
            v = s.get(VideoProject, vid_id)
            v.status = "failed"
            v.error = str(e)
        log_activity("video", f"Video #{vid_id} xatosi: {e}", "error")
        raise


async def publish_video(video_id: int) -> str:
    """Publish a rendered video to all configured target platforms (called AFTER approval)."""
    v = get_video(video_id)
    if not v or not v.get("video_path") or not Path(v["video_path"]).exists():
        raise FileNotFoundError(f"Video #{video_id} fayli topilmadi")

    results: dict[str, str] = {}
    errors: list[str] = []
    targets = v.get("targets") or []

    if "youtube" in targets:
        if runtime.youtube and runtime.youtube.configured:
            try:
                url = await runtime.youtube.upload_video(
                    Path(v["video_path"]),
                    title=v["title"],
                    description=v["description"],
                    tags=v["tags"],
                    thumbnail_path=Path(v["thumbnail_path"]) if v.get("thumbnail_path") else None,
                )
                results["youtube"] = url
            except Exception as e:
                errors.append(f"YouTube: {e}")
        else:
            errors.append("YouTube ulanmagan (python youtube_auth.py)")

    if "instagram" in targets:
        if runtime.instagram and runtime.instagram.configured:
            try:
                url = await runtime.instagram.publish_reel(
                    video_id=video_id,
                    caption=f"{v['title']}\n\n{v['description']}",
                )
                results["instagram"] = url
            except Exception as e:
                errors.append(f"Instagram: {e}")
        else:
            errors.append("Instagram ulanmagan (.env: IG_ACCESS_TOKEN, IG_ACCOUNT_ID)")

    if "telegram" in targets:
        channels = repo.allowed_channels()
        if runtime.userbot and runtime.userbot.connected and channels:
            try:
                default_id = get_settings().get("content", {}).get("default_channel_id")
                ch = next((c for c in channels if c["id"] == default_id), channels[0])
                msg_id = await runtime.userbot.publish(
                    ch["id"], f"**{v['title']}**\n\n{v['description']}", media_path=v["video_path"]
                )
                results["telegram"] = f"msg:{msg_id} ({ch['title']})"
            except Exception as e:
                errors.append(f"Telegram: {e}")
        else:
            errors.append("Telegram kanal yoki userbot ulanmagan")

    with session_scope() as s:
        row = s.get(VideoProject, video_id)
        row.published_urls = results
        if results:
            row.status = "published"
            row.published_at = utcnow()
            row.error = "; ".join(errors) if errors else None
        else:
            row.status = "ready" if not targets else "failed"
            row.error = "; ".join(errors) if errors else None

    if results:
        summary = ", ".join(f"{k}: {u}" for k, u in results.items())
        if errors:
            summary += f" (xatolar: {'; '.join(errors)})"
        log_activity("video", f"🚀 Video #{video_id} joylandi: {summary}")
        return summary
    if not targets:
        return "Video saqlandi (joylash platformasi tanlanmagan)"
    raise RuntimeError("; ".join(errors))


@approvals.on_approve("publish_video")
async def _on_video_approved(payload: dict[str, Any], approval_id: int) -> str:
    return await publish_video(int(payload["video_id"]))


@approvals.on_reject("publish_video")
async def _on_video_rejected(payload: dict[str, Any], approval_id: int) -> str:
    with session_scope() as s:
        v = s.get(VideoProject, int(payload["video_id"]))
        if v:
            v.status = "rejected"
    return "Video rad etildi"
