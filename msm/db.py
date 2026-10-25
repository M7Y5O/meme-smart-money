"""SQLite state: what we've seen, what we've posted."""
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS cursors (wallet TEXT PRIMARY KEY, last_sig TEXT, updated_ts INTEGER);
CREATE TABLE IF NOT EXISTS buys (
  sig TEXT, wallet TEXT, mint TEXT, ts INTEGER, sol_spent REAL, usd_spent REAL,
  PRIMARY KEY (sig, mint));
CREATE INDEX IF NOT EXISTS buys_ts ON buys(ts);
CREATE TABLE IF NOT EXISTS tokens (
  mint TEXT PRIMARY KEY, symbol TEXT, name TEXT, first_seen_ts INTEGER,
  first_mcap REAL, last_mcap REAL, liquidity REAL, url TEXT, updated_ts INTEGER);
CREATE TABLE IF NOT EXISTS alerts (mint TEXT, kind TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, channel TEXT,
  text TEXT, ts INTEGER, ok INTEGER, ref TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS traders (day TEXT, rank INTEGER, label TEXT, address TEXT, pnl REAL, x TEXT,
  PRIMARY KEY (day, address));
"""


class DB:
    def __init__(self, path):
        self.c = sqlite3.connect(path)
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)
        self.c.commit()

    # meta
    def get_meta(self, k, default=None):
        r = self.c.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
        return r["value"] if r else default

    def set_meta(self, k, v):
        self.c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (k, str(v)))
        self.c.commit()

    # cursors
    def get_cursor(self, wallet):
        r = self.c.execute("SELECT last_sig FROM cursors WHERE wallet=?", (wallet,)).fetchone()
        return r["last_sig"] if r else None

    def set_cursor(self, wallet, sig):
        self.c.execute("INSERT OR REPLACE INTO cursors(wallet,last_sig,updated_ts) VALUES(?,?,?)",
                       (wallet, sig, int(time.time())))
        self.c.commit()

    # buys
    def add_buy(self, b):
        cur = self.c.execute(
            "INSERT OR IGNORE INTO buys(sig,wallet,mint,ts,sol_spent,usd_spent) VALUES(?,?,?,?,?,?)",
            (b["sig"], b["wallet"], b["mint"], b["ts"], b.get("sol_spent", 0), b.get("usd_spent", 0)))
        self.c.commit()
        return cur.rowcount == 1

    def buys_since(self, ts):
        return [dict(r) for r in self.c.execute("SELECT * FROM buys WHERE ts>=? ORDER BY ts", (ts,))]

    # tokens
    def get_token(self, mint):
        r = self.c.execute("SELECT * FROM tokens WHERE mint=?", (mint,)).fetchone()
        return dict(r) if r else None

    def upsert_token(self, mint, info, first_seen_ts=None):
        old = self.get_token(mint)
        now = int(time.time())
        if old is None:
            self.c.execute(
                "INSERT INTO tokens(mint,symbol,name,first_seen_ts,first_mcap,last_mcap,liquidity,url,updated_ts)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (mint, info.get("symbol"), info.get("name"), first_seen_ts or now, info.get("mcap"),
                 info.get("mcap"), info.get("liquidity"), info.get("url"), now))
        else:
            self.c.execute(
                "UPDATE tokens SET symbol=COALESCE(?,symbol), name=COALESCE(?,name), last_mcap=?, liquidity=?,"
                " url=COALESCE(?,url), first_mcap=COALESCE(first_mcap,?), updated_ts=? WHERE mint=?",
                (info.get("symbol"), info.get("name"), info.get("mcap"), info.get("liquidity"), info.get("url"),
                 info.get("mcap"), now, mint))
        self.c.commit()

    # alerts / posts
    def alerted_since(self, mint, kind, ts):
        return self.c.execute("SELECT 1 FROM alerts WHERE mint=? AND kind=? AND ts>=?", (mint, kind, ts)).fetchone() is not None

    def add_alert(self, mint, kind, ts=None):
        self.c.execute("INSERT INTO alerts(mint,kind,ts) VALUES(?,?,?)", (mint, kind, int(ts or time.time())))
        self.c.commit()

    def log_post(self, kind, channel, text, ok, ref="", ts=None):
        self.c.execute("INSERT INTO posts(kind,channel,text,ts,ok,ref) VALUES(?,?,?,?,?,?)",
                       (kind, channel, text, int(ts or time.time()), 1 if ok else 0, ref))
        self.c.commit()

    def x_posts_since(self, ts):
        return self.c.execute("SELECT COUNT(*) n FROM posts WHERE channel='x' AND ok=1 AND ts>=?", (ts,)).fetchone()["n"]

    # daily top-trader snapshots (from the Fomo API)
    def save_traders(self, day, traders):
        self.c.execute("DELETE FROM traders WHERE day=?", (day,))
        self.c.executemany("INSERT OR REPLACE INTO traders(day,rank,label,address,pnl,x) VALUES(?,?,?,?,?,?)",
                           [(day, t["rank"], t["label"], t["address"], t.get("pnl"), t.get("x", "")) for t in traders])
        self.c.commit()

    def latest_traders(self):
        r = self.c.execute("SELECT MAX(day) d FROM traders").fetchone()
        if not r or not r["d"]:
            return []
        return [dict(x) for x in self.c.execute("SELECT * FROM traders WHERE day=? ORDER BY rank", (r["d"],))]
