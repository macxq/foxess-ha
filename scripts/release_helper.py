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


def parse_yaml_block(yaml_text: str) -> dict[str, str]:
    """Parse a simple key-value YAML block without third-party dependencies."""
    data: dict[str, str] = {}
    for line in yaml_text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        # Strip surrounding quotes if present
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        data[key] = val
    return data


def parse_releases_file(releases_path: Path | str) -> dict[str, str]:
    """Parse the latest release entry from a releases Markdown file."""
    path = Path(releases_path)
    if not path.is_file():
        raise FileNotFoundError(f"Releases file not found: {path}")

    content = path.read_text(encoding="utf-8")

    # Match release sections: ## [v0.56] or ## v0.56
    heading_pattern = re.compile(r"^##\s+\[?(v\d+\.\d+)\]?", re.MULTILINE)
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

    metadata = parse_yaml_block(yaml_match.group(1))
    if "title" not in metadata:
        raise ValueError(
            f"Release section for {version} in {path} is missing required 'title' in YAML metadata."
        )

    # Body is everything after the ```yaml ... ``` block
    body = section_text[yaml_match.end():].strip()
    if not body:
        raise ValueError(f"Release section for {version} in {path} body cannot be empty.")

    result = {
        "version": version,
        "title": metadata["title"],
        "date": metadata.get("date", ""),
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
    except Exception:
        return []


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
