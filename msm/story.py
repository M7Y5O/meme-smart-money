"""Storytelling TikTok: 'I tracked the best Fomo traders for N days' told from the bot's real data.

Every number comes from the buys the bot recorded and live market caps. Beats are skipped when the data
doesn't support them (no losing cluster, no top trader...). Renders with the same look and voice as video.py.
"""
import logging
import tempfile

from . import detect, fmt, video
from .video import DISPLAY, GAIN, LOSS, MARGIN, MED, SEMI, TEXT, TEXT2, W, El, centered, fit, text_img

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
