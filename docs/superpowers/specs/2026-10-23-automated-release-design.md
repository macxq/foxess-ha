# Design Document: Automated Releases via PR Validation & RELEASES.md

**Date:** 2026-10-23  
**Status:** Draft  
**Target:** FoxESS Home Assistant Integration (`foxess-ha`)

---

## 1. Intent & Context

Currently, releases for the FoxESS Home Assistant integration are created manually using the GitHub CLI or web UI after merging PRs. Version numbers are manually updated in `custom_components/foxess/manifest.json`. This manual process can lead to forgotten releases, mismatched versions, or release notes not being version-controlled in the repository.

The goal is to introduce an automated, robust release mechanism that:
1. Keeps release notes and metadata version-controlled in a dedicated `RELEASES.md` file.
2. Enforces consistency between `custom_components/foxess/manifest.json` and `RELEASES.md` in every Pull Request via a blocking CI check.
3. Automatically creates a git tag and GitHub Release when a PR containing a version bump is merged into `main`.

---

## 2. Goals, Non-Goals & Anti-Goals

### Goals
- **Single Source of Release History:** Track all releases, titles, and release notes in a root `RELEASES.md` file.
- **Pre-Merge Validation:** Block merging any PR where `manifest.json`'s version does not match the latest release entry in `RELEASES.md`.
- **Zero-Overhead Merging:** When merging a PR with a version bump, GitHub Actions automatically handles tag creation and GitHub Release publication without any manual intervention.
- **Support for Non-Release PRs:** PRs that do not bump versions (e.g., test improvements, chore refactoring) do not trigger new releases.
- **Full Test Coverage:** Provide automated unit tests for the parsing and validation logic.

### Non-Goals
- **Automated SemVer Deduction:** We do not automatically calculate major/minor/patch numbers from commit messages (like `semantic-release`). The PR author explicitly chooses the version.
- **Post-Merge Commits by Bots:** The workflow will not commit back to `main` (no "bump version" bot commits). Everything needed for the release is contained within the PR.

### Anti-Goals
- **Accidental Releases:** A PR merged without an intentional version bump must never trigger a duplicate or unintended release.
- **Silent Failures:** If a release step fails (e.g., token permissions, malformed YAML), CI must fail visibly.

---

## 3. Architecture & File Format

### 3.1 `RELEASES.md` Format
A Markdown file at repository root with per-release sections containing YAML metadata:

```markdown
# Releases

## [v0.56]
```yaml
title: "v0.56 - Native aiohttp Client & cloud_polling Refactor (#389)"
date: "2026-10-23"
```

### 🚀 Native aiohttp Client & Modernized Cloud Architecture (#389)

• Native aiohttp Session: Replaced legacy synchronous `RestData` objects...
```

- Each release section starts with a Markdown heading containing the version tag: `## [vX.YY]` or `## vX.YY`.
- A fenced YAML code block immediately follows the heading, containing at least:
  - `title`: String used for the GitHub Release title.
  - `date`: Release date (YYYY-MM-DD).
- The rest of the section until the next `##` heading is the Markdown release notes / body.

### 3.2 Helper Utility (`scripts/release_helper.py`)
A standalone Python script (standard library only, `pathlib`, `json`, `re`, `argparse`, `sys`, with optional fallback or PyYAML/lightweight parser for the simple key-value block) providing CLI commands:
- `validate`:
  - Parses `custom_components/foxess/manifest.json` to get `current_version`.
  - Parses the top entry in `RELEASES.md` to get `latest_release_version`, `title`, and `body`.
  - Asserts `current_version == latest_release_version`.
  - Verifies required YAML fields (`title`).
  - Returns exit code 0 on success, exit code 1 with clear diagnostic error message on failure.
- `extract-latest`:
  - Outputs a JSON object `{"version": "...", "title": "...", "body": "..."}` or sets GitHub Actions step outputs (`version`, `title`, `body`).
- `check-bump`:
  - Compares `manifest.json["version"]` against existing git tags (`git tag -l`).
  - Returns whether this version is already tagged (`is_new=true` or `is_new=false`).

### 3.3 CI/CD Workflows

#### A. Pre-Merge PR Check (`.github/workflows/tests.yaml` or `release-check.yaml`)
- Runs on `pull_request` and `push` to branches.
- Executes `python3 scripts/release_helper.py validate`.
- If `manifest.json` and `RELEASES.md` are not in sync, the check fails, blocking merge.

#### B. Post-Merge Release Automation (`.github/workflows/release.yaml`)
- Triggers on `push` to `main`.
- Runs `scripts/release_helper.py check-bump`.
- If `is_new == 'false'`:
  - Logs "Version vX.YY already released or not bumped. Skipping release." and exits cleanly.
- If `is_new == 'true'`:
  - Extracts release title and body using `release_helper.py`.
  - Uses `gh release create <tag> --title "<title>" --notes-file <file>` with `GITHUB_TOKEN` permissions (`contents: write`).

---

## 4. Error Handling & Edge Cases

1. **PR without Version Bump:** Both `manifest.json` and `RELEASES.md` have the existing version (e.g. `v0.56`). The PR validation passes (`manifest == releases`). After merge to `main`, `check-bump` sees tag `v0.56` already exists and exits without creating a release.
2. **Author bumps `manifest.json` but forgets `RELEASES.md`:** PR validation fails: `Version mismatch: manifest.json has v0.57, but RELEASES.md latest entry is v0.56`. Merge is blocked.
3. **Author adds entry to `RELEASES.md` but forgets `manifest.json`:** PR validation fails: `Version mismatch: manifest.json has v0.56, but RELEASES.md latest entry is v0.57`. Merge is blocked.
4. **Malformed YAML block:** PR validation fails with a parse error indicating the line number.

---

## 5. Security & Permissions
- GitHub Actions workflow requires `permissions: contents: write` to create git tags and GitHub releases.
- No third-party untrusted actions required; can use native `gh` CLI built into GitHub Actions runners (`ubuntu-latest`).

---

## 6. Implementation Scope & Division of Work
- **Design:** This document (`docs/superpowers/specs/2026-10-23-automated-release-design.md`).
- **Builder responsibilities:**
  1. Create initial `RELEASES.md` seeded with current `v0.56` release notes.
  2. Implement `scripts/release_helper.py`.
  3. Write unit tests for `scripts/release_helper.py` in `tests/test_release_helper.py`.
  4. Add pre-merge validation step to PR workflow.
  5. Add `.github/workflows/release.yaml` for post-merge automated releases.
