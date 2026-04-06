# Signal Engine x-feed Native Source Migration Design

**Date:** 2026-04-06  
**Status:** draft for review  
**Scope:** Replace `x-feed`'s `opencli` backend with a native Signal Engine source implementation while preserving the Phase 1 runtime/artifact architecture.

---

## 1. Goal

Migrate `signal-engine`'s `x-feed` lane off `opencli` completely, so that:

- `signal-engine collect --lane x-feed` no longer shells out to `opencli`
- `signal-engine` owns its own X source backend
- runtime behavior already established in Phase 1 remains intact:
  - `SignalRecord`
  - `RunResult`
  - `signals/*.md`
  - `index.md`
  - `run.json`
  - `collect / diagnose / status / config`
- the codebase, config, diagnostics, tests, and docs all stop treating `opencli` as a system dependency

This is a **B2 migration**:
- not a total greenfield rewrite of X acquisition
- not a continued runtime dependency on `opencli`
- but a controlled migration of the already-validated X adapter logic into `signal-engine`

---

## 2. Non-goals

This design does **not** include:

- redesigning `SignalRecord` / `RunResult`
- redesigning artifact protocols (`signals/*.md`, `index.md`, `run.json`)
- migrating other X lanes such as `x-following`
- introducing plugin systems or source auto-discovery
- preserving `opencli` as an in-product fallback backend
- turning `signal-engine` into a generic replacement for all `opencli` capabilities
- implementing a completely new X reverse-engineering stack from scratch

---

## 3. Acceptance Level

This migration targets **Level C completion**:

> not only must `x-feed` stop depending on `opencli` at runtime, but the repository, config, diagnostics, tests, and official docs must also stop treating `opencli` as part of the supported system.

A migration is not considered complete if any of the following remain true:
- runtime shells out to `opencli`
- config still uses `opencli.path` semantics
- diagnose still probes `dist/main.js`
- docs describe `opencli` as an operational dependency
- tests only validate the old backend assumptions

---

## 4. Recommended Approach

### 4.1 Chosen direction

Use a **controlled migration strategy**:

- preserve the Phase 1 runtime/artifact architecture
- replace only the X source backend
- migrate only the minimum X timeline acquisition logic needed for `x-feed`
- reorganize migrated logic to fit Signal Engine's own boundaries
- do **not** keep `opencli_legacy` or dual-backend runtime support inside `signal-engine`

### 4.2 Why this approach

This balances three constraints:

1. **Cleaner than runtime reuse** — `signal-engine` becomes operationally independent
2. **Cheaper than full greenfield rewrite** — avoids rediscovering all X-acquisition behavior from zero
3. **Compatible with current architecture** — does not destabilize the Phase 1 runtime that has already been validated

---

## 5. Architecture

## 5.1 Stable runtime boundary

The following layers remain conceptually unchanged:

- `commands/`
- `runtime/`
- `lanes/x_feed.py`
- `SignalRecord` / `RunResult`
- signal markdown render/writer
- index render/writer
- run manifest mapper/writer

The lane continues to consume a source interface that yields normalized feed items, then maps them into `SignalRecord` and artifact outputs.

### Design rule

`x-feed` lane must not know:
- whether the source used browser-derived requests, cookies, feature flags, or any legacy logic
- where auth material came from internally
- any historical `opencli` command semantics

It should only know:
- how to call the source
- what normalized fields come back
- how to map those fields into `SignalRecord`

---

## 5.2 New source subsystem

Proposed structure:

```text
src/signal_engine/sources/x/
  __init__.py
  auth.py
  client.py
  parser.py
  models.py
  errors.py
  timeline.py
```

### `auth.py`
Responsibility:
- load authentication material
- validate auth presence / shape
- expose source-facing auth state

Examples of concerns:
- cookie file discovery
- cookie parsing
- auth preflight validation

### `client.py`
Responsibility:
- build requests for home timeline acquisition
- handle transport
- isolate HTTP/session mechanics from parsing

### `parser.py`
Responsibility:
- transform raw X timeline responses into normalized source-side objects
- centralize source schema assumptions
- detect schema drift explicitly

### `models.py`
Responsibility:
- define normalized source-side models / typed records
- capture the source contract expected by `x-feed`

### `errors.py`
Responsibility:
- define source-specific error taxonomy
- distinguish auth, transport, rate-limit, parse, and schema errors

### `timeline.py`
Responsibility:
- expose the one stable source entry point used by the lane, e.g.
  - `fetch_home_timeline(limit: int) -> list[NormalizedTweet]`

---

## 6. Source contract

The `x-feed` lane should consume a normalized tweet shape with at least these fields:

- `id`
- `author`
- `text`
- `likes`
- `retweets`
- `replies`
- `views`
- `created_at`
- `url`

This is intentionally the minimum field set already needed by Phase 1 artifact generation.

### Contract rule

The lane depends on the normalized shape only.

It does **not** depend on:
- raw X response structure
- legacy field names from `opencli`
- transport details
- browser/CDP details
- request signing or feature-flag internals

---

## 7. Error model

The native X source should define explicit error categories such as:

- `AuthError`
- `TransportError`
- `RateLimitError`
- `SchemaError`
- `SourceUnavailableError`

This matters because the current Phase 1 runtime already distinguishes runtime states (`SUCCESS / EMPTY / FAILED`), and native source migration should improve—not blur—diagnostics.

### Mapping expectation

At the lane/runtime boundary:
- auth/transport/schema failures should become structured run errors
- empty feed should remain distinguishable from source breakage
- diagnose should be able to report the specific failing layer

---

## 8. Config design

The migration must remove `opencli`-specific config semantics.

### Current style to remove
Examples that should disappear from supported config shape:
- `lanes.x-feed.opencli.path`
- `lanes.x-feed.opencli.limit`

### Native config direction
Config should describe the source itself, not the legacy backend. Example shape:

```yaml
lanes:
  x-feed:
    enabled: true
    source:
      limit: 100
      timeout_seconds: 30
      auth:
        cookie_file: ~/.signal-engine/x-cookies.json
```

Field names may differ in implementation, but the rule is fixed:

> config must express native source concerns, not legacy backend plumbing.

---

## 9. Diagnose design

`diagnose --lane x-feed` must stop checking `opencli`-specific runtime assumptions.

### Old assumptions to remove
- `dist/main.js` existence
- `node ... twitter timeline ...` probe
- `opencli binary` wording

### New diagnose checks
Recommended minimal checks:

1. source config exists and is parseable
2. auth material exists
3. auth material is structurally valid
4. native timeline probe executes
5. probe response parses into normalized source fields
6. output data directory is writable

### Diagnose output should report native concerns
Examples:
- auth state: OK / FAIL
- timeline probe: OK / FAIL
- response parse: OK / FAIL
- output dir: OK / FAIL

This is a system-level requirement, not just wording cleanup.

---

## 10. Data flow

Post-migration `x-feed` flow should be:

1. `collect_x_feed()` calls native source entry point
2. source loads auth, performs timeline request, parses response, returns normalized tweets
3. lane maps normalized tweets into `SignalRecord`
4. runtime writes:
   - signal markdown files
   - `index.md`
   - `run.json`

The runtime remains the owner of:
- run state
- artifact discipline
- final status semantics
- receipt generation

The source remains the owner of:
- acquisition
- normalization
- source-specific failure classification

---

## 11. Verification strategy

Because there will be no in-product dual backend, verification has to be explicit and disciplined.

## 11.1 Field-level verification

Use side-by-side comparison during migration work (outside product runtime if needed) to verify that native source output matches the old backend on the fields that matter:

- item count expectations
- `id`
- `author`
- `url`
- `text`
- engagement fields
- timestamp presence/shape

This comparison can be done with temporary scripts, fixtures, or migration notebooks, but should not become a permanent runtime feature.

## 11.2 Artifact-level verification

Run native `x-feed` collection and verify that:
- `signals_written` is sensible
- frontmatter fields remain compatible
- `index.md` structure remains usable
- `run.json` remains a truthful final receipt

## 11.3 Failure-mode verification

Explicitly test:
- missing/invalid auth
- transport failure
- schema parse failure
- empty feed
- partial signal write failure
- index write failure
- run manifest write failure

---

## 12. Testing expectations

Native migration should add or update tests in at least these areas:

### Source tests
- auth loading success/failure
- timeline fetch success
- parser success on representative fixture
- parser/schema failure on malformed fixture

### Lane/runtime tests
- native source success path
- native empty-source path
- native source error path
- partial signal write failure
- final `run.json` reflects final status

### Diagnose tests
- auth failure reported correctly
- parse failure reported correctly
- probe success/failure semantics

### Compatibility tests
- real artifact fields still match expected Phase 1 contract

---

## 13. Migration constraints

### Constraint 1: No runtime fallback backend
No `opencli_legacy` backend remains in the product runtime.

### Constraint 2: No partial cleanup accepted as complete
Removing `subprocess.run()` while leaving docs/config/diagnose opencli-shaped does not count as done.

### Constraint 3: No platform creep
Only migrate what is required for `x-feed` timeline collection. Do not use this effort to absorb unrelated X/article/search/following logic.

### Constraint 4: No runtime protocol breakage without explicit decision
If any artifact/frontmatter/run-manifest contract needs to change, that must be a separate design decision—not a side effect of source migration.

---

## 14. Major risks

## 14.1 Auth handling is the highest fragility area
If auth loading and auth diagnosis are not separated cleanly, failures will become harder—not easier—to debug.

## 14.2 Schema drift may be silently copied over
If parser logic is migrated without making schema assumptions explicit, `signal-engine` may inherit hidden fragility from the old backend while pretending to be cleaner.

## 14.3 Over-migration risk
There is real danger in importing too much opencli structure and ending up with `signal-engine` as a semi-forked copy of a larger tool.

### Required mitigation
Before implementation, enumerate exactly which X-specific logic is being migrated and which categories are explicitly excluded.

## 14.4 Validation gap risk
Without dual-runtime fallback, the migration must rely on stronger tests and explicit comparison discipline. If verification is weak, the system may look independent while field semantics have drifted.

---

## 15. Recommendation

Proceed with a **controlled native-source migration**:

- preserve current runtime/artifact architecture
- migrate only the minimal X timeline acquisition logic needed for `x-feed`
- reorganize migrated logic into `signal-engine`'s own source subsystem boundaries
- remove `opencli` from runtime, config, diagnostics, tests, and supported docs
- rely on explicit migration-time verification rather than permanent dual-backend support

This achieves the chosen goal:

> Signal Engine owns `x-feed` end-to-end as a product system, while avoiding the cost of a full greenfield X reverse-engineering project.

---

## 16. Next step

If this design is approved, the next document should be an implementation plan that breaks the migration into concrete tasks, including:
- source subsystem creation
- config migration
- diagnose rewrite
- test migration
- compatibility verification
- cleanup/removal of old `opencli` dependency references
