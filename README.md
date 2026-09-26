[Português do Brasil](README.pt-BR.md) | [English](README.md)

# AI usage for Cinnamon

Version 0.2.0. Local applet to consult quotas, spend and balances of AI services on Linux Mint Cinnamon.

- **Single click:** up to five services, first the ones with observed usage and then the ones with the most recent reading (a service without a reading takes no row).
- **Hover:** tooltip with a summary per service, the collection time and warnings.
- **Double click:** the full window, with every available metric.
- **See all services…:** a visible alternative to the double click.
- **Credentials…:** keeps keys in the system keyring and points to credentials files.
- **Update:** manual query. The automatic refresh uses 120 seconds by default.

The menu does not change order while it is open. The window uses the system GTK theme, scrolls and separates the services without a reading.

Failure and a stale reading appear named, separated from the quota: `Reading failed: Codex, Grok` in red in the menu and in the tooltip, and `Stale reading: Antigravity` without highlight — the robot colour still answers only to the quota percentage, and the applet checks the **age** of the reading, not only the state: a quota from an hour ago does not colour the icon even with the collection paused. In the window, the stale-reading warning says what happened — an expired interval is different from a refresh that failed.

The robot appears in the panel as a symbolic icon: in normal use it follows the theme colour, turns **yellow from 70% used** and **red from 90%**, considering the highest percentage across all the windows of all the services with a valid reading. Balances and spend without a known cap do not trigger the colour; stale readings are identified in the tooltip and excluded from the calculation. The SVG is in `assets/robot-head-symbolic.svg` (transparent background, `fill:currentColor`).

## Language

- The interface follows the session language; Preferences can pin a language or leave it on `auto`.
- A pinned language only takes effect when its catalog exists; without a catalog the interface answers in English.
- Changing the language does not discard a reading, does not force a collection and does not mark anything as stale.
- The strings live in `locale/`; `sh scripts/i18n.sh` rebuilds the catalog. Details in [docs/i18n.md](docs/i18n.md).

## State of the first version

Verified on 2026-09-25, Mint 22.3 / Cinnamon 6.6.9:

| Service | Reading implemented | Local verification |
|---|---|---|
| Codex | Every window returned by the app-server, with renewal | Authenticated query OK, two windows |
| OpenCode Go | Rolling, weekly and monthly window | Authenticated query OK, three windows |
| Nous Portal | Total balance, plan balance and top-ups; plan renewal | Authenticated query OK via the Hermes OAuth login |
| DeepSeek | Balance per currency | Authenticated query OK |
| OpenRouter | Monthly/cumulative spend; percentage if the key has a limit | Authenticated query OK; no cap on the key, no invented bar |
| Antigravity | Plan credits and quotas per model, via the local server | Authenticated query OK with the IDE open: plan credits and named models |
| Grok / xAI | Prepaid balance of the management API | Authenticated query OK with the management key and team_id; the Grok subscription does not appear here |
| Meta AI (Muse Code) | Current and weekly window of the subscription | Authenticated query answers; on 2026-09-26 the route returned the account metadata **without** the usage block, preserving the last reading. See the service section |
| Claude Code | 5 h and weekly window of the subscription (and per-model windows, when they come) | **Not verified**: no Anthropic account on this machine; the route and the format come from the public documentation of the community |

The Grok connector monitors **the xAI API**, not the SuperGrok/Grok Build subscription. Those plans require another source. Antigravity and Go use interfaces that may change; changes are treated as unavailability, without turning the absence of data into zero. The Meta connector reads the Muse Code **subscription** (current and weekly window), not Meta's API usage billing. The Claude Code connector is the only one published **without verification on a real account** — it is implemented, tested against the documented format and labelled as not verified; its section explains what is missing and how to report.

[Preview of the window with fictional data](docs/demo.png)

## Run without installing

Requires Python 3, PyGObject/GTK3 and Cinnamon/CJS. On Debian/Ubuntu-derived distributions (Mint included):

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 librsvg2-common
```

`librsvg2-common` is what rasterises the robot SVG in the window. Without it the window still opens, with a theme icon in its place and a warning in the icon tooltip. The system keyring is optional (`gir1.2-secret-1`, already present on Mint): without it, the keys come from the indicated file or from the environment. Node serves only the JavaScript verification, not the execution of the applet. There are no pip/npm packages.

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

The demo reads no credentials and does not change the cache. The real collection does no inference, purchases, top-ups or plan changes.

## Install for the user

```bash
python3 install.py
```

The installer copies the applet and the backend to `~/.local/share/cinnamon/applets/ai-usage@claudio.drews/`. Keep the source code in this repository. A previous version is moved to `~/.local/share/cinnamon/ai-usage-backups/` before the replacement.

Then open **System Settings → Applets → Manage**, look for **AI usage** and add it to the panel. The installer does not enable applets or restart Cinnamon. After an update, remove and add the applet to load the new version. Interval and pause preferences are in **Configure**, in the context menu.

To uninstall, first remove the applet from the panel and delete only the `ai-usage@claudio.drews` directory from the applets folder. Cache and preferences are separate and can be preserved.

## Credentials and settings

Cinnamon preferences do not keep secrets. Each credential is looked up in this order:

1. **System keyring** (Secret Service / gnome-keyring) — it is where the **Credentials…** window writes what the person types. The keyring counts for any of the accepted names of the credential and beats the file and the environment, so that saving a new key always replaces the one the collection had been using. Nothing is displayed back: the window only states where the value would come from.
2. **A file indicated by you** in `config.json`, under the key `credentials_path`, in the `NAME=VALUE` format — any path (`~/.env`, `~/.config/secrets.env`, whatever you use). The file is read without a shell: `$(...)` and backticks stay literal. Without quotes, the value counts exactly as written — `KEY=sk-abc#def` keeps `sk-abc#def`, because `#` only starts a comment after a space. With quotes, the shell rules apply, escape included (`KEY="with # inside"`, `KEY="double\"quote"`). A line without `=` or with unterminated quotes is ignored — and the credentials window lists which ones were ignored and why, so that “not configured” never appears without a cause.
3. **Environment variables** of the process.

For services that authenticate by login, and not by key, `token_files` points to a JSON; the first `access_token` found, at any level, is used (never copied to the cache).

Recognized variables: `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `OPENCODE_GO_API_KEY` (or `OPENCODE_API_KEY`), `XAI_MANAGEMENT_API_KEY` (xAI API balance; the inference key does not work) and `NOUS_PORTAL_TOKEN`.

### xAI key (Grok)

The balance is not in the inference key: it lives in the **Management API**, which requires a **management key** — a separate credential, created at `console.x.ai` → *Settings* → *Management Keys*. To create and use it, the account user needs the `Management Keys` permission with **Read + Write** on the *Users* page of the Console; without it the item does not appear, and the one who enables it is the team administrator. The ACLs (`api-key:model`, `api-key:endpoint`) apply to the inference keys and do not replace that permission.

The connector uses two pieces of data:

- `XAI_MANAGEMENT_KEY` (also accepted as `XAI_MANAGEMENT_API_KEY`) — the management key (Bearer). Set it through the applet's **Credentials…** button, which writes to the system keyring.
- `XAI_TEAM_ID` in the credentials file itself, or `grok.team_id` in `~/.config/cinnamon-ai-usage/config.json`, or the corresponding field in the **Credentials…** window — the team identifier, visible in the Console URL (`console.x.ai/team/<team_id>/…`). The value from the configuration takes precedence.

Endpoints that matter for a panel:

| Use | Endpoint |
| --- | --- |
| Prepaid balance and changes (used today) | `GET /v1/billing/teams/{team_id}/prepaid/balance` |
| Check whether the key is a valid management key (does not require ACL) | `GET /auth/management-keys/validation` |
| Spend of the period and the cap in force (gives a real percentage) | `GET /v1/billing/teams/{team_id}/postpaid/invoice/preview` |
| Configured spending limits | `GET /v1/billing/teams/{team_id}/postpaid/spending-limits` |
| Usage per model and period | `POST /v1/billing/teams/{team_id}/usage` |

Base for all of them: `https://management-api.x.ai`. The balance comes in `total.val`, in cents, and **with the sign inverted**: xAI records a top-up as a negative value in the ledger and the total is the sum of the changes, so that the available credit is the absolute value of that total. The applet displays the available credit and records the convention in the service note.

When there is prepaid credit consumption, the second line of the service shows the percentage used over the total topped up (the sum of the top-ups), because the key brings no cap of its own. While there is no consumption, only the balance appears — no invented bar at zero.

The management key is a powerful credential: it creates and revokes API keys and touches billing. Keep it in the keyring, not in a versioned file.

Codex uses the login of its own CLI (`codex login`) in `~/.codex/auth.json`, Muse Code uses its own (`muse login`) in `~/.config/muse/auth.json` and Claude Code uses the one from `claude /login` in `~/.claude/.credentials.json`; none of the three appears in the credentials window, because the file is found by the default path of the application itself. Antigravity is probed only on loopback and requires the IDE server to be running; do not confuse `ANTIGRAVITY_API_KEY` with the IDE login.

### Muse Code subscription (Meta)

Meta does not expose a quota-reading route: neither `GET /muse-code/usage`, nor `used_percent` in the local file — the `/cost` panel lives only in the memory of the client. What works is the call the client itself makes when it starts up, `POST https://api.meta.ai/muse-code/key`, with the OAuth token from `muse login`. It used to return `subs_usage` with the current window (`used_percent`, `window_duration_mins`, `resets_at` in epoch) and the weekly one — see the current state just below.

**State on 2026-09-26 — the route stopped returning the usage block.** The reading at 16:59:16Z brought the two windows with percentages; the attempt at 17:17:48Z, on the same route, returned only the account and subscription metadata (key, e-mail, tier, subscription situation — `is_subs_active` true, with no payment requirement) and **no** `subs_usage`. The connector did what it should: it marked the attempt as a failure, preserved the previous reading and showed it as a stale reading due to failure, instead of reusing it as a good reading. This is what the response showed; it is **not** proof that Meta changed the route — it may be a change on their side, some state the call now carries, or variation between calls. What separates the hypotheses is the report of `diag meta` (below), which says which fields came and which of the expected ones were missing.

Two things you should know before enabling it:

- The call **issues a credential**, and does not only read. We verified on 2026-09-26 that it is **idempotent**: it returns exactly the same `api_key` that the client already keeps, without touching `auth.json`. Nothing was rotated and the CLI kept working.
- Even so the applet queries at most every 15 minutes (`meta.min_interval_seconds`), keeps the last reading in a private cache and shows its real time. Between one query and the next the row appears as a stale reading, with the warning — this is intentional: we prefer an old datum that is identified to hammering a route without documented limits. The interval counts the last **attempt**: after a failure (an HTTP 429, for example) the next query waits for the interval instead of repeating the call; without a reading to reuse, the service becomes `unavailable` with "Consultation deferred", and with a previous reading the row stays marked as a failure, with the message of that attempt — reusing the reading does not erase what happened, and only a new response brings the service back to `ok`.

The row shows the percentage of the two windows. There is no dollar spend for this service: the model API does not publish prices, and inventing a denominator is exactly what this project avoids.

### Compatibility with Muse Code versions

Verified with Muse Code **1.4.0** (`1.4.0-R4161.1`) and `auth.json` at `schema_version` 1. The connector uses two things:

- The **login file**, looked up in the same order the client itself resolves it in its launcher: `token_files.meta` in the applet configuration, then `$MUSE_AUTH_PATH`, then `$XDG_CONFIG_HOME/muse/auth.json` and, without it, `~/.config/muse/auth.json`. It is enough for an `access_token` to exist at any level of the JSON — when the file started grouping by `providers.meta`, on 2026-09-26, the reading kept working without changes.
- The **route** `POST https://api.meta.ai/muse-code/key`, with `subs_usage.window` and `subs_usage.weekly`.

The connector does not run the Muse Code binary — it does not need it installed to read the file, nor running —, so the version of the installed CLI does not change the behaviour of the applet. What depends on the version is the format of the file and the route.

When Meta changes something, the expectation is to degrade and never to invent: missing file or file without a token → `unconfigured` (the message asks for `muse login`); response without `subs_usage` → `unavailable`, with the last value preserved; network failure → `error`, with the previous value marked as a stale reading. None of those cases becomes 0%, and none of them breaks the panel.

If the response comes without `subs_usage`, or with the percentages under another name, report it on GitHub with the output of:

```bash
python3 backend/collector.py diag meta
```

That report brings **field names, types and the range of the numbers**, plus the list of the fields the connector looks for — saying which ones are absent, null or of another type. No value, no account identifier and no path of your machine. It is a path that really exists: `diag` answers for any service that the failure messages suggest, and a test checks that.

If you keep more than one version of Muse Code with logins in different files, point the one of your current use in `token_files.meta` (see the configuration below).

### Claude Code subscription

The windows of the Claude Code subscription come from `GET https://api.anthropic.com/api/oauth/usage`, with `Authorization: Bearer <login token>` and `anthropic-beta: oauth-2025-04-20`. It is the same route the CLI uses in the `/usage` command and that the CLI tracking projects documented; Anthropic does not publish it as an API, so it is treated as something that may change.

What the connector does **not** do, and why:

- **It makes no inference request.** The draft that originated this connector asked for a response at `/v1/messages`, with `max_tokens: 1`, only to read the `anthropic-ratelimit-unified-*` headers. Each query would consume a little of the quota the applet displays: in an applet that refreshes every two minutes, that would be the monitor eating what it monitors. The reading route returns the two windows in JSON, with no quota cost.
- **It does not renew or write a credential.** The Claude Code token is worth about an hour and it is the CLI itself that renews it. With an expired token the service stays at `unconfigured` with the warning "run `claude` to renew" — the applet does not touch the `refreshToken`.
- **It does not guess the scale.** The percentage is used as it came, on the 0–100 scale: no multiplying by 100 when the value looks small, which would turn 0.4% into 40%.

On the row, `five_hour` (or `kind: session`) appears as **5 h window**, `seven_day` (or `weekly_all`) as **Week** and `weekly_scoped` as **Week · {model}**. An entry of an unknown type is ignored — it never becomes zero —, and without any recognized window the service stays at `unavailable`.

The route is queried at most every 5 minutes (`claude.min_interval_seconds`), with a private cache; between one query and the next the row appears as a stale reading, with the real time — and, as in the Meta connector, an attempt that failed also holds the interval and keeps the failure warning until the service answers again. The login file is looked up in `token_files.claude`, then in `$CLAUDE_CONFIG_DIR/.credentials.json` and finally in `~/.claude/.credentials.json` — the order published by Anthropic for those who run more than one account. On macOS the login lives in the Keychain and is not read from here.

This serves those who have a **Pro, Max, Team or Enterprise** subscription: those who use only an API key do not have these windows, and the service appears without a reading.

**What has not been verified yet** — there is no Anthropic account on this machine:

- whether the route accepts `Bearer` with the login token (the probe with an invalid token returned 401 and the body complained about `x-api-key`, which only a real token clarifies);
- whether the current `.credentials.json` keeps `claudeAiOauth.accessToken`, and whether the request needs another `anthropic-beta`;
- whether the percentage really comes on 0–100, the premise of the decision not to rescale.

If you have an account and the service shows nothing, report it on GitHub with the output of:

```bash
python3 backend/collector.py diag claude
```

That report brings only **field names, types, the range of the numbers** and which windows the connector recognized: no value, no path of your machine and no piece of credential. It is what a PR needs to adjust the parser.

Optional configuration **without secrets** in `~/.config/cinnamon-ai-usage/config.json`:

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

The writing of the file is atomic and in mode 0600. The interval selected in the applet counts for its queries. The standalone window uses the TTL of the file above (120 seconds if absent). The Update button forces the collection in both — and, if there is already a collection in progress, it warns that the refresh was skipped instead of showing a failure: the displayed values remain the last ones read. Disabling a provider in the file removes it from the next collections; a change may wait for the TTL or for Update.

The cache lives in `~/.cache/cinnamon-ai-usage/` (directory 0700, snapshot 0600), with atomic writing and a lock to prevent duplicate queries. It keeps metrics and history, without tokens or raw responses. Private identification fields use a SHA-256 digest to avoid comparing different accounts and are omitted from the public output.

## What “recent” means

The first query creates the reference. Only a later change of consumption or balance assigns an approximate recency. Refreshing the balance does not count as using the service. That is why the click opens with up to five rows: first the ones with observed usage and, to complete, the ones with the most recent reading — each row says whether there is observed usage. Services without any reading take no menu row; they appear in the tooltip and in the window.

The order records **observed activity**, not the exact time of each call. Simultaneous collections may produce ties; uses outside this machine may also affect the consumption of the account. Expiry of credits may look like consumption, and a simultaneous top-up may hide it. We do not associate that time with a specific agent. Changes of account or of window restart the comparison. Failures preserve the last reading, marked as stale.

The balance of DeepSeek and Nous does not become monthly consumption by division by a budget. Top-up credits and rollover need to be considered; in this version we display monetary values.

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

The offline tests cover parsers, absence versus zero, renewal, recency, account switching, failure preserving the cache and isolation of secrets. The JS test simulates the applet environment to check clicks, timers, collection and the limit of five; it does not replace the validation on the real panel. The GTK test opens and closes a demo window.

Architecture and format: [docs/contract.md](docs/contract.md). Evidence, sources and limitations: [docs/validation.md](docs/validation.md).

To add a service: implement the connector in `backend/providers.py` according to the contract rules — read-only, without inference, without renewing a credential and degrading instead of inventing zero; register the id in `SERVICES`; cover the parser with fixtures in `tests/test_backend.py`; and say in the README what was verified and what was not. A PR is far easier to accept with the secret-free output of `python3 backend/collector.py worker <serviço>` (or `diag <serviço>`, when it exists) in the body.

Project reference: [omarchy-ai-usage](https://github.com/rodrigo-sntg/omarchy-ai-usage), by Rodrigo Santiago, MIT license. This implementation uses its own contract to preserve distinct windows and models.
