"""
Рендер музыкального клипа из видеофрагментов + аудиотрека.
Видеофрагменты склеиваются с xfade-переходами, зацикливаются если видеоряд короче трека.
"""
import os
import sys
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

from src.logger import get_logger

log = get_logger()

_BIN_DIR = Path(__file__).parent.parent / "bin"


def _ffmpeg() -> str:
    local = _BIN_DIR / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


def _ffprobe() -> str:
    local = _BIN_DIR / "ffprobe.exe"
    return str(local) if local.exists() else "ffprobe"


def _kw() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _run(cmd: list[str], on_log) -> bool:
    on_log(f"$ {' '.join(cmd[:5])}...")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", **_kw()
        )
        last = []
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                last.append(line)
                if len(last) > 20:
                    last.pop(0)
                if "error" in line.lower() or "warning" in line.lower():
                    on_log(line)
        proc.wait()
        if proc.returncode != 0:
            on_log(f"X ffmpeg error (code {proc.returncode})")
            for l in last[-8:]:
                on_log(f"  > {l}")
            return False
        return True
    except Exception as e:
        on_log(f"X {e}")
        return False


def _duration(path: str) -> float:
    try:
        r = subprocess.run(
            [_ffprobe(), "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10, **_kw()
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _encoder_args() -> list[str]:
    return [
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-color_range", "tv",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
    ]


_GAP_SECONDS = 2.0  # пауза между треками


def _build_audio_track(tracks: list[str], out_path: str, on_log) -> bool:
    """Склеивает аудиотреки с паузой 2 сек между ними."""
    if not tracks:
        return False
    if len(tracks) == 1:
        cmd = [_ffmpeg(), "-y", "-i", tracks[0], "-c:a", "pcm_s16le", out_path]
        return _run(cmd, on_log)

    silence = out_path + "_gap.wav"
    if not _run([
        _ffmpeg(), "-y", "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", str(_GAP_SECONDS), "-c:a", "pcm_s16le", silence,
    ], on_log):
        return False

    parts = []
    for i, t in enumerate(tracks):
        parts.append(t)
        if i < len(tracks) - 1:
            parts.append(silence)

    args = []
    for p in parts:
        args += ["-i", p]
    n = len(parts)
    flt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]"
    cmd = [_ffmpeg(), "-y", *args, "-filter_complex", flt,
           "-map", "[aout]", "-c:a", "pcm_s16le", out_path]
    ok = _run(cmd, on_log)
    try:
        os.remove(silence)
    except Exception:
        pass
    return ok


def _normalize_video(src: str, out: str, width: int, height: int, fps: int, on_log) -> bool:
    """Нормализует видео: нужный размер/fps, без звука, tpad-хвост для xfade."""
    norm = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1/1,fps={fps},"
        f"format=yuv420p,"
        f"tpad=stop_mode=clone:stop_duration=0.5"
    )
    cmd = [
        _ffmpeg(), "-y", "-i", src,
        "-vf", norm, "-an",
        *_encoder_args(),
        out,
    ]
    return _run(cmd, on_log)


def _concat_xfade(segments: list[dict], out_path: str, total_dur: float, on_log) -> bool:
    """
    Склеивает видеосегменты с xfade-переходами и обрезает по total_dur.
    segments: [{"path": str, "dur": float, "trans": str, "trans_dur": float}, ...]
    """
    n = len(segments)
    if n == 0:
        return False
    if n == 1:
        cmd = [_ffmpeg(), "-y", "-i", segments[0]["path"],
               "-t", f"{total_dur:.3f}", "-c", "copy", out_path]
        return _run(cmd, on_log)

    args = []
    for s in segments:
        args += ["-i", s["path"]]

    prep = [f"[{i}:v]setsar=1/1,format=yuv420p[v_in{i}]" for i in range(n)]
    xfades = []
    prev = "[v_in0]"
    offset = segments[0]["dur"]

    for i in range(1, n):
        nxt = f"[v_in{i}]"
        out = f"[v_out{i}]" if i < n - 1 else "[v_final]"
        t_id = segments[i - 1]["trans"]
        t_dur = segments[i - 1]["trans_dur"]
        if t_id == "none" or t_dur <= 0.001:
            t_id, t_dur = "fade", 0.04

        max_allowed = min(segments[i - 1]["dur"], segments[i]["dur"]) * 0.4
        t_dur = min(t_dur, max_allowed)

        xfades.append(
            f"{prev}{nxt}xfade=transition={t_id}:duration={t_dur:.3f}:offset={offset:.3f}{out}"
        )
        prev = out
        offset += segments[i]["dur"]

    filter_complex = ";".join(prep + xfades)
    filter_script = out_path + ".filter"
    with open(filter_script, "w", encoding="utf-8") as f:
        f.write(filter_complex)

    cmd = [
        _ffmpeg(), "-y", *args,
        "-filter_complex_script", filter_script,
        "-map", "[v_final]",
        "-t", f"{total_dur:.3f}",
        *_encoder_args(),
        out_path,
    ]
    ok = _run(cmd, on_log)
    try:
        os.remove(filter_script)
    except Exception:
        pass
    return ok


def _mix_audio(video_path: str, audio_path: str, out_path: str,
               fade_in: float, fade_out: float, on_log) -> bool:
    """Накладывает аудиотрек на видео с fade in/out."""
    video_dur = _duration(video_path)
    fade_out_st = max(0.0, video_dur - fade_out)

    flt = (
        f"[1:a]"
        f"afade=t=in:st=0:d={fade_in:.2f},"
        f"afade=t=out:st={fade_out_st:.2f}:d={fade_out:.2f},"
        f"aloop=loop=-1:size=2000000000,"
        f"atrim=end={video_dur:.3f}"
        f"[aout]"
    )
    cmd = [
        _ffmpeg(), "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", flt,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",          # копируем видео без перекодирования — сохраняем цвет
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{video_dur:.3f}",
        out_path,
    ]
    return _run(cmd, on_log)


def render_clip(
    tracks: list[str],
    media_items: list[str],
    settings: dict,
    output_dir: str,
    on_log,
    on_progress,
) -> tuple[bool, str]:
    """
    tracks      — аудиофайлы в порядке воспроизведения
    media_items — видеофрагменты (без звука)
    settings    — {width, height, fps, transition, trans_duration, track_swoosh, fade_in, fade_out}
    output_dir  — папка для результата
    """
    try:
        if not tracks:
            return False, "Нет треков"
        if not media_items:
            return False, "Нет видеофрагментов"

        width      = settings.get("width", 1920)
        height     = settings.get("height", 1080)
        fps        = settings.get("fps", 25)
        transition = settings.get("transition", "fade")
        trans_dur  = settings.get("trans_duration", 0.5)
        fade_in    = settings.get("fade_in", 0.5)
        fade_out   = settings.get("fade_out", 0.5)

        tmp_dir = Path(output_dir) / "clip_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = str(Path(output_dir) / f"clip_{ts}.mp4")

        # Шаг 1: аудио
        on_log("Собираю аудиодорожку...")
        on_progress(5)
        audio_path = str(tmp_dir / "audio.wav")
        if not _build_audio_track(tracks, audio_path, on_log):
            return False, "Ошибка сборки аудио"

        total_dur = _duration(audio_path)
        if total_dur <= 0:
            return False, "Не удалось определить длину трека"
        on_log(f"Длина трека: {total_dur:.2f} с")

        # Шаг 2: нормализация видеофрагментов
        n = len(media_items)
        on_log(f"Нормализую {n} видеофрагментов...")
        base_segs = []
        for i, src in enumerate(media_items):
            on_progress(10 + int(i / n * 30))
            original_dur = _duration(src)
            out = str(tmp_dir / f"seg_{i:03d}.mp4")
            if not _normalize_video(src, out, width, height, fps, on_log):
                return False, f"Ошибка нормализации видео {i+1}"
            base_segs.append({"path": out, "dur": original_dur})
            on_log(f"  OK видео {i+1}: {original_dur:.2f} с")

        # Шаг 3: зацикливание если видеоряд короче трека
        total_video = sum(s["dur"] for s in base_segs)
        if total_video < total_dur and total_video > 0:
            cycles = int(total_dur / total_video) + 1
            on_log(f"Зацикливаю x{cycles} ({total_video:.1f}c / {total_dur:.1f}c)...")
            looped = []
            for c in range(cycles):
                for j, s in enumerate(base_segs):
                    looped_out = str(tmp_dir / f"seg_{c:02d}_{j:03d}.mp4")
                    shutil.copy2(s["path"], looped_out)
                    looped.append({"path": looped_out, "dur": s["dur"]})
            base_segs = looped

        segments = [
            {"path": s["path"], "dur": s["dur"], "trans": transition, "trans_dur": trans_dur}
            for s in base_segs
        ]

        # Шаг 4: склейка с переходами
        total_seg_dur = sum(s["dur"] for s in segments)
        on_log(f"Склеиваю {len(segments)} сегментов ({total_seg_dur:.1f}c -> {total_dur:.1f}c)...")
        on_progress(55)
        raw_video = str(tmp_dir / "raw.mp4")
        if not _concat_xfade(segments, raw_video, total_dur, on_log):
            return False, "Ошибка склейки видеоряда"

        # Шаг 5: финальный микс
        on_log("Микс видео + трек...")
        on_progress(80)
        if not _mix_audio(raw_video, audio_path, final_path, fade_in, fade_out, on_log):
            return False, "Ошибка финального микса"

        on_progress(100)
        on_log(f"OK Клип готов: {final_path}")
        return True, final_path

    except Exception as e:
        msg = str(e)[:300]
        log.error(f"clip_render: {msg}")
        return False, msg
