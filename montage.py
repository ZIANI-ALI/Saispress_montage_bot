"""Montage d video Saispress: format 9:16, logo, w titre f panel navy b animation.

L animation (b7al l exemple d l brand):
  dkhla: l khatt gold kaykber, l pill d l rkn w l panel kayban b fade, mn ba3d l titre kaytkchef men l imin l l issar.
  khrja: l titre kaytkhba men l issar l l imin, mn ba3d l panel w l pill w l khatt.
L logo kaybqa l video kamla.

Qualité: nefs l résolution (ila l video deja 9:16), x264 CRF 17 preset slow, l son kaytnsakh kif howa.
Videowat HDR (iPhone) kaytbddlo l SDR b tone-mapping bach l alwan ma ybhtouch.
"""
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageDraw, ImageFont, features

ASSETS = Path(__file__).resolve().parent / "assets"
NAVY = (13, 26, 60)
GOLD = (190, 150, 33)
WHITE = (255, 255, 255)
PANEL_ALPHA = 240
FONT_TITLE = "Tajawal-ExtraBold.ttf"
FONT_PILL = "Tajawal-Bold.ttf"

CRF = os.environ.get("MONTAGE_CRF", "17")
PRESET = os.environ.get("MONTAGE_PRESET", "slow")
TITLE_SECONDS = float(os.environ.get("TITLE_SECONDS", "4.2"))  # ch7al ybqa l titre kaml 9bel ma ykhrej

HDR_TRC = {"smpte2084", "arib-std-b67"}
COPY_AUDIO = {"aac", "mp3", "alac", "opus"}

if not features.check("raqm"):
    raise RuntimeError("Pillow bla raqm: l 7rouf l 3arbiya ghaykhrjo mfer9in (khass libraqm/libfribidi)")


# ───────────────────────── probe ─────────────────────────

@dataclass
class Probe:
    width: int          # mn ba3d rotation
    height: int
    fps: float
    duration: float
    hdr: bool
    audio: str | None   # codec d son, wla None


def _fps(rate: str) -> float:
    try:
        n, d = rate.split("/")
        return float(n) / float(d) if float(d) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: Path) -> Probe:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    if v is None:
        raise ValueError("had l fichier ma fihch video")
    a = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if "rotate" in v.get("tags", {}):
        rot = int(v["tags"]["rotate"])
    if abs(rot) % 180 == 90:
        w, h = h, w
    fps = _fps(v.get("avg_frame_rate", "0/0")) or _fps(v.get("r_frame_rate", "0/0")) or 30.0
    if fps > 120:  # timebase ghalat f chi fichiers
        fps = 30.0
    dur = float(data["format"].get("duration") or v.get("duration") or 0)
    return Probe(w, h, fps, dur, v.get("color_transfer") in HDR_TRC, a.get("codec_name") if a else None)


# ───────────────────────── texte ─────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSETS / "fonts" / name), size, layout_engine=ImageFont.Layout.RAQM)


def _width(text: str, fnt) -> float:
    return fnt.getlength(text, direction="rtl")


def clean_title(title: str) -> str:
    """N7ayydo emoji w rmouz ma kaybanouch f l font."""
    t = re.sub(r"[^\w\s؀-ۿ.,:;!?«»\"'()%\-–—،؛؟]", "", title)
    return re.sub(r"\s+", " ", t).strip(" -–—")


def _wrap(text: str, fnt, maxw: float) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if not cur or _width(t, fnt) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + [cur] if cur else lines


def _fit(text: str, maxw: float, s: float):
    """3 stoura f l a9sa b taille kbira; ila ma dkhelch kanssghro, w f l akhir 4 stoura."""
    for max_lines, hi, lo in ((3, 37, 30), (4, 30, 25)):
        for size in range(hi, lo - 1, -1):
            fnt = _font(FONT_TITLE, round(size * s))
            lines = _wrap(text, fnt, maxw)
            if len(lines) <= max_lines:
                return fnt, lines
    return fnt, lines


# ───────────────────────── overlay d titre ─────────────────────────

@dataclass
class Overlay:
    x: int
    y: int
    layers: dict          # Image RGBA d kol 3onsor, b nefs l 7ajm
    text_box: tuple       # (left, right) d l nass f l overlay
    length: float         # ch7al kaydoum l overlay b tawani
    t_out: float


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _prog(t: float, a: float, b: float) -> float:
    return _ease((t - a) / (b - a))


def build_overlay(W: int, H: int, title: str, category: str | None, duration: float) -> Overlay:
    s = W / 720  # l exemple 720x1280, kolchi kaytkber b nisba
    px0, px1 = round(62 * s), round(650 * s)          # panel
    pad_r, pad_l = round(9 * s), round(18 * s)
    pad_t, pad_b = round(24 * s), round(40 * s)
    fnt, lines = _fit(title, px1 - px0 - pad_r - pad_l, s)
    asc, desc = fnt.getmetrics()
    lh = round(fnt.size * 1.18)
    ptop_abs = round(745 * s)
    ph = pad_t + lh * (len(lines) - 1) + asc + desc + pad_b
    bar_x0, bar_x1 = px1 + round(2 * s), px1 + round(8 * s)

    pill_h = round(27 * s)
    pill_gap = round(4 * s)
    x0 = px0
    x1 = bar_x1 + round(2 * s)
    y0 = ptop_abs - pill_gap - pill_h
    ow, oh = x1 - x0, ptop_abs + ph - y0
    ox = lambda x: x - x0  # noqa: E731
    pt = ptop_abs - y0     # top d l panel f l overlay

    def layer():
        return Image.new("RGBA", (ow, oh), (0, 0, 0, 0))

    panel = layer()
    ImageDraw.Draw(panel).rectangle((0, pt, ox(px1) - 1, oh - 1), fill=(*NAVY, PANEL_ALPHA))

    bar = layer()
    ImageDraw.Draw(bar).rectangle((ox(bar_x0), pt + round(26 * s), ox(bar_x1) - 1, oh - round(40 * s)),
                                  fill=(*GOLD, 255))

    pill = layer()
    if category:
        pf = _font(FONT_PILL, round(19 * s))
        right = ox(round(643 * s))
        tw = _width(category, pf)
        left = right - tw - 2 * round(28 * s)
        d = ImageDraw.Draw(pill)
        d.rounded_rectangle((left, 0, right, pill_h), radius=pill_h // 2, fill=(*GOLD, 255))
        d.text((right - round(28 * s), pill_h / 2 + round(1 * s)), category, font=pf, fill=NAVY,
               anchor="rm", direction="rtl")

    text = layer()
    d = ImageDraw.Draw(text)
    right = ox(px1) - pad_r
    top = pt + pad_t
    lefts = []
    for i, ln in enumerate(lines):
        d.text((right, top + i * lh), ln, font=fnt, fill=WHITE, anchor="ra", direction="rtl")
        lefts.append(right - _width(ln, fnt))

    t_out = max(1.5, min(TITLE_SECONDS, duration - 0.6)) if duration else TITLE_SECONDS
    return Overlay(x0, y0, {"panel": panel, "bar": bar, "pill": pill, "text": text},
                   (int(min(lefts)) - 2, right + 2), t_out + 0.40, t_out)


def _alpha(img: Image.Image, k: float) -> Image.Image:
    if k >= 1:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * k)))
    return out


def _wipe_mask(size, left: float, right: float, feather: int) -> Image.Image:
    """Mask kayban ghir bin left w right, b 7afa nay3a."""
    w, h = size
    row = Image.new("L", (w, 1), 0)
    px = row.load()
    for x in range(w):
        a = min((x - left) / feather + 1, (right - x) / feather + 1)
        px[x, 0] = int(255 * min(1.0, max(0.0, a)))
    return row.resize((w, h))


# Tranches d l panel: (bdya, nihaya b nisba l l 3lw, ittijah d z-zl9a, ta2khir)
SLICES = ((0.00, 0.28, 1, 0.00), (0.28, 0.72, -1, 0.03), (0.72, 1.00, 1, 0.06))


def _panel_slices(panel: Image.Image, out: Image.Image, k_in: float, k_out: float,
                  t: float, a: float, b: float, to: float) -> None:
    """Panel f 3 tranches: kol wa7da katzl9 men jenb w katban b chwiya (b7al l exemple)."""
    bbox = panel.getbbox()
    if not bbox:
        return
    x0, y0, x1, y1 = bbox
    amp = (x1 - x0) * 0.07
    for f0, f1, sign, delay in SLICES:
        ki = _prog(t, a + delay, b + delay) * k_in
        ko = _prog(t, to + 0.05 + delay / 2, to + 0.22 + delay / 2) if t >= to else 0.0
        k = ki * (1 - ko)
        if k <= 0:
            continue
        sy0, sy1 = y0 + round((y1 - y0) * f0), y0 + round((y1 - y0) * f1)
        strip = panel.crop((0, sy0, panel.width, sy1))
        dx = round(sign * amp * ((1 - ki) - ko))
        if dx < 0:
            strip, dx = strip.crop((-dx, 0, strip.width, strip.height)), 0
        out.alpha_composite(_alpha(strip, k), (dx, sy0))


def render_frame(ov: Overlay, t: float) -> Image.Image:
    L = ov.layers
    ow, oh = L["panel"].size
    out = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
    to = ov.t_out
    tl, tr = ov.text_box
    feather = max(8, (tr - tl) // 14)

    # dkhla (30 fps: pill f3, khatt f3-9, panel f7-14, ktaba f9-14)
    pill_k = _prog(t, 0.07, 0.25)
    bar_k = _prog(t, 0.10, 0.30)
    reveal = _prog(t, 0.28, 0.50)
    # khrja (~4.2s): ktaba katmsa7 men l issar l l imin, panel w l khatt w l pill kaytfaw
    hide = _prog(t, to, to + 0.15) if t >= to else 0.0
    if t >= to:
        pill_k *= 1 - _prog(t, to + 0.08, to + 0.28)
        bar_k *= 1 - _prog(t, to + 0.03, to + 0.18)

    _panel_slices(L["panel"], out, 1.0, 1.0, t, 0.22, 0.45, to)
    if bar_k > 0:
        bar = L["bar"]
        bbox = bar.getbbox()
        if bbox:
            cy = (bbox[1] + bbox[3]) / 2
            half = (bbox[3] - bbox[1]) / 2 * bar_k
            m = Image.new("L", bar.size, 0)
            ImageDraw.Draw(m).rectangle((0, round(cy - half), ow, round(cy + half)), fill=255)
            out.alpha_composite(Image.composite(bar, Image.new("RGBA", bar.size), m))
    if pill_k > 0:
        out.alpha_composite(_alpha(L["pill"], pill_k))
    if reveal > 0 and hide < 1:
        # dkhla: katban men l issar l l imin. khrja: katmsa7 f nefs l ittijah.
        right = tl - feather + (tr - tl + 2 * feather) * reveal
        left = tl - feather + (tr - tl + 2 * feather) * hide
        m = _wipe_mask((ow, oh), left, right, feather)
        txt = L["text"].copy()
        txt.putalpha(ImageChops.multiply(txt.getchannel("A"), m))
        out.alpha_composite(txt)
    return out


def render_overlay_frames(ov: Overlay, fps: float, folder: Path) -> int:
    n = math.ceil(ov.length * fps) + 1
    for i in range(n):
        render_frame(ov, i / fps).save(folder / f"f{i:05d}.png", compress_level=1)
    return n


def logo_image(W: int) -> tuple[Image.Image, int, int]:
    s = W / 720
    lg = Image.open(ASSETS / "logo.png").convert("RGBA")
    w = round(100 * s)
    lg = lg.resize((w, round(lg.height * w / lg.width)), Image.LANCZOS)
    return lg, round(648 * s) - w, round(190 * s)


# ───────────────────────── ffmpeg ─────────────────────────

def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def out_size(p: Probe) -> tuple[int, int, bool]:
    """(W, H, deja_9_16). Ila l video deja 9:16 kanbqaw 3la nefs l résolution."""
    if abs(p.width / p.height - 9 / 16) < 0.02:
        return _even(p.width), _even(p.height), True
    W = 1080 if max(p.width, p.height) >= 1280 else 720
    return W, W * 16 // 9, False


def tonemap_available() -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return " zscale " in out and " tonemap " in out


def build_filter(p: Probe, W: int, H: int, native: bool, logo_xy, ov: Overlay) -> str:
    chain = []
    if p.hdr and tonemap_available():
        chain.append("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                     "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
    chain.append("format=yuv420p")
    pre = ",".join(chain)
    if native:
        g = f"[0:v]{pre},scale={W}:{H}:flags=lanczos,setsar=1[base];"
    else:
        # fond flou (mn nefs l video) w l video kamla f l wst
        bw, bh = W // 8, H // 8
        g = (f"[0:v]{pre},split[a][b];"
             f"[a]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
             f"gblur=sigma=6,eq=brightness=-0.10:saturation=0.9,scale={W}:{H}:flags=bicubic,setsar=1[bg];"
             f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1[fg];"
             f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];")
    lx, ly = logo_xy
    g += (f"[base][1:v]overlay={lx}:{ly}[lg];"
          f"[lg][2:v]overlay={ov.x}:{ov.y}:eof_action=pass,format=yuv420p[v]")
    return g


def montage(src: Path, dst: Path, title: str, category: str | None = None,
            progress: Callable[[float], None] | None = None) -> Probe:
    p = probe(src)
    W, H, native = out_size(p)
    title = clean_title(title)
    if not title:
        raise ValueError("titre khawi")
    ov = build_overlay(W, H, title, clean_title(category) if category else None, p.duration)
    work = Path(tempfile.mkdtemp(prefix="ov_"))
    try:
        lg, lx, ly = logo_image(W)
        lg.save(work / "logo.png")
        render_overlay_frames(ov, p.fps, work)
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
               "-i", str(src),
               "-i", str(work / "logo.png"),  # tswira wa7da: overlay kay3awedha 7tta l akhir
               "-framerate", f"{p.fps:.5f}", "-i", str(work / "f%05d.png"),
               "-filter_complex", build_filter(p, W, H, native, (lx, ly), ov),
               "-map", "[v]", "-map", "0:a:0?",
               "-c:v", "libx264", "-preset", PRESET, "-crf", CRF, "-profile:v", "high",
               "-pix_fmt", "yuv420p",
               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-fps_mode", "passthrough", "-shortest"]
        if p.audio in COPY_AUDIO:
            cmd += ["-c:a", "copy"]
        elif p.audio:
            cmd += ["-c:a", "aac", "-b:a", "256k"]
        cmd += ["-movflags", "+faststart", str(dst)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in proc.stdout:
            if progress and line.startswith("out_time_us=") and p.duration:
                try:
                    progress(min(1.0, int(line.split("=")[1]) / 1e6 / p.duration))
                except ValueError:
                    pass
        err = proc.stderr.read()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg fchel: {err.strip()[-400:]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return p


def thumbnail(video: Path, dst: Path, at: float = 1.0) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=320:-2", "-q:v", "4", str(dst)], check=True)
    return dst


if __name__ == "__main__":  # tajriba: python montage.py in.mp4 out.mp4 "titre" [rkn]
    import sys
    a = sys.argv[1:]
    montage(Path(a[0]), Path(a[1]), a[2], a[3] if len(a) > 3 else None,
            progress=lambda x: print(f"\r{x:.0%}", end="", flush=True))
    print()
