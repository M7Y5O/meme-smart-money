"""Data sources: Helius (wallet swaps on Solana) and DexScreener (token market data)."""
import os
import time
import urllib.parse

from . import http

HELIUS_BASE = os.environ.get("HELIUS_BASE", "https://api.helius.xyz")

# Mints treated as "money" (what traders pay with), not as the coin being bought.
WSOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
QUOTE_MINTS = {WSOL, USDC, USDT}
LAMPORTS = 1_000_000_000


def fetch_new_transactions(api_key, wallet, last_sig=None, since_ts=None, max_pages=5):
    """Newest-first parsed transactions for `wallet`, stopping at `last_sig` or older than `since_ts`."""
    out, before = [], None
    for _ in range(max_pages):
        q = {"api-key": api_key, "limit": 100}
        if before:
            q["before"] = before
        url = f"{HELIUS_BASE}/v0/addresses/{wallet}/transactions?{urllib.parse.urlencode(q)}"
        page = http.get(url) or []
        if not page:
            break
        stop = False
        for tx in page:
            if last_sig and tx.get("signature") == last_sig:
                stop = True
                break
            if since_ts and tx.get("timestamp", 0) < since_ts:
                stop = True
                break
            out.append(tx)
        if stop or len(page) < 100:
            break
        before = page[-1].get("signature")
        time.sleep(0.2)
    return out


HELIUS_RPC = os.environ.get("HELIUS_RPC", "https://mainnet.helius-rpc.com")


def _rpc(api_key, method, params):
    r = http.post(f"{HELIUS_RPC}/?api-key={api_key}",
                  body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(f"{method}: {r['error']}")
    return (r or {}).get("result")


def rpc_tx_to_simple(tx, sig, wallet):
    """Turn a getTransaction (jsonParsed) result into the small shape parse_buy() reads:
    the wallet's SOL change (fee excluded) and its per-token balance changes."""
    if not tx:
        return None
    meta = tx.get("meta") or {}
    msg = (tx.get("transaction") or {}).get("message") or {}
    keys = [k.get("pubkey") if isinstance(k, dict) else k for k in msg.get("accountKeys") or []]
    native, tokens = [], []
    if wallet in keys:
        i = keys.index(wallet)
        pre, post = meta.get("preBalances") or [], meta.get("postBalances") or []
        if i < len(pre) and i < len(post):
            delta = post[i] - pre[i]
            if i == 0:  # fee payer: don't count the network fee as "spent on the coin"
                delta += meta.get("fee") or 0
            if delta < 0:
                native.append({"fromUserAccount": wallet, "toUserAccount": "", "amount": -delta})
    bal = {}
    for side, sign in (("preTokenBalances", -1), ("postTokenBalances", 1)):
        for b in meta.get(side) or []:
            if b.get("owner") != wallet:
                continue
            amt = float(((b.get("uiTokenAmount") or {}).get("uiAmountString")) or 0)
            bal[b.get("mint")] = bal.get(b.get("mint"), 0) + sign * amt
    for mint, d in bal.items():
        if d > 0:
            tokens.append({"fromUserAccount": "", "toUserAccount": wallet, "mint": mint, "tokenAmount": d})
        elif d < 0:
            tokens.append({"fromUserAccount": wallet, "toUserAccount": "", "mint": mint, "tokenAmount": -d})
    return {"signature": sig, "timestamp": tx.get("blockTime") or 0, "transactionError": meta.get("err"),
            "nativeTransfers": native, "tokenTransfers": tokens}


def fetch_new_transactions_rpc(api_key, wallet, last_sig=None, since_ts=None, max_tx=40):
    """Cheap path (1 Helius credit per call): list new signatures, then fetch each transaction."""
    opts = {"limit": 100}
    if last_sig:
        opts["until"] = last_sig
    sigs = _rpc(api_key, "getSignaturesForAddress", [wallet, opts]) or []
    sigs = [x for x in sigs if not x.get("err") and (not since_ts or (x.get("blockTime") or 0) >= since_ts)]
    if not sigs:
        return []
    out = [{"signature": sigs[0]["signature"], "timestamp": sigs[0].get("blockTime") or 0, "cursor_only": True}]
    for x in sigs[:max_tx]:
        tx = _rpc(api_key, "getTransaction", [x["signature"], {"encoding": "jsonParsed",
                                                               "maxSupportedTransactionVersion": 0}])
        simple = rpc_tx_to_simple(tx, x["signature"], wallet)
        if simple:
            out.append(simple)
    return out


def parse_buy(tx, wallet):
    """Return buy events (one per coin received) if `wallet` paid SOL/USDC/USDT to receive a coin."""
    if tx.get("transactionError") or tx.get("cursor_only"):
        return []
    received, sent_coin = {}, set()
    sol_spent, usd_spent = 0.0, 0.0
    for t in tx.get("tokenTransfers") or []:
        mint, amt = t.get("mint"), float(t.get("tokenAmount") or 0)
        if t.get("toUserAccount") == wallet and mint not in QUOTE_MINTS and amt > 0:
            received[mint] = received.get(mint, 0) + amt
        if t.get("fromUserAccount") == wallet:
            if mint == WSOL:
                sol_spent += amt
            elif mint in (USDC, USDT):
                usd_spent += amt
            else:
                sent_coin.add(mint)
    for n in tx.get("nativeTransfers") or []:
        if n.get("fromUserAccount") == wallet:
            sol_spent += float(n.get("amount") or 0) / LAMPORTS
    # Ignore tiny SOL movements (fees, rent) so airdrops/transfers aren't counted as buys.
    paid = sol_spent >= 0.01 or usd_spent >= 1
    if not paid:
        return []
    return [{"sig": tx.get("signature"), "wallet": wallet, "mint": m, "ts": int(tx.get("timestamp") or 0),
             "amount": a, "sol_spent": round(sol_spent, 6), "usd_spent": round(usd_spent, 2)}
            for m, a in received.items() if m not in sent_coin]


def token_market_data(mints):
    """{mint: {symbol, name, mcap, liquidity, url}} from DexScreener (no API key), most liquid pair wins."""
    res = {}
    mints = list(dict.fromkeys(mints))
    for i in range(0, len(mints), 30):
        chunk = mints[i:i + 30]
        pairs = http.get("https://api.dexscreener.com/tokens/v1/solana/" + ",".join(chunk)) or []
        if isinstance(pairs, dict):
            pairs = pairs.get("pairs") or []
        for p in pairs:
            base = (p.get("baseToken") or {})
            mint = base.get("address")
            if mint not in chunk:
                continue
            liq = float((p.get("liquidity") or {}).get("usd") or 0)
            if mint in res and res[mint]["liquidity"] >= liq:
                continue
            res[mint] = {"symbol": base.get("symbol"), "name": base.get("name"),
                         "mcap": float(p.get("marketCap") or p.get("fdv") or 0),
                         "liquidity": liq, "url": p.get("url")}
        time.sleep(0.3)
    return res
