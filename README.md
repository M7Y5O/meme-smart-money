# Meme Smart Money bot

Watches the wallets of top Fomo traders on Solana and posts automatically to **@MemeSmartMoney** (X) and your **Telegram channel**:

| Post | When | Where |
|---|---|---|
| Smart-money cluster alert | When 3+ tracked wallets buy the same coin within 6h | X + Telegram |
| Daily recap (top coins bought in 24h) | Every day at 9am ET | X + Telegram |
| Weekly "what smart money bought most" | Sundays 10am ET | X + Telegram |
| Weekly top Fomo traders by PnL (needs the Fomo API) | Sundays 10am ET | X + Telegram |

Safety built in: dry-run mode, no alert on coins with under $25K liquidity, max 8 X posts per day, never the same alert twice in 24h, no alerts on old trades after a restart, "Not financial advice" on every post. The Fomo referral link only appears on Telegram (with an affiliate disclosure), never on X.

No dependencies: Python 3.10+ standard library only.

---

## 1. Which traders to track

**Option A: Fomo API (recommended, refreshed daily).** Fill the `FOMO_*` lines in `.env`. Check the mapping with:

```bash
python3 -m msm traders   # should print rank, name, wallet address and PnL for each trader
```

If names or wallets come back empty, adjust `FOMO_ITEMS_PATH` / `FOMO_FIELD_*` to match the response (dot paths, e.g. `data.traders` and `user.username`).

**Option B: fixed list.** Used when `FOMO_LEADERBOARD_URL` is empty, and as a fallback if the API is down.

1. In the Fomo app, open the profile of each top trader you want to track (start with 10–20).
2. Copy their Solana wallet address.
3. Copy `wallets.example.json` to `wallets.json` and fill in one line per trader.

Only Solana wallets are supported in this version.

## 2. Get the keys

- **Helius** (wallet data): sign up at dashboard.helius.dev and copy the API key. Watch your usage in the dashboard. If you run low, track fewer wallets or raise `POLL_SECONDS`.
- **X** (posting): log into developer.x.com **as @MemeSmartMoney**, create a project and app, set app permissions to **Read and write**, then generate the API key/secret and access token/secret. Posting needs an API plan that allows writes. Check X's current plans and limits, and set `MAX_X_POSTS_PER_DAY` to stay under yours.
- **Telegram**: message @BotFather, run `/newbot`, copy the token. Add the bot as an **admin** of your channel. `TELEGRAM_CHANNEL` is `@yourchannel`.

Copy `.env.example` to `.env` and paste the keys in. **Never commit `.env`** (it's already in `.gitignore`).

## 3. Mark the account as automated on X

On @MemeSmartMoney: Settings > Your account > Account information > **Automation**, then set @M7Y50 as the managing account. X requires this for bot accounts, and it shows the "Automated" label.

## 4. Test locally (on your Mac)

```bash
cd meme-smart-money
python3 -m unittest -v tests.test_bot   # logic tests
python3 -m msm test-telegram            # sends a test message to your channel
python3 -m msm once                     # one poll, DRY_RUN prints posts instead of sending
python3 -m msm recap                    # prints today's recap (dry run)
```

When the printed posts look right, set `DRY_RUN=false` in `.env`.

## 5. Run it for free on GitHub Actions (no card needed)

GitHub runs the bot every 10 minutes (`.github/workflows/bot.yml`) and keeps its memory between runs. It's free for **public** repos. Your keys stay hidden in GitHub Secrets; only the code is public.

1. In GitHub Desktop: File > Add local repository > `development/meme-smart-money` (create the repository if asked), then **Publish repository** with "Keep this code private" **unticked**.
2. On github.com, open the repo > **Settings > Secrets and variables > Actions**.
   - **Secrets** tab, add: `HELIUS_API_KEY`, `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`, `TELEGRAM_BOT_TOKEN`, `FOMO_API_KEY`
   - **Variables** tab, add: `TELEGRAM_CHANNEL`, `FOMO_REF_LINK`, `FOMO_LEADERBOARD_URL` and any `FOMO_*` mapping fields, `DRY_RUN` = `true`
3. **Actions** tab: enable workflows if asked, open "Smart Money bot" and click **Run workflow**. Open the run to read the log.
4. When the dry-run posts in the log look right, change the `DRY_RUN` variable to `false`.

Good to know:
- Runs can start a few minutes late when GitHub is busy, so alerts aren't instant.
- GitHub pauses scheduled workflows in public repos after 60 days with no commits. Push any small change (or click "Enable workflow") to keep it going.
- The first run only reads history and posts nothing; alerts start from the next runs.

**Alternative:** `deploy/install.sh` installs it as an always-on service on any Debian/Ubuntu server, and the `Dockerfile` works on paid hosts.

## Commands

```
python3 -m msm run            # run forever
python3 -m msm once           # one poll + cluster check
python3 -m msm tick           # one full cycle (what GitHub Actions runs)
python3 -m msm recap          # publish the daily recap now
python3 -m msm weekly         # publish the weekly post now
python3 -m msm test-telegram  # Telegram test message
python3 -m msm test-x         # PUBLIC test tweet
python3 -m msm traders        # print today's top traders from the Fomo API
```

## Notes and limits

- "Market cap when first spotted" is measured when the bot first sees a tracked wallet buy the coin, so it's within a few minutes of the real first buy.
- Trader names in Telegram alerts come from your `wallets.json` labels.
- The PnL leaderboard uses the PnL reported by the Fomo API. Set `PNL_PERIOD_LABEL` only if you know the period it covers.
- Upgrade path: switch from polling to Helius webhooks for instant alerts and lower API usage.
