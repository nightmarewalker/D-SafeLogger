# D-SafeLogger テスト設計 v23k

作成日: 2026-04-29
対象バージョン: v23k（multiprocess observability 追加）

---

## 概要

v23k は v23j の公開前品質ゲートを維持したまま、multiprocess observability の runtime warning、shutdown report、delivery status schema を追加する。

現行 v23k のローカル検証 baseline は Python 3.14.3 / Windows 上の結果であり、`714 passed, 3 skipped`（`717` collected）である。fork E2E は POSIX-only、Windows spawn E2E は Windows-only であるため、OS によって skipped 数は変動し得る。0.2.2 向けの公開前品質ゲートでは、これに加えて `mypy src` / `pyright src` / `pyright tests/typing_smoke` / built wheel に対する `pyright --verifytypes dsafelogger --ignoreexternal` 100% completeness gate を実行する。

v23h から継続する動作変更は以下:

1. Writer の per-record 計上化と sink 分類（H2 / M1 / L5）
2. `_writer_event_reject` の分離（M4: `_writer_reconstruct_reject` + `_writer_close_marker_reject`）
3. stderr warning の rate-limit 統一（H3）
4. `TrackedQueue` による cross-platform `qsize()`（M3）
5. env var invalid 時の fail-fast（L2）
6. `WriterRuntime.__init__` validation（L3）
7. per-message flush 時 dead branch 回避（L1）
8. 設計書 §16.5 / §12.3 / §11.16.1 / §11.27 / inventory L4 / TestDesign 構成（H1 / L4 / M5）
9. **Bounded shutdown 契約（§12.4.1, v23h 追加対応）**: WriterRuntime の `_log_thread` / `_control_thread` を `daemon=True` 化、`stop()` の join timeout 後に thread が生存していれば stuck thread 名を含む stderr visible warning。silent hang 禁止

v23j で追加する公開前方針は以下:

10. `dsafelogger.mp` は preview ではなく正式仕様として公開前検証する
11. 公式テストは `uv sync --group dev` 後の `uv run pytest tests -v` とし、OpenTelemetry / structlog 連携テストも必須実行対象に含める
12. optional 連携テストは skip しない。補助的な分離実行のため `optional_integration` marker を付与する
13. spawn E2E は Writer IPC primitive と worker process が同じ `mp_context='spawn'` を共有する
14. `Queue.empty()` に依存するテストは禁止し、timeout 付き `get()` または fake/recording queue で検証する
15. benchmark 公開成果物は `benchmarks/summary/manifest.json` を source of truth とし、`BENCHMARK.md` は手動編集文書とする
16. merge 後の設定正規化・検証を single-process / module-specific / multiprocess で共通化する
17. routing / 世代管理 / hash の無効組み合わせは warning 補正ではなく `ValueError` とする
18. `structured=True` と formatter 指定、未登録 level、数値範囲不正、Python API bool 型不正を fail-fast 検証する
19. `py.typed` 配布に対応し、source typing (`mypy src`, `pyright src`) と packaged typing (`pyright --verifytypes dsafelogger --ignoreexternal`) を公開前品質ゲートへ含める
20. 利用者視点の public API typing smoke test は `tests/typing_smoke/` に置き、`tests/typing/` という名前は標準ライブラリ `typing` shadow を避けるため使わない

---

## DOD

| ID | 条件 |
|---|---|
| DOD-v23h-1 (H2/M1/L5) | required sink set のみが `_writer_sink_reject` / `_writer_policy_reject` / `_writer_partial_delivered` の対象。best-effort（console 等）の失敗は `_writer_best_effort_failures` のみ増分する |
| DOD-v23h-2 (M1) | N 個の required handler が同一 record を全て filter reject した場合、`_writer_policy_reject` は **+1**（+N ではない）。emit error 同様 |
| DOD-v23h-3 (H2 partial) | required sink set 内で「成功と失敗が混在」した場合のみ `_writer_partial_delivered += 1` する。partial 計上時は `_writer_sink_reject` / `_writer_policy_reject` / `_reject_counter` を increment しない |
| DOD-v23h-4 (L5) | required handler が 1 個のみの route は partial を増分しない（spec §12.3 で明示） |
| DOD-v23h-5 (H3) | `_writer_sink_reject` / `_writer_policy_reject` / `_writer_route_reject` / `_writer_reconstruct_reject` / `_writer_close_marker_reject` / `_writer_best_effort_failures` の stderr warning は初回（count==1）と 100 件ごとのみ出力する |
| DOD-v23h-6 (M3) | `mp.ConfigureLogger()` が生成する `log_queue` は `TrackedQueue` インスタンスである |
| DOD-v23h-7 (M3) | `TrackedQueue.__init__` は native `qsize()` を例外プローブし、`NotImplementedError` を捕捉した場合のみ `multiprocessing.Value` カウンタモードへ fallback する。Linux/Windows ではネイティブ qsize を使う |
| DOD-v23h-8 (M3) | qsize unsupported モードで put / get を行うと `qsize()` は近似値（race window 1 件）で更新される |
| DOD-v23h-9 (M4) | LogEvent の reconstruct failure は `_writer_reconstruct_reject` を、不正 CloseMarker は `_writer_close_marker_reject` を増分する。STATUS API は両方を別フィールドで公開する |
| DOD-v23h-10 (M4) | STATUS API は `writer_event_reject` を含まない（後方互換不要のため完全置換） |
| DOD-v23h-11 (L1) | `WriterRuntime._batch_flush_enabled` は `writer_flush_batch > 1` のとき True、それ以外で False。`_log_loop` は False のとき idle / shutdown flush の dead branch を踏まない |
| DOD-v23h-12 (L2) | `{prefix}_IPC_LOG_TIMEOUT` / `_IPC_LOG_QUEUE_MAXSIZE` / `_IPC_CLIENT_QUEUE_MAXSIZE` / `_WRITER_FLUSH_BATCH` の env var が int / float に解釈できない値を持つとき、`mp.ConfigureLogger()` は `ValueError` を raise する |
| DOD-v23h-13 (L3) | `WriterRuntime(ctx, ...)` は `ctx.writer_flush_batch < 1` の場合 `ValueError` を raise する |
| DOD-v23h-14 (H1) | 詳細設計 §15a.5.5 の WriterRuntime 疑似コードはメソッド名・例外型・フローが実装と一致する |
| DOD-v23h-15 (H2/L5/M4) | 仕様書 §12.3 は required / best-effort sink 分類、partial の単一 handler 不成立、`writer_event_reject` 分離後の counter 表を記述している |
| DOD-v23h-16 (§12.4.1) | `WriterRuntime` の `_log_thread` / `_control_thread` は **`daemon=True`** で起動する |
| DOD-v23h-17 (§12.4.1) | `runtime.stop(timeout)` は最大 `timeout` 秒で thread の join を待ち、timeout 後に thread が生存していれば stuck thread 名（`log_thread` / `control_thread` のうち該当するもの）を含む stderr visible warning を 1 回出力する |
| DOD-v23h-18 (§12.4.1) | `runtime.stop()` で drain が timeout 内に完了した場合、bounded warning は出力されない |
| DOD-v23h-19 (§12.4.1) | 仕様書 §12.4.1 に bounded shutdown 契約（bounded wait → visible warning → process exits）が明記されている。v22h の non-daemon 化決定の撤回理由は v23h changelog にのみ記録され、v22h changelog は変更しない |
| DOD-v23j-20 | Linux spawn / Linux fork / Windows spawn の MP E2E を正式公開条件に含める |
| DOD-v23j-21 | spawn E2E では `mp.ConfigureLogger(..., mp_context=spawn_ctx)` と worker 起動 context を一致させる |
| DOD-v23j-22 | `tests/` は `Queue.empty()` に依存しない |
| DOD-v23j-23 | OpenTelemetry / structlog 連携テストは `optional_integration` marker を持つが、公式 full test では必ず実行される |
| DOD-v23j-24 | benchmark runner は `BENCHMARK.md` を生成しない。`benchmarks/update_summary.py` が manifest から `benchmarks/summary/*.md` を生成する |
| DOD-v23j-25 | `cyclic` / `none` / overflow-error mode と `enable_hash` / `backup_count` / `archive_mode` の無効組み合わせは `ValueError` |
| DOD-v23j-26 | Layer 2 merge 後の `structured=True + fmt/file_fmt/console_fmt`、未登録 `default_level`、`max_count < 1`、`suffix_digits < 1` は `ValueError` |
| DOD-v23j-27 | module-specific `level` と routing/generation/hash 設定は global と同等に検証する |
| DOD-v23j-28 | mp の validation は single-process と同じ共通検証を使い、`structured=True + file_fmt/console_fmt` も拒否する |
| DOD-v23j-29 | mp module-specific `level` は worker attach 側 logger level に反映する |
| DOD-v23j-30 | Python API bool 引数に `str` など bool 以外を渡した場合は `TypeError` |
| DOD-v23j-type-31 | `uv run mypy src` と `uv run pyright src` が 0 errors で完了する |
| DOD-v23j-type-32 | `uv run pyright tests/typing_smoke` が 0 errors で完了し、`tests/typing_smoke/public_api_smoke.py` は pytest default collection に含まれない |
| DOD-v23j-type-33 | built wheel install 後、`uv run --no-sync python scripts/check_type_completeness.py --min-score 100` が `pyright --verifytypes dsafelogger --ignoreexternal` の 100% completeness を確認する |
| DOD-v23j-type-34 | `tests/typing_smoke/` の名称により spawn worker で stdlib `typing` を shadow しない |

---

## 実装テスト対応表

| DOD | 実装テスト |
|---|---|
| DOD-v23h-1 | `tests/test_mp_runtime.py::TestCauseSpecificCounters::test_best_effort_failure_does_not_count_as_reject`、`TestSinkClassification::test_partial_delivered_only_within_required_set` |
| DOD-v23h-2 | `TestCauseSpecificCounters::test_writer_policy_reject_per_record_not_per_handler` |
| DOD-v23h-3 | `TestCauseSpecificCounters::test_writer_partial_delivered_increments_on_mixed_required_result` |
| DOD-v23h-4 | `TestSinkClassification::test_partial_delivered_only_within_required_set`、仕様書 §12.3 partial_delivered 説明 |
| DOD-v23h-5 | `TestCauseSpecificCounters::test_sink_reject_stderr_rate_limit`、`test_policy_reject_stderr_rate_limit`、既存 `test_drop_warning_first_and_every_100`、`test_flush_error_100th_also_warns` |
| DOD-v23h-6 | `TestTrackedQueue::test_tracked_queue_used_for_log_queue` |
| DOD-v23h-7 | `TestTrackedQueue::test_native_qsize_supported_on_this_platform` |
| DOD-v23h-8 | `TestTrackedQueue::test_qsize_tracks_put_get`、`test_unsupported_native_falls_back_to_value_counter` |
| DOD-v23h-9 | `TestCauseSpecificCounters::test_writer_reconstruct_reject_increments_on_bad_logevent`、`TestCloseMarkerDrain::test_close_marker_rejects_session_mismatch`、`test_close_marker_rejects_unexpected_client` |
| DOD-v23h-10 | `TestCauseSpecificCounters::test_status_includes_v23h_split_counters` |
| DOD-v23h-11 | `TestV23HValidation::test_per_message_flush_skips_idle_flush_logic`、`test_batch_flush_enables_idle_flush_logic` |
| DOD-v23h-12 | `tests/test_mp_attach.py::TestQueueMaxsizeConfig::test_invalid_log_queue_env_raises`、`test_invalid_client_queue_env_raises`、`test_invalid_log_timeout_env_raises`、`TestWriterFlushBatchConfig::test_invalid_writer_flush_batch_env_raises` |
| DOD-v23h-13 | `TestV23HValidation::test_writer_runtime_rejects_zero_flush_batch`、`test_writer_runtime_rejects_negative_flush_batch` |
| DOD-v23h-14 | 設計書 `D-SafeLogger_DetailedDesign_v23.md` §15a.5.5 を grep |
| DOD-v23h-15 | 仕様書 `D_SafeLogger_Specification_v23_full.md` §12.3 を grep |
| DOD-v23h-16 | `tests/test_mp_runtime.py::TestWriterRuntime::test_writer_threads_are_daemon` |
| DOD-v23h-17 | `TestV23HValidation::test_stop_emits_bounded_warning_when_threads_stuck` |
| DOD-v23h-18 | `TestV23HValidation::test_stop_emits_no_warning_on_clean_shutdown` |
| DOD-v23h-19 | 仕様書 §12.4.1 を grep + v22h changelog 行が無変更であることを git diff（後者は git 未初期化のため目視確認） |
| DOD-v23j-20 | `tests/test_mp_integration.py` / `tests/test_mp_fork.py` / `tests/test_mp_spawn_windows.py` |
| DOD-v23j-21 | `tests/test_mp_integration.py` の spawn context 明示 |
| DOD-v23j-22 | `tests/` 配下の `Queue.empty()` grep が 0 件 |
| DOD-v23j-23 | `tests/test_opentelemetry.py` / `tests/test_structlog.py` と `pyproject.toml` markers |
| DOD-v23j-24 | `benchmarks/summary/manifest.json` / `benchmarks/update_summary.py` / runner に `BENCHMARK.md` 書き込みがないこと |
| DOD-v23j-25 | `tests/test_configure.py::TestConfigureLoggerErrors::test_cyclic_hash_rejected`、`tests/test_coverage_boost.py::TestConfigureAdvanced::test_enable_hash_none_mode_raises`、`test_overflow_mode_backup_raises` |
| DOD-v23j-26 | `tests/test_configure.py::TestConfigureLoggerErrors::test_config_dict_structured_with_fmt`、`test_config_dict_invalid_default_level`、`test_config_dict_max_count_zero` |
| DOD-v23j-27 | `tests/test_configure.py::TestConfigureLoggerErrors::test_module_invalid_level` |
| DOD-v23j-28 | `tests/test_mp_configure.py::TestMpConfigureLogger::test_structured_and_file_fmt_mutual_exclusion`、`test_config_dict_invalid_default_level_raises` |
| DOD-v23j-29 | `tests/test_mp_configure.py::TestMpConfigureLogger::test_module_level_propagates_to_attached_logger` |
| DOD-v23j-30 | `tests/test_coverage_boost.py::TestConfigureAdvanced::test_enable_hash_wrong_type` と追加 bool 型検査 |
| DOD-v23j-type-31 | `uv run mypy src` / `uv run pyright src` |
| DOD-v23j-type-32 | `uv run pyright tests/typing_smoke` / `uv run pytest tests --collect-only -q` |
| DOD-v23j-type-33 | `scripts/install_built_wheel.py` / `scripts/check_type_completeness.py --min-score 100` |
| DOD-v23j-type-34 | `tests/typing_smoke/public_api_smoke.py` の配置と spawn 系 MP tests (`tests/test_mp_integration.py`, `tests/test_mp_spawn_windows.py`) |

---

## 公式テスト契約

公式テストは dev dependency group を前提にする。ライブラリ本体の runtime dependency が zero であることと、テストが OpenTelemetry / structlog 等の dev dependency を使うことは矛盾しない。

```bash
uv sync --group dev
uv run pytest tests -v
uv run mypy src
uv run pyright src
uv run pyright tests/typing_smoke
```

packaged typing の completeness は built wheel を対象に検証する。`install_built_wheel.py` 実行後の verifytypes は editable install へ戻らないよう `uv run --no-sync` を使う。

```bash
uv build
uv run python scripts/install_built_wheel.py
uv run --no-sync python scripts/check_type_completeness.py --min-score 100
uv sync --reinstall
```

補助的な切り分け用途として以下を許可するが、release 判定の代替にはしない。

```bash
uv run pytest tests -v -m "not optional_integration"
uv run pytest tests -v -m optional_integration
```

---

## ベンチ検証

v23h は I/O / dispatch のホットパスを変更しないため、ベンチ再走は必須ではない。次の点だけ確認する:

- `_dispatch` のループ本体は1イテレーションあたり 1 つの追加 attribute lookup（`getattr(h, '_ds_required', True)`）が増えるのみ。p50 への影響は見込めない（既に 11µs オーダー）。
- `TrackedQueue` の `put` / `get` は **native 対応プラットフォーム**（Linux / Windows）でゼロオーバーヘッド（`super()` 経由のみ）。未対応プラットフォーム（macOS 等）でのみ `Value` lock × 1 回が乗る。

v23j では benchmark 公開成果物の管理方式を変更する。runner は `benchmarks/results/<session>/summary.json` / `summary.md` を生成するのみで、`BENCHMARK.md` を直接更新しない。公開代表結果は `benchmarks/summary/manifest.json` で固定し、`uv run python benchmarks/update_summary.py` により `benchmarks/summary/*.md` を再生成する。

### v23j Publication Sync Addendum

公開前同期の追加 DOD として、coverage 再生成、API docs `--check`、design docs sync check、GitHub CI / publish preflight、examples の formal MP / external rotation 追加を検証対象に含める。0.2.2 向けにはさらに source typing、typing smoke、built wheel に対する verifytypes 100% completeness gate を追加する。これらは runtime behavior を変更せず、公開成果物と品質ゲートを同期するための補助検証である。

---

## 参照

- v23g 監査結果（このファイルの上流入力）: 当 conversation の前ターン
- 仕様書 `D_SafeLogger_Specification_v23_full.md` §11.16.1 / §11.27 / §12.3 / changelog v23h
- 詳細設計 `D-SafeLogger_DetailedDesign_v23.md` §8.5 / §15a.5.5 / changelog v23h
- inventory `D-SafeLogger_v23_baseline_diff_inventory.md` 差分 #1（v23h L4 訂正）

## v23k Multiprocess Observability Test Addendum

v23k では multiprocess runtime observability の回帰を以下のテスト群で固定する。

- `tests/test_runtime_warning.py`: runtime warning JSONL schema、worker warning queue、fallback file、rate limit、non-blocking warning path、module transport coverage、warning queue drain semantics。
- `tests/test_shutdown_report.py`: shutdown report atomic write、clean shutdown、worker crash identity、drain deadline、write failure fallback、writer-side / attempted-side invariant、breakdown source separation、partial delivery independence。
- `tests/test_delivery_status_api.py`: `mp.GetDeliveryStatus()` public API、`DeliveryStatus` required fields、breakdown keys、ACK timeout、active-worker incomplete snapshot、sink reject、partial delivery、snapshot completion after detach。
- `tests/typing_smoke/public_api_smoke.py`: `mp.DeliveryStatus` and `mp.GetDeliveryStatus()` user-facing type smoke.

Quality gates: `uv run pytest tests -q`, `uv run pyright tests/typing_smoke`, `uv run mypy src`, `uv run pyright src`, and `uv run python scripts/check_type_completeness.py --min-score 100`.
