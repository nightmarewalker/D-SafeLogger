# D-SafeLogger - Agent Context Guide

This guide gives AI agents the current project context, quality gates, and benchmark rules for D-SafeLogger.

## Project Overview

**D-SafeLogger** is a zero-runtime-dependency, production-ready Python logging library built on top of the standard library `logging` module. It is designed to remain compatible with stdlib logging while adding safer file routing, structured output, context propagation, integrity auditing, async transport, and a formal multiprocess API.

## Current Release Status

- Current target release: `0.4.0`
- Current import name: `dsafelogger`
- Latest pre-publish review status (2026-05-07): **GO-with-fixes**, with v23j follow-up fixes applied locally.
- Resolved release blockers:
  - sdist packaging now uses explicit `MANIFEST.in` include rules and includes `tests/conftest.py`.
  - sdist includes key release documents: `CHANGELOG.md`, `README_ja.md`, `TESTING.md`, `BENCHMARK.md`, and `CONTRIBUTING.md`.
  - selected benchmark raw summaries include both `summary.json` and `summary.md` so generated benchmark summaries can be checked from sdist.
  - `dsafelogger.mp` bootstrap-ready validation now checks registry hash consistency instead of being a no-op.
  - custom `RegisterLevel()` spawn-worker propagation requirements are documented in public docs/examples/API docs.
  - publish workflow now validates wheel/sdist contents and runs `uvx twine check dist/*` before PyPI upload.
- Remaining release-time checks:
  - Clean repository scratch artifacts before release (`*.zip`, extracted temp directories, old `dist/`, temporary logs, generated unpacked trees, stray `*.egg-info`).
  - Rebuild distribution artifacts from a clean tree and rerun package content validation immediately before publishing.

Key features:

- **Zero runtime dependencies:** The library itself depends only on the Python standard library.
- **Stdlib logging compatibility:** Works with existing `logging` usage and third-party libraries through normal logger integration.
- **Append-only file routing:** Log files are never renamed or truncated during rotation. Output is rerouted to new append-only destinations.
- **Structured JSON logging:** JSON Lines output for observability pipelines.
- **Contextual logging:** Thread-safe and async-safe context management via `contextualize()`.
- **Integrity auditing:** SHA-256 verification for log files.
- **Multi-layer configuration:** Code defaults, INI/dict configuration, and environment variable overrides.
- **Async transport:** Queue-backed asynchronous logging with context preservation.
- **Formal multiprocess API:** `dsafelogger.mp` provides Writer-owned sinks, worker attach/detach, control-plane ACKs, and classified delivery-state counters.
- **Free-threaded support:** Designed for CPython free-threaded builds where supported.

## Design Philosophy

1. **Reroute, don't rotate:** Avoid rename/truncate operations. Write append-only and switch destinations at rotation boundaries.
2. **Fail before it breaks:** Prefer explicit counters, warnings, and bounded shutdown behavior over ambiguous loss.
3. **Start quick, ship as-is:** Keep basic setup small with `ConfigureLogger()` and `GetLogger()`.
4. **Zero external runtime dependencies:** Development and benchmark dependencies are allowed only in their dependency groups.
5. **Be honest about multiprocess behavior:** `dsafelogger.mp` does not claim impossible durability under every failure. Its value is making delivery state observable through accepted, delivered, rejected, dropped, partial, and unexplained-loss counters.

## Directory Structure

```text
D-Logger/
├── src/
│   └── dsafelogger/          # Main package source code
├── tests/                     # Unit and integration test suite
│   ├── conftest.py
│   └── test_*.py
├── benchmarks/                # Benchmark runners, selected summaries, and result artifacts
│   ├── run_benchmark.py
│   ├── run_multiprocess_compare_v23a.py
│   ├── update_summary.py
│   ├── summary/
│   └── results/
├── examples/                  # Scenario-based usage guides
├── docs/                      # Public documentation, including design docs
├── plan/                      # Private planning notes and review history
├── pyproject.toml             # Project metadata, uv groups, pytest config
├── uv.lock                    # Locked dependency resolution
├── README.md / README_ja.md   # Public overview documents
├── TESTING.md                 # Test execution guide
├── BENCHMARK.md               # Manually edited public benchmark analysis
└── CHANGELOG.md
```

## Tests

The official quality gate is the full test suite with the `dev` dependency group installed.

```bash
uv sync --group dev
uv run pytest tests -v
```

Current v23k local validation on Python 3.14.3 / Windows:

```text
749 passed, 3 skipped
```

Latest collection-only validation:

```text
752 tests collected
```

Latest coverage validation: terminal total `87%`, XML line-rate `89.17%`, XML branch-rate `82.02%` on Python 3.14.3 / Windows.

Skip counts are platform-dependent because fork E2E tests are POSIX-only and Windows spawn E2E tests are Windows-only.

Important test policy:

- OpenTelemetry and structlog coexistence tests are part of the official full dev test run.
- The `optional_integration` marker is for diagnostic selection only. Do not treat `-m "not optional_integration"` as release validation.
- Multiprocess tests are part of the standard quality gate because `dsafelogger.mp` is a formal feature.
- Spawn E2E tests must use the same `multiprocessing` context for `mp.ConfigureLogger(..., mp_context=ctx)` and worker process creation.
- Tests must not rely on `multiprocessing.Queue.empty()` for correctness. Use timeout-based `get()` or recording/fake queues.
- Fork E2E tests are POSIX-only. Windows spawn E2E tests are Windows-only.

Useful commands:

```bash
# Concise local run
uv run pytest tests -q

# Coverage
uv run pytest tests -v --cov=dsafelogger --cov-report=term-missing

# API docs check
uv run python scripts/generate_api_docs.py --check

# Public design docs readiness check
uv run python scripts/check_design_docs_sync.py

# Release identity / documented facts checks (read-only; do not run tests)
uv run python scripts/check_release_identity.py
uv run python scripts/check_release_facts.py

# Optional integration tests only
uv run pytest tests -v -m optional_integration

# Temporarily exclude optional integration tests for local troubleshooting only
uv run pytest tests -v -m "not optional_integration"
```

Free-threaded Python, where available:

```bash
PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v
```

## Benchmarks

Benchmark dependencies are in the `benchmark` dependency group.

```bash
uv sync --group benchmark
```

Primary benchmark runners:

```bash
# Single-process benchmark matrix
uv run python benchmarks/run_benchmark.py

# Multiprocess comparison benchmark
uv run python benchmarks/run_multiprocess_compare_v23a.py --repo-root . --profile performance_profile

# Multiprocess resilience benchmark
uv run python benchmarks/run_multiprocess_compare_v23a.py --repo-root . --profile resilience_profile

# Diagnostic-only multiprocess benchmark
uv run python benchmarks/run_multiprocess_v23d_diagnostic.py --repo-root .
```

Benchmark publication model:

- `benchmarks/results/<session>/` contains complete per-run artifacts such as `summary.json`, `summary.md`, and raw result bundles.
- `benchmarks/summary/manifest.json` selects the benchmark sessions used for public summaries.
- `benchmarks/summary/*.md` is generated from the manifest.
- `BENCHMARK.md` is manually edited public analysis and must not be regenerated by benchmark runners.
- Diagnostic benchmark sessions are normally kept out of `BENCHMARK.md` and generated public summaries.

Regenerate and verify selected summaries:

```bash
uv run python benchmarks/update_summary.py
uv run python benchmarks/update_summary.py --check
```

Benchmark scratch/output rule:

- Final benchmark artifacts belong under `benchmarks/results/`.
- Runtime scratch data, log files, worker outputs, and transient working directories must use `C:\TempX\D-SafeLogger-bench\...`.
- Do not use `%TEMP%`, `%TMP%`, `tempfile` defaults, or ad-hoc scratch directories under `benchmarks/results/` for benchmark runtime I/O.
- If a benchmark runner needs a scratch root option, default it to `C:\TempX\D-SafeLogger-bench` and record the actual path in the session summary.
- Keep result artifacts and scratch data explicitly separated when adding or modifying benchmark scripts.

## Documentation Rules

- Keep `README.md`, `README_ja.md`, `TESTING.md`, `BENCHMARK.md`, `CHANGELOG.md`, and the current public design documents under `docs/design/` consistent when behavior, test policy, or benchmark interpretation changes. Do not assume the design-document version suffix remains `v23j`; inspect the current filenames before updating references or checks.
- Do not describe `dsafelogger.mp` as preview or experimental.
- Do not claim D-SafeLogger is always the fastest backend. Single-process async has strong selected results; multiprocess raw throughput is not the primary value proposition.
- Describe multiprocess value as Writer-owned sinks plus observable delivery state under abnormal conditions.
- Do not publish stale benchmark claims, old test counts, or local absolute paths.
- Regenerate `docs/api/` with `uv run python scripts/generate_api_docs.py` after public API/docstring changes, then verify with `--check`.
- Treat `docs/design/` as the public design-document location. `plan/` is private and must not be linked from public docs.
- Verify public design docs with `uv run python scripts/check_design_docs_sync.py`.
- Verify release identity fields with `uv run python scripts/check_release_identity.py`. Use `--tag vX.Y.Z` when checking an intended release tag. Use `--review-version-mentions` for a non-failing report of older version strings in prose.
- Verify documented current test/coverage facts with `uv run python scripts/check_release_facts.py`. This script is read-only and does not run tests; it checks that current baseline text is consistent across release documents. Use `--review-numeric-mentions` for a non-failing report of older validation numbers in prose/history sections.
- Before release, rebuild distribution artifacts from a clean tree and verify wheel/sdist contents explicitly.
- Do not change the package version until release readiness is explicitly confirmed.

## Version Bump and Push Procedure

Use this checklist when updating the package version and pushing a release branch/tag.

- Confirm release readiness first; do not bump versions speculatively.
- Inspect `git status --short`, `git diff`, and `git log --oneline -10` before editing. If unrelated user changes exist, leave them untouched.
- Confirm the target version and update only the required version identity files: `pyproject.toml`, `src/dsafelogger/__init__.py`, `uv.lock`, `CHANGELOG.md`, and `AGENTS.md` current release status when appropriate.
- Update public docs only when the release changes behavior, public API, test policy, benchmark interpretation, or user-facing release identity. Do not mechanically rewrite historical version numbers in changelog/history sections.
- If public API, docstrings, or exported typing information changed, regenerate and check API docs with `uv run python scripts/generate_api_docs.py` and `uv run python scripts/generate_api_docs.py --check`.
- If behavior, test policy, benchmark interpretation, or architecture changed, update the relevant current design documents under `docs/design/` and run `uv run python scripts/check_design_docs_sync.py`. Design document version suffixes may change, so discover the current document set instead of hardcoding `v23j`.
- If benchmark claims or selected summaries changed, update benchmark summaries with `uv run python benchmarks/update_summary.py` and verify with `uv run python benchmarks/update_summary.py --check`. Do not regenerate manually edited `BENCHMARK.md` from benchmark runners.
- Run read-only identity/facts checks before committing: `uv run python scripts/check_release_identity.py` and `uv run python scripts/check_release_facts.py`. These checks do not replace actual test execution; they prevent stale current-version, test-count, and coverage text from surviving after validation results have been recorded.
- Run the release validation appropriate for the change: at minimum `uv run pytest tests -q`, `uv run mypy src`, `uv run pyright src`, `uv run pyright tests/typing_smoke`, `uv run python scripts/check_type_completeness.py --min-score 100`, `uv run python scripts/generate_api_docs.py --check`, `uv run python scripts/check_design_docs_sync.py`, `uv run python benchmarks/update_summary.py --check`, and `git diff --check`.
- Before publishing, clean old distribution/scratch artifacts, build from a clean tree, validate wheel/sdist contents with `scripts/check_distribution_contents.py`, run `uvx twine check`, install the built wheel with `scripts/install_built_wheel.py`, and run packaged type completeness with `uv run --no-sync python scripts/check_type_completeness.py --min-score 100`.
- Commit only intended files after reviewing the staged diff. Use a concise release-style commit message when the commit is an actual release version bump.
- Create an annotated tag whose name exactly matches the package version, such as `vX.Y.Z`, and verify the tag points to the intended commit.
- Push `main` first, wait for CI if appropriate, then push the tag so the publish workflow sees matching source and tag state.
- For GitHub Releases, keep release notes focused on user-visible runtime/API/behavioral changes and important compatibility or operational notes. As a rule, do not include documentation-only changes, wording cleanups, internal planning updates, or routine generated-doc refreshes unless they materially affect users.
- After push/publish, verify GitHub Actions, GitHub Release, PyPI version availability, local tags, and a clean working tree.

---

# D-SafeLogger - エージェント用コンテキストガイド

このガイドは、D-SafeLogger で作業する AI エージェント向けに、現行のプロジェクト方針・品質ゲート・ベンチマーク運用ルールをまとめたものです。

## プロジェクト概要

**D-SafeLogger** は、Python 標準ライブラリ `logging` の上に構築された、runtime 依存ゼロの本番向けロギングライブラリです。stdlib logging との互換性を保ちながら、安全なファイルルーティング、構造化出力、コンテキスト伝播、完全性監査、async transport、正式な multiprocess API を提供します。

## 現在のリリース状態

- 現在の公開対象バージョン: `0.4.0`
- 現在の import 名: `dsafelogger`
- 最新の公開前レビュー結果（2026-05-07）: **GO-with-fixes**。v23j の follow-up fixes は local に反映済み。
- 解消済み release blockers:
  - sdist packaging は明示的な `MANIFEST.in` include rules を使い、`tests/conftest.py` を含む。
  - sdist は主要 release documents（`CHANGELOG.md`, `README_ja.md`, `TESTING.md`, `BENCHMARK.md`, `CONTRIBUTING.md`）を含む。
  - selected benchmark raw summaries は `summary.json` と `summary.md` の両方を含み、sdist から generated benchmark summaries を検証できる。
  - `dsafelogger.mp` の bootstrap-ready validation は registry hash consistency を確認し、no-op ではない。
  - spawn worker 向け custom `RegisterLevel()` propagation requirements は public docs/examples/API docs に記載済み。
  - publish workflow は PyPI upload 前に wheel/sdist contents と `uvx twine check dist/*` を検証する。
- release 時点で再確認する項目:
  - repository 上の scratch artifacts（`*.zip`、展開済み一時ディレクトリ、古い `dist/`、一時 log、手動展開ツリー、 stray `*.egg-info`）を整理すること。
  - clean tree から distribution artifacts を再生成し、公開直前に package content validation を再実行すること。

主な機能:

- **runtime 依存ゼロ:** ライブラリ本体は Python 標準ライブラリのみに依存します。
- **stdlib logging 互換:** 通常の logger 統合を通じて既存の `logging` 利用やサードパーティライブラリと共存します。
- **追記専用ファイルルーティング:** rotation 時にファイルの rename/truncate を行わず、新しい追記先へ出力を切り替えます。
- **構造化 JSON logging:** observability pipeline 向けの JSON Lines 出力を提供します。
- **コンテキスト logging:** `contextualize()` による thread-safe / async-safe なコンテキスト管理を提供します。
- **完全性監査:** ログファイルの SHA-256 検証を提供します。
- **多層設定:** コード既定値、INI/dict 設定、環境変数 override に対応します。
- **async transport:** コンテキストを保持した queue-backed async logging を提供します。
- **正式 multiprocess API:** `dsafelogger.mp` は Writer-owned sinks、worker attach/detach、control-plane ACK、分類済み delivery-state counters を提供します。
- **free-threaded 対応:** 対応環境では CPython free-threaded build を考慮します。

## 設計思想

1. **リネームせず、ルーティングする:** rename/truncate を避け、append-only のまま rotation 境界で出力先を切り替えます。
2. **壊れる前に明示する:** 曖昧な欠損より、明示的な counters、warnings、bounded shutdown を優先します。
3. **すぐに始めて、そのまま本番へ:** `ConfigureLogger()` と `GetLogger()` で基本設定を小さく保ちます。
4. **runtime 外部依存ゼロ:** 開発・benchmark 用依存は専用 dependency group に限定します。
5. **multiprocess の限界を正直に扱う:** `dsafelogger.mp` はあらゆる障害下での完全永続化を主張しません。価値は accepted、delivered、rejected、dropped、partial、unexplained-loss counters によって配送状態を観測可能にすることです。

## ディレクトリ構造

```text
D-Logger/
├── src/
│   └── dsafelogger/          # メインパッケージ
├── tests/                     # unit / integration test suite
│   ├── conftest.py
│   └── test_*.py
├── benchmarks/                # benchmark runners, selected summaries, result artifacts
│   ├── run_benchmark.py
│   ├── run_multiprocess_compare_v23a.py
│   ├── update_summary.py
│   ├── summary/
│   └── results/
├── examples/                  # シナリオ別 usage guides
├── docs/                      # 公開ドキュメント（設計書を含む）
├── plan/                      # 非公開の計画メモ・review 履歴
├── pyproject.toml             # project metadata, uv groups, pytest config
├── uv.lock                    # locked dependency resolution
├── README.md / README_ja.md   # 公開 overview
├── TESTING.md                 # test execution guide
├── BENCHMARK.md               # 手動編集の公開 benchmark analysis
└── CHANGELOG.md
```

## テスト

公式品質ゲートは、`dev` dependency group を入れた full test suite です。

```bash
uv sync --group dev
uv run pytest tests -v
```

現行 v23k の local validation（Python 3.14.3 / Windows）:

```text
749 passed, 3 skipped
```

最新の collect-only validation:

```text
752 tests collected
```

最新 coverage validation: terminal total `87%`, XML line-rate `89.17%`, XML branch-rate `82.02%`（Python 3.14.3 / Windows）。

skipped 数は OS 依存です。fork E2E tests は POSIX-only、Windows spawn E2E tests は Windows-only です。

重要なテスト方針:

- OpenTelemetry / structlog coexistence tests は公式 full dev test run に含めます。
- `optional_integration` marker は診断用の選択 marker です。`-m "not optional_integration"` を release validation として扱わないでください。
- `dsafelogger.mp` は正式機能なので、multiprocess tests は標準品質ゲートに含めます。
- spawn E2E tests では、`mp.ConfigureLogger(..., mp_context=ctx)` と worker process creation で同じ `multiprocessing` context を使ってください。
- test correctness に `multiprocessing.Queue.empty()` を使わないでください。timeout-based `get()` または recording/fake queue を使ってください。
- fork E2E tests は POSIX-only、Windows spawn E2E tests は Windows-only です。

便利なコマンド:

```bash
# concise local run
uv run pytest tests -q

# coverage
uv run pytest tests -v --cov=dsafelogger --cov-report=term-missing

# API docs check
uv run python scripts/generate_api_docs.py --check

# public design docs readiness check
uv run python scripts/check_design_docs_sync.py

# release identity / documented facts checks (read-only; tests は実行しない)
uv run python scripts/check_release_identity.py
uv run python scripts/check_release_facts.py

# optional integration tests only
uv run pytest tests -v -m optional_integration

# local troubleshooting only
uv run pytest tests -v -m "not optional_integration"
```

free-threaded Python が使える場合:

```bash
PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v
```

## ベンチマーク

benchmark 依存は `benchmark` dependency group にあります。

```bash
uv sync --group benchmark
```

主な benchmark runners:

```bash
# single-process benchmark matrix
uv run python benchmarks/run_benchmark.py

# multiprocess comparison benchmark
uv run python benchmarks/run_multiprocess_compare_v23a.py --repo-root . --profile performance_profile

# multiprocess resilience benchmark
uv run python benchmarks/run_multiprocess_compare_v23a.py --repo-root . --profile resilience_profile

# diagnostic-only multiprocess benchmark
uv run python benchmarks/run_multiprocess_v23d_diagnostic.py --repo-root .
```

benchmark 公開モデル:

- `benchmarks/results/<session>/` は `summary.json`, `summary.md`, raw result bundle など、実行ごとの完全な成果物を保持します。
- `benchmarks/summary/manifest.json` は公開 summary に採用する benchmark session を固定します。
- `benchmarks/summary/*.md` は manifest から生成されます。
- `BENCHMARK.md` は手動編集の公開 analysis です。benchmark runner から再生成してはいけません。
- diagnostic benchmark session は通常 `BENCHMARK.md` と generated public summaries に混ぜません。

selected summaries の再生成と検証:

```bash
uv run python benchmarks/update_summary.py
uv run python benchmarks/update_summary.py --check
```

benchmark scratch/output ルール:

- 最終成果物は `benchmarks/results/` 配下に保存します。
- 実行時 scratch data、log files、worker outputs、一時作業ディレクトリは `C:\TempX\D-SafeLogger-bench\...` を使います。
- `%TEMP%`, `%TMP%`, `tempfile` defaults、`benchmarks/results/` 配下への ad-hoc scratch 出力は禁止です。
- benchmark runner に scratch root option が必要な場合、既定値は `C:\TempX\D-SafeLogger-bench` とし、実際の使用 path を session summary に記録します。
- benchmark script を追加・修正するときは、result artifacts と scratch data を明示的に分離してください。

## ドキュメント更新ルール

- behavior、test policy、benchmark interpretation を変更した場合は、`README.md`, `README_ja.md`, `TESTING.md`, `BENCHMARK.md`, `CHANGELOG.md`, `docs/design/` 配下の現行公開設計書の整合を保ってください。設計書のバージョン suffix が常に `v23j` とは限らないため、参照やチェックを更新する前に現在のファイル名を確認してください。
- `dsafelogger.mp` を preview / experimental と表現しないでください。
- D-SafeLogger が常に最速だと主張しないでください。single-process async には強い selected results がありますが、multiprocess raw throughput は主な価値ではありません。
- multiprocess の価値は、Writer-owned sinks と異常時 delivery state の観測可能性として説明してください。
- 古い benchmark claims、古い test counts、local absolute paths を公開文書に残さないでください。
- public API / docstring を変更したら `uv run python scripts/generate_api_docs.py` で `docs/api/` を再生成し、`--check` で検証してください。
- 公開設計書の置き場所は `docs/design/` です。`plan/` は非公開扱いで、公開文書から link しないでください。
- 公開設計書は `uv run python scripts/check_design_docs_sync.py` で検証してください。
- release identity fields は `uv run python scripts/check_release_identity.py` で検証してください。予定 tag を確認する場合は `--tag vX.Y.Z` を使ってください。文章中の旧 version 文字列は `--review-version-mentions` で non-failing report として確認できます。
- current test/coverage facts の文書内整合は `uv run python scripts/check_release_facts.py` で検証してください。この script は read-only で tests を実行しません。文章・履歴 section 内の古い検証数値は `--review-numeric-mentions` で non-failing report として確認できます。
- release 前には clean tree から配布物を再生成し、wheel/sdist の内容を明示的に確認してください。
- release readiness が明示的に確定するまで package version を変更しないでください。

## バージョン更新と push 手順

package version を更新し、release branch/tag を push する場合は以下を使ってください。

- 先に release readiness を確認してください。見込みだけで version bump しないでください。
- 編集前に `git status --short`, `git diff`, `git log --oneline -10` を確認してください。無関係な user 変更がある場合は触らないでください。
- 対象 version を確定し、必要な version identity file だけを更新してください: `pyproject.toml`, `src/dsafelogger/__init__.py`, `uv.lock`, `CHANGELOG.md`, 必要に応じて `AGENTS.md` の current release status。
- 公開文書は、behavior、public API、test policy、benchmark interpretation、user-facing release identity が変わる場合だけ更新してください。changelog/history section に残る過去 version は機械置換しないでください。
- public API、docstring、exported typing information が変わった場合は、`uv run python scripts/generate_api_docs.py` と `uv run python scripts/generate_api_docs.py --check` を実行してください。
- behavior、test policy、benchmark interpretation、architecture が変わった場合は、`docs/design/` 配下の現行設計書を更新し、`uv run python scripts/check_design_docs_sync.py` を実行してください。設計書の version suffix は変わる可能性があるため、`v23j` 固定で扱わず、現在の設計書セットを確認してください。
- benchmark claim や selected summary が変わった場合は、`uv run python benchmarks/update_summary.py` で summary を更新し、`uv run python benchmarks/update_summary.py --check` で検証してください。手動編集の `BENCHMARK.md` を benchmark runner から再生成しないでください。
- commit 前に read-only identity/facts checks を実行してください: `uv run python scripts/check_release_identity.py` と `uv run python scripts/check_release_facts.py`。これらは実際の test execution を代替しません。validation results を文書へ記録した後に、current version、test count、coverage text の stale 表記が残ることを防ぐためのものです。
- 変更内容に応じた release validation を実行してください。最低限、`uv run pytest tests -q`, `uv run mypy src`, `uv run pyright src`, `uv run pyright tests/typing_smoke`, `uv run python scripts/check_type_completeness.py --min-score 100`, `uv run python scripts/generate_api_docs.py --check`, `uv run python scripts/check_design_docs_sync.py`, `uv run python benchmarks/update_summary.py --check`, `git diff --check` を確認してください。
- publish 前には古い distribution/scratch artifacts を整理し、clean tree から build し、`scripts/check_distribution_contents.py` で wheel/sdist contents を検証し、`uvx twine check` を実行してください。built wheel は `scripts/install_built_wheel.py` で install し、`uv run --no-sync python scripts/check_type_completeness.py --min-score 100` で packaged type completeness を検証してください。
- staged diff を確認し、意図したファイルだけを commit してください。実際の release version bump なら release-style の簡潔な commit message を使ってください。
- package version と完全に一致する annotated tag を作成してください。例: `vX.Y.Z`。tag が意図した commit を指すことも確認してください。
- 先に `main` を push し、必要に応じて CI を待ってから tag を push してください。publish workflow が source と tag の整合した状態を見るようにします。
- GitHub Release の release notes は、user-visible な runtime/API/behavior 変更と重要な互換性・運用上の注意に絞ってください。原則として、documentation-only change、文言整理、internal planning update、routine generated-doc refresh は、ユーザーに実質影響がない限り含めないでください。
- push/publish 後は GitHub Actions、GitHub Release、PyPI version availability、local tag、clean working tree を確認してください。
