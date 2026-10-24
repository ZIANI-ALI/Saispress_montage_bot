"""Montage d video Saispress: format 9:16, logo, w titre f panel navy b animation.

Video 3rida (16:9, 4:3, mrabba3a): frame 9:16 (frame_layout) b7al l reels d l akhbar: l video kamla f l wost
(bla crop), fond = nefs l video mdbbla, l fo9 logo + #rkn, lta7t titre kbir (flèches dahbiyin l imin).
L titre f l frame kaydkhel b animation (flèches, mn ba3d stoura kaytkchfo men l imin) w kayb9a 7tta l akhir.
Video 9:16: l bot kaydir jouj versions: zoom + panel (frame=False) w frame (frame=True). F frame d 9:16 l video
3amra l cadre (full): header l fo9 w titre l t7t, b dégradé navy bach ybanou.
«Ghir logo» (with_title=False): nefs l montage bla titre. Cover (cover_image): frame JPEG mn l video l mkmmla.
F عاجل: block 7mer ta7t l video b label «عاجل».

L animation (b7al l exemple d l brand):
  dkhla: l khatt gold kaykber, l pill d l rkn w l panel kayban b fade, mn ba3d l titre kaytkchef men l imin l l issar.
  khrja: l titre kaytkhba men l issar l l imin, mn ba3d l panel w l pill w l khatt.
L logo kaybqa l video kamla.

Qualité: f l a9al 1080x1920 (nefs l résolution ila l video 9:16 kbira), x264 CRF 17 preset slow, l son kaytnsakh kif howa.
Videowat HDR (iPhone) kaytbddlo l SDR b tone-mapping bach l alwan ma ybhtouch.
"""
import itertools
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
RED = (204, 20, 38)  # عاجل
PANEL_ALPHA = 240
FONT_TITLE = "Tajawal-ExtraBold.ttf"
FONT_PILL = "Tajawal-Bold.ttf"
PAD_T, PAD_B, LINE_H = 19, 26, 1.12
MIN_W = 1080  # 3ard l output f l a9al

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


ORPHAN_SHRINK = 0.75  # ster lakher fih klma wa7da: kanssghro l ktaba (7tta had nisba) bach yn9as ster


def _balance(text: str, fnt, maxw: float, n: int) -> list[str] | None:
    """n stoura mtwazniin (b7al b7al f t-tol, bla faraghat kbar), w bla ster fih klma wa7da ila mmkin."""
    words = text.split()
    if n <= 1 or len(words) <= n:
        return None
    width: dict[tuple[int, int], float] = {}

    def w(a: int, b: int) -> float:
        if (a, b) not in width:
            width[a, b] = _width(" ".join(words[a:b]), fnt)
        return width[a, b]
    best, best_key = None, None
    for cuts in itertools.combinations(range(1, len(words)), n - 1):
        bounds = (0, *cuts, len(words))
        ws = [w(bounds[i], bounds[i + 1]) for i in range(n)]
        if max(ws) > maxw:
            continue
        lone = sum(bounds[i + 1] - bounds[i] == 1 for i in range(n))
        key = (lone, max(ws) - min(ws), max(ws))
        if best_key is None or key < best_key:
            best, best_key = bounds, key
    return [" ".join(words[best[i]:best[i + 1]]) for i in range(n)] if best else None


def _fit_title(text: str, name: str, maxw: float, steps) -> tuple:
    """steps = [(max_lines, hi, lo), ...]: akbar taille li kaydkhel fiha titre. Ila ster lakher fih ghir klma
    wa7da, kanssghro (7tta ORPHAN_SHRINK) bach ykhrej b ster a9al. Mn ba3d stoura mtwazniin (_balance)."""
    sizes = [(size, max_lines) for max_lines, hi, lo in steps for size in range(hi, lo - 1, -1)]
    pick = None
    for size, max_lines in sizes:
        lines = _wrap(text, _font(name, size), maxw)
        if len(lines) <= max_lines:
            pick = (size, lines)
            break
    if pick is None:
        size = sizes[-1][0]
        return _font(name, size), _wrap(text, _font(name, size), maxw)
    size, lines = pick
    n = len(lines)
    if n > 1 and len(lines[-1].split()) == 1:
        for smaller in sorted({sz for sz, _ in sizes if size * ORPHAN_SHRINK <= sz < size}, reverse=True):
            if len(_wrap(text, _font(name, smaller), maxw)) < n:
                size, n = smaller, n - 1
                break
    fnt = _font(name, size)
    return fnt, _balance(text, fnt, maxw, n) or _wrap(text, fnt, maxw)


def _fit(text: str, maxw: float, s: float):
    """3 stoura f l a9sa b taille kbira; ila ma dkhelch kanssghro, w f l akhir 4 stoura."""
    return _fit_title(text, FONT_TITLE, maxw, [(3, round(50 * s), round(36 * s)), (4, round(36 * s), round(30 * s))])


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


PANEL_SCALE = 0.88  # panel w ktaba sghar mn l exemple


def build_overlay(W: int, H: int, title: str, category: str | None, duration: float) -> Overlay:
    """Panel mcentri, 3ardo 3la 9ad l ktaba (bla blasa khawya), b 3ard l exemple f l a9sa."""
    s = W / 720  # l exemple 720x1280, kolchi kaytkber b nisba
    k = s * PANEL_SCALE
    pad_r, pad_l = round(17 * k), round(16 * k)
    pad_t, pad_b = round(PAD_T * k), round(PAD_B * k)
    fnt, lines = _fit(title, round(613 * k) - pad_r - pad_l, k)
    pw = pad_r + pad_l + math.ceil(max(_width(ln, fnt) for ln in lines))
    if category:  # l pill ma tkhrejch 3la l panel
        pw = max(pw, math.ceil(_width(category, _font(FONT_PILL, round(22 * k)))) + 2 * round(15 * k)
                 + round(8 * s))
    bar_w = round(8 * s)
    px0 = (W - pw - bar_w) // 2                        # panel + khatt gold mcentrin
    px1 = px0 + pw
    asc, desc = fnt.getmetrics()
    lh = round(fnt.size * LINE_H)
    ptop_abs = round(768 * s)
    ph = pad_t + lh * (len(lines) - 1) + asc + desc + pad_b
    bar_x0, bar_x1 = px1 + round(1 * s), px1 + round(8 * s)

    pill_h = round(28 * k)
    pill_gap = round(1 * s)
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
    ImageDraw.Draw(bar).rectangle((ox(bar_x0), pt + round(32 * k), ox(bar_x1) - 1, oh - round(38 * k)),
                                  fill=(*GOLD, 255))

    pill = layer()
    if category:
        pf = _font(FONT_PILL, round(22 * k))
        right = ox(px1 - round(8 * s))
        tw = _width(category, pf)
        left = right - tw - 2 * round(15 * k)
        d = ImageDraw.Draw(pill)
        d.rounded_rectangle((left, 0, right, pill_h), radius=pill_h // 2, fill=(*GOLD, 255))
        d.text((right - round(15 * k), pill_h / 2 + round(1 * s)), category, font=pf, fill=NAVY,
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


def _row_mask(size, spans) -> Image.Image:
    """Mask men saff wa7d: spans = [(left, right, 9owwa 0..1)], kayjm3o (max 1)."""
    w, h = size
    row = Image.new("L", (w, 1), 0)
    px = row.load()
    for x in range(w):
        v = sum(k for l, r, k in spans if l <= x < r)
        px[x, 0] = int(255 * min(1.0, v))
    return row.resize((w, h))


# Panel f 3 tbaqat (b7al l exemple): sbagha khfifa 3la l 3ard kaml, men ba3d tba9a
# katmsa7 men l issar l l imin, men ba3d tba9a lkhra m3a l ktaba.
LAYERS = (0.37, 0.27, 0.36)


def render_frame(ov: Overlay, t: float) -> Image.Image:
    L = ov.layers
    ow, oh = L["panel"].size
    out = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
    to = ov.t_out
    bbox = L["panel"].getbbox()
    px0, px1 = (bbox[0], bbox[2]) if bbox else (0, ow)
    pw = px1 - px0
    out_on = t >= to

    # dkhla (30 fps): pill w khatt f3-8, sbagha f3-5, tba9a 2 f5-8, ktaba f8-13
    pill_k = _prog(t, 0.07, 0.20)
    bar_k = _prog(t, 0.08, 0.25)
    base_k = _prog(t, 0.10, 0.17)
    w1_in, w2_in = _prog(t, 0.15, 0.27), _prog(t, 0.25, 0.43)
    # khrja: nefs l 7araka b l39s, kolchi kaymsa7 men l issar l l imin
    w2_out = _prog(t, to, to + 0.13) if out_on else 0.0
    w1_out = _prog(t, to + 0.07, to + 0.20) if out_on else 0.0
    if out_on:
        base_k *= 1 - _prog(t, to + 0.15, to + 0.23)
        bar_k *= 1 - _prog(t, to + 0.05, to + 0.20)
        pill_k *= 1 - _prog(t, to + 0.15, to + 0.27)

    e1 = (px0 + pw * w1_out, px0 + pw * w1_in)
    e2 = (px0 + pw * w2_out, px0 + pw * w2_in)
    panel_m = _row_mask((ow, oh), [(px0, px1, LAYERS[0] * base_k), (*e1, LAYERS[1]), (*e2, LAYERS[2])])
    pan = L["panel"].copy()
    pan.putalpha(ImageChops.multiply(pan.getchannel("A").point(lambda v: 255 if v else 0), panel_m))
    out.alpha_composite(pan)

    if bar_k > 0:
        bar = L["bar"]
        bb = bar.getbbox()
        if bb:
            cy = (bb[1] + bb[3]) / 2
            half = (bb[3] - bb[1]) / 2 * bar_k
            m = Image.new("L", bar.size, 0)
            ImageDraw.Draw(m).rectangle((0, round(cy - half), ow, round(cy + half)), fill=255)
            out.alpha_composite(Image.composite(bar, Image.new("RGBA", bar.size), m))
    if pill_k > 0:
        out.alpha_composite(_alpha(L["pill"], pill_k))
    # ktaba: katban m3a tba9a 3 (nefs l 7afa 9ad9a), katmsa7 m3aha f l khrja
    if e2[1] > e2[0]:
        m = _row_mask((ow, oh), [(*e2, 1.0)])
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


# ───────────────────────── frame 9:16 l videos 3rida ─────────────────────────

FW, FH = 1080, 1920
VID_TOP = 560          # l video f l wost (fo9ha header, ta7tha titre)
VID_MAX_H = 760        # video 4:3 / mrabba3a: ma tklach l blasa d titre
TEXT_R, TEXT_L = 940, 70   # nass bin had jouj (l imin: icons d Reels)
TEXT_MAX_Y = 1640      # ta7t: caption w boutons d Instagram


def framed(p: Probe) -> bool:
    """Video 3rida wla mrabba3a: frame (bla crop). 9:16 / 4:5: zoom kif 9bel."""
    return p.width / p.height >= 0.9


def fill_choice(p: Probe) -> bool:
    """4:5, 3:4, 2:3...: machi 9:16 w machi 3rida → l user kaykhtar crop (full) wla cadre (fond mdbbel)."""
    return not framed(p) and p.width / p.height - 9 / 16 > 0.03


def urgent_cat(category: str | None) -> bool:
    return bool(category) and category.strip().strip("!") == "عاجل"


def video_box(p: Probe) -> tuple[int, int, int, int]:
    """(x, y, w, h) d l video f l frame."""
    w, h = FW, _even(FW * p.height / p.width)
    if h > VID_MAX_H:
        w, h = _even(VID_MAX_H * p.width / p.height), VID_MAX_H
    return (FW - w) // 2, VID_TOP, w, h


def _chevrons(d: ImageDraw.ImageDraw, x: int, cy: int, size: int, fill) -> None:
    """«‹‹» l imin d titre (bla glyph f l font)."""
    for k in (0, 1):
        x0 = x - k * size * 0.62
        d.line([(x0, cy - size / 2), (x0 - size / 2, cy), (x0, cy + size / 2)], fill=fill, width=9, joint="curve")


@dataclass
class FrameLayers:
    """Frame f tba9at (l animation): base (tint + header) tabta, w l3anasir d titre (kolha f 1080x1920)."""
    base: Image.Image
    block: Image.Image | None       # عاجل: block 7mer (bla label)
    label: Image.Image | None       # عاجل: label «عاجل»
    chev: Image.Image | None        # flèches dahbiyin
    lines: list                     # [(Image d satr + khatt dahbi, (left, right))]
    top: int                        # awal y fih chi 3onsor d titre (l crop d l animation)


def _layer() -> Image.Image:
    return Image.new("RGBA", (FW, FH), (0, 0, 0, 0))


def _gradient(y0: int, y1: int, a0: int, a1: int) -> Image.Image:
    """Tba9a navy men y0 l y1, alpha men a0 l a1 (b tadrij)."""
    lay = _layer()
    col = Image.new("L", (1, max(1, y1 - y0)))
    n = max(1, y1 - y0 - 1)
    col.putdata([round(a0 + (a1 - a0) * (i / n) ** 1.2) for i in range(y1 - y0)])
    lay.paste(Image.new("RGBA", (FW, y1 - y0), (*NAVY, 255)), (0, y0), col.resize((FW, y1 - y0)))
    return lay


FULL_BOTTOM = TEXT_MAX_Y  # full: akhir satr d titre (fo9 caption d Instagram)


def frame_layers(box: tuple[int, int, int, int], title: str | None, category: str | None,
                 full: bool = False) -> FrameLayers:
    """full: video 9:16 3amra l cadre (bla fond mdbbel); header w titre fo9ha b dégradé navy."""
    vx, vy, vw, vh = box
    urgent = urgent_cat(category)
    if full:
        im = _gradient(0, 560, 170, 0)
    else:
        im = Image.new("RGBA", (FW, FH), (*NAVY, 140))
        ImageDraw.Draw(im).rectangle((vx, vy, vx + vw - 1, vy + vh - 1), fill=(0, 0, 0, 0))  # l video bla tint
    d = ImageDraw.Draw(im)

    # header: logo l imin, #rkn l issar (ta7t interface d Reels ~230px)
    lg = Image.open(ASSETS / "logo.png").convert("RGBA")
    lw = 150  # nefs 7ajm d l logo f version zoom (logo_image: 100 * 1080/720)
    lg = lg.resize((lw, round(lg.height * lw / lg.width)), Image.LANCZOS)
    im.alpha_composite(lg, (FW - 60 - lw, 291 - lg.height // 2))  # f nefs l khatt m3a #rkn
    tag_f = _font(FONT_PILL, 40)
    tag = f"{category}" if category else "Saispress"
    tw = _width(tag, tag_f)
    ph = 66
    sq = ph - 12
    x0, y0 = 60, 258
    x1 = x0 + 24 + tw + 18 + sq + 6
    d.rounded_rectangle((x0, y0, x1, y0 + ph), radius=14, fill=(*NAVY, 235), outline=(*GOLD, 255), width=3)
    d.rounded_rectangle((x1 - 6 - sq, y0 + 6, x1 - 6, y0 + 6 + sq), radius=10, fill=(*(RED if urgent else GOLD), 255))
    d.text((x1 - 6 - sq / 2, y0 + ph / 2 + 2), "#", font=_font(FONT_TITLE, 44), fill=WHITE, anchor="mm")
    d.text((x1 - 6 - sq - 18, y0 + ph / 2 + 3), tag, font=tag_f, fill=WHITE, anchor="rm", direction="rtl")
    top = vy + vh
    fl = FrameLayers(im, None, None, None, [], top)
    if not title:
        return fl
    if urgent:  # b7al l akhbar 3ajila: block 7mer ta7t l video, label «عاجل», titre byed
        fnt, lines = _fit_title(title, FONT_TITLE, TEXT_R - TEXT_L, ((3, 70, 58), (4, 58, 46)))
        lh = round(fnt.size * 1.32)
        if full:  # block l t7t (fo9 caption d Instagram)
            bottom = FH - 200
            top = bottom - max(96 + lh * len(lines) + 70, 380)
        y_text = top + 96
        if not full:
            bottom = min(FH - 200, max(y_text + lh * len(lines) + 70, top + 380))
        fl.block = _layer()
        ImageDraw.Draw(fl.block).rectangle((0, top, FW, bottom), fill=(*RED, 255))
        fl.label = _layer()
        d = ImageDraw.Draw(fl.label)
        lf = _font(FONT_TITLE, 66)
        lab_w = _width("عاجل", lf) + 64
        d.rectangle((TEXT_R - lab_w, top - 52, TEXT_R, top + 40), fill=(*WHITE, 255))
        d.rectangle((TEXT_R - lab_w + 7, top - 45, TEXT_R - 7, top + 33), outline=(*RED, 255), width=4)
        d.text((TEXT_R - lab_w / 2, top - 6), "عاجل", font=lf, fill=RED, anchor="mm", direction="rtl")
        fl.top = top - 52
        for i, ln in enumerate(lines):
            lay = _layer()
            ImageDraw.Draw(lay).text((TEXT_R, y_text + i * lh), ln, font=fnt, fill=WHITE, anchor="ra",
                                     direction="rtl")
            fl.lines.append((lay, (TEXT_R - _width(ln, fnt) - 4, TEXT_R + 4)))
        return fl

    right = TEXT_R - 70  # l imin: flèches dahbiyin 9bel titre
    y = top + 64
    room = TEXT_MAX_Y - y if not full else 560
    for steps in (((2, 84, 70), (3, 74, 60)), ((3, 60, 50), (4, 52, 44))):
        fnt, lines = _fit_title(title, FONT_TITLE, right - TEXT_L, steps)
        lh = round(fnt.size * 1.42)
        if lh * len(lines) <= room:
            break
    asc, desc = fnt.getmetrics()
    if full:  # titre l t7t, w dégradé navy ta7to bach yban 3la ay video
        y = FULL_BOTTOM - lh * len(lines)
        fl.base.alpha_composite(_gradient(y - 300, FH, 0, 215))
        fl.top = y - 20
    fl.chev = _layer()
    _chevrons(ImageDraw.Draw(fl.chev), TEXT_R, round(y + asc * 0.6), round(fnt.size * 0.5), (*GOLD, 255))
    for i, ln in enumerate(lines):
        lay = _layer()
        d = ImageDraw.Draw(lay)
        ty = y + i * lh
        d.text((right, ty), ln, font=fnt, fill=WHITE, anchor="ra", direction="rtl")
        uy = ty + asc + desc + 4  # khatt dahbi ta7t kol satr (b7al l exemple)
        left = right - _width(ln, fnt)
        d.rectangle((left, uy, right, uy + 5), fill=(*GOLD, 255))
        d.ellipse((right - 4, uy - 4, right + 10, uy + 9), fill=(*GOLD, 255))
        fl.lines.append((lay, (left - 4, right + 12)))
    return fl


def frame_overlay(box: tuple[int, int, int, int], title: str | None, category: str | None,
                  full: bool = False) -> Image.Image:
    """Overlay 1080x1920 (RGBA) l l video kamla: tint navy 3la l fond, header, titre (wla block عاجل).
    title None: ghir logo w #rkn."""
    fl = frame_layers(box, title, category, full)
    im = fl.base.copy()
    for lay in (fl.block, fl.label, fl.chev, *(ln for ln, _ in fl.lines)):
        if lay is not None:
            im.alpha_composite(lay)
    return im


# Animation d titre f l frame (dkhla bo7dha: l titre kayb9a 7tta l akhir, 7it ma kaygttich l video)
FRAME_ANIM_START = 0.15   # block / flèches
FRAME_LINE_DELAY = 0.30   # satr lowel
FRAME_LINE_STEP = 0.16    # bin stoura
FRAME_LINE_DUR = 0.42     # satr kaytkchef (men l imin l l issar) f had l modda


def frame_anim_end(fl: FrameLayers) -> float:
    n = len(fl.lines)
    return FRAME_LINE_DELAY + max(0, n - 1) * FRAME_LINE_STEP + FRAME_LINE_DUR if n else 0.0


def _wipe(lay: Image.Image, span: tuple[float, float], k: float) -> Image.Image:
    """Kaytkchef men l imin l l issar (RTL): k=0 walou, k=1 kamel."""
    left, right = span
    edge = right - (right - left) * k
    m = _row_mask(lay.size, [(max(0, int(edge)), FW, 1.0)])
    out = lay.copy()
    out.putalpha(ImageChops.multiply(lay.getchannel("A"), m))
    return out


def _shift(lay: Image.Image, dx: int) -> Image.Image:
    """Kaydfe3 l tba9a l imin b dx (dx >= 0)."""
    out = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    out.paste(lay.crop((0, 0, FW - dx, FH)), (dx, 0))
    return out


def render_frame_title(fl: FrameLayers, t: float) -> Image.Image:
    """Tba9at d titre f l w9t t (bla base), kolha f 1080x1920."""
    out = _layer()
    a = FRAME_ANIM_START
    if fl.block is not None:  # عاجل: block 7mer kaytkchef men l imin, label kayban mn ba3d
        k = _prog(t, a, a + 0.30)
        if k > 0:
            out.alpha_composite(_wipe(fl.block, (0, FW), k))
        k = _prog(t, a + 0.20, a + 0.38)
        if k > 0:
            out.alpha_composite(_alpha(_shift(fl.label, round(40 * (1 - k))), k))
    if fl.chev is not None:  # flèches: fade + jaya men l imin
        k = _prog(t, a, a + 0.30)
        if k > 0:
            out.alpha_composite(_alpha(_shift(fl.chev, round(50 * (1 - k))), k))
    for i, (lay, span) in enumerate(fl.lines):
        s0 = FRAME_LINE_DELAY + i * FRAME_LINE_STEP
        k = _prog(t, s0, s0 + FRAME_LINE_DUR)
        if k > 0:
            out.alpha_composite(_wipe(lay, span, k))
    return out


def render_frame_title_frames(fl: FrameLayers, fps: float, folder: Path) -> int:
    """PNG d l animation (crop men fl.top 7tta l t7t); l frame lakhra katb9a (eof_action=repeat)."""
    n = math.ceil(frame_anim_end(fl) * fps) + 1
    for i in range(n):
        render_frame_title(fl, i / fps).crop((0, fl.top, FW, FH)).save(folder / f"t{i:05d}.png", compress_level=1)
    return n


def build_filter_framed(p: Probe, box: tuple[int, int, int, int], anim_y: int | None = None) -> str:
    """anim_y: l animation d titre (input 2, PNG) f had l y; None: frame tabta (input 1) bo7dha."""
    vx, vy, vw, vh = box
    chain = []
    if p.hdr and tonemap_available():
        chain.append("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                     "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
    chain.append("format=yuv420p")
    pre = ",".join(chain)
    if (vw, vh) == (FW, FH):  # full: l video 3amra l cadre (crop f l wst ila machi 9:16 bdbt)
        g = (f"[0:v]{pre},scale={FW}:{FH}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={FW}:{FH},setsar=1[base];")
        return g + (f"[base][1:v]overlay=0:0[fr];[fr][2:v]overlay=0:{anim_y}:eof_action=repeat,format=yuv420p[v]"
                    if anim_y is not None else "[base][1:v]overlay=0:0,format=yuv420p[v]")
    # fond: nefs l video sghira, mdbbla, mkebbra (asra3 mn blur 3la 1080x1920)
    return (f"[0:v]{pre},split[a][b];"
            f"[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=12:3,"
            f"scale={FW}:{FH}:flags=bicubic,setsar=1[bg];"
            f"[b]scale={vw}:{vh}:flags=lanczos,setsar=1[fg];"
            f"[bg][fg]overlay={vx}:{vy}[base];"
            + (f"[base][1:v]overlay=0:0[fr];[fr][2:v]overlay=0:{anim_y}:eof_action=repeat,format=yuv420p[v]"
               if anim_y is not None else "[base][1:v]overlay=0:0,format=yuv420p[v]"))


# ───────────────────────── ffmpeg ─────────────────────────

def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def out_size(p: Probe, frame: bool | None = None) -> tuple[int, int, bool]:
    """(W, H, deja_9_16). F l a9al 1080x1920: l titre w l logo kaytrsmo b qualité kamla
    w Instagram ma ykbbrhomch (kayfer9ou). Ila l video deja 9:16 w kbira, kanbqaw 3la résolution dyalha.
    frame None: 3la 7sab l format (framed)."""
    if framed(p) if frame is None else frame:
        return FW, FH, False
    native = abs(p.width / p.height - 9 / 16) < 0.02
    if native and p.width >= MIN_W:
        return _even(p.width), _even(p.height), True
    return MIN_W, MIN_W * 16 // 9, native


def tonemap_available() -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return " zscale " in out and " tonemap " in out


def build_filter(p: Probe, W: int, H: int, native: bool, logo_xy, ov: Overlay | None) -> str:
    chain = []
    if p.hdr and tonemap_available():
        chain.append("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                     "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
    chain.append("format=yuv420p")
    pre = ",".join(chain)
    if native:
        g = f"[0:v]{pre},scale={W}:{H}:flags=lanczos,setsar=1[base];"
    else:
        # zoom in 7tta l video t3mer l cadre kaml (crop f l wst), bla fond flou
        g = (f"[0:v]{pre},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={W}:{H},setsar=1[base];")
    lx, ly = logo_xy
    if not ov:  # ghir logo
        return g + f"[base][1:v]overlay={lx}:{ly},format=yuv420p[v]"
    g += (f"[base][1:v]overlay={lx}:{ly}[lg];"
          f"[lg][2:v]overlay={ov.x}:{ov.y}:eof_action=pass,format=yuv420p[v]")
    return g


def montage(src: Path, dst: Path, title: str, category: str | None = None,
            progress: Callable[[float], None] | None = None, with_title: bool = True,
            frame: bool | None = None, fill: bool = True) -> Probe:
    """with_title=False: ghir logo (w #rkn f frame). frame None: 3la 7sab l format (framed); True: frame 7tta
    l 9:16 (titre b animation); False: zoom 9:16 (panel). fill (frame d video machi 3rida): True = crop 7tta
    t3mer l cadre, False = f l wost b fond mdbbel (b7al 16:9)."""
    p = probe(src)
    frame = framed(p) if frame is None else frame
    W, H, native = out_size(p, frame)
    title = clean_title(title) if with_title else ""
    if with_title and not title:
        raise ValueError("titre khawi")
    category = clean_title(category) if category else None
    work = Path(tempfile.mkdtemp(prefix="ov_"))
    try:
        if frame:
            full = not framed(p) and fill  # 9:16 / 4:5 (crop): l video 3amra l cadre
            box = (0, 0, FW, FH) if full else video_box(p)
            fl = frame_layers(box, title or None, category, full)
            fl.base.save(work / "frame.png")
            inputs = ["-i", str(work / "frame.png")]  # tswira wa7da l video kamla
            if fl.lines:  # titre b animation (dkhla), l frame lakhra katb9a
                render_frame_title_frames(fl, p.fps, work)
                inputs += ["-framerate", f"{p.fps:.5f}", "-i", str(work / "t%05d.png")]
            graph = build_filter_framed(p, box, fl.top if fl.lines else None)
        else:
            ov = build_overlay(W, H, title, category, p.duration) if title else None
            lg, lx, ly = logo_image(W)
            lg.save(work / "logo.png")
            inputs = ["-i", str(work / "logo.png")]  # tswira wa7da: overlay kay3awedha 7tta l akhir
            if ov:
                render_overlay_frames(ov, p.fps, work)
                inputs += ["-framerate", f"{p.fps:.5f}", "-i", str(work / "f%05d.png")]
            graph = build_filter(p, W, H, native, (lx, ly), ov)
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
               "-i", str(src), *inputs,
               "-filter_complex", graph,
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


def cover_time(p: Probe, with_title: bool, frame: bool | None = None) -> float:
    """W9t d l cover f l video l mkmmla: frame (titre kayb9a mor l animation) f l wost (max 2 s); 9:16 b titre:
    mlli l panel kaykoun kaml (0.43 s → TITLE_SECONDS)."""
    if not p.duration:
        return 0.0
    if with_title and not (framed(p) if frame is None else frame):
        return min(1.5, max(0.5, min(TITLE_SECONDS, p.duration - 0.6) - 0.2), p.duration / 2)
    # frame: mor l animation d titre (~1.2 s)
    return max(0.0, min(2.0, max(p.duration / 2, 1.3), p.duration - 0.1))


def cover_image(video: Path, dst: Path, at: float) -> Path:
    """Cover JPEG b résolution kamla (l Reels: «Edit cover» → mn l galerie)."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
                    "-q:v", "2", str(dst)], check=True)
    return dst


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
