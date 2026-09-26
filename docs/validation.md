# Validation of version 0.2.0 — 25 and 26/09/2026

## Current state — 26/09/2026

What the panel showed at the end of the round, connector by connector. The sections below keep
the chronological record, with the numbers of each moment; where they disagree with this table,
this table is what holds.

| Connector | Today | What the reading rests on |
|---|---|---|
| Codex | reading OK | `codex app-server`, two quota windows |
| OpenCode Go | reading OK | the application key, three windows from `usage.rolling/weekly/monthly` |
| Nous | reading OK | the OAuth token of the Hermes login, three balances |
| DeepSeek | reading OK | balance |
| OpenRouter | reading OK | monthly spend; with no cap on the key, no percentage is invented |
| Grok / xAI | reading OK | management key and `team_id`; prepaid balance of the Management API. The Grok subscription is not read here — that plan needs another source |
| Meta / Muse Code | reading OK, with reuse between calls | current and weekly window of the subscription; the route is the one that issues the Muse Code credential, queried at most every 15 minutes, and a failed attempt keeps the previous reading as stale |
| Claude Code | no reading on this machine | there is no Anthropic account here. Route, headers, credential field and the 0–100 scale of the response match an independent published implementation (the applet `claude-usage@mtwebster`, accepted in Spices), but none of that was measured on a real account from this machine: the connector stays labeled unverified |
| Antigravity | reading OK while the IDE is open | local server of the IDE, probed on loopback. With the IDE closed the line shows a stale reading — expected, and not a failure of the applet |

The `Result` block below is the record of the first day of the round: it reports Antigravity
without a validated query and Grok without a management key, both true on 25/09 and both
superseded by the table above.

## Result

Local implementation on Linux Mint 22.3, Cinnamon 6.6.9, Python 3.12 and CJS 115.1. Real data was consulted only for reading usage/balance. This document contains no percentages, balances, renewal times, paths of this machine or agent session identifiers: the numbers cited are from tests, from interface thresholds or from the shape of the response. No credential enters the repository, the cache, the log or the interface — credential reading only returns the value to the service call.

- **Codex:** the app-server returned two quota metrics.
- **OpenCode Go:** the available key returned three metrics per `usage.rolling/weekly/monthly`, with `percent` and `resetsAt`. The first probe without the application's User-Agent received HTTP 403; the collector's queries passed. A Zen label in the inventory did not demonstrate the absence of Go.
- **Nous:** `GET /api/oauth/account` with the OAuth existing in Hermes returned three balances. The `paid_service_access` field supplies the values; the plan renewal comes from `subscription.current_period_end`. No scope grant, purchase or token renewal was made by the applet.
- **DeepSeek:** valid balance reading.
- **OpenRouter:** valid monthly/cumulative spend reading; with no cap on the key, no percentage bar is invented.
- **Antigravity:** IDE server absent in this session; connector and parser implemented, real query not yet validated.
- **Grok/xAI:** management key not available. Connector conditioned on `XAI_MANAGEMENT_API_KEY` and `grok.team_id`; it does not amount to monitoring the subscription of the Grok application.

## Checks

- 24 offline Python tests: formats of the five providers, Antigravity parser, absence/zero, limits, rollover, recency, account/window change, failures and private cache.
- Syntax of the Python and JavaScript modules.
- Applet JS test: construction, Gio arguments, tuple return, single/double click, limit of five, stable ordering while open, error preserving the reading and timer cleanup.
- Real CJS: St properties and methods used by the applet and asynchronous capture of Gio.Subprocess checked.
- Real GTK: demo window, seven services rendered, asynchronous query finished, widgets visible and clean shutdown.
- Installation into a temporary directory: first installation, execution of the installed backend and update preserving the previous copy.

The JS test uses substitutes for the APIs to exercise behavior. A previous attempt to create an isolated Clutter stage failed with Unknown input backend in the Muffin fork. The integrated validation below was done later inside the real Cinnamon process.

## Test in the real panel

On 25/09/2026, at the user's request, we installed and enabled `ai-usage@claudio.local` in the panel. The previous configuration was saved to `~/.local/share/cinnamon/ai-usage-backups/panel-before-20260925-190727.json`; the activation added only the new instance and advanced the next identifier.

- Loading confirmed by Cinnamon and five sources with status OK in the panel instance; Antigravity unavailable and Grok without configuration.
- Mouse events via XTest on the icon: a single click opens/closes the menu; a double click opens the GTK window; another double click keeps a single window.
- A menu with seven synthetic services identified as demo showed only the five most recent. Visual capture and measurements of the actors confirmed the bars; the real snapshot was restored immediately, without writing the demo to the cache.
- Two observed problems fixed: an empty style generated warnings from the St parser (removed with `null`); the requested width of 290 pixels could be enlarged by the theme, distorting the proportion. The fill now follows the allocated width. Bars of 25%, 33%, 41% and 57% stayed within 0,5 percentage point, including pixel rounding.
- Only the applet was reloaded, without restarting Cinnamon. No new applet warning appeared in the log after the fixes. The JS test includes a regression for the width enlarged by the theme; 24 Python tests kept passing.

The applet remains enabled for use. The real menu starts empty until it detects a change of consumption between collections; the full window already shows the available data. Images with real data were not incorporated into the repository.

## Feedback: tooltip and robot icon

On 25/09/2026, the PNG provided by the user was incorporated unchanged into `assets/robot-head.png`. The installer includes the asset; panel, window icon and GTK header use the same image. The alert remains a yellow outline (70% used) or red (90%), without replacing the robot. It considers all valid quotas, excluding stale readings and monetary values without a percentage.

The native tooltip now presents the summary of each service, the collection time, the update state and the quota responsible for the alert. Real pointer entry, simulated by XTest, confirmed the tooltip visible without a click. A first probe that did not guarantee pointer exit/entry did not find it visible; the check with explicit entry passed. Visual capture confirmed the summary and the robot in the panel; the real image was discarded after checking.

The JS test covers the 70/90% thresholds, a quota outside the recent history, exclusion of a stale reading from the alert and balance presentation. The 24 Python tests pass. GTK smoke confirmed the icon loaded, the header visible and a clean shutdown. Update installed and reloaded only in the applet, keeping the position chosen by the user.

## Second round — credentials, five rows and symbolic icon

On 25/09/2026, from the user's feedback, five changes were implemented and verified on the real machine.

- **One-click menu:** up to five rows, first those with observed usage and then those with the most recent reading; a service without a reading takes no row. In the real panel, the menu opened with DeepSeek, Codex, Antigravity, Nous Portal and OpenCode Go (OpenRouter outside the cut), each quota row with its bar and the rows without observed usage identified; Grok appeared in the notice “1 serviço(s) sem leitura” and the actions Ver todos/Atualizar/Credenciais…/Configurações… (both the notice and the action names are Portuguese interface text, as shown at the time) stayed in the footer. Text checked by reading the menu actors and by screenshot.
- **Nous without duplication:** when the total balance and the plan balance coincide, one row remains; the renewal one and the top-up one (if different from zero) remain.
- **Credentials:** `backend/credentials.py` resolves in the order system keyring (Secret Service) → `NOME=VALOR` file indicated in `config.json:credentials_path` → environment variables, plus `token_files` for OAuth login in JSON. `backend/credentials_window.py` writes to the keyring, shows the origin of each value, clears the field after saving, allows removing and allows choosing any path. No credential path of a specific machine was left in the repository; the local configuration of this machine only points to paths. Verified: keyring available, `set`/`get`/`names`/`delete` in separate processes; window built with five fields, correct origin states and writing of `config.json` in mode 0600 in a temporary directory.
- **Antigravity:** the parser started reading the plan credits (`monthlyPromptCredits`/`availablePromptCredits` and the flow equivalent) and the real name of each model in `label`, ignoring entries without a valid fraction. A real query with the IDE open returned the plan credits and the named models; the semantic deviation of the reference project (model families treated as five-hour/seven-day windows) was not copied.
- **Icon:** `assets/robot-head-symbolic.svg` replaced the PNG (removed); the applet uses `set_applet_icon_symbolic_path`, without a border, and the alert color is applied on the icon itself. Three states checked by exact pixel counting in the panel strip: 450 pixels `#e01b24` with the Antigravity quota above the critical threshold, 369 pixels `#e5a50a` with a 75% quota injected only in memory (real snapshot restored right afterwards, without writing to the cache) and 423 pixels `#e1e1e1`, the theme's foreground color, when no quota reached the threshold. The icon's theme node resolves `color` to (224, 27, 36) in the critical state, confirming that the symbolic icon is recolored by the CSS.

Checks of this round: 29 offline Python tests, applet JS test (limit of five including the fill by recent reading, exclusion of a service without a reading, priority of observed usage, menu actions including Credenciais…), `node --check`, `compileall`, real CJS with the St/Gio APIs, installation into a temporary directory with execution of the installed backend, real query of the seven providers and reload of only the applet in the panel without restarting Cinnamon and without new warnings in the log.

A fix found in the check itself: with no alert, `_paintIcon` passed an empty string to the icon's `set_style` and the St parser logged two `cr_parser_new_from_buf`. The style is now `null` in that case; the warning count in the log before and after stayed the same (6), including in the state without alert, and the JS test now requires `null` instead of an empty string.

The panel inspection apparatus deserves a record: `imports.ui.appletManager.applets[uuid]` is the namespace of the applet directory, not the list of instances; the live instance was located by walking the panel boxes and reading `_delegate._uuid`. The color applied by `set_style` shows up in `get_theme_node().get_color('color')` and in the panel pixels.

## Full panel: the xAI key came in

With the management key and the `team_id` placed by the user in this machine's credentials file, the seven services came to have a reading — Grok included, which was the only hole. Adjustments made the same day:

- The connector accepts `XAI_MANAGEMENT_KEY` as an equivalent name of `XAI_MANAGEMENT_API_KEY`, and reads the team from `XAI_TEAM_ID` in the credentials file when there is no `grok.team_id` in the configuration. `team_id` is still validated against `[A-Za-z0-9_-]{1,100}` before entering the URL. The credentials window always writes the backend's preferred name, and the keyring takes precedence over file and environment **in any of the names** — before, a freshly saved key under the alternative name could lose to an old credential from the file.
- The sign of `total.val` stopped being an uncertainty: xAI records the top-up as a negative value in the ledger and the total is the sum of the changes, so that the available credit is the modulus of that total. The applet started displaying the available credit and recording the convention in the service note.
- With consumption, the second metric shows the percentage over the topped-up credits (sum of the top-ups), which is the only honest denominator of the key; with no consumption, no bar at zero. An account without postpaid returns `effectiveSpendingLimit` 0 and no billing row: the connector then shows only the prepaid credits.
- The credentials window gained the non-secret field of the `team_id` and recognizes the alternative name of the key when showing the origin of the value.

Verified: 35 Python tests, `compileall`, GTK smoke of the credentials window (five key fields, origin of each value, `team_id` read from the file, 0600 write in a temporary directory), real query of the seven providers by the collector and panel menu with Grok/xAI among the five rows, without a new warning in the log. Antigravity appears as a stale reading because the IDE server was not up at the moment of the collection.

## Eighth source: the Muse Code subscription (Meta)

On 26/09/2026, at the user's request, the applet started reading the Muse Code subscription. Before writing the connector, the route was probed with the account's real credential, in a single call and with a backup copy of `auth.json`.

What the probe showed:

- **Idempotency confirmed.** `POST https://api.meta.ai/muse-code/key` with the OAuth token returned HTTP 200 and the **same** `api_key` already stored (identical sha256), without any change to `auth.json` (bytes and mtime preserved). The key remained valid: `GET /muse-code/models` answered 200 with the four models after the call.
- **The quota comes in the return:** `subs_usage.window` (used percentage, window duration in minutes and `resets_at` in epoch) and `subs_usage.weekly` (percentage of the week), plus `tier`. The renewal times came coherent with the `/cost` panel of the analysis document. The struct has sixteen fields; the previous list of fifteen was incomplete (`base_url`, `payment_method` and `show_subs_upsell` were left out).
- **Price is not served by the API.** `GET /muse-code/models` returned 3388 bytes and four models **without any cost field** (also without a result with `x-client-id: tbh:tui`, `?include=cost` and `?verbose=true`; the route accepts only the API key, not the OAuth token). With no verifiable price, dollar spend left the scope: the token count does not enter the contract, which knows only quota, balance and spend.
- **Local consumption is aggregable** should the subject come back: each usage record in the CLI's `session.jsonl` files carries `owner.run_id`, and the model of each run is in `run.model.configured`; the records marked with `reported: true` matched a model in the scan performed.

The implemented connector does one thing only: it reads the subscription, with its own minimum interval (`meta.min_interval_seconds`, default 900 s) and private cache `~/.cache/cinnamon-ai-usage/meta.json` (0600, only the account digest). Within the interval there is no new call and the reused reading keeps the real `read_at`, so that the applet presents it as a stale reading once the TTL passes. Without Muse Code login the service stays `unconfigured` and no call goes out; a network failure or a response without a percentage stays `error`/`unavailable`, never 0%.

The login path was not guessed: the launcher script embedded in the binary resolves `$MUSE_AUTH_PATH` and, without it, `$XDG_CONFIG_HOME/muse/auth.json` or `$HOME/.config/muse/auth.json`. The connector follows that same order, with `token_files.meta` from the configuration ahead, and does not execute the binary at any moment — that is why the installed CLI version does not change the applet's behavior. The README carries the compatibility note; the connector was last exercised with Muse Code 1.4.0 (`1.4.0-R4161.1`) and `auth.json` at `schema_version` 1.

Verified: 46 offline Python tests (11 new, only from this connector: two windows, missing percentage, value above 100 capped in the bar with the real number in the note, absence of credential/account leakage in the message, POST with the expected token and header, reuse within the interval, expired reading, login file resolution order, interval limits, failure without an invented zero), `compileall`, `node --check`, applet JS test, real CJS test, real reading by `worker meta` (0,7 s on the first call with network, 0,06 s on the second, without network) and checking of the cache file at 0600.

## Ninth source: the Claude Code subscription

On 26/09/2026, at the user's request, the ninth connector came in. The starting point was a draft of 307 lines generated by another assistant (kept outside the repository), analyzed line by line before integration. The draft served as a map — it found the local OAuth token, the `claudeAiOauth.accessToken` format with `expiresAt`, the expired-token check and the intention to fail soft —, but the collection mechanics were rejected:

- **It consumed the quota it measures.** To pull the `anthropic-ratelimit-unified-*` headers, the draft did a POST to `/v1/messages` with `max_tokens: 1`. With a collection every two minutes, the applet would spend the user's quota to display it — the opposite of what the project allows itself. The connector uses the read route `GET /api/oauth/usage`, the same one the CLI uses in `/usage`.
- **Guessed header names**, and one of them meaningless: `anthropic-ratelimit-unified-5h-utilization` and `-7d-reset` do not exist in the public documentation (the pattern is `-{claim}-utilization` and `-reset`), and there was a fallback to `anthropic-ratelimit-unified-status`, which brings `allowed`/`rejected` and not a percentage.
- **A heuristic that invents a number:** `f * 100 if f <= 1 else f` would turn 0,4% into 40%. The connector uses the percentage as it came.
- **Raw headers inside the result** (which would go to the cache) and the machine path in the error message, both against the contract rules; besides macOS and Windows branches with no purpose in a Cinnamon applet on Linux and a User-Agent imitating the CLI.

What was verified on this machine, and what was not:

- **The route exists.** `GET https://api.anthropic.com/api/oauth/usage` with an invalid token returned **401** (not 404), with a JSON error — the path is real and the failure mode falls into the existing 401 mapping. The body complained about `x-api-key`, not about the `Bearer`; without a valid token there is no way to know whether that matters.
- **Without an account, there is no call.** With no `claude` CLI, no `~/.claude/.credentials.json` and no Anthropic variables on this machine (verified), the service stays `unconfigured`, with empty metrics and no request — the state of whoever installs the applet without Claude Code.
- **Diagnostics without values.** `collector.py diag claude` returns the origin of the path, the existence of the file, the names of the login fields, the structure of the response (names, types and range of the numbers) and the recognized windows — without values, without the machine path and without a credential. It is what an issue report needs.
- **61 offline tests** (15 new: flat objects and a `limits` list, unknown type ignored, absence of a percentage, scale not rescaled, login resolution order, expired token without a call, GET with `anthropic-beta` and without a body, reuse within the interval, 0600 cache with only the digest, unknown response asking for diagnostics, 401 without an invented zero, note without leakage and diagnostics without values).
- **Not verified:** the query with a real account — there is no Anthropic subscription or key here. The acceptance of the `Bearer` on that route, the current format of `.credentials.json` and the scale of the percentage remain open. The README states this in the status table and in the service section.

The route and the format came from third-party public documentation, not from Anthropic: the `wakamex/ccusage` project, the issues `anthropics/claude-code#27915` and `#18121` and Anthropic's own documentation about where the credentials live (`~/.claude/.credentials.json`, `CLAUDE_CONFIG_DIR`, Keychain on macOS).

## Review of the external analysis (26/09/2026)

An analysis by another assistant (kept outside the repository) reviewed the applet on 25/09, when the project had seven services and 35 tests. Each finding was checked against the current code before becoming a fix; one of them was a false positive and was discarded.

- **A skipped collection said "falhei".** With the `collect.lock` lock busy, the `collect` returned the old snapshot with all services downgraded to `stale` and exited with 0: the Atualizar button seemed to do nothing and the window asserted a failure that did not happen. Fixed with the public field `notice` (a notice, not an error) and with the inverted condition that suppressed the notice of a real failure when there were services without a reading.
- **A credential value was cut in silence.** `KEY=sk-abc#def` became `sk-abc` (the `#` cut the rest, and an API key usually has `#`), a value with a space was discarded and a loose quote discarded the value — everything showing up as "não configurado". Now the value without quotes counts as written and the window lists the ignored lines with the reason.
- **Black robot icon in the window.** Measured in the pixbuf: 389 opaque pixels, all `(0,0,0)`, because `currentColor` is not resolved by GdkPixbuf. Now the theme's foreground color is applied to the SVG before loading, and the same colored icon serves the window (128 px).
- **The window depended on an undeclared package.** The SVG loader comes from `librsvg2-common` and the call had no guard: without the package, the window failed at construction. Now there is degradation to the theme icon and the list of packages is in the README.
- **Invented labels in the demo** (prepaid Grok with "Janela de 5 h", OpenCode Go with a single window) and `docs/demo.png` captured before the Credenciais button: the repository's public image showed an interface that no longer exists. The demo started following the shape of each connector and the preview was recaptured.
- **Three different versions** (metadata 0.2.0, User-Agent 0.1.0, validation 0.1.0). Now a single constant, with a test that fails if they diverge.

**False positive discarded:** the analysis claimed that the context menu would be empty and that the README was wrong. Cinnamon installs "Configure…" by itself when `settings-schema.json` exists (`/usr/share/cinnamon/js/ui/applet.js`): the README instruction was correct.

**UUID before publishing:** the applet was born as `ai-usage@claudio.local` and became `ai-usage@claudio.drews` — the `.local` suffix means "não distribuir" and is frowned upon in a submission to the Spices. The change also applies to the identifiers of the windows (`claudio.drews.CinnamonAIUsage`, `…​.Credenciais`) and to the name of the keyring schema, which is invisible to the user; changing it after publishing would invalidate already stored preferences and items.

Verification of this round: 72 offline Python tests (11 new), applet JS test with the skipped-collection notice and the names of the services with failures, `node --check`, `compileall`, proof with real GTK of the credentials window (syntax notice and pending path) and of the header pixbuf, GTK smoke with the nine services and `docs/demo.png` recaptured.

Hygiene of the same list, done right after: `read` started using the `refresh_seconds` from the configuration instead of a fixed 120 s (it contracted an "antigo" state that the applet did not consider stale); an ISO date without a timezone stopped being silently discarded and is read as UTC, by a convention declared in the contract; the cleanup of the workers gained a guard for the process that dies between the `poll` and the signal, which before turned into "falha ao ler configuração" and lied about the cause; the duration of the window (`window_seconds`), which only appeared when the origin label already stated it, entered the details line; and the installer stopped creating the staging directory inside the applets folder (it appeared as a phantom applet) and stopped delivering the copy with 0700 — which, in an installation to `/usr/share`, would leave the applet readable only by root. Verification: 76 offline tests (four new, one of them exercising the `read` subcommand for real and another installing into a throwaway directory and checking the mode and the absence of leftovers).

## Second external review (26/09/2026)

Another review of the same commit (`7616f6d`) pointed out five functional problems and three sanitization points. All were reproduced and fixed; the three sanitization ones became content and history cleanup.

- **A stale reading could appear as current, depending on the path.** The quota connectors (Meta and Claude) reuse the reading within the minimum interval, keeping the original `read_at` with status `ok`; the `read` applied the age evaluation, but the `collect` returned the raw result — the same ten-minute reading came out `ok` on one path and `stale` on the other, and an expired quota kept coloring the robot. Now the `collect` applies to the output the same age evaluation as the `read`, and the real value remains in the metric.
- **Saving the xAI key in the keyring could fail to replace the credential used.** The window wrote `XAI_MANAGEMENT_KEY`, the backend preferred `XAI_MANAGEMENT_API_KEY`: with the alias existing in the file or in the environment, it won over the freshly saved key and the authentication failure continued. The window started writing the backend's preferred name, the keyring started winning over file and environment **in any of the names** (it is the value the person just typed), and "remover do cofre" also deletes the equivalent names. A consistency test compares the names of the window with those of the backend and would have caught the mismatch.
- **The minimum interval did not protect against failures.** The control was the time of the last **successful** reading; an attempt with an error did not update it, so after an HTTP 429 the automatic collection repeated the query every two minutes, worsening the block. Now the private cache records the timestamp of the attempt (preserving the last good reading) and the interval applies to any attempt: with no reading to reuse, the service stays `unavailable` with "Consulta adiada". Three consecutive attempts produce a single call, verified in the two connectors.
- **Pausing the collection froze the state.** With the collection paused the applet removed the loop and nothing else reevaluated the age; the color considered only `status === 'ok'`, so a reading from an hour ago kept the icon red and received no notice. The applet started checking the age of the reading (configured interval plus a minute of slack, so that the next cycle arrives without blinking every round) and a loop of 60 s reevaluates this without consulting any service — including paused. An `ok` reading without a time is not treated as current.
- **The window accused a failure where there was only an expired interval.** Any `stale` service received "a atualização mais recente deste serviço falhou", even when the collector had said only "atualização pendente". The snapshot gained the field `stale_reason` (`pending` or `failure`), documented in the contract, and the text of the card follows the real reason, with deduction from the message for old snapshots. The decision lives in the collector and has its own test; proof with real GTK checked the two texts in the built card.

Sanitization, done right after:

- **Real account data left the published documentation:** consumption percentages of the subscriptions, top-up/balance value, renewal times, counts of the scan of local session files and session identifiers of the agents. Where the number was the point (the sign convention of the xAI balance), the text started explaining the mechanism without the account value — in the README, in the validation and in the `docstring` of the connector; the comment of the test also stopped citing the real response. This cleanup was measured **only in the tree**: the previous commits kept carrying the versions with the numbers, and the whole history was rewritten in the third review, below.
- **Paths of this machine in the Git history:** the old history still kept the author's personal path in intermediate versions of `README.md` and `AGENTS.md`. Since publishing the repository publishes the history, the rewrite replaced those paths with relative forms in all commits, not only in the current tree.
- **`AGENTS.md`** said "não é publicado" and was versioned: in a normal push, it would go up. The file remains on disk to guide whoever works here, but it stayed out of the tree and of the history.

Verification of this round: **84 offline Python tests** (8 new: stale reading in the output of the collection, reason of the failure preserved, text of the notice, interval after failure in the two connectors, cache without the new field, names of the window equal to those of the backend, keyring winning over the alias of the file), applet JS test (reevaluation of age with the collection paused, one-hour reading out of the color of the icon), `node --check`, `compileall`, proof with real GTK of the text of the stale-reading cards and a full reading of the history to check the absence of personal paths.

## Third external review (26/09/2026)

Third review of the same commit (`3d88336`) confirmed, independently, the 84 tests
Python, the JS test, the syntax, the CJS/St/Gio check, the 12 files then installed
coinciding with the repository (0644 and main directory 0755), the single authorship of the 22 commits
and the absence of a remote and of a personal path in any blob. It found three pending items; the three
were reproduced and fixed.

- **The cleanup of the account data was worth only for the tree.** The current versions of `README.md` and
  `docs/validation.md` no longer carried percentages, balance or session identifiers, but the
  old commits kept carrying those versions — and publishing the repository publishes the
  history. The previous verification measured the tree and considered the item resolved; the right measure is
  to scan every blob of every commit. In this round the 24 commits were rewritten with
  `filter-branch --tree-filter` (literal substitutions, only in text files, each one
  written from what the published version already said), and the history started telling the same
  thing as the HEAD. This record commit was born after the rewrite, already clean by construction.
- **The failure of the last attempt disappeared in the reused reading.** With a good reading in the
  private cache, the round following an HTTP 429 reused that reading with status `ok`: the
  collector then reclassified it as "atualização pendente", and the failure left the screen without the
  service having come back. The cache started keeping the outcome of the attempt (`attempt_status`,
  `attempt_message`, preserving the last good reading) and the reused reading comes out with
  `stale_reason` `failure` and the message of that attempt; a response without the expected
  percentages is also recorded as a failure, in the two quota connectors. Reproduced with
  fictitious data before and after — good reading, 429, next round without a new call: before, `ok` in the
  output of the connector and `stale`/`pending` on the screen; now, `stale`/`failure` with the time and the
  values of the reading preserved, and a new response returns the service to `ok`.
- **The window could report the wrong origin of the credential.** The backend started preferring the
  keyring in any of the names, but the window kept checking keyring, file and environment of
  one name before moving on to the next: with `XAI_MANAGEMENT_KEY` in the keyring and
  `XAI_MANAGEMENT_API_KEY` in the file, the collection used the keyring and the interface said "do arquivo
  indicado". The window started asking the origin to `credentials.value_source`, the same function
  that decides the precedence for the backend — a single rule, without reimplementation —, and a test
  covers the three levels and the absence of a value. Proof with real GTK in this session (`Gtk.init_check`
  true here): credentials window built, three cases checked by the label text —
  keyring of the alias with file of the preferred name → "guardado no cofre" (the previous logic would say
  "do arquivo indicado"), file only → "do arquivo indicado", nothing → "não configurado".

**Verification of this round: 90 offline Python tests** (6 new: failure preserved in the reused
reading in the two connectors, service that goes back to answering clearing the previous state,
first failure without a previous reading following `unavailable` with "Consulta adiada", origin of the
credential in the three levels and the interface without repeating the order), applet JS test,
`node --check`, `compileall`, CJS/St/Gio check and the proof with real GTK above. The three
tests that discriminate the defects fail against the previous commit and pass on this one.

History rewrite, with the numbers of the scan done at the moment of the rewrite (24 commits,
496 tree blob versions): before, 10 lines of account data existed **only** in the history —
measured subscription percentage, balance/top-up in currency, renewal time, count of the
scan of session files and agent session identifier —, and none of them in the published
tree; after, zero in the two lists. In the final state (25 commits, 135 blobs in the directory of
objects, already with this record commit), the search for the 14 phrases of account data in **all** the
objects of the repository returns zero, including the two session identifiers of the agents. The
tree of the `HEAD` had the same hash before and after the rewrite
(`88f2503aa7b7c5a7762588b8683cee886376a545`): the rewrite changed what the old commits
said, not what the published version delivers. A copy of the previous state kept outside the
repository (`~/backups/cinnamon-ai-usage-antes-da-reescrita-*.bundle`, verified as a
complete history, and `~/backups/cinnamon-ai-usage-dot-git-*/`), along with the scan scripts
and the GTK proof; `refs/original`, reflog and loose objects were deleted afterwards, and `git fsck`
stays clean.

Two points left on purpose: the values `-1000` of the test fixtures, which are a test
value and remain in the published tree — what the test checks there is the conversion of cents to
the monetary unit, not an account number —, and the comment of an intermediate commit that
cites the example of `-1000` cents from the **public documentation of the xAI** — it is the example of the
documentation, not a response of the account.

## Investigation of the Meta connector failure (26/09/2026)

In the first collection of the applet already with the corrected backend, the real call at 17:17:48Z came back **without**
the percentages and the new code recorded the attempt as a failure, preserving the previous reading
(`read_at` 16:59:16Z, with the two windows and percentages) and showing the service as a stale reading
due to failure. The report recommended `diag meta`, and the recommendation was a dead end: `DIAGNOSTICS`
brought only Claude, and the command answered "não há diagnóstico para este serviço" without consulting anything.

- Fixed: there is a `meta_diag`, under the same privacy discipline of `claude_diag` — names of
  fields, types and range of the numbers, no value, account identifier or machine path;
  without a credential there is no call. Besides the structure, the report brings `campos_esperados`: for each
  path the connector looks for (`subs_usage.window.used_percent`, `subs_usage.weekly.used_percent`),
  whether it is absent, null, or with what type it came.
- A test reads the messages of the module and the table `DIAGNOSTICS`: no suggestion of `diag` points to
  a service without a report. It was the mismatch between message and table that produced the dead end.
- Reproduction of the difference, with the same command: the code then installed in the panel returned
  `{"diagnostico": "não há diagnóstico para este serviço"}`; the corrected code returned the complete
  report, saying that the response brings `subs_usage` absent and no recognized window.

**Correction of a previous statement of mine.** When reporting the failure, I said that "the format of the response
of the API changed or the field the connector looks for no longer comes". The evidence does not sustain the first
part: it shows that the parser did not find the percentages, and nothing beyond that. What is known, measured:
the reading of 16:59:16Z, on the same route, brought the two windows with percentages; the attempt of
17:17:48Z returned only metadata of the account and of the subscription, with `is_subs_active` true and without
payment requirement, and no `subs_usage`. Whether this is a change on Meta's side, some state that the
call started carrying, or variation between calls, **is not proven** — and the report of
`diag meta` is what separates the hypotheses. While there is no new response with the windows, the service
appears as a stale reading due to failure, with the reading of 16:59:16Z preserved; no number was
invented and no bar stayed full.

## Internationalization (26/09/2026)

The prose visible to the user left the code for a single gettext catalog, whose domain is the uuid of the applet (`ai-usage@claudio.drews`): the same catalog covers the panel, the two GTK windows, the installer and the name and the description of the xlet in the Cinnamon screens. The msgids are written in English and pt_BR is the translation catalog; without a `.mo` installed the interface degrades to English, never to a language without a catalog.

What remains recorded in the contract and in the cache keeps no translated text: `message_id`/`message_args` in the service and `label_id`/`label_args` in the metric carry the msgid (English) and the raw values of the placeholders, and `message`/`label` keep the text in the language of the collection for whoever consumes without a catalog. Changing the language does not discard a reading, does not force a collection and does not mark anything as stale. A persisted identifier always uses the singular entry — the contract does not offer plural selection in those records — and a lock walks the 88 `N_()`/`message_id=`/`label_id=` of the backend plus the `N_()` of the panel against the plural entries of the catalog.

The language precedence is project policy, written in `docs/i18n.md`, and does not promise equivalence with native gettext nor with the screens of the desktop: a defined and non-empty `LANGUAGE` rules alone — it is through it that the applet exports the fixed language to the child processes — otherwise the first of `LC_ALL`, `LC_MESSAGES` and `LANG` applies; a language without a catalog answers English, never the language of whoever is logged in. The plural rule comes from the expression `Plural-Forms` of the header of the catalog, mirrored in a table in each runtime: in pt_BR `plural=(n > 1)`, so zero is singular.

The work was divided into three fronts with disjoint `git worktree` (providers; the two windows; collection and credentials), each one delivering a `.po` fragment, and the catalog was closed by a single owner with `msgcat`: 276 of the 277 entries translated (the one missing is the header), zero obsolete, zero fuzzy.

Two fixes came from checking what the test said it proved, and not from the code of the product. The sieve of prose outside the catalog counted non-ASCII characters and was blind to half of the problem — `Saldo`, `Sem uso observado` and any fixed English sentence in the code have no accent at all; it started deciding by the shape, and what looks like prose without being screen text stays declared with a reason and compared by equality. And the messages of the installer, which also speak to a person, stayed out of the scan because only `backend/*.py` was looked at: the installer entered the catalog, with the language activated in the `main()` and never in the import.

Verification of this round: **224 offline Python tests in pt_BR and in English**, panel suite in Node and `node --check`, `compileall`, `sh scripts/i18n.sh` idempotent (`.po`, `.pot` and `.mo` identical in two runs) and no path of this machine in the repository. The visible text in pt_BR was compared with the previous commit by a canonical dump — demo, the nine diagnostics and the collection without configuration — and came out identical; the same dump in English has no residue of Portuguese. The two GTK windows were opened with synthetic data in pt_BR and in English, each one checked in the resolved language and by capture (`docs/demo.png` in English, `docs/demo.pt-BR.png` in Portuguese); the paths of the captures and of the dumps are listed in `docs/evidence/README.md`. Nothing was installed, activated or reloaded in the panel.

## Fixes after the review of `de3b6b7` (26/09/2026)

A review of the internationalization delivery found three defects the suite passed over and
asked for the documentation the plan had promised. The three were reproduced before being
fixed.

- **The cache still stored translated arguments and formatted numbers.** `window_hours()`
  returned a localized string, saved in `label_args`: a 90-minute window collected in
  Portuguese appeared in an English presentation as "Window of 1,5 h". The optional clauses of
  the Meta/Claude note (`meta_note_args`, `claude_note_args`) were whole translated sentences
  in `details`, so an English reading of a Portuguese collection showed the Portuguese text
  "Plano: Pro. A Meta relatou 125,5% de uso; a barra do applet vai até 100%". And `source` was
  translated text in the snapshot, shown as is by the window: "OpenRouter · chave" stayed in an
  English presentation. The collection now stores raw data — the number (`1.5`), the plan, the
  reported percentage, the identifier of each clause and the values that fill it — and the
  presentation composes and formats: `i18n.arg_text()` in the backend and `_argValue()` in the
  panel read the same language table, and the clauses of the note are joined with the space
  that separates the block from the sentence. The origin travels as `source_id` +
  `source_args` next to `source`, and both windows resolve it through `Source: {source}` — the
  fresh collection return of Meta and Claude, however, was still leaving `source_id` empty at
  this point, which the review below reproduces and `3cc2564` fixes. The same snapshot answers
  in both languages, with nothing re-collected and nothing discarded:
  the saved text stays as the fallback for whoever has no catalog, and a snapshot written by
  an earlier version keeps showing what it saved.
- **The technical identifier of Antigravity followed the language.** With no model name,
  `parse_antigravity()` built `model:` + label, and the label comes from the catalog:
  `model:Modelo 1` in Portuguese, `model:Model 1` in English. The comparison between two
  readings keys on the id, so the same quota under two names made consumption going from 20%
  to 40% visible in Portuguese and invisible after switching to English. The id now comes from
  the raw data of the reading — the model id in the response, or the position of the model in
  the answer when there is no name at all — and `id_aliases` carries the ids an earlier version
  wrote from the label, so the first collection after the fix still compares against the history
  already on disk — the label translated from the catalog when the model has no name, and the
  label fields of the response when it has one, since the service's own label is data. **The
  named model is the case this paragraph got wrong until the review of `c78dc9f`**: it had also
  changed id, and the alias for the id the earlier version wrote from its label came only in the
  round of `3cc2564` (below).
- **The test of the reused note reproduced the defect in its own expectation**, comparing the
  output with the same `args` already translated. It now walks Portuguese → English →
  Portuguese over a **single** record, built once with a fractional window, a plan, a
  percentage above 100% and an origin, and checks the whole sentence and the separators of each
  language. The Antigravity regression compares two readings of the same quota, one collected
  in Portuguese and one in English, and requires the same id and the rise in consumption to be
  seen; it also covers the snapshot an earlier version left on disk, without aliases. A test
  walks the record through a JSON round trip, which is where a formatted number would stop
  being a number.
- **Documentation.** `docs/contract.md` and `docs/validation.md` are in English, as the plan
  promised, with the content, the commands and the evidence preserved — the Portuguese text of
  the interface stays quoted where it is the point. The contract now states the three shapes of
  a placeholder argument, the list of parts, `source_id` and the rule that a technical
  identifier never comes from a label; `docs/i18n.md` carries the same policy under "Texts that
  stay in the cache".

Verification of this round: **231 offline Python tests in pt_BR and in English** (7 new),
panel suite in Node (raw numbers, clauses of the note and the skipped-collection notice read by
identifier), `node --check`, `compileall`, `sh scripts/i18n.sh` idempotent (`.po`, `.pot` and
`.mo` identical in two runs) and no path of this machine in the repository. The visible text in
pt_BR came out **byte-identical** to `de3b6b7` by the canonical dump of the demonstration, the
nine diagnostics and the collection without configuration
(`docs/evidence/text-de3b6b7-pt_BR.json` against `docs/evidence/text-after-pt_BR.json`), and
the same dump in English (`docs/evidence/text-after-en.json`) has no Portuguese left in the
visible text. The four GTK captures of the round, with effective paths — `docs/demo.png` (usage
window, English), `docs/demo.pt-BR.png` (usage window, pt_BR),
`docs/evidence/window-credentials-en.png` and `docs/evidence/window-credentials-pt_BR.png`
(credentials window, English and pt_BR) — are reproduced by `tests/smoke_gtk.py` and
`tests/smoke_gtk_credentials.py`, which activate the language as the product does and refuse to
write a capture when the resolved language does not show up in the widgets. The dumps of the
round and their index are in `docs/evidence/` (`README.md`, `text-*.json`,
`texts-credentials-*.json`). The three dumps and the two captures of the credentials window were
regenerated later inside the isolation of `tests/isolation.py` (round of `5489134`, below): the
harnesses at this point pointed only `XDG_CONFIG_HOME`/`XDG_CACHE_HOME` at a temporary directory
and left the keyring, the credential variables, the login files, the local binaries and the
process table reachable — the versioned dump itself recorded Codex as `ok` in the section with
no configuration. The pt_BR before/after stays byte-identical with both sides isolated. Nothing
was installed, activated or reloaded in the panel.

## Review of `c78dc9f` and `3e4762e`: origin, named-model id and the isolation of the evidence (26/09/2026)

A review of the internationalization delivery, and of the fixes that came after it,
reproduced two functional defects the suite passed over and one defect in the evidence
harnesses themselves, which claimed an isolation they did not have. The three are fixed in
`3cc2564` and `5489134`, the commits of this round.

- **The fresh collection of Meta and Claude returned the origin without `source_id`.** Both
  connectors built the identifier of the origin (`Muse Code · Meta subscription`, `Claude
  Code · subscription (not verified)`) and handed it to `service()` in the **text** field
  (`source=source`): the record left with the translated text and no `source_id`, and the
  presenter resolves the origin through the identifier (`Source: {source}` in both windows),
  so a reading collected in Portuguese showed the raw msgid in the presentation, in either
  language. The reading reused from the private cache already went through `source_id`. Now
  both connectors pass `source_id` to `service()`, which writes the translated text to
  `source` and the msgid to `source_id`, and the two paths carry the same identifier.
  Regression: `tests/test_backend.py::ProviderTests::test_meta_origin_travels_by_identifier_in_the_collection_and_in_the_reuse`
  and `tests/test_backend.py::ClaudeTests::test_claude_origin_travels_by_identifier_in_the_collection_and_in_the_reuse`
  — each one runs the collection in Portuguese against a simulated response and requires the
  same `source_id` and the same `source` on the fresh reading and on the reused one (a single
  call for the two). Both fail against `3e4762e`.
- **A named Antigravity model lost the id the previous version had written.** With
  `label="Display Model"` and `modelOrAlias.model="backend-model"`, `parse_antigravity()` had
  stopped taking the id from the label — correctly, the raw datum is the stable one — but
  declared no alias when a name existed. The reading the previous version had written as
  `model:Display Model` stopped comparing with `model:backend-model`, and a quota rising from
  20% to 40% passed in silence against the history already on disk.
  `legacy_named_model_ids()` now puts the id the earlier version took from the label into
  `id_aliases` — the label fields of the response (`label`, `modelLabel`), which are data of
  the service and not translated text. Regression:
  `tests/test_backend.py::HistoryTests::test_the_named_model_identifier_keeps_the_one_the_previous_version_saved`
  reads a record in the previous format (id from the label, no alias), requires the new id to
  come from the raw data with the old one in `id_aliases`, checks `merge_history` with
  `recency_basis: observed_change`, and covers the model that only brings `modelLabel` and the
  unnamed model, whose alias still comes from the catalog. It fails against `3e4762e`.
- **The two evidence harnesses claimed an isolation they did not have.**
  `tests/dump_visible_text.py` pointed only `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` at a
  temporary directory and then called `providers.diagnose()` and `collector.collect(force=True)`
  with the environment, the keyring, the login files and the `codex` installed on the machine
  reachable — the versioned dump was the proof of the leak: it recorded Codex as `ok` in the
  section that says "no configuration". `tests/smoke_gtk_credentials.py` built the real window
  without replacing the queries to the keyring. `tests/isolation.py` (new) builds the isolation
  instead of asserting it: an exclusive sandbox under `/tmp` with `HOME` and every `XDG_*` path
  inside it and the credential variables out of the environment, and a fixture in the place of
  the system keyring, the indicated file, the network, the local executables, the process table
  and the worker process of the collection. `assert_clean()` fails the run that stops going
  through a fixture or that reaches the network, the keyring, a local binary or a real process,
  and the harness prints the summary of the isolation on stderr, so stdout stays byte-comparable;
  the sandbox is removed at the end. The two seams the product gained for this are
  `collector.worker` with `collector.launch_worker` and `providers.local_server_processes`; run
  against a tree older than them, the harness reports the missing seam on stderr instead of
  hiding it. New `tests/test_evidence_isolation.py` (8 tests): a dump produced with a poisoned
  environment and a fake `codex` on the `PATH` comes out identical to the clean run, the guard
  rejects a network query, a read outside the sandbox and a write to the keyring, a substitution
  that was not exercised fails the run, every path the product resolves stays inside the sandbox,
  and the report on stderr names what was substituted and which variables left the environment.

The evidence was regenerated inside that isolation, and the files are committed: in the three
dumps the only difference from the previous version is the Codex line, which was the leak; the
before/after in pt_BR stays byte-identical, now with both sides isolated. The "before"
(`docs/evidence/text-de3b6b7-pt_BR.json`) is produced by running the **current** harness against
a tree of the old commit, inside the same fixtures:

```
$ mkdir <dir> && git archive de3b6b7 | tar -x -C <dir>
$ LANGUAGE=pt_BR.UTF-8 python3 tests/dump_visible_text.py <dir> > docs/evidence/text-de3b6b7-pt_BR.json
```

The two captures of the credentials window were redone with the example file inside the sandbox,
so the visible text changes only in the path shown; the texts dumps
(`docs/evidence/texts-credentials-*.json`) reproduce except for the path of the sandbox, which is
different in every run. The exact commands are in `docs/evidence/README.md`.

Verification of this round: **242 offline Python tests in pt_BR, in English and in the default
locale**, `node --check`, `compileall`, `sh scripts/i18n.sh` idempotent and no path of this
machine in the repository. For this record the harnesses were rerun: the three dumps came out
byte-identical to the committed ones (`cmp` empty), including the "before" regenerated against
the tree of `de3b6b7`, and the two credentials texts match except for the path of the sandbox.
Nothing was installed, activated or reloaded in the panel.

## Delegation and review

Hermes implemented the base of the GTK window in `backend/window.py`; OpenCode implemented the first version of `applet/`. Codex defined the contract, implemented the connectors/cache/tests/installer and reviewed the deliveries. The review fixed Cinnamon APIs, signature and output capture of Gio.Subprocess, timers, St composition, GTK shutdown and renewal presentation. Passing `node --check` alone would not have detected those integration errors.

Delivery sessions: the sessions of the agents that took part stayed out of this document, along with full logs, credentials, SQLite databases and account responses — none of that belongs to a published repository. What stays recorded is the verifiable result: commands, tests and what each one showed.

## Sources

- [Codex App Server](https://developers.openai.com/codex/app-server/) — initialize, initialized, account/rateLimits/read, usedPercent, windowDurationMins, resetsAt and rateLimitsByLimitId.
- [OpenRouter: current key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key).
- [DeepSeek: balance](https://api-docs.deepseek.com/api/get-user-balance/).
- [xAI: billing in the Management API](https://docs.x.ai/developers/rest-api-reference/management/billing).
- [omarchy-ai-usage](https://github.com/rodrigo-sntg/omarchy-ai-usage), branch master, scripts ai-usage-codex.sh and ai-usage-antigravity.sh — protocol reference; we do not use the mapping of Antigravity families to fictitious windows of five hours/seven days.
- Installed Cinnamon code: `/usr/share/cinnamon/js/ui/applet.js`, `popupMenu.js`, `settings.js`, native applets and schema `org.cinnamon.desktop.peripherals.mouse`.
- Installed Hermes code: `hermes_cli/nous_account.py`, `agent/billing_usage.py` and corresponding tests — OAuth read contract of the Nous; format checked with a real response.
- [Claude Code: where the credentials live](https://code.claude.com/docs/en/authentication) and [environment variables](https://code.claude.com/docs/en/env-vars) — `~/.claude/.credentials.json`, `CLAUDE_CONFIG_DIR` and Keychain on macOS.
- Usage route of the Claude Code and format of the response: [ccusage](https://pypi.org/project/ccusage/) (`wakamex/ccusage`) and [anthropics/claude-code#27915](https://github.com/anthropics/claude-code/issues/27915) — `GET /api/oauth/usage` with `anthropic-beta: oauth-2025-04-20`, objects `five_hour`/`seven_day` and the list `limits` with `kind`, `percent` and `resets_at`. We do not use the POST to `/v1/messages` to scrape rate limit headers: it consumes the displayed quota.

## Known limitations

Recency derives from changes between collections: it is approximate, starts without history, includes consumption of the account outside this computer and does not prove which agent made the call. The Nous connector does not renew tokens; the login is managed by Hermes. Antigravity depends on the IDE and on an experimental local protocol. Go may change its endpoint. A change of format shows absence/error and preserves the last valid value, without zeroing quotas. The connector of the **Claude Code** is the only one published without verification on a real account: the route and the format follow the public documentation of the community, and the README states this in the table and in the section of the service. The complete interface does not implement notifications nor historical charts in this version.
