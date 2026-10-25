"""Settings, read from environment variables (see .env.example)."""
import json
import os
from dataclasses import dataclass
from pathlib import Path


def _env(name, default=None, cast=str):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    if cast is bool:
        return v.strip().lower() in ("1", "true", "yes", "on")
    return cast(v)


def load_dotenv(path=".env"):
    """Tiny .env loader so the bot has zero dependencies."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Settings:
    helius_api_key: str
    x_api_key: str
    x_api_secret: str
    x_access_token: str
    x_access_secret: str
    telegram_bot_token: str
    telegram_channel: str
    fomo_ref_link: str
    wallets_file: str
    db_path: str
    dry_run: bool
    poll_seconds: int
    cluster_min_wallets: int
    cluster_window_hours: float
    min_liquidity_usd: float
    max_x_posts_per_day: int
    recap_hour_et: int
    weekly_day: int  # 0=Mon ... 6=Sun
    weekly_hour_et: int
    backfill_hours: int
    pnl_period_label: str = ""
    x_drafts_chat: str = ""  # Telegram chat that receives X posts to publish by hand

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(
            helius_api_key=_env("HELIUS_API_KEY", ""),
            x_api_key=_env("X_API_KEY", ""),
            x_api_secret=_env("X_API_SECRET", ""),
            x_access_token=_env("X_ACCESS_TOKEN", ""),
            x_access_secret=_env("X_ACCESS_SECRET", ""),
            telegram_bot_token=_env("TELEGRAM_BOT_TOKEN", ""),
            telegram_channel=_env("TELEGRAM_CHANNEL", ""),
            fomo_ref_link=_env("FOMO_REF_LINK", ""),
            wallets_file=_env("WALLETS_FILE", "wallets.json"),
            db_path=_env("DB_PATH", "msm.sqlite3"),
            dry_run=_env("DRY_RUN", True, bool),
            poll_seconds=_env("POLL_SECONDS", 120, int),
            cluster_min_wallets=_env("CLUSTER_MIN_WALLETS", 3, int),
            cluster_window_hours=_env("CLUSTER_WINDOW_HOURS", 6, float),
            min_liquidity_usd=_env("MIN_LIQUIDITY_USD", 25000, float),
            max_x_posts_per_day=_env("MAX_X_POSTS_PER_DAY", 8, int),
            recap_hour_et=_env("RECAP_HOUR_ET", 9, int),
            weekly_day=_env("WEEKLY_DAY", 6, int),
            weekly_hour_et=_env("WEEKLY_HOUR_ET", 10, int),
            backfill_hours=_env("BACKFILL_HOURS", 24, int),
            pnl_period_label=_env("PNL_PERIOD_LABEL", ""),
            x_drafts_chat=_env("X_DRAFTS_CHAT_ID", ""),
        )


def load_wallets(path):
    """wallets.json: [{"label": "trader name", "address": "...", "x": "@handle"}]"""
    data = json.loads(Path(path).read_text())
    out = []
    for w in data:
        if not w.get("address"):
            continue
        out.append({"label": w.get("label") or w["address"][:6], "address": w["address"], "x": w.get("x", "")})
    return out
