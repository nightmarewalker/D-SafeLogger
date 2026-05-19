# D-SafeLogger - Agent Context Guide

This guide gives AI agents the current project context, quality gates, and benchmark rules for D-SafeLogger.

## Project Overview

**D-SafeLogger** is a zero-runtime-dependency, production-ready Python logging library built on top of the standard library `logging` module. It is designed to remain compatible with stdlib logging while adding safer file routing, structured output, context propagation, integrity auditing, async transport, and a formal multiprocess API.

## Current Release Status

- Current target release: `0.2.1`
- Current import name: `dsafelogger`
- Latest pre-publish review status (2026-05-07): **GO-with-fixes**, with v23j follow-up fixes applied locally.
- Resolved release blockers:
  - sdist packaging now uses explicit `MANIFEST.in` include rules and includes `tests/conftest.py`.
  - sdist includes key release documents: `CHANGELOG.md`, `README_ja.md`, `TESTING.md`, `BENCHMARK.md`, and `CONTRIBUTING.md`.
  - selected benchmark raw summaries include both `summary.json` and `summary.md` so generated benchmark summaries can be checked from sdist.
  - `dsafelogger.mp` bootstrap-ready validation now checks registry hash consistency instead of being a no-op.
  - custom `register_level()` spawn-worker propagation requirements are documented in public docs/examples/API docs.
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

Current v23j local validation on Python 3.14.3 / Windows:

```text
658 passed, 3 skipped
```

Latest collection-only validation:

```text
661 tests collected
```

Latest coverage validation: terminal total `87%`, XML line-rate `88.97%`, XML branch-rate `81.46%` on Python 3.14.3 / Windows.

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

- Keep `README.md`, `README_ja.md`, `TESTING.md`, `BENCHMARK.md`, `CHANGELOG.md`, and `docs/design/*v23j*` consistent when behavior, test policy, or benchmark interpretation changes.
- Do not describe `dsafelogger.mp` as preview or experimental.
- Do not claim D-SafeLogger is always the fastest backend. Single-process async has strong selected results; multiprocess raw throughput is not the primary value proposition.
- Describe multiprocess value as Writer-owned sinks plus observable delivery state under abnormal conditions.
- Do not publish stale benchmark claims, old test counts, or local absolute paths.
- Regenerate `docs/api/` with `uv run python scripts/generate_api_docs.py` after public API/docstring changes, then verify with `--check`.
- Treat `docs/design/` as the public design-document location. `plan/` is private and must not be linked from public docs.
- Verify public design docs with `uv run python scripts/check_design_docs_sync.py`.
- Before release, rebuild distribution artifacts from a clean tree and verify wheel/sdist contents explicitly.
- Do not change the package version until release readiness is explicitly confirmed.

---

# D-SafeLogger - エージェント用コンテキストガイド

このガイドは、D-SafeLogger で作業する AI エージェント向けに、現行のプロジェクト方針・品質ゲート・ベンチマーク運用ルールをまとめたものです。

## プロジェクト概要

**D-SafeLogger** は、Python 標準ライブラリ `logging` の上に構築された、runtime 依存ゼロの本番向けロギングライブラリです。stdlib logging との互換性を保ちながら、安全なファイルルーティング、構造化出力、コンテキスト伝播、完全性監査、async transport、正式な multiprocess API を提供します。

## 現在のリリース状態

- 現在の公開対象バージョン: `0.2.1`
- 現在の import 名: `dsafelogger`
- 最新の公開前レビュー結果（2026-05-07）: **GO-with-fixes**。v23j の follow-up fixes は local に反映済み。
- 解消済み release blockers:
  - sdist packaging は明示的な `MANIFEST.in` include rules を使い、`tests/conftest.py` を含む。
  - sdist は主要 release documents（`CHANGELOG.md`, `README_ja.md`, `TESTING.md`, `BENCHMARK.md`, `CONTRIBUTING.md`）を含む。
  - selected benchmark raw summaries は `summary.json` と `summary.md` の両方を含み、sdist から generated benchmark summaries を検証できる。
  - `dsafelogger.mp` の bootstrap-ready validation は registry hash consistency を確認し、no-op ではない。
  - spawn worker 向け custom `register_level()` propagation requirements は public docs/examples/API docs に記載済み。
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

現行 v23j の local validation（Python 3.14.3 / Windows）:

```text
658 passed, 3 skipped
```

最新の collect-only validation:

```text
661 tests collected
```

最新 coverage validation: terminal total `87%`, XML line-rate `88.97%`, XML branch-rate `81.46%`（Python 3.14.3 / Windows）。

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

- behavior、test policy、benchmark interpretation を変更した場合は、`README.md`, `README_ja.md`, `TESTING.md`, `BENCHMARK.md`, `CHANGELOG.md`, `docs/design/*v23j*` の整合を保ってください。
- `dsafelogger.mp` を preview / experimental と表現しないでください。
- D-SafeLogger が常に最速だと主張しないでください。single-process async には強い selected results がありますが、multiprocess raw throughput は主な価値ではありません。
- multiprocess の価値は、Writer-owned sinks と異常時 delivery state の観測可能性として説明してください。
- 古い benchmark claims、古い test counts、local absolute paths を公開文書に残さないでください。
- public API / docstring を変更したら `uv run python scripts/generate_api_docs.py` で `docs/api/` を再生成し、`--check` で検証してください。
- 公開設計書の置き場所は `docs/design/` です。`plan/` は非公開扱いで、公開文書から link しないでください。
- 公開設計書は `uv run python scripts/check_design_docs_sync.py` で検証してください。
- release 前には clean tree から配布物を再生成し、wheel/sdist の内容を明示的に確認してください。
- release readiness が明示的に確定するまで package version を変更しないでください。
