"""Vertical TikTok videos (1080x1920) from the bot's real data, in the $SM style, with a voice-over.

Look: black, Apple-like, Inter Display, the $SM logo. One scene per coin / trader,
each as long as its narration (about 45-60 s in total).

Needs Pillow and ffmpeg (installed by the GitHub workflow). The voice uses edge-tts (free neural voices);
if it is missing or fails, the video is still made, silent, with estimated timings.
"""
import asyncio
import datetime as dt
import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile

from . import fmt

log = logging.getLogger("msm")

W, H, FPS = 1080, 1920, 30
BG = (0, 0, 0)
TILE = (22, 22, 23)            # #161617
TILE2 = (35, 35, 37)           # #232325
TEXT = (245, 245, 247)         # #F5F5F7
TEXT2 = (161, 161, 166)        # #A1A1A6
GAIN = (50, 215, 75)           # #32D74B
LOSS = (255, 69, 58)           # #FF453A
MARGIN = 84
VOICE = os.environ.get("MSM_VOICE", "en-US-AndrewNeural")
VOICE_RATE = os.environ.get("MSM_VOICE_RATE", "+6%")

FONT_DIRS = [os.environ.get("MSM_FONT_DIR", ""), ".tools/fonts", "/usr/share/fonts/opentype/inter",
             "/usr/share/fonts/truetype/inter"]
FALLBACK = {"InterDisplay-Bold": "Inter-Bold", "InterDisplay-SemiBold": "Inter-SemiBold",
            "Inter-SemiBold": "Inter-Bold", "Inter-Medium": "Inter-Bold"}


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
    return bool(ffmpeg_bin()) and bool(_font_path("Inter-Bold"))


def _font_path(name):
    while name:
        for d in FONT_DIRS:
            if not d:
                continue
            for ext in ("ttf", "otf"):
                hits = glob.glob(os.path.join(d, f"{name}.{ext}"))
                if hits:
                    return hits[0]
        name = FALLBACK.get(name)
    return None


_fonts = {}


def font(name, size):
    from PIL import ImageFont
    key = (name, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(_font_path(name), size)
    return _fonts[key]


DISPLAY, SEMI, MED = "InterDisplay-Bold", "Inter-SemiBold", "Inter-Medium"


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


# ---------- drawing ----------
def sm_logo(d):
    """The $SM logo: off-white '$SM' on a near-black rounded tile, with a hairline so it reads on black."""
    from PIL import Image, ImageDraw
    k = 3
    D = d * k
    img = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle((0, 0, D - 1, D - 1), radius=int(D * 0.22), fill=(17, 17, 17, 255),
                         outline=(255, 255, 255, 38), width=max(2, int(D * 0.012)))
    size = fit("$SM", DISPLAY, int(D * 0.6), D * 0.74, floor=8)
    f = font(DISPLAY, size)
    bbox = dr.textbbox((0, 0), "$SM", font=f)
    x = (D - (bbox[2] - bbox[0])) / 2 - bbox[0]
    y = (D - (bbox[3] - bbox[1])) / 2 - bbox[1]
    dr.text((x, y), "$SM", font=f, fill=(244, 245, 240, 255))
    return img.resize((d, d), Image.LANCZOS)


def background():
    """Black with a faint neutral glow at the top."""
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((W / 2 - 700, -900, W / 2 + 700, 380), fill=(30, 30, 33))
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    img = Image.blend(img, glow, 0.85)
    noise = Image.effect_noise((W, H), 8).convert("RGB")
    return Image.blend(img, noise, 0.02)


def text_img(lines, size, name=DISPLAY, line_gap=1.08, align="left"):
    """lines: list of lines; each line a list of (text, color) runs. Returns an RGBA image."""
    from PIL import Image, ImageDraw
    f = font(name, size)
    asc, desc = f.getmetrics()
    lh = int(size * line_gap)
    widths = [sum(f.getlength(t) for t, _ in line) for line in lines]
    w = int(max(widths) + 6)
    h = int(lh * (len(lines) - 1) + asc + desc + 4)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        x = (w - widths[i]) / 2 if align == "center" else 0
        for t, col in line:
            d.text((x, i * lh), t, font=f, fill=col + (255,))
            x += f.getlength(t)
    return img


def fit(text, name, size, max_w, floor=30):
    while size > floor and font(name, size).getlength(text) > max_w:
        size -= 2
    return size


def wrap(text, name, size, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        nxt = (cur + " " + w).strip()
        if cur and font(name, size).getlength(nxt) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    return lines + ([cur] if cur else [])


def tile(rows, width=W - 2 * MARGIN):
    """Rounded #161617 card with label/value rows separated by hairlines. rows: [(label, value, color)]."""
    from PIL import Image, ImageDraw
    pad, rh = 52, 132
    h = pad * 2 + rh * len(rows) - 28
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, width - 1, h - 1), radius=44, fill=TILE + (255,))
    fl, fv = font(MED, 38), None
    for i, (label, value, color) in enumerate(rows):
        y = pad + i * rh
        d.text((pad, y + 18), label, font=fl, fill=TEXT2 + (255,))
        size = fit(value, DISPLAY, 60, width - 2 * pad - fl.getlength(label) - 40)
        fv = font(DISPLAY, size)
        d.text((width - pad - fv.getlength(value), y + 8 + (60 - size) // 2), value, font=fv,
               fill=(color or TEXT) + (255,))
        if i < len(rows) - 1:
            d.line((pad, y + rh - 22, width - pad, y + rh - 22), fill=(255, 255, 255, 26), width=2)
    return img


def chips(names, max_w=W - 2 * MARGIN, size=40):
    """Trader names as rounded #232325 chips, wrapped on lines."""
    from PIL import Image, ImageDraw
    f = font(SEMI, size)
    ch, gap, px = int(size * 2.0), 18, 34
    pos, x, y = [], 0, 0
    for n in names:
        w = int(f.getlength(n) + 2 * px)
        if x and x + w > max_w:
            x, y = 0, y + ch + gap
        pos.append((n, x, y, w))
        x += w + gap
    img = Image.new("RGBA", (max_w, y + ch + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for n, x, y, w in pos:
        d.rounded_rectangle((x, y, x + w, y + ch), radius=ch // 2, fill=TILE2 + (255,))
        d.text((x + px, y + (ch - size * 1.2) / 2), n, font=f, fill=TEXT + (255,))
    return img


def brand():
    """Small '$SM  $SMART MONEY' mark used at the top of every frame."""
    from PIL import Image
    o = sm_logo(64)
    t = text_img([[("$SMART MONEY", TEXT)]], 36, DISPLAY)
    img = Image.new("RGBA", (o.width + 18 + t.width, max(o.height, t.height)), (0, 0, 0, 0))
    img.paste(o, (0, (img.height - o.height) // 2), o)
    img.paste(t, (o.width + 18, (img.height - t.height) // 2 + 2), t)
    return img


class El:
    """An element that fades/slides in at t_in and fades out at t_out."""

    def __init__(self, img, x, y, t_in, t_out=None, dy=40, dur=0.5):
        self.img, self.x, self.y, self.t_in, self.t_out, self.dy, self.dur = img, x, y, t_in, t_out, dy, dur
        self.alpha = img.getchannel("A")
        self.rgb = img.convert("RGB")

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
        frame.paste(self.rgb, (int(self.x), int(self.y + off)), mask)


def centered(img, y, t_in, t_out, dy=40, dur=0.5):
    return El(img, (W - img.width) / 2, y, t_in, t_out, dy, dur)


# ---------- voice ----------
def _duration(path):
    """Length of an audio file in seconds (from ffmpeg's header read)."""
    p = subprocess.run([ffmpeg_bin(), "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def speak(text, path):
    """Neural TTS with edge-tts. Returns the clip duration, or None (no voice: the video stays silent)."""
    if os.environ.get("MSM_VOICE", "x").lower() in ("", "off", "none"):
        return None
    try:
        import edge_tts
    except ImportError:
        return None
    import time
    err = None
    for attempt in range(4):  # the free TTS service sometimes drops a request: retry, then try the default speed
        try:
            kw = {"rate": VOICE_RATE} if attempt < 2 else {}
            asyncio.run(edge_tts.Communicate(text, VOICE, **kw).save(path))
            d = _duration(path)
            if d > 0.3:
                return d
            err = "empty audio"
        except Exception as e:
            err = str(e)[:160]
        time.sleep(1.5 * (attempt + 1))
    log.warning("voice failed for %r (scene stays silent): %s", text[:60], err)
    return None


def _estimate(text):
    return 0.4 + len(text.split()) / 2.7


def spoken_money(x):
    x = abs(float(x or 0))
    if x < 10000:  # "5800 dollars" reads better than "5.8 thousand dollars"
        return f"{x:.0f} dollars"
    for div, word in ((1e9, "billion"), (1e6, "million"), (1e3, "thousand")):
        if x >= div:
            v = x / div
            v = f"{v:.1f}".rstrip("0").rstrip(".") if v < 100 else f"{v:.0f}"
            return f"{v} {word} dollars"
    return f"{x:.0f} dollars"


def spoken_ticker(sym):
    s = sym.lstrip("$")
    return " ".join(s) if len(s) <= 3 else s.capitalize()


def spoken_name(name):
    n = re.sub(r"[^A-Za-z0-9 ._-]", "", name).replace("_", " ").strip()
    return n or "an anonymous trader"


def spoken_list(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


ORDINAL = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


# ---------- assembly ----------
def build(scenes, out_path, workdir):
    """scenes: [{'say': str, 'els': fn(t0, t_out) -> [El], 'min': seconds}]. Times each scene on its narration."""
    clips, t, els = [], 0.0, []
    head = brand()
    for i, sc in enumerate(scenes):
        clip = os.path.join(workdir, f"v{i}.mp3")
        d = speak(sc["say"], clip)
        dur = max(sc.get("min", 2.5), (d if d else _estimate(sc["say"])) + 0.7)
        if d:
            clips.append((clip, t + 0.25))
        last = i == len(scenes) - 1
        els += sc["els"](t, None if last else t + dur - 0.35)
        t += dur
    els.insert(0, centered(head, 150, 0.05, None, dy=0))
    total = t + 0.6
    audio = _mix_audio(clips, total, workdir) if clips else None
    return encode(els, total, out_path, audio)


def _mix_audio(clips, total, workdir):
    out = os.path.join(workdir, "voice.m4a")
    cmd = [ffmpeg_bin(), "-v", "error", "-y"]
    for c, _ in clips:
        cmd += ["-i", c]
    parts = [f"[{i}:a]aresample=44100,adelay={int(st * 1000)}:all=1[a{i}]" for i, (_, st) in enumerate(clips)]
    mix = "".join(f"[a{i}]" for i in range(len(clips)))
    flt = ";".join(parts) + f";{mix}amix=inputs={len(clips)}:normalize=0,apad,atrim=0:{total:.2f}[out]"
    cmd += ["-filter_complex", flt, "-map", "[out]", "-ac", "2", "-c:a", "aac", "-b:a", "128k", out]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return out
    except Exception as e:
        log.warning("audio mix failed (video will be silent): %s", str(e)[:200])
        return None


def encode(elements, duration, out_path, audio=None):
    """Render frames and pipe them to ffmpeg (H.264 + AAC, TikTok-friendly)."""
    bg = background()
    audio_in = ["-i", audio] if audio else ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd = [ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", *audio_in, "-map", "0:v", "-map", "1:a", "-t", f"{duration:.2f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out_path]
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
def _date_label(now_ts):
    return dt.datetime.fromtimestamp(now_ts, dt.timezone.utc).strftime("%b %-d")


def hook_scene(line1, line2, sub, say):
    def els(t0, t_out):
        s = min(fit(line1, DISPLAY, 128, W - 2 * MARGIN), fit(line2, DISPLAY, 128, W - 2 * MARGIN))
        big = text_img([[(line1, TEXT)], [(line2, TEXT2)]], s, align="center")
        o = sm_logo(220)
        y = H * 0.40 - big.height / 2
        subi = text_img([[(sub, TEXT2)]], fit(sub, MED, 40, W - 2 * MARGIN), MED, align="center")
        return [centered(o, y - 300, t0 + 0.05, t_out, dy=0, dur=0.7),
                centered(big, y, t0 + 0.2, t_out, dy=60, dur=0.6),
                centered(subi, y + big.height + 44, t0 + 0.5, t_out)]
    return {"say": say, "els": els, "min": 3.2}


def _stack_top(heights, gaps, center=H * 0.47, top=320):
    total = sum(heights) + sum(gaps)
    return max(top, int(center - total / 2))


def item_scene(rank, title, title_color, rows, names, names_label, say):
    """One coin / trader: rank, huge title, a data card and the trader chips (centred vertically)."""
    def els(t0, t_out):
        r = text_img([[(f"No. {rank}" if isinstance(rank, int) else str(rank), TEXT2)]], 44, SEMI)
        big = text_img([[(title, title_color)]], fit(title, DISPLAY, 150, W - 2 * MARGIN, floor=70))
        card = tile(rows) if rows else None
        lab = text_img([[(names_label, TEXT2)]], 36, MED) if names else None
        ch = chips(names) if names else None
        hs = [r.height, big.height] + ([card.height] if card else []) + ([lab.height, ch.height] if names else [])
        gs = [20] + ([70] if card else []) + ([60 if card else 70, 24] if names else [])
        y = _stack_top(hs, gs)
        out = [El(r, MARGIN, y, t0 + 0.05, t_out, dy=0)]
        y += r.height + 20
        out.append(El(big, MARGIN, y, t0 + 0.15, t_out, dy=50, dur=0.55))
        y += big.height + 70
        if card:
            out.append(El(card, MARGIN, y, t0 + 0.45, t_out, dy=50))
            y += card.height + 60
        if names:
            out.append(El(lab, MARGIN, y, t0 + 0.8, t_out, dy=0))
            out.append(El(ch, MARGIN, y + lab.height + 24, t0 + 0.95, t_out, dy=30))
        return out
    return {"say": say, "els": els, "min": 4.0}


def summary_scene(title, items, say):
    """items: [(name, right, right_color)] — the full ranking at once (centred vertically)."""
    def els(t0, t_out):
        head = text_img([[(title, TEXT)]], fit(title, DISPLAY, 92, W - 2 * MARGIN))
        y = _stack_top([head.height, 150 * len(items)], [70])
        out = [El(head, MARGIN, y, t0 + 0.05, t_out)]
        y += head.height + 70
        for i, (name, right, col) in enumerate(items):
            ti = t0 + 0.3 + i * 0.22
            n = text_img([[(f"{i + 1}", TEXT2)]], 52, SEMI)
            out.append(El(n, MARGIN, y + 8, ti, t_out, dy=24))
            rv = text_img([[(right, col or TEXT2)]], 46, SEMI)
            nm_max = W - 2 * MARGIN - 90 - rv.width - 30
            nm = text_img([[(name, TEXT)]], fit(name, DISPLAY, 68, nm_max))
            out.append(El(nm, MARGIN + 90, y, ti, t_out, dy=24))
            out.append(El(rv, W - MARGIN - rv.width, y + 12, ti, t_out, dy=24))
            y += 150
        return out
    return {"say": say, "els": els, "min": 3.5}


def outro_scene(line, sub, say):
    def els(t0, t_out):
        o = sm_logo(260)
        big = text_img([[(w, TEXT)] for w in wrap(line, DISPLAY, 96, W - 2 * MARGIN)], 96, align="center")
        y = H * 0.42
        out = [centered(o, y - 340, t0 + 0.05, t_out, dy=0, dur=0.7),
               centered(big, y, t0 + 0.2, t_out, dy=50, dur=0.6)]
        sy = y + big.height + 50
        for i, s in enumerate(sub):
            si = text_img([[(s, TEXT2)]], fit(s, MED, 40, W - 2 * MARGIN), MED, align="center")
            out.append(centered(si, sy, t0 + 0.5 + i * 0.2, t_out))
            sy += si.height + 22
        nfa = text_img([[("Not financial advice.", TEXT2)]], 30, MED, align="center")
        out.append(centered(nfa, 1480, t0 + 0.9, t_out, dy=0))
        return out
    return {"say": say, "els": els, "min": 4.0}


# ---------- public ----------
def _coin(r, tokens, labels):
    t = tokens.get(r["mint"]) or {}
    sym = fmt.ticker(t, r["mint"])
    w = len(r["wallets"])
    rows = [("Top traders", str(w), None)]
    mult = None
    if t.get("last_mcap"):
        rows.append(("Market cap", fmt.money(t["last_mcap"]), None))
    if t.get("first_mcap"):
        if t.get("last_mcap"):
            mult = t["last_mcap"] / t["first_mcap"]
        val = fmt.money(t["first_mcap"]) + (f"  ·  {mult:.1f}x" if mult and mult >= 1.2 else "")
        rows.append(("Spotted at", val, GAIN if mult and mult >= 1.2 else None))
    names = fmt.buyer_names(r, labels, 6)
    return sym, w, rows, names, t, mult


def render_recap(rows, tokens, out_path, now_ts, period="last 24h", label="daily", labels=None, n=5):
    rows = rows[:n]
    if len(rows) < 3:
        return None
    labels = labels or {}
    today = period == "last 24h"
    scenes = [hook_scene("What smart money", "bought today." if today else "bought this week.",
                         f"{_date_label(now_ts)}  ·  top Fomo traders  ·  {period}",
                         f"Here's what smart money bought {'today' if today else 'this week'}. "
                         f"These are the {len(rows)} coins the top traders on Fomo bought the most.")]
    summary = []
    for i, r in enumerate(rows, 1):
        sym, w, card, names, t, mult = _coin(r, tokens, labels)
        real = [x for x in names if not x.startswith("+")]
        say = f"Number {ORDINAL[i - 1]}: {spoken_ticker(sym)}. "
        say += (f"{w} top traders bought it" if w > 1 else "One top trader bought it")
        say += (f": {spoken_list(spoken_name(x) for x in real[:3])}" + (" and others. " if w > 3 else ". ")) if real else ". "
        if t.get("last_mcap"):
            say += f"Market cap is now {spoken_money(t['last_mcap'])}"
            say += (f", {mult:.1f} times what it was when we spotted it." if mult and mult >= 1.2 else ".")
        scenes.append(item_scene(i, sym, TEXT, card, names, "Bought by", say))
        summary.append((sym, f"{w} trader{'s' if w > 1 else ''}", None))
    scenes.append(summary_scene(f"Top {len(rows)} today" if today else f"Top {len(rows)} this week", summary,
                                f"So that's the list: {spoken_list(spoken_ticker(s) for s, _, _ in summary)}."))
    bot = fmt.receipts_bot()
    scenes.append(outro_scene("Follow the smart money.",
                              ["Daily data from the top Fomo traders"] + ([f"Check any trader: @{bot}"] if bot else []),
                              "Follow for smart money data every day. "
                              + ("And before you copy a trader, check their receipts with Receipts on Telegram. " if bot else "")
                              + "Not financial advice."))
    with tempfile.TemporaryDirectory() as wd:
        return build(scenes, out_path, wd)


def render_leaderboard(traders, out_path, now_ts, period="", n=5):
    traders = traders[:n]
    if len(traders) < 3:
        return None
    per = period or "this week"
    scenes = [hook_scene("The top Fomo traders", "this week.", f"{_date_label(now_ts)}  ·  ranked by PnL  ·  {per}",
                         f"These are the top {len(traders)} traders on Fomo this week, ranked by profit.")]
    summary = []
    bot = fmt.receipts_bot()
    for i, tr in enumerate(traders, 1):
        name = tr["label"][:24]
        pnl = tr.get("pnl") or 0
        col = GAIN if pnl >= 0 else LOSS
        card = [("PnL" + (f" ({period})" if period else ""), fmt.signed_money(pnl), col)]
        if tr.get("x"):
            card.append(("On X", "@" + str(tr["x"]).lstrip("@")[:20], None))
        say = (f"Number {ORDINAL[i - 1]}: {spoken_name(name)}, with "
               f"{spoken_money(pnl)} in {'profit' if pnl >= 0 else 'losses'}.")
        if i == 1 and bot:
            say += " Skill, or luck? Receipts tells you."
        scenes.append(item_scene(i, name, TEXT, card, [], "", say))
        summary.append((name, fmt.signed_money(pnl), col))
    scenes.append(summary_scene(f"Top {len(traders)} by PnL", summary,
                                f"That's this week's top {len(traders)}. Follow to see who makes the list next week."))
    scenes.append(outro_scene("Skill or luck?", ([f"Check any trader: @{bot}"] if bot else [])
                              + ["Weekly leaderboard every Sunday"],
                              ("Want to know if a trader is skilled or just lucky? Check their receipts with "
                               "Receipts on Telegram. " if bot else "") + "Not financial advice."))
    with tempfile.TemporaryDirectory() as wd:
        return build(scenes, out_path, wd)


HASHTAGS = "#memecoin #memecoins #solana #crypto #smartmoney #cryptotrading"


def _receipts_line():
    bot = fmt.receipts_bot()
    return f"\nScore any Fomo trader before you copy them: @{bot} on Telegram." if bot else ""


def recap_caption(rows, tokens, period="last 24h", labels=None):
    names = [fmt.ticker(tokens.get(r["mint"]), r["mint"]) for r in rows[:3]]
    when = "today" if period == "last 24h" else "this week"
    who = ""
    if labels and rows:
        who = f"\n{names[0]} was bought by " + ", ".join(fmt.buyer_names(rows[0], labels, 3)) + "."
    return (f"What smart money bought {when}: {', '.join(names)} 👀{who}\n"
            f"Data from the wallets of the top traders on Fomo. Follow for daily smart-money data."
            f"{_receipts_line()}\nNot financial advice.\n\n{HASHTAGS}")


def leaderboard_caption(traders, period=""):
    top = traders[0]
    return (f"This week's top Fomo trader: {top['label']} at {fmt.signed_money(top['pnl'])} PnL 🏆\n"
            f"Top 5 by PnL{' ' + period if period else ''}. Past results don't predict future ones."
            f"{_receipts_line()}\nNot financial advice.\n\n{HASHTAGS}")
