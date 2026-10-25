"""Vertical TikTok videos (1080x1920) from the bot's real data, in the @MemeSmartMoney style.

Needs Pillow and ffmpeg (installed by the GitHub workflow). If either is missing, render_* returns None
and the bot simply skips the video.
"""
import datetime as dt
import glob
import logging
import os
import shutil
import subprocess

from . import fmt

log = logging.getLogger("msm")

W, H, FPS = 1080, 1920, 30
INK = (234, 237, 255)          # #EAEDFF
ACCENT = (142, 155, 255)       # #8E9BFF
ACCENT2 = (169, 180, 255)      # #A9B4FF
GAIN = (94, 230, 160)
LOSS = (255, 107, 134)         # #FF6B86
MUTED = (234, 237, 255, 128)
PILL = (81, 106, 246, 60)

FONT_DIRS = [os.environ.get("MSM_FONT_DIR", ""), ".tools/fonts", "/usr/share/fonts/opentype/inter",
             "/usr/share/fonts/truetype/inter"]


def ffmpeg_bin():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg  # bundled static ffmpeg (pip install imageio-ffmpeg)
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def available():
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return bool(ffmpeg_bin()) and bool(_font_path("Bold"))


def _font_path(weight):
    for d in FONT_DIRS:
        if not d:
            continue
        for ext in ("ttf", "otf"):
            hits = glob.glob(os.path.join(d, f"Inter-{weight}.{ext}"))
            if hits:
                return hits[0]
    return None


_fonts = {}


def font(weight, size):
    from PIL import ImageFont
    key = (weight, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(_font_path(weight) or _font_path("Bold"), size)
    return _fonts[key]


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


# ---------- drawing helpers ----------
def background():
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGB", (W, H), (6, 5, 16))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((W * 0.5 - 760, -620, W * 0.5 + 760, 520), fill=(28, 36, 92))
    glow = glow.filter(ImageFilter.GaussianBlur(170))
    base = Image.new("RGB", (W, H), (0, 0, 0))
    d2 = ImageDraw.Draw(base)
    d2.ellipse((-300, 300, W + 300, H + 300), fill=(12, 11, 22))
    base = base.filter(ImageFilter.GaussianBlur(260))
    img = Image.blend(img, base, 0.9)
    img = Image.composite(glow, img, glow.convert("L").point(lambda v: min(255, v * 4)))
    noise = Image.effect_noise((W, H), 9).convert("RGB")
    return Image.blend(img, noise, 0.035)


def text_img(parts, size, weight="Bold", line_gap=1.12, align="left", max_w=None):
    """parts: list of lines; each line is a list of (text, color) runs. Returns an RGBA image."""
    from PIL import Image, ImageDraw
    f = font(weight, size)
    asc, desc = f.getmetrics()
    lh = int(size * line_gap)
    widths = [sum(f.getlength(t) for t, _ in line) for line in parts]
    w = int(max(widths) + 4)
    h = int(lh * (len(parts) - 1) + asc + desc + 4)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(parts):
        x = (w - widths[i]) / 2 if align == "center" else 0
        for t, col in line:
            d.text((x, i * lh), t, font=f, fill=col if len(col) == 4 else col + (255,))
            x += f.getlength(t)
    return img


def fit_size(text, weight, size, max_w):
    while size > 30 and font(weight, size).getlength(text) > max_w:
        size -= 2
    return size


def pill(label, size=38):
    from PIL import Image, ImageDraw
    f = font("SemiBold", size)
    tw = f.getlength(label)
    w, h = int(tw + 44), int(size * 1.7)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=PILL, outline=(142, 155, 255, 90), width=2)
    d.text(((w - tw) / 2, (h - size * 1.2) / 2), label, font=f, fill=ACCENT2 + (255,))
    return img


class El:
    """An element that fades and slides in at t_in and fades out at t_out."""

    def __init__(self, img, x, y, t_in, t_out=None, dy=46, dur=0.5):
        self.img, self.x, self.y, self.t_in, self.t_out, self.dy, self.dur = img, x, y, t_in, t_out, dy, dur
        self.alpha = img.getchannel("A")

    def state(self, t):
        a = ease((t - self.t_in) / self.dur)
        if self.t_out is not None:
            a *= 1 - ease((t - self.t_out) / 0.35)
        return round(a, 3), round((1 - ease((t - self.t_in) / self.dur)) * self.dy)

    def draw(self, frame, t):
        a, off = self.state(t)
        if a <= 0:
            return
        mask = self.alpha if a >= 1 else self.alpha.point(lambda v: int(v * a))
        frame.paste(self.img.convert("RGB"), (int(self.x), int(self.y + off)), mask)


def encode(elements, duration, out_path):
    """Render frames and pipe them to ffmpeg (H.264 + silent AAC track, TikTok-friendly)."""
    bg = background()
    cmd = [ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out_path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last_key, last_bytes = None, None
    for i in range(int(duration * FPS)):
        t = i / FPS
        key = tuple(e.state(t) for e in elements)
        if key != last_key:
            frame = bg.copy()
            for e in elements:
                e.draw(frame, t)
            last_key, last_bytes = key, frame.tobytes()
        p.stdin.write(last_bytes)
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return out_path


# ---------- scenes ----------
MARGIN = 84


def _header(label, t_out):
    img = text_img([[(label, MUTED)]], 34, "Medium")
    return El(img, (W - img.width) / 2, 250, 0.1, t_out, dy=0)


def _hook(line1, line2, t_out):
    s = min(fit_size(line1, "Bold", 104, W - 2 * MARGIN), fit_size(line2, "Bold", 104, W - 2 * MARGIN))
    img = text_img([[(line1, INK)], [(line2, ACCENT)]], s, align="center")
    return El(img, (W - img.width) / 2, H * 0.42 - img.height / 2, 0.25, t_out, dy=60, dur=0.6)


def _outro(t0, tagline):
    els = []
    big = text_img([[("Follow the ", INK), ("money.", ACCENT)]], 100, align="center")
    els.append(El(big, (W - big.width) / 2, H * 0.40, t0, dy=60, dur=0.6))
    sub = text_img([[(tagline, MUTED)]], fit_size(tagline, "Medium", 40, W - 2 * MARGIN - 40), "Medium", align="center")
    els.append(El(sub, (W - sub.width) / 2, H * 0.40 + big.height + 40, t0 + 0.35))
    sm = text_img([[("$SM", INK)]], 44)
    els.append(El(sm, MARGIN, 1430, t0 + 0.6, dy=0))
    nfa = text_img([[("Not financial advice.", MUTED)]], 30, "Medium")
    els.append(El(nfa, W - MARGIN - nfa.width, 1440, t0 + 0.6, dy=0))
    return els


def _list_scene(title, subtitle, rows, t0, t_out, step=0.75):
    """rows: [{'name', 'right', 'right_color', 'sub'}]"""
    els = []
    head = text_img([[(title, INK)]], fit_size(title, "Bold", 84, W - 2 * MARGIN))
    els.append(El(head, MARGIN, 350, t0, t_out))
    sub = text_img([[(subtitle, MUTED)]], fit_size(subtitle, "Medium", 36, W - 2 * MARGIN), "Medium")
    els.append(El(sub, MARGIN, 350 + head.height + 18, t0 + 0.15, t_out))
    y = 620
    row_h = 180 if len(rows) > 4 else 205
    for i, r in enumerate(rows):
        ti = t0 + 0.6 + i * step
        p = pill(f"{i + 1:02d}")
        els.append(El(p, MARGIN, y + 10, ti, t_out))
        right = text_img([[(r["right"], r.get("right_color", ACCENT))]], 46, "SemiBold")
        name_max = W - 2 * MARGIN - p.width - 30 - right.width - 30
        name = text_img([[(r["name"], INK)]], fit_size(r["name"], "Bold", 66, name_max))
        els.append(El(name, MARGIN + p.width + 30, y, ti + 0.05, t_out))
        els.append(El(right, W - MARGIN - right.width, y + 14, ti + 0.1, t_out))
        if r.get("sub"):
            s = text_img([[(r["sub"], MUTED)]], fit_size(r["sub"], "Medium", 32, W - 2 * MARGIN - p.width - 30),
                         "Medium")
            els.append(El(s, MARGIN + p.width + 30, y + 92, ti + 0.15, t_out))
        y += row_h
    return els, t0 + 0.6 + len(rows) * step


def _date_label(now_ts):
    d = dt.datetime.fromtimestamp(now_ts, dt.timezone.utc)
    return d.strftime("%b %-d")


# ---------- public ----------
def recap_rows(rows, tokens, n=5):
    out = []
    for r in rows[:n]:
        t = tokens.get(r["mint"]) or {}
        w = len(r["wallets"])
        sub = []
        if t.get("last_mcap"):
            sub.append(f"mcap {fmt.money(t['last_mcap'])}")
        if t.get("first_mcap") and t.get("last_mcap"):
            mult = t["last_mcap"] / t["first_mcap"]
            sub.append(f"spotted at {fmt.money(t['first_mcap'])}" + (f" ({mult:.1f}x)" if mult >= 1.2 else ""))
        out.append({"name": fmt.ticker(t, r["mint"]), "right": f"{w} trader{'s' if w > 1 else ''}",
                    "sub": " · ".join(sub)})
    return out


def render_recap(rows, tokens, out_path, now_ts, period="last 24h", label="daily"):
    items = recap_rows(rows, tokens)
    if len(items) < 3:
        return None
    hook_end = 2.8
    els = [_header(f"smart money · {label} · {_date_label(now_ts)}", None),
           _hook("What smart money", "bought today." if period == "last 24h" else "bought this week.", hook_end)]
    list_els, list_end = _list_scene(f"Top {len(items)} coins", f"most bought by top Fomo traders · {period}",
                                     items, hook_end + 0.3, None)
    t_out = list_end + 3.2
    for e in list_els:
        e.t_out = t_out
    els += list_els + _outro(t_out + 0.4, "daily smart-money data")
    return encode(els, t_out + 3.6, out_path)


def render_leaderboard(traders, out_path, now_ts, period=""):
    items = [{"name": t["label"][:22], "right": fmt.signed_money(t["pnl"]),
              "right_color": GAIN if t["pnl"] >= 0 else LOSS} for t in traders[:5]]
    if len(items) < 3:
        return None
    hook_end = 2.8
    els = [_header(f"smart money · weekly · {_date_label(now_ts)}", None),
           _hook("The top Fomo traders", "this week.", hook_end)]
    list_els, list_end = _list_scene(f"Top {len(items)} by PnL", f"Fomo traders · {period or 'by PnL'}",
                                     items, hook_end + 0.3, None, step=0.7)
    t_out = list_end + 3.2
    for e in list_els:
        e.t_out = t_out
    bot = fmt.receipts_bot()
    els += list_els + _outro(t_out + 0.4, f"skill or luck? check any trader: @{bot}" if bot
                             else "weekly leaderboard every Sunday")
    return encode(els, t_out + 3.6, out_path)


HASHTAGS = "#memecoin #memecoins #solana #crypto #smartmoney #cryptotrading"


def _receipts_line():
    bot = fmt.receipts_bot()
    return f"\nScore any Fomo trader before you copy them: @{bot} on Telegram." if bot else ""


def recap_caption(rows, tokens, period="last 24h"):
    names = [fmt.ticker(tokens.get(r["mint"]), r["mint"]) for r in rows[:3]]
    when = "today" if period == "last 24h" else "this week"
    return (f"What smart money bought {when}: {', '.join(names)} 👀\n"
            f"Data from the wallets of the top traders on Fomo. Follow for daily smart-money data."
            f"{_receipts_line()}\nNot financial advice.\n\n{HASHTAGS}")


def leaderboard_caption(traders, period=""):
    top = traders[0]
    return (f"This week's top Fomo trader: {top['label']} at {fmt.signed_money(top['pnl'])} PnL 🏆\n"
            f"Top 5 by PnL{' ' + period if period else ''}. Past results don't predict future ones."
            f"{_receipts_line()}\nNot financial advice.\n\n{HASHTAGS}")
