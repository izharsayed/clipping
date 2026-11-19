"""Dynamic graphic overlays for the 7 gaming niches using Pillow:
titles, pills, attempt counters, verdict stamps, countdown boards, and pop-up cards.
"""
from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
FONTS_DIR = BASE_DIR / "backend" / "fonts"
if not FONTS_DIR.exists():
    FONTS_DIR = Path("/app/fonts")

HEAVY_FONTS = [
    str(FONTS_DIR / "THEBOLDFONT.ttf"),
    str(FONTS_DIR / "Anton-Regular.ttf"),
    str(FONTS_DIR / "BebasNeue-Regular.ttf"),
    str(FONTS_DIR / "TikTokSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/ariblk.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Black.ttf",
]

REGULAR_FONTS = [
    str(FONTS_DIR / "TikTokSans-Bold.ttf"),
    str(FONTS_DIR / "Inter.ttf"),
    str(FONTS_DIR / "Roboto.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]

YELLOW = (255, 214, 10, 255)
WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
RED = (230, 32, 42, 255)
GREEN = (24, 196, 92, 255)
INK = (14, 14, 14, 255)

_font_cache: dict = {}


def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    candidates = HEAVY_FONTS if bold else REGULAR_FONTS
    for p in candidates:
        if Path(p).exists():
            try:
                _font_cache[key] = ImageFont.truetype(p, size)
                return _font_cache[key]
            except Exception:
                continue
    try:
        _font_cache[key] = ImageFont.load_default(size)
    except TypeError:
        _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        try:
            length = f.getlength(t)
        except AttributeError:
            length = len(t) * 14
        if length <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_lines(text: str, size: int, max_w: int, max_lines: int, min_size: int = 36, bold: bool = True):
    while True:
        f = get_font(size, bold)
        lines = _wrap(text, f, max_w)
        if len(lines) <= max_lines or size <= min_size:
            return f, lines, size
        size -= 4


def _shadowed(img: Image.Image, radius: int = 12, alpha: int = 140, dy: int = 8) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    a = img.split()[3]
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sh.putalpha(a.point(lambda v: v * alpha // 255))
    sh = sh.filter(ImageFilter.GaussianBlur(radius))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (0, min(dy, img.size[1] - 1)))
    out.alpha_composite(img)
    return out


def _canvas(w: int, h: int) -> Image.Image:
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def place(src: Image.Image, canvas_size: Tuple[int, int], x: int, y: int) -> Image.Image:
    c = _canvas(*canvas_size)
    c.alpha_composite(src, (x, y))
    return c


def outline_text(text: str, size: int, max_w: int, fill=YELLOW, stroke_w: int = 8, stroke_fill=BLACK, bold: bool = True) -> Image.Image:
    f, lines, _ = _fit_lines(text, size, max_w - 40, max_lines=3, bold=bold)
    line_h = int(size * 1.15)
    w = max(int(f.getlength(ln)) for ln in lines) + stroke_w * 2 + 20
    h = line_h * len(lines) + stroke_w * 2 + 10
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        lx = (w - int(f.getlength(ln))) // 2
        ly = stroke_w + i * line_h
        d.text((lx, ly), ln, font=f, fill=fill, stroke_width=stroke_w, stroke_fill=stroke_fill)
    return _shadowed(img, radius=10, alpha=150, dy=6)


def title_card(text: str, max_w: int = 960, size: int = 64, max_lines: int = 3, bg=(14, 14, 18, 235), fg=WHITE) -> Image.Image:
    """Glossy high-contrast opening title card."""
    f, lines, sz = _fit_lines(text.upper(), size, max_w - 60, max_lines, min_size=38, bold=True)
    line_h = int(sz * 1.18)
    tw = max(int(f.getlength(ln)) for ln in lines)
    cw = max(400, tw + 56)
    ch = line_h * len(lines) + 40
    card = _canvas(cw, ch)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, cw, ch), radius=28, fill=bg, outline=(255, 255, 255, 45), width=2)
    for i, ln in enumerate(lines):
        lx = (cw - int(f.getlength(ln))) // 2
        ly = 20 + i * line_h
        d.text((lx, ly), ln, font=f, fill=fg, stroke_width=2, stroke_fill=(0, 0, 0, 180))
    return _shadowed(card, radius=16, alpha=160, dy=10)


def pill(label: str, sub: Optional[str] = None, bg=(16, 16, 20, 225), fg=WHITE, size: int = 60) -> Image.Image:
    """Sleek label pill for split-screen comparisons, replay markers, etc."""
    f = get_font(size, bold=True)
    sub_f = get_font(int(size * 0.55), bold=False) if sub else None
    lw = int(f.getlength(label))
    sw = int(sub_f.getlength(sub)) if sub and sub_f else 0
    w = max(lw, sw) + 48
    h = int(size * 1.5) if not sub else int(size * 2.0)
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w, h), radius=h // 2, fill=bg, outline=(255, 255, 255, 40), width=2)
    if sub and sub_f:
        d.text(((w - lw) // 2, int(size * 0.2)), label, font=f, fill=fg)
        d.text(((w - sw) // 2, int(size * 1.25)), sub, font=sub_f, fill=(200, 200, 210, 230))
    else:
        d.text(((w - lw) // 2, (h - int(size * 1.1)) // 2), label, font=f, fill=fg)
    return _shadowed(img, radius=12, alpha=140, dy=6)


def attempt_tag(number: int, landed: bool = False, size: int = 76) -> Image.Image:
    """Stunt attempt badge with animated color accent."""
    text = f"ATTEMPT #{number}"
    f = get_font(size, bold=True)
    tw = int(f.getlength(text))
    w, h = tw + 60, int(size * 1.55)
    img = _canvas(w, h)
    d = ImageDraw.Draw(img)
    bg = (24, 180, 80, 240) if landed else (20, 20, 24, 230)
    outline = (100, 255, 150, 180) if landed else (255, 255, 255, 45)
    fg = WHITE
    d.rounded_rectangle((0, 0, w, h), radius=22, fill=bg, outline=outline, width=3)
    d.text(((w - tw) // 2, (h - int(size * 1.15)) // 2), text, font=f, fill=fg, stroke_width=3, stroke_fill=BLACK)
    return _shadowed(img, radius=16, alpha=170, dy=8)


def stamp(verdict: str, color: Tuple[int, int, int, int] = RED, size: int = 140) -> Image.Image:
    """Heavy rubber/badge stamp (BUSTED / CONFIRMED / PATCHED) with thick borders."""
    text = verdict.upper()
    f = get_font(size, bold=True)
    tw = int(f.getlength(text))
    bw, bh = tw + 80, int(size * 1.45)
    stamp_img = _canvas(bw, bh)
    d = ImageDraw.Draw(stamp_img)
    # Double outline
    d.rounded_rectangle((0, 0, bw, bh), radius=20, outline=color, width=9)
    d.rounded_rectangle((12, 12, bw - 12, bh - 12), radius=14, outline=color, width=3)
    d.text(((bw - tw) // 2, (bh - int(size * 1.1)) // 2), text, font=f, fill=color, stroke_width=4, stroke_fill=(0, 0, 0, 180))
    # Slight dynamic rotation (-4.5 degrees) for realistic stamp look
    rotated = stamp_img.rotate(-4.5, resample=Image.Resampling.BICUBIC, expand=True)
    return _shadowed(rotated, radius=18, alpha=180, dy=12)


def rank_board(labels: dict[int, str], shown: Set[int], active_rank: Optional[int], total: int = 5, title: Optional[str] = None) -> Image.Image:
    """Animated 5-to-1 countdown listicle leaderboard overlay."""
    W, H = 1080, 1920
    img = _canvas(W, H)
    d = ImageDraw.Draw(img)

    # Header title
    if title:
        tcard = title_card(title, max_w=980, size=52, max_lines=2)
        img.alpha_composite(tcard, ((W - tcard.width) // 2, 80))

    board_w = 980
    row_h = 104
    start_y = 1260
    for r in range(total, 0, -1):
        y = start_y + (total - r) * (row_h + 14)
        is_active = (r == active_rank)
        is_shown = (r in shown)

        bg = (255, 214, 10, 240) if is_active else (22, 22, 28, 220) if is_shown else (14, 14, 18, 160)
        fg = INK if is_active else WHITE if is_shown else (130, 130, 140, 200)
        outline = (255, 255, 255, 80) if is_active else (255, 255, 255, 25)

        row_card = _canvas(board_w, row_h)
        rd = ImageDraw.Draw(row_card)
        rd.rounded_rectangle((0, 0, board_w, row_h), radius=20, fill=bg, outline=outline, width=2)

        # Rank badge
        rf = get_font(52, bold=True)
        r_text = f"#{r}"
        rd.text((32, (row_h - 52) // 2), r_text, font=rf, fill=fg)

        # Label text
        txt = labels.get(r, f"Choice {r}") if is_shown else "???"
        tf, lines, _ = _fit_lines(txt.upper(), 44, board_w - 200, max_lines=1, bold=True)
        rd.text((150, (row_h - 44) // 2), lines[0] if lines else txt, font=tf, fill=fg)

        sh_row = _shadowed(row_card, radius=12, alpha=140, dy=6)
        img.alpha_composite(sh_row, ((W - board_w) // 2, y))

    return img


def picture_card(image_path: Path, max_w: int = 940, max_h: int = 640, caption: Optional[str] = None) -> Image.Image:
    """Pop-up picture card for Commentary videos."""
    if not image_path.exists():
        return _canvas(max_w, max_h)
    try:
        raw = Image.open(str(image_path)).convert("RGBA")
    except Exception:
        return _canvas(max_w, max_h)

    # Scale to fit max_w x max_h preserving aspect ratio
    raw.thumbnail((max_w - 32, max_h - (90 if caption else 32)), Image.Resampling.LANCZOS)
    cw = raw.width + 32
    ch = raw.height + (90 if caption else 32)
    card = _canvas(cw, ch)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, cw, ch), radius=24, fill=(16, 16, 20, 240), outline=(255, 255, 255, 50), width=3)
    card.alpha_composite(raw, (16, 16))

    if caption:
        cf, lines, _ = _fit_lines(caption, 36, cw - 32, max_lines=1, bold=True)
        cl = lines[0] if lines else caption
        cx = (cw - int(cf.getlength(cl))) // 2
        d.text((cx, ch - 54), cl, font=cf, fill=WHITE)

    return _shadowed(card, radius=18, alpha=160, dy=10)


def pop_frames(img: Image.Image, canvas_size: Tuple[int, int], scales: Optional[List[float]] = None) -> List[Image.Image]:
    """Spring physics scale frames (e.g. 0.8 -> 0.96 -> 1.04 -> 1.0) so overlays visually 'pop'."""
    scales = scales or [0.75, 0.94, 1.05, 1.0]
    cw, ch = canvas_size
    frames = []
    for s in scales:
        nw = max(2, int(round(img.width * s / 2) * 2))
        nh = max(2, int(round(img.height * s / 2) * 2))
        res = img.resize((nw, nh), Image.Resampling.BILINEAR)
        c = _canvas(cw, ch)
        c.alpha_composite(res, ((cw - nw) // 2, (ch - nh) // 2))
        frames.append(c)
    return frames
