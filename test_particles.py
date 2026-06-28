"""
test_particles.py — тест эффекта частиц (запускать отдельно)
Берёт первую картинку из img/, рендерит 15 сек, сохраняет test_particles.mp4
"""
import math
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

# ── настройки ──────────────────────────────────────────────────────────────
DUR     = 15        # секунд
FPS     = 25
W, H    = 1920, 1080
N       = 15        # количество частиц
# ───────────────────────────────────────────────────────────────────────────

ROOT    = Path(__file__).parent
IMG_DIR = ROOT / "img"
OUT     = ROOT / "test_particles.mp4"
_BIN    = ROOT / "bin" / "ffmpeg.exe"
FFMPEG  = str(_BIN) if _BIN.exists() else "ffmpeg"

EXTS = {".jpg", ".jpeg", ".png", ".webp"}
imgs = sorted(f for f in IMG_DIR.iterdir() if f.suffix.lower() in EXTS)
if not imgs:
    sys.exit("Нет картинок в img/")
src = imgs[0]
print(f"Картинка: {src.name}")

# ── предподготовка: масштабируем под Ken Burns (zoom-in 0→8%) ──────────────
TOTAL   = DUR * FPS
MAX_Z   = 1.08
bw, bh  = int(W * MAX_Z), int(H * MAX_Z)
base_big = Image.open(src).convert("RGB").resize((bw, bh), Image.LANCZOS)
print(f"Подготовлено. Рендерю {TOTAL} кадров ({DUR} сек × {FPS} fps)...")


def get_base_frame(fi: int) -> Image.Image:
    """Кадр картинки с медленным zoom-in."""
    p   = fi / max(1, TOTAL - 1)          # 0.0 → 1.0
    cw  = int(W * (1.0 + p * (MAX_Z - 1.0)))
    ch  = int(H * (1.0 + p * (MAX_Z - 1.0)))
    x0  = (bw - cw) // 2
    y0  = (bh - ch) // 2
    return base_big.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.BILINEAR)


def draw_particles(img: Image.Image, fi: int) -> Image.Image:
    """Белые точки с настоящим размытым свечением (Gaussian blur)."""
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    core_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    cd = ImageDraw.Draw(core_layer)

    for i in range(N):
        x_base = (i * 137.5) % W
        sp     = 0.4 + ((i * 53) % 100) / 120
        ph     = (i * 41) % 360
        sz     = 1 + ((i * 17) % 3)   # ядро: 1–3 px

        y  = ((fi * sp + ph * 5) % (H + 130)) - 65
        x  = x_base + math.sin((fi + ph) / 40) * 38

        op = 0.20 + abs(math.sin((fi + ph) / 30)) * 0.45
        a  = int(op * 255)

        # на glow_layer рисуем увеличенный круг — он потом размоется
        g = sz * 4
        gd.ellipse([x - g, y - g, x + g, y + g], fill=(255, 255, 255, a))
        # на core_layer — острое белое ядро
        cd.ellipse([x - sz, y - sz, x + sz, y + sz], fill=(255, 255, 255, a))

    # размываем glow-слой → получаем мягкое свечение
    glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=5))

    base = img.convert("RGBA")
    result = Image.alpha_composite(base, glow_blurred)
    result = Image.alpha_composite(result, core_layer)
    return result.convert("RGB")


# ── FFmpeg принимает кадры через stdin ─────────────────────────────────────
cmd = [
    FFMPEG, "-y",
    "-f", "rawvideo", "-vcodec", "rawvideo",
    "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(FPS),
    "-i", "pipe:0",
    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
    "-pix_fmt", "yuv420p",
    str(OUT),
]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

for fi in range(TOTAL):
    if fi % FPS == 0:
        print(f"  {fi // FPS + 1}/{DUR} сек", end="\r")
    frame = draw_particles(get_base_frame(fi), fi)
    proc.stdin.write(frame.tobytes())

proc.stdin.close()
proc.wait()
print(f"\nГотово → {OUT}")
