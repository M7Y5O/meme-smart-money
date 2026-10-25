"""Minimal HTTP helpers (stdlib only) with retries."""
import json
import time
import urllib.error
import urllib.request

UA = "meme-smart-money-bot/1.0"


def request(method, url, headers=None, body=None, timeout=20, retries=3):
    data = None
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            data = body.encode()
        else:
            data = body
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode() or "null"
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            last = RuntimeError(f"{method} {url.split('?')[0]} -> HTTP {e.code}: {msg}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 * (attempt + 1) * (5 if e.code == 429 else 1))
                continue
            raise last
        except (urllib.error.URLError, TimeoutError) as e:
            last = RuntimeError(f"{method} {url.split('?')[0]} -> {e}")
            time.sleep(2 * (attempt + 1))
    raise last


def get(url, **kw):
    return request("GET", url, **kw)


def post(url, **kw):
    return request("POST", url, **kw)
