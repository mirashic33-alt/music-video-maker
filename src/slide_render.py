"""
Рендер слайдшоу: картинки + Ken Burns + частицы + xfade + аудио.
"""
import math
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from src.logger import get_logger

log = get_logger()

_BIN_DIR = Path(__file__).parent.parent / "bin"
_GAP_SECONDS = 2.0
_N_PARTICLES = 15
_LOOP_DUR    = 10   # секунд для зацикленного оверлея частиц


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
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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


def _build_audio_track(tracks: list[str], out_path: str, on_log) -> bool:
    if not tracks:
        return False
    if len(tracks) == 1:
        cmd = [_ffmpeg(), "-y", "-i", tracks[0], "-c:a", "pcm_s16le", out_path]
        return _run(cmd, on_log)

    silence = out_path + "_gap.wav"
    if not _run([_ffmpeg(), "-y", "-f", "lavfi",
                 "-i", "anullsrc=r=44100:cl=stereo",
                 "-t", str(_GAP_SECONDS), "-c:a", "pcm_s16le", silence], on_log):
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


def _make_slide_video(img_path: str, out_path: str,
                      duration: float, fps: int, w: int, h: int,
                      effect: str, on_log) -> bool:
    """Картинка → видео: Ken Burns (PIL affine) или статика (FFmpeg)."""
    if effect == "none":
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p")
        cmd = [_ffmpeg(), "-y", "-loop", "1", "-i", img_path,
               "-vf", vf, "-t", f"{duration:.3f}",
               "-c:v", "libx264", "-preset", "fast", "-crf", "18",
               "-pix_fmt", "yuv420p", out_path]
        return _run(cmd, on_log)

    frames = max(1, int(duration * fps))
    buf_w, buf_h = w * 2, h * 2  # 2× буфер для качественного сэмплинга

    img = Image.open(img_path).convert("RGB")
    iw, ih = img.size
    sc = max(buf_w / iw, buf_h / ih)
    bw, bh = int(iw * sc + 0.5), int(ih * sc + 0.5)
    img_buf = img.resize((bw, bh), Image.LANCZOS)
    xc, yc = (bw - buf_w) // 2, (bh - buf_h) // 2
    img_buf = img_buf.crop((xc, yc, xc + buf_w, yc + buf_h))

    enc = subprocess.Popen(
        [_ffmpeg(), "-y",
         "-f", "rawvideo", "-vcodec", "rawvideo",
         "-s", f"{w}x{h}", "-pix_fmt", "rgb24", "-r", str(fps),
         "-i", "pipe:0",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18",
         "-pix_fmt", "yuv420p", out_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **_kw()
    )

    try:
        for fi in range(frames):
            t = fi / max(1, frames - 1)
            e = t * t * (3 - 2 * t)  # smoothstep

            cx, cy = buf_w / 2.0, buf_h / 2.0

            if effect == "zoomin":
                zoom = 1.0 + 0.25 * e
            elif effect == "zoomout":
                zoom = 1.25 - 0.25 * e
            elif effect == "panleft":
                zoom = 1.25
                vp = buf_w / zoom
                cx = vp / 2.0 + (buf_w - vp) * (1.0 - e)
            else:  # panright
                zoom = 1.25
                vp = buf_w / zoom
                cx = vp / 2.0 + (buf_w - vp) * e

            vp_w = buf_w / zoom
            vp_h = buf_h / zoom
            x0 = cx - vp_w / 2.0
            y0 = cy - vp_h / 2.0
            sx = vp_w / w
            sy = vp_h / h

            frame = img_buf.transform(
                (w, h), Image.AFFINE,
                (sx, 0.0, x0, 0.0, sy, y0),
                Image.BICUBIC
            )
            enc.stdin.write(frame.tobytes())
    except Exception as ex:
        on_log(f"! PIL рендер слайда: {ex}")
    finally:
        enc.stdin.close()
        enc.wait()

    return enc.returncode == 0


def _concat_xfade(segments: list[str], durs: list[float],
                  out_path: str, total_dur: float,
                  transition: str, trans_dur: float, on_log) -> bool:
    n = len(segments)
    if n == 0:
        return False
    if n == 1:
        cmd = [_ffmpeg(), "-y", "-i", segments[0],
               "-t", f"{total_dur:.3f}", "-c", "copy", out_path]
        return _run(cmd, on_log)

    args = []
    for s in segments:
        args += ["-i", s]

    prep = [f"[{i}:v]setsar=1/1,format=yuv420p[v_in{i}]" for i in range(n)]
    xfades = []
    prev = "[v_in0]"
    offset = durs[0] - trans_dur

    for i in range(1, n):
        nxt = f"[v_in{i}]"
        out = f"[v_out{i}]" if i < n - 1 else "[v_final]"
        td  = max(0.04, min(trans_dur, min(durs[i - 1], durs[i]) * 0.4))
        xfades.append(
            f"{prev}{nxt}xfade=transition={transition}:"
            f"duration={td:.3f}:offset={offset:.3f}{out}"
        )
        prev = out
        offset += durs[i] - trans_dur

    filter_str = ";".join(prep + xfades)
    fscript = out_path + ".filter"
    with open(fscript, "w", encoding="utf-8") as f:
        f.write(filter_str)

    cmd = [
        _ffmpeg(), "-y", *args,
        "-filter_complex_script", fscript,
        "-map", "[v_final]",
        "-t", f"{total_dur:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        out_path,
    ]
    ok = _run(cmd, on_log)
    try:
        os.remove(fscript)
    except Exception:
        pass
    return ok


def _generate_particle_loop(out_path: str, fps: int, w: int, h: int, on_log) -> bool:
    """Генерирует короткий видеолуп с частицами (чёрный фон, белые точки)."""
    on_log("Генерирую частицы...")
    total_frames = _LOOP_DUR * fps

    cmd = [
        _ffmpeg(), "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **_kw())
    try:
        for fi in range(total_frames):
            base       = Image.new("RGB", (w, h), (0, 0, 0))
            glow_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            core_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow_layer)
            cd = ImageDraw.Draw(core_layer)

            for i in range(_N_PARTICLES):
                x_base = (i * 137.5) % w
                sp = 0.4 + ((i * 53) % 100) / 120
                ph = (i * 41) % 360
                sz = 1 + ((i * 17) % 3)
                y  = ((fi * sp + ph * 5) % (h + 130)) - 65
                x  = x_base + math.sin((fi + ph) / 40) * 38
                op = 0.20 + abs(math.sin((fi + ph) / 30)) * 0.45
                a  = int(op * 255)
                g  = sz * 4
                gd.ellipse([x - g, y - g, x + g, y + g], fill=(255, 255, 255, a))
                cd.ellipse([x - sz, y - sz, x + sz, y + sz], fill=(255, 255, 255, a))

            glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=5))
            result = Image.alpha_composite(base.convert("RGBA"), glow_blurred)
            result = Image.alpha_composite(result, core_layer)
            proc.stdin.write(result.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        proc.wait()

    return proc.returncode == 0


def _mix_audio(video_path: str, audio_path: str, out_path: str,
               fade_in: float, fade_out: float, on_log) -> bool:
    video_dur    = _duration(video_path)
    fade_out_st  = max(0.0, video_dur - fade_out)
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
        "-i", video_path, "-i", audio_path,
        "-filter_complex", flt,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",          # копируем видео без перекодирования — сохраняем цвет
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{video_dur:.3f}",
        out_path,
    ]
    return _run(cmd, on_log)


def _esc_dt(text: str) -> str:
    """Экранирует текст для FFmpeg drawtext."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'",  "\\'")
    text = text.replace(":",  "\\:")
    text = text.replace("%",  "%%")
    return text


def _add_watermark(src: str, dst: str,
                   channel: str, ch_font: str, ch_size: int,
                   track_name: str, tr_font: str, tr_size: int,
                   on_log) -> bool:
    parts = []
    if channel:
        fp = f"C\\:/Windows/Fonts/{ch_font}"
        t  = _esc_dt(channel)
        parts.append(
            f"drawtext=fontfile='{fp}':text='{t}'"
            f":x=w-tw-20:y=h-th-20"
            f":fontsize={ch_size}:fontcolor=white@0.4"
        )
    if track_name:
        fp = f"C\\:/Windows/Fonts/{tr_font}"
        t  = _esc_dt(track_name)
        parts.append(
            f"drawtext=fontfile='{fp}':text='{t}'"
            f":x=(w-tw)/2:y=30"
            f":fontsize={tr_size}:fontcolor=white"
            f":alpha='if(lt(t,5),0,if(lt(t,6),0.85*(t-5),if(lt(t,25),0.85,if(lt(t,30),0.85*(30-t)/5,0))))'"
        )

    cmd = [
        _ffmpeg(), "-y", "-i", src,
        "-vf", ",".join(parts),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "copy",
        dst,
    ]
    return _run(cmd, on_log)


_EFFECTS = ["zoomin", "zoomout", "panleft", "panright"]


def render_slideshow(
    images:     list[str],
    tracks:     list[str],
    settings:   dict,
    output_dir: str,
    on_log,
    on_progress,
) -> tuple[bool, str]:
    try:
        if not tracks:
            return False, "Нет треков"
        if not images:
            return False, "Нет слайдов"

        mode       = settings.get("mode", "auto")
        dur_per    = float(settings.get("dur_per_img", 20.0))
        transition = settings.get("transition", "fade")
        trans_dur  = float(settings.get("trans_duration", 0.8))
        fade_in    = float(settings.get("fade_in", 1.0))
        fade_out   = float(settings.get("fade_out", 2.0))
        kenburns   = bool(settings.get("kenburns", True))
        particles  = bool(settings.get("particles", True))
        w          = int(settings.get("width", 1920))
        h          = int(settings.get("height", 1080))
        fps        = int(settings.get("fps", 25))

        tmp_dir = Path(output_dir) / "slide_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = str(Path(output_dir) / f"slideshow_{ts}.mp4")

        # ── Шаг 1: аудио ──────────────────────────────────────────────────
        on_log("Собираю аудиодорожку...")
        on_progress(5)
        audio_path = str(tmp_dir / "audio.wav")
        if not _build_audio_track(tracks, audio_path, on_log):
            return False, "Ошибка сборки аудио"

        total_dur = _duration(audio_path)
        if total_dur <= 0:
            return False, "Не удалось определить длину трека"
        on_log(f"Длина трека: {total_dur:.2f} с")

        # ── Шаг 2: список слайдов и длительности ──────────────────────────
        if mode == "loop":
            slide_list, slide_durs = [], []
            t, idx = 0.0, 0
            while t < total_dur:
                remaining = total_dur - t
                d = min(dur_per, remaining)
                slide_list.append(images[idx % len(images)])
                slide_durs.append(max(0.5, d))
                t += dur_per
                idx += 1
        else:
            slide_list = images
            each = total_dur / len(images)
            slide_durs = [each] * len(images)

        n_slides = len(slide_list)
        on_log(f"Слайдов: {n_slides}, ~{slide_durs[0]:.1f} с каждый")

        # ── Шаг 3: Ken Burns на каждую картинку ───────────────────────────
        on_log("Применяю Ken Burns...")
        on_progress(10)
        slide_videos = []
        for i, (img, dur) in enumerate(zip(slide_list, slide_durs)):
            on_progress(10 + int(i / n_slides * 45))
            effect = _EFFECTS[i % len(_EFFECTS)] if kenburns else "none"
            out = str(tmp_dir / f"slide_{i:04d}.mp4")
            if not _make_slide_video(img, out, dur, fps, w, h, effect, on_log):
                return False, f"Ошибка обработки слайда {i + 1}"
            slide_videos.append(out)
            on_log(f"  {i + 1}/{n_slides}: {Path(img).name} [{effect}]")

        # ── Шаг 4: склейка с xfade ────────────────────────────────────────
        on_log("Склеиваю слайды...")
        on_progress(60)
        raw_video = str(tmp_dir / "raw.mp4")
        if not _concat_xfade(slide_videos, slide_durs, raw_video,
                              total_dur, transition, trans_dur, on_log):
            return False, "Ошибка склейки слайдов"

        # ── Шаг 5: частицы (screen blend) ─────────────────────────────────
        if particles:
            on_log("Накладываю частицы...")
            on_progress(70)
            ploop = str(tmp_dir / "ploop.mp4")
            if _generate_particle_loop(ploop, fps, w, h, on_log):
                with_p = str(tmp_dir / "with_particles.mp4")
                vdur   = _duration(raw_video)
                loop_frames = _LOOP_DUR * fps
                flt = (
                    f"[1:v]loop=loop=-1:size={loop_frames}:start=0,"
                    f"trim=duration={vdur:.3f},hue=s=0[part];"
                    f"[0:v][part]blend="
                    f"c0_expr='A+B-A*B/255':"
                    f"c1_expr='A':"
                    f"c2_expr='A'[v]"
                )
                cmd = [
                    _ffmpeg(), "-y",
                    "-i", raw_video, "-i", ploop,
                    "-filter_complex", flt,
                    "-map", "[v]",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-pix_fmt", "yuv420p", with_p,
                ]
                if _run(cmd, on_log):
                    raw_video = with_p
                else:
                    on_log("Предупреждение: частицы не наложились, продолжаю без них")
            else:
                on_log("Предупреждение: частицы не сгенерированы")

        # ── Шаг 6: финальный микс ─────────────────────────────────────────
        on_log("Микс видео + аудио...")
        on_progress(85)
        channel    = settings.get("channel", "").strip()
        track_name = settings.get("track_name", "").strip()
        need_wm    = bool(channel or track_name)
        mixed_path = str(tmp_dir / "mixed.mp4") if need_wm else final_path

        if not _mix_audio(raw_video, audio_path, mixed_path, fade_in, fade_out, on_log):
            return False, "Ошибка финального микса"

        if need_wm:
            on_log("Добавляю подписи...")
            on_progress(93)
            ch_font = settings.get("ch_font", "arial.ttf")
            ch_size = settings.get("ch_size", 28)
            tr_font = settings.get("tr_font", "arial.ttf")
            tr_size = settings.get("tr_size", 42)
            if not _add_watermark(mixed_path, final_path,
                                  channel, ch_font, ch_size,
                                  track_name, tr_font, tr_size, on_log):
                on_log("Предупреждение: подписи не добавились, сохраняю без них")
                import shutil as _sh
                _sh.copy2(mixed_path, final_path)

        on_progress(100)
        on_log(f"OK Слайдшоу готово: {final_path}")
        return True, final_path

    except Exception as e:
        msg = str(e)[:300]
        log.error(f"slide_render: {msg}")
        return False, msg
