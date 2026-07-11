# D-SafeLogger

[![CI](https://github.com/nightmarewalker/D-SafeLogger/actions/workflows/ci.yml/badge.svg)](https://github.com/nightmarewalker/D-SafeLogger/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/d-safelogger.svg?cacheSeconds=3600)](https://pypi.org/project/d-safelogger/)
[![Python](https://img.shields.io/pypi/pyversions/d-safelogger.svg?cacheSeconds=3600)](https://pypi.org/project/d-safelogger/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#主な特徴)

言語: [English](README.md) | [日本語](README_ja.md)

D-SafeLogger は、外部依存ゼロで stdlib logging 互換の Python ロガーです。Python 標準ライブラリの `logging` を土台にしています。

標準 logging の経路を置き換えるのではなく拡張するため、既存のアプリケーションコードや外部ライブラリの logging 呼び出しを維持できます。開発時は小さく始めつつ、サービス、スケジュール実行、監査向けログ、マルチプロセス worker で、ローカルファイル出力を明示的に制御・確認できる状態へ広げるためのライブラリです。

## 主な特徴

1. **stdlib `logging` 互換**：既存の `logger.info()` 呼び出しと、`logging.getLogger()` を使うサードパーティライブラリのログを、変更なしで同じ logging 構成に参加させられます。

2. **rename しない追記専用ルーティング**：使用中のログファイルを rename / truncate せず、境界到達時に次の出力先ファイルを開きます。rename ベースの rotation で起きやすい Windows のファイルロック問題と、POSIX 系で rename は成功しても writer が古い file descriptor へ書き続ける問題を避けます。

3. **外部実行時依存ゼロ**：runtime package は Python 標準ライブラリだけで動作します。アプリケーションに追加の依存チェーンを持ち込みません。

4. **3行で始めて、設定で運用ポリシーを追加**：最小構成は3行です。呼び出し側のコードはそのままに、設定でモジュール別ログレベルと出力先ファイル（通常本番の分離、開発時の集中調査、障害対応時の一時退避に利用可能）、9種類のルーティング戦略（`daily`, `hourly`, `size` など）、JSON Lines、SHA-256 sidecar / manifest、機微情報マスキング、診断モード、コード / INI・dict / 環境変数による設定レイヤーを追加できます。

5. **堅牢なマルチプロセスファイル logging**：親プロセス側 Writer がファイル書き込みを所有するため、worker は共有ログファイルを直接開きません。reject / drop されたレコードや説明不能なレコードは、単なる原因不明の欠落ではなく明示的に可視化されます。

## どんなときに使うか

D-SafeLogger は、既存の `logging.getLogger()` / `logger.info()` 呼び出しを維持したまま、以下を追加したい場合に向いています。

- 追記専用のローカルファイルルーティング
- 通常本番の分離、開発時の集中調査、障害対応に使える per-module log control
- 環境変数による運用時上書き
- 任意の SHA-256 sidecar / manifest
- 親プロセス側 Writer によるマルチプロセスファイル出力
- 配送状態の分類・説明

一方、アプリケーションが stdout/stderr に出すだけで、外部のログ収集基盤がルーティング、保持、集約、耐久性をすべて担う構成では、D-SafeLogger は必須ではありません。

## インストール

```bash
pip install d-safelogger
```

配布パッケージ名は `d-safelogger`、import 名は `dsafelogger` です。

Python 3.11 以上が必要です。

## クイックスタート

この内容を `quickstart.py` として保存します。

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path="./logs", pg_name="MyApp")

logger = GetLogger(__name__)
logger.info("Application started")
```

`pg_name` はログファイル名の接頭辞として使われるアプリケーション名です（ここでは `MyApp.log`、daily routing を使うと `MyApp_20260403.log` になります）。

実行します。

```bash
python quickstart.py
```

console output:

```text
2026-04-03 09:15:22.738 [INF][quickstart.py:6:<module>] Application started
```

実際の対応ターミナルでは、console output は color-aware になります。ログレベルは強調表示され、日時・発生箇所などのメタ情報は低ノイズに装飾されます。file output はプレーンテキストのままで、ANSI color code は入りません。色を無効化するには `D_LOG_COLOR=0` または標準の `NO_COLOR` 環境変数を設定します。

file output も確認します。

```bash
cat ./logs/MyApp.log
```

file には次のようなプレーンテキスト行が含まれます。

```text
2026-04-03 09:15:22.738 [INF][quickstart.py:6:<module>] Application started
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

後から routing を有効化した場合は、同梱 CLI で routed file を確認できます。

```bash
dsafelogger ls ./logs
dsafelogger tail -f ./logs MyApp
```

`dsafelogger tail -f` は D-SafeLogger の routed file 命名を理解し、routing により次のファイルが作られた場合も追従できます。ログ一覧、live tail、設定テンプレート生成の詳細は [CLI Operations](examples/14_cli_operations.md) を参照してください。

### console-only mode

CLI ツールやローカル開発では、file sink を作らず stderr のみに出力できます。

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(console_out="only")
logger = GetLogger(__name__)
logger.info("hello")
```

`console_out="only"` は stdlib 互換の logger 統合と console formatter を維持しますが、root file sink や module file sink は作成しません。`log_path`、routing、hash sidecar、manifest、module path など file 前提の設定は黙って無視せず fail-fast します。

`ReopenLogFiles()` は file lifecycle API のままです。console-only では reopen 対象の file sink がないため `RuntimeError` を送出します。`dsafelogger.mp` は console-only mode をサポートしません。

運用上の注意:

- `D_LOG_CONSOLE` は通常どおり環境変数 override として最優先です。`D_LOG_CONSOLE=1` または `true` は API/INI の `console_out="only"` を file + console 出力へ戻し、`D_LOG_CONSOLE=0` または `false` は file-only 出力へ戻します。
- file sink を作らない保証は、最終 merge 後の設定が console-only であり、かつ最初の explicit 初期化が `ConfigureLogger(console_out="only")` だった場合に限ります。`GetLogger()` が先に auto-fire した場合や、以前の explicit 設定が file sink を作成済みの場合、後続呼び出しは最初の初期化ではありません。
- `{prefix}_CONSOLE` は `1`, `true`, `0`, `false`, `only` だけを受け付けます。`yes`, `no`, `on`, `off` など従来の bool alias はこの環境変数では invalid として fail-fast します。一方で `{prefix}_COLOR` と `{prefix}_HASH` は invalid 値を無視する従来挙動を維持します。

console-only FAQ:

- **環境変数で file が作られることはありますか?** あります。`D_LOG_CONSOLE=1` / `true` または `0` / `false` は、final mode 解決前に API/INI の指定を上書きします。
- **`GetLogger()` 実行後に console-only へ切り替えられますか?** できません。先行する auto-fire または explicit 初期化が active pipeline を所有済みです。
- **なぜ `D_LOG_CONSOLE=yes` や `on` は失敗しますか?** この環境変数は file sink を作るかどうかを決めるため、曖昧または互換 alias だけの表記は無視せず拒否します。

マルチプロセス構成は [マルチプロセスでのログ出力](#マルチプロセスでのログ出力) を、INI 設定、リクエスト単位のコンテキスト、整合性 sidecar、非同期出力、CLI は [チュートリアル / サンプル](#チュートリアル--サンプル) を参照してください。

設定は fail-fast です。cyclic routing と hash/archive retention の併用、`routing_mode='none'` と D-SafeLogger 側の世代管理、`structured=True` と custom formatter string の併用など、指定しても効果を持てない組み合わせは起動時に拒否します。

## なぜ D-SafeLogger か

D-SafeLogger は、標準 logging の経路を置き換えるのではなく拡張します。`logging.getLogger()` や既存の `logger.info()` の呼び出しはそのまま使い続けられ、その上に安全側に寄せたローカルファイル出力を追加できます。

これは、既に stdlib logging の呼び出しがあるアプリケーションや、`logging.getLogger()` 経由でログを出す外部ライブラリを使うプロジェクトで重要です。D-SafeLogger は、それらのレコードを、同じルーティング、フォーマット、コンテキスト、整合性 sidecar、非同期出力、マルチプロセス Writer 経路へ参加させられます。

ログ呼び出し箇所が安定しているため、コードを変更せずに運用上のログ配置を切り替えられます。同じモジュール別 routing 機構は、3つの目的に使えます。**通常本番運用**では高出力量モジュールや重要モジュールを専用ファイルへ分離し、**開発時**にはアプリケーション全体の verbosity を上げずに特定モジュールだけログレベルを下げ、**障害対応時**には疑わしいモジュールを期限付き調査用の incident file へ退避できます。

すでに `structlog` を構造化 logging のフロントエンドとして使っている場合、D-SafeLogger は置き換えではなく共存を目的にしています。役割分担は明確で、`structlog` がイベント辞書の構築、D-SafeLogger がファイル出力・ルーティング・sidecar・マスキング・運用時の制御を担当します。2つの統合パターンは [Structlog Coexistence](examples/16_structlog_coexistence.md) を参照してください。

## なぜ外部ローテーションではなくルーティングか

従来の外部ローテーションは、外部プロセスが active log file を rename / truncate し、その後でアプリケーション側に reopen を依頼する方式です。広く使われている運用手順ですが、これは「ファイルを後から動かす設計」を成り立たせるための調整であって、ログ出力そのものの処理ではありません。

Windows では、writer が active file を保持しているため rename に失敗することがあります。POSIX 系では `rename()` 自体は成功しやすい一方、writer 側の file descriptor は古いファイルを指したままになることがあります。つまり、rotation がファイル操作として通っていても、新しいログがどこに書かれるかは別問題です。

D-SafeLogger は、active file を後から動かす代わりに、書き込み時点で次の出力先を選びます。結果として、外部からの rename・signal・reopen の連携に頼らずに済みます。

## “Safe” が意味するもの

"Safe" は、あらゆる障害で全レコードの保存を保証するという意味ではありません。避けられる logging 失敗を減らし、観測できる失敗を説明可能にするための設計方針です。

| 側面 | 意味 |
|---|---|
| 起動時の安全性 | 不正な設定値、矛盾したオプション、書き込めない出力先は、本体処理を始める前に初期化時点で失敗させます。 |
| ファイルの安全性 | ログファイルを、書き込み中の active file、close 済みの routed file、任意の SHA-256 sidecar、任意の manifest、後続の転送・アーカイブという明示的なライフサイクルで扱います。整合性機能は close 済みファイルの後続検証のためのもので、アクセス制御ではありません。 |
| レコードとコンテキストの安全性 | context は hand-off 時に producer 側で snapshot します。diagnostic snapshot と Writer 側 formatting では、初期化時に確定した機微情報キーワード集合を使います。 |
| 運用時の制御 | 運用時の上書きは、明示的で operator-owned な操作として設計されています。global および per-module のログレベル、per-module の出力先、ルーティング、ハッシュ出力、timeout 挙動は rebuild なしで切り替えられます。一方、ローカル変数を展開する診断モードは環境変数による明示的な opt-in に限定され、由来不明の INI ファイルからは有効化できません。 |
| 並行性とマルチプロセスの安全性 | スレッド間・プロセス間の logging 経路には、上限つきキュー、明示的な timeout、拒否 / drop 経路、shutdown drain の上限を置きます。無期限待機ではなく、明示的な上限を持つ設計です。 |
| 配送失敗の可視化 | 異常な配送結果は、`mp.GetDeliveryStatus()`、runtime warning JSON Lines、shutdown report JSON として見える形に残します。`UnexplainedLost` も明示的な状態として残すため、異常な実行結果を「ログファイルが短いだけ」として見落としにくくします。 |

append-only routing は、active file を外部から rename / truncate する前提を避ける設計です。ただし、NFS / SMB / CIFS / FUSE / クラウド同期フォルダ / コンテナ bind mount / in-memory filesystem など、ローカルファイルシステムと異なる性質を持つ出力先を完全に安全化するものではありません。監査性を重視する場合、active log は耐久性のあるローカルファイルシステムへ出力し、close 済みの routed file をアーカイブ先やネットワークストレージへ転送する構成を推奨します。

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

**配送状態の分類記録** とは、レコードごとに `KnownRejected` / `KnownDropped` / `UnexplainedLost` と `partial_delivered` を分類し、`mp.GetDeliveryStatus()`、runtime warning JSON Lines、shutdown report JSON に反映する仕組みです。詳細は [`examples/12_multiprocess_logging.md`](examples/12_multiprocess_logging.md)、[`docs/design/D-SafeLogger_DeliveryStatusSchema_v23m.md`](docs/design/D-SafeLogger_DeliveryStatusSchema_v23m.md)、[BENCHMARK.md](BENCHMARK.md) を参照してください。

## マルチプロセスでのログ出力

`dsafelogger.mp` は、複数の worker process から共通の出力先へログを送るための API です。各 worker が同じログファイルを個別に開かない構成を取ります。

このモードでは、親プロセス側の Writer がファイル出力先を所有します。worker は Writer に attach し、IPC 経由でログレコードを送ります。これによりファイル所有が一箇所に集約され、attempted / accepted / delivered / partial-delivered / known-rejected / known-dropped / unexplained-lost といった配送状態のカウンターが公開されます。

公開 API は、よく使われる3つの worker 構成を想定しています。`multiprocessing.Process`、`multiprocessing.Pool`、`concurrent.futures.ProcessPoolExecutor` です。同じ Writer session に、明示的な attach、または Pool / Executor 向けの `GetWorkerInitializer()` helper を使って worker を参加させます。

Writer の終了処理では上限つきの待機を行います。timeout 内で drain と join を試み、設定されていれば runtime warning と shutdown report を残し、host process が無期限に hang し続けることを避けます。

具体的なコード、`multiprocessing` の context ルール、Pool initializer、`ProcessPoolExecutor` 連携、Windows での spawn の注意、カスタムログレベル、attach / detach のライフサイクル、環境変数のチューニング、終了処理は [`examples/12_multiprocess_logging.md`](examples/12_multiprocess_logging.md) を参照してください。

`dsafelogger.mp` の公開 API: `ConfigureLogger`, `AttachCurrentProcess`, `DetachCurrentProcess`, `GetLogger`, `GetWorkerInitializer`, `GetDeliveryStatus`, `DeliveryStatus`, `ReopenLogFiles`。

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

INI ファイル、dict 設定、モジュール別ルーティング、優先順位は [Configuration Guide](examples/02_configuration_guide.md) を参照してください。本番・開発・障害対応で使うモジュール別の出力先とログレベル制御は [Per-module Log Control](examples/24_per_module_log_control.md) を参照してください。ルーティングモードの選び方、削除 / アーカイブによる保持、長期稼働時のファイルライフサイクル例は [Long-Running Service](examples/07_long_running_service.md) を参照してください。

## チュートリアル / サンプル

おすすめの読み順:

- **入門:** 01, 02, 03
- **stdlib と周辺ライブラリ連携:** 03, 04, 15, 16, 18, 19, 20
- **runtime ownership と GUI:** 17, 21, 23
- **Windows とサービス運用:** 05, 07, 13, 14
- **アプリケーションパターン:** 06, 10, 11, 17, 24
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
| 9 | [Diagnostic Debugging](examples/09_debugging_production.md) | 開発・検証・本番調査で使える診断モード、ローカル変数 snapshot、マスキング |
| 10 | [Incident Response Bundle](examples/10_incident_response_bundle.md) | 構造化ログ、診断、hash、manifest を障害調査に使う |
| 11 | [Async & High Throughput](examples/11_async_performance.md) | キューを使った非同期 logging |
| 12 | [Multiprocess Logging](examples/12_multiprocess_logging.md) | worker から親プロセス側 Writer へ送る logging |
| 13 | [External Rotation and Reopen](examples/13_external_rotation_reopen.md) | 外部 rotation 後のファイル再オープン |
| 14 | [CLI Operations](examples/14_cli_operations.md) | `dsafelogger` コマンド |
| 15 | [OpenTelemetry Logging](examples/15_opentelemetry_logging.md) | stdlib instrumentation による trace 連携 |
| 16 | [Structlog Coexistence](examples/16_structlog_coexistence.md) | structlog と併用する構成 |
| 17 | [Container and Collector Coexistence](examples/17_container_collector_coexistence.md) | 外部 collector と共存しながらローカル JSONL も残す |
| 18 | [Console Progress Coexistence](examples/18_console_progress_coexistence.md) | tqdm/Rich の進捗表示と永続ファイル logging の共存 |
| 19 | [Sentry Coexistence](examples/19_sentry_coexistence.md) | remote error tracking とローカル証跡の併用 |
| 20 | [Testing and Warnings](examples/20_testing_and_warnings.md) | pytest caplog と warnings.warn() の routing |
| 21 | [Web Runtime Ownership](examples/21_web_runtime_ownership.md) | Web framework との logger ownership |
| 22 | [Cloud Logging Coexistence](examples/22_cloud_logging_coexistence.md) | cloud logging platform とローカル永続証跡の責務分離 |
| 23 | [GUI Logging (Qt)](examples/23_gui_logging_qt.md) | PySide6 log panel と永続ファイル logging |
| 24 | [Per-module Log Control](examples/24_per_module_log_control.md) | 本番・開発・障害対応で使うモジュール別の出力先とログレベル制御 |

## ベンチマーク

D-SafeLogger は、採用済みの単一プロセス async ベンチマークでは競争力があります。マルチプロセスでは、単純なスループットではなく、親プロセス側 Writer によるファイル出力と配送状態の分類が主な価値です。

ベンチマークには、sink unavailable、burst backpressure、worker crash、warning-IPC fallback、mixed worker behavior、shutdown behavior などのマルチプロセス resilience profile も含まれます。これらはスループット主張ではなく、試みられたレコードを delivered / partial-delivered / known-rejected / known-dropped / unexplained-lost として説明できるかを見るものです。

採用 run、計測条件、主張できる範囲は [BENCHMARK.md](BENCHMARK.md) を、公開済みのサマリーは [`benchmarks/summary/`](benchmarks/summary/) を参照してください。

## テスト / 品質

リリースゲートでは、Python 3.11〜3.14 の Windows / macOS / Linux 上で full dev test suite を実行します。CI では Ubuntu の free-threaded CPython `3.13t` / `3.14t` 互換性ジョブも `PYTHON_GIL=0` で実行します。公開前チェックでは source typing、typing smoke test、packaged `pyright --verifytypes`、生成 API docs、公開設計文書、benchmark summary、パッケージビルド出力も検証します。

詳細は [TESTING.md](TESTING.md) を参照してください。

## 互換性 / 対象外

### Public API の命名

D-SafeLogger の public 関数は、PEP 8 の snake_case ではなく PascalCase を意図的に
採用しています。

Python 標準の `logging` モジュール自体にも、`getLogger()`、`basicConfig()`、
`setLoggerClass()`、`setLogRecordFactory()` のような、アンダースコアを使わない
mixedCase API が正式 API として長く存在します。D-SafeLogger は stdlib `logging`
互換のロガーであり、`logging.getLogger()` や `logger.info()` といった通常の
stdlib logging 呼び出しを維持します。そのうえで、D-SafeLogger 自身が提供する
setup/control API は `ConfigureLogger()`、`GetLogger()`、`RegisterLevel()`、
`ReopenLogFiles()`、`SafeShutdown()` のように PascalCase に統一しています。

同じ camelCase を使うと、D-SafeLogger の setup 呼び出しが隣接する stdlib logging
API と視覚的に区別できなくなります。PascalCase にすることで、logging ドメインの
アンダースコアなしの慣習を保ちつつ、2つの API 層を明確に分離しています。

### 0.4.0 以降への移行

`register_level()` は 0.4.0 以降で `RegisterLevel()` に改名されます。これは public API
命名を意図的に正規化するための変更です。`from dsafelogger import register_level` は
`from dsafelogger import RegisterLevel` に更新してください。

- Python: 3.11 以上。
- OS: Windows, macOS, Linux。
- 実行時依存: なし。
- 型情報: `py.typed` を同梱。CI では `mypy`、`pyright`、typing smoke test、`pyright --verifytypes` による public type completeness 100% を確認します。詳細は [TESTING.md](TESTING.md) を参照してください。
- API docs: [`docs/api/`](docs/api/)。
- Design docs: [`docs/design/`](docs/design/)。
- 配布パッケージ名は `d-safelogger`、import 名は `dsafelogger` です。

D-SafeLogger は log shipper、metrics pipeline、distributed tracing backend、アクセス制御システムではありません。これらの用途には Fluent Bit、Vector、Filebeat、OpenTelemetry Collector、tracing backend などを使ってください。

脆弱性報告は [SECURITY.md](SECURITY.md) を参照してください。

## 設計文書

より深い設計意図と仕様の詳細は、以下を参照してください。

- [アーキテクチャ分析ホワイトペーパー](docs/design/D-SafeLogger_v23m_WhitePaper.md)
- [基本設計仕様書](docs/design/D_SafeLogger_Specification_v23m_full.md)
- [API Reference](docs/api/index.md)

英語版の設計文書も [`docs/design/`](docs/design/) にあります。

## ライセンス

Apache License 2.0。詳細は [LICENSE](LICENSE) を参照してください。

© D-SafeLogger contributors
