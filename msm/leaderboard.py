"""Daily list of top traders from the Fomo API.

The response shape is configured with env vars so it can be mapped without code changes:
  FOMO_LEADERBOARD_URL   full URL of the top-traders endpoint
  FOMO_API_KEY           secret, sent in FOMO_AUTH_HEADER (default "Authorization")
  FOMO_AUTH_PREFIX       e.g. "Bearer " (default empty)
  FOMO_ITEMS_PATH        dot path to the list in the JSON, e.g. "data.traders" ("" = top level list)
  FOMO_FIELD_NAME        field with the trader name/username   (dot path allowed)
  FOMO_FIELD_WALLET      field with the Solana wallet address  (dot path allowed)
  FOMO_FIELD_PNL         field with PnL in USD (optional)
  FOMO_FIELD_X           field with the X handle (optional)
  FOMO_TOP_N             how many traders to track (default 25)
"""
import os

from . import http


def _dig(obj, path):
    if not path:
        return obj
    for part in path.split("."):
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
        if obj is None:
            return None
    return obj


def parse_traders(payload, cfg):
    items = _dig(payload, cfg.get("items_path", "")) or []
    out, seen = [], set()
    for i, it in enumerate(items):
        wallet = _dig(it, cfg["field_wallet"])
        if not wallet or wallet in seen:
            continue
        seen.add(wallet)
        pnl = _dig(it, cfg.get("field_pnl") or "") if cfg.get("field_pnl") else None
        try:
            pnl = float(pnl) if pnl is not None else None
        except (TypeError, ValueError):
            pnl = None
        out.append({
            "rank": len(out) + 1,
            "label": str(_dig(it, cfg.get("field_name") or "") or wallet[:6]) if cfg.get("field_name") else wallet[:6],
            "address": wallet,
            "pnl": pnl,
            "x": (_dig(it, cfg["field_x"]) or "") if cfg.get("field_x") else "",
        })
        if len(out) >= cfg.get("top_n", 25):
            break
    return out


def _get(name, default=""):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def config_from_env():
    g = _get
    return {
        "url": g("FOMO_LEADERBOARD_URL", ""),
        "api_key": g("FOMO_API_KEY", ""),
        "auth_header": g("FOMO_AUTH_HEADER", "Authorization"),
        "auth_prefix": g("FOMO_AUTH_PREFIX", ""),
        "items_path": g("FOMO_ITEMS_PATH", ""),
        "field_name": g("FOMO_FIELD_NAME", "username"),
        "field_wallet": g("FOMO_FIELD_WALLET", "wallet"),
        "field_pnl": g("FOMO_FIELD_PNL", ""),
        "field_x": g("FOMO_FIELD_X", ""),
        "top_n": int(g("FOMO_TOP_N", "25")),
    }


def fetch_top_traders(cfg):
    if not cfg["url"]:
        return None
    headers = {}
    if cfg["api_key"]:
        prefix = cfg["auth_prefix"]
        if prefix and not prefix.endswith(" "):
            prefix += " "  # "Bearer" -> "Bearer " (GitHub variables trim trailing spaces)
        headers[cfg["auth_header"]] = prefix + cfg["api_key"]
    return parse_traders(http.get(cfg["url"], headers=headers), cfg)
