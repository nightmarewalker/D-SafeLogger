# Contributing to D-SafeLogger

Thank you for your interest in contributing to D-SafeLogger!
This project prioritises **stability, zero-dependency purity, and architectural clarity** above all else.
Every change is evaluated against those pillars — please read this guide before opening an issue or pull request.

## 1. Understand the Design Principles

Before contributing, familiarise yourself with the **Compatibility** and **Non-Goals** sections in
[README.md](README.md). D-SafeLogger is a drop-in enhancement for Python's standard `logging`
module, and its scope is intentionally narrow.

## 2. Contribution Flow: Issue-First Policy

1. **Open an Issue or Discussion first** — describe what you want to change and why.
2. **Wait for consensus** — a maintainer will triage and discuss feasibility.
3. **PRs by invitation** — once the issue is accepted, you will be invited to submit a PR.

> ⚠️ **Unsolicited pull requests** (those without a prior accepted issue) **may be closed without review.**
> This is not meant to discourage contributions — it ensures every change aligns with the project's direction.

## 3. Where to Start?

### Directly Welcome (Open an Issue)

- **Bug reports** — include a minimal reproducible example, Python version, and OS.
- **Documentation improvements** — typo fixes, clarifications, better examples.
- **Security concerns** — please report responsibly via [SECURITY.md](SECURITY.md) or private disclosure.

### Requires Discussion First

- **Features not in current scope** — propose in a Discussion before writing code.
- **Architecture changes** — structural modifications need explicit design approval.
- **New dependencies** — almost certainly rejected. D-SafeLogger follows a strict **zero-dependency policy**.

## 4. Core Constraints

All contributions **must** respect these invariants:

1. **Zero-dependency** — Python standard library only. No exceptions.
2. **Fail-fast configuration** — errors must raise immediately, not fail silently.
3. **Thread safety** — all shared state protected by explicit locks (no GIL reliance).
4. **Append-only invariant** — log files must never be renamed or truncated.
5. **`logging` compatibility** — must remain a drop-in enhancement for stdlib `logging`.

## 5. Development Setup

```bash
git clone https://github.com/<your-username>/D-SafeLogger.git
cd D-SafeLogger
uv sync --group dev
uv run pytest tests/ -v
uv run ruff check src/ tests/
```

## 6. Code Style

- **PEP 8**, max **100** characters per line.
- **ruff** for linting (`uv run ruff check src/ tests/`).
- **Type hints required** — use Python 3.11+ `X | Y` union syntax.

## 7. Pull Request Process

1. Create a feature branch from `main`.
2. Add tests for new functionality.
3. Ensure **all** tests pass: `uv run pytest tests/ -v`.
4. Update documentation if needed.
5. Submit a PR with a clear description referencing the accepted issue.

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE).

---

*D-SafeLogger is currently in a **stability-first phase**.
New features are accepted conservatively — quality and reliability come first.*
