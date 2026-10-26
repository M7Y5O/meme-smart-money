"""Usage:
  python -m msm run            # run forever (poll, alerts, daily recap, weekly post)
  python -m msm once           # one poll + cluster check, then exit
  python -m msm tick           # one full cycle (wallets, poll, alerts, recap, weekly) - for cron/GitHub Actions
  python -m msm recap          # build and publish the daily recap now
  python -m msm weekly         # build and publish the weekly post now
  python -m msm test-telegram  # send a test message to your Telegram channel
  python -m msm check-telegram # check the bot is admin of the channel (posts nothing)
  python -m msm telegram-chats # list chat ids that messaged the bot (for X_DRAFTS_CHAT_ID)
  python -m msm test-x-draft   # send a sample X post to X_DRAFTS_CHAT_ID
  python -m msm test-x        # post a test tweet (careful: it is public)
  python -m msm tiktok         # render today's TikTok videos (real data), send them to X_DRAFTS_CHAT_ID
  python -m msm story          # storytelling video ("I tracked the best Fomo traders...") sent to X_DRAFTS_CHAT_ID
  python -m msm sync           # send the bot's activity to the dashboard database (DATABASE_URL) now
  python -m msm traders        # fetch and print today's top traders from the Fomo API
"""
import logging
import sys

import os

from . import leaderboard, publish
from .bot import Bot
from .config import Settings, load_wallets
from .db import DB


def main(argv):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cmd = argv[1] if len(argv) > 1 else "run"
    s = Settings.from_env()
    if cmd == "test-telegram":
        print("message id:", publish.post_telegram(s, "✅ Smart Money bot is connected."))
        return
    if cmd == "check-telegram":  # read-only: nothing is posted
        from . import http
        base = f"https://api.telegram.org/bot{s.telegram_bot_token}"
        me = (http.get(f"{base}/getMe") or {}).get("result") or {}
        print("bot:", "@" + str(me.get("username")))
        chat = (http.get(f"{base}/getChat?chat_id={s.telegram_channel}") or {}).get("result") or {}
        print("channel:", chat.get("title"), chat.get("username"))
        m = (http.get(f"{base}/getChatMember?chat_id={s.telegram_channel}&user_id={me.get('id')}") or {}).get("result") or {}
        print("status:", m.get("status"), "| can_post_messages:", m.get("can_post_messages"))
        if m.get("status") != "administrator" or not m.get("can_post_messages"):
            sys.exit("bot cannot post in the channel")
        return
    if cmd == "telegram-chats":  # read-only: lists private chats that messaged the bot
        from . import http
        upd = (http.get(f"https://api.telegram.org/bot{s.telegram_bot_token}/getUpdates") or {}).get("result") or []
        seen = set()
        for u in upd:
            c = ((u.get("message") or {}).get("chat")) or {}
            if c.get("type") == "private" and c.get("id") not in seen:
                seen.add(c.get("id"))
                print("chat id:", c.get("id"), "|", c.get("first_name"), "@" + str(c.get("username")))
        if not seen:
            print("no private chat yet: send /start to the bot from your Telegram account, then run this again")
        return
    if cmd == "test-x-draft":
        print("message id:", publish.send_x_draft(s, "test", "Testing the Smart Money data feed. Not financial advice."))
        return
    if cmd == "test-x":
        print("tweet id:", publish.post_x(s, "Testing the Smart Money data feed. Not financial advice."))
        return
    if cmd == "traders":
        for t in leaderboard.fetch_top_traders(leaderboard.config_from_env()) or []:
            print(t)
        return
    if not s.helius_api_key:
        sys.exit("HELIUS_API_KEY is missing (see .env.example)")
    wallets = load_wallets(s.wallets_file) if os.path.exists(s.wallets_file) else []
    bot = Bot(s, DB(s.db_path), wallets)
    if cmd == "run":
        bot.run_forever()
    elif cmd == "tick":
        bot.tick()
    elif cmd == "once":
        bot.refresh_wallets(force=True)
        bot.poll()
        bot.check_clusters()
    elif cmd == "recap":
        bot.refresh_wallets()
        bot.poll()
        bot.maybe_recap(force=True)
    elif cmd == "tiktok":  # render today's videos from real data and send them to X_DRAFTS_CHAT_ID now
        bot.refresh_wallets()
        bot.poll()
        rows, tokens = bot._ranked(int(bot.clock()) - 24 * 3600, 10)
        print("recap video:", bot.tiktok_recap(rows, tokens))
        traders = sorted([t for t in bot.db.latest_traders() if t.get("pnl") is not None], key=lambda t: -t["pnl"])
        print("leaderboard video:", bot.tiktok_leaderboard(traders))
    elif cmd == "story":  # storytelling video from the last days of real data, sent to X_DRAFTS_CHAT_ID
        from . import story
        bot.refresh_wallets()
        bot.poll()
        f = story.facts(bot)
        print("story video:", bool(f) and bot.tiktok("story", lambda p: story.render(f, p), story.caption(f)))
    elif cmd == "sync":  # send activity to the dashboard database now
        from . import sync
        bot.refresh_wallets()
        print("synced:", sync.maybe_sync(bot, force=True))
    elif cmd == "weekly":
        bot.refresh_wallets()
        bot.poll()
        bot.maybe_weekly(force=True)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
