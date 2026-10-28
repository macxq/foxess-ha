#!/usr/bin/env python3
"""Release helper utility for FoxESS Home Assistant integration.

Validates version synchronization between manifest.json and RELEASES.md,
extracts release notes for CI, and checks whether a release bump is needed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def parse_yaml_block(yaml_text: str, start_line: int = 1, file_path: str = "RELEASES.md") -> dict[str, str]:
    """Parse a simple key-value YAML block with syntax validation and line reporting."""
    data: dict[str, str] = {}
    for idx, raw_line in enumerate(yaml_text.splitlines()):
        line_no = start_line + idx
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(
                f"YAML syntax error in {file_path} at line {line_no}: missing ':' in '{line}'"
            )
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        if not key:
            raise ValueError(
                f"YAML syntax error in {file_path} at line {line_no}: missing key before ':'"
            )
        # Strip surrounding quotes if present and verify matching quotes
        if val.startswith('"') or val.startswith("'"):
            quote_char = val[0]
            if len(val) < 2 or not val.endswith(quote_char):
                raise ValueError(
                    f"YAML syntax error in {file_path} at line {line_no}: unmatched quote in '{val}'"
                )
            val = val[1:-1]
        data[key] = val
    return data


def normalize_markdown_bullets(text: str) -> str:
    """Normalize unicode bullet points (•) at line starts to standard Markdown list items (-).

    This ensures Markdown parsers (e.g. Home Assistant HACS, GitHub) treat each entry
    as an unordered list item with a newline instead of collapsing lines into a single run-on paragraph.
    """
    return re.sub(r"^([ \t]*)•[ \t]*", r"\1- ", text, flags=re.MULTILINE)


def clean_release_title(title: str, version: str) -> str:
    """Strip redundant leading version prefix like 'v0.58 - ' or '[v0.58]: ' from title.

    Prevents Home Assistant HACS update changelog from displaying redundant version
    headings like 'v0.58 - v0.58 - Fix ...'.
    """
    cleaned = re.sub(r"^\[?" + re.escape(version) + r"\]?\s*[-:]\s*", "", title).strip()
    return cleaned or title


def parse_releases_file(releases_path: Path | str) -> dict[str, str]:
    """Parse the latest release entry from a releases Markdown file."""
    path = Path(releases_path)
    if not path.is_file():
        raise FileNotFoundError(f"Releases file not found: {path}")

    content = path.read_text(encoding="utf-8")

    # Match release sections: ## [v0.56], ## [v0.56.1], ## [v0.60.0b1], ## v0.56, etc.
    heading_pattern = re.compile(
        r"^##\s+\[?(v\d+(?:\.\d+)+(?:[.-]?[0-9A-Za-z.-]+)?)\]?\s*$", re.MULTILINE
    )
    matches = list(heading_pattern.finditer(content))
    if not matches:
        raise ValueError(f"No release headings (e.g. '## [v0.56]') found in {path}")

    # First match is the latest release
    latest_match = matches[0]
    version = latest_match.group(1)

    start_pos = latest_match.end()
    # End pos is either the next release heading or end of file
    end_pos = matches[1].start() if len(matches) > 1 else len(content)
    section_text = content[start_pos:end_pos].strip()

    # Find ```yaml ... ``` block
    yaml_match = re.search(r"```ya?ml\s*\n(.*?)\n```", section_text, re.DOTALL)
    if not yaml_match:
        raise ValueError(
            f"Release section for {version} in {path} is missing required ```yaml metadata block."
        )

    # Calculate 1-indexed line number in original file for YAML content
    yaml_start_in_file = content.find(section_text) + yaml_match.start(1)
    yaml_start_line = content[:yaml_start_in_file].count("\n") + 1

    metadata = parse_yaml_block(yaml_match.group(1), start_line=yaml_start_line, file_path=str(path))
    raw_title = metadata.get("title", "").strip()
    if not raw_title:
        raise ValueError(
            f"Release section for {version} in {path} is missing required 'title' in YAML metadata."
        )

    # Body is everything after the ```yaml ... ``` block
    body = section_text[yaml_match.end():].strip()
    if not body:
        raise ValueError(f"Release section for {version} in {path} body cannot be empty.")

    body = normalize_markdown_bullets(body)
    title = clean_release_title(raw_title, version)

    try:
        from awesomeversion import AwesomeVersion
        av = AwesomeVersion(version)
        is_prerelease = bool(av.beta or av.dev)
    except Exception:
        is_prerelease = bool(re.search(r"[-b](?:beta|alpha|rc|\d)", version, re.IGNORECASE))

    if "prerelease" in metadata:
        is_prerelease = metadata["prerelease"].lower() in ("true", "1", "yes")

    result = {
        "version": version,
        "title": title,
        "raw_title": raw_title,
        "date": metadata.get("date", ""),
        "prerelease": is_prerelease,
        "body": body,
    }
    return result


def validate_manifest_and_releases(
    manifest_path: Path | str, releases_path: Path | str
) -> tuple[bool, str]:
    """Validate that the version in manifest.json matches the latest entry in RELEASES.md."""
    m_path = Path(manifest_path)
    r_path = Path(releases_path)

    if not m_path.is_file():
        return False, f"Manifest file not found: {m_path}"
    if not r_path.is_file():
        return False, f"Releases file not found: {r_path}"

    try:
        manifest_data = json.loads(m_path.read_text(encoding="utf-8"))
        manifest_version = manifest_data.get("version")
    except Exception as err:
        return False, f"Failed to read/parse manifest {m_path}: {err}"

    if not manifest_version:
        return False, f"No 'version' field found in {m_path}"

    try:
        release_info = parse_releases_file(r_path)
    except Exception as err:
        return False, f"Failed to parse releases file {r_path}: {err}"

    release_version = release_info["version"]
    if manifest_version != release_version:
        return (
            False,
            f"Version mismatch: manifest.json has '{manifest_version}', "
            f"but RELEASES.md latest entry is '{release_version}'.",
        )

    return (
        True,
        f"Validation successful: version '{manifest_version}' matches between manifest.json and RELEASES.md.",
    )


def check_bump(manifest_path: Path | str, existing_tags: list[str]) -> bool:
    """Return True if manifest version is not in existing_tags."""
    m_path = Path(manifest_path)
    manifest_data = json.loads(m_path.read_text(encoding="utf-8"))
    manifest_version = manifest_data["version"]
    return manifest_version not in existing_tags


def extract_latest(releases_path: Path | str) -> str:
    """Return latest release info formatted as JSON string."""
    info = parse_releases_file(releases_path)
    return json.dumps(info, indent=2)


def get_git_tags() -> list[str]:
    """Retrieve list of git tags in the current repository."""
    try:
        output = subprocess.check_output(["git", "tag", "-l"], text=True)
        return [tag.strip() for tag in output.splitlines() if tag.strip()]
    except Exception as err:
        raise RuntimeError(f"Failed to retrieve git tags: {err}") from err


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="FoxESS release helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: validate
    validate_parser = subparsers.add_parser("validate", help="Validate manifest and releases file sync")
    validate_parser.add_argument(
        "--manifest",
        default="custom_components/foxess/manifest.json",
        help="Path to manifest.json",
    )
    validate_parser.add_argument(
        "--releases",
        default="RELEASES.md",
        help="Path to RELEASES.md",
    )

    # Subcommand: extract-latest
    extract_parser = subparsers.add_parser("extract-latest", help="Extract latest release info as JSON")
    extract_parser.add_argument(
        "--releases",
        default="RELEASES.md",
        help="Path to RELEASES.md",
    )

    # Subcommand: check-bump
    bump_parser = subparsers.add_parser("check-bump", help="Check if manifest version is a new tag")
    bump_parser.add_argument(
        "--manifest",
        default="custom_components/foxess/manifest.json",
        help="Path to manifest.json",
    )

    args = parser.parse_args()

    if args.command == "validate":
        valid, message = validate_manifest_and_releases(args.manifest, args.releases)
        if valid:
            print(f"✓ {message}")
            return 0
        print(f"✗ {message}", file=sys.stderr)
        return 1

    if args.command == "extract-latest":
        try:
            print(extract_latest(args.releases))
            return 0
        except Exception as err:
            print(f"Error extracting latest release: {err}", file=sys.stderr)
            return 1

    if args.command == "check-bump":
        tags = get_git_tags()
        is_new = check_bump(args.manifest, tags)
        print(f"is_new={'true' if is_new else 'false'}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
