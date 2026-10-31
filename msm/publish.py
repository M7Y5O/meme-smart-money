"""Publishing to X (API v2, OAuth 1.0a user context) and Telegram (Bot API)."""
import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse

from . import http

X_TWEET_URL = "https://api.x.com/2/tweets"


def _pct(s):
    return urllib.parse.quote(str(s), safe="~-._")


def oauth1_header(method, url, consumer_key, consumer_secret, token, token_secret, params=None,
                  nonce=None, timestamp=None):
    """OAuth 1.0a HMAC-SHA1 Authorization header. JSON bodies are not part of the signature."""
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(timestamp or int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    all_params = {**(params or {}), **oauth}
    # Percent-encode keys and values, then sort the encoded pairs (RFC 5849 section 3.4.1.3.2).
    param_str = "&".join(f"{k}={v}" for k, v in sorted((_pct(k), _pct(v)) for k, v in all_params.items()))
    base = "&".join([method.upper(), _pct(url), _pct(param_str)])
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


def post_x(s, text):
    auth = oauth1_header("POST", X_TWEET_URL, s.x_api_key, s.x_api_secret, s.x_access_token, s.x_access_secret)
    r = http.post(X_TWEET_URL, headers={"Authorization": auth}, body={"text": text}, retries=1)
    return (r or {}).get("data", {}).get("id", "")


def post_telegram(s, html_text, chat_id=None):
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    body = {"chat_id": chat_id or s.telegram_channel, "text": html_text, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    r = http.post(url, body=body)
    return str(((r or {}).get("result") or {}).get("message_id", ""))


def send_x_draft(s, kind, text):
    """Send an X post to your private Telegram chat, ready to copy (tap the block to copy it)."""
    import html
    msg = f"\U0001F4DD <b>X post to publish</b> ({html.escape(kind)})\n\n<pre>{html.escape(text)}</pre>"
    return post_telegram(s, msg, chat_id=s.x_drafts_chat)


def _multipart_upload(s, method, field, chat_id, path, caption_html, mime, extra=None, timeout=120):
    import os
    import uuid
    boundary = uuid.uuid4().hex
    fields = {"chat_id": str(chat_id), "caption": caption_html, "parse_mode": "HTML", **(extra or {})}
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
             for k, v in fields.items()]
    with open(path, "rb") as f:
        data = f.read()
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{os.path.basename(path)}"\r\n'
                 f'Content-Type: {mime}\r\n\r\n'.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/{method}"
    r = http.post(url, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                  body=b"".join(parts), timeout=timeout)
    return str(((r or {}).get("result") or {}).get("message_id", ""))


def send_x_photo_draft(s, kind, text, path):
    """X post + its image card, sent to your private Telegram chat: save the image, copy the text."""
    import html
    cap = f"\U0001F4DD <b>X post to publish</b> ({html.escape(kind)}), with this image\n\n<pre>{html.escape(text)}</pre>"
    return _multipart_upload(s, "sendPhoto", "photo", s.x_drafts_chat, path, cap[:1024], "image/png")


def send_video(s, chat_id, path, caption_html):
    """Upload a video to a Telegram chat (multipart/form-data, stdlib only)."""
    import os
    import uuid
    boundary = uuid.uuid4().hex
    fields = {"chat_id": str(chat_id), "caption": caption_html, "parse_mode": "HTML", "supports_streaming": "true"}
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    with open(path, "rb") as f:
        data = f.read()
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="video"; filename="{os.path.basename(path)}"\r\n'
                 f'Content-Type: video/mp4\r\n\r\n'.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendVideo"
    r = http.post(url, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                  body=b"".join(parts), timeout=120)
    return str(((r or {}).get("result") or {}).get("message_id", ""))


def send_tiktok_draft(s, kind, path, caption):
    import html
    cap = f"\U0001F3AC <b>TikTok to post</b> ({html.escape(kind)})\n\n<pre>{html.escape(caption)}</pre>"
    return send_video(s, s.x_drafts_chat, path, cap)
