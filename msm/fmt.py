"""Post templates. X posts must stay <= 280 characters."""
import html
import os
import re

X_LIMIT = 280
NFA = "Not financial advice."


def receipts_bot():
    """Telegram username of the Receipts trader-check bot ("" turns the cross-promo off)."""
    v = os.environ.get("RECEIPTS_BOT")
    return "fomoreceipts_bot" if v is None else v.strip().lstrip("@")


def receipts_tg(line):
    bot = receipts_bot()
    return [f'{line} <a href="https://t.me/{bot}">@{bot}</a>'] if bot else []


def money(x):
    if not x:
        return "n/a"
    x = float(x)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if x >= div:
            v = x / div
            return f"${v:.1f}{suf}".replace(".0" + suf, suf)
    return f"${x:,.0f}"


def ticker(token, mint):
    sym = (token or {}).get("symbol") or mint[:4]
    sym = re.sub(r"[^A-Za-z0-9]", "", sym).upper()[:12] or mint[:4]
    return "$" + sym


def x_len(text):
    """X's weighted length: most Latin chars count 1, emoji and CJK count 2."""
    return sum(1 if ord(ch) <= 0x10FF or 0x2000 <= ord(ch) <= 0x200D or 0x2010 <= ord(ch) <= 0x201F
               or 0x2032 <= ord(ch) <= 0x2037 else 2 for ch in text)


def _fit(text):
    while x_len(text) > X_LIMIT:
        text = text[:-2].rstrip() + "…"
    return text


def hours_label(h):
    h = float(h)
    return f"{int(h)}h" if h == int(h) else f"{h}h"


def cluster_x(c, token, window_h):
    lines = [
        "🟢 Smart-money cluster",
        "",
        f"{len(c['wallets'])} top traders bought {ticker(token, c['mint'])} in the last {hours_label(window_h)}",
    ]
    if token and token.get("first_mcap"):
        lines.append(f"Market cap when first spotted: {money(token['first_mcap'])}")
    if token and token.get("last_mcap"):
        lines.append(f"Market cap now: {money(token['last_mcap'])}")
    lines += ["", "Full alerts on Telegram (link in bio)", NFA]
    return _fit("\n".join(lines))


def cluster_tg(c, token, window_h, labels, ref_link):
    lines = [
        "🟢 <b>Smart-money cluster</b>",
        "",
        f"<b>{len(c['wallets'])}</b> top traders bought <b>{ticker(token, c['mint'])}</b> in the last {hours_label(window_h)}",
    ]
    if token and token.get("first_mcap"):
        lines.append(f"Market cap when first spotted: {money(token['first_mcap'])}")
    if token and token.get("last_mcap"):
        lines.append(f"Market cap now: {money(token['last_mcap'])}")
    if token and token.get("liquidity"):
        lines.append(f"Liquidity: {money(token['liquidity'])}")
    if labels:
        lines += ["", "Bought by: " + ", ".join(html.escape(l) for l in labels)]
        lines += receipts_tg("🧾 Check their track record before you copy:")
    lines += ["", f"<code>{c['mint']}</code>"]
    if token and token.get("url"):
        lines.append(f'<a href="{token["url"]}">Chart</a>')
    if ref_link:
        lines += ["", f'Trade it on Fomo: {ref_link}', "(affiliate link, I earn a commission)"]
    lines += ["", NFA + " Most memecoins go to zero."]
    return "\n".join(lines)


def buyer_names(r, labels, k=3):
    """Labels of the tracked traders who bought this coin, e.g. ['pointfarmcap', 'frank', '+2']."""
    names = sorted({(labels or {}).get(w, w[:6]) for w in r["wallets"]}, key=str.lower)
    return names[:k] + ([f"+{len(names) - k}"] if len(names) > k else [])


def _clean(name):
    return re.sub(r"[@\n]", "", name)[:18]


def recap_x(rows, tokens, title="Smart-money recap, last 24h", n=3, labels=None):
    def build(with_names):
        lines = [title, "", "Most bought by top traders:"]
        for i, r in enumerate(rows[:n], 1):
            w = len(r["wallets"])
            line = f"{i}. {ticker(tokens.get(r['mint']), r['mint'])}: {w} trader{'s' if w > 1 else ''}"
            if with_names and labels:
                line += " (" + ", ".join(_clean(x) for x in buyer_names(r, labels, with_names)) + ")"
            lines.append(line)
        lines += ["", "Full list on Telegram (link in bio)", NFA]
        return "\n".join(lines)
    for k in (3, 2, 1):  # as many buyer names as fit in 280 characters
        text = build(k)
        if x_len(text) <= X_LIMIT:
            return text
    return _fit(build(0))


def recap_tg(rows, tokens, title, ref_link, n=10, labels=None):
    lines = [f"<b>{title}</b>", "", "Most bought by top traders:"]
    for i, r in enumerate(rows[:n], 1):
        t = tokens.get(r["mint"]) or {}
        w = len(r["wallets"])
        extra = f" · mcap {money(t.get('last_mcap'))}" if t.get("last_mcap") else ""
        lines.append(f"{i}. <b>{ticker(t, r['mint'])}</b>: {w} trader{'s' if w > 1 else ''}{extra}")
        if labels:
            lines.append("    ↳ " + ", ".join(html.escape(x) for x in buyer_names(r, labels, 4)))
    lines += [""] + receipts_tg("🧾 Score any Fomo trader:") if receipts_bot() else []
    if ref_link:
        lines += ["", f"Trade on Fomo: {ref_link}", "(affiliate link, I earn a commission)"]
    lines += ["", NFA]
    return "\n".join(lines)


def signed_money(x):
    return ("+" if x >= 0 else "-") + money(abs(x)) if x else "$0"


def leaderboard_x(traders, period="", n=5):
    title = f"Top {min(n, len(traders))} Fomo traders{' ' + period if period else ''} by PnL:"
    lines = [title, ""]
    for i, t in enumerate(traders[:n], 1):
        name = re.sub(r"[@\n]", "", t["label"])[:20]
        lines.append(f"{i}. {name} {signed_money(t['pnl'])}")
    lines += ["", "Full list on Telegram (link in bio)", NFA]
    bot = receipts_bot()
    if bot:
        with_cta = lines[:-2] + [f"Skill or luck? Check any trader: t.me/{bot}", NFA]
        if x_len("\n".join(with_cta)) <= X_LIMIT:
            return "\n".join(with_cta)
    return _fit("\n".join(lines))


def leaderboard_tg(traders, period, ref_link, n=10):
    lines = [f"<b>Top Fomo traders{' ' + html.escape(period) if period else ''} by PnL</b>", ""]
    for i, t in enumerate(traders[:n], 1):
        x = f" ({html.escape(t['x'])})" if t.get("x") else ""
        lines.append(f"{i}. <b>{html.escape(t['label'])}</b>{x}: {signed_money(t['pnl'])}")
    lines += [""] + receipts_tg("🧾 Skill or luck? Get any trader's score card:") if receipts_bot() else []
    if ref_link:
        lines += ["", f"Trade on Fomo: {ref_link}", "(affiliate link, I earn a commission)"]
    lines += ["", NFA + " Past results don't predict future ones."]
    return "\n".join(lines)
