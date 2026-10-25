"""Pure logic: turn recorded buys into clusters and rankings (easy to test)."""
from collections import defaultdict


def group_by_mint(buys):
    g = defaultdict(lambda: {"wallets": set(), "first_ts": None, "last_ts": 0, "n_buys": 0})
    for b in buys:
        e = g[b["mint"]]
        e["wallets"].add(b["wallet"])
        e["n_buys"] += 1
        e["first_ts"] = b["ts"] if e["first_ts"] is None else min(e["first_ts"], b["ts"])
        e["last_ts"] = max(e["last_ts"], b["ts"])
    return g


def find_clusters(buys, now, window_s, min_wallets, not_before_ts=0):
    """Coins bought by >= min_wallets distinct tracked wallets inside the window.

    not_before_ts: ignore clusters whose newest buy happened before this (e.g. bot start),
    so a restart never re-posts old news.
    """
    recent = [b for b in buys if b["ts"] >= now - window_s]
    out = []
    for mint, e in group_by_mint(recent).items():
        if len(e["wallets"]) >= min_wallets and e["last_ts"] >= not_before_ts:
            out.append({"mint": mint, **e})
    out.sort(key=lambda c: (-len(c["wallets"]), c["first_ts"]))
    return out


def rank_mints(buys, k=5, min_wallets=1):
    """Most-bought coins by number of distinct wallets, then number of buys."""
    rows = [{"mint": m, **e} for m, e in group_by_mint(buys).items() if len(e["wallets"]) >= min_wallets]
    rows.sort(key=lambda r: (-len(r["wallets"]), -r["n_buys"], r["first_ts"]))
    return rows[:k]
