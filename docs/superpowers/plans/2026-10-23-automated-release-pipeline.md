# Automated Release Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement automated release creation on merge to `main` by validating version synchronization between `manifest.json` and a root `RELEASES.md` file in PRs and executing `gh release create` in CI.

**Architecture:** A lightweight Python 3 utility (`scripts/release_helper.py`) parses `RELEASES.md` (Markdown with YAML metadata blocks) and compares versions with `custom_components/foxess/manifest.json`. A GitHub Actions PR check executes this validation to block inconsistent merges. A post-merge GitHub Action detects new version bumps against git tags and publishes GitHub Releases using the GitHub CLI.

**Tech Stack:** Python 3 (standard library), pytest, GitHub Actions (`gh` CLI, `actions/checkout`).

**Spec:** `docs/superpowers/specs/2026-10-23-automated-release-design.md`

## Global Constraints

- Python 3 standard library only for `scripts/release_helper.py` (no third-party dependencies so it runs in bare CI without extra installations).
- Version tag format: `vX.YY` (e.g. `v0.56`).
- Manifest path: `custom_components/foxess/manifest.json`.
- Releases document path: `RELEASES.md`.
- Workflow permission: `contents: write` for `.github/workflows/release.yaml`.

## Review Focus

- Malformed YAML code block under a release heading in `RELEASES.md` -> validator must exit code 1 with line number and syntax error description.
- Release version in `manifest.json` does not match latest heading in `RELEASES.md` -> validator must exit code 1 showing both versions clearly.
- `RELEASES.md` has missing required metadata field (`title`) -> validator must exit code 1 reporting missing required field.
- Release section contains empty body -> validator must exit code 1 reporting that release notes body cannot be empty.
- Version is already tagged in git -> `check-bump` command must report `is_new=false` so post-merge CI skips without error.

---

### Task 1: Initialize `RELEASES.md` with v0.56 Notes

**Files:**
- Create: `RELEASES.md`
- Test: `tests/test_release_helper.py` (added in Task 2)

**Interfaces:**
- Consumes: None (seeds base documentation file)
- Produces: `RELEASES.md` formatted with `## [v0.56]` heading, YAML metadata (`title`, `date`), and markdown notes.

- [ ] **Step 1: Create `RELEASES.md` at repository root**

Create `RELEASES.md` with:
```markdown
# Releases

## [v0.56]
```yaml
title: "v0.56 - Native aiohttp Client & cloud_polling Refactor (#389)"
date: "2026-10-23"
```

### 🚀 Native aiohttp Client & Modernized Cloud Architecture (#389)

• **Native aiohttp Session**: Replaced legacy synchronous `RestData` objects across all 6 FoxESS OpenAPI endpoints (`getOADeviceDetail`, `getOADeviceList`, `getOABatterySettings`, `getReport`, `getReportDailyGeneration`, and `getRaw`) with Home Assistant's native `async_get_clientsession(hass)` in a centralized `FoxESSApiClient`.
• **Metadata Classification**: Updated `iot_class` to `cloud_polling` and removed unnecessary `rest` core dependency in `manifest.json`.
• **Centralized Architecture (`api.py` & `const.py`)**: Extracted all API endpoints, configuration constants, HTTP headers, MD5 signature generation (`GetAuth`), token handling, rate limiting (`wait_for_api`), and error/errno code mapping into reusable modules.
• **Preserved Reliability**: Retains all existing entity unique IDs, device grouping, age and offset checks, energy decay prevention, and daily generation resilience features (#324).
• **Full Backward Compatibility**: Fully backwards compatible with existing YAML and UI config entries.
• **Test Suite**: Added comprehensive unit test coverage for `FoxESSApiClient` (`tests/test_api.py`) and updated test suite to verify 65/65 passing tests.
```

- [ ] **Step 2: Verify `RELEASES.md` exists and is readable**

Run: `test -f RELEASES.md && echo "RELEASES.md exists"`  
Expected: `RELEASES.md exists`

- [ ] **Step 3: Commit**

```bash
git add RELEASES.md
git commit -m "docs: seed RELEASES.md with v0.56 release notes"
```

---

### Task 2: Implement and Test `scripts/release_helper.py`

**Files:**
- Create: `scripts/release_helper.py`
- Create: `tests/test_release_helper.py`

**Interfaces:**
- Consumes: `RELEASES.md`, `custom_components/foxess/manifest.json`, `git tag -l`
- Produces: CLI commands:
  - `python3 scripts/release_helper.py validate [--manifest PATH] [--releases PATH]`
  - `python3 scripts/release_helper.py extract-latest [--releases PATH]`
  - `python3 scripts/release_helper.py check-bump [--manifest PATH]`

- [ ] **Step 1: Write the failing tests in `tests/test_release_helper.py`**

Write test functions in `tests/test_release_helper.py`:
- `test_parse_releases_valid()`
- `test_parse_releases_missing_yaml()`
- `test_parse_releases_missing_title()`
- `test_validate_matching_version()`
- `test_validate_mismatched_version()`
- `test_check_bump_existing_tag()`
- `test_check_bump_new_tag()`
- `test_extract_latest_json()`

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_release_helper.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'` or `FileNotFoundError`

- [ ] **Step 3: Implement `scripts/release_helper.py`**

Create `scripts/release_helper.py` implementing:
- `parse_releases_file(releases_path: Path) -> dict`: Parses sections starting with `## [vX.YY]` or `## vX.YY`. Extracts YAML block between ````yaml` and ```` into key-value pairs (handling simple YAML without external dependency), and remaining markdown as `body`.
- `validate_manifest_and_releases(manifest_path: Path, releases_path: Path) -> tuple[bool, str]`: Validates version match and non-empty metadata/body.
- `check_bump(manifest_path: Path, existing_tags: list[str]) -> bool`: Returns `True` if `manifest_version` is NOT in `existing_tags`.
- CLI commands: `validate`, `extract-latest`, `check-bump`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_release_helper.py -v`  
Expected: PASS (all tests pass)

- [ ] **Step 5: Run validation against actual repo files**

Run: `python3 scripts/release_helper.py validate`  
Expected: PASS with exit code 0 (`Validation successful: v0.56 matches between manifest.json and RELEASES.md`)

- [ ] **Step 6: Commit**

```bash
git add scripts/release_helper.py tests/test_release_helper.py
git commit -m "feat: add release_helper script and tests"
```

---

### Task 3: Integrate Pre-Merge Validation into PR Workflow

**Files:**
- Modify: `.github/workflows/tests.yaml`

**Interfaces:**
- Consumes: `python3 scripts/release_helper.py validate`
- Produces: Failing CI step on PRs if `manifest.json` and `RELEASES.md` are out of sync.

- [ ] **Step 1: Check existing `.github/workflows/tests.yaml`**

Run: `cat .github/workflows/tests.yaml`

- [ ] **Step 2: Add validation step to `.github/workflows/tests.yaml`**

Add step before or after pytest:
```yaml
      - name: Validate Release & Manifest Version Sync
        run: |
          python3 scripts/release_helper.py validate
```

- [ ] **Step 3: Run full pytest suite including new release tests**

Run: `.venv/bin/pytest tests/ -v`  
Expected: All tests pass (65 existing tests + new release helper tests).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tests.yaml
git commit -m "ci: add manifest and release notes synchronization check"
```

---

### Task 4: Add Post-Merge Automated Release Workflow

**Files:**
- Create: `.github/workflows/release.yaml`

**Interfaces:**
- Consumes: `push: branches: [main]`, `scripts/release_helper.py`
- Produces: Automated tag creation and `gh release create` when a new version is detected.

- [ ] **Step 1: Create `.github/workflows/release.yaml`**

Create `.github/workflows/release.yaml`:
```yaml
name: Automated Release

on:
  push:
    branches:
      - main

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code with full tag history
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Check if version needs release
        id: check_release
        run: |
          python3 scripts/release_helper.py check-bump >> "$GITHUB_OUTPUT"

      - name: Publish GitHub Release
        if: steps.check_release.outputs.is_new == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python3 scripts/release_helper.py extract-latest > release_info.json
          VERSION=$(python3 -c "import json; print(json.load(open('release_info.json'))['version'])")
          TITLE=$(python3 -c "import json; print(json.load(open('release_info.json'))['title'])")
          python3 -c "import json; open('notes.md', 'w').write(json.load(open('release_info.json'))['body'])"
          
          echo "Publishing release $VERSION: $TITLE"
          gh release create "$VERSION" --title "$TITLE" --notes-file notes.md
```

- [ ] **Step 2: Test `check-bump` locally against current git tags**

Run: `python3 scripts/release_helper.py check-bump`  
Expected: `is_new=false` (since `v0.56` is already tagged).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yaml
git commit -m "ci: add automated release workflow on merge to main"
```

---

### Task 5: End-to-End Verification and Dry Run

**Files:**
- None modified directly (verification task)

**Interfaces:**
- Consumes: all files from Tasks 1-4
- Produces: Verified test runs and dry-run execution proof.

- [ ] **Step 1: Run complete test suite**

Run: `.venv/bin/pytest tests/`  
Expected: 100% tests pass.

- [ ] **Step 2: Run dry-run checks for all helper subcommands**

Run:
```bash
python3 scripts/release_helper.py validate
python3 scripts/release_helper.py check-bump
python3 scripts/release_helper.py extract-latest
```
Expected: All exit with code 0 and valid outputs.

- [ ] **Step 3: Verify git status is clean**

Run: `git status`  
Expected: Clean working tree.
