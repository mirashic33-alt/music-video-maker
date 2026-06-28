import math

FPS_DEFAULT = 30
SUPERSAMPLE = 2


def _param(name, label, type_, **kw):
    return {"name": name, "label": label, "type": type_, **kw}


def _vf_none(width, height, fps, duration, **p):
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps}"
    )


def _vf_kenburns(width, height, fps, duration, **p):
    zoom_speed = p.get("zoom_speed", 0.3)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    return (
        f"scale={ss_w}:{ss_h}:flags=lanczos,"
        f"zoompan="
        f"z='1+{zoom_speed}*on/{total}':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={total}:s={ss_w}x{ss_h}:fps={fps},"
        f"scale={width}:{height}:flags=lanczos"
    )


def _vf_zoom_out(width, height, fps, duration, **p):
    zoom_speed = p.get("zoom_speed", 0.3)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    return (
        f"scale={ss_w}:{ss_h}:flags=lanczos,"
        f"zoompan="
        f"z='1+{zoom_speed}*(1-on/{total})':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={total}:s={ss_w}x{ss_h}:fps={fps},"
        f"scale={width}:{height}:flags=lanczos"
    )


def _vf_kenburns_easing(width, height, fps, duration, **p):
    zoom_speed = p.get("zoom_speed", 0.3)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    Z = zoom_speed
    return (
        f"scale={ss_w}:{ss_h}:flags=lanczos,"
        f"zoompan="
        f"z='1+{Z}*(on/{total})*(on/{total})*(3-2*on/{total})':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={total}:s={ss_w}x{ss_h}:fps={fps},"
        f"scale={width}:{height}:flags=lanczos"
    )


def _vf_zoom_pan(width, height, fps, duration, **p):
    zoom_speed = p.get("zoom_speed", 0.4)
    pan_x = p.get("pan_x", 0.5)
    pan_y = p.get("pan_y", -0.3)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    return (
        f"scale={ss_w}:{ss_h}:flags=lanczos,"
        f"zoompan="
        f"z='1+{zoom_speed}*on/{total}':"
        f"x='min(max((iw/2-iw/zoom/2)*(1+{pan_x}*on/{total}),0),iw-iw/zoom)':"
        f"y='min(max((ih/2-ih/zoom/2)*(1+{pan_y}*on/{total}),0),ih-ih/zoom)':"
        f"d={total}:s={ss_w}x{ss_h}:fps={fps},"
        f"scale={width}:{height}:flags=lanczos"
    )


def _vf_pulse(width, height, fps, duration, **p):
    amplitude = p.get("amplitude", 0.04)
    speed = p.get("pulse_speed", 2.0)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    PI = math.pi
    freq = 2 * PI * speed
    A = amplitude
    return (
        f"scale={ss_w}:{ss_h}:flags=lanczos,"
        f"zoompan="
        f"z='1+{A}/2+{A}/2*sin({freq}*on/{total}-{PI/2})':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={total}:s={ss_w}x{ss_h}:fps={fps},"
        f"scale={width}:{height}:flags=lanczos"
    )


def _vf_vignette(width, height, fps, duration, **p):
    strength = p.get("vignette_strength", 0.6)
    zoom_speed = p.get("zoom_speed", 0.2)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    PI = math.pi
    parts = [f"scale={ss_w}:{ss_h}:flags=lanczos"]
    if zoom_speed > 0:
        parts.append(
            f"zoompan=z='1+{zoom_speed}*on/{total}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total}:s={ss_w}x{ss_h}:fps={fps}"
        )
    parts.append(f"scale={width}:{height}:flags=lanczos")
    if zoom_speed <= 0:
        parts.append(f"fps={fps}")
    angle = PI/2 - strength * (PI/2 - PI/6)
    parts.append(f"vignette=angle={angle:.4f}")
    contrast = 1.0 + strength * 0.12
    parts.append(f"eq=contrast={contrast:.3f}")
    return ",".join(parts)


def _vf_lofi(width, height, fps, duration, **p):
    zoom_speed = p.get("zoom_speed", 0.1)
    warmth = p.get("warmth", 0.6)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    parts = [f"scale={ss_w}:{ss_h}:flags=lanczos"]
    if zoom_speed > 0:
        parts.append(
            f"zoompan=z='1+{zoom_speed}*on/{total}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total}:s={ss_w}x{ss_h}:fps={fps}"
        )
    parts.append(f"scale={width}:{height}:flags=lanczos")
    if zoom_speed <= 0:
        parts.append(f"fps={fps}")
    w = warmth
    parts.append(
        f"colorbalance="
        f"rs={0.15*w:.3f}:gs={-0.05*w:.3f}:bs={0.20*w:.3f}:"
        f"rm={0.10*w:.3f}:gm={-0.03*w:.3f}:bm={0.12*w:.3f}:"
        f"rh={0.05*w:.3f}:gh={0.0:.3f}:bh={0.08*w:.3f}"
    )
    parts.append(f"eq=brightness=-0.04:contrast=0.88:saturation={1.1+0.3*w:.2f}")
    return ",".join(parts)


def _vf_cinematic(width, height, fps, duration, **p):
    zoom_speed = p.get("zoom_speed", 0.15)
    teal_orange = p.get("teal_orange", 0.7)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    parts = [f"scale={ss_w}:{ss_h}:flags=lanczos"]
    if zoom_speed > 0:
        parts.append(
            f"zoompan=z='1+{zoom_speed}*on/{total}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total}:s={ss_w}x{ss_h}:fps={fps}"
        )
    parts.append(f"scale={width}:{height}:flags=lanczos")
    if zoom_speed <= 0:
        parts.append(f"fps={fps}")
    to = teal_orange
    parts.append(
        f"colorbalance="
        f"rs={0.18*to:.3f}:gs={-0.04*to:.3f}:bs={-0.15*to:.3f}:"
        f"rm={0.08*to:.3f}:gm={-0.02*to:.3f}:bm={-0.08*to:.3f}:"
        f"rh={0.05*to:.3f}:gh={0.05*to:.3f}:bh={-0.10*to:.3f}"
    )
    parts.append(f"eq=contrast={1.0+0.15*to:.3f}:saturation={1.2+0.2*to:.2f}")
    parts.append(
        f"drawbox=x=0:y=0:w={width}:h={int(height*0.06)}:color=black:t=fill,"
        f"drawbox=x=0:y={int(height*0.94)}:w={width}:h={int(height*0.06)}:color=black:t=fill"
    )
    angle = math.pi / 2 - 0.25 * (math.pi / 2 - math.pi / 6)
    parts.append(f"vignette=angle={angle:.4f}")
    return ",".join(parts)


def _vf_neon(width, height, fps, duration, **p):
    zoom_speed = p.get("zoom_speed", 0.12)
    intensity = p.get("intensity", 0.8)
    ss = SUPERSAMPLE
    ss_w, ss_h = width * ss, height * ss
    total = fps * int(duration)
    parts = [f"scale={ss_w}:{ss_h}:flags=lanczos"]
    if zoom_speed > 0:
        parts.append(
            f"zoompan=z='1+{zoom_speed}*on/{total}':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total}:s={ss_w}x{ss_h}:fps={fps}"
        )
    parts.append(f"scale={width}:{height}:flags=lanczos")
    if zoom_speed <= 0:
        parts.append(f"fps={fps}")
    iv = intensity
    parts.append(
        f"colorbalance="
        f"rs={-0.10*iv:.3f}:gs={-0.05*iv:.3f}:bs={0.25*iv:.3f}:"
        f"rm={-0.05*iv:.3f}:gm={0.02*iv:.3f}:bm={0.15*iv:.3f}:"
        f"rh={0.05*iv:.3f}:gh={-0.05*iv:.3f}:bh={0.10*iv:.3f}"
    )
    parts.append(f"eq=contrast={1.1+0.15*iv:.3f}:saturation={1.3+0.4*iv:.2f}:brightness=-0.05")
    parts.append(f"hue=s={1.2+0.5*iv:.2f}")
    return ",".join(parts)


EFFECTS = [
    {"id": "none",             "name": "Без эффекта",              "params": [], "build_vf": _vf_none},
    {"id": "kenburns",         "name": "Ken Burns (наезд)",         "params": [_param("zoom_speed", "Скорость зума", "float", min=0.05, max=0.8, default=0.3, step=0.05)], "build_vf": _vf_kenburns},
    {"id": "zoom_out",         "name": "Ken Burns (отъезд)",        "params": [_param("zoom_speed", "Скорость зума", "float", min=0.05, max=0.8, default=0.3, step=0.05)], "build_vf": _vf_zoom_out},
    {"id": "kenburns_easing",  "name": "Ken Burns (плавный)",       "params": [_param("zoom_speed", "Скорость зума", "float", min=0.05, max=0.8, default=0.3, step=0.05)], "build_vf": _vf_kenburns_easing},
    {"id": "zoom_pan",         "name": "Zoom + Pan",                "params": [_param("zoom_speed", "Скорость", "float", min=0.05, max=0.8, default=0.4, step=0.05), _param("pan_x", "Сдвиг X", "float", min=-1.0, max=1.0, default=0.5, step=0.1), _param("pan_y", "Сдвиг Y", "float", min=-1.0, max=1.0, default=-0.3, step=0.1)], "build_vf": _vf_zoom_pan},
    {"id": "pulse",            "name": "Пульсация",                 "params": [_param("amplitude", "Амплитуда", "float", min=0.01, max=0.1, default=0.04, step=0.01), _param("pulse_speed", "Скорость", "float", min=0.5, max=5.0, default=2.0, step=0.5)], "build_vf": _vf_pulse},
    {"id": "vignette",         "name": "Виньетка",                  "params": [_param("vignette_strength", "Сила", "float", min=0.1, max=1.0, default=0.6, step=0.1), _param("zoom_speed", "Зум", "float", min=0.0, max=0.5, default=0.2, step=0.05)], "build_vf": _vf_vignette},
    {"id": "lofi",             "name": "Lofi / Dreamy",             "params": [_param("warmth", "Тёплость", "float", min=0.1, max=1.0, default=0.6, step=0.1), _param("zoom_speed", "Зум", "float", min=0.0, max=0.4, default=0.1, step=0.05)], "build_vf": _vf_lofi},
    {"id": "cinematic",        "name": "Cinematic (Teal & Orange)", "params": [_param("teal_orange", "Интенсивность", "float", min=0.1, max=1.0, default=0.7, step=0.1), _param("zoom_speed", "Зум", "float", min=0.0, max=0.4, default=0.15, step=0.05)], "build_vf": _vf_cinematic},
    {"id": "neon",             "name": "Neon / Cyberpunk",          "params": [_param("intensity", "Интенсивность", "float", min=0.1, max=1.0, default=0.8, step=0.1), _param("zoom_speed", "Зум", "float", min=0.0, max=0.4, default=0.12, step=0.05)], "build_vf": _vf_neon},
]


def get_effect(effect_id: str) -> dict | None:
    for e in EFFECTS:
        if e["id"] == effect_id:
            return e
    return None


def get_effect_names() -> list[tuple[str, str]]:
    return [(e["id"], e["name"]) for e in EFFECTS]


def build_vf(effect_id: str, width: int, height: int, fps: int, duration: float, **params) -> str:
    effect = get_effect(effect_id)
    if not effect:
        return _vf_none(width, height, fps, duration)
    return effect["build_vf"](width, height, fps, duration, **params)
