"""Orchestration: poll wallets -> store buys -> detect -> publish."""
import datetime as dt
import logging
import time
from zoneinfo import ZoneInfo

from . import detect, fmt, leaderboard, publish, sources

ET = ZoneInfo("America/New_York")
log = logging.getLogger("msm")


class Bot:
    def __init__(self, settings, db, wallets, fetch=None, market=None, post_x=None, post_tg=None, clock=None,
                 top_traders=None):
        self.s, self.db = settings, db
        self.fallback_wallets = wallets
        self.set_wallets(wallets)
        lb_cfg = leaderboard.config_from_env()
        self.top_traders = top_traders or (lambda: leaderboard.fetch_top_traders(lb_cfg))
        self.fetch = fetch or (lambda w, last, since: sources.fetch_new_transactions(settings.helius_api_key, w, last, since))
        self.market = market or sources.token_market_data
        self.post_x = post_x or (lambda text: publish.post_x(settings, text))
        self.post_tg = post_tg or (lambda html: publish.post_telegram(settings, html))
        self.clock = clock or time.time
        # First time this bot ever ran. Clusters older than this are never posted, so the first
        # run (which backfills history) stays quiet. Stored, so scheduled runs share one value.
        first = self.db.get_meta("first_start")
        if first is None:
            first = int(self.clock())
            self.db.set_meta("first_start", first)
        self.start_ts = int(first)

    def set_wallets(self, wallets):
        self.wallets = wallets
        self.labels = {w["address"]: w["label"] for w in wallets}

    # ---------- data ----------
    def refresh_wallets(self, force=False):
        """Once a day, replace the tracked wallets with today's top traders from the Fomo API."""
        today = dt.datetime.fromtimestamp(self.clock(), ET).date().isoformat()
        if not force and self.db.get_meta("last_wallet_refresh") == today:
            return False
        try:
            traders = self.top_traders()
        except Exception as e:
            log.warning("Fomo leaderboard failed, keeping current wallets: %s", e)
            return False
        if not traders:  # API not configured or empty: keep wallets.json / previous list
            if not self.wallets:
                self.set_wallets(self.fallback_wallets)
            return False
        self.db.save_traders(today, traders)
        self.db.set_meta("last_wallet_refresh", today)
        self.set_wallets([{"label": t["label"], "address": t["address"], "x": t.get("x", "")} for t in traders])
        log.info("tracking today's top %d Fomo traders", len(traders))
        return True

    def poll(self):
        now = int(self.clock())
        new_buys = []
        for w in self.wallets:
            addr = w["address"]
            last = self.db.get_cursor(addr)
            since = None if last else now - self.s.backfill_hours * 3600
            try:
                txs = self.fetch(addr, last, since)
            except Exception as e:  # one bad wallet shouldn't stop the others
                log.warning("fetch failed for %s: %s", w["label"], e)
                continue
            if txs:
                self.db.set_cursor(addr, txs[0]["signature"])
            for tx in txs:
                for b in sources.parse_buy(tx, addr):
                    if self.db.add_buy(b):
                        new_buys.append(b)
        if new_buys:
            first_ts = {}
            for b in new_buys:
                first_ts[b["mint"]] = min(first_ts.get(b["mint"], b["ts"]), b["ts"])
            unknown = [m for m in first_ts if not self.db.get_token(m)]
            self.refresh_tokens(unknown, first_ts)
        log.info("poll: %d new buys from %d wallets", len(new_buys), len(self.wallets))
        return new_buys

    def refresh_tokens(self, mints, first_ts=None):
        if not mints:
            return
        try:
            data = self.market(mints)
        except Exception as e:
            log.warning("market data failed: %s", e)
            return
        for m in mints:
            if m in data:
                self.db.upsert_token(m, data[m], (first_ts or {}).get(m))

    # ---------- publishing ----------
    def _et_midnight_ts(self):
        now = dt.datetime.fromtimestamp(self.clock(), ET)
        return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    def publish(self, kind, x_text, tg_html, ref=""):
        if self.s.dry_run:
            print(f"\n----- [DRY RUN] {kind} -> X ({fmt.x_len(x_text)} chars) -----\n{x_text}")
            print(f"----- [DRY RUN] {kind} -> Telegram -----\n{tg_html}\n")
            self.db.log_post(kind, "dry", x_text, True, ref, ts=self.clock())
            return
        if x_text and self.s.x_api_key:
            if self.db.x_posts_since(self._et_midnight_ts()) >= self.s.max_x_posts_per_day:
                log.info("X daily cap reached, skipping X for %s", kind)
            else:
                try:
                    tid = self.post_x(x_text)
                    self.db.log_post(kind, "x", x_text, True, tid, ts=self.clock())
                except Exception as e:
                    log.error("X post failed: %s", e)
                    self.db.log_post(kind, "x", x_text, False, str(e)[:200], ts=self.clock())
        if tg_html and self.s.telegram_bot_token and self.s.telegram_channel:
            try:
                mid = self.post_tg(tg_html)
                self.db.log_post(kind, "telegram", tg_html, True, mid, ts=self.clock())
            except Exception as e:
                log.error("Telegram post failed: %s", e)
                self.db.log_post(kind, "telegram", tg_html, False, str(e)[:200], ts=self.clock())

    # ---------- jobs ----------
    def check_clusters(self):
        now = int(self.clock())
        window = int(self.s.cluster_window_hours * 3600)
        buys = self.db.buys_since(now - window)
        posted = 0
        for c in detect.find_clusters(buys, now, window, self.s.cluster_min_wallets, self.start_ts):
            if self.db.alerted_since(c["mint"], "cluster", now - 24 * 3600):
                continue
            self.refresh_tokens([c["mint"]])
            tok = self.db.get_token(c["mint"])
            if not tok or (tok.get("liquidity") or 0) < self.s.min_liquidity_usd:
                log.info("cluster on %s skipped (low/unknown liquidity)", c["mint"])
                continue
            labels = [self.labels.get(w, w[:6]) for w in sorted(c["wallets"])]
            self.publish("cluster",
                         fmt.cluster_x(c, tok, self.s.cluster_window_hours),
                         fmt.cluster_tg(c, tok, self.s.cluster_window_hours, labels, self.s.fomo_ref_link),
                         c["mint"])
            self.db.add_alert(c["mint"], "cluster", self.clock())
            posted += 1
        return posted

    def _ranked(self, since_ts, k):
        rows = detect.rank_mints(self.db.buys_since(since_ts), k=k * 3)
        self.refresh_tokens([r["mint"] for r in rows])
        tokens = {r["mint"]: self.db.get_token(r["mint"]) for r in rows}
        rows = [r for r in rows if (tokens[r["mint"]] or {}).get("liquidity", 0) >= self.s.min_liquidity_usd]
        return rows[:k], tokens

    def maybe_recap(self, force=False):
        now = dt.datetime.fromtimestamp(self.clock(), ET)
        today = now.date().isoformat()
        if not force and (now.hour < self.s.recap_hour_et or self.db.get_meta("last_recap") == today):
            return False
        self.db.set_meta("last_recap", today)
        rows, tokens = self._ranked(int(self.clock()) - 24 * 3600, 10)
        if not rows:
            log.info("recap: nothing to post")
            return False
        self.publish("recap", fmt.recap_x(rows, tokens),
                     fmt.recap_tg(rows, tokens, "Smart-money recap, last 24h", self.s.fomo_ref_link))
        return True

    def maybe_weekly(self, force=False):
        now = dt.datetime.fromtimestamp(self.clock(), ET)
        today = now.date().isoformat()
        due = now.weekday() == self.s.weekly_day and now.hour >= self.s.weekly_hour_et
        if not force and (not due or self.db.get_meta("last_weekly") == today):
            return False
        self.db.set_meta("last_weekly", today)
        self.post_pnl_leaderboard()
        rows, tokens = self._ranked(int(self.clock()) - 7 * 24 * 3600, 10)
        if not rows:
            return False
        self.publish("weekly",
                     fmt.recap_x(rows, tokens, title="This week: what smart money bought most", n=5),
                     fmt.recap_tg(rows, tokens, "This week: what smart money bought most", self.s.fomo_ref_link))
        return True

    def post_pnl_leaderboard(self):
        traders = [t for t in self.db.latest_traders() if t.get("pnl") is not None]
        if len(traders) < 3:
            return False
        traders.sort(key=lambda t: -t["pnl"])
        period = self.s.pnl_period_label
        self.publish("leaderboard", fmt.leaderboard_x(traders, period), fmt.leaderboard_tg(traders, period, self.s.fomo_ref_link))
        return True

    def tick(self):
        self.refresh_wallets()
        self.poll()
        self.check_clusters()
        self.maybe_recap()
        self.maybe_weekly()

    def run_forever(self):
        log.info("bot started: %d wallets, dry_run=%s", len(self.wallets), self.s.dry_run)
        while True:
            try:
                self.tick()
            except Exception as e:
                log.exception("tick failed: %s", e)
            time.sleep(self.s.poll_seconds)
