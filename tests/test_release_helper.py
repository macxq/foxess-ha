"""Tests for scripts/release_helper.py."""

from pathlib import Path
import json
import pytest

from scripts.release_helper import (
    parse_releases_file,
    validate_manifest_and_releases,
    check_bump,
    extract_latest,
    normalize_markdown_bullets,
    clean_release_title,
)

SAMPLE_VALID_RELEASES = """# Releases

## [v0.56]
```yaml
title: "v0.56 - Native aiohttp Client & cloud_polling Refactor (#389)"
date: "2026-10-23"
```

### Changes
• Native aiohttp Session
• Centralized Architecture
"""

SAMPLE_MULTIPLE_RELEASES = """# Releases

## [v0.56]
```yaml
title: "v0.56 - Latest Release"
date: "2026-10-23"
```

Latest body.

## [v0.55]
```yaml
title: "v0.55 - Older Release"
date: "2026-10-22"
```

Older body.
"""

SAMPLE_MISSING_YAML = """# Releases

## [v0.56]
Just plain text without yaml block.
"""

SAMPLE_MISSING_TITLE = """# Releases

## [v0.56]
```yaml
date: "2026-10-23"
```

Some notes.
"""

SAMPLE_EMPTY_BODY = """# Releases

## [v0.56]
```yaml
title: "v0.56 - No body"
date: "2026-10-23"
```
"""


def test_parse_releases_valid(tmp_path: Path):
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(SAMPLE_VALID_RELEASES)

    release = parse_releases_file(rel_file)
    assert release["version"] == "v0.56"
    assert release["title"] == "Native aiohttp Client & cloud_polling Refactor (#389)"
    assert release["raw_title"] == "v0.56 - Native aiohttp Client & cloud_polling Refactor (#389)"
    assert release["date"] == "2026-10-23"
    assert "- Native aiohttp Session" in release["body"]


def test_parse_releases_takes_latest(tmp_path: Path):
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(SAMPLE_MULTIPLE_RELEASES)

    release = parse_releases_file(rel_file)
    assert release["version"] == "v0.56"
    assert release["title"] == "Latest Release"
    assert release["body"] == "Latest body."


def test_parse_releases_missing_yaml(tmp_path: Path):
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(SAMPLE_MISSING_YAML)

    with pytest.raises(ValueError, match="```yaml metadata block"):
        parse_releases_file(rel_file)


def test_parse_releases_missing_title(tmp_path: Path):
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(SAMPLE_MISSING_TITLE)

    with pytest.raises(ValueError, match="missing required 'title'"):
        parse_releases_file(rel_file)


def test_parse_releases_empty_body(tmp_path: Path):
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(SAMPLE_EMPTY_BODY)

    with pytest.raises(ValueError, match="body cannot be empty"):
        parse_releases_file(rel_file)


def test_validate_matching_version(tmp_path: Path):
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({"version": "v0.56"}))
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(SAMPLE_VALID_RELEASES)

    is_valid, msg = validate_manifest_and_releases(manifest_file, rel_file)
    assert is_valid is True
    assert "matches" in msg


def test_validate_mismatched_version(tmp_path: Path):
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({"version": "v0.57"}))
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(SAMPLE_VALID_RELEASES)

    is_valid, msg = validate_manifest_and_releases(manifest_file, rel_file)
    assert is_valid is False
    assert "v0.57" in msg
    assert "v0.56" in msg


def test_check_bump_existing_tag(tmp_path: Path):
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({"version": "v0.56"}))

    is_new = check_bump(manifest_file, existing_tags=["v0.55", "v0.56"])
    assert is_new is False


def test_check_bump_new_tag(tmp_path: Path):
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({"version": "v0.57"}))

    is_new = check_bump(manifest_file, existing_tags=["v0.55", "v0.56"])
    assert is_new is True


def test_extract_latest_json(tmp_path: Path):
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(SAMPLE_VALID_RELEASES)

    output = extract_latest(rel_file)
    data = json.loads(output)
    assert data["version"] == "v0.56"
    assert data["title"] == "Native aiohttp Client & cloud_polling Refactor (#389)"
    assert "- Native aiohttp Session" in data["body"]


def test_parse_releases_yaml_syntax_error_line_number(tmp_path: Path):
    content = """# Releases

## [v0.56]
```yaml
title: "v0.56 - Valid title"
malformed line without colon
date: "2026-10-23"
```

Body content.
"""
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(content)

    with pytest.raises(ValueError, match=r"syntax error.*line 6"):
        parse_releases_file(rel_file)


def test_parse_releases_semver_patch_version(tmp_path: Path):
    content = """# Releases

## [v0.56.1]
```yaml
title: "v0.56.1 - Patch Release"
date: "2026-10-24"
```

Patch notes.
"""
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(content)

    release = parse_releases_file(rel_file)
    assert release["version"] == "v0.56.1"
    assert release["title"] == "Patch Release"
    assert release["raw_title"] == "v0.56.1 - Patch Release"
    assert release["prerelease"] is False


def test_parse_releases_prerelease_detection(tmp_path: Path):
    content = """# Releases

## [v0.60-beta.1]
```yaml
title: "v0.60-beta.1 - Beta Release"
date: "2026-10-27"
```

Beta notes.
"""
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(content)

    release = parse_releases_file(rel_file)
    assert release["version"] == "v0.60-beta.1"
    assert release["title"] == "Beta Release"
    assert release["prerelease"] is True


def test_parse_releases_explicit_prerelease_flag(tmp_path: Path):
    content = """# Releases

## [v0.60]
```yaml
title: "v0.60 - Staging Release"
date: "2026-10-27"
prerelease: "true"
```

Staging notes.
"""
    rel_file = tmp_path / "RELEASES.md"
    rel_file.write_text(content)

    release = parse_releases_file(rel_file)
    assert release["version"] == "v0.60"
    assert release["prerelease"] is True


def test_normalize_markdown_bullets():
    raw = """• First item
• Second item
  • Indented sub-item
- Already a dash
* Asterisk list item
Plain paragraph line"""
    expected = """- First item
- Second item
  - Indented sub-item
- Already a dash
* Asterisk list item
Plain paragraph line"""
    assert normalize_markdown_bullets(raw) == expected


def test_clean_release_title():
    assert clean_release_title("v0.58 - Bug Fix (#394)", "v0.58") == "Bug Fix (#394)"
    assert clean_release_title("v0.58: Bug Fix (#394)", "v0.58") == "Bug Fix (#394)"
    assert clean_release_title("[v0.58] - Bug Fix (#394)", "v0.58") == "Bug Fix (#394)"
    assert clean_release_title("Bug Fix (#394)", "v0.58") == "Bug Fix (#394)"
    assert clean_release_title("v0.59 - Other Version", "v0.58") == "v0.59 - Other Version"
    # When title is just the version itself, keep it
    assert clean_release_title("v0.58", "v0.58") == "v0.58"


def test_get_git_tags_failure_raises(monkeypatch: pytest.MonkeyPatch):
    from scripts import release_helper
    import subprocess

    def fake_check_output(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["git", "tag", "-l"])

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    with pytest.raises(RuntimeError, match="Failed to retrieve git tags"):
        release_helper.get_git_tags()

