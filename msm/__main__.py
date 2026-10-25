"""Usage:
  python -m msm run            # run forever (poll, alerts, daily recap, weekly post)
  python -m msm once           # one poll + cluster check, then exit
  python -m msm tick           # one full cycle (wallets, poll, alerts, recap, weekly) - for cron/GitHub Actions
  python -m msm recap          # build and publish the daily recap now
  python -m msm weekly         # build and publish the weekly post now
  python -m msm test-telegram  # send a test message to your Telegram channel
  python -m msm test-x         # post a test tweet (careful: it is public)
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
    elif cmd == "weekly":
        bot.refresh_wallets()
        bot.poll()
        bot.maybe_weekly(force=True)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
