"""Video compositor and broadcast audio normalizer for the 7 gaming niches.
Renders 1080x1920 9:16 Shorts with stacked split-screens, slow-mo replays,
Pillow dynamic overlay tracks, and broadcast-standard -14 LUFS loudness.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...media.ffmpeg import run_ffmpeg_command

logger = logging.getLogger(__name__)

W, H = 1080, 1920
FPS = 30
AFMT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"


def _atempo(speed: float) -> str:
    parts = []
    s = speed
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def _cover_crop(label_in: str, label_out: str, bw: int, bh: int, focus: float = 0.5, zoom: float = 1.0, focus_y: float = 0.5) -> str:
    """Scale source to cover (bw x bh) * zoom, then crop at the focus coordinate."""
    scale = max(1.0, zoom)
    scale_expr = f"scale=-2:'ih*max({bw}/iw,{bh}/ih)*{scale:.3f}':flags=lanczos"
    crop_x = f"(iw-{bw})*{focus:.3f}"
    crop_y = f"(ih-{bh})*{focus_y:.3f}"
    return f"[{label_in}]{scale_expr},crop={bw}:{bh}:{crop_x}:{crop_y},setsar=1[{label_out}]"


def probe_media(path: Path) -> Dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,width,height",
        "-of", "json", str(path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    out = {"dur": 10.0, "w": 1920, "h": 1080, "audio": False}
    if p.returncode == 0:
        try:
            data = json.loads(p.stdout)
            fmt = data.get("format", {})
            out["dur"] = float(fmt.get("duration") or 10.0)
            for st in data.get("streams", []):
                if st.get("codec_type") == "video" and "width" in st:
                    out["w"] = int(st["width"])
                    out["h"] = int(st["height"])
                elif st.get("codec_type") == "audio":
                    out["audio"] = True
        except Exception:
            pass
    return out


def measure_loudness(video_path: Path) -> float:
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(video_path),
        "-af", "ebur128=framelog=verbose", "-f", "null", "-",
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    matches = re.findall(r"Integrated loudness:\s+I:\s+([-\d.]+)\s+LUFS", p.stderr)
    if matches:
        try:
            return float(matches[-1])
        except ValueError:
            pass
    return -24.0


def render_short(
    segments: List[Dict[str, Any]],
    overlay_images: List[Tuple[float, float, Path, int, int]],  # (start_s, end_s, image_path, x, y)
    output_path: Path,
    mode: str,
    voice_audio: Optional[Path] = None,
    music_audio: Optional[Path] = None,
    music_gain_db: float = -22.0,
    voice_start_s: float = 0.15,
) -> Dict[str, Any]:
    """Render a vertical 1080x1920 video short with all audio tracks and graphic overlays."""
    t0 = time.time()
    work_dir = output_path.parent / f"_work_{output_path.stem}"
    work_dir.mkdir(parents=True, exist_ok=True)

    input_files: List[str] = []
    file_info: Dict[str, Dict[str, Any]] = {}

    def get_input_idx(fpath: str) -> int:
        fpath = str(fpath)
        if fpath not in input_files:
            input_files.append(fpath)
            file_info[fpath] = probe_media(Path(fpath))
        return input_files.index(fpath)

    fc: List[str] = []
    vlabels, alabels = [], []
    total_dur = 0.0

    for i, sg in enumerate(segments):
        speed = float(sg.get("speed", 1.0) or 1.0)
        kind = sg.get("kind", "single")

        if kind == "stack":
            # 2-way split screen (top / bottom)
            top, bot = sg["top"], sg["bottom"]
            dur = min(float(top["b"]) - float(top["a"]), float(bot["b"]) - float(bot["a"])) / speed
            dur = max(0.5, dur)
            parts = []
            for k_prefix, part in (("t", top), ("b", bot)):
                idx = get_input_idx(part["file"])
                a = float(part["a"])
                fc.append(f"[{idx}:v]trim=start={a:.3f}:end={a + dur * speed:.3f},setpts=(PTS-STARTPTS)/{speed:.4f}[s{i}{k_prefix}0]")
                fc.append(_cover_crop(f"s{i}{k_prefix}0", f"s{i}{k_prefix}", W, H // 2, float(part.get("focus", 0.5)), float(part.get("zoom", 1.0)), float(part.get("focus_y", 0.5))))
                parts.append(f"[s{i}{k_prefix}]")
            fc.append(f"{parts[0]}{parts[1]}vstack=inputs=2,fps={FPS},format=yuv420p,setsar=1[v{i}]")

            # Stack audio
            which_a = sg.get("audio", "top")
            srcs = {"top": [top], "bottom": [bot], "both": [top, bot], "none": []}.get(which_a, [top])
            alist = []
            for j, part in enumerate(srcs):
                idx = get_input_idx(part["file"])
                if not file_info[str(part["file"])]["audio"]:
                    continue
                a = float(part["a"])
                g = float(part.get("gain", 0) or 0) - (3 if len(srcs) == 2 else 0)
                fc.append(f"[{idx}:a]atrim=start={a:.3f}:end={a + dur * speed:.3f},asetpts=PTS-STARTPTS,{_atempo(speed) if speed != 1.0 else 'anull'},{AFMT},volume={g:.2f}dB[a{i}_{j}]")
                alist.append(f"[a{i}_{j}]")
            if len(alist) == 2:
                fc.append(f"{alist[0]}{alist[1]}amix=inputs=2:normalize=0:duration=first[a{i}r]")
            elif len(alist) == 1:
                fc.append(f"{alist[0]}anull[a{i}r]")
            else:
                fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f},{AFMT}[a{i}r]")

        else:
            # Single clip
            idx = get_input_idx(sg["file"])
            info = file_info[str(sg["file"])]
            a, b = float(sg.get("a", 0.0)), float(sg.get("b", 10.0))
            dur = max(0.5, (b - a) / speed)
            head = f"[{idx}:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{speed:.4f}"

            if sg.get("layout") == "fit":
                # Blurred background + foreground
                fc.append(f"{head},split=2[g{i}a][g{i}b]")
                fc.append(f"[g{i}a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=36,eq=brightness=-0.12[g{i}bg]")
                fc.append(f"[g{i}b]scale={W}:-2:flags=lanczos,setsar=1[g{i}fg]")
                fc.append(f"[g{i}bg][g{i}fg]overlay=0:(H-h)/2,fps={FPS},format=yuv420p,setsar=1[v{i}]")
            else:
                fc.append(f"{head}[g{i}0]")
                fc.append(_cover_crop(f"g{i}0", f"g{i}1", W, H, float(sg.get("focus", 0.5)), float(sg.get("zoom", 1.0)), float(sg.get("focus_y", 0.5))))
                fc.append(f"[g{i}1]fps={FPS},format=yuv420p,setsar=1[v{i}]")

            gain = sg.get("gain", 0.0)
            if info["audio"] and gain is not None:
                fc.append(f"[{idx}:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,{_atempo(speed) if speed != 1.0 else 'anull'},{AFMT},volume={float(gain):.2f}dB,afade=t=in:d=0.02,afade=t=out:st={max(0, dur - 0.02):.3f}:d=0.02[a{i}r]")
            else:
                fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f},{AFMT}[a{i}r]")

        vlabels.append(f"[v{i}]")
        alabels.append(f"[a{i}r]")
        total_dur += dur

    K = len(segments)
    fc.append("".join(f"{v}{a}" for v, a in zip(vlabels, alabels)) + f"concat=n={K}:v=1:a=1[base][game]")

    # Build inputs command
    ffmpeg_inputs: List[str] = []
    for f in input_files:
        ffmpeg_inputs += ["-i", f]
    n_in = len(input_files)

    # Process Graphic Overlays
    last_v = "base"
    for k_idx, (s_t, e_t, img_p, ox, oy) in enumerate(overlay_images):
        if not img_p.exists():
            continue
        ffmpeg_inputs += ["-loop", "1", "-t", f"{e_t - s_t:.3f}", "-i", str(img_p)]
        fc.append(f"[{n_in}:v]format=rgba,setpts=PTS-STARTPTS+{s_t:.3f}/TB[ov{k_idx}]")
        fc.append(f"[{last_v}][ov{k_idx}]overlay=x={ox}:y={oy}:enable='between(t,{s_t:.3f},{e_t:.3f})':eof_action=pass[ov_out{k_idx}]")
        last_v = f"ov_out{k_idx}"
        n_in += 1

    # Sound mixing: Game + Voiceover + Music
    mix_tracks = ["[game]"]
    if voice_audio and voice_audio.exists():
        ffmpeg_inputs += ["-i", str(voice_audio)]
        delay_ms = int(voice_start_s * 1000)
        fc.append(f"[{n_in}:a]{AFMT},adelay={delay_ms}|{delay_ms},volume=1.0[vo]")
        mix_tracks.append("[vo]")
        n_in += 1

    if music_audio and music_audio.exists():
        ffmpeg_inputs += ["-stream_loop", "-1", "-i", str(music_audio)]
        fc.append(f"[{n_in}:a]{AFMT},volume={music_gain_db:.2f}dB,atrim=0:{total_dur:.3f}[mu]")
        mix_tracks.append("[mu]")
        n_in += 1

    if len(mix_tracks) > 1:
        fc.append("".join(mix_tracks) + f"amix=inputs={len(mix_tracks)}:normalize=0:duration=first[mixed]")
        amain = "mixed"
    else:
        amain = "game"

    fc.append(f"[{amain}]alimiter=limit=0.89:level=false,aresample=48000[aout]")

    # Write filter script
    filter_script = work_dir / "filter_graph.txt"
    filter_script.write_text(";\n".join(fc), encoding="utf-8")

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        *ffmpeg_inputs,
        "-filter_complex_script", str(filter_script),
        "-map", f"[{last_v}]", "-map", "[aout]",
        "-r", str(FPS), "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-t", f"{total_dur:.3f}",
        str(output_path),
    ]

    logger.info("Executing niche render (%s, %.1fs)...", mode, total_dur)
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0 or not output_path.exists() or output_path.stat().st_size < 10000:
        raise RuntimeError(f"FFmpeg render failed:\n{p.stderr[-1800:]}")

    # Two-pass broadcast loudness normalization: strictly enforce -14 LUFS
    lufs = measure_loudness(output_path)
    if lufs > -70.0 and abs(lufs + 14.0) > 0.8:
        gain_correction = -14.0 - lufs
        logger.info("Loudness was %.1f LUFS. Applying %.2fdB correction...", lufs, gain_correction)
        norm_output = output_path.with_suffix(".norm.mp4")
        norm_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(output_path),
            "-c:v", "copy",
            "-af", f"volume={gain_correction:.2f}dB,alimiter=limit=0.89:level=false",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(norm_output),
        ]
        p_norm = subprocess.run(norm_cmd, capture_output=True, text=True, check=False)
        if p_norm.returncode == 0 and norm_output.exists():
            norm_output.replace(output_path)
            lufs = -14.0

    # Extract high-res cover image
    cover_path = output_path.with_suffix(".jpg")
    cover_t = min(max(1.0, total_dur * 0.3), total_dur - 0.5)
    cover_cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{cover_t:.3f}",
        "-i", str(output_path),
        "-vframes", "1",
        "-q:v", "2",
        str(cover_path),
    ]
    subprocess.run(cover_cmd, capture_output=True, check=False)

    elapsed = time.time() - t0
    return {
        "output_path": str(output_path),
        "cover_path": str(cover_path) if cover_path.exists() else None,
        "duration": round(total_dur, 2),
        "loudness_lufs": round(lufs, 1),
        "render_time_seconds": round(elapsed, 2),
    }
