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

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, features

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


GREEDY_SHRINK = 0.9   # greedy: a9sa ma kanssghro bach ster lowel ykoun ltwil
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


def _fit_title(text: str, name: str, maxw: float, steps, greedy: bool = False) -> tuple:
    """steps = [(max_lines, hi, lo), ...]: akbar taille li kaydkhel fiha titre. Ila ster lakher fih ghir klma
    wa7da, kanssghro (7tta ORPHAN_SHRINK) bach ykhrej b ster a9al. Mn ba3d stoura mtwazniin (_balance).
    greedy: ster lowel 3amer 7tta l 3ard kaml, w lba9i l ster li moraha (wakha ykoun fih ghir klma)."""
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
    if greedy:  # ster lowel howa ltwil: ila la, kanssghro chwiya (7tta GREEDY_SHRINK) bach ywli twil
        n = len(lines)
        for sz in range(size, math.floor(size * GREEDY_SHRINK) - 1, -1):
            fnt = _font(name, sz)
            cand = _wrap(text, fnt, maxw)
            if len(cand) <= n and _width(cand[0], fnt) >= max(_width(ln, fnt) for ln in cand):
                return fnt, cand
        return _font(name, size), lines
    n = len(lines)
    if n > 1 and len(lines[-1].split()) == 1:
        for smaller in sorted({sz for sz, _ in sizes if size * ORPHAN_SHRINK <= sz < size}, reverse=True):
            if len(_wrap(text, _font(name, smaller), maxw)) < n:
                size, n = smaller, n - 1
                break
    fnt = _font(name, size)
    return fnt, _balance(text, fnt, maxw, n) or _wrap(text, fnt, maxw)


def _fit(text: str, maxw: float, s: float):
    """2 stoura ila dkhel b taille kbira chwiya, sinon 3 stoura; ila ma dkhelch kanssghro, w f l akhir 4 stoura.
    Greedy: ster lowel twil (l panel dima 3rid, machi mrabba3)."""
    return _fit_title(text, FONT_TITLE, maxw, [(2, round(50 * s), round(42 * s)), (3, round(50 * s), round(36 * s)),
                                               (4, round(36 * s), round(30 * s))], greedy=True)


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

    t_out = title_out(duration)
    return Overlay(x0, y0, {"panel": panel, "bar": bar, "pill": pill, "text": text},
                   (int(min(lefts)) - 2, right + 2), t_out + 0.40, t_out)


def title_out(duration: float) -> float:
    """Waqt fach l titre kaybda ykhrej (b animation)."""
    return max(1.5, min(TITLE_SECONDS, duration - 0.6)) if duration else TITLE_SECONDS


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


def _back(x: float) -> float:
    """Ease out back: kaytjawez chwiya w yrje3 (pop)."""
    x = min(1.0, max(0.0, x))
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


# Animation d l logo (~1.4 s): l 7rf kaytktb men l imin l l issar (wipe mayl b 7afa rtba w daw dahbi f l 7afa)
# m3a zoom kayrtta7 (1.12 → 1), mn ba3d PRESS: l mrab3at kaytl3o wa7d b wa7d (pop), w f l akhir lam3a r9i9a.
LOGO_PAD = 0.08              # blasa l zoom (scale > 1)
LOGO_WRITE = (0.08, 0.62)    # l 7rf kaytktb
LOGO_SETTLE = (0.08, 0.85)   # zoom 1.12 → 1 (ease out expo)
LOGO_BOX = (0.48, 0.06, 0.38)  # PRESS: bdya, bin mrab3a w mrab3a, modda
LOGO_GLINT = (0.98, 1.38)    # lam3a men l issar l l imin
LOGO_END = 1.40
LOGO_TILT = 0.35             # mayl d l 7afa (dx/dy)


def _ease_io(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def _ease_expo(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


_logo_cache: dict = {}


def _logo_parts(lg: Image.Image):
    """(l 7rf bla PRESS, [(mrab3a, (x, y))]): l mrab3at dahbiyin d PRESS kanl9awhom b l loun."""
    key = (lg.size, lg.tobytes()[:4096])
    if key in _logo_cache:
        return _logo_cache[key]
    w, h = lg.size
    px = lg.load()
    gold = lambda c: c[3] > 160 and c[0] - c[2] > 70 and c[1] > 90  # noqa: E731
    cols = [x for x in range(w) if any(gold(px[x, y]) for y in range(h // 2, h))]
    runs, start = [], None
    for x in range(w + 1):
        on = x in cols if x < w else False
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start >= 3:
                runs.append((start, x))
            start = None
    mark = lg.copy()
    boxes = []
    for x0, x1 in runs:
        ys = [y for y in range(h // 2, h) for x in range(x0, x1) if gold(px[x, y])]
        y0, y1 = min(ys), max(ys) + 1
        rect = (max(0, x0 - 1), max(0, y0 - 1), min(w, x1 + 1), min(h, y1 + 1))
        boxes.append((lg.crop(rect), rect[:2]))
        ImageDraw.Draw(mark).rectangle((rect[0], rect[1], rect[2] - 1, rect[3] - 1), fill=(0, 0, 0, 0))
    _logo_cache[key] = (mark, boxes)
    return mark, boxes


def _edge_mask(size, edge: float, feather: float, peak: bool = False) -> Image.Image:
    """Mask b 7afa mayla f x = edge (+ LOGO_TILT * y): 0 9bel, 255 mor (rtba f feather). peak: ghir l 7afa."""
    w, h = size
    f = max(2, round(feather))
    pad = w + h + f
    if peak:
        vals = [0] * pad + [round(255 * math.sin(math.pi * i / f)) for i in range(f)] + [0] * (pad + w)
    else:
        vals = [0] * pad + [round(255 * i / f) for i in range(f)] + [255] * (pad + w)
    ramp = Image.new("L", (len(vals), 1))
    ramp.putdata(vals)
    # input u = x - edge + LOGO_TILT * (y - h/2) + pad
    return ramp.transform((w, h), Image.AFFINE, (1, LOGO_TILT, pad - edge - LOGO_TILT * h / 2, 0, 0, 0),
                          resample=Image.BILINEAR)


def logo_at(lg: Image.Image, t: float) -> Image.Image:
    """Logo f l w9t t, f canvas fih LOGO_PAD men kol jiha (l centre tabet)."""
    w, h = lg.size
    pw, ph = round(w * LOGO_PAD), round(h * LOGO_PAD)
    out = Image.new("RGBA", (w + 2 * pw, h + 2 * ph), (0, 0, 0, 0))
    if t <= LOGO_WRITE[0]:
        return out
    mark, boxes = _logo_parts(lg)
    span = w + LOGO_TILT * h
    feather = w * 0.22

    # 1) l 7rf: kaytkchef men l imin l l issar (RTL), b daw dahbi f l 7afa
    k = _ease_io((t - LOGO_WRITE[0]) / (LOGO_WRITE[1] - LOGO_WRITE[0]))
    m = mark.copy()
    if k < 1:
        edge = w + LOGO_TILT * h / 2 - (span + feather) * k   # visible men l 7afa l l imin
        a = m.getchannel("A")
        m.putalpha(ImageChops.multiply(a, _edge_mask((w, h), edge - feather, feather)))
        glow = Image.new("RGBA", (w, h), (*GOLD, 0))
        g = ImageChops.multiply(a, _edge_mask((w, h), edge - feather * 0.6, feather * 0.9, peak=True))
        glow.putalpha(g.point(lambda v: int(v * 0.95 * math.sin(math.pi * min(1.0, k * 1.15)))))
        m.alpha_composite(glow)
    # 3) lam3a r9i9a (men l issar l l imin) 3la l 7rf
    kg = (t - LOGO_GLINT[0]) / (LOGO_GLINT[1] - LOGO_GLINT[0])
    if 0 < kg < 1:
        e = -w * 0.15 - LOGO_TILT * h / 2 + (span + w * 0.3) * _ease_io(kg)
        g = ImageChops.multiply(m.getchannel("A"), _edge_mask((w, h), e, w * 0.12, peak=True))
        glint = Image.new("RGBA", (w, h), (255, 236, 170, 0))
        glint.putalpha(g.point(lambda v: int(v * 0.75)))
        m.alpha_composite(glint)
    # zoom kayrtta7
    sc = 1.12 - 0.12 * _ease_expo((t - LOGO_SETTLE[0]) / (LOGO_SETTLE[1] - LOGO_SETTLE[0]))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    layer.alpha_composite(m)
    # 2) PRESS: kol mrab3a katl3 men l t7t b pop
    for i, (bx, (x, y)) in enumerate(boxes):
        b0 = LOGO_BOX[0] + i * LOGO_BOX[1]
        kb = (t - b0) / LOGO_BOX[2]
        if kb <= 0:
            continue
        e = _back(kb)
        bw_, bh_ = bx.size
        sy = max(0.05, e)
        nb = bx.resize((bw_, max(1, round(bh_ * sy))), Image.LANCZOS) if sy != 1 else bx
        dy = round(bh_ * 0.6 * (1 - _ease(kb)))
        layer.alpha_composite(_alpha(nb, min(1.0, kb * 2.5)), (x, y + bh_ - nb.height + dy))
    nw, nh = max(1, round(w * sc)), max(1, round(h * sc))
    if (nw, nh) != (w, h):
        layer = layer.resize((nw, nh), Image.LANCZOS)
    out.alpha_composite(layer, (pw + (w - nw) // 2, ph + (h - nh) // 2))
    return out


def render_logo_frames(lg: Image.Image, fps: float, folder: Path) -> int:
    """PNG d l logo (dkhla + lam3a); l frame lakhra katb9a (overlay kay3awedha)."""
    n = math.ceil(LOGO_END * fps) + 2
    for i in range(n):
        logo_at(lg, i / fps).save(folder / f"l{i:05d}.png", compress_level=1)
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
VID_MIN_TOP = 360      # video 3alya (4:3, mrabba3a): kat-tla3 7tta ta7t l header
VID_MAX_H = 1080       # 3ard kaml (lasqa m3a jnab) 7tta l mrabba3a; ktar: katdye9
TITLE_ROOM = 300       # blasa d titre ta7t l video
TITLE_GAP = 36         # bin l video w titre
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
    y = max(VID_MIN_TOP, min(VID_TOP, TEXT_MAX_Y - TITLE_ROOM - h))
    return (FW - w) // 2, y, w, h


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
    t_out: float | None = None      # full: waqt khrja d titre (None: kayb9a 7tta l akhir)
    logo: tuple | None = None       # (Image, (x, y)) d l logo f l header
    tag: tuple | None = None        # (box, sq, text, (x0, x1), (sq_x0, sq_y0, sq_x1, sq_y1)): #rkn


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


FULL_TOP = round(768 * FH / 1280)  # full: titre f nefs blasat l panel d version zoom (768/1280 d l exemple)


def frame_layers(box: tuple[int, int, int, int], title: str | None, category: str | None,
                 full: bool = False) -> FrameLayers:
    """full: video 9:16 3amra l cadre (bla fond mdbbel); header (b dégradé navy) w titre (bla shadow) fo9ha."""
    vx, vy, vw, vh = box
    urgent = urgent_cat(category)
    if full:  # dégradé navy ghir fo9 (header); titre b shadow sghir mora l ktaba (_soft_shadow)
        im = _gradient(0, 560, 170, 0)
    else:
        im = Image.new("RGBA", (FW, FH), (*NAVY, 140))
        ImageDraw.Draw(im).rectangle((vx, vy, vx + vw - 1, vy + vh - 1), fill=(0, 0, 0, 0))  # l video bla tint
    d = ImageDraw.Draw(im)

    # header: logo l imin, #rkn l issar (ta7t interface d Reels ~230px)
    lg = Image.open(ASSETS / "logo.png").convert("RGBA")
    lw = 150  # nefs 7ajm d l logo f version zoom (logo_image: 100 * 1080/720)
    lg = lg.resize((lw, round(lg.height * lw / lg.width)), Image.LANCZOS)
    logo = (lg, (FW - 60 - lw, 291 - lg.height // 2))  # f nefs l khatt m3a #rkn (b animation: render_header)
    tag_f = _font(FONT_PILL, 40)
    tag = f"{category}" if category else "Saispress"
    tw = _width(tag, tag_f)
    ph = 66
    sq = ph - 12
    x0, y0 = 60, 258
    x1 = x0 + 24 + tw + 18 + sq + 6
    box_l, sq_l, txt_l = _layer(), _layer(), _layer()
    ImageDraw.Draw(box_l).rounded_rectangle((x0, y0, x1, y0 + ph), radius=14, fill=(*NAVY, 235),
                                            outline=(*GOLD, 255), width=3)
    d = ImageDraw.Draw(sq_l)
    sqb = (round(x1 - 6 - sq), y0 + 6, round(x1 - 6), y0 + 6 + sq)
    d.rounded_rectangle(sqb, radius=10, fill=(*(RED if urgent else GOLD), 255))
    d.text((x1 - 6 - sq / 2, y0 + ph / 2 + 2), "#", font=_font(FONT_TITLE, 44), fill=WHITE, anchor="mm")
    ImageDraw.Draw(txt_l).text((x1 - 6 - sq - 18, y0 + ph / 2 + 3), tag, font=tag_f, fill=WHITE, anchor="rm",
                               direction="rtl")
    top = vy + vh
    fl = FrameLayers(im, None, None, None, [], top, logo=logo, tag=(box_l, sq_l, txt_l, (x0, x1), sqb))
    if not title:
        return fl
    if urgent:  # b7al l akhbar 3ajila: block 7mer ta7t l video, label «عاجل», titre byed
        fnt, lines = _fit_title(title, FONT_TITLE, TEXT_R - TEXT_L, ((3, 70, 58), (4, 58, 46)))
        lh = round(fnt.size * 1.32)
        if full:  # block l t7t (fo9 caption d Instagram)
            top = FULL_TOP
            bottom = top + max(96 + lh * len(lines) + 70, 380)
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
    y = top + TITLE_GAP
    room = TEXT_MAX_Y - (FULL_TOP if full else y)
    sizes = ((((2, 76, 66), (3, 66, 56)),) if full  # full: ster lowel twil, lba9i l ster tani
             else (((2, 84, 70), (3, 74, 60)), ((3, 60, 50), (4, 52, 44))))
    for steps in sizes:
        fnt, lines = _fit_title(title, FONT_TITLE, right - TEXT_L, steps, greedy=full)
        lh = round(fnt.size * 1.42)
        if lh * len(lines) <= room:
            break
    asc, desc = fnt.getmetrics()
    if full:  # titre l t7t (bla dégradé)
        y = FULL_TOP
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
        fl.lines.append((_soft_shadow(lay), (left - 4, right + 12)))
    return fl


def _soft_shadow(lay: Image.Image, blur: int = 5, dy: int = 3, k: float = 0.6) -> Image.Image:
    """Shadow sghir mora l ktaba bo7dha (machi dégradé): nefs l forma, mdbbla, ta7t b dy."""
    bb = lay.getbbox()
    if not bb:
        return lay
    m = 4 * blur
    x0, y0, x1, y1 = max(0, bb[0] - m), max(0, bb[1] - m), min(FW, bb[2] + m), min(FH - dy, bb[3] + m)
    a = lay.crop((x0, y0, x1, y1)).getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * k))
    sh = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    sh.putalpha(a)
    out = _layer()
    out.paste(sh, (x0, y0 + dy))
    out.alpha_composite(lay)
    return out


HDR_Y0, HDR_Y1 = 200, 400   # l header (logo + #rkn) f had l bande
HDR_END = max(LOGO_END, 0.85)


def render_header(fl: FrameLayers, t: float) -> Image.Image:
    """Logo (pop + lam3a) w #rkn: l cadre kaytfta7 men l issar, «#» kaybrez, l ktaba katkchef men l imin."""
    out = _layer()
    if fl.tag:
        box, sq, txt, (x0, x1), (sx0, sy0, sx1, sy1) = fl.tag
        k = _prog(t, 0.12, 0.42)
        if k > 0:
            m = Image.new("L", (FW, FH), 0)
            ImageDraw.Draw(m).rectangle((0, 0, round(x0 + (x1 - x0) * k), FH), fill=255)
            b = _alpha(box, min(1.0, k * 2)).copy()  # _alpha k>=1 kayrj3 nefs l image: ma nbddlouhach
            b.putalpha(ImageChops.multiply(b.getchannel("A"), m))
            out.alpha_composite(b)
        k = (t - 0.32) / 0.28
        if k > 0:
            sc = _back(k)
            w, h = sx1 - sx0, sy1 - sy0
            nw, nh = max(1, round(w * sc)), max(1, round(h * sc))
            piece = sq.crop((sx0, sy0, sx1, sy1)).resize((nw, nh), Image.LANCZOS)
            out.alpha_composite(_alpha(piece, min(1.0, k * 3)), (sx0 + (w - nw) // 2, sy0 + (h - nh) // 2))
        k = _prog(t, 0.45, 0.85)
        if k > 0:
            bb = txt.getbbox()
            if bb:
                out.alpha_composite(_wipe(txt, (bb[0], bb[2]), k))
    if fl.logo:
        lg, (lx, ly) = fl.logo
        out.alpha_composite(logo_at(lg, t), (lx - round(lg.width * LOGO_PAD), ly - round(lg.height * LOGO_PAD)))
    return out


def render_header_frames(fl: FrameLayers, fps: float, folder: Path) -> int:
    n = math.ceil(HDR_END * fps) + 2
    for i in range(n):
        render_header(fl, i / fps).crop((0, HDR_Y0, FW, HDR_Y1)).save(folder / f"h{i:05d}.png", compress_level=1)
    return n


def frame_overlay(box: tuple[int, int, int, int], title: str | None, category: str | None,
                  full: bool = False) -> Image.Image:
    """Overlay 1080x1920 (RGBA) l l video kamla: tint navy 3la l fond, header, titre (wla block عاجل).
    title None: ghir logo w #rkn."""
    fl = frame_layers(box, title, category, full)
    im = fl.base.copy()
    im.alpha_composite(render_header(fl, HDR_END))
    for lay in (fl.block, fl.label, fl.chev, *(ln for ln, _ in fl.lines)):
        if lay is not None:
            im.alpha_composite(lay)
    return im


# Animation d titre f l frame (dkhla bo7dha: l titre kayb9a 7tta l akhir, 7it ma kaygttich l video)
FRAME_ANIM_START = 0.15   # block / flèches
FRAME_LINE_DELAY = 0.30   # satr lowel
FRAME_LINE_STEP = 0.16    # bin stoura
FRAME_LINE_DUR = 0.42     # satr kaytkchef (men l imin l l issar) f had l modda


FRAME_OUT_STEP = 0.10     # khrja: bin stoura
FRAME_OUT_DUR = 0.35      # khrja: satr kaytmsa7 f had l modda
FRAME_BLOCK_OUT = 0.55    # khrja: block عاجل mor stoura


def frame_anim_end(fl: FrameLayers) -> float:
    n = len(fl.lines)
    if not n:
        return 0.0
    if fl.t_out is not None:
        return fl.t_out + max(0, n - 1) * FRAME_OUT_STEP + FRAME_OUT_DUR + FRAME_BLOCK_OUT
    return FRAME_LINE_DELAY + max(0, n - 1) * FRAME_LINE_STEP + FRAME_LINE_DUR


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


def _unwipe(lay: Image.Image, span: tuple[float, float], k: float) -> Image.Image:
    """Khrja: kaytmsa7 men l imin l l issar (b7al ma dkhel): k=0 kamel, k=1 walou."""
    left, right = span
    edge = right - (right - left) * k
    m = _row_mask(lay.size, [(0, max(0, int(edge)), 1.0)])
    out = lay.copy()
    out.putalpha(ImageChops.multiply(lay.getchannel("A"), m))
    return out


def render_frame_title(fl: FrameLayers, t: float) -> Image.Image:
    """Tba9at d titre f l w9t t (bla base), kolha f 1080x1920. fl.t_out: kolchi kaykhrej b animation."""
    out = _layer()
    a = FRAME_ANIM_START
    to = fl.t_out
    n = len(fl.lines)
    o_lines = to + max(0, n - 1) * FRAME_OUT_STEP + FRAME_OUT_DUR if to is not None else None
    # khrja (0 → 1): flèches / label m3a satr lowel, block mor stoura
    def gone(b0: float | None, d: float) -> float:  # khrja men b0 f d; titre bla khrja (to None): 0
        return _prog(t, b0, b0 + d) if b0 is not None else 0.0
    if fl.block is not None:  # عاجل: block 7mer kaytkchef men l imin, label kayban mn ba3d
        k = _prog(t, a, a + 0.30)
        ko = gone(o_lines, FRAME_BLOCK_OUT)
        if k > 0 and ko < 1:
            blk = _wipe(fl.block, (0, FW), k)
            out.alpha_composite(_unwipe(blk, (0, FW), ko) if ko > 0 else blk)
        k = _prog(t, a + 0.20, a + 0.38) * (1 - gone(to, 0.25))
        if k > 0:
            out.alpha_composite(_alpha(_shift(fl.label, round(40 * (1 - k))), k))
    if fl.chev is not None:  # flèches: fade + jaya men l imin
        k = _prog(t, a, a + 0.30) * (1 - gone(to, 0.25))
        if k > 0:
            out.alpha_composite(_alpha(_shift(fl.chev, round(50 * (1 - k))), k))
    for i, (lay, span) in enumerate(fl.lines):
        s0 = FRAME_LINE_DELAY + i * FRAME_LINE_STEP
        k = _prog(t, s0, s0 + FRAME_LINE_DUR)
        if k <= 0:
            continue
        lay = _wipe(lay, span, k)
        if to is not None:
            e0 = to + i * FRAME_OUT_STEP
            ko = _prog(t, e0, e0 + FRAME_OUT_DUR)
            if ko >= 1:
                continue
            if ko > 0:
                lay = _unwipe(lay, span, ko)
        out.alpha_composite(lay)
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


# ───────────────────────── source (platform + page / متداول) ─────────────────────────

PLATFORMS = ("X", "Instagram", "TikTok", "Facebook", "YouTube")
SRC_CY = 0.355              # wost d l ktaba (nisba men l 3lou), lasqa f jnab l issar
SRC_X = 0.05                # b3d men jnab (nisba men l 3ard); 9rib mn l 7af kayt9ta3 f Reels
SRC_START = 0.45            # dkhla
SRC_GROW, SRC_SWEEP = 0.25, 0.40     # dkhla: khatt dahbi kaykber men l wost, mn ba3d kaymsa7 w l ktaba katban
SRC_BACK, SRC_SHRINK = 0.35, 0.22    # khrja: b l39s
SRC_HOLD = float(os.environ.get("SOURCE_SECONDS", "1"))  # ch7al tb9a source kamla 9bel ma tkhrej


def clean_source(name: str) -> str:
    """Smiyt l page: bla emoji; kelma latin wa7da bla @ → @kelma."""
    t = re.sub(r"[^\w\s؀-ۿ@.\-]", "", name)
    t = re.sub(r"\s+", " ", t).strip()[:32]
    if t and " " not in t and not t.startswith("@") and re.fullmatch(r"[\w.\-]+", t, re.A):
        t = "@" + t
    return t


def _icon(platform: str, s: int, col) -> Image.Image:
    """Icon sghir d l platform (mrsoum, bla logos f l font)."""
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(2, round(s * 0.11))
    hole = (*NAVY, 255)
    if platform == "Instagram":
        d.rounded_rectangle((w / 2, w / 2, s - w / 2 - 1, s - w / 2 - 1), radius=s * 0.3, outline=col, width=w)
        r = s * 0.21
        d.ellipse((s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r), outline=col, width=w)
        d.ellipse((s * 0.69, s * 0.2, s * 0.69 + w * 1.1, s * 0.2 + w * 1.1), fill=col)
    elif platform == "YouTube":
        d.rounded_rectangle((0, s * 0.17, s - 1, s * 0.83), radius=s * 0.2, fill=col)
        d.polygon([(s * 0.41, s * 0.35), (s * 0.41, s * 0.65), (s * 0.68, s * 0.5)], fill=hole)
    elif platform == "Facebook":
        d.ellipse((0, 0, s - 1, s - 1), fill=col)
        d.text((s * 0.55, s * 0.58), "f", font=_font(FONT_TITLE, round(s * 0.9)), fill=hole, anchor="mm")
    elif platform == "TikTok":  # note d musi9a
        r = s * 0.2
        cx, cy = s * 0.36, s * 0.74
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=w)
        x = cx + r - w / 2
        d.line([(x, cy), (x, s * 0.06)], fill=col, width=w)
        d.line([(x, s * 0.08), (s * 0.9, s * 0.34)], fill=col, width=w)
    else:  # X
        d.line([(s * 0.12, s * 0.08), (s * 0.88, s * 0.92)], fill=col, width=round(w * 1.4))
        d.line([(s * 0.86, s * 0.08), (s * 0.14, s * 0.92)], fill=col, width=max(2, w // 2))
    return im


@dataclass
class SourceTab:
    content: Image.Image   # icon | smiya (ofo9i, b shadow), kaytdawr f l akhir
    bar: tuple             # (y0, y1) d l khatt dahbi (ofo9i)
    x0: int                # bdya d l ktaba (bla margin d shadow)
    length: int
    x: int
    y: int
    t_out: float


def source_tab(platform: str, name: str, W: int, H: int, duration: float) -> SourceTab:
    """[smiya | icon] dawr 90° (b7al Hespress): icon l fo9, ktaba kat9ra men l t7t l l fo9, byda b shadow."""
    s = W / 1080
    fnt = _font(FONT_PILL, round(34 * s))
    ic, gap, sep = round(30 * s), round(12 * s), max(2, round(3 * s))
    m = round(8 * s)                      # margin d shadow
    h = round(48 * s)
    rtl = bool(re.search(r"[؀-ۿ]", name))
    tw = math.ceil(fnt.getlength(name, direction="rtl" if rtl else "ltr"))
    L = (ic + gap if platform else 0) + sep + gap + tw  # bla platform (متداول): ghir l khatt dahbi
    cy = m + h / 2
    fg = Image.new("RGBA", (L + 2 * m, h + 2 * m), (0, 0, 0, 0))
    if platform:
        fg.alpha_composite(_icon(platform, ic, (*WHITE, 255)).rotate(-90), (m + L - ic, round(cy - ic / 2)))  # wa9ef
    d = ImageDraw.Draw(fg)
    sx = m + tw + gap
    d.rectangle((sx, round(cy - ic * 0.5), sx + sep - 1, round(cy + ic * 0.5)), fill=(*GOLD, 255))
    d.text((m, cy + round(2 * s)), name, font=fnt, fill=WHITE, anchor="lm", direction="rtl" if rtl else "ltr")
    sh = Image.new("RGBA", fg.size, (0, 0, 0, 0))
    sh.putalpha(fg.getchannel("A").filter(ImageFilter.GaussianBlur(round(4 * s))).point(lambda v: min(255, v * 2) * 0.55))
    content = Image.alpha_composite(sh, fg)
    bt = round(h * 0.62)
    out = SRC_START + SRC_GROW + SRC_SWEEP + SRC_HOLD
    if duration:
        out = max(1.2, min(out, duration - SRC_BACK - SRC_SHRINK - 0.1))
    return SourceTab(content, (round(cy - bt / 2), round(cy + bt / 2)), m, L,
                     round(W * SRC_X) - m, round(H * SRC_CY - (L + 2 * m) / 2), out)


def _source_frame(st: SourceTab, t: float) -> Image.Image:
    """(Ofo9i: l icon f l imin = l fo9 mor dawra.) Dkhla: khatt dahbi kaykber men l wost, mn ba3d kaymsa7 men
    l fo9 l l t7t w l ktaba katban mn ta7to.
    Khrja: l khatt kayrje3 ygtti l ktaba men l t7t l l fo9, w kaytsaghar l l wost."""
    w, hh = st.content.size
    a0, L = st.x0, st.length
    c = a0 + L / 2
    to = st.t_out
    if t < to:
        k1 = _prog(t, SRC_START, SRC_START + SRC_GROW)
        k2 = _prog(t, SRC_START + SRC_GROW, SRC_START + SRC_GROW + SRC_SWEEP)
    else:
        k2 = 1 - _prog(t, to, to + SRC_BACK)
        k1 = 1 - _prog(t, to + SRC_BACK, to + SRC_BACK + SRC_SHRINK)
    out = Image.new("RGBA", (w, hh), (0, 0, 0, 0))
    e = a0 + L * (1 - k2)                 # l ktaba katban mn e l l imin (l fo9)
    if k2 > 0:
        m = Image.new("L", (w, hh), 0)
        ImageDraw.Draw(m).rectangle((round(e), 0, w, hh), fill=255)
        c_img = st.content.copy()
        c_img.putalpha(ImageChops.multiply(c_img.getchannel("A"), m))
        out.alpha_composite(c_img)
    if k1 > 0 and k2 < 1:
        x0, x1 = (c - (c - a0) * k1, c + (a0 + L - c) * k1) if k2 <= 0 else (a0, e)
        y0, y1 = st.bar
        if x1 - x0 >= 1:
            ImageDraw.Draw(out).rounded_rectangle((x0, y0, x1, y1), radius=min((y1 - y0) / 2, (x1 - x0) / 2),
                                                  fill=(*GOLD, 255))
    return out.rotate(90, expand=True)    # ofo9i → 3amoudi (l icon l fo9)


def render_source_frames(st: SourceTab, fps: float, folder: Path) -> int:
    """PNG d source 7tta tsali l khrja; l frame lakhra khawya (eof_action=repeat)."""
    n = math.ceil((st.t_out + SRC_BACK + SRC_SHRINK) * fps) + 2
    for i in range(n):
        _source_frame(st, i / fps).save(folder / f"s{i:05d}.png", compress_level=1)
    return n


# ───────────────────────── outro (end card) ─────────────────────────
# B7al l pages l kbar d l akhbar (AJ+, Brut…): l video kat7bes f akhir frame w bandat mayliin (dahbi, navy)
# kaygttiwha men l imin; mn ba3d l logo b animation dyalo, khatt dahbi, «تابعونا لكل جديد», l site w icons d l réseaux.

OUTRO = os.environ.get("OUTRO", "1") != "0"
OUTRO_SECONDS = 2.8
OUTRO_TAG = "تابعونا لكل جديد"
OUTRO_SITE = os.environ.get("OUTRO_SITE", "saispress.com")
OUTRO_LOGO_T0 = 0.38          # l logo kaybda (b nefs animation d l header)
OUTRO_ANIM_END = 2.25         # akhir 7araka (icons); ba9i l outro tabet
NAVY_DEEP = (8, 16, 40)


@dataclass
class OutroLayers:
    W: int
    H: int
    bg: Image.Image          # navy b daw f l wost
    logo: Image.Image
    logo_xy: tuple
    line_y: int
    tag: Image.Image         # ktaba (layer kamel)
    tag_span: tuple
    site: Image.Image        # pill d l site (crop) + blasto
    site_xy: tuple
    icons: list              # [(Image, (x, y))]


def outro_layers(W: int, H: int) -> OutroLayers:
    s = W / 1080
    bg = Image.new("RGBA", (W, H), (*NAVY_DEEP, 255))
    glow = Image.new("L", (W // 8, H // 8), 0)
    gw, gh = glow.size
    ImageDraw.Draw(glow).ellipse((gw * 0.05, gh * 0.22, gw * 0.95, gh * 0.62), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(gw * 0.12)).resize((W, H), Image.BICUBIC)
    bg.paste(Image.new("RGBA", (W, H), (*NAVY, 255)), (0, 0), glow)

    lg = Image.open(ASSETS / "logo.png").convert("RGBA")
    lw = round(400 * s)
    lg = lg.resize((lw, round(lg.height * lw / lg.width)), Image.LANCZOS)
    cy = round(H * 0.40)
    logo_xy = ((W - lw) // 2, cy - lg.height // 2 - round(40 * s))
    line_y = logo_xy[1] + lg.height + round(50 * s)

    tf = _font(FONT_TITLE, round(62 * s))
    tag = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ty = line_y + round(42 * s)
    ImageDraw.Draw(tag).text((W / 2, ty), OUTRO_TAG, font=tf, fill=WHITE, anchor="ma", direction="rtl")
    tw = _width(OUTRO_TAG, tf)
    tag = _soft_shadow_any(tag)

    sf = _font(FONT_PILL, round(40 * s))
    sw = math.ceil(sf.getlength(OUTRO_SITE))
    ph, padx = round(76 * s), round(36 * s)
    site = Image.new("RGBA", (sw + 2 * padx, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(site)
    d.rounded_rectangle((0, 0, site.width - 1, ph - 1), radius=ph // 2, fill=(*NAVY, 255), outline=(*GOLD, 255),
                        width=max(2, round(3 * s)))
    d.text((site.width / 2, ph / 2 + round(2 * s)), OUTRO_SITE, font=sf, fill=WHITE, anchor="mm")
    site_xy = ((W - site.width) // 2, ty + round(110 * s))

    ic, gap = round(54 * s), round(34 * s)
    names = ("Instagram", "Facebook", "TikTok", "YouTube", "X")
    total = len(names) * ic + (len(names) - 1) * gap
    iy = site_xy[1] + ph + round(70 * s)
    icons = [(_icon(n, ic, (*GOLD, 255)), ((W - total) // 2 + i * (ic + gap), iy)) for i, n in enumerate(names)]
    return OutroLayers(W, H, bg, lg, logo_xy, line_y, tag, ((W - tw) / 2 - 4, (W + tw) / 2 + 4), site, site_xy,
                       icons)


def _soft_shadow_any(lay: Image.Image, blur: int = 6, dy: int = 3, k: float = 0.55) -> Image.Image:
    sh = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    sh.putalpha(lay.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * k)))
    out = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    out.paste(sh, (0, dy))
    out.alpha_composite(lay)
    return out


def render_outro(o: OutroLayers, t: float) -> Image.Image:
    W, H = o.W, o.H
    s = W / 1080
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # 1) bandat kaydkhlo men l imin (dahbi, navy, mn ba3d l fond) w kaygttiw l video
    sl = H * 0.18
    span = W + 2 * sl
    for i, col in enumerate(((*GOLD, 255), (*NAVY, 255), None)):
        k = _ease_io((t - i * 0.08) / 0.45)
        if k <= 0:
            continue
        edge = W + sl - span * k  # l 7afa l issar (f l wost d l 3lou)
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).polygon([(edge + sl, 0), (W * 3, 0), (W * 3, H), (edge - sl, H)], fill=255)
        lay = o.bg.copy() if col is None else Image.new("RGBA", (W, H), col)
        lay.putalpha(m)
        out.alpha_composite(lay)
    if t < 0.4:
        return out
    # 2) logo (nefs animation d l header, kbir)
    lx, ly = o.logo_xy
    out.alpha_composite(logo_at(o.logo, t - OUTRO_LOGO_T0),
                        (lx - round(o.logo.width * LOGO_PAD), ly - round(o.logo.height * LOGO_PAD)))
    # 3) khatt dahbi kaytfta7 men l wost
    k = _ease_expo((t - 1.05) / 0.5)
    if k > 0:
        half = round(210 * s * k)
        ImageDraw.Draw(out).rounded_rectangle((W // 2 - half, o.line_y, W // 2 + half, o.line_y + round(5 * s)),
                                              radius=round(3 * s), fill=(*GOLD, 255))
    # 4) «تابعونا لكل جديد»: katkchef men l imin + tl3a sghira
    k = _prog(t, 1.15, 1.6)
    if k > 0:
        tag = _wipe_any(o.tag, o.tag_span, k)
        out.alpha_composite(tag, (0, round(18 * s * (1 - k))))
    # 5) l site (pop)
    k = (t - 1.35) / 0.4
    if k > 0:
        sc = _back(k)
        sw, sh = o.site.size
        nw, nh = max(1, round(sw * sc)), max(1, round(sh * sc))
        out.alpha_composite(_alpha(o.site.resize((nw, nh), Image.LANCZOS), min(1.0, k * 3)),
                            (o.site_xy[0] + (sw - nw) // 2, o.site_xy[1] + (sh - nh) // 2))
    # 6) icons wa7d b wa7d
    for i, (im, (x, y)) in enumerate(o.icons):
        k = (t - 1.55 - i * 0.07) / 0.35
        if k <= 0:
            continue
        dy = round(30 * s * (1 - _ease(k)))
        out.alpha_composite(_alpha(im, min(1.0, k * 2.5)), (x, y + dy))
    return out


def _wipe_any(lay: Image.Image, span: tuple[float, float], k: float) -> Image.Image:
    left, right = span
    edge = right - (right - left) * k
    m = _row_mask(lay.size, [(max(0, int(edge)), lay.width, 1.0)])
    out = lay.copy()
    out.putalpha(ImageChops.multiply(lay.getchannel("A"), m))
    return out


def render_outro_frames(W: int, H: int, fps: float, folder: Path) -> int:
    o = outro_layers(W, H)
    n = math.ceil(OUTRO_ANIM_END * fps) + 1  # mor had l w9t kolchi tabet (eof_action=repeat)
    for i in range(n):
        render_outro(o, i / fps).save(folder / f"o{i:05d}.png", compress_level=1)
    return n


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


def _add_overlay(graph: str, inputs: list, pattern: Path, fps: float, x: int, y: int) -> str:
    """Kanzidou sequence PNG (input jdid) fo9 [v]; l frame lakhra katb9a."""
    n = 1 + inputs.count("-i")
    inputs += ["-framerate", f"{fps:.5f}", "-i", str(pattern)]
    return (graph.removesuffix("[v]") + f"[o{n}];[o{n}][{n}:v]overlay={x}:{y}:eof_action=repeat,"
            "format=yuv420p[v]")


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
            frame: bool | None = None, fill: bool = True, source: tuple[str, str] | None = None,
            outro: bool = OUTRO) -> Probe:
    """source: (platform, smiyt l page wla «متداول») → tab f jnab l issar. with_title=False: ghir logo (w #rkn f frame). frame None: 3la 7sab l format (framed); True: frame 7tta
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
            if full and fl.lines:  # titre fo9 l video: kaykhrej b animation b7al version zoom
                fl.t_out = title_out(p.duration)
            fl.base.save(work / "frame.png")
            inputs = ["-i", str(work / "frame.png")]  # tswira wa7da l video kamla
            if fl.lines:  # titre b animation (dkhla), l frame lakhra katb9a
                render_frame_title_frames(fl, p.fps, work)
                inputs += ["-framerate", f"{p.fps:.5f}", "-i", str(work / "t%05d.png")]
            graph = build_filter_framed(p, box, fl.top if fl.lines else None)
            render_header_frames(fl, p.fps, work)  # logo + #rkn b animation
            graph = _add_overlay(graph, inputs, work / "h%05d.png", p.fps, 0, HDR_Y0)
        else:
            ov = build_overlay(W, H, title, category, p.duration) if title else None
            lg, lx, ly = logo_image(W)
            render_logo_frames(lg, p.fps, work)  # logo b animation, l frame lakhra katb9a
            lx, ly = lx - round(lg.width * LOGO_PAD), ly - round(lg.height * LOGO_PAD)
            inputs = ["-framerate", f"{p.fps:.5f}", "-i", str(work / "l%05d.png")]
            if ov:
                render_overlay_frames(ov, p.fps, work)
                inputs += ["-framerate", f"{p.fps:.5f}", "-i", str(work / "f%05d.png")]
            graph = build_filter(p, W, H, native, (lx, ly), ov)
        name = clean_source(source[1]) if source else ""
        if name:  # tab d source fo9 kolchi
            st = source_tab(source[0], name, *((FW, FH) if frame else (W, H)), p.duration)
            render_source_frames(st, p.fps, work)
            graph = _add_overlay(graph, inputs, work / "s%05d.png", p.fps, st.x, st.y)
        amap = "0:a:0?"
        outro = outro and p.duration > 0
        if outro:  # l video kat7bes f akhir frame, l outro fo9ha; l son kaytfada w kaytzad silence
            ow, oh = (FW, FH) if frame else (W, H)
            render_outro_frames(ow, oh, p.fps, work)
            n = 1 + inputs.count("-i")
            inputs += ["-framerate", f"{p.fps:.5f}", "-itsoffset", f"{p.duration:.3f}", "-i", str(work / "o%05d.png")]
            graph = (graph.removesuffix("[v]") + f"[x];[x]tpad=stop_mode=clone:stop_duration={OUTRO_SECONDS}[xp];"
                     f"[xp][{n}:v]overlay=0:0:eof_action=repeat,format=yuv420p[v]")
            if p.audio:
                graph += (f";[0:a:0]afade=t=out:st={max(0.0, p.duration - 0.5):.3f}:d=0.5,"
                          f"atrim=end={p.duration:.3f},apad=whole_dur={p.duration + OUTRO_SECONDS:.3f}[a]")
                amap = "[a]"
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
               "-i", str(src), *inputs,
               "-filter_complex", graph,
               "-map", "[v]", "-map", amap,
               "-c:v", "libx264", "-preset", PRESET, "-crf", CRF, "-profile:v", "high",
               "-pix_fmt", "yuv420p",
               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-fps_mode", "passthrough", "-shortest"]
        if p.audio in COPY_AUDIO and not outro:
            cmd += ["-c:a", "copy"]
        elif p.audio:
            cmd += ["-c:a", "aac", "-b:a", "256k"]
        cmd += ["-movflags", "+faststart", str(dst)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for line in proc.stdout:
                if progress and line.startswith("out_time_us=") and p.duration:
                    try:
                        progress(min(1.0, int(line.split("=")[1]) / 1e6 / p.duration))
                    except ValueError:
                        pass
        except BaseException:  # progress kaytl9 exception (b7al /cancel): nwe99fo ffmpeg
            proc.kill()
            proc.wait()
            raise
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
