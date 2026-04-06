# signals-engine Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the project end-to-end from `signal-engine` / `signal_engine` to `signals-engine` / `signals_engine`, including local directory, Python package/import path, CLI metadata, docs, tests, and GitHub repository naming, while keeping the system buildable and testable at each checkpoint.

**Architecture:** Treat this as a pure rename migration, not a refactor. This is an intentional breaking rename: the old package/CLI names are not preserved as first-class compatibility surfaces. First capture a rollback point and confirm the new PyPI name is already valid, then add focused rename-safety tests, then rename Python package/module paths, then update packaging and user-facing docs/commands, and only after code/tests are green perform repository/path renames and final verification. Keep changes narrowly scoped to naming so failures are easy to localize.

**Tech Stack:** Python 3.11, setuptools, twine, unittest, gh CLI, git, PyPI, GitHub

---

## File / Surface Impact Map

### Code and packaging
- Modify: `pyproject.toml` — published package name, console-script entrypoint, package discovery assumptions.
- Rename directory: `src/signal_engine/` -> `src/signals_engine/` — primary Python package path.
- Rename metadata dir if recreated by build: `src/signal_engine.egg-info/` -> generated as `src/signals_engine.egg-info/`.
- Search/update all Python imports across source and tests from `signal_engine` to `signals_engine`.

### Tests
- Modify: `tests/test_cli_entrypoint.py` — module invocation/import strings.
- Modify: `tests/test_render.py`
- Modify: `tests/test_runtime_debug_logging.py`
- Modify: `tests/test_x_feed_collect.py`
- Modify: `tests/test_x_feed_diagnose_native.py`
- Modify: `tests/test_x_source.py`
- Add (if needed): `tests/test_package_imports.py` — focused import/CLI smoke tests for new package path.

### Docs / user-facing strings
- Modify: `README.md` — install command, package name, import/module examples, repo references.
- Search/update docs under `docs/` and scripts/comments if they mention `signal-engine` or `signal_engine` as the canonical project/package name.

### Repo / path surfaces
- Rename local directory after code is green: `/Users/haha/workspace/signal-engine` -> `/Users/haha/workspace/signals-engine`.
- Rename GitHub repo after local verification: `T0UGH/signal-engine` -> `T0UGH/signals-engine`.
- Verify `origin` remote URL after repo rename.
- Audit absolute-path assumptions before the filesystem move, especially docs, shell snippets, configs, fixtures, and generated examples that may embed `/Users/haha/workspace/signal-engine`.
- Audit external rename fallout after GitHub repo rename: badges, release URLs, repo homepage links, GitHub Actions references, webhooks/integrations, and any automation keyed by old repo name.

### Migration policy
- This is a breaking rename. Old canonical names (`signal-engine`, `signal_engine`, `signal-engine` console script) are being retired rather than maintained as compatibility aliases.
- `signals-engine` PyPI package name has already been validated in practice by a successful `0.1.0` upload; do not reopen package-name selection unless a new blocker appears.

### Generated / cleanup
- Remove and regenerate: `dist/`, `build/`, old `*.egg-info/` before final packaging validation.
- Decide explicitly whether to keep or ignore `uv.lock`; do not let it ride along accidentally.

---

## Task 0: Create rollback point and record migration assumptions

**Files / surfaces:**
- Git history / branch state
- Current published package state

- [ ] **Step 1: Record the current green baseline commit**

Run:
```bash
cd /Users/haha/workspace/signal-engine
git rev-parse HEAD
git status --short
```
Expected: capture the exact pre-rename commit hash and any existing working-tree changes.

- [ ] **Step 2: Create an isolated rename branch**

Run:
```bash
cd /Users/haha/workspace/signal-engine
git checkout -b chore/signals-engine-rename
```
Expected: rename work no longer happens on the previous branch tip directly.

- [ ] **Step 3: Record the breaking-change policy in the branch context**

Write/update the plan notes or commit message guidance so implementation explicitly assumes:
- no compatibility alias for `signal_engine`
- no compatibility alias for `signal-engine` CLI
- no compatibility alias for old PyPI package name

- [ ] **Step 4: Confirm the new PyPI name is already valid and published**

Check:
- `https://pypi.org/project/signals-engine/`

Expected: `signals-engine` already exists under the intended account because `0.1.0` was successfully uploaded.

- [ ] **Step 5: Commit or at least checkpoint the migration branch start**

Optional lightweight checkpoint:
```bash
git status --short
```
Expected: clear understanding of branch starting state before renames begin.

---

## Task 1: Freeze baseline and add rename safety checks

**Files:**
- Modify: `tests/test_cli_entrypoint.py`
- Create: `tests/test_package_imports.py`

- [ ] **Step 1: Inspect current import/module assumptions**

Run:
```bash
cd /Users/haha/workspace/signal-engine
rg -n "signal_engine|signal-engine" src tests README.md pyproject.toml docs scripts
```
Expected: a complete list of old-name references to migrate.

- [ ] **Step 2: Add a focused import smoke test for the future package name**

Create `tests/test_package_imports.py`:
```python
import importlib


def test_signals_engine_package_importable():
    pkg = importlib.import_module("signals_engine")
    assert pkg is not None


def test_signals_engine_cli_module_importable():
    mod = importlib.import_module("signals_engine.cli")
    assert hasattr(mod, "main")
```

- [ ] **Step 3: Update CLI entrypoint test to target the future module name**

In `tests/test_cli_entrypoint.py`, change module execution/import expectations from `signal_engine.cli` to `signals_engine.cli`.

- [ ] **Step 4: Run the focused tests and confirm they fail for the right reason**

Run:
```bash
cd /Users/haha/workspace/signal-engine
python3.11 -m unittest tests.test_cli_entrypoint tests.test_package_imports -v
```
Expected: FAIL with import/module-not-found errors referencing `signals_engine`.

- [ ] **Step 5: Commit the failing-test checkpoint**

```bash
git add tests/test_cli_entrypoint.py tests/test_package_imports.py
git commit -m "test: add rename safety checks for signals_engine package"
```

---

## Task 2: Rename the Python package and internal imports

**Files:**
- Rename: `src/signal_engine/` -> `src/signals_engine/`
- Modify: all Python files under `src/signals_engine/`
- Modify: all Python tests under `tests/`

- [ ] **Step 1: Rename the package directory**

Run:
```bash
cd /Users/haha/workspace/signal-engine
mv src/signal_engine src/signals_engine
```

- [ ] **Step 2: Rewrite source imports to the new package path**

Run a targeted replacement across source/tests for import forms such as:
- `from signal_engine...`
- `import signal_engine...`
- `python -m signal_engine.cli`

Use a scripted replacement or careful editor-wide rename; do not hand-edit ad hoc.

- [ ] **Step 3: Update `__init__` package markers if needed**

Ensure `src/signals_engine/__init__.py` still exists and exports exactly what the old package exported.

- [ ] **Step 4: Run focused rename tests**

Run:
```bash
cd /Users/haha/workspace/signal-engine
python3.11 -m unittest tests.test_cli_entrypoint tests.test_package_imports -v
```
Expected: PASS.

- [ ] **Step 5: Run the full test suite**

Run:
```bash
cd /Users/haha/workspace/signal-engine
python3.11 -m unittest discover -s tests -v
```
Expected: all tests PASS under `signals_engine` imports.

- [ ] **Step 6: Commit package rename**

```bash
git add src tests
git commit -m "refactor: rename python package to signals_engine"
```

---

## Task 3: Update packaging metadata and CLI installation surfaces

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`

- [ ] **Step 1: Update package metadata in `pyproject.toml`**

Ensure:
```toml
[project]
name = "signals-engine"

[project.scripts]
signals-engine = "signals_engine.cli:main"
```

Also verify setuptools package discovery still points at `src` and does not hardcode the old package path.

- [ ] **Step 2: Update README install and usage examples**

At minimum replace old canonical forms with new ones:
```bash
pip install signals-engine
signals-engine --help
python3.11 -m signals_engine.cli --help
```

- [ ] **Step 3: Search for remaining old public-name references**

Run:
```bash
cd /Users/haha/workspace/signal-engine
rg -n "signal-engine|signal_engine" README.md pyproject.toml docs scripts tests src
```
Expected: only intentional historical references remain (if any). Prefer zero old canonical references.

- [ ] **Step 4: Rebuild from scratch**

Run:
```bash
cd /Users/haha/workspace/signal-engine
rm -rf dist build src/*.egg-info
python3.11 -m build
python3.11 -m twine check dist/*
```
Expected: build succeeds and produces `signals_engine-<version>` artifacts.

- [ ] **Step 5: Verify installed console entrypoint metadata**

Run:
```bash
cd /Users/haha/workspace/signal-engine
python3.11 - <<'PY'
import zipfile
from pathlib import Path
wheel = sorted(Path('dist').glob('signals_engine-*.whl'))[-1]
with zipfile.ZipFile(wheel) as zf:
    ep = [n for n in zf.namelist() if n.endswith('entry_points.txt')][0]
    print(zf.read(ep).decode())
PY
```
Expected output includes:
```ini
[console_scripts]
signals-engine = signals_engine.cli:main
```

- [ ] **Step 6: Commit packaging/doc rename**

```bash
git add pyproject.toml README.md
git commit -m "build: rename package metadata and CLI to signals-engine"
```

---

## Task 4: Update docs, scripts, and operational references

**Additional requirement:** this task must explicitly audit both hardcoded absolute paths and GitHub-repo-linked surfaces, not just generic old-name strings.

**Files:**
- Modify: all docs under `docs/` that reference the old project name/path
- Modify: `scripts/check_no_opencli.py` (only if it references old module names in strings/tests)
- Modify: `scripts/migrate_x_feed_config.py` (same rule)

- [ ] **Step 1: Search the repo for remaining old references and hardcoded paths**

Run:
```bash
cd /Users/haha/workspace/signal-engine
rg -n "signal-engine|signal_engine|/Users/haha/workspace/signal-engine|T0UGH/signal-engine" .
```
Expected: reviewable list of leftover names, URLs, and absolute-path assumptions.

- [ ] **Step 2: Update docs and scripts to the new canonical names**

Examples to normalize:
- local path -> `/Users/haha/workspace/signals-engine`
- repo URL -> `https://github.com/T0UGH/signals-engine`
- module path -> `signals_engine`
- CLI command -> `signals-engine`

- [ ] **Step 3: Audit GitHub-linked surfaces before repo rename**

Explicitly inspect and update, where applicable:
- README badges
- release/documentation links
- project homepage metadata
- GitHub Actions workflow strings
- webhook/integration configs checked into the repo

- [ ] **Step 4: Run tests again if any executable code or test fixtures changed**

Run:
```bash
cd /Users/haha/workspace/signal-engine
python3.11 -m unittest discover -s tests -v
```
Expected: PASS.

- [ ] **Step 5: Commit docs/script rename sweep**

```bash
git add docs scripts tests README.md
git commit -m "docs: align repo references with signals-engine rename"
```

---

## Task 5: Rename the GitHub repository and local working directory

**Files / surfaces:**
- External surface: GitHub repo `T0UGH/signal-engine`
- Filesystem path: `/Users/haha/workspace/signal-engine`

- [ ] **Step 1: Rename the GitHub repo via `gh`**

Run:
```bash
cd /Users/haha/workspace/signal-engine
gh repo rename signals-engine --repo T0UGH/signal-engine
```
Expected: repo becomes `T0UGH/signals-engine`.

- [ ] **Step 2: Verify the new repo identity**

Run:
```bash
gh repo view T0UGH/signals-engine --json nameWithOwner,url,visibility
```
Expected JSON includes:
- `"nameWithOwner":"T0UGH/signals-engine"`

- [ ] **Step 3: Rename the local directory**

Run from parent dir:
```bash
cd /Users/haha/workspace
mv signal-engine signals-engine
cd /Users/haha/workspace/signals-engine
```

- [ ] **Step 4: Verify git remote and local status after rename**

Run:
```bash
cd /Users/haha/workspace/signals-engine
git remote -v
git status --short
pwd
```
Expected:
- remote URL points to `T0UGH/signals-engine`
- working tree status is understood/clean except intentional files
- pwd is `/Users/haha/workspace/signals-engine`

- [ ] **Step 5: Commit any path-reference fixups caused by the rename**

```bash
cd /Users/haha/workspace/signals-engine
git add -A
git commit -m "chore: rename repo and workspace path to signals-engine"
```

---

## Task 6: Final verification and publish-state cleanup

**Files / surfaces:**
- Entire repo

- [ ] **Step 1: Run end-to-end verification from the renamed directory**

Run:
```bash
cd /Users/haha/workspace/signals-engine
python3.11 -m unittest discover -s tests -v
python3.11 -m build
python3.11 -m twine check dist/*
python3.11 -m signals_engine.cli --help
```
Expected: all commands succeed.

- [ ] **Step 2: Verify PyPI page and install command match the rename**

Check manually or via web:
- `https://pypi.org/project/signals-engine/`

Then smoke-test install in a clean environment if practical:
```bash
python3.11 -m venv /tmp/signals-engine-smoke
source /tmp/signals-engine-smoke/bin/activate
pip install signals-engine
signals-engine --help
python -c "import signals_engine; print(signals_engine.__file__)"
```
Expected: install/import/CLI all work.

- [ ] **Step 3: Decide on `uv.lock` explicitly**

Either:
- commit it intentionally, or
- add/keep ignore policy and remove from working tree noise.

Do not leave it as unexplained untracked state.

- [ ] **Step 4: Push all rename commits**

```bash
cd /Users/haha/workspace/signals-engine
git push origin main
```
Expected: remote updated successfully.

- [ ] **Step 5: Record final outcome**

Summarize for handoff:
- final repo path
- final GitHub URL
- final PyPI package name
- final import name
- verification commands run
- final commit hash

---

## Acceptance Criteria

- Local workspace directory is `signals-engine`.
- GitHub repository is `T0UGH/signals-engine`.
- PyPI package name is `signals-engine`.
- Python package/import path is `signals_engine`.
- Console script is `signals-engine`.
- `python3.11 -m unittest discover -s tests -v` passes.
- `python3.11 -m build` and `python3.11 -m twine check dist/*` pass.
- `python3.11 -m signals_engine.cli --help` works.
- No unintended canonical references to `signal-engine` / `signal_engine` remain outside historical documentation.
