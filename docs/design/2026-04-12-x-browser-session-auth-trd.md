# Signal Engine X Browser-Session Auth TRD

**Date:** 2026-04-12  
**Status:** draft for implementation  
**Scope:** Replace file-based X cookie auth with browser-session-based auth for `x-feed` and `x-following`, while preserving existing lane/runtime/output contracts and keeping cookie-file mode only as a legacy fallback.

---

## 1. Goal

Migrate Signal Engine's X authentication model away from manually exported cookie files such as:

- `~/.signal-engine/x-cookies.json`
- Netscape cookie dumps

and toward a browser-session-based model that reuses a real, manually logged-in Chrome session.

The target outcome is:

- `x-feed` and `x-following` can run without a cookie export file
- the operator manually logs into X once in a dedicated local Chrome profile
- Signal Engine connects to that live browser session at runtime
- Signal Engine extracts `ct0` from the page context and performs X GraphQL fetches from within the browser context using `credentials: 'include'`
- X session cookies such as `auth_token` are no longer stored in Signal Engine-managed files
- existing lane outputs remain intact:
  - `SignalRecord`
  - `RunResult`
  - `signals/*.md`
  - `index.md`
  - `run.json`

This is not a generic browser platform initiative. It is a targeted auth/runtime improvement for X lanes.

---

## 2. Background

The current native X source implementation in Signal Engine uses a file-based auth model:

- `sources/x/auth.py` loads cookies from a local file
- `sources/x/client.py` builds an HTTP request using:
  - hardcoded bearer token
  - `ct0`
  - full `Cookie` header including `auth_token`
- lane config defaults assume `~/.signal-engine/x-cookies.json`

This has four problems:

1. **Operationally ugly** — users must manually export and refresh cookie files
2. **Brittle** — expired cookies look similar to source empty states
3. **Security-poor** — Signal Engine holds sensitive session cookies in files it manages
4. **Mismatch with desired workflow** — user preference is to reuse a real logged-in browser session instead of exporting credentials

A review of OpenCLI's X implementation shows that OpenCLI does **not** avoid cookies entirely. Instead, it avoids cookie files by:

- requiring the user to be logged into X in Chrome
- attaching to the live browser session
- extracting `ct0` from `document.cookie`
- issuing `fetch(..., credentials: 'include')` inside the page context so session cookies ride along automatically

That is the model this TRD adopts.

---

## 3. Non-goals

This work does **not** include:

- redesigning `SignalRecord` or `RunResult`
- redesigning the signal markdown / index / manifest protocols
- building a general-purpose browser automation framework for all Signal Engine sources
- adding browser-session support to non-X lanes
- implementing posting/replying/mutation features for X
- preserving cookie-file auth as the preferred mode
- replacing all `httpx`-based X logic with browser automation everywhere

---

## 4. Acceptance Criteria

This migration is considered complete when all of the following are true:

1. `x-feed` and `x-following` can collect successfully using a live Chrome browser session, without a cookie export file.
2. Config can explicitly select auth mode:
   - `browser-session`
   - `cookie-file` (legacy fallback)
3. Browser-session mode:
   - connects to a running Chrome instance over CDP
   - ensures there is an `x.com` page/context
   - extracts `ct0` from page context
   - performs GraphQL fetches in-browser with `credentials: 'include'`
4. Missing browser session / missing `ct0` / not-logged-in states produce explicit auth errors, not misleading silent success.
5. Existing lane outputs (`signals/*.md`, `index.md`, `run.json`) remain compatible.
6. Tests cover:
   - browser-session auth happy path
   - browser-session auth missing-login path
   - legacy cookie-file fallback still works where explicitly configured
   - lane-level integration behavior for at least one browser-session path
7. Docs explain the new preferred setup and demote cookie-file mode to legacy fallback.

---

## 5. Recommended Approach

## 5.1 Chosen direction

Use **Playwright over CDP** to attach to a real Chrome instance that the user has already logged into.

The core strategy is:

- the user launches a dedicated Chrome profile with remote debugging enabled
- Signal Engine uses Playwright `connect_over_cdp(...)`
- Signal Engine navigates to `https://x.com` in that browser context
- Signal Engine reads `ct0` inside the page context
- Signal Engine uses `page.evaluate(...)` to execute `fetch(...)` requests against X GraphQL endpoints with:
  - bearer token in header
  - `X-Csrf-Token: ct0`
  - `credentials: 'include'`
- the browser session automatically attaches `auth_token` and related cookies
- response JSON is returned to Python and parsed by the existing normalization pipeline

## 5.2 Why this approach

This is the best fit because it:

1. removes manual cookie-file export from the preferred workflow
2. preserves the anti-bot-friendly manual-login model
3. matches the proven pattern used by OpenCLI for X
4. avoids building a heavyweight custom browser bridge/daemon/extension stack
5. keeps Signal Engine's lane and artifact architecture stable

---

## 6. Architecture

## 6.1 Stable runtime boundary

The following layers should remain conceptually stable:

- `commands/collect.py`
- `runtime/collect.py`
- `lanes/x_feed.py`
- `lanes/x_following.py`
- `SignalRecord`
- `RunResult`
- signal writer / renderers / frontmatter / index / manifest

The migration should be isolated mainly to the X source subsystem and X-related diagnostics/config.

---

## 6.2 New X auth/runtime split

Proposed source structure:

```text
src/signals_engine/sources/x/
  __init__.py
  auth.py                  # auth mode resolution + legacy cookie-file loading
  browser_session.py       # Playwright/CDP attach + in-browser X fetch execution
  client.py                # legacy httpx client (cookie-file mode only)
  parser.py
  models.py
  errors.py
  feed/
    timeline.py
  following/
    timeline.py
```

### `auth.py`
Responsibility:
- resolve auth mode from config
- validate config for `browser-session` vs `cookie-file`
- keep legacy cookie-file loader for compatibility

### `browser_session.py`
Responsibility:
- connect to Chrome over CDP
- select or create an `x.com` page
- extract `ct0`
- execute X GraphQL fetches in browser context
- return raw JSON payloads to Python callers

### `client.py`
Responsibility:
- retain current `httpx` request path for `cookie-file` mode only
- stop being the default/preferred path

### `feed/timeline.py` and `following/timeline.py`
Responsibility:
- become mode-aware source entry points
- dispatch to browser-session or cookie-file fetch path
- preserve their normalized output contract

---

## 7. Auth Modes

## 7.1 `browser-session` (preferred)

This becomes the recommended mode.

Example config:

```yaml
lanes:
  x-feed:
    source:
      auth:
        mode: browser-session
        cdp_url: http://127.0.0.1:9222
        target_url: https://x.com
```

Possible optional fields:

- `cdp_url` — default `http://127.0.0.1:9222`
- `target_url` — default `https://x.com`
- `reuse_existing_page` — default `true`
- `timeout_seconds` — per lane, already exists in lane config and should continue to apply

Behavior:

1. connect to Chrome over CDP
2. find existing page whose URL is on `x.com` if possible
3. otherwise open/navigate a page to `https://x.com`
4. read `ct0` from `document.cookie`
5. if no `ct0`, raise auth/login-required error
6. issue GraphQL request inside browser context
7. return raw JSON to parser

## 7.2 `cookie-file` (legacy fallback)

This remains supported for compatibility and non-browser environments, but is no longer the preferred path.

Example config:

```yaml
lanes:
  x-feed:
    source:
      auth:
        mode: cookie-file
        cookie_file: ~/.signal-engine/x-cookies.json
```

Behavior:
- retain current auth loading and `httpx` request path
- only use this path when explicitly configured or when compatibility policy requires it

---

## 8. Browser Runtime Contract

## 8.1 Required operator setup

The user runs a dedicated Chrome profile with remote debugging enabled, for example:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=$HOME/.signal-engine/chrome-profile
```

Then they log into X manually in that browser profile.

Signal Engine must **not** automate login or request raw credentials.

## 8.2 Fetch behavior

Browser-session mode should use page-context fetch similar to:

```js
fetch(graphqlUrl, {
  method: 'GET' or 'POST',
  headers: {
    Authorization: `Bearer ...`,
    'X-Csrf-Token': ct0,
    'X-Twitter-Auth-Type': 'OAuth2Session',
    'X-Twitter-Active-User': 'yes'
  },
  credentials: 'include'
})
```

Important rule:

- Python should not need to materialize full session cookies when using `browser-session`
- the browser should carry the session cookies automatically

This is the main security and ergonomics win compared with cookie-file mode.

---

## 9. Error Model

The migration must improve error semantics rather than blur them.

Recommended categories:

- `AuthError`
  - browser not running
  - CDP unreachable
  - no `x.com` page can be established
  - `ct0` missing
  - not logged in
- `TransportError`
  - browser-evaluated fetch failed for network reasons
- `RateLimitError`
  - HTTP 429 from X
- `SchemaError`
  - response envelope changed
- `SourceUnavailableError`
  - upstream 5xx or equivalent

### Status mapping expectation

At lane/runtime level:

- browser-session auth/config failures should be surfaced clearly as source errors
- actual empty timeline should remain distinguishable from auth failure
- diagnose should identify whether the failure is:
  - no Chrome / no CDP
  - browser reachable but not logged into X
  - X request failure
  - schema drift

Note: current X lanes return `EMPTY` when fetch fails and `tweets == []`. This migration should be reviewed carefully so that auth-missing states are no longer silently indistinguishable from legitimate empty-source runs.

---

## 10. Diagnostics Design

`diagnose` for X lanes should evolve from cookie-file checking to mode-aware checks.

### For `browser-session`
Recommended checks:

1. lane registered
2. lane exists in config
3. auth mode = `browser-session`
4. CDP endpoint reachable
5. Chrome session available
6. `x.com` page open or creatable
7. `ct0` present in page context
8. lightweight X probe succeeds

### For `cookie-file`
Keep existing checks:

1. cookie file exists
2. `auth_token` present
3. `ct0` present
4. lightweight API probe succeeds

The diagnose output should explicitly say which auth mode is being checked.

---

## 11. Implementation Plan (High-Level)

### Step 1 — Add browser-session source support
Create browser-session source module using Playwright + CDP attach.

### Step 2 — Make feed/following source mode-aware
Update:

- `sources/x/feed/timeline.py`
- `sources/x/following/timeline.py`

so they dispatch based on auth mode.

### Step 3 — Preserve cookie-file mode as explicit fallback
Keep legacy path in place, but demote it from default/recommended mode.

### Step 4 — Update diagnose
Make X diagnose mode-aware and surface browser-session prerequisites/errors cleanly.

### Step 5 — Update docs/config examples
Replace cookie-file-first documentation with browser-session-first guidance.

### Step 6 — Add tests
Cover:

- browser-session auth success
- browser-session auth missing `ct0`
- browser-session CDP unreachable
- cookie-file fallback path still works when explicitly selected
- one lane-level collection path using browser-session mocks

---

## 12. Testing Strategy

## 12.1 Unit tests

New tests should isolate:

- auth mode resolution
- browser-session config validation
- browser fetch wrapper behavior
- ct0 extraction behavior
- browser-session error mapping

## 12.2 Lane tests

At least one lane-level test should verify:

- a browser-session raw payload is accepted
- normalized tweets are generated
- signal markdown / index / run manifest still work as before

## 12.3 Non-goal for tests

Do **not** make CI depend on a real running Chrome with a real X session.

The browser-session path should be tested via mocks/fakes at the source boundary.

---

## 13. Risks

### Risk 1: Playwright dependency adds packaging/runtime complexity
Mitigation:
- make it an explicit project dependency
- keep usage narrow and local to X source
- do not spread browser abstractions across unrelated lanes

### Risk 2: CDP attach can be flaky if operator setup is unclear
Mitigation:
- define one explicit startup convention for Chrome
- improve diagnose output
- document the setup clearly

### Risk 3: Browser-session mode could still be mistaken for generic browser automation scope creep
Mitigation:
- keep this confined to X source auth/fetch
- do not broaden this TRD into a multi-site browser engine refactor

### Risk 4: Status semantics may still mask auth failures as `EMPTY`
Mitigation:
- review lane finalization behavior while implementing
- ensure auth failure remains visible in errors and diagnose
- if needed, tighten status mapping in a follow-up compatible change

---

## 14. Recommendation

Proceed with:

- **Playwright + CDP attach to dedicated Chrome profile**
- **browser-session as the preferred auth mode**
- **cookie-file retained only as explicit legacy fallback**

This gives Signal Engine a cleaner, more operator-friendly X auth model without dragging the codebase into a full browser-platform rewrite.

---

## 15. One-Sentence Decision

Signal Engine should stop treating exported X cookie files as the primary auth mechanism and instead adopt an OpenCLI-style browser-session model: manually logged-in Chrome + CDP attach + in-browser GraphQL fetch with `credentials: 'include'`, while preserving cookie-file mode only as a legacy fallback.
