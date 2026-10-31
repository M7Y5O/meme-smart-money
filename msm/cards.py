"""Image cards (1080x1350) for X drafts, in the $SM style: recap, cluster alert, leaderboard, alert receipts.

Uses the same fonts and look as the videos (video.py). Needs Pillow; without it no card is made and the
draft goes out as text only.
"""
import os
import tempfile

from . import fmt, video

W, H, M = 1080, 1350, 84


def _bg():
    return video.background().crop((0, 0, W, H))


def _put(img, el, x, y):
    img.paste(el, (int(x), int(y)), el)
    return y + el.height


def _frame(kicker, title, sub=None):
    """Background, $SM header, kicker, big title, optional sub. Returns (image, next y)."""
    img = _bg()
    b = video.brand()
    _put(img, b, (W - b.width) / 2, 70)
    y = 180
    k = video.text_img([[(kicker, video.TEXT2)]], 38, video.SEMI)
    y = _put(img, k, M, y) + 22
    t = video.text_img([[(title, video.TEXT)]], video.fit(title, video.DISPLAY, 96, W - 2 * M))
    y = _put(img, t, M, y) + 14
    if sub:
        s = video.text_img([[(sub, video.TEXT2)]], video.fit(sub, video.MED, 36, W - 2 * M), video.MED)
        y = _put(img, s, M, y)
    return img, y + 44


def _rows(rows, width=W - 2 * M, nums=None):
    """Numbered list card. rows: [(name, sub, right, right_color)]."""
    from PIL import Image, ImageDraw
    rh, pad = 136, 36
    img = Image.new("RGBA", (width, pad * 2 + rh * len(rows) - 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, width - 1, img.height - 1), radius=40, fill=video.TILE + (255,))
    for i, (name, sub, right, col) in enumerate(rows):
        y = pad + i * rh
        d.text((pad, y + 6), str(nums[i] if nums else i + 1), font=video.font(video.SEMI, 46), fill=video.TEXT2 + (255,))
        fr = video.font(video.DISPLAY, 50)
        rw = fr.getlength(right)
        d.text((width - pad - rw, y + 4), right, font=fr, fill=(col or video.TEXT) + (255,))
        nmax = width - 2 * pad - 70 - rw - 30
        fn = video.font(video.DISPLAY, video.fit(name, video.DISPLAY, 56, nmax))
        d.text((pad + 70, y), name, font=fn, fill=video.TEXT + (255,))
        if sub:
            fs = video.font(video.MED, video.fit(sub, video.MED, 30, width - 2 * pad - 70))
            d.text((pad + 70, y + 66), sub, font=fs, fill=video.TEXT2 + (255,))
        if i < len(rows) - 1:
            d.line((pad, y + rh - 22, width - pad, y + rh - 22), fill=(255, 255, 255, 26), width=2)
    return img


def _footer(img, extra=None):
    ch = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    txt = "Not financial advice" + (f"  ·  Live alerts: t.me/{ch.lstrip('@')}" if ch.startswith("@") else "")
    f = video.text_img([[(extra or txt, video.TEXT2)]], video.fit(extra or txt, video.MED, 28, W - 2 * M), video.MED)
    _put(img, f, (W - f.width) / 2, H - 66)


def _save(img, name):
    path = os.path.join(tempfile.gettempdir(), f"msm-card-{name}.png")
    img.convert("RGB").save(path, optimize=True)
    return path


# ---------- cards ----------
def recap(rows, tokens, labels=None, title="What smart money bought", period="last 24h", n=5):
    rows = rows[:n]
    if not rows:
        return None
    img, y = _frame("Smart-money recap · " + period, title, "Most bought by the top Fomo traders")
    items = []
    for r in rows:
        t = tokens.get(r["mint"]) or {}
        w = len(r["wallets"])
        who = ", ".join(fmt.buyer_names(r, labels, 3)) if labels else ""
        mc = f"mcap {fmt.money(t['last_mcap'])}" if t.get("last_mcap") else ""
        items.append((fmt.ticker(t, r["mint"]), " · ".join(x for x in (who, mc) if x),
                      f"{w} trader{'s' if w > 1 else ''}", video.GAIN if w > 1 else None))
    _put(img, _rows(items), M, y)
    _footer(img)
    return _save(img, "recap")


def cluster(c, token, window_h, labels):
    sym = fmt.ticker(token, c["mint"])
    img, y = _frame("Smart-money cluster", sym,
                    f"{len(c['wallets'])} top Fomo traders bought it in {fmt.hours_label(window_h)}")
    rows = [("Top traders", str(len(c["wallets"])), video.GAIN)]
    if token and token.get("first_mcap"):
        rows.append(("Market cap when spotted", fmt.money(token["first_mcap"]), None))
    if token and token.get("last_mcap"):
        rows.append(("Market cap now", fmt.money(token["last_mcap"]), None))
    if token and token.get("liquidity"):
        rows.append(("Liquidity", fmt.money(token["liquidity"]), None))
    card = video.tile(rows)
    y = _put(img, card, M, y) + 34
    if labels:
        lab = video.text_img([[("Bought by", video.TEXT2)]], 36, video.MED)
        y = _put(img, lab, M, y) + 14
        names = list(labels)
        while len(names) > 1:  # one line of chips: drop names into a "+N" chip until it fits
            shown = names if len(names) == len(labels) else names + [f"+{len(labels) - len(names)}"]
            if video.chips(shown).height < 100:
                break
            names = names[:-1]
        shown = names if len(names) == len(labels) else names + [f"+{len(labels) - len(names)}"]
        _put(img, video.chips(shown), M, y)
    _footer(img)
    return _save(img, "cluster")


def leaderboard(traders, period="", n=5):
    traders = traders[:n]
    if not traders:
        return None
    img, y = _frame("Weekly leaderboard" + (f" · {period}" if period else ""), "Top Fomo traders",
                    "Ranked by PnL. Past results don't predict future ones.")
    items = [(t["label"][:22], ("@" + str(t["x"]).lstrip("@")) if t.get("x") else "", fmt.signed_money(t["pnl"]),
              video.GAIN if t["pnl"] >= 0 else video.LOSS) for t in traders]
    _put(img, _rows(items), M, y)
    bot = fmt.receipts_bot()
    _footer(img, f"Skill or luck? Check any trader: @{bot}  ·  Not financial advice" if bot else None)
    return _save(img, "leaderboard")


def receipts(items, stats):
    """items: [{'sym', 'mult', 'at', 'now'}] best first."""
    if not items:
        return None
    up, n = stats["up"], stats["n"]
    img, y = _frame("Alert receipts · last 7 days", "How our alerts did",
                    f"{n} alerts · {up} up · {n - up} down · wins AND losses"
                    + (" · best 3, worst 2" if n > 5 else ""))
    rows = []
    nums = list(range(1, 6)) if len(items) <= 5 else [1, 2, 3, len(items) - 1, len(items)]
    for it in (items if len(items) <= 5 else items[:3] + items[-2:]):  # best 3 + worst 2
        pct = (it["mult"] - 1) * 100
        rows.append((it["sym"], f"{fmt.money(it['at'])} at alert → {fmt.money(it['now'])} now", f"{pct:+.0f}%",
                     video.GAIN if pct >= 0 else video.LOSS))
    _put(img, _rows(rows, nums=nums), M, y)
    _footer(img)
    return _save(img, "receipts")
