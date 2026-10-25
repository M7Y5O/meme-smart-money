"""Copy the bot's activity to Postgres (Neon) for the dashboard, about once an hour.

Uses Neon's HTTPS SQL endpoint, so it needs no driver (stdlib only). Set DATABASE_URL to the Neon
connection string; without it nothing is sent. Hourly batches let a free Neon database sleep in between.
"""
import hashlib
import logging
import os
import time
import urllib.parse

from . import http

log = logging.getLogger("msm")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS msm_buys (sig text, mint text, wallet text, trader text, ts timestamptz,
         sol double precision, usd double precision, PRIMARY KEY (sig, mint))""",
    """CREATE TABLE IF NOT EXISTS msm_tokens (mint text PRIMARY KEY, symbol text, first_seen timestamptz,
         first_mcap double precision, last_mcap double precision, liquidity double precision, url text,
         updated timestamptz)""",
    """CREATE TABLE IF NOT EXISTS msm_posts (id text PRIMARY KEY, kind text, channel text, ok boolean,
         ts timestamptz, text text)""",
    """CREATE TABLE IF NOT EXISTS msm_traders (day date, rank int, label text, address text,
         pnl double precision, PRIMARY KEY (day, address))""",
    """CREATE TABLE IF NOT EXISTS msm_sync (at timestamptz PRIMARY KEY, buys int, posts int)""",
]


def _endpoint(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return f"https://{host}/sql"


def sql(url, query, params=None):
    return http.post(_endpoint(url), headers={"Neon-Connection-String": url},
                     body={"query": query, "params": params or []}, timeout=30, retries=2)


def upsert(url, table, cols, key, rows, chunk=300):
    """INSERT ... ON CONFLICT (key) DO UPDATE, in chunks, with $n parameters."""
    upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in key)
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        vals, params = [], []
        for r in part:
            ph = []
            for v in r:
                params.append(v)
                ph.append(f"${len(params)}")
            vals.append("(" + ",".join(ph) + ")")
        q = (f"INSERT INTO {table} ({','.join(cols)}) VALUES {','.join(vals)} "
             f"ON CONFLICT ({','.join(key)}) DO " + (f"UPDATE SET {upd}" if upd else "NOTHING"))
        sql(url, q, params)


def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts))) if ts else None


def post_id(p):
    return hashlib.sha1(f"{p['kind']}|{p['channel']}|{p['ts']}|{(p['text'] or '')[:80]}".encode()).hexdigest()[:20]


def collect(db, since, labels):
    c = db.c
    buys = [(r["sig"], r["mint"], r["wallet"], labels.get(r["wallet"], r["wallet"][:6]), _iso(r["ts"]),
             r["sol_spent"], r["usd_spent"])
            for r in c.execute("SELECT * FROM buys WHERE ts>=?", (since,))]
    tokens = [(r["mint"], r["symbol"], _iso(r["first_seen_ts"]), r["first_mcap"], r["last_mcap"], r["liquidity"],
               r["url"], _iso(r["updated_ts"]))
              for r in c.execute("SELECT * FROM tokens WHERE updated_ts>=?", (since,))]
    posts = [(post_id(dict(r)), r["kind"], r["channel"], bool(r["ok"]), _iso(r["ts"]), (r["text"] or "")[:1000])
             for r in c.execute("SELECT * FROM posts WHERE ts>=?", (since,))]
    traders = [(t["day"], t["rank"], t["label"], t["address"], t["pnl"]) for t in db.latest_traders()]
    return buys, tokens, posts, traders


def maybe_sync(bot, force=False, every=None):
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return False
    every = every or int(os.environ.get("SYNC_EVERY_SECONDS", "3600"))
    now = int(bot.clock())
    last = int(bot.db.get_meta("last_sync") or 0)
    if not force and now - last < every:
        return False
    since = (last - 3600) if last else 0  # overlap an hour so late rows aren't missed
    try:
        if bot.db.get_meta("sync_schema") != "1":
            for q in SCHEMA:
                sql(url, q)
            bot.db.set_meta("sync_schema", "1")
        buys, tokens, posts, traders = collect(bot.db, since, bot.labels)
        upsert(url, "msm_buys", ["sig", "mint", "wallet", "trader", "ts", "sol", "usd"], ["sig", "mint"], buys)
        upsert(url, "msm_tokens", ["mint", "symbol", "first_seen", "first_mcap", "last_mcap", "liquidity", "url",
                                   "updated"], ["mint"], tokens)
        upsert(url, "msm_posts", ["id", "kind", "channel", "ok", "ts", "text"], ["id"], posts)
        upsert(url, "msm_traders", ["day", "rank", "label", "address", "pnl"], ["day", "address"], traders)
        sql(url, "INSERT INTO msm_sync (at, buys, posts) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            [_iso(now), len(buys), len(posts)])
        bot.db.set_meta("last_sync", now)
        log.info("sync: %d buys, %d tokens, %d posts, %d traders sent to the dashboard",
                 len(buys), len(tokens), len(posts), len(traders))
        return True
    except Exception as e:  # the dashboard must never stop the bot
        log.warning("sync failed: %s", str(e)[:300])
        return False
