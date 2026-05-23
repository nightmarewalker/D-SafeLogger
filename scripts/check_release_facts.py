"""Check documented release facts without running tests.

The script reads currently documented validation facts and compares only fields
that are presented as current baselines. It does not run pytest, coverage, mypy,
pyright, or any other validation command. Historical changelog/design-document
numbers are not hard-failed; optional scanning reports them for review.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ReleaseFacts:
    passed: str
    skipped: str
    collected: str
    coverage_total: str
    line_rate: str
    branch_rate: str
    validation_env: str


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _require_match(text: str, pattern: str, label: str, flags: int = 0) -> re.Match[str]:
    match = re.search(pattern, text, flags)
    if not match:
        raise ValueError(f"could not read {label}")
    return match


def _facts_from_testing() -> ReleaseFacts:
    text = _read_text(REPO_ROOT / "TESTING.md")
    env = _require_match(
        text,
        r"Current v\w+ local validation on ([^:]+):",
        "TESTING.md validation environment",
    ).group(1)
    counts = _require_match(
        text,
        r"```text\s*(\d+) passed, (\d+) skipped\s*(\d+) collected\s*```",
        "TESTING.md pytest baseline",
        re.DOTALL,
    )
    coverage = _require_match(
        text,
        r"TOTAL coverage: (\d+%)\s*XML line-rate: ([\d.]+%)\s*XML branch-rate: ([\d.]+%)",
        "TESTING.md coverage baseline",
    )
    return ReleaseFacts(
        passed=counts.group(1),
        skipped=counts.group(2),
        collected=counts.group(3),
        coverage_total=coverage.group(1),
        line_rate=coverage.group(2),
        branch_rate=coverage.group(3),
        validation_env=env,
    )


def _check_contains(findings: list[Finding], path: str, expected: str, description: str) -> None:
    text = _read_text(REPO_ROOT / path)
    if expected not in text:
        findings.append(Finding("FAIL", f"{path}: missing current {description}: {expected!r}"))
    else:
        findings.append(Finding("OK", f"{path}: current {description} present"))


def _check_agents(facts: ReleaseFacts, findings: list[Finding]) -> None:
    expected_strings = (
        (f"{facts.passed} passed, {facts.skipped} skipped", "pytest result"),
        (f"{facts.collected} tests collected", "collection count"),
        (
            f"terminal total `{facts.coverage_total}`, XML line-rate `{facts.line_rate}`, "
            f"XML branch-rate `{facts.branch_rate}`",
            "coverage baseline",
        ),
        (facts.validation_env, "validation environment"),
    )
    for expected, description in expected_strings:
        _check_contains(findings, "AGENTS.md", expected, description)


def _check_current_design_docs(facts: ReleaseFacts, findings: list[Finding]) -> None:
    test_designs = sorted((REPO_ROOT / "docs" / "design").glob("*TestDesign*.md"))
    if not test_designs:
        findings.append(Finding("FAIL", "docs/design: no current TestDesign document found"))
        return
    expected = f"{facts.passed} passed, {facts.skipped} skipped"
    collected = f"{facts.collected}` collected"
    for path in test_designs:
        text = _read_text(path)
        rel = path.relative_to(REPO_ROOT).as_posix()
        if expected in text and collected in text:
            findings.append(Finding("OK", f"{rel}: current pytest baseline present"))
            return
    findings.append(
        Finding(
            "FAIL",
            "docs/design TestDesign documents: missing current pytest baseline "
            f"{expected!r} / {facts.collected} collected",
        )
    )


def _check_latest_changelog_section(facts: ReleaseFacts, findings: list[Finding]) -> None:
    text = _read_text(REPO_ROOT / "CHANGELOG.md")
    match = re.search(
        r"^## \[[^\]]+\].*?(?=^## \[[^\]]+\]|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        findings.append(Finding("FAIL", "CHANGELOG.md: no latest release section found"))
        return

    section = match.group(0)
    has_validation_numbers = any(
        token in section
        for token in (
            "passed",
            "skipped",
            "collected",
            "Coverage validation",
            "coverage.xml",
        )
    )
    if not has_validation_numbers:
        findings.append(
            Finding("OK", "CHANGELOG.md latest release section has no current validation numbers")
        )
        return

    expected = (
        f"{facts.passed} passed, {facts.skipped} skipped",
        f"{facts.collected}` collected",
        f"terminal total `{facts.coverage_total}`",
        f"line-rate `{facts.line_rate}`",
        f"branch-rate `{facts.branch_rate}`",
    )
    missing = [value for value in expected if value not in section]
    if missing:
        findings.append(
            Finding("FAIL", f"CHANGELOG.md latest release validation facts mismatch: {missing}")
        )
    else:
        findings.append(Finding("OK", "CHANGELOG.md latest release validation facts match"))


def _review_numeric_mentions(facts: ReleaseFacts) -> list[Finding]:
    current_values = {
        facts.passed,
        facts.skipped,
        facts.collected,
        facts.coverage_total.rstrip("%"),
        facts.line_rate.rstrip("%"),
        facts.branch_rate.rstrip("%"),
    }
    pattern = re.compile(
        r"(\d+ passed|\d+ skipped|\d+ collected|\d+ tests collected|"
        r"terminal total `?\d+%|line-rate `?[\d.]+%|branch-rate `?[\d.]+%)"
    )
    findings: list[Finding] = []
    files = [
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "TESTING.md",
        REPO_ROOT / "CHANGELOG.md",
    ]
    files.extend(sorted((REPO_ROOT / "docs" / "design").glob("*.md")))
    for path in files:
        for line_no, line in enumerate(_read_text(path).splitlines(), start=1):
            if not pattern.search(line):
                continue
            current_baseline_line = any(
                expected in line
                for expected in (
                    f"{facts.passed} passed, {facts.skipped} skipped",
                    f"{facts.collected} tests collected",
                    f"{facts.collected}` collected",
                    f"terminal total `{facts.coverage_total}`",
                    f"line-rate `{facts.line_rate}`",
                    f"branch-rate `{facts.branch_rate}`",
                    f"terminal total **{facts.coverage_total}**",
                    f"XML line-rate **{facts.line_rate}**",
                    f"branch-rate **{facts.branch_rate}**",
                    facts.validation_env,
                )
            )
            if current_baseline_line:
                continue
            numbers = set(re.findall(r"\d+(?:\.\d+)?", line))
            if numbers and not numbers <= current_values:
                rel = path.relative_to(REPO_ROOT).as_posix()
                findings.append(
                    Finding(
                        "REVIEW",
                        f"{rel}:{line_no}: validation number may be historical or stale",
                    )
                )
    return findings


def check(review_numeric_mentions: bool) -> list[Finding]:
    findings: list[Finding] = []
    try:
        facts = _facts_from_testing()
    except ValueError as exc:
        return [Finding("FAIL", str(exc))]

    findings.append(Finding("OK", "TESTING.md current release facts parsed"))
    _check_agents(facts, findings)
    _check_current_design_docs(facts, findings)
    _check_latest_changelog_section(facts, findings)
    if review_numeric_mentions:
        findings.extend(_review_numeric_mentions(facts))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review-numeric-mentions",
        action="store_true",
        help="Report validation-number mentions outside current baseline checks as REVIEW findings.",
    )
    args = parser.parse_args()

    findings = check(args.review_numeric_mentions)
    for finding in findings:
        stream = sys.stderr if finding.level == "FAIL" else sys.stdout
        print(f"{finding.level}: {finding.message}", file=stream)
    return 1 if any(f.level == "FAIL" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
