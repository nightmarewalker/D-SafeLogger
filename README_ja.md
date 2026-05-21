# D-SafeLogger

[![CI](https://github.com/nightmarewalker/D-SafeLogger/actions/workflows/ci.yml/badge.svg)](https://github.com/nightmarewalker/D-SafeLogger/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/d-safelogger.svg)](https://pypi.org/project/d-safelogger/)
[![Python](https://img.shields.io/pypi/pyversions/d-safelogger.svg)](https://pypi.org/project/d-safelogger/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#主な機能)

言語: [English](README.md) | [日本語](README_ja.md)

## 概要

D-SafeLogger は、外部依存ゼロで stdlib logging 互換の Python ロガーです。Python 標準ライブラリの `logging` を土台にしています。

標準 logging の経路を置き換えるのではなく拡張します。既存の `logging.getLogger()` や `logger.info()` の呼び出しはそのまま参加でき、その上に D-SafeLogger が、追記専用のファイルルーティング、JSON Lines 構造化出力、コンテキスト付与、SHA-256 sidecar、環境変数による運用時の上書き、親プロセス側 Writer が出力先を所有するマルチプロセス logging を追加します。

追記専用ルーティングでは、使用中のログファイルを rename / truncate せず、次の出力先ファイルを開きます。これにより、rename ベースの rotation で起きやすい Windows のファイルロック問題を避けられます。さらに POSIX 系では、rename 自体は成功しても writer 側の file descriptor が古いファイルを指したままになり、ログの書き込み先が新しい世代へ切り替わらない、というずれも避けられます。

製品名にある "Safe" は、fail-fast な初期化、追記専用のファイル処理、producer 側の context snapshot、上限つきキュー、明示的な timeout、配送状態の分類記録といった、運用上の安全側設計を指します。

## インストール

```bash
pip install d-safelogger
```

配布パッケージ名は `d-safelogger`、import 名は `dsafelogger` です。

Python 3.11 以上が必要です。

## クイックスタート

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path="./logs", pg_name="MyApp")

logger = GetLogger(__name__)
logger.info("Application started")
```

`pg_name` はルーティング後のログファイル名の接頭辞として使われるアプリケーション名です。例: `MyApp_20260403.log`。

標準的なテキスト出力:

```text
2026-04-03 09:15:22.738 [INF][app.py:6:<module>] Application started
```

JSON Lines で出力したい場合は、初期化時に `structured=True` を指定します。

```python
ConfigureLogger(log_path="./logs", pg_name="MyApp", structured=True)
logger = GetLogger(__name__)
logger.info("Application started")
```

```jsonl
{"timestamp":"2026-04-03 09:15:22.738","level":"INF","logger":"__main__","message":"Application started"}
```

マルチプロセス構成は [マルチプロセスでのログ出力](#マルチプロセスでのログ出力) を、INI 設定、リクエスト単位のコンテキスト、整合性 sidecar、非同期出力、CLI は [チュートリアル / サンプル](#チュートリアル--サンプル) を参照してください。

設定は fail-fast です。cyclic routing と hash/archive retention の併用、`routing_mode='none'` と D-SafeLogger 側の世代管理、`structured=True` と custom formatter string の併用など、指定しても効果を持てない組み合わせは起動時に拒否します。

## どんなときに使うか

D-SafeLogger は、既存の `logging.getLogger()` / `logger.info()` 呼び出しを維持したまま、以下を追加したい場合に向いています。

- 追記専用のローカルファイルルーティング
- 環境変数による運用時上書き
- 任意の SHA-256 sidecar / manifest
- 親プロセス側 Writer によるマルチプロセスファイル出力
- 配送状態の分類・説明

一方、アプリケーションが stdout/stderr に出すだけで、外部のログ収集基盤がルーティング、保持、集約、耐久性をすべて担う構成では、D-SafeLogger は必須ではありません。

## なぜ D-SafeLogger か

D-SafeLogger は、標準 logging の経路を置き換えるのではなく拡張します。`logging.getLogger()` や既存の `logger.info()` の呼び出しはそのまま使い続けられ、その上に安全側に寄せたローカルファイル出力、rename しない追記専用ルーティング、fail-fast な設定検証、SHA-256 sidecar、機微情報マスキング、環境変数による運用時制御、親プロセス側 Writer によるマルチプロセス対応を追加できます。

すでに `structlog` を構造化 logging のフロントエンドとして使っている場合、D-SafeLogger は置き換えではなく共存を目的にしています。役割分担は明確で、`structlog` がイベント辞書の構築、D-SafeLogger がファイル出力・ルーティング・sidecar・マスキング・運用時の制御を担当します。2 つの統合パターンは [Structlog Coexistence](examples/16_structlog_coexistence.md) を参照してください。

## なぜ外部ローテーションではなくルーティングか

従来の外部ローテーションは、外部プロセスが active log file を rename / truncate し、その後でアプリケーション側に reopen を依頼する方式です。広く使われている運用手順ですが、これは「ファイルを後から動かす設計」を成り立たせるための調整であって、ログ出力そのものの処理ではありません。

POSIX 系では `rename()` 自体は成功しやすい一方、writer 側の file descriptor は古いファイルを指したままになることがあります。つまり、rotation がファイル操作として通っていても、新しいログがどこに書かれるかは別問題で、書き込み先が古い世代に残ったままになることがあります。`logrotate` の `copytruncate` や `delaycompress` は、この状況を運用側で吸収するためのオプションです。

D-SafeLogger は、active file を後から動かす代わりに、書き込み時点で次の出力先を選びます。結果として、外部からの rename・signal・reopen の連携に頼らずに済みます。

## “Safe” が意味するもの

製品名にある "Safe" は、失敗時のふるまいだけを指す概念ではなく、日常の運用の複数の側面にまたがる設計方針です。

- **起動時の安全性:** 不正な設定値、矛盾したオプション、書き込めない出力先は初期化時に失敗させます。壊れた logging 構成のまま本体処理を進め、あとから気づきにくい形で動作が崩れることを防ぎます。
- **ファイルの安全性:** ルーティング層は使用中のログファイルを rename / truncate せず、境界到達時に次の出力先を開きます。これにより active file の rename に起因する Windows 特有の失敗を避けられます。また、POSIX 系で rename が成功しても writer が古い file descriptor へ書き続ける、という世代切り替えのずれも避けられます。ルーティング済みファイルには SHA-256 sidecar と、任意で manifest を付けられ、後からログ内容を検証できます。
- **レコードとコンテキストの安全性:** request ID、user ID、job ID といったコンテキストは producer 側で snapshot を取り、listener / Writer 側では live な `contextvars` を参照しません。diagnostic のローカル変数 snapshot と Writer 側 formatting では、初期化時に確定した機微情報キーワード集合を使います。
- **運用時の制御:** 環境変数により、コードを変更せずにログレベル、診断出力、モジュール別ルーティング、ハッシュ出力、キュー / timeout 設定を切り替えられます。
- **並行性とマルチプロセスの安全性:** マルチプロセスでは worker が共有のログファイルを直接開かず、親プロセス側の Writer が出力先を所有して IPC でレコードを受け付けます。上限つきのキューと明示的な timeout により、本体プロセスが無制限に待ち続けることを避けます。
- **失敗の可観測性:** 配送できなかったレコードは、可能な範囲で `KnownRejected` / `KnownDropped` / `UnexplainedLost` のいずれかに分類されます。カウンタと shutdown summary により、異常時のふるまいが見落とされず、説明できる形で残ります。
- **出力先ファイルシステムの注意:** append-only routing は、active file を外部から rename / truncate する前提を避ける設計です。ただし、NFS / SMB / CIFS / FUSE / クラウド同期フォルダ / コンテナ bind mount / in-memory filesystem など、ローカルファイルシステムと異なる性質を持つ出力先を完全に安全化するものではありません。監査性を重視する場合、active log は耐久性のあるローカルファイルシステムへ出力し、close 済みの routed file をアーカイブ先やネットワークストレージへ転送する構成を推奨します。

## 機能比較

この表は総合的な優劣を示すものではありません。各プロジェクトが、どの関心事を組み込みの設計対象として扱っているかを示すものです。

凡例:

- **◎** 主な強み / 設計上の中核
- **○** 標準で対応
- **△** 公式の設定・アダプターで限定的に対応
- **—** ライブラリ自体の機能としては提供しない
- **※n** 条件・範囲の説明あり

| 機能 | stdlib `logging` | loguru | structlog | D-SafeLogger |
|---|:---:|:---:|:---:|:---:|
| 標準 `logging` API 互換 | ◎ | △※2 | △※3 | ◎ |
| 既存の `logger.info()` / `getLogger()` 呼び出しの維持 | ◎ | △※2 | △※3 | ◎ |
| `logging.getLogger()` を呼ぶ外部ライブラリとの共存 | ◎ | △※2 | △※3 | ◎ |
| 外部実行時依存ゼロ | ◎ | — | — | ◎ |
| handler / formatter 設定を置き換える中央初期化 | △※1 | ◎ | △※3 | ◎ |
| テキストファイル出力 | ○ | ○ | △※3 | ○ |
| JSON Lines 出力 | —※1 | ○ | ◎ | ○ |
| コンテキスト付与 | △※1 | ○ | ◎ | ○ |
| fail-fast な設定検証 | △※4 | △※4 | △※4 | ◎ |
| rename/truncate に頼らない追記専用ルーティング | —※5 | —※6 | —※3 | ◎ |
| ルーティング済みファイルの削除 / アーカイブ | —※5 | ○※6 | —※3 | ○ |
| SHA-256 sidecar / manifest 出力 | — | — | —※3 | ◎ |
| コード / INI-dict / 環境変数の設定レイヤー | △※1 | △※7 | △※7 | ○ |
| 環境変数限定の診断モード | — | —※8 | — | ◎ |
| context snapshot を伴う非同期転送 | △※1 | ○※9 | △※3 | ○ |
| 親プロセス側 Writer によるマルチプロセスファイル出力 | —※10 | —※9 | —※3 | ◎ |
| 配送状態の分類記録 (マルチプロセス) | — | — | — | ◎ |

注記:

- **※1** stdlib `logging` には handler、filter、formatter、`dictConfig`、`QueueHandler`、`QueueListener` などの部品があります。ただし JSON 整形、コンテキスト方針、環境変数を含む多層設定、全体としての検証は、アプリケーション側の組み立てや独自クラスが必要です。
- **※2** loguru は公式に stdlib logging との連携パターンを示していますが、基本は stdlib API 互換ではなく、置き換え型の logger API です。
- **※3** structlog は主に構造化 logging のフロントエンドです。stdlib logging や各種 backend と統合できますが、ファイルのライフサイクル、保持、完全性 sidecar、マルチプロセスでの sink 所有は backend またはアプリケーション側の責務です。
- **※4** 各プロジェクトは自分の設定値の一部を検証します。ただし D-SafeLogger は、マージ後の設定、書き込み先、運用上の安全条件を起動時契約として検証します。
- **※5** stdlib の rotation handler は追記専用ルーティングではありません。rename しないルーティングやルーティング済みファイルの管理には、独自 handler または外部運用ツールが必要です。POSIX 系では rename 自体が成功しても、writer が旧 file descriptor へ書き続ける場合があり、rotation 操作の成功だけでは新しいログが新しいファイルへ向かうとは限りません。
- **※6** loguru は rotation、retention、compression を標準機能として持ちます。ただし、active file を rename/truncate せずに出力先を切り替える D-SafeLogger の追記専用ルーティングとは別物です。D-SafeLogger が避けているのは、active file を後から動かし、その後の reopen 成功に頼る設計です。
- **※7** loguru と structlog はコードによる設定や一部の既定値設定に対応します。D-SafeLogger のようなコード / INI-dict / 環境変数の優先順位つき設定レイヤーとは別の範囲です。
- **※8** loguru は詳細な例外診断を提供しますが、D-SafeLogger の診断モードは安全境界として環境変数からのみ有効化できます。
- **※9** loguru の `enqueue=True` は queue 経由の multiprocessing-safe logging を提供します。ただし、親プロセス側 Writer が sink を所有するモデルではなく、D-SafeLogger と同等の配送状態分類も公開しません。
- **※10** stdlib logging は listener / queue 構成を組めますが、親プロセス側 Writer API としてパッケージ化されているわけではありません。

**配送状態の分類記録** とは、レコードごとに `KnownRejected` / `KnownDropped` / `UnexplainedLost` のいずれかに分類してカウンタや shutdown summary に反映する仕組みです。詳細は [`examples/12_multiprocess_logging.md`](examples/12_multiprocess_logging.md) と [BENCHMARK.md](BENCHMARK.md) を参照してください。

## 主な機能

- **実行時依存なし:** ライブラリ本体は Python 標準ライブラリだけで動作します。
- **stdlib logging 互換:** 既存の `logger.info()` 呼び出しや、`logging.getLogger()` を使う外部ライブラリを、同じ logging 構成に参加させられます。
- **中央初期化:** `basicConfig()`、`dictConfig()`、formatter、handler、rotation 設定の boilerplate を `ConfigureLogger()` に集約できます。
- **fail-fast 初期化:** 不正な設定値や書き込めないログ出力先は初期化時に失敗させ、あとから気づきにくい形で動作が崩れることを避けます。
- **追記専用のファイルルーティング:** ルーティング層は、使用中のログファイルを rename / truncate せず、境界到達時に次の出力先を開きます。Windows の active file rename 失敗だけでなく、POSIX 系で rename が成功したまま writer が旧世代へ書き続ける問題も避けられます。
- **ルーティング済みファイルの保持管理:** ルーティング済みファイルは `backup_count` に基づいて保持できます。古いファイルは purge worker による削除、または `archive_mode=True` による ZIP archive 化が可能です。
- **配送状態の分類:** 失われたレコードをファイル上の見えない欠損として扱わず、可能な範囲で known-rejected / known-dropped / unexplained-lost に分類します。
- **境界をもった logging 経路:** 上限つきキュー、明示的な timeout、明示的な拒否経路を使うことで、logging 処理が本体プロセス側で無制限に待ち続ける設計を避けます。
- **JSON Lines 出力:** ログ収集基盤や監視基盤へ渡しやすい JSON 形式で出力できます。
- **コンテキスト付与:** request ID、user ID、job ID などを、スレッドや非同期境界をまたいでログへ付与できます。`contextvars` の snapshot は producer 側で取り、Writer 側では live な `contextvars` を参照しません。
- **整合性 sidecar:** ルーティング済みログファイルに対して SHA-256 sidecar と、任意で manifest を出力できます。これは closed file の改ざんや破損を後から検出しやすくするためのもので、access-control system や compliance system ではありません。
- **運用時の上書き:** ログレベル、モジュール別ルーティング、コンソール出力、色、ハッシュ、設定ファイルパス、キュー / timeout 関連を環境変数で変更できます。本番障害時にコードを変更せず診断レベルを上げる用途を主に想定しています。
- **環境変数限定の診断モード:** `D_LOG_DIAGNOSE=1` を有効にすると、選択フレームの `f_locals` を展開できます。INI や引数からは意図的に有効化できないため、由来のわからない設定ファイルから ON にされることがありません。
- **非同期出力:** アプリケーションスレッドが直接ファイル出力を待たないよう、キューを介した logging を選べます。
- **カスタムログレベル:** `register_level()` を `ConfigureLogger()` の前に呼ぶことで、組み込みの 5 レベルに加えて任意のレベルを追加できます。
- **外部 rotation 後の再オープン:** `ReopenLogFiles()` およびマルチプロセス版で、`logrotate` などの外部 rotation 後に出力先を再オープンできます。
- **配送状態の可視化 (マルチプロセス):** worker のログ送出について、配送状態のカウンターと shutdown summary が公開されます。異常終了、出力先の不可用、worker クラッシュを見過ごさず、説明できる形で残します。

## マルチプロセスでのログ出力

`dsafelogger.mp` は、複数の worker process から共通の出力先へログを送るための API です。各 worker が同じログファイルを個別に開かない構成を取ります。

このモードでは、親プロセス側の Writer がファイル出力先を所有します。worker は Writer に attach し、IPC 経由でログレコードを送ります。これによりファイル所有が一箇所に集約され、accepted / delivered / rejected / dropped / unexplained-lost といった配送状態のカウンターが公開されます。

Writer の終了処理では上限つきの待機を行います。timeout 内で drain と join を試み、drain が完了しない場合は warning を出し、host process が無期限に hang し続けることを避けます。

具体的なコード、`multiprocessing` の context ルール、Pool initializer、`ProcessPoolExecutor` 連携、Windows での spawn の注意、カスタムログレベル、attach / detach のライフサイクル、環境変数のチューニング、終了処理は [`examples/12_multiprocess_logging.md`](examples/12_multiprocess_logging.md) を参照してください。

`dsafelogger.mp` の公開 API: `ConfigureLogger`, `AttachCurrentProcess`, `DetachCurrentProcess`, `GetLogger`, `GetWorkerInitializer`, `ReopenLogFiles`。

## 設定

D-SafeLogger は 3 つの設定レイヤーを組み合わせます。

| レイヤー | 用途 |
|---|---|
| コード | `ConfigureLogger()` に渡すアプリケーションの既定値 |
| INI または dict | コードを変えずに切り替える配置用設定 |
| 環境変数 | 運用時の一時的な上書きや緊急変更 |

主な環境変数。既定の prefix `D_LOG_*` を使用します。prefix は `ConfigureLogger(env_prefix=...)` で変更できます。

- 単一プロセス: `D_LOG_LEVEL`, `D_LOG_MODULES`, `D_LOG_CONFIG`, `D_LOG_DIAGNOSE`, `D_LOG_CONSOLE`, `D_LOG_COLOR`, `D_LOG_HASH`, `D_LOG_MANIFEST`、および業界標準の `NO_COLOR`。`NO_COLOR` は `env_prefix` の影響を受けません。
- マルチプロセス (`dsafelogger.mp`): `D_LOG_IPC_LOG_TIMEOUT`, `D_LOG_IPC_LOG_QUEUE_MAXSIZE`, `D_LOG_IPC_CLIENT_QUEUE_MAXSIZE`, `D_LOG_WRITER_FLUSH_BATCH`。これらは backpressure 時の挙動を調整するもので、通常は既定値のままで構いません。

INI ファイル、dict 設定、モジュール別ルーティング、優先順位は [Configuration Guide](examples/02_configuration_guide.md) を参照してください。

## チュートリアル / サンプル

おすすめの読み順:

- **入門:** 01, 02, 03
- **stdlib と周辺ライブラリ連携:** 03, 04, 15, 16
- **Windows とサービス運用:** 05, 07, 13, 14
- **アプリケーションパターン:** 06, 10, 11, 17
- **監査と障害調査:** 08, 09, 10
- **マルチプロセス logging:** 12

| # | ガイド | 内容 |
|---|---|---|
| 1 | [Quick Start](examples/01_quick_start.md) | インストール、初期設定、最初のログ出力 |
| 2 | [Configuration Guide](examples/02_configuration_guide.md) | コード、INI/dict、環境変数による設定 |
| 3 | [Migrating from stdlib](examples/03_migration_from_stdlib.md) | 標準 logging からの移行 |
| 4 | [Stdlib Ecosystem Coexistence](examples/04_stdlib_ecosystem_coexistence.md) | 既存の stdlib logging ベースのライブラリ出力を集約 |
| 5 | [Windows Service and Scheduled Batch](examples/05_windows_service_and_scheduled_batch.md) | Windows サービスやスケジュール実行での追記専用ファイル出力 |
| 6 | [Web API Logging](examples/06_web_api_logging.md) | リクエスト単位で関連付けた構造化ログ |
| 7 | [Long-Running Service](examples/07_long_running_service.md) | ルーティング、保持、アーカイブ |
| 8 | [Compliance & Audit Logging](examples/08_compliance_audit.md) | SHA-256 による整合性確認と監査ログ |
| 9 | [Debugging in Production](examples/09_debugging_production.md) | 診断モードとマスキング |
| 10 | [Incident Response Bundle](examples/10_incident_response_bundle.md) | 構造化ログ、診断情報、ハッシュ、マニフェストをまとめる構成 |
| 11 | [Async & High Throughput](examples/11_async_performance.md) | キューを使った非同期 logging |
| 12 | [Multiprocess Logging](examples/12_multiprocess_logging.md) | worker から親プロセスの書き込み役へ送る logging |
| 13 | [External Rotation and Reopen](examples/13_external_rotation_reopen.md) | 外部 rotation 後のファイル再オープン |
| 14 | [CLI Operations](examples/14_cli_operations.md) | `dsafelogger` コマンド |
| 15 | [OpenTelemetry Logging](examples/15_opentelemetry_logging.md) | stdlib instrumentation による trace 連携 |
| 16 | [Structlog Coexistence](examples/16_structlog_coexistence.md) | structlog と併用する構成 |
| 17 | [Container and Collector Coexistence](examples/17_container_collector_coexistence.md) | 外部 collector に任せながらローカル JSONL を残す構成 |

## ベンチマーク

D-SafeLogger は、採用済みの単一プロセス async ベンチマークでは競争力があります。マルチプロセスでは、単純な throughput ではなく、親プロセス側 Writer によるファイル出力と配送状態の分類が主な価値です。

ベンチマークには、sink-unavailable、burst backpressure、worker crash、mixed worker behavior、shutdown behavior などの multiprocess resilience profile も含まれます。これらは throughput claim ではなく、attempted record を delivered / known-rejected / known-dropped / unexplained-lost として説明できるかを確認するものです。

採用 run、計測条件、主張できる範囲は [BENCHMARK.md](BENCHMARK.md) を、公開済みの summary は [`benchmarks/summary/`](benchmarks/summary/) を参照してください。

## テスト / 品質

リリースゲートでは、Windows / macOS / Linux と Python 3.11-3.14 の組み合わせで dev 依存を含む full test suite を実行します。CI では Ubuntu free-threaded CPython `3.13t` / `3.14t` の互換性ジョブも `PYTHON_GIL=0` で実行します。公開前チェックでは、生成済み API docs、公開設計書、ベンチマークサマリー、パッケージ build も検証します。

詳しくは [TESTING.md](TESTING.md) を参照してください。

## 互換性 / 対象外

- Python: 3.11 以上。
- OS: Windows, macOS, Linux。
- 実行時依存: なし。
- 型情報: `py.typed` を同梱。CI で `mypy` / `pyright`、typing smoke test、`pyright --verifytypes` による public type completeness 100% gate を検証。詳細は [TESTING.md](TESTING.md)。
- API docs: [`docs/api/`](docs/api/)。
- Design docs: [`docs/design/`](docs/design/)。
- 配布パッケージ名は `d-safelogger` (ハイフン)、import 名は `dsafelogger` (区切りなし) です。

D-SafeLogger は log shipper、metrics pipeline、distributed tracing backend、アクセス制御システムではありません。これらの用途には Fluent Bit、Vector、Filebeat、OpenTelemetry Collector、tracing backend などを使ってください。

脆弱性報告については [SECURITY.md](SECURITY.md) を参照してください。

## 設計文書

詳細な設計意図と仕様は以下を参照してください。

- [アーキテクチャ分析ホワイトペーパー](docs/design/D-SafeLogger_v23j_WhitePaper.md)
- [基本設計仕様書](docs/design/D_SafeLogger_Specification_v23j_full.md)
- [API Reference](docs/api/index.md)

英訳版の設計文書も [`docs/design/`](docs/design/) 配下に配置しています。

## ライセンス

Apache License 2.0。詳細は [LICENSE](LICENSE) を参照してください。

© D-SafeLogger contributors
