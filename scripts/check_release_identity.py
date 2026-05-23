"""Check release identity fields without rewriting files.

This script intentionally separates hard release-identity fields from free-text
mentions. Structured current-version fields fail on mismatch; older versions in
ordinary prose are reported for review instead of failing, because historical
explanations and changelog entries may legitimately mention older releases.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _pyproject_version() -> str:
    data = tomllib.loads(_read_text(REPO_ROOT / "pyproject.toml"))
    return str(data["project"]["version"])


def _public_version() -> str | None:
    text = _read_text(REPO_ROOT / "src" / "dsafelogger" / "__init__.py")
    match = re.search(r"^__version__\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    return match.group(1) if match else None


def _uv_lock_version() -> str | None:
    text = _read_text(REPO_ROOT / "uv.lock")
    pattern = re.compile(
        r"\[\[package\]\]\s+name\s*=\s*\"d-safelogger\"\s+version\s*=\s*\"([^\"]+)\"",
        re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1) if match else None


def _latest_changelog_version() -> str | None:
    text = _read_text(REPO_ROOT / "CHANGELOG.md")
    for match in re.finditer(r"^## \[([^\]]+)\]", text, re.MULTILINE):
        value = match.group(1)
        if value.lower() != "unreleased":
            return value
    return None


def _changelog_release_versions() -> set[str]:
    text = _read_text(REPO_ROOT / "CHANGELOG.md")
    versions: set[str] = set()
    for match in re.finditer(r"^## \[([^\]]+)\]", text, re.MULTILINE):
        value = match.group(1)
        if value.lower() != "unreleased":
            versions.add(value)
    return versions


def _agents_current_versions() -> list[tuple[int, str]]:
    path = REPO_ROOT / "AGENTS.md"
    versions: list[tuple[int, str]] = []
    patterns = (
        re.compile(r"Current target release:\s*`([^`]+)`"),
        re.compile(r"現在の公開対象バージョン:\s*`([^`]+)`"),
    )
    for line_no, line in enumerate(_read_text(path).splitlines(), start=1):
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                versions.append((line_no, match.group(1)))
    return versions


def _check_equal(findings: list[Finding], label: str, actual: str | None, expected: str) -> None:
    if actual is None:
        findings.append(Finding("FAIL", f"{label}: missing, expected {expected}"))
    elif actual != expected:
        findings.append(Finding("FAIL", f"{label}: {actual!r}, expected {expected!r}"))
    else:
        findings.append(Finding("OK", f"{label}: {actual}"))


def _review_version_mentions(target_version: str) -> list[Finding]:
    findings: list[Finding] = []
    historical_versions = sorted(_changelog_release_versions() - {target_version})
    if not historical_versions:
        return findings

    files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "README_ja.md",
        REPO_ROOT / "TESTING.md",
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / "BENCHMARK.md",
        REPO_ROOT / "CHANGELOG.md",
        REPO_ROOT / "AGENTS.md",
    ]
    files.extend(sorted((REPO_ROOT / "docs" / "design").glob("*.md")))

    for path in files:
        if not path.exists():
            continue
        for line_no, line in enumerate(_read_text(path).splitlines(), start=1):
            for version in historical_versions:
                if version not in line and f"v{version}" not in line:
                    continue
                rel = path.relative_to(REPO_ROOT).as_posix()
                findings.append(
                    Finding(
                        "REVIEW",
                        f"{rel}:{line_no}: mentions project version {version!r}; "
                        "verify historical/current context",
                    )
                )
    return findings


def check(expected_version: str | None, tag: str | None, review_mentions: bool) -> list[Finding]:
    target = expected_version or _pyproject_version()
    findings: list[Finding] = []

    _check_equal(findings, "pyproject.toml project.version", _pyproject_version(), target)
    _check_equal(findings, "src/dsafelogger/__init__.py __version__", _public_version(), target)
    _check_equal(findings, "uv.lock d-safelogger version", _uv_lock_version(), target)
    _check_equal(findings, "CHANGELOG.md latest release heading", _latest_changelog_version(), target)

    for line_no, version in _agents_current_versions():
        _check_equal(findings, f"AGENTS.md:{line_no} current release", version, target)

    github_ref_tag = os.environ.get("GITHUB_REF_NAME") if os.environ.get("GITHUB_REF_TYPE") == "tag" else None
    effective_tag = tag if tag is not None else github_ref_tag
    if effective_tag:
        _check_equal(findings, "release tag", effective_tag, f"v{target}")

    if review_mentions:
        findings.extend(_review_version_mentions(target))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", help="Expected package version. Defaults to pyproject.")
    parser.add_argument("--tag", help="Release tag to check, e.g. v0.2.2.")
    parser.add_argument(
        "--review-version-mentions",
        action="store_true",
        help="Report non-target semantic-version mentions as REVIEW findings.",
    )
    args = parser.parse_args()

    findings = check(args.expected_version, args.tag, args.review_version_mentions)
    for finding in findings:
        stream = sys.stderr if finding.level == "FAIL" else sys.stdout
        print(f"{finding.level}: {finding.message}", file=stream)
    return 1 if any(f.level == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
