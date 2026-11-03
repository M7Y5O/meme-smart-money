"""Storytelling TikTok: 'I tracked the best Fomo traders for N days' told from the bot's real data.

Every number comes from the buys the bot recorded and live market caps. Beats are skipped when the data
doesn't support them (no losing cluster, no top trader...). Renders with the same look and voice as video.py.
"""
import logging
import os
import tempfile

from . import detect, fmt, video
from .video import DISPLAY, GAIN, LOSS, MARGIN, MED, SEMI, TEXT, TEXT2, W, Anim, El, centered, fit, text_img

log = logging.getLogger("msm")


def facts(bot, days=7):
    now = int(bot.clock())
    buys = bot.db.buys_since(now - days * 86400)
    if len(buys) < 10:
        return None
    groups = detect.group_by_mint(buys)
    bot.refresh_tokens(list(groups))
    coins = []
    for mint, g in groups.items():
        t = bot.db.get_token(mint) or {}
        mult = (t["last_mcap"] / t["first_mcap"]) if t.get("first_mcap") and t.get("last_mcap") else None
        coins.append({"mint": mint, "sym": fmt.ticker(t, mint), "wallets": g["wallets"], "mult": mult,
                      "first_mcap": t.get("first_mcap"), "last_mcap": t.get("last_mcap")})
    known = [c for c in coins if c["mult"] is not None]
    traps = sorted([c for c in known if len(c["wallets"]) >= 2 and c["mult"] < 0.8],
                   key=lambda c: (-len(c["wallets"]), c["mult"]))
    wins = sorted([c for c in known if c["mult"] >= 1.5], key=lambda c: -c["mult"])
    traders = sorted([t for t in bot.db.latest_traders() if t.get("pnl") is not None], key=lambda t: -t["pnl"])
    hours = (now - min(b["ts"] for b in buys)) / 3600
    return {
        "tracked": len(bot.wallets) or len({b["wallet"] for b in buys}),
        "period": f"{round(hours)} hours" if hours < 44 else f"{round(hours / 24)} days",
        "usd": sum(b.get("usd_spent") or 0 for b in buys),
        "coins": len(coins),
        "up": sum(1 for c in known if c["mult"] >= 1.05),
        "halved": sum(1 for c in known if c["mult"] < 0.5),
        "trap": traps[0] if traps else None,
        "win": wins[0] if wins else None,
        "top": traders[0] if traders else None,
        "labels": bot.labels,
        "pnl_period": bot.s.pnl_period_label,
    }


def statement(lines, say, kicker=None, size=118, min_dur=3.0):
    """Big centred sentence. lines: [[(text, color), ...], ...]."""
    def els(t0, t_out):
        widest = max(lines, key=lambda l: video.font(DISPLAY, size).getlength("".join(t for t, _ in l)))
        s = fit("".join(t for t, _ in widest), DISPLAY, size, W - 2 * MARGIN)
        out, y = [], 0
        imgs = [text_img([line], s, align="center") for line in lines]
        k = text_img([[(kicker, TEXT2)]], 40, SEMI, align="center") if kicker else None
        total = sum(i.height for i in imgs) + (k.height + 40 if k else 0)
        y = video._stack_top([total], [])
        if k:
            out.append(centered(k, y, t0 + 0.05, t_out, dy=0))
            y += k.height + 40
        for i, img in enumerate(imgs):
            out.append(centered(img, y, t0 + 0.15 + i * 0.28, t_out, dy=50, dur=0.55))
            y += img.height
        return out
    return {"say": say, "els": els, "min": min_dur}


def _pct(mult):
    return f"{(mult - 1) * 100:+.0f}%"


def scenes(f):
    n, period, M = f["tracked"], f["period"], fmt.money
    out = [statement([[("I tracked the ", TEXT), (f"{n} best", TEXT)], [("memecoin traders", TEXT)],
                      [("for ", TEXT2), (period + ".", TEXT2)]],
                     f"I tracked the wallets of the {n} best memecoin traders on Fomo for {period}. "
                     f"Here's what I found.", kicker="a $SMART MONEY story", min_dur=3.5),
           statement([[("They spent ", TEXT), (M(f["usd"]), GAIN)], [("on ", TEXT), (str(f["coins"]), GAIN),
                                                                    (" coins.", TEXT)]],
                     f"Together, they spent {video.spoken_money(f['usd'])} on {f['coins']} different coins."),
           statement([[("Copy them,", TEXT)], [("and you win.", TEXT)], [("Right?", TEXT2)]],
                     "So if you just copy them, you win. Right?", min_dur=2.6)]
    trap = f["trap"]
    if trap:
        names = fmt.buyer_names({"wallets": trap["wallets"]}, f["labels"], 6)
        w = len(trap["wallets"])
        card = [("Top traders who bought", str(w), None),
                ("Market cap when they bought", M(trap["first_mcap"]), None),
                ("Market cap now", M(trap["last_mcap"]), LOSS),
                ("Change", _pct(trap["mult"]), LOSS)]
        out.append(video.item_scene("The trap", trap["sym"], TEXT, card, names, "Bought by",
                                    f"Take {video.spoken_ticker(trap['sym'])}. {w} of them bought it at a "
                                    f"{video.spoken_money(trap['first_mcap'])[:-1]} market cap. Today it's at "
                                    f"{video.spoken_money(trap['last_mcap'])}. "
                                    f"Down {round((1 - trap['mult']) * 100)} percent."))
    if f["halved"]:
        out.append(statement([[(str(f["halved"]), LOSS), (" of ", TEXT), (str(f["coins"]), TEXT), (" coins", TEXT)],
                              [("lost more than half.", TEXT)],
                              [("Only ", TEXT2), (str(f["up"]), GAIN), (" went up.", TEXT2)]],
                             f"And it wasn't the only one. {f['halved']} of the {f['coins']} coins lost more "
                             f"than half their value. Only {f['up']} went up."))
    if f["win"]:
        win = f["win"]
        out.append(statement([[("The best one: ", TEXT2)], [(win["sym"], TEXT), (f"  {win['mult']:.1f}x", GAIN)]],
                             f"The best one, {video.spoken_ticker(win['sym'])}, did {win['mult']:.1f} times."))
    top = f["top"]
    if top and top["pnl"] > 0:
        name = top["label"][:20]
        out.append(statement([[("Yet ", TEXT2), (name, TEXT)], [("is up ", TEXT), (fmt.signed_money(top["pnl"]), GAIN)]],
                             f"And yet, the top trader on Fomo, {video.spoken_name(name)}, is up "
                             f"{video.spoken_money(top['pnl'])}.",
                             kicker=f"PnL {f['pnl_period']}".strip() if f["pnl_period"] else None))
    out.append(statement([[("Copying a buy", TEXT)], [("isn't copying", TEXT)], [("a strategy.", TEXT2)]],
                         "Because copying a buy isn't copying a strategy. You don't see how much they bet. "
                         "And you don't see when they sell.", min_dur=3.5))
    bot = fmt.receipts_bot()
    out.append(video.outro_scene("Check the receipts.",
                                 ["Win rate · hold time · skill or luck"] + ([f"@{bot} on Telegram"] if bot else []),
                                 "So before you copy anyone, check their receipts. "
                                 + ("Receipts on Telegram scores any Fomo trader. " if bot else "")
                                 + "Follow for smart money data every day. Not financial advice."))
    return out


def render(f, out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(scenes(f), out_path, wd)


def caption(f):
    trap = f.get("trap")
    line = (f"\n{len(trap['wallets'])} of them bought {trap['sym']}… it's {_pct(trap['mult'])} since.\n"
            if trap else "\n")
    bot = fmt.receipts_bot()
    return (f"I tracked the {f['tracked']} best memecoin traders on Fomo for {f['period']} 👀{line}"
            f"Copying a buy isn't copying a strategy."
            + (f"\nCheck any trader's receipts: @{bot} on Telegram." if bot else "")
            + f"\nNot financial advice.\n\n{video.HASHTAGS} #storytime")


# ---------- story 2: the $100 copy experiment ----------
def copy_facts(bot, days=7, stake=100):
    """What $stake on every coin a top trader bought (at the market cap when first spotted) is worth now."""
    now = int(bot.clock())
    buys = bot.db.buys_since(now - days * 86400)
    groups = detect.group_by_mint(buys)
    bot.refresh_tokens(list(groups))
    coins = []
    for mint, g in groups.items():
        t = bot.db.get_token(mint) or {}
        if t.get("first_mcap") and t.get("last_mcap"):
            coins.append({"sym": fmt.ticker(t, mint), "mult": t["last_mcap"] / t["first_mcap"],
                          "first_mcap": t["first_mcap"], "last_mcap": t["last_mcap"],
                          "who": sorted({bot.labels.get(w, w[:6]) for w in g["wallets"]}, key=str.lower)})
    if len(coins) < 8:
        return None
    coins.sort(key=lambda c: -c["mult"])
    best, worst = coins[0], coins[-1]
    if best["mult"] < 1.3 or worst["mult"] > 0.7:
        return None
    # the twist: traders whose own picks include both a big winner and a big loser
    per = {}
    for c in coins:
        for name in c["who"]:
            per.setdefault(name, []).append(c)
    twins = []
    for name, cs in per.items():
        hi, lo = max(cs, key=lambda c: c["mult"]), min(cs, key=lambda c: c["mult"])
        if hi["mult"] >= 1.3 and lo["mult"] <= 0.5:
            twins.append({"name": name, "hi": hi, "lo": lo})
    twins.sort(key=lambda x: -(x["hi"]["mult"] - x["lo"]["mult"]))
    hours = (now - min(b["ts"] for b in buys)) / 3600
    return {"stake": stake, "n": len(coins), "invested": stake * len(coins),
            "value": sum(stake * c["mult"] for c in coins), "best": best, "worst": worst,
            "halved": sum(1 for c in coins if c["mult"] < 0.5), "twins": twins[:2],
            "period": f"{round(hours)} hours" if hours < 44 else f"{round(hours / 24)} days"}


def _coin_scene(label, c, stake, say):
    up = c["mult"] >= 1
    col = GAIN if up else LOSS
    card = [("Bought by", ", ".join(c["who"][:2]), None),
            ("Market cap then", fmt.money(c["first_mcap"]), None),
            ("Market cap now", fmt.money(c["last_mcap"]), col),
            (f"${stake} became", fmt.money(stake * c["mult"]) if stake * c["mult"] >= 10 else f"${stake * c['mult']:.2f}", col)]
    return video.item_scene(label, f"{c['sym']}  {_pct(c['mult'])}", TEXT, card, [], "", say)


def copy_scenes(f):
    s, M = f["stake"], fmt.money
    best, worst = f["best"], f["worst"]
    out = [statement([[("I copied every buy", TEXT)], [("of the top traders", TEXT)], [(f"with ${s}.", TEXT2)]],
                     f"What if you copied every single buy of the top traders on Fomo, with {s} dollars each? "
                     f"I tracked their wallets for {f['period']} to find out.",
                     kicker="a $SMART MONEY experiment", min_dur=3.5),
           statement([[(str(f["n"]), GAIN), (" coins.", TEXT)], [(M(f["invested"]), GAIN), (" in.", TEXT)]],
                     f"That's {f['n']} coins. {video.spoken_money(f['invested'])} in.", min_dur=2.6),
           _coin_scene("The best one", best, s,
                       f"The best one: {video.spoken_ticker(best['sym'])}, bought by "
                       f"{video.spoken_name(best['who'][0])}. It went up {round((best['mult'] - 1) * 100)} percent. "
                       f"Your {s} dollars became {video.spoken_money(s * best['mult'])}."),
           _coin_scene("The worst one", worst, s,
                       f"The worst: {video.spoken_ticker(worst['sym'])}, bought by "
                       f"{video.spoken_name(worst['who'][0])}. Down {round((1 - worst['mult']) * 100)} percent. "
                       f"Your {s} dollars are now worth almost nothing.")]
    if f["twins"]:
        lines, said = [[("Same traders.", TEXT)]], []
        for t in f["twins"]:
            lines.append([(t["name"][:14] + "  ", TEXT2), (_pct(t["hi"]["mult"]), GAIN), ("  ", TEXT),
                          (_pct(t["lo"]["mult"]), LOSS)])
            said.append(f"{video.spoken_name(t['name'])} made {round((t['hi']['mult'] - 1) * 100)} percent "
                        f"on {video.spoken_ticker(t['hi']['sym'])}, and lost "
                        f"{round((1 - t['lo']['mult']) * 100)} percent on {video.spoken_ticker(t['lo']['sym'])}")
        out.append(statement(lines, "Here's the twist. The best and the worst picks came from the same traders. "
                             + ". ".join(said) + ".", size=96, min_dur=4.0))
    pct = (f["value"] / f["invested"] - 1) * 100
    out.append(statement([[(M(f["invested"]), TEXT), (" → ", TEXT2), (M(f["value"]), GAIN if pct >= 0 else LOSS)],
                          [(f"{pct:+.0f}%", GAIN if pct >= 0 else LOSS)],
                          [(f"{f['halved']} coins lost half.", TEXT2)]],
                         f"Final result: {video.spoken_money(f['invested'])} became "
                         f"{video.spoken_money(f['value'])}. That's {'up' if pct >= 0 else 'down'} "
                         f"{abs(round(pct))} percent. And {f['halved']} coins lost more than half.",
                         kicker="the result", min_dur=3.5))
    out.append(statement([[("Top traders lose often.", TEXT)], [("They win big", TEXT)], [("on a few.", TEXT2)]],
                         "Top traders lose often. They just win big on a few. "
                         "Copy everything, and you get all of their losses too.", min_dur=3.5))
    bot = fmt.receipts_bot()
    out.append(video.outro_scene("Know who you copy.",
                                 ["Win rate · hold time · skill or luck"] + ([f"@{bot} on Telegram"] if bot else []),
                                 "So know who you copy. "
                                 + ("Receipts on Telegram shows any Fomo trader's real win rate. " if bot else "")
                                 + "Follow for smart money data every day. Not financial advice."))
    return out


def copy_render(f, out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(copy_scenes(f), out_path, wd)


def copy_caption(f):
    pct = (f["value"] / f["invested"] - 1) * 100
    bot = fmt.receipts_bot()
    return (f"I copied every buy of the top Fomo traders with ${f['stake']} 💸\n"
            f"{f['n']} coins later: {fmt.money(f['invested'])} → {fmt.money(f['value'])} ({pct:+.0f}%).\n"
            f"Best: {f['best']['sym']} {_pct(f['best']['mult'])}. Worst: {f['worst']['sym']} {_pct(f['worst']['mult'])}."
            + (f"\nKnow who you copy: @{bot} on Telegram." if bot else "")
            + f"\nNot financial advice. Paper experiment, market caps when first spotted vs now."
            + f"\n\n{video.HASHTAGS} #storytime #copytrading")


# ---------- story 3: three styles ----------
def styles_facts(bot, days=7, min_usd=5000):
    """Three top traders with opposite styles: all-in on one buy, stacking one coin, shotgun across many."""
    now = int(bot.clock())
    buys = [b for b in bot.db.buys_since(now - days * 86400) if (b.get("usd_spent") or 0) > 0]
    if not buys:
        return None
    by = {}
    for b in buys:
        by.setdefault(b["wallet"], []).append(b)
    mints = sorted({b["mint"] for b in buys})
    bot.refresh_tokens(mints)
    toks = {m: bot.db.get_token(m) or {} for m in mints}
    board = {t["address"]: t for t in bot.db.latest_traders()}
    people = []
    for w, bs in by.items():
        usd = sum(b["usd_spent"] for b in bs)
        if usd < min_usd:
            continue
        per = {}
        for b in bs:
            per[b["mint"]] = per.get(b["mint"], 0) + b["usd_spent"]
        now_val = 0
        for m, u in per.items():
            t = toks[m]
            mult = t["last_mcap"] / t["first_mcap"] if t.get("first_mcap") and t.get("last_mcap") else 1
            now_val += u * mult
        top = sorted(per, key=lambda m: -per[m])
        people.append({"name": bot.labels.get(w, w[:6]), "buys": len(bs), "coins": len(per), "usd": usd,
                       "biggest": max(b["usd_spent"] for b in bs), "value": now_val,
                       "syms": [fmt.ticker(toks[m], m) for m in top[:6]],
                       "pnl": (board.get(w) or {}).get("pnl"), "rank": (board.get(w) or {}).get("rank")})
    pick, used = [], set()

    def take(style, cands, key):
        cands = [p for p in cands if p["name"] not in used]
        if cands:
            p = max(cands, key=key)
            used.add(p["name"])
            pick.append(dict(p, style=style))
    take("The all-in", [p for p in people if p["coins"] == 1 and p["biggest"] >= 0.7 * p["usd"]], lambda p: p["usd"])
    take("The stacker", [p for p in people if p["coins"] == 1 and p["buys"] >= 5], lambda p: p["usd"])
    take("The shotgun", [p for p in people if p["coins"] >= 8], lambda p: p["coins"])
    if len(pick) < 2:
        return None
    hours = (now - min(b["ts"] for b in buys)) / 3600
    return {"people": pick, "period": f"{round(hours)} hours" if hours < 44 else f"{round(hours / 24)} days"}


def _style_say(p):
    name, M = video.spoken_name(p["name"]), video.spoken_money
    if p["style"] == "The all-in":
        s = (f"The all-in. {name} put {M(p['usd'])} into one single coin, {video.spoken_ticker(p['syms'][0])}. "
             f"The biggest buy alone: {M(p['biggest'])}.")
    elif p["style"] == "The stacker":
        s = (f"The stacker. {name} bought the same coin, {video.spoken_ticker(p['syms'][0])}, {p['buys']} times. "
             f"{M(p['usd'])} in total, about {M(round(p['usd'] / p['buys'], -2))} each time.")
    else:
        s = (f"The shotgun. {name} made {p['buys']} buys across {p['coins']} different coins. "
             f"{M(p['usd'])} spread everywhere.")
    pct = (p["value"] / p["usd"] - 1) * 100
    if abs(pct) >= 3:
        s += f" On paper, it's {'up' if pct > 0 else 'down'} {abs(round(pct))} percent since."
    return s


def styles_scenes(f):
    M = fmt.money
    n = len(f["people"])
    out = [statement([[(f"{n} top traders.", TEXT)], [(f"{n} opposite", TEXT2)], [("strategies.", TEXT2)]],
                     f"{n} traders from the top of the Fomo leaderboard. {n} completely opposite ways to trade "
                     f"memecoins. I tracked their wallets for {f['period']}.",
                     kicker="a $SMART MONEY story", min_dur=3.5)]
    for p in f["people"]:
        pct = (p["value"] / p["usd"] - 1) * 100
        col = GAIN if pct >= 0 else LOSS
        card = [("Buys", str(p["buys"]), None), ("Coins", str(p["coins"]), None),
                ("Total bet", M(p["usd"]), None), ("Biggest buy", M(p["biggest"]), None),
                ("Since they bought", f"{pct:+.0f}%", col)]
        out.append(video.item_scene(p["style"], p["name"][:20], TEXT, card, p["syms"],
                                    "Coins" if p["coins"] > 1 else "Coin", _style_say(p)))
    ranked = [p for p in f["people"] if p.get("pnl")]
    if ranked:
        items = [((f"#{p['rank']} " if p.get("rank") else "") + p["name"][:16], fmt.signed_money(p["pnl"]),
                  GAIN if p["pnl"] >= 0 else LOSS) for p in ranked]
        all_up = all(p["pnl"] > 0 for p in ranked)
        out.append(video.summary_scene("Same leaderboard.", items,
                                        "And here's the thing. " + ("All of them are in profit on the leaderboard. "
                                        if all_up else "They're all on the leaderboard. ")
                                        + "Opposite strategies. Same result."))
    shot = next((p for p in f["people"] if p["style"] == "The shotgun"), None)
    out.append(statement([[("One buy alert", TEXT)], [("doesn't tell you", TEXT)], [("which game they play.", TEXT2)]],
                         "So when you see one of them buy, you don't know if it's a giant conviction bet, "
                         f"or one lottery ticket out of {shot['buys'] if shot else 'fifty'}. "
                         "Copy the wrong style, and you take the wrong risk.",
                         min_dur=3.5))
    bot = fmt.receipts_bot()
    out.append(video.outro_scene("Know their style.",
                                 ["Bet size · hold time · win rate"] + ([f"@{bot} on Telegram"] if bot else []),
                                 "So know their style before you copy. "
                                 + ("Receipts on Telegram shows how any Fomo trader really plays. " if bot else "")
                                 + "Follow for smart money data every day. Not financial advice."))
    return out


def styles_render(f, out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(styles_scenes(f), out_path, wd)


def styles_caption(f):
    bot = fmt.receipts_bot()
    lines = [f"{p['style']}: {p['name']} ({p['buys']} buys, {p['coins']} coin{'s' if p['coins'] > 1 else ''}, "
             f"{fmt.money(p['usd'])})" for p in f["people"]]
    return (f"{len(f['people'])} top Fomo traders, {len(f['people'])} opposite strategies 🧠\n" + "\n".join(lines)
            + "\nOne buy alert doesn't tell you which game they play."
            + (f"\nKnow their style: @{bot} on Telegram." if bot else "")
            + "\nNot financial advice. Paper values: market caps when first spotted vs now."
            + f"\n\n{video.HASHTAGS} #storytime #tradingstrategy")


# ---------- story 4: when smart money buys ----------
def _hour_label(h):
    return {0: "midnight", 12: "noon"}.get(h, f"{h % 12}{'am' if h < 12 else 'pm'}")


def timing_facts(bot, days=7, window=4):
    """Money spent by the top traders per hour of the day, New York time."""
    import datetime as dt
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    now = int(bot.clock())
    buys = [b for b in bot.db.buys_since(now - days * 86400) if (b.get("usd_spent") or 0) >= 5]
    if len(buys) < 50:
        return None
    usd = [0.0] * 24
    for b in buys:
        usd[dt.datetime.fromtimestamp(b["ts"], et).hour] += b["usd_spent"]
    total = sum(usd)
    start = max(range(24), key=lambda h: sum(usd[(h + i) % 24] for i in range(window)))
    win = sum(usd[(start + i) % 24] for i in range(window))
    night = sum(usd[0:8])
    peak = max(range(24), key=lambda h: usd[h])
    hours = (now - min(b["ts"] for b in buys)) / 3600
    return {"usd": usd, "total": total, "buys": len(buys), "start": start, "window": window,
            "win_share": win / total, "night_share": night / total, "peak": peak, "peak_usd": usd[peak],
            "period": f"{round(hours)} hours" if hours < 44 else f"{round(hours / 24)} days",
            "channel": (bot.s.telegram_channel or "").strip()}


def hour_chart(f):
    """24 bars of money spent per hour; the busiest window in green."""
    from PIL import Image, ImageDraw
    cw, ch = W - 2 * MARGIN, 760
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=44, fill=video.TILE + (255,))
    pad, top, bottom = 48, 60, 110
    bw = (cw - 2 * pad) / 24
    mx = max(f["usd"]) or 1
    inwin = {(f["start"] + i) % 24 for i in range(f["window"])}
    for h, v in enumerate(f["usd"]):
        bh = max(6, (ch - top - bottom) * v / mx)
        x0 = pad + h * bw + bw * 0.16
        col = GAIN if h in inwin else (70, 70, 74)
        d.rounded_rectangle((x0, ch - bottom - bh, x0 + bw * 0.68, ch - bottom), radius=int(bw * 0.2), fill=col + (255,))
    fl = video.font(MED, 30)
    for h in (0, 6, 12, 18):
        lab = _hour_label(h)
        d.text((pad + h * bw, ch - bottom + 28), lab, font=fl, fill=TEXT2 + (255,))
    return img


def chart_scene(f, say):
    def els(t0, t_out):
        head = text_img([[("Money spent, by hour", TEXT)]], fit("Money spent, by hour", DISPLAY, 80, W - 2 * MARGIN))
        sub = text_img([[("New York time · " + f["period"], TEXT2)]], 38, MED)
        chart = hour_chart(f)
        y = video._stack_top([head.height, sub.height, chart.height], [16, 50])
        return [El(head, MARGIN, y, t0 + 0.05, t_out),
                El(sub, MARGIN, y + head.height + 16, t0 + 0.2, t_out, dy=0),
                El(chart, MARGIN, y + head.height + 16 + sub.height + 50, t0 + 0.4, t_out, dy=60, dur=0.7)]
    return {"say": say, "els": els, "min": 4.5}


def timing_scenes(f):
    M = fmt.money
    s, e = _hour_label(f["start"]), _hour_label((f["start"] + f["window"]) % 24)
    win, night = round(f["win_share"] * 100), round(f["night_share"] * 100)
    out = [statement([[("When does", TEXT)], [("smart money", TEXT)], [("buy?", TEXT2)]],
                     f"When do the best memecoin traders on Fomo actually buy? I logged every buy for "
                     f"{f['period']}. {f['buys']} buys. {video.spoken_money(f['total'])}.",
                     kicker="a $SMART MONEY story", min_dur=3.5),
           chart_scene(f, "Here's every dollar they spent, hour by hour, New York time."),
           statement([[(f"{s} to {e}:", TEXT)], [(f"{win}%", GAIN), (" of the money.", TEXT)]],
                     f"Between {s} and {e}, they spent {win} percent of all their money. "
                     f"In just {f['window']} hours.", kicker="the window"),
           statement([[("Midnight to 8am:", TEXT)], [("only ", TEXT2), (f"{night}%", LOSS), (".", TEXT2)]],
                     f"From midnight to 8am? Only {night} percent. Smart money sleeps too."),
           statement([[("Biggest hour: ", TEXT2), (_hour_label(f["peak"]), TEXT)],
                      [(M(f["peak_usd"]), GAIN), (" in one hour.", TEXT)]],
                     f"The single biggest hour: {_hour_label(f['peak'])}. "
                     f"{video.spoken_money(f['peak_usd'])} in sixty minutes."),
           statement([[("The money moves", TEXT)], [("while you're", TEXT)], [("at work.", TEXT2)]],
                     "The biggest moves happen in the middle of the day. When most people are at work, "
                     "and can't watch the charts.", min_dur=3.5)]
    ch = f["channel"]
    bot = fmt.receipts_bot()
    out.append(video.outro_scene("Get the alerts.",
                                 ["Live smart-money alerts" + (f": {ch}" if ch else "")]
                                 + ([f"Check any trader: @{bot}"] if bot else []),
                                 "That's why the bot watches for you. Get the live alerts on our Telegram, link in "
                                 "bio. " + ("And check any trader with Receipts. " if bot else "")
                                 + "Not financial advice."))
    return out


def timing_render(f, out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(timing_scenes(f), out_path, wd)


def timing_caption(f):
    s, e = _hour_label(f["start"]), _hour_label((f["start"] + f["window"]) % 24)
    ch = f["channel"]
    return (f"When does smart money buy? ⏰\n"
            f"{s}–{e} New York time: {round(f['win_share'] * 100)}% of the money. "
            f"Midnight–8am: {round(f['night_share'] * 100)}%.\n"
            f"{f['buys']} buys from the top Fomo traders over {f['period']}."
            + (f"\nLive alerts: {ch} on Telegram." if ch else "")
            + "\nNot financial advice."
            + f"\n\n{video.HASHTAGS} #storytime #daytrading")


# ---------- story 5: how to check a memecoin (educational, no data needed) ----------
CHECKS = [
    ("Mint & freeze", [("Safe", "Both revoked", GAIN), ("Red flag", "Still active", LOSS),
                       ("Why", "Dev can print or freeze", None)],
     "Check one: mint and freeze authority. Both should be revoked. If they're still active, the dev can print "
     "new tokens, or freeze your wallet."),
    ("Liquidity pool", [("Safe", "Burned or locked", GAIN), ("Red flag", "Unlocked", LOSS),
                        ("Why", "Dev can pull it", None)],
     "Check two: the liquidity pool. It should be burned or locked. If it's unlocked, the dev can pull it "
     "and walk away with the money."),
    ("Exit size", [("Safe", "Deep enough to sell", GAIN), ("Red flag", "$500K mcap, $10K liq", LOSS),
                   ("Why", "You can't get out", None)],
     "Check three: can you actually get out? A five hundred thousand dollar market cap with ten thousand "
     "dollars of liquidity means you can't sell without crashing it."),
    ("Top holders", [("Safe", "Spread out", GAIN), ("Red flag", "Top 10 own 30%+", LOSS),
                     ("Why", "One dump ends it", None)],
     "Check four: the top holders. If ten wallets own a third of the supply, one dump ends the party."),
    ("Dev & snipers", [("Safe", "Dev holds little", GAIN), ("Red flag", "Bundled wallets", LOSS),
                       ("Why", "Same person, ready to sell", None)],
     "Check five: the dev and the snipers. Wallets that all bought in the same second are usually one person, "
     "waiting to sell to you."),
    ("Who's buying", [("Safe", "Proven traders", GAIN), ("Red flag", "Only fresh wallets", LOSS),
                      ("Why", "No next buyer", None)],
     "Check six: who's buying? Proven traders, or only brand new wallets? Without real buyers, there's no one "
     "to sell to after you."),
]


def check_scenes():
    n = len(CHECKS)
    out = [statement([[("How to check", TEXT)], [("a memecoin", TEXT)], [("in 60 seconds.", TEXT2)]],
                     f"Before you buy any memecoin, run these {n} checks. It takes sixty seconds, "
                     "and it can save your whole bag.", kicker="a $SMART MONEY guide", min_dur=3.5)]
    for i, (title, rows, say) in enumerate(CHECKS, 1):
        out.append(video.item_scene(f"Check {i}/{n}", title, TEXT, rows, [], "", say))
    out.append(statement([[(f"Pass all {n}?", TEXT)], [("Still not a buy.", TEXT)], [("Most go to zero.", TEXT2)]],
                         f"Passed all {n}? It's still not a buy. Most memecoins go to zero. "
                         "These checks just keep you out of the obvious traps.", min_dur=3.5))
    ch = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    bot = fmt.receipts_bot()
    out.append(video.outro_scene("Check who's buying.",
                                 ([f"Live smart-money alerts: {ch}"] if ch else [])
                                 + ([f"Check any trader: @{bot}"] if bot else []),
                                 "The easiest check? See who's buying. Our bot tracks the best traders on Fomo, "
                                 "live, on Telegram. Link in bio. Not financial advice."))
    return out


def check_render(out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(check_scenes(), out_path, wd)


def check_caption():
    return ("How to check a memecoin in 60 seconds ✅\n"
            "1. Mint & freeze revoked\n2. Liquidity burned or locked\n3. Enough liquidity to exit\n"
            "4. Top holders spread out\n5. No bundled dev/sniper wallets\n6. Real traders buying\n"
            "Save this for your next trade.\nNot financial advice. Most memecoins go to zero."
            f"\n\n{video.HASHTAGS} #rugpull #memecointips")


# ---------- story 6: where to find memecoins (educational, no data needed) ----------
SOURCES = [
    ("New launches", [("Coins a day", "Thousands", None), ("Risk", "Extreme", LOSS),
                      ("Catch", "Most die in minutes", None)],
     "Source one: new launches, straight from the launchpads. Thousands of coins a day. Extreme risk. "
     "Most of them die within minutes, and bots buy before you can click."),
    ("Trending pages", [("Coins a day", "Dozens", None), ("Risk", "High", LOSS),
                        ("Catch", "Can be paid for", None)],
     "Source two: trending pages. Easier to follow, but you're often late, and a spot on trending can be "
     "bought with paid boosts."),
    ("X narratives", [("Coins a day", "A few", None), ("Risk", "High", LOSS),
                      ("Catch", "Shills hide exits", None)],
     "Source three: narratives on X. Catch a meme early and it can run. But the loudest accounts are often "
     "selling to the people they hype."),
    ("Smart money", [("Coins a day", "A handful", None), ("Risk", "Medium", (255, 196, 64)),
                     ("Catch", "Copy blindly = losses", None)],
     "Source four: smart money. Coins bought by traders with a proven track record. Fewer coins, better odds. "
     "The catch: copy them blindly, and you take their losses too."),
]


def find_scenes():
    n = len(SOURCES)
    out = [statement([[("Where to find", TEXT)], [("memecoins.", TEXT)], [(f"{n} sources, ranked.", TEXT2)]],
                     f"Where do traders actually find memecoins? Here are the {n} main sources, from the riskiest "
                     "to the smartest.", kicker="a $SMART MONEY guide", min_dur=3.5)]
    for i, (title, rows, say) in enumerate(SOURCES, 1):
        out.append(video.item_scene(f"Source {i}/{n}", title, TEXT, rows, [], "", say))
    out.append(statement([[("Found one?", TEXT)], [("Run the 6 checks", TEXT)], [("before you buy.", TEXT2)]],
                         "Found a coin? Don't buy yet. Run the six checks from our last video: mint, liquidity, "
                         "exit size, holders, dev, and who's buying.", min_dur=3.5))
    ch = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    bot = fmt.receipts_bot()
    out.append(video.outro_scene("Start with smart money.",
                                 ([f"Live alerts: {ch}"] if ch else [])
                                 + ([f"Check any trader: @{bot}"] if bot else []),
                                 "We track the smart money for you, live, on Telegram. Link in bio. "
                                 + ("And check any trader's record with Receipts. " if bot else "")
                                 + "Not financial advice."))
    return out


def find_render(out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(find_scenes(), out_path, wd)


def find_caption():
    return ("Where to find memecoins: 4 sources, ranked by risk 🔎\n"
            "1. New launches: extreme risk\n2. Trending pages: often late, can be paid for\n"
            "3. X narratives: watch who's shilling\n4. Smart money: fewer coins, better odds\n"
            "Found one? Run the 6 checks before you buy.\nNot financial advice. Most memecoins go to zero."
            f"\n\n{video.HASHTAGS} #memecointips #solanamemecoins")


# ---------- story 7: why $SMART MONEY exists (the problem we solve, the value we bring) ----------
PROBLEMS = [
    ("Too much noise", [("Coins a day", "Thousands", None), ("Real signals", "A handful", None),
                        ("Result", "You chase hype", LOSS)],
     "Problem one: too much noise. Thousands of new coins every day. Only a handful matter. "
     "So most people end up chasing hype."),
    ("No view on the best", [("Their wallets", "Public on-chain", None), ("Watching 24/7", "Impossible by hand", None),
                             ("Result", "You find out too late", LOSS)],
     "Problem two: you can't see what the best traders do. Their wallets are public, but nobody can watch "
     "them all, all day. By the time you hear about a coin, it's late."),
    ("Nobody shows losses", [("Calls accounts", "Show their wins", None), ("Their losses", "Deleted", None),
                             ("Result", "You can't trust anyone", LOSS)],
     "Problem three: nobody tells the truth. Calls accounts show their wins and delete their losses. "
     "So you never know who to trust."),
]


def why_scenes():
    out = [statement([[("Thousands of coins.", TEXT)], [("Endless shills.", TEXT)], [("Who do you trust?", TEXT2)]],
                     "Thousands of new memecoins a day. Endless shills. Who do you actually trust?",
                     kicker="why $SMART MONEY exists", min_dur=3.5)]
    for i, (title, rows, say) in enumerate(PROBLEMS, 1):
        out.append(video.item_scene(f"Problem {i}/{len(PROBLEMS)}", title, TEXT, rows, [], "", say))
    out.append(statement([[("So we built a bot", TEXT)], [("that watches", TEXT)], [("the best traders.", TEXT2)]],
                         "So we built a bot that watches the best traders for you.", min_dur=3.0))
    out.append(video.item_scene("What $SM does", "The fix", TEXT,
                                [("Filters", "~25 proven wallets", GAIN), ("Watches", "24/7", GAIN),
                                 ("Alerts", "When they cluster", GAIN), ("Shows", "Wins AND losses", GAIN)],
                                [], "",
                                "It follows the top traders on Fomo, the ones with real, verified profits. It watches "
                                "their wallets around the clock. It alerts you when several of them buy the same coin. "
                                "And every week, it shows how its own alerts did. Wins and losses."))
    out.append(statement([[("Not calls.", TEXT)], [("Not promises.", TEXT)], [("Information.", GAIN)]],
                         "No calls. No promises. Just information: what the best traders do, fast, and honestly.",
                         min_dur=3.0))
    out.append(statement([[("We even show you", TEXT)], [("when we're wrong.", TEXT2)]],
                         "We even show you when we're wrong. Because that's how you know you can trust the rest.",
                         min_dur=3.0))
    ch = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    bot = fmt.receipts_bot()
    out.append(video.outro_scene("We track the wallets. You decide.",
                                 ([f"Live alerts: {ch}"] if ch else [])
                                 + ([f"Check any trader: @{bot}"] if bot else []),
                                 "We track the wallets. You decide. Live alerts on Telegram, link in bio. "
                                 "Not financial advice."))
    return out


def why_render(out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(why_scenes(), out_path, wd)


def why_caption():
    return ("Why $SMART MONEY exists 👀\n"
            "Too much noise. No view on the best traders. Nobody shows their losses.\n"
            "So we built a bot that watches the top Fomo traders 24/7, alerts when they cluster on a coin, "
            "and shows how its own alerts did. Wins AND losses.\n"
            "We track the wallets. You decide.\nNot financial advice."
            f"\n\n{video.HASHTAGS} #onchain")


# ---------- story 8: how most people lose money (animated, captions, made to be shared) ----------
_PATH = [(0, .12), (.08, .14), (.16, .13), (.24, .19), (.32, .21), (.40, .30), (.48, .45), (.56, .70),
         (.62, .92), (.66, 1.0), (.70, .82), (.76, .46), (.84, .26), (.92, .20), (1, .18)]
_SM_X, _PEAK_X, _CRASH_X = .24, .66, .92
CX, CY, CW, CH = MARGIN, 470, W - 2 * MARGIN, 680


def _pt(x, y):
    pad = 40
    return CX + pad + x * (CW - 2 * pad), CY + CH - 70 - y * (CH - 150)


def _label(d, xy, text, color, up=True):
    f = video.font(SEMI, 34)
    w = f.getlength(text) + 36
    x, y = xy
    x = min(max(CX + 12, x - w / 2), CX + CW - w - 12)
    y = y - 96 if up else y + 34
    d.rounded_rectangle((x, y, x + w, y + 58), radius=29, fill=color + (255,))
    d.text((x + 18, y + 9), text, font=f, fill=(0, 0, 0, 255))


def _chart(frame, p, shake=0, show_sm=True, show_you=True, show_crash=True, highlight_sm=False):
    """Draw the example price chart up to progress p (0..1)."""
    from PIL import Image, ImageDraw
    import random
    ox, oy = (random.randint(-shake, shake), random.randint(-shake, shake)) if shake else (0, 0)
    layer = Image.new("RGBA", (W, video.H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((CX, CY, CX + CW, CY + CH), radius=44, fill=video.TILE + (255,))
    for gy in (0.25, 0.5, 0.75):
        yy = CY + 40 + gy * (CH - 110)
        d.line((CX + 30, yy, CX + CW - 30, yy), fill=(255, 255, 255, 18), width=2)
    d.text((CX + 36, CY + 26), "$FROG", font=video.font(DISPLAY, 46), fill=TEXT + (255,))
    tag = "example"
    ft = video.font(MED, 28)
    d.text((CX + CW - 36 - ft.getlength(tag), CY + 36), tag, font=ft, fill=TEXT2 + (255,))
    pts = []
    for (x0, y0), (x1, y1) in zip(_PATH, _PATH[1:]):
        if x0 >= p:
            break
        if x1 > p:
            y1 = y0 + (y1 - y0) * (p - x0) / (x1 - x0)
            x1 = p
        pts.append(((x0, y0), (x1, y1)))
    for (x0, y0), (x1, y1) in pts:
        col = GAIN if x1 <= _PEAK_X else LOSS
        d.line((*_pt(x0, y0), *_pt(x1, y1)), fill=col + (255,), width=12, joint="curve")
    if pts:
        hx, hy = _pt(*pts[-1][1])
        d.ellipse((hx - 14, hy - 14, hx + 14, hy + 14), fill=(GAIN if p <= _PEAK_X else LOSS) + (255,))
    if show_sm and p >= _SM_X:
        sx, sy = _pt(_SM_X, .19)
        r = 20 if highlight_sm else 14
        d.ellipse((sx - r, sy - r, sx + r, sy + r), fill=GAIN + (255,), outline=(255, 255, 255, 255), width=4)
        _label(d, (sx, sy), "Smart money buys", GAIN)
    if show_you and p >= _PEAK_X:
        yx, yy = _pt(_PEAK_X, 1.0)
        d.ellipse((yx - 16, yy - 16, yx + 16, yy + 16), fill=TEXT + (255,))
        _label(d, (yx, yy), "YOU buy", TEXT, up=False)
    if show_crash and p >= _CRASH_X:
        cx, cy = _pt(_CRASH_X, .20)
        _label(d, (cx, cy), "-80%", LOSS)
    frame.paste(layer, (ox, oy), layer)


def _flash(frame, lt, dur=0.45):
    from PIL import Image
    a = max(0.0, 1 - lt / dur)
    if a > 0:
        red = Image.new("RGB", frame.size, LOSS)
        frame.paste(red, (0, 0), Image.new("L", frame.size, int(110 * a)))


def _tweet_card():
    from PIL import Image, ImageDraw
    w, h = W - 2 * MARGIN, 360
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=44, fill=video.TILE + (255,))
    d.ellipse((40, 40, 130, 130), fill=(70, 70, 74, 255))
    d.text((152, 44), "Big Crypto Account", font=video.font(DISPLAY, 44), fill=TEXT + (255,))
    d.text((152, 98), "2m · example", font=video.font(MED, 32), fill=TEXT2 + (255,))
    f = video.font(DISPLAY, 60)
    d.text((40, 170), "$FROG is going 100x.", font=f, fill=TEXT + (255,))
    d.text((40, 245), "Don't miss this one.", font=f, fill=TEXT + (255,))
    return img


def _notif_card():
    from PIL import Image, ImageDraw
    w, h = W - 2 * MARGIN, 230
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=40, fill=(30, 30, 33, 255), outline=(255, 255, 255, 30), width=2)
    logo = video.sm_logo(96)
    img.paste(logo, (34, 34), logo)
    d.text((152, 36), "Smart Money", font=video.font(DISPLAY, 42), fill=TEXT + (255,))
    fn = video.font(MED, 30)
    d.text((w - 40 - fn.getlength("now"), 44), "now", font=fn, fill=TEXT2 + (255,))
    d.ellipse((154, 112, 176, 134), fill=GAIN + (255,))
    d.text((192, 100), "3 top traders bought $FROG", font=video.font(SEMI, 40), fill=TEXT + (255,))
    d.text((152, 162), "example alert", font=fn, fill=TEXT2 + (255,))
    return img


def rug_scenes():
    out = []

    def hook(t0, t_out):
        big = text_img([[("-80%", LOSS)]], 300)
        line = text_img([[("This is how most people", TEXT)], [("lose money on memecoins.", TEXT2)]], 66, align="center")
        return [El(big, (W - big.width) / 2, 520, -1, t_out, pop=False),
                centered(line, 520 + big.height + 40, -1, t_out, dy=0),
                Anim(lambda fr, lt: _flash(fr, lt, 0.5), t0 + 0.2, t0 + 0.7)]
    out.append({"say": "This is how most people lose money on memecoins.", "els": hook, "min": 3.2,
                "sfx": [(0.2, "hit")]})

    def tweet(t0, t_out):
        k = text_img([[("It starts with a tweet.", TEXT2)]], 54, SEMI, align="center")
        card = _tweet_card()
        return [centered(k, 420, t0 + 0.05, t_out, dy=0),
                El(card, MARGIN, 560, t0 + 0.25, t_out, pop=True)]
    out.append({"say": "It starts with a tweet. A big account says this coin is going a hundred x.",
                "els": tweet, "min": 3.5, "sfx": [(0.25, "pop")]})

    def pump(t0, t_out):
        k = text_img([[("The chart goes vertical.", TEXT2)]], 54, SEMI, align="center")
        return [centered(k, 340, t0 + 0.05, t_out, dy=0),
                Anim(lambda fr, lt: _chart(fr, min(_PEAK_X, lt / 3.2 * _PEAK_X), show_sm=False,
                                           show_you=lt > 3.3), t0, t_out)]
    out.append({"say": "The chart goes vertical. Everyone is talking about it. So you buy.",
                "els": pump, "min": 4.4, "sfx": [(3.3, "pop")]})

    def before(t0, t_out):
        k = text_img([[("But who bought ", TEXT2), ("before", GAIN), (" the hype?", TEXT2)]], 54, SEMI, align="center")
        return [centered(k, 340, t0 + 0.05, t_out, dy=0),
                Anim(lambda fr, lt: _chart(fr, _PEAK_X, highlight_sm=int(lt * 3) % 2 == 0), t0, t_out)]
    out.append({"say": "But here's what you didn't see. Hours earlier, the smart money had already bought. Way lower.",
                "els": before, "min": 4.0, "sfx": [(0.4, "pop")]})

    def crash(t0, t_out):
        k = text_img([[("Then they sell. ", TEXT2), ("To you.", LOSS)]], 54, SEMI, align="center")
        dur = 1.6
        return [centered(k, 340, t0 + 0.05, t_out, dy=0),
                Anim(lambda fr, lt: _chart(fr, min(1.0, _PEAK_X + (1 - _PEAK_X) * lt / dur),
                                           shake=10 if 0.9 < lt < 1.6 else 0), t0, t_out),
                Anim(lambda fr, lt: _flash(fr, lt), t0 + 1.0, t0 + 1.5)]
    out.append({"say": "And when the hype hits, who do you think they're selling to? You.",
                "els": crash, "min": 3.8, "sfx": [(1.0, "hit")]})

    def notif(t0, t_out):
        card = _notif_card()
        k = text_img([[("So we track", TEXT)], [("those wallets.", TEXT)]], 104, align="center")
        sub = text_img([[("When top traders buy the same coin,", TEXT2)], [("you see it as it happens.", TEXT2)]],
                       44, MED, align="center")

        def slide(fr, lt):
            y = -card.height + (420 + card.height) * video.back_ease(lt / 0.6)
            fr.paste(card, (MARGIN, int(y)), card)
        return [Anim(slide, t0 + 0.1, t_out),
                centered(k, 760, t0 + 0.6, t_out),
                centered(sub, 760 + k.height + 36, t0 + 0.9, t_out)]
    out.append({"say": "That's why we built a bot that tracks those wallets. When the top traders buy the same coin, "
                       "you see it as it happens. Not hours later, in a tweet.",
                "els": notif, "min": 4.5, "sfx": [(0.1, "pop")]})

    out.append(statement([[("Not every alert wins.", TEXT)], [("We post our misses too.", TEXT2)]],
                         "Not every alert wins. And we post our misses too.", min_dur=2.8))
    ch = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    out.append(video.outro_scene("Follow the wallets, not the hype.",
                                 ([f"Live alerts: {ch}"] if ch else []) + ["Every alert, wins and losses"],
                                 "Follow the wallets, not the hype. Live alerts on Telegram, link in bio."))
    return out


def rug_render(out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(rug_scenes(), out_path, wd, captions=True, progress=True, sfx=True, pad=0.4)


def rug_caption():
    return ("This is how most people lose money on memecoins 📉\n"
            "Tweet → pump → you buy the top → the wallets that bought early sell to you.\n"
            "Follow the wallets, not the hype. Live alerts on Telegram (link in bio).\n"
            "$FROG is a made-up example. Not financial advice."
            f"\n\n{video.HASHTAGS} #memecointips #rugpull #fyp")


# ---------- story 9: market cap is a lie (liquidity explained, animated, captions) ----------
def _tank(d, x, y, w, h, level, label, value, color):
    """A pool reserve drawn as a tank filled to `level` (0..1)."""
    d.rounded_rectangle((x, y, x + w, y + h), radius=36, fill=(28, 28, 30, 255), outline=(255, 255, 255, 40), width=3)
    lv = max(0.0, min(1.0, level))
    if lv > 0.01:
        d.rounded_rectangle((x + 8, y + 8 + (h - 16) * (1 - lv), x + w - 8, y + h - 8), radius=28, fill=color + (230,))
    fl = video.font(SEMI, 38)
    d.text((x + (w - fl.getlength(label)) / 2, y - 62), label, font=fl, fill=TEXT2 + (255,))
    fv = video.font(DISPLAY, video.fit(value, DISPLAY, 50, w + 40))
    d.text((x + (w - fv.getlength(value)) / 2, y + h + 22), value, font=fv, fill=TEXT + (255,))


def _layer():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (W, video.H), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _center_text(d, y, text, size, color, name=DISPLAY):
    f = video.font(name, size)
    d.text(((W - f.getlength(text)) / 2, y), text, font=f, fill=color + (255,))


def _pool(frame, frog, sol, extra=None):
    img, d = _layer()
    tw, th, y = 330, 520, 560
    _tank(d, 150, y, tw, th, frog, "$FROG", f"{frog * 2:.2f}M", (120, 120, 126))
    _tank(d, W - 150 - tw, y, tw, th, sol, "SOL", f"{sol * 200:.0f} SOL", GAIN)
    _center_text(d, y + th / 2 - 30, "+", 60, TEXT2)
    if extra:
        extra(d)
    frame.paste(img, (0, 0), img)


def liq_scenes():
    out = []

    def hook(t0, t_out):
        def draw(fr, lt):
            img, d = _layer()
            _center_text(d, 520, "$500K", 230, TEXT)
            p = min(1.0, max(0.0, (lt - 0.6) / 0.35))
            if p > 0:
                f = video.font(DISPLAY, 230)
                tw = f.getlength("$500K")
                x0 = (W - tw) / 2 - 20
                d.line((x0, 660, x0 + (tw + 40) * p, 640), fill=LOSS + (255,), width=22)
            _center_text(d, 860, "market cap", 54, TEXT2, SEMI)
            if lt > 1.0:
                _center_text(d, 960, "You'll never sell for that.", 62, LOSS)
            fr.paste(img, (0, 0), img)
        return [Anim(draw, -1, t_out)]
    out.append({"say": "This coin has a five hundred thousand dollar market cap. You will never sell it for that. Here's why.",
                "els": hook, "min": 3.4, "sfx": [(0.6, "hit")]})

    def pool(t0, t_out):
        k = text_img([[("Meet the pool.", TEXT)]], 80, align="center")
        tag = text_img([[("example", TEXT2)]], 30, MED, align="center")
        return [centered(k, 330, t0 + 0.05, t_out, dy=0), centered(tag, 330 + k.height + 6, t0 + 0.05, t_out, dy=0),
                Anim(lambda fr, lt: _pool(fr, 0.5 * video.ease(lt / 0.5), 0.5 * video.ease(lt / 0.5)), t0 + 0.2, t_out)]
    out.append({"say": "Memecoins don't trade on an order book. They trade against a pool: coins on one side, money on the other.",
                "els": pool, "min": 4.0, "sfx": [(0.2, "pop")]})

    def buy(t0, t_out):
        k = text_img([[("You buy.", TEXT)]], 80, align="center")

        def draw(fr, lt):
            p = video.ease((lt - 0.4) / 1.6)
            sol = 0.5 * (1 + 0.3 * p)
            frog = 0.5 / (1 + 0.3 * p)

            def extra(d):
                price = ((sol / 0.5) ** 2 - 1) * 100
                _center_text(d, 1190, f"Price +{price:.0f}%", 72, GAIN)
            _pool(fr, frog, sol, extra)
        return [centered(k, 330, t0 + 0.05, t_out, dy=0), Anim(draw, t0, t_out)]
    out.append({"say": "When you buy, money goes in and coins come out. Fewer coins left, so the price goes up. "
                       "Sell, and it's the opposite.",
                "els": buy, "min": 4.5, "sfx": [(0.4, "whoosh")]})

    def size(t0, t_out):
        k = text_img([[("Same $1,000 buy.", TEXT)]], 76, align="center")

        def draw(fr, lt):
            img, d = _layer()
            p = video.ease((lt - 0.6) / 1.2)
            _tank(d, 120, 640, 360, 360, 0.15 + 0.03 * p, "Small pool", "$10K", GAIN)
            _tank(d, W - 480, 640, 360, 360, 0.85, "Big pool", "$500K", GAIN)
            if lt > 0.6:
                f = video.font(DISPLAY, 84)
                a, b = f"+{44 * p:.0f}%", f"+{0.8 * p:.1f}%"
                d.text((300 - f.getlength(a) / 2, 1100), a, font=f, fill=LOSS + (255,))
                d.text((W - 300 - f.getlength(b) / 2, 1100), b, font=f, fill=TEXT + (255,))
            fr.paste(img, (0, 0), img)
        return [centered(k, 360, t0 + 0.05, t_out, dy=0), Anim(draw, t0 + 0.15, t_out)]
    out.append({"say": "Now size matters. Put a thousand dollars into a ten thousand dollar pool, and the price jumps "
                       "forty four percent. In a five hundred thousand dollar pool? Less than one percent.",
                "els": size, "min": 5.0, "sfx": [(0.6, "pop")]})

    def lie(t0, t_out):
        k = text_img([[("$500K market cap.", TEXT)], [("$10K liquidity.", LOSS)]], 84, align="center")

        def draw(fr, lt):
            img, d = _layer()
            p = video.ease((lt - 0.8) / 1.0)
            card = video.tile([("Your bag, on paper", "$25,000", None),
                               ("What you'd get selling", f"${25000 - (25000 - 4200) * p:,.0f}", LOSS)])
            img.paste(card, (MARGIN, 760), card)
            fr.paste(img, (0, 0), img)
        return [centered(k, 360, t0 + 0.05, t_out, dy=0), Anim(draw, t0 + 0.3, t_out)]
    out.append({"say": "So on a coin with a five hundred thousand dollar market cap and only ten thousand dollars of "
                       "liquidity, a twenty five thousand dollar bag gets you about four thousand if you sell. "
                       "The market cap is a mirage.",
                "els": lie, "min": 5.5, "sfx": [(0.8, "hit")]})

    def rug(t0, t_out):
        k = text_img([[("Who holds the pool's key?", TEXT)]], 70, align="center")

        def draw(fr, lt):
            img, d = _layer()
            drain = video.ease((lt - 4.5) / 0.5)
            _tank(d, (W - 420) / 2, 560, 420, 400, 0.6 * (1 - drain), "the pool", "$0" if drain > 0.9 else "$10K", GAIN)
            if lt > 0.5:
                txt = "Key: not locked" if lt < 4.5 else "Rug pull. -100%"
                _center_text(d, 1090, txt, 60, LOSS)
            fr.paste(img, (0, 0), img)
        return [centered(k, 360, t0 + 0.05, t_out, dy=0), Anim(draw, t0 + 0.1, t_out),
                Anim(lambda fr, lt: _flash(fr, lt), t0 + 4.6, t0 + 5.1)]
    out.append({"say": "And whoever created the pool holds the key to it. If that key isn't burned or locked, "
                       "the dev can pull all the money out. That's a rug pull.",
                "els": rug, "min": 6.0, "sfx": [(4.6, "hit")]})

    def checks(t0, t_out):
        r = text_img([[("Before you buy", TEXT2)]], 44, SEMI)
        big = text_img([[("3 checks", TEXT)]], 130)
        card = video.tile([("Liquidity vs mcap", "Not a mirage", GAIN), ("Pool key", "Burned or locked", GAIN),
                           ("Volume", "Real buyers, not bots", GAIN)])
        y = 300
        return [El(r, MARGIN, y, t0 + 0.05, t_out, dy=0), El(big, MARGIN, y + r.height + 20, t0 + 0.15, t_out, dy=50, dur=0.55),
                El(card, MARGIN, y + r.height + big.height + 80, t0 + 0.45, t_out, dy=50)]
    out.append({"say": "So before you buy, check three things. Liquidity compared to market cap. Who holds the pool. "
                       "And whether the volume is real, because it's often just bots trading with themselves.",
                "els": checks, "min": 4.0, "sfx": [(0.15, "pop")]})
    ch = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    out.append(video.outro_scene("Market cap lies. Liquidity doesn't.",
                                 ([f"Live alerts: {ch}"] if ch else []) + ["$FROG is a made-up example"],
                                 "Market cap lies. Liquidity doesn't. Follow for more, and get our live alerts on Telegram."))
    return out


def liq_render(out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(liq_scenes(), out_path, wd, captions=True, progress=True, sfx=True, pad=0.4)


def liq_caption():
    return ("Market cap is a lie 🫗\n"
            "$500K mcap + $10K liquidity = a $25K bag sells for ~$4K.\n"
            "Before you buy: liquidity vs mcap, who holds the pool, is the volume real?\n"
            "$FROG is a made-up example. Not financial advice."
            f"\n\n{video.HASHTAGS} #memecointips #liquidity #rugpull #fyp")


# ---------- story 10: holders lie (top holders, bundles, snipers; animated, captions) ----------
_WALLETS = [(170, 690), (330, 610), (520, 650), (720, 600), (900, 680), (230, 820), (430, 790), (640, 830),
            (850, 800), (150, 960), (360, 940), (560, 980), (760, 950), (930, 930), (260, 1080), (480, 1100),
            (690, 1090), (880, 1070)]
_BUNDLE = {1, 3, 6, 8, 10, 12, 15, 16}  # the wallets secretly funded by the same wallet


def _wallets(frame, link=0.0, red=0.0, gone=0.0):
    """Dots for wallets. link: lines to the funder appear (0..1). red: bundle turns red. gone: bundle fades out."""
    img, d = _layer()
    fx, fy = W / 2, 500
    if link > 0:
        for i in sorted(_BUNDLE):
            x, y = _WALLETS[i]
            y = 620 + (y - 600) * 0.86
            d.line((fx, fy, fx + (x - fx) * link, fy + (y - fy) * link), fill=LOSS + (int(170 * (1 - gone)),), width=5)
        r = 46 * video.ease(link / 0.4)
        d.ellipse((fx - r, fy - r, fx + r, fy + r), fill=LOSS + (255,))
        if link > 0.5:
            f = video.font(SEMI, 34)
            t = "1 funding wallet"
            d.text((fx + 66, fy - 20), t, font=f, fill=LOSS + (255,))
    for i, (x, y) in enumerate(_WALLETS):
        y = 620 + (y - 600) * 0.86
        b = i in _BUNDLE
        col = tuple(int(GAIN[k] + (LOSS[k] - GAIN[k]) * red) for k in range(3)) if b else GAIN
        a = int(255 * (1 - gone)) if b else 255
        d.ellipse((x - 30, y - 30, x + 30, y + 30), fill=col + (a,))
    frame.paste(img, (0, 0), img)


def _supply_bar(d, y, top, label_top):
    x0, x1, h = MARGIN, W - MARGIN, 120
    d.rounded_rectangle((x0, y, x1, y + h), radius=30, fill=(44, 44, 46, 255))
    if top > 0.005:
        d.rounded_rectangle((x0, y, x0 + (x1 - x0) * top, y + h), radius=30, fill=LOSS + (255,))
    f = video.font(DISPLAY, 64)
    t = f"{top * 100:.0f}%"
    d.text((x0 + 30, y + 22), t, font=f, fill=TEXT + (255,))
    fl = video.font(MED, 38)
    d.text((x0, y + h + 26), label_top, font=fl, fill=LOSS + (255,))
    r = "everyone else"
    d.text((x1 - fl.getlength(r), y + h + 26), r, font=fl, fill=TEXT2 + (255,))


def hold_scenes():
    out = []

    def hook(t0, t_out):
        def draw(fr, lt):
            img, d = _layer()
            n = int(1200 * video.ease(lt / 1.0))
            _center_text(d, 520, f"{n:,}", 230, TEXT)
            _center_text(d, 790, "holders", 60, TEXT2, SEMI)
            if lt > 1.6:
                _center_text(d, 900, "1 owner.", 96, LOSS)
            fr.paste(img, (0, 0), img)
        return [Anim(draw, -1, t_out)]
    out.append({"say": "This coin has twelve hundred holders. Looks safe, right? One person controls half of it.",
                "els": hook, "min": 3.6, "sfx": [(1.6, "hit")]})

    def top10(t0, t_out):
        k = text_img([[("Who owns the supply?", TEXT)]], 76, align="center")

        def draw(fr, lt):
            img, d = _layer()
            _supply_bar(d, 700, 0.48 * video.ease((lt - 0.4) / 1.4), "top 10 wallets")
            fr.paste(img, (0, 0), img)
        return [centered(k, 360, t0 + 0.05, t_out, dy=0), Anim(draw, t0 + 0.1, t_out)]
    out.append({"say": "The holder count doesn't matter. Look at the top ten wallets. Here, they own almost half the supply.",
                "els": top10, "min": 4.5, "sfx": [(0.4, "whoosh")]})

    def bundle(t0, t_out):
        k = text_img([[("Different wallets?", TEXT)]], 76, align="center")

        def draw(fr, lt):
            _wallets(fr, link=video.ease((lt - 1.5) / 1.2), red=video.ease((lt - 1.5) / 0.8))
        return [centered(k, 300, t0 + 0.05, t_out, dy=0), Anim(draw, t0 + 0.1, t_out)]
    out.append({"say": "And many of those wallets? Funded by the same wallet, minutes before launch. "
                       "That's a bundle: one person, wearing many disguises.",
                "els": bundle, "min": 5.0, "sfx": [(1.5, "pop")]})

    def dump(t0, t_out):
        k = text_img([[("They sell together.", TEXT)]], 76, align="center")

        def draw(fr, lt):
            p = video.ease((lt - 0.8) / 0.6)
            _wallets(fr, link=1.0, red=1.0, gone=p)
            if lt > 0.8:
                img, d = _layer()
                _center_text(d, 1120, f"-{80 * p:.0f}%", 90, LOSS)
                fr.paste(img, (0, 0), img)
        return [centered(k, 300, t0 + 0.05, t_out, dy=0), Anim(draw, t0, t_out),
                Anim(lambda fr, lt: _flash(fr, lt), t0 + 0.9, t0 + 1.4)]
    out.append({"say": "When they sell, they sell together, and the chart dies in seconds. The holder count never warned you.",
                "els": dump, "min": 4.0, "sfx": [(0.9, "hit")]})

    def snipers(t0, t_out):
        k = text_img([[("Bought in the first second?", TEXT)]], 70, align="center")

        def draw(fr, lt):
            img, d = _layer()
            f = video.font(DISPLAY, 200)
            t = "0.4s"
            d.text(((W - f.getlength(t)) / 2, 560), t, font=f, fill=LOSS + (255,))
            _center_text(d, 820, "after launch", 54, TEXT2, SEMI)
            if lt > 1.2:
                _center_text(d, 950, "= sniper", 84, TEXT)
            fr.paste(img, (0, 0), img)
        return [centered(k, 360, t0 + 0.05, t_out, dy=0), Anim(draw, t0 + 0.3, t_out)]
    out.append({"say": "Then there are snipers: bots that buy in the very first second. They're not believers. "
                       "They're waiting for you to buy, so they can sell to you.",
                "els": snipers, "min": 4.5, "sfx": [(0.3, "pop")]})

    def checks(t0, t_out):
        r = text_img([[("Before you buy", TEXT2)]], 44, SEMI)
        big = text_img([[("3 checks", TEXT)]], 130)
        card = video.tile([("Top 10 wallets", "Not half the supply", GAIN), ("Same funder", "No clusters", GAIN),
                           ("Snipers", "Few, or gone", GAIN)])
        y = 300
        return [El(r, MARGIN, y, t0 + 0.05, t_out, dy=0), El(big, MARGIN, y + r.height + 20, t0 + 0.15, t_out, dy=50, dur=0.55),
                El(card, MARGIN, y + r.height + big.height + 80, t0 + 0.45, t_out, dy=50)]
    out.append({"say": "So before you buy, check three things. How much the top ten wallets hold. Whether wallets share "
                       "the same funder. And how many snipers are still in.",
                "els": checks, "min": 4.0, "sfx": [(0.15, "pop")]})
    ch = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    out.append(video.outro_scene("Holders lie. Wallets don't.",
                                 ([f"Live alerts: {ch}"] if ch else []) + ["Example for illustration"],
                                 "Holders lie. Wallets don't. That's why we track wallets. Follow for more, "
                                 "and get our live alerts on Telegram."))
    return out


def hold_render(out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(hold_scenes(), out_path, wd, captions=True, progress=True, sfx=True, pad=0.4)


def hold_caption():
    return ("1,200 holders. 1 owner. 🎭\n"
            "Holder count means nothing. Check the top 10 wallets, same-funder bundles and snipers before you buy.\n"
            "Example for illustration. Not financial advice."
            f"\n\n{video.HASHTAGS} #memecointips #bundles #snipers #fyp")


# ---------- story 11: take your initials (profit-taking explained, animated, captions) ----------
_TP_PATH = [(0, 1.0), (.12, 1.4), (.22, 2.0), (.3, 1.75), (.45, 3.4), (.58, 5.0), (.68, 3.1), (.78, 1.3), (.88, .55), (1.0, .2)]
_TP_SELL = .22  # where the 2x happens


def tp_chart(d, box, p, mark=False, label="2x: sell half"):
    """Price path in a rounded box, drawn up to progress p (0..1). box: (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=44, fill=video.TILE + (255,))
    ix0, ix1, iy0, iy1 = x0 + 50, x1 - 50, y0 + 110, y1 - 60

    def pt(x, m):
        return ix0 + (ix1 - ix0) * x, iy1 - (iy1 - iy0) * m / 5.3

    for m in (1, 2, 5):
        yy = pt(0, m)[1]
        d.line((ix0, yy, ix1, yy), fill=(255, 255, 255, 22), width=2)
        f = video.font(MED, 28)
        d.text((ix1 - f.getlength(f"{m}x"), yy - 36), f"{m}x", font=f, fill=TEXT2 + (255,))
    d.text((x0 + 36, y0 + 28), "$FROG", font=video.font(DISPLAY, 46), fill=TEXT + (255,))
    ft = video.font(MED, 28)
    d.text((x1 - 36 - ft.getlength("example"), y0 + 38), "example", font=ft, fill=TEXT2 + (255,))
    last = None
    for (a, ma), (b, mb) in zip(_TP_PATH, _TP_PATH[1:]):
        if a >= p:
            break
        if b > p:
            mb, b = ma + (mb - ma) * (p - a) / (b - a), p
        col = GAIN if b <= .58 else LOSS
        d.line((*pt(a, ma), *pt(b, mb)), fill=col + (255,), width=12, joint="curve")
        last = (pt(b, mb), col)
    if last:
        (hx, hy), col = last
        d.ellipse((hx - 14, hy - 14, hx + 14, hy + 14), fill=col + (255,))
    if mark and p >= _TP_SELL:
        sx, sy = pt(_TP_SELL, 2.0)
        d.ellipse((sx - 22, sy - 22, sx + 22, sy + 22), fill=GAIN + (255,), outline=(255, 255, 255, 255), width=5)
        f = video.font(SEMI, 34)
        w = f.getlength(label) + 36
        d.rounded_rectangle((sx - 20, sy - 104, sx - 20 + w, sy - 46), radius=29, fill=GAIN + (255,))
        d.text((sx - 2, sy - 95), label, font=f, fill=(0, 0, 0, 255))


def _outcome_tile(title, rows):
    """Header line + label/value rows on a dark tile."""
    from PIL import Image
    h = text_img([[(title, TEXT2)]], 40, SEMI)
    t = video.tile(rows)
    img = Image.new("RGBA", (t.width, h.height + 18 + t.height), (0, 0, 0, 0))
    img.paste(h, (6, 0), h)
    img.paste(t, (0, h.height + 18), t)
    return img


def tp_scenes():
    out = []

    def hook(t0, t_out):
        def draw(fr, lt):
            img, d = _layer()
            if lt < 3.0:  # this Anim starts at t=-1, so lt 3.0 is 2s into the video
                v = int(400 * video.ease((lt - 1.2) / 1.4))
                _center_text(d, 560, f"+{v}%", 230, GAIN)
                _center_text(d, 860, "You were up.", 64, TEXT)
            else:
                _center_text(d, 560, "-80%", 230, LOSS)
                _center_text(d, 860, "You sold here.", 64, TEXT)
            fr.paste(img, (0, 0), img)
        return [Anim(draw, -1, t_out), Anim(lambda fr, lt: _flash(fr, lt), t0 + 2.0, t0 + 2.5)]
    out.append({"say": "You were up four hundred percent. You sold at minus eighty. Here's the rule that stops that from happening.",
                "els": hook, "min": 4.0, "sfx": [(2.0, "hit")]})

    def ride(t0, t_out):
        k = text_img([[("The round trip.", TEXT)]], 80, align="center")

        def draw(fr, lt):
            img, d = _layer()
            tp_chart(d, (MARGIN, 520, W - MARGIN, 1180), video.ease((lt - 0.2) / 3.2))
            fr.paste(img, (0, 0), img)
        return [centered(k, 340, t0 + 0.05, t_out, dy=0), Anim(draw, t0 + 0.1, t_out)]
    out.append({"say": "Memecoins go up fast, and come down even faster. Most people ride the whole round trip, "
                       "waiting for one more pump.",
                "els": ride, "min": 4.5, "sfx": [(0.3, "whoosh")]})

    out.append(statement([[("Take your", TEXT)], [("initials.", GAIN)]],
                         "The fix has a name. Take your initials.", kicker="The rule", min_dur=2.6))

    def sell(t0, t_out):
        k = text_img([[("At 2x, sell half.", TEXT)]], 80, align="center")

        def draw(fr, lt):
            img, d = _layer()
            tp_chart(d, (MARGIN, 520, W - MARGIN, 1180), min(_TP_SELL, 0.02 + video.ease((lt - 0.2) / 1.2) * _TP_SELL),
                     mark=lt > 1.4)
            fr.paste(img, (0, 0), img)
        return [centered(k, 340, t0 + 0.05, t_out, dy=0), Anim(draw, t0 + 0.1, t_out)]
    out.append({"say": "When your coin does a two x, sell half. That gives you back everything you put in.",
                "els": sell, "min": 3.8, "sfx": [(1.5, "pop")]})

    def math(t0, t_out):
        k = text_img([[("The math", TEXT2)]], 44, SEMI)
        big = text_img([[("Free ride.", GAIN)]], 130)
        card = video.tile([("You put in", "$100", None), ("At 2x, you sell half", "+$100 back", GAIN),
                           ("Still in the coin", "$100, free", GAIN)])
        y = 300
        return [El(k, MARGIN, y, t0 + 0.05, t_out, dy=0), El(big, MARGIN, y + k.height + 20, t0 + 0.15, t_out, dy=50, dur=0.55),
                El(card, MARGIN, y + k.height + big.height + 80, t0 + 0.5, t_out, dy=50)]
    out.append({"say": "A hundred dollars in. At two x, you sell half and a hundred comes back to your wallet. "
                       "The other half stays in the coin, and you can't lose your own money anymore.",
                "els": math, "min": 5.0, "sfx": [(0.5, "pop")]})

    def outcomes(t0, t_out):
        a = _outcome_tile("If the coin dies", [("Held everything", "$0", LOSS), ("Took initials", "$100", GAIN)])
        b = _outcome_tile("If the coin does 10x", [("Held everything", "$1,000", GAIN), ("Took initials", "$600", GAIN)])
        return [El(a, MARGIN, 300, t0 + 0.1, t_out, dy=50), El(b, MARGIN, 300 + a.height + 60, t0 + 2.6, t_out, dy=50)]
    out.append({"say": "If the coin dies, holders end with zero. You keep your hundred. If it does a ten x, you still make six hundred. "
                       "You give up a little of the moon, and you never lose your stack.",
                "els": outcomes, "min": 6.0, "sfx": [(0.1, "pop"), (2.6, "pop")]})

    out.append(statement([[("Profits only count", TEXT)], [("when you sell.", GAIN)]],
                         "Remember: profits only count when you sell.", min_dur=2.6))
    ch = os.environ.get("TELEGRAM_CHANNEL", "").strip()
    out.append(video.outro_scene("Take profits. Not lessons.",
                                 ([f"Live alerts: {ch}"] if ch else []) + ["$FROG is a made-up example"],
                                 "Take profits, not lessons. Follow for more, and get our live alerts on Telegram."))
    return out


def tp_render(out_path):
    with tempfile.TemporaryDirectory() as wd:
        return video.build(tp_scenes(), out_path, wd, captions=True, progress=True, sfx=True, pad=0.4)


def tp_caption():
    return ("You were up 400%. You sold at -80%. 📉\n"
            "The rule: take your initials. At 2x, sell half: your $100 is back, the rest rides free.\n"
            "$FROG is a made-up example. Not financial advice."
            f"\n\n{video.HASHTAGS} #memecointips #takeprofit #fyp")
