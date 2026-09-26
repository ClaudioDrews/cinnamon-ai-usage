[Português do Brasil](README.pt-BR.md) | [English](README.md)

# AI usage for Cinnamon

Version 0.2.0. Local applet to check quotas, spend, and balances of AI services on Linux Mint Cinnamon.

- **Single click:** up to five services, first those with observed use and then those with the most recent reading (those without a reading don't take up a line).
- **Hover:** tooltip with per-service summary, collection time, and warnings.
- **Double click:** full window, with all available metrics.
- **See all services…:** visible alternative to double click.
- **Credentials…:** stores keys in the system keyring and points to credential files.
- **Update:** manual query. Automatic refresh uses 120 seconds by default.

The menu doesn't change order while open. The window uses the system GTK theme, has scrolling, and separates services without a reading.

Failure and stale reading appear named, separated from the quota: `Reading failed: Codex, Grok` in red in the menu and tooltip, and `Stale reading: Antigravity` without highlight — the robot color still responds only to the quota percentage, and the applet checks the **age** of the reading, not just the state: a quota from one hour ago doesn't color the icon even with collection paused. In the window, the stale reading warning says what happened — expired interval is different from a failed refresh.

The robot appears in the panel as a symbolic icon: in normal use it follows the theme color, turns **yellow from 70% used** and **red from 90%**, considering the highest percentage among all windows of all services with a valid reading. Balances and spend without a known cap don't trigger the color; stale readings are identified in the tooltip and excluded from the calculation. The SVG is at `assets/robot-head-symbolic.svg` (transparent background, `fill:currentColor`).

## Language

- The interface follows the session language; Preferences can pin a language or leave it on `auto`.
- A pinned language only takes effect when its catalog exists; without a catalog the interface answers in English.
- Changing the language does not discard a reading, does not force a collection and does not mark anything as stale.
- The strings live in `locale/`; `sh scripts/i18n.sh` rebuilds the catalog. Details in [docs/i18n.md](docs/i18n.md).

## State of the first version

Verified on 2026-09-25, Mint 22.3 / Cinnamon 6.6.9:

| Service | Reading implemented | Local verification |
|---|---|---|
| Codex | All windows returned by the app-server, with renewal | Authenticated query OK, two windows |
| OpenCode Go | Rolling, weekly, and monthly window | Authenticated query OK, three windows |
| Nous Portal | Total balance, plan balance, and recharges; plan renewal | Authenticated query OK via Hermes OAuth login |
| DeepSeek | Balance per currency | Authenticated query OK |
| OpenRouter | Monthly/cumulative spend; percentage if the key has a limit | Authenticated query OK; no cap on the key, no invented bar |
| Antigravity | Plan credits and per-model quotas, via local server | Authenticated query OK with IDE open: plan credits and named models |
| Grok / xAI | Prepaid balance from the management API | Authenticated query OK with management key and team_id; the Grok subscription doesn't appear here |
| Meta AI (Muse Code) | Current and weekly window of the subscription | Authenticated query responds; on 2026-09-26 the route returned the account metadata **without** the usage block, preserving the last reading. See the service section |
| Claude Code | 5 h and weekly window of the subscription (and per-model windows, when they come) | **Not verified**: no Anthropic account on this machine; route and format come from community public documentation |

The Grok connector monitors **the xAI API**, not the SuperGrok/Grok Build subscription. Those plans require another source. Antigravity and Go use interfaces that may change; changes are treated as unavailability, without turning absence of data into zero. The Meta connector reads the Muse Code **subscription** (current and weekly window), not the Meta API usage billing. The Claude Code connector is the only one published **without verification on a real account** — it's implemented, tested against the documented format, and labeled as unverified; its section explains what's missing and how to report.

[Preview of the window with fictional data](docs/demo.png)

## Run without installing

Requires Python 3, PyGObject/GTK3, and Cinnamon/CJS. On Debian/Ubuntu-derived distributions (Mint included):

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 librsvg2-common
```

`librsvg2-common` is what rasterizes the robot SVG in the window. Without it the window still opens, with a theme icon in its place and a warning in the icon tooltip. The system keyring is optional (`gir1.2-secret-1`, already present on Mint): without it, keys come from the indicated file or the environment. Node is only for JavaScript verification, not for running the applet. There are no pip/npm packages.

```bash
cd /path/to/repository
python3 backend/window.py --demo   # window with made-up data
python3 backend/window.py          # real usage/balance queries
python3 backend/credentials_window.py  # keys in the keyring and file paths
python3 backend/collector.py collect
python3 backend/collector.py read  # cache only, no network queries
python3 backend/collector.py worker <service>  # queries a single provider
python3 backend/collector.py diag <service>    # field names and ranges, no values
```

Demo doesn't read credentials or change the cache. Real collection doesn't do inference, purchases, recharges, or plan changes.

## Install for the user

```bash
python3 install.py
```

The installer copies the applet and backend to `~/.local/share/cinnamon/applets/ai-usage@claudio.drews/`. Keep the source code in this repository. A previous version is moved to `~/.local/share/cinnamon/ai-usage-backups/` before replacement.

Then open **System Settings → Applets → Manage**, look for **AI usage** and add it to the panel. The installer doesn't activate applets or restart Cinnamon. After an update, remove and add the applet to load the new version. Interval and pause preferences are in **Configure**, in the context menu.

To uninstall, first remove the applet from the panel and delete only the `ai-usage@claudio.drews` directory from the applets folder. Cache and preferences are separate and can be preserved.

## Credentials and settings

Cinnamon preferences don't store secrets. Each credential is searched in this order:

1. **System keyring** (Secret Service / gnome-keyring) — this is where the **Credentials…** window stores what the user types. The keyring applies to any of the accepted credential names and overrides the file and the environment, so saving a new key always replaces the one the collection was using. Nothing is displayed back: the window only says where the value would come from.
2. **File indicated by you** in `config.json`, in the `credentials_path` key, in `NAME=VALUE` format — any path (`~/.env`, `~/.config/secrets.env`, whatever you use). The file is read without a shell: `$(...)` and backticks stay literal. Without quotes, the value is exactly as written — `KEY=sk-abc#def` stores `sk-abc#def`, because `#` only starts a comment after a space. With quotes, shell rules apply, including escape (`KEY="with # inside"`, `KEY="double\"quote"`). A line without `=` or with unclosed quotes is ignored — and the credentials window lists which were ignored and why, so "not configured" never appears without a cause.
3. **Environment variables** of the process.

For services that authenticate by login, not by key, `token_files` points to a JSON; the first `access_token` found, at any level, is used (never copied to the cache).

Recognized variables: `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `OPENCODE_GO_API_KEY` (or `OPENCODE_API_KEY`), `XAI_MANAGEMENT_API_KEY` (xAI API balance; the inference key doesn't work) and `NOUS_PORTAL_TOKEN`.

### xAI key (Grok)

The balance is not in the inference key: it lives in the **Management API**, which requires a **management key** — a separate credential, created at `console.x.ai` → *Settings* → *Management Keys*. To create and use it, the account user needs the `Management Keys` **Read + Write** permission on the Console *Users* page; without it the item doesn't appear and the one who enables it is the team admin. The ACLs (`api-key:model`, `api-key:endpoint`) apply to inference keys and don't replace this permission.

The connector uses two pieces of data:

- `XAI_MANAGEMENT_KEY` (also accepted as `XAI_MANAGEMENT_API_KEY`) — the management key (Bearer). Set it via the applet's **Credentials…** button, which stores it in the system keyring.
- `XAI_TEAM_ID` in the credentials file itself, or `grok.team_id` in `~/.config/cinnamon-ai-usage/config.json`, or the corresponding field in the **Credentials…** window — the team identifier, visible in the Console URL (`console.x.ai/team/<team_id>/…`). The config value takes precedence.

Endpoints that matter for a panel:

| Use | Endpoint |
| --- | --- |
| Prepaid balance and changes (used today) | `GET /v1/billing/teams/{team_id}/prepaid/balance` |
| Check if the key is a valid management key (doesn't require ACL) | `GET /auth/management-keys/validation` |
| Period spend and current cap (gives real percentage) | `GET /v1/billing/teams/{team_id}/postpaid/invoice/preview` |
| Configured spend limits | `GET /v1/billing/teams/{team_id}/postpaid/spending-limits` |
| Usage by model and period | `POST /v1/billing/teams/{team_id}/usage` |

Base for all: `https://management-api.x.ai`. The balance comes in `total.val`, in cents, and **with the sign inverted**: xAI records the recharge as a negative value in the ledger and the total is the sum of changes, so the available credit is the absolute value of that total. The applet displays the available credit and records the convention in the service note.

When there's prepaid credit consumption, the service's second line shows the percentage used over the total recharged (the sum of recharges), because the key doesn't carry its own cap. While there's no consumption, only the balance appears — no invented zero bar.

The management key is a powerful credential: it creates and revokes API keys and messes with billing. Keep it in the keyring, not in a versioned file.

Codex uses the CLI's own login (`codex login`) at `~/.codex/auth.json`, Muse Code uses its own (`muse login`) at `~/.config/muse/auth.json`, and Claude Code uses the one from `claude /login` at `~/.claude/.credentials.json`; none of the three appears in the credentials window, because the file is found by the application's own default path. Antigravity is only probed on loopback and requires the IDE server running; don't confuse `ANTIGRAVITY_API_KEY` with the IDE login.

### Muse Code subscription (Meta)

Meta doesn't expose a quota reading route: neither `GET /muse-code/usage`, nor `used_percent` in the local file — the `/cost` panel lives only in the client's memory. What works is the call the client itself makes on startup, `POST https://api.meta.ai/muse-code/key`, with the OAuth token from `muse login`. It used to return `subs_usage` with the current window (`used_percent`, `window_duration_mins`, `resets_at` in epoch) and the weekly one — see the current status below.

**Status as of 2026-09-26 — the route stopped returning the usage block.** The 16:59:16Z reading brought both windows with percentages; the 17:17:48Z attempt, on the same route, returned only the account and subscription metadata (key, email, tier, subscription status — `is_subs_active` true, no payment required) and **no** `subs_usage`. The connector did what it should: marked the attempt as failed, preserved the previous reading, and showed it as a stale reading due to failure, instead of reusing it as a good reading. This is what the response showed; it's **not** proof that Meta changed the route — it could be a change on their side, some state the call now carries, or variation between calls. What separates the hypotheses is the `diag meta` report (below), which says which fields came and which expected ones were missing.

Two things you should know before enabling:

- The call **emits a credential**, not just reads. We verified on 2026-09-26 that it's **idempotent**: it returns exactly the same `api_key` the client already stores, without touching `auth.json`. Nothing was rotated and the CLI kept working.
- Even so, the applet queries at most every 15 minutes (`meta.min_interval_seconds`), keeps the last reading in a private cache, and shows its real time. Between queries the line appears as a stale reading, with the warning — it's intentional: we prefer identified old data to hammering a route without rate limit documentation. The interval counts the last **attempt**: after a failure (an HTTP 429, for example) the next query waits the interval instead of repeating the call; without a reading to reuse the service becomes `unavailable` with "Consultation deferred", and with a previous reading the line stays marked as failed, with that attempt's message — reusing the reading doesn't erase what happened, and only a new response brings the service back to `ok`.

The line shows the percentage of both windows. There's no dollar spend for this service: the models API doesn't publish prices, and inventing a denominator is exactly what this project avoids.

### Compatibility with Muse Code versions

Verified with Muse Code **1.4.0** (`1.4.0-R4161.1`) and `auth.json` at `schema_version` 1. The connector uses two things:

- The **login file**, searched in the same order the client itself resolves in its launcher: `token_files.meta` in the applet config, then `$MUSE_AUTH_PATH`, then `$XDG_CONFIG_HOME/muse/auth.json`, and without it, `~/.config/muse/auth.json`. It's enough to have an `access_token` at any level of the JSON — when the file started grouping by `providers.meta`, on 2026-09-26, the reading kept working without changes.
- The **route** `POST https://api.meta.ai/muse-code/key`, with `subs_usage.window` and `subs_usage.weekly`.

The connector doesn't run the Muse Code binary — it doesn't need it installed to read the file, nor running — so the installed CLI version doesn't change the applet's behavior. What depends on version is the file format and the route.

When Meta changes something, the expected behavior is to degrade and never invent: missing file or without token → `unconfigured` (the message asks for `muse login`); response without `subs_usage` → `unavailable`, with the last value preserved; network failure → `error`, with the previous value marked as stale reading. None of these cases becomes 0%, and none of them breaks the panel.

If the response comes without `subs_usage`, or with the percentages under a different name, report on GitHub with the output of:

```bash
python3 backend/collector.py diag meta
```

This report brings **field names, types, and number ranges**, plus the list of fields the connector looks for — saying which are missing, null, or of another type. No values, account identifiers, or paths from your machine. It's a path that really exists: `diag` responds for any service that failure messages suggest, and a test verifies this.

If you maintain more than one version of Muse Code with logins in different files, point to your current one in `token_files.meta` (see the configuration below).

### Claude Code subscription

The Claude Code subscription windows come from `GET https://api.anthropic.com/api/oauth/usage`, with `Authorization: Bearer <login token>` and `anthropic-beta: oauth-2025-04-20`. It's the same route the CLI uses in the `/usage` command and that CLI tracking projects documented; Anthropic doesn't publish it as an API, so it's treated as something that may change.

What the connector **doesn't** do, and why:

- **Doesn't make inference requests.** The draft that originated this connector asked for a response from `/v1/messages`, with `max_tokens: 1`, just to read the `anthropic-ratelimit-unified-*` headers. Each query would consume a bit of the quota the applet displays: in an applet that refreshes every two minutes, it would be the monitor eating what it monitors. The reading route returns both windows in JSON, without quota cost.
- **Doesn't renew or store credentials.** The Claude Code token lasts about an hour and the CLI itself renews it. With an expired token the service becomes `unconfigured` with the warning "run `claude` to renew" — the applet doesn't touch `refreshToken`.
- **Doesn't guess scale.** The percentage is used as-is, on the 0–100 scale: no multiplying by 100 when the value looks small, which would turn 0.4% into 40%.

In the line, `five_hour` (or `kind: session`) appears as **5 h window**, `seven_day` (or `weekly_all`) as **Week**, and `weekly_scoped` as **Week · {model}**. Unknown type entries are ignored — they never become zero — and without any recognized window the service becomes `unavailable`.

The route is queried at most every 5 minutes (`claude.min_interval_seconds`), with a private cache; between queries the line appears as a stale reading, with the real time — and, as with the Meta connector, a failed attempt also holds the interval and keeps the failure warning until the service responds again. The login file is searched in `token_files.claude`, then in `$CLAUDE_CONFIG_DIR/.credentials.json`, and finally in `~/.claude/.credentials.json` — the order published by Anthropic for those who run more than one account. On macOS the login is in the Keychain and isn't read from here.

This serves those who have a **Pro, Max, Team, or Enterprise** subscription: those who use only an API key don't have these windows, and the service appears without a reading.

**What hasn't been verified yet** — there's no Anthropic account on this machine:

- whether the route accepts `Bearer` with the login token (probing with an invalid token returned 401 and the body complained about `x-api-key`, which only a real token clarifies);
- whether the current `.credentials.json` keeps `claudeAiOauth.accessToken`, and whether the request needs another `anthropic-beta`;
- whether the percentage really comes in 0–100, the premise of the decision not to rescale.

If you have an account and the service doesn't show anything, report on GitHub with the output of:

```bash
python3 backend/collector.py diag claude
```

This report brings only **field names, types, number ranges**, and which windows the connector recognized: no values, no paths from your machine, and no piece of credential. It's what a PR needs to adjust the parser.

Optional **secret-free** configuration in `~/.config/cinnamon-ai-usage/config.json`:

```json
{
  "refresh_seconds": 120,
  "credentials_path": "~/.config/secrets.env",
  "token_files": {"nous": "~/.local/share/my-login/auth.json"},
  "enabled": {"grok": false},
  "grok": {"team_id": "YOUR_TEAM_ID"},
  "meta": {"min_interval_seconds": 900},
  "claude": {"min_interval_seconds": 300}
}
```

`token_files.meta` is only needed if the Muse Code login is outside the default path (`~/.config/muse/auth.json`). `token_files.claude` is only needed if the Claude Code login is outside `$CLAUDE_CONFIG_DIR` and `~/.claude/.credentials.json`.

The file write is atomic and in 0600 mode. The interval selected in the applet applies to your queries. The independent window uses the TTL from the file above (120 seconds if absent). The Update button forces collection in both — and, if a collection is already running, it warns that the refresh was ignored instead of showing failure: the displayed values remain the last read ones. Disabling a provider in the file removes it from the next collections; a change can wait for the TTL or Update.

The cache lives in `~/.cache/cinnamon-ai-usage/` (0700 directory, 0600 snapshot), with atomic write and a lock to prevent duplicate queries. It stores metrics and history, without tokens or raw responses. Private identification fields use SHA-256 digest to avoid comparing different accounts and are omitted from public output.

## What "recent" means

The first query creates the reference. Only a later change in consumption or balance assigns approximate recency. Refreshing the balance doesn't count as using the service. That's why the click opens with up to five lines: first those with observed use and, to complete, those with the most recent reading — each line says whether there's observed use. Services without any reading don't take up a menu line; they appear in the tooltip and in the window.

The order records **observed activity**, not the exact time of each call. Simultaneous collections can produce ties; uses outside this machine can also affect account consumption. Credit expiration can look like consumption, and a simultaneous recharge can hide it. We don't associate this time with a specific agent. Account or window changes restart the comparison. Failures preserve the last reading, marked as stale.

The DeepSeek and Nous balance doesn't become monthly consumption by division by a budget. Recharge and rollover credits need to be considered; in this version we display monetary values.

## Development and verification

```bash
python3 -m unittest discover -s tests -v
node --check applet/applet.js
node tests/test_applet.js
GI_TYPELIB_PATH=/usr/lib/x86_64-linux-gnu/cinnamon:/usr/lib/x86_64-linux-gnu/muffin \
LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/cinnamon:/usr/lib/x86_64-linux-gnu/muffin \
cjs tests/check_cjs_api.js
python3 -m compileall -q backend
python3 tests/smoke_gtk.py /tmp/ai-usage-demo.png  # requires a graphical session
```

The offline tests cover parsers, absence versus zero, renewal, recency, account change, failure preserving cache, and secret isolation. The JS test simulates the applet's environment to check clicks, timers, collection, and the five-item limit; it doesn't replace validation on the real panel. The GTK test opens and closes a demo window.

Architecture and format: [docs/contract.md](docs/contract.md). Evidence, sources, and limitations: [docs/validation.md](docs/validation.md).

To add a service: implement the connector in `backend/providers.py` following the contract rules — read-only, no inference, no credential renewal, and degrading instead of inventing zero; register the id in `SERVICES`; cover the parser with fixtures in `tests/test_backend.py`; and say in the README what was verified and what wasn't. A PR is much easier to accept with the secret-free output of `python3 backend/collector.py worker <service>` (or `diag <service>`, when it exists) in the body.

Project reference: [omarchy-ai-usage](https://github.com/rodrigo-sntg/omarchy-ai-usage), by Rodrigo Santiago, MIT license. This implementation uses its own contract to preserve distinct windows and models.
