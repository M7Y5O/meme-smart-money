import os
import tempfile
import unittest

from msm import detect, fmt, leaderboard, publish, sources
from msm.bot import Bot
from msm.config import Settings
from msm.db import DB

W1, W2, W3, W4 = ("Wallet1aaaa", "Wallet2bbbb", "Wallet3cccc", "Wallet4dddd")
COIN = "CoinMint1111111111111111111111111111111111111"
COIN2 = "CoinMint2222222222222222222222222222222222222"


def swap_tx(sig, wallet, mint, ts, sol=0.5):
    """Shape of a Helius enhanced transaction for a SOL -> coin swap."""
    return {
        "signature": sig, "timestamp": ts, "type": "SWAP", "transactionError": None,
        "nativeTransfers": [{"fromUserAccount": wallet, "toUserAccount": "Pool", "amount": int(sol * 1e9)}],
        "tokenTransfers": [{"fromUserAccount": "Pool", "toUserAccount": wallet, "mint": mint, "tokenAmount": 123456.0}],
    }


def settings(**kw):
    base = dict(helius_api_key="k", x_api_key="", x_api_secret="", x_access_token="", x_access_secret="",
                telegram_bot_token="", telegram_channel="", fomo_ref_link="https://fomo.family/r/TEST",
                wallets_file="", db_path="", dry_run=False, poll_seconds=60, cluster_min_wallets=3,
                cluster_window_hours=6, min_liquidity_usd=25000, max_x_posts_per_day=8, recap_hour_et=9,
                weekly_day=6, weekly_hour_et=10, backfill_hours=24)
    base.update(kw)
    return Settings(**base)


class ParseTests(unittest.TestCase):
    def test_sol_swap_is_buy(self):
        b = sources.parse_buy(swap_tx("s1", W1, COIN, 100), W1)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["mint"], COIN)
        self.assertAlmostEqual(b[0]["sol_spent"], 0.5)

    def test_usdc_swap_is_buy(self):
        tx = {"signature": "s2", "timestamp": 1, "nativeTransfers": [],
              "tokenTransfers": [
                  {"fromUserAccount": W1, "toUserAccount": "Pool", "mint": sources.USDC, "tokenAmount": 250},
                  {"fromUserAccount": "Pool", "toUserAccount": W1, "mint": COIN, "tokenAmount": 10}]}
        b = sources.parse_buy(tx, W1)
        self.assertEqual(b[0]["usd_spent"], 250)

    def test_airdrop_is_not_buy(self):
        tx = swap_tx("s3", W1, COIN, 1, sol=0.000005)  # only a fee-sized SOL movement
        self.assertEqual(sources.parse_buy(tx, W1), [])

    def test_sell_is_not_buy(self):
        tx = {"signature": "s4", "timestamp": 1,
              "nativeTransfers": [{"fromUserAccount": "Pool", "toUserAccount": W1, "amount": 10**9}],
              "tokenTransfers": [{"fromUserAccount": W1, "toUserAccount": "Pool", "mint": COIN, "tokenAmount": 5}]}
        self.assertEqual(sources.parse_buy(tx, W1), [])

    def test_failed_tx_ignored(self):
        tx = swap_tx("s5", W1, COIN, 1)
        tx["transactionError"] = {"err": 1}
        self.assertEqual(sources.parse_buy(tx, W1), [])


class DetectTests(unittest.TestCase):
    def test_cluster_needs_distinct_wallets(self):
        buys = [{"mint": COIN, "wallet": W1, "ts": 100}, {"mint": COIN, "wallet": W1, "ts": 110},
                {"mint": COIN, "wallet": W2, "ts": 120}]
        self.assertEqual(detect.find_clusters(buys, 200, 3600, 3), [])
        buys.append({"mint": COIN, "wallet": W3, "ts": 130})
        c = detect.find_clusters(buys, 200, 3600, 3)
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c[0]["wallets"]), 3)

    def test_cluster_window(self):
        buys = [{"mint": COIN, "wallet": w, "ts": t} for w, t in ((W1, 0), (W2, 10), (W3, 9000))]
        self.assertEqual(detect.find_clusters(buys, 9000, 3600, 3), [])

    def test_not_before_blocks_old_news(self):
        buys = [{"mint": COIN, "wallet": w, "ts": 100 + i} for i, w in enumerate((W1, W2, W3))]
        self.assertEqual(detect.find_clusters(buys, 200, 3600, 3, not_before_ts=150), [])

    def test_rank(self):
        buys = [{"mint": COIN, "wallet": W1, "ts": 1}, {"mint": COIN, "wallet": W2, "ts": 2},
                {"mint": COIN2, "wallet": W1, "ts": 3}]
        r = detect.rank_mints(buys)
        self.assertEqual(r[0]["mint"], COIN)


class FormatTests(unittest.TestCase):
    def test_money(self):
        self.assertEqual(fmt.money(1_250_000), "$1.2M")
        self.assertEqual(fmt.money(480_000), "$480K")
        self.assertEqual(fmt.money(2_000_000_000), "$2B")

    def test_x_posts_fit(self):
        c = {"mint": COIN, "wallets": {W1, W2, W3, W4}}
        tok = {"symbol": "SUPERLONGTICKERNAME!!", "first_mcap": 410000, "last_mcap": 2300000}
        self.assertLessEqual(fmt.x_len(fmt.cluster_x(c, tok, 6)), 280)
        rows = [{"mint": f"M{i}", "wallets": {W1, W2}} for i in range(10)]
        self.assertLessEqual(fmt.x_len(fmt.recap_x(rows, {}, n=5)), 280)

    def test_ticker_sanitized(self):
        self.assertEqual(fmt.ticker({"symbol": "pe<p>e"}, COIN), "$PEPE")


class OAuthTest(unittest.TestCase):
    def test_signature_matches_twitter_docs_example(self):
        # Example from X/Twitter's "Creating a signature" documentation.
        h = publish.oauth1_header(
            "POST", "https://api.twitter.com/1.1/statuses/update.json",
            "xvz1evFS4wEEPTGEFPHBog", "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
            "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb", "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
            params={"status": "Hello Ladies + Gentlemen, a signed OAuth request!", "include_entities": "true"},
            nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg", timestamp=1318622958)
        self.assertIn('oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"', h)


class BotFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        self.now = 1_800_000_000
        self.txs = {W1: [], W2: [], W3: [], W4: []}
        self.x, self.tg = [], []
        wallets = [{"label": n, "address": a} for n, a in (("alpha", W1), ("bravo", W2), ("charlie", W3), ("delta", W4))]
        self.bot = Bot(settings(x_api_key="k", telegram_bot_token="t", telegram_channel="@c"), DB(self.tmp), wallets,
                       fetch=lambda w, last, since: [t for t in self.txs[w] if t["signature"] != last][:],
                       market=lambda mints: {m: {"symbol": "PEPE", "mcap": 400000, "liquidity": 90000, "url": "u"} for m in mints},
                       post_x=lambda t: self.x.append(t) or "1", post_tg=lambda h: self.tg.append(h) or "2",
                       clock=lambda: self.now)

    def tearDown(self):
        os.unlink(self.tmp)

    def test_cluster_posts_once(self):
        self.now += 60
        for i, w in enumerate((W1, W2, W3)):
            self.txs[w] = [swap_tx(f"sig{i}", w, COIN, self.now - 30 + i)]
        self.bot.poll()
        self.assertEqual(self.bot.check_clusters(), 1)
        self.assertEqual(len(self.x), 1)
        self.assertIn("3 top traders bought $PEPE", self.x[0])
        self.assertIn("alpha", self.tg[0])
        self.assertIn("affiliate link", self.tg[0])
        self.assertNotIn("fomo.family", self.x[0])  # no referral link on X
        # second check: no duplicate
        self.bot.poll()
        self.assertEqual(self.bot.check_clusters(), 0)

    def test_backfill_does_not_alert(self):
        for i, w in enumerate((W1, W2, W3)):
            self.txs[w] = [swap_tx(f"old{i}", w, COIN, self.now - 3600 + i)]
        self.bot.poll()
        self.assertEqual(self.bot.check_clusters(), 0)

    def test_low_liquidity_skipped(self):
        self.bot.market = lambda mints: {m: {"symbol": "RUG", "mcap": 9000, "liquidity": 500} for m in mints}
        self.now += 60
        for i, w in enumerate((W1, W2, W3)):
            self.txs[w] = [swap_tx(f"r{i}", w, COIN2, self.now - 10 + i)]
        self.bot.poll()
        self.assertEqual(self.bot.check_clusters(), 0)

    def test_daily_cap(self):
        self.bot.s.max_x_posts_per_day = 0
        self.now += 60
        for i, w in enumerate((W1, W2, W3)):
            self.txs[w] = [swap_tx(f"c{i}", w, COIN, self.now - 10 + i)]
        self.bot.poll()
        self.bot.check_clusters()
        self.assertEqual(self.x, [])
        self.assertEqual(len(self.tg), 1)

    def test_recap(self):
        for i, w in enumerate((W1, W2)):
            self.txs[w] = [swap_tx(f"d{i}", w, COIN, self.now - 100 + i)]
        self.bot.poll()
        self.assertTrue(self.bot.maybe_recap(force=True))
        self.assertIn("1. $PEPE: 2 traders", self.x[0])


class LeaderboardTests(unittest.TestCase):
    PAYLOAD = {"data": {"traders": [
        {"user": {"username": "degenking"}, "wallet": {"solana": W1}, "stats": {"pnl": "52300.5"}},
        {"user": {"username": "early_ape"}, "wallet": {"solana": W2}, "stats": {"pnl": 18000}},
        {"user": {"username": "dup"}, "wallet": {"solana": W1}, "stats": {"pnl": 1}},
        {"user": {"username": "nowallet"}, "wallet": {}, "stats": {"pnl": 9}},
        {"user": {"username": "third"}, "wallet": {"solana": W3}, "stats": {"pnl": -1200}},
    ]}}
    CFG = {"items_path": "data.traders", "field_name": "user.username", "field_wallet": "wallet.solana",
           "field_pnl": "stats.pnl", "field_x": "", "top_n": 25}

    def test_parse_nested(self):
        t = leaderboard.parse_traders(self.PAYLOAD, self.CFG)
        self.assertEqual([x["label"] for x in t], ["degenking", "early_ape", "third"])
        self.assertEqual(t[0]["pnl"], 52300.5)
        self.assertEqual(t[2]["rank"], 3)

    def test_fomoapi_io_shape(self):
        payload = {"window": "7d", "count": 2, "traders": [
            {"rank": 1, "handle": "CryptoKaleo", "displayName": "K A L E O", "pnlUsd": 151383,
             "wallets": {"solana": W1, "evm": "0x7b4d"}},
            {"rank": 2, "handle": "evmonly", "pnlUsd": 9000, "wallets": {"solana": None, "evm": "0xabc"}}]}
        cfg = {"items_path": "traders", "field_name": "handle", "field_wallet": "wallets.solana",
               "field_pnl": "pnlUsd", "field_x": "", "top_n": 25}
        t = leaderboard.parse_traders(payload, cfg)
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0]["label"], t[0]["address"], t[0]["pnl"]), ("CryptoKaleo", W1, 151383.0))

    def test_top_n(self):
        self.assertEqual(len(leaderboard.parse_traders(self.PAYLOAD, {**self.CFG, "top_n": 2})), 2)

    def test_bot_refresh_and_pnl_post(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        x, tg = [], []
        traders = leaderboard.parse_traders(self.PAYLOAD, self.CFG)
        bot = Bot(settings(x_api_key="k", telegram_bot_token="t", telegram_channel="@c", pnl_period_label="this week"),
                  DB(tmp), [], fetch=lambda *a: [], market=lambda m: {}, post_x=lambda t: x.append(t) or "1",
                  post_tg=lambda h: tg.append(h) or "2", clock=lambda: 1_800_000_000, top_traders=lambda: traders)
        self.assertTrue(bot.refresh_wallets())
        self.assertEqual(len(bot.wallets), 3)
        self.assertFalse(bot.refresh_wallets())  # once a day
        self.assertTrue(bot.post_pnl_leaderboard())
        self.assertIn("Top 3 Fomo traders this week by PnL", x[0])
        self.assertIn("1. degenking +$52.3K", x[0])
        self.assertIn("3. third -$1.2K", x[0])
        os.unlink(tmp)

    def test_api_down_keeps_fallback(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        def boom():
            raise RuntimeError("down")
        bot = Bot(settings(), DB(tmp), [{"label": "a", "address": W1}], fetch=lambda *a: [], market=lambda m: {},
                  clock=lambda: 1_800_000_000, top_traders=boom)
        self.assertFalse(bot.refresh_wallets())
        self.assertEqual(len(bot.wallets), 1)
        os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
