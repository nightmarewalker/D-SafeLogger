# D-SafeLogger 基本設計仕様書 v23j (Capture/Transport/Sink 3層化・dsafelogger.mp 正式仕様・外部 log rotation 共存・Control Plane/Backpressure 固定化・Vendor-Agnostic)

## 1. 文書の目的と位置づけ
本モジュールは、`D` によって提供される様々な Python エコシステム（D-Settings, DPySide, D-MessageRouter 等）の全プロジェクトで共通利用する、軽量・高速・高機能なロギング基盤である。
単体で OSS として公開する前提だが、広く普及させる目的よりも、「D エコシステム」の共通基盤として運用することを最優先とする。
「標準ライブラリへの完全な準拠」を絶対条件としつつ、サードパーティ製ライブラリ（Loguru等）を凌駕する診断能力と、Windows環境での致命的なファイルロック問題を回避する堅牢性を外部依存ゼロで実現する。

※ 本モジュールの最大の特徴であり他に類を見ない独自の強み・価値である「安全性・堅牢性（Safe）」の概念を明確化するため、プロダクト名を **`D-SafeLogger`** としている。

対象 Python バージョンは **3.11 以上** とする。これは基本設計全体で `X | Y` 形式の型ヒント構文を前提とし、今後の実装・ドキュメント・型注釈の整合を保つためである。加えて、通常 build に加えて **Python 3.13 以上の free-threaded build** を設計対象に含める。ただし、実装は 3.14 専用 API に依存せず、3.11+ で統一可能な方式を採用する。

## 2. アーキテクチャと技術的優位点（概要）
* **Zero Dependency (外部依存ゼロ):**
  標準ライブラリのみで構成。外部依存を完全に排除し、サプライチェーンリスクをゼロにする。
* **3層設定管理パイプライン (環境変数 > INI/辞書 > 引数):**
  環境変数（緊急オーバーライド）、INIファイルまたは辞書（運用ベースライン）、ConfigureLogger引数（デフォルト）の3層でマージされる厳格な設定管理。大規模プロジェクトでのモジュール別設定管理と、運用時の確実な制御を両立させる。
* **関心の分離 (Separation of Concerns):**
  ロガーの初期設定（Configure）と各モジュールでの利用（GetLogger）を明確に分けることで、コードの可読性と保守性を高める。
* **Drop-in Replacement (完全な標準互換):**
  `logging.setLoggerClass()` により、標準の `logging.Logger` を継承した独自クラスを返す。SQLAlchemy や Django 等の標準ロギング対応ライブラリへ一切のハックなしにシームレスに注入可能であり、エコシステム全体との強力な互換性と独自機能を両立する。
* **Async Mode (非同期 I/O):**
  `Transport` 抽象（`DirectTransport` / `QueueTransport`）を介した同期・非同期 I/O の統一的制御。メインスレッド（GUIスレッド等）の書き込み遅延を完全に排除する。v18 では producer thread 側でコンテキスト情報と必要時のみ診断情報をスナップショット化し、thread 境界を越えても意味論が崩れない hand-off を行う。v20 では内部アーキテクチャを Capture / Transport / Sink の3層に再構成し、v22c ではこの3層分離を維持したまま multiprocess 版を `dsafelogger.mp` として再設計する。single-process 版の `is_async=True` は thread 境界の hand-off を担い、multiprocess 版ではこれに加えて client → Writer の process 境界 hand-off が導入される。
* **Free-threaded Python Ready (GIL 非依存の共有状態管理):**
  `_configure_state`、`_active_pipeline`、`_active_workers`、`_custom_levels` 等の共有状態は GIL の存在を前提にせず、明示ロックにより保護する。`list` / `dict` の実装依存の原子性には依存しない。
* **Append-Only ルーティング (O(1) File Access):**
  リネームを行わず、出力先ファイル名を動的に決定する Append-Only モデルを採用。Windows 特有のファイルロック競合による `PermissionError` を物理的に回避し、ファイル操作に伴う OS の負荷を O(1) に抑制する。
* **Fire-and-Forget 非同期パージと自己修復性:**
  世代管理（古いファイルの削除やアーカイブ）は出力先切り替え時のみ使い捨ての別スレッドで行う。万一 Windows のファイルロック等でパージに失敗しても、次回の切り替えタイミングで自動的に自己修復（リトライ）を行う。
* **Fail-Fast な初期化検証 & ストレージ事前検証:**
  起動時（`ConfigureLogger` 実行時）に出力先ディレクトリの作成可否やパーミッションを即座にテストし、権限エラーやディスクフルを早期に検知する。INIファイルの不正値もサイレントフォールバックせず即座に例外を送出する。
* **安全を担保する環境変数オンリー設定 (`diagnose`):**
  例外発生時の `f_locals` 自動展開機能を、コード上の戻し忘れ事故を防ぐため、**環境変数からのみ有効化できる**構造を採用。INIファイルからの設定も許容しない「聖域」として保護。
* **JSONL（構造化ログ）の透過的サポート:**
  Append-Only アーキテクチャの強みを維持したまま、1行1JSON オブジェクトの完全な構造化ログへの切り替えをサポート。
* **スレッド/非同期コンテキスト付与 (Contextualize):**
  `contextvars` を活用し、特定の識別子を特定のスコープ内の全ログに自動付与する。スレッドだけでなく非同期（asyncio）タスク間でも完全に独立分離させる。
* **カスタムレベル名とカラー出力:**
  `DBG`, `INF`, `WAR`, `ERR`, `CRI` のレベル名略称に加え、コンソール出力時の ANSI カラー化を標準でサポート。
* **コンソールカラーパレット設定:**
  ビルトイン5段階およびカスタムレベルのコンソールカラー（ANSIカラーコード）を、INI/辞書の `[global]` セクションで `color_{略称}` キーにより変更可能。ターミナル環境や視覚特性に応じた配色カスタマイズを、コード変更なしに実現する。本設定は第2層（INI/辞書）専用であり、環境変数・引数からの設定は意図的に非対応とする。
* **カスタムログレベル (Custom Log Levels):**
  `register_level()` により、標準5段階（DEBUG/INFO/WARNING/ERROR/CRITICAL）に加えて任意の数値位置にカスタムログレベルを差し込み可能。3文字略称・ANSIカラー・便利メソッドの一括登録を `ConfigureLogger` 前の単一呼び出しで完結させる。ビルトイン5段階は不可侵として保護され、3層設定管理パイプラインとも完全に整合する。
* **ファイル完全性検証 (Integrity Verification):**
  ルーティングによるファイル切り替え時に、書き込み完了ファイルの SHA-256 ハッシュを自動生成。`sha256sum -c` 互換のサイドカーファイルと、タイムスタンプ付きマニフェストにより、改竄検知・転送検証・ファイル消失検知を実現する。ハッシュ計算は別スレッドで実行され、メインスレッドの I/O をブロックしない。
* **安全な終了 (Safe Shutdown):**
  通常終了時は queue drain、bounded worker join、handler close の順序を明示的に管理する。`daemon=True` は異常終了時の backstop にとどめ、通常終了時の安全性根拠にはしない。
* **Vendor-Agnostic 原則 (v20):**
  コアモジュール（`src/dsafelogger/` 配下）にベンダー固有の import（OpenTelemetry 等）やデータ参照を一切含めない。OTel 等のベンダー統合は、`file_fmt` / `console_fmt` によるカスタム Formatter の差し込み、`contextualize()` によるコンテキスト注入、`examples/` 配下のサンプルコードとして提供する。
* **Formatter 個別指定 (v20):**
  `file_fmt` / `console_fmt` パラメータにより、ファイル出力とコンソール出力に**個別の Formatter** を指定可能。従来の `fmt` は全体デフォルトとして後方互換を維持しつつ、出力先ごとの差別化を実現する。
* **No-Copy Snapshot (FrozenContext) (v20):**
  コンテキスト管理を `contextvars.ContextVar[dict]` から `contextvars.ContextVar[MappingProxyType]` に変更。`MappingProxyType` による immutability 保証により、async mode でのコンテキスト snapshot / consumer-side hand-off を O(1) の参照渡しに最適化する。なお、`contextualize()` の kwargs には **immutable な値（str, int, float, tuple 等）のみを渡すこと**。contextualize() に渡された kwargs の値が list, dict, set 等の代表的な mutable オブジェクトであった場合、TypeError または ValueError を送出する (Fail-Fast)。これにより、O(1) 参照渡しによる意図しない副作用を開発時に確実に検知する。`MappingProxyType` はトップレベルのキー操作のみを保護し、値が mutable（list, dict 等）の場合は内容変更を防げない。
* **内部3層パイプライン Capture / Transport / Sink (v20, v22c 継承):**
  内部アーキテクチャを Capture（ログ生成）、Transport（転送）、Sink（出力）の3層モデルとして維持する。single-process 版では `DirectTransport` / `QueueTransport`、multiprocess 版では client 側 attach runtime と Writer runtime の間を結ぶ internal transport を用いるが、いずれも Capture と Sink の責務境界は変えない。v22c では「logging 互換は Capture 層の責務」「routing / hash / manifest / reopen / purge は Sink/Writer 側の責務」という分離を multiprocess 正式設計として明文化する。
* **並行安全性の強化 (v21):**
  `ConfigureLogger` の初期化処理（`_do_configure()`）全体を `_lifecycle_lock` 保持下で実行する。`GetLogger` は `'configuring'` 状態を検出して lock 構造待機を行う。これにより初期化中の中途状態読み取りを並行安全に防止する。`AppendOnlyFileHandler` の独立した `self._lock` を廃止し、親クラス `logging.Handler` の lock API（`self.acquire()/release()`）に統一することで二重 lock オーバーヘッドを排除した。
* **module-specific path の Transport 完全統合 (v21):**
  `is_async=True` の意味論を root 経路だけでなく module-specific path 経路にも一貫して適用する。`Pipeline` は `module_transports: dict[str, Transport]` を保持し、`stop()` 時に全 Transport を構造的に停止する。module logger への handler attach は `pipeline.get_module_handler()` を経由する。
* **非破壊 level 表示解決 (v21):**
  `DSafeFormatter.format()` および `ColorStreamHandler.emit()` では、`record.levelname` を変更しない。レベル略称変換と ANSI カラー付与は、表示用の局所マッピングまたは表示用 proxy により解決し、共有 `LogRecord` に対する破壊的変更を避ける。`copy.copy(record)` や try/finally による一時差し替えには依存しない。`logging.Formatter` が許容する `%` / `{}` / `$` の各 style で同一の意味論を保証する。
* **context snapshot fallback の正確化 (v21):**
  Formatter での context 返却を `getattr(record, '_ds_context', None) or get_context()` パターンから `hasattr` ベース分岐に変更。`_ds_context` 属性が存在する場合は空の `MappingProxyType` でも authoritative な snapshot として扱い、Transport を経由しない直接呼び出し時のみ `get_context()` にフォールバックする。

---

## 3. 3層設定管理パイプライン

### 3.1. 設計思想

D-SafeLoggerは、設定の来源を以下の3層に分離し、上位層が下位層を常に上書きする厳格なマージ順序を定義する。

```
第1層: 環境変数（最優先 / 緊急オーバーライド）
  ↓ 上書き
第2層: INIファイルまたは辞書（運用ベースライン）
  ↓ 上書き
第3層: ConfigureLogger 引数（デフォルト / シンプル用途）
```

### 3.2. 各層の役割

**第3層: `ConfigureLogger` の引数（最下位）**

単一ファイルや小規模スクリプトなど、要件がシンプルな場合の初期ベース設定。INIファイルも環境変数も使わない最小構成では、この層のみで完結する。

```python
ConfigureLogger(
    default_level='INFO',
    log_path='./logs',
    routing_mode='daily',
    backup_count=7,
)
```

**第2層: INIファイルまたは辞書（中位）**

多数のモジュールごとのログレベルや出力先を、きめ細かく構造的に管理・可視化するための主軸。ConfigureLoggerの引数で指定可能な全パラメータに加え、モジュール別のレベル・出力先・ルーティング設定をセクションとして記述できる。ConfigureLogger引数の同名パラメータを上書きする。INIファイルの代替として、同等の構造を持つ辞書（`config_dict`）を直接渡すことも可能（§5.7 参照）。

**第1層: 環境変数（最上位）**

起動前に設定する最終上書き手段。ソースコードや設定ファイルを変更せずに、次回の `ConfigureLogger` 実行時に適用される設定値を指定できる。INIファイルの設定を含め、全てを上書きする。

### 3.3. マージの具体例

以下の3層がすべて存在する場合のマージ結果を示す。

```python
# 第3層: ConfigureLogger引数
ConfigureLogger(default_level='DEBUG', log_path='./logs', routing_mode='daily')
```

```ini
# 第2層: INIファイル
[global]
default_level = INFO
backup_count = 30
```

```bash
# 第1層: 環境変数
D_LOG_LEVEL=WARNING
```

マージ結果:
- `default_level` = `WARNING`（環境変数が最終決定）
- `log_path` = `./logs`（INIに記載なし、引数が維持）
- `routing_mode` = `daily`（INIに記載なし、引数が維持）
- `backup_count` = `30`（INIが引数のデフォルト値を上書き）

### 3.4. 設定マージの完全なフローチャート

```
ConfigureLogger() 呼び出し
  │
  ├─ 第3層: 引数値をベース設定として格納
  │
  ├─ config_file / config_dict / {env_prefix}_CONFIG の解決
  │   ├─ {env_prefix}_CONFIG 環境変数あり → そのパスを使用（config_file / config_dict 双方を上書き）
  │   ├─ config_file と config_dict の両方が指定 → ValueError（排他違反）
  │   ├─ config_file 引数あり             → そのパスのINIファイルを使用
  │   ├─ config_dict 引数あり             → 辞書を第2層として使用
  │   └─ いずれもなし                     → 第2層スキップ
  │
  ├─ 第2層: INIファイルまたは辞書の読み込みとマージ
  │   ├─ ファイル不在/読み込み失敗  → Fail-Fast（例外送出）
  │   ├─ [global] セクション           → 引数値を上書き
  │   ├─ [dsafelogger:mod] セクション → モジュール別設定として登録
  │   ├─ color_{略称} キーの抽出      → カラーパレットオーバーライド辞書を構築（§5.3 参照）
  │   ├─ 型変換エラー               → Fail-Fast（例外送出）
  │   └─ diagnose キーが存在        → 無視（警告もエラーもなし）
  │
  ├─ 第1層: 環境変数の適用
  │   ├─ {env_prefix}_LEVEL    → グローバルレベルを上書き
  │   ├─ {env_prefix}_MODULES  → モジュール別設定を上書き（レベル/パスのみ）
  │   ├─ {env_prefix}_CONSOLE  → console_out を上書き
  │   ├─ {env_prefix}_COLOR    → カラー設定を上書き
  │   ├─ {env_prefix}_DIAGNOSE → diagnose を有効化（"1" のみ）
  │   ├─ {env_prefix}_HASH     → enable_hash を上書き
  │   └─ {env_prefix}_MANIFEST → manifest_path を上書き
  │
  │   > v20 明確化: `sens_kws` / `sens_kws_replace` は環境変数からの設定を意図的に非対応とする。これは `diagnose` と同様の「聖域」的扱いであり、センシティブキーワードの意図しない変更を防止するための設計判断である。
  │   > `file_fmt` / `console_fmt` も環境変数からの設定は非対応とする（Formatter インスタンスは環境変数で表現不可能）。
  │
  ├─ sens_kws / sens_kws_replace の解決
  │   ├─ sens_kws_replace=True  → ビルトインキーワードを破棄し、sens_kws のみ使用
  │   └─ sens_kws_replace=False → ビルトインキーワード + sens_kws をマージ（デフォルト動作）
  │
  ├─ Fail-Fast 検証
  │   ├─ log_path のパーミッション/ディスク容量テスト
  │   ├─ モジュール別 path のパーミッションテスト
  │   └─ manifest_path のパーミッションテスト（指定時）
  │
  └─ ハンドラ初期化・ルートロガーへのバインド
```

---

## 4. 運用仕様：環境変数による起動時設定上書き

環境変数を用いて、ソースコードや設定ファイルを変更せずに、`ConfigureLogger` 実行時に適用される全体のログレベル、モジュール別の出力先、各種モードの有無を制御できる。環境変数の値はINIファイルおよびコードの設定を**初期化時に上書き（Override）**する。

本章の環境変数は、**プロセス稼働中に動的反映されるものではない**。変更を反映するには、対象プロセスの再起動、または `ConfigureLogger` が再実行される初期化経路が必要である。

全ての制御用環境変数は `ConfigureLogger` の `env_prefix` パラメータ（デフォルト: `'D_LOG'`）に基づく命名規則に従う。以下、デフォルトプレフィックス `D_LOG` を例に説明する。

### 4.1. 環境変数の全一覧

| 環境変数 | 用途 | 有効値 | 上書き対象 |
|---|---|---|---|
| `{prefix}_LEVEL` | グローバルデフォルトレベル | `DEBUG`〜`CRITICAL` + 登録済みカスタムレベル名 | INI `default_level`、引数 `default_level` |
| `{prefix}_MODULES` | モジュール別レベル/出力先 | `MOD:LEVEL[,...]` | INI モジュール別セクション |
| `{prefix}_DIAGNOSE` | 診断モード（f_locals展開） | `"1"` のみ有効 | **INI/引数からの設定不可（聖域）** |
| `{prefix}_CONSOLE` | コンソール出力の強制制御 | `"1"/"0"`, `"true"/"false"` | INI `console_out`、引数 `console_out` |
| `{prefix}_COLOR` | カラー出力の強制制御 | `"1"/"0"`, `"true"/"false"` | 自動検出を上書き |
| `{prefix}_CONFIG` | INIファイルパスの上書き | ファイルパス | 引数 `config_file` および `config_dict` |
| `{prefix}_HASH` | ハッシュ生成の有効化 | `"1"/"0"`, `"true"/"false"` | INI `enable_hash`、引数 `enable_hash` |
| `{prefix}_MANIFEST` | マニフェストファイルパスの上書き | ファイルパス | INI `manifest_path`、引数 `manifest_path` |
| `{prefix}_IPC_LOG_TIMEOUT` | multiprocess 版 log plane の送信待機時間 | 正の浮動小数点秒数 | multiprocess 引数 `ipc_log_timeout` |
| `{prefix}_IPC_LOG_QUEUE_MAXSIZE` | multiprocess 版 log plane queue 容量 | 正の整数 | multiprocess 引数 `ipc_log_queue_maxsize` |
| `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` | multiprocess 版 process-local async queue 容量 | 正の整数 | multiprocess 引数 `ipc_client_queue_maxsize` |
| `{prefix}_WRITER_FLUSH_BATCH` | multiprocess Writer の flush batch サイズ | 正の整数 | multiprocess 引数 `writer_flush_batch` |
| `NO_COLOR` | カラー出力の強制無効化 | 設定されていれば（値不問） | `{prefix}_COLOR` より優先 |

> ※ `NO_COLOR` は業界標準（https://no-color.org/）であり、`env_prefix` の影響を受けない唯一の環境変数である。

### 4.2. `{prefix}_LEVEL`（グローバルデフォルトレベル専用）

グローバルデフォルトレベルのみを指定する。モジュール別構文は受け付けない。

- 有効値: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`（大文字小文字不問）に加え、`register_level()` で登録済みのカスタムレベル名も使用可能
- INIファイルの `default_level` および ConfigureLogger の `default_level` 引数を上書きする

**設計判断: グローバル専用への限定理由**

モジュール別設定を専用の `{prefix}_MODULES` に分離することで、`{prefix}_LEVEL` の値が単一のレベル名であることが保証され、パースの曖昧性が排除される。

カンマ区切りの値が指定された場合は、Fail-Fastとして `ValueError` を送出し、`{prefix}_MODULES` への移行を促すエラーメッセージを出力する。

```
ValueError: D_LOG_LEVEL contains comma-separated module specs.
Use D_LOG_MODULES for per-module settings.
Example: D_LOG_LEVEL=INFO  D_LOG_MODULES=ModuleA:DEBUG,ModuleB:ERROR
```

### 4.3. `{prefix}_MODULES`（モジュール別個別設定専用）

モジュール別のレベルおよび出力先を環境変数で指定する。

書式: `MOD_SPEC1,MOD_SPEC2,...`

```bash
D_LOG_MODULES=myapp.db:DEBUG,myapp.api:ERROR:/var/log/api.log
```

- INIファイルのモジュール別セクション設定を上書きする
- `{prefix}_LEVEL` のグローバルレベルとは独立して評価される
- 指定されたフィールド（レベル、パス）のみがINI値を上書きし、INI側のルーティング詳細（routing_mode, max_bytes等）は影響を受けず維持される
- レベル名にはビルトイン5段階に加え、`register_level()` で登録済みのカスタムレベル名も使用可能
- 個々の `MOD_SPEC` が書式違反の場合（例: コロン不足など）は、その要素のみを stderr に警告出力してスキップし、他の正常な要素の適用は継続する

#### 4.3.1. レベルのみ指定 (`MOD:LEVEL`)
対象モジュールのレベルのみを変更する（例: `myapp.db:DEBUG`）。INI側でそのモジュールに設定された出力先パスやルーティング設定は維持される。

#### 4.3.2. フル指定 (`MOD:LEVEL:PATH`)
レベルと共に出力先を個別に変更する。INI側で設定されたルーティング関連設定は維持される。
* **PATH がファイル名のみ（パスセパレータなし）**: 全体の `log_path` 直下にそのファイル名で出力される。
* **PATH がディレクトリ構造を含む**: 全体の `log_path` 設定を無視し、指定されたフルパス（絶対または相対）に直接出力される。
* **Windows 絶対パス対応**: PATH 部分は先頭2つのコロン以降をすべて PATH として解釈するため、`myapp.api:ERROR:C:\logs\api.log` のような Windows 絶対パスも指定可能である。

**環境変数のみで新規モジュールを定義した場合のデフォルトルーティング:**
`{prefix}_MODULES` はレベルとパスのみを表現するため、INIに存在しない新規モジュールへ `PATH` を指定して個別ファイル出力させる場合、その個別ハンドラのルーティングモードは `none`（ルーティングなし）を既定とする。

**モジュール別指定を単一環境変数に統合する技術的根拠:**
`GetLogger(__name__)` に渡されるPythonのモジュール名（例: `myapp.db.core`）にはドット（`.`）が含まれるが、Linux/Bashの環境変数命名規則ではドットが使用できない。モジュールごとに個別環境変数を設けると、名前変換のパースバグや名前空間の衝突を誘発するため、単一変数にカンマ区切りで統合する方式を採用する。

### 4.4. `{prefix}_DIAGNOSE`（変数自動展開の制御）

環境変数 `{prefix}_DIAGNOSE=1` が設定された場合に限り、診断モード（例外発生時のローカル変数 `f_locals` 自動展開）が有効化される。`"1"` 以外の値は無視され、`"true"`、`"yes"`、`"True"` 等も有効値とはしない。

**本機能は `ConfigureLogger` の引数としては提供されない。INIファイルからの設定も一切許容しない（聖域）。** これは、開発時のデバッグ設定が本番環境に混入する事故を構造的に防止するための意図的な設計判断である。

- ソースコード上に `diagnose=True` と記述する手段が存在しないため、「コードに書いて戻し忘れる」という事故パターンが物理的に発生し得ない。
- INIファイルはバージョン管理（git）に含まれることが多く、`diagnose = true` がコミットされて本番環境に混入するリスクはコード上の引数と同等である。したがって、INIファイルからの経路も遮断する。
- INIファイルに `diagnose` キーが記載されていても無視される（警告もエラーも出さない、ただの無効キーとして扱う）。
- `"1"` のみに限定することで、運用環境ごとの真偽値表記差異による意図しない有効化を防ぐ。
- 本番環境での有効化が必要な場合は、環境変数の設定というインフラ層の操作として明示的に行うこと。

### 4.5. `{prefix}_CONSOLE` および `{prefix}_COLOR`（コンソール出力の強制制御）

環境変数 `{prefix}_CONSOLE`（有効値: `"1"` / `"0"` または `"true"` / `"false"`: 大文字小文字不問）により、コンソール（標準エラー出力）へのログ出力有無を上書き制御する。
D エコシステム（ecosystem）の他のパラメータと方向性を揃えるための仕様であり、ソースコード内で `console_out=False` と設計されているバックグラウンドサービスでも、起動前の環境変数設定により開発時のみ `True` へ上書きして起動することが可能となる。

また、環境変数 `{prefix}_COLOR`（有効値: `"1"` / `"0"` または `"true"` / `"false"`: 大文字小文字不問）および業界標準の `NO_COLOR` 環境変数を解釈し、ANSIカラー出力の有効化・無効化を強制制御する機能もサポートする。

カラー制御の優先順位は以下の通りとする。

1. `NO_COLOR` が設定されていれば、値を問わず常にカラー無効
2. `NO_COLOR` 未設定で `{prefix}_COLOR` が設定されていれば、その値に従う
3. 両者とも未設定の場合は、`sys.stderr.isatty()` によるTTY判定で自動決定する

### 4.6. `{prefix}_CONFIG`（INIファイルパスの上書き）

環境変数 `{prefix}_CONFIG` にファイルパスを指定することで、`ConfigureLogger` の `config_file` 引数で指定されたINIファイルパスを上書きする。これにより、同一のアプリケーションバイナリを異なる環境（開発/ステージング/本番）で異なる設定ファイルで起動することが可能になる。

**`config_dict` との関係**: `{prefix}_CONFIG` が設定されている場合、`config_file` 引数だけでなく `config_dict` 引数も無視され、環境変数で指定されたINIファイルが第2層として使用される（環境変数は全てに優先する原則）。

### 4.7. `{prefix}_HASH`（ハッシュ生成の有効化）

環境変数 `{prefix}_HASH`（有効値: `"1"` / `"0"` または `"true"` / `"false"`: 大文字小文字不問）により、ファイル完全性検証のためのSHA-256ハッシュ生成の有効・無効を上書き制御する。INIファイルの `enable_hash` および ConfigureLogger の `enable_hash` 引数を上書きする。

本番環境でのみハッシュを有効化する運用例:
```bash
D_LOG_HASH=true
```

### 4.8. `{prefix}_MANIFEST`（マニフェストファイルパスの上書き）

環境変数 `{prefix}_MANIFEST` にファイルパスを指定することで、`ConfigureLogger` の `manifest_path` 引数およびINIファイルの `manifest_path` キーで指定されたマニフェストファイルパスを上書きする。

```bash
D_LOG_MANIFEST=/var/log/audit/checksums.txt
```

### 4.9. `{prefix}_IPC_LOG_TIMEOUT`（multiprocess log plane timeout の上書き）

multiprocess 版 `dsafelogger.mp.ConfigureLogger()` における **通常ログの log plane queue** への送信待機時間を、環境変数 `{prefix}_IPC_LOG_TIMEOUT` により上書きできる。

**適用対象:**
- multiprocess 版のみ
- `LOG` hand-off のみ
- `ATTACH` / `DETACH` / `STOP` / `REOPEN` / `STATUS` などの control plane command には適用しない

**契約:**
- 有効値は **正の浮動小数点秒数**
- `0` 以下、または `None` 相当の値は **`ValueError`**
- 実効値が内部上限 **`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0`** を超える場合は、stderr warning を出した上で **3.0 秒へクリップ**する
- 環境変数は API 引数 `ipc_log_timeout` より優先する

```bash
D_LOG_IPC_LOG_TIMEOUT=1.5
```

### 4.10. `{prefix}_IPC_LOG_QUEUE_MAXSIZE` / `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE`

v23c 以降、multiprocess 版の queue 容量は起動時設定として上書きできる。これらは **bootstrap-time only** の設定であり、Writer runtime 起動後または child attach 後の変更は反映しない。child process 側の環境変数変更で queue size を上書きしてはならず、全 child は `BootstrapContext` に含まれる queue size 契約に従う。

**契約:**
- 有効値は **正の整数**
- `0` 以下は **`ValueError`**
- `100000` を超える値は stderr warning を出した上で初期化を継続する
- `{prefix}_IPC_LOG_QUEUE_MAXSIZE` は `ipc_log_queue_maxsize` 引数より優先する
- `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` は `ipc_client_queue_maxsize` 引数より優先する
- `ipc_client_queue_maxsize` 未指定時は、実効 `ipc_log_queue_maxsize` と同値にする

```bash
D_LOG_IPC_LOG_QUEUE_MAXSIZE=20000
D_LOG_IPC_CLIENT_QUEUE_MAXSIZE=5000
```

### 4.11. `{prefix}_WRITER_FLUSH_BATCH`

v23g 以降、multiprocess Writer の flush 戦略は `writer_flush_batch` で起動時に設定できる。既定値 `1` は per-message flush であり、v23 baseline の durability 契約を維持する。`2` 以上を指定した場合のみ batch flush に opt-in する。

**契約:**
- 有効値は **正の整数**
- `0` 以下は **`ValueError`**
- `1024` を超える値は stderr warning を出した上で初期化を継続する
- 環境変数は API 引数 `writer_flush_batch` より優先する

```bash
D_LOG_WRITER_FLUSH_BATCH=16
```

---

## 5. INIファイル設定仕様（辞書設定を含む）

### 5.1. INIファイルパスの指定方法

INIファイルのパスは以下の2つの経路で指定でき、環境変数が引数を上書きする。INIファイルの代替として辞書（`config_dict`）を使用することも可能（§5.7 参照）。

```python
# 第3層: 引数で指定
ConfigureLogger(config_file='./config/logging.ini')

# 第1層: 環境変数で上書き
# D_LOG_CONFIG=/etc/myapp/logging.ini
```

- `config_file` のデフォルトは `None`（INIファイルなしで動作）
- `config_file` が指定されたがファイルが存在しない/読み込み失敗の場合は **Fail-Fast**（即座に例外送出して起動停止）
- `config_file` が `None`（デフォルト）かつ `{prefix}_CONFIG` も未設定の場合は、INI層をスキップして第3層（引数）のみで動作する

### 5.2. INIファイルフォーマット

標準ライブラリ `configparser` で解釈可能なINI形式を採用する。`ConfigParser(interpolation=None)` で初期化し、`%` のエスケープを不要とする。

```ini
; D-SafeLogger 設定ファイル
; グローバルセクション: [global]
; モジュール別セクション: [dsafelogger:モジュール名]

[global]
; --- グローバル設定（ConfigureLogger引数と対応） ---
default_level = INFO
log_path = ./logs
pg_name = MyApp
is_async = false
backup_count = 30
archive_mode = true
routing_mode = daily
interval = 10
max_bytes = 10485760
max_lines = 10000
; max_count は省略時 None（上限到達エラーモード）
suffix_digits = 3
console_out = true
structured = false
fmt = %(asctime)s.%(msecs)03d [%(levelname)-3s] %(message)s
datefmt = %Y-%m-%d %H:%M:%S
enable_hash = true
manifest_path = /var/log/myapp/audit/checksums.txt
sens_kws = my_secret, api_token

; --- Console color palette ---
; ANSI color codes for each level abbreviation (SGR parameter numbers).
; Only specified keys override defaults; omitted levels keep their colors.
; color_dbg = 36
; color_inf = 32
; color_war = 33
; color_err = 31
; color_cri = 1;31

; --- モジュール別設定 ---
; [dsafelogger:モジュール名] の形式でセクションを分ける

[dsafelogger:myapp.db]
level = DEBUG
; path 省略時は全体の log_path を継承、ルーティングは none

[dsafelogger:myapp.api]
level = ERROR
path = /var/log/myapp/api.log
; path 指定時は独自ルーティングを設定可能
routing_mode = size
max_bytes = 10485760
max_count = 5
suffix_digits = 2

[dsafelogger:myapp.auth]
level = WARNING
path = auth_events.log
; ファイル名のみの場合は全体の log_path 直下に出力
```

> **`interpolation=None` の設計根拠**: `configparser` はデフォルトで `%` を補間文字として解釈するため、ログフォーマット文字列（`%(asctime)s` 等）の記述に `%%` エスケープが必要になる。これはユーザビリティを著しく損なうため、`interpolation=None` を採用してエスケープを不要とする。D-SafeLoggerのINIファイルには変数補間の需要がないため、この設計判断にデメリットはない。

### 5.3. グローバルセクション `[global]` のキー一覧

ConfigureLogger の引数と1対1で対応する。`config_file` 自身は設定対象外（自己参照になるため）。

| INIキー | 対応する引数 | 型 | 備考 |
|---|---|---|---|
| `default_level` | `default_level` | str | カスタムレベル名も使用可能 |
| `log_path` | `log_path` | str | |
| `pg_name` | `pg_name` | str | |
| `env_prefix` | `env_prefix` | str | v20: INI/config_dict での変更は禁止。記載時は stderr 警告して無視。通常は変更不要 |
| `is_async` | `is_async` | bool | `true`/`false` に加え `1`/`0`/`yes`/`no`/`on`/`off` も許容（大文字小文字不問） |
| `backup_count` | `backup_count` | int | |
| `archive_mode` | `archive_mode` | bool | `true`/`false` に加え `1`/`0`/`yes`/`no`/`on`/`off` も許容 |
| `routing_mode` | `routing_mode` | str | |
| `interval` | `interval` | str or int | `10` or `12h` or `1d` |
| `max_bytes` | `max_bytes` | int | |
| `max_lines` | `max_lines` | int | |
| `max_count` | `max_count` | int or 省略 | 省略時/空値は None（上限到達エラーモード） |
| `suffix_digits` | `suffix_digits` | int | |
| `console_out` | `console_out` | bool | `true`/`false` に加え `1`/`0`/`yes`/`no`/`on`/`off` も許容 |
| `structured` | `structured` | bool | `true`/`false` に加え `1`/`0`/`yes`/`no`/`on`/`off` も許容 |
| `fmt` | `fmt` | str | `interpolation=None` のためエスケープ不要 |
| `file_fmt` | `file_fmt` | str | v20 追加。ファイル出力専用のカスタムフォーマット。`fmt` より優先される。省略時は `fmt` にフォールバック |
| `console_fmt` | `console_fmt` | str | v20 追加。コンソール出力専用のカスタムフォーマット。`fmt` より優先される。省略時は `fmt` にフォールバック |
| `datefmt` | `datefmt` | str | 同上 |
| `enable_hash` | `enable_hash` | bool | `true`/`false` に加え `1`/`0`/`yes`/`no`/`on`/`off` も許容 |
| `manifest_path` | `manifest_path` | str | 省略時/空値は None（サイドカーのみ） |
| `sens_kws` | `sens_kws` | str (CSV) | カンマ区切りでセンシティブキーワードを指定（例: `my_secret, api_token`）。ビルトインキーワードに追加される |
| `sens_kws_replace` | `sens_kws_replace` | bool | `true` 時、`sens_kws` でビルトインキーワードを完全に置換する。`true`/`false` に加え `1`/`0`/`yes`/`no`/`on`/`off` も許容 |
| `color_{略称}` | — | str | ANSI SGR パラメータの数値部分（例: `36`, `1;31`, `38;5;208`）。`color_dbg`, `color_inf`, `color_war`, `color_err`, `color_cri` がビルトイン対応。`register_level()` で登録されたカスタムレベルの略称も使用可能。ConfigureLogger 引数・環境変数からの設定は不可（第2層専用）。空文字列で該当レベルのカラー化を無効にする |
| `diagnose` | — | **無効** | 記載されても無視される（聖域） |

**型変換とバリデーション**: INIファイルから読み込んだ文字列値の型変換（`is_async` の bool 化、`max_bytes` の int 化等）やフォーマット違反については、安易にデフォルト値へフォールバックせず、即座に例外を送出して起動を停止させる（Fail-Fast）。デフォルト値へのサイレントフォールバックは「設定が反映されていないのに動いているように見える」という最も危険な障害パターンを生む。

**オプショナルキーの空値処理**: `max_count =`（空値）のように値が空文字列の場合は、「キー不在」と同等（`None`）として扱う。`fmt =` / `file_fmt =` / `console_fmt =` / `datefmt =` のようなオプショナルな書式キーの空値も同様に「未指定」として扱い、通常のフォールバック規則へ委ねる。

**未知キーの扱い**: `[global]` セクションに未知のキーが記載されていた場合、そのキーは stderr に警告出力した上で無視する。既存の有効キーに対する型変換エラーとは異なり、未知キーは設定ミスの通知対象ではあるが、ただちに起動停止にはしない。ただし、`color_` プレフィックスを持つキーはパターンベースで認識されるため、固定キー一覧には含まれない。`color_` プレフィックスのキーは略称部分がビルトイン5段階または `register_level()` で登録済みのカスタムレベルの略称と一致するかを動的に検証し、未知略称の場合は stderr に警告出力してスキップする（Fail-Fast ではない）。

**`color_{略称}` キーのバリデーション**: `color_` プレフィックスのキーに対しては以下のバリデーションが適用される:
* **未知略称**: `color_` の後ろの部分が有効な略称（ビルトイン + カスタムレベル）に一致しない場合、stderr に警告出力してキーを無視する
* **不正文字**: 値に `0-9` と `;` 以外の文字が含まれている場合、stderr に警告出力してキーを無視する
* **空文字列**: 有効。該当レベルのカラー化を無効にする（カラーなしで出力）
* 上記のいずれの場合も Fail-Fast（例外送出）ではなく、警告+スキップで処理を継続する。他の有効なカラー設定の適用は妨げられない

**カスタムレベル名のバリデーション**: `default_level` およびモジュール別セクションの `level` キーは、ビルトイン5段階に加え `register_level()` で登録済みのカスタムレベル名も受け付ける。未登録のレベル名が指定された場合は `ValueError` を送出する（Fail-Fast）。

**v23j: merge 後の統一検証**: Python API 引数、INI/config_dict、環境変数を merge した後、最終的な file sink 設定に対して同じ検証を再実行する。`structured=True` と `fmt` / `file_fmt` / `console_fmt` の同時指定、未登録 `default_level`、`backup_count < 0`、`max_count < 1`、`suffix_digits < 1`、`startup_interval` の `interval < 1` は、指定元に関係なく `ValueError` とする。Python API 直指定の bool 引数（`is_async`, `archive_mode`, `console_out`, `structured`, `enable_hash`, `sens_kws_replace`）は `bool` 型のみを受け付け、文字列の truthy/falsy 解釈は行わない。

**v23j: 無効な機能組み合わせの Fail-Fast**: 以下の組み合わせは、指定された機能が実際には効かない、または意味論を壊すため、warning 補正ではなく `ValueError` とする。

```text
routing_mode='none' + enable_hash=True
routing_mode='none' + backup_count > 0
routing_mode='none' + archive_mode=True
cyclic 系 routing + enable_hash=True
cyclic 系 routing + backup_count > 0
cyclic 系 routing + archive_mode=True
size/count + max_count=None + backup_count > 0
size/count + max_count=None + archive_mode=True
archive_mode=True + backup_count=0
manifest_path 指定 + enable_hash=False
```

ここで cyclic 系 routing は `cyclic_weekday` / `cyclic_month` / `size|count + max_count 指定` を指す。`size/count + max_count=None` は overflow-error mode であり、全ログ保持と容量設計ミスの fail-fast を目的とするため、世代管理 (`backup_count` / `archive_mode`) とは併用しない。

### 5.4. モジュール別セクション `[dsafelogger:モジュール名]`

セクション名の `:` 以降がモジュール名（`GetLogger(__name__)` に渡される名前）に対応する。

`[dsafelogger:]` のようにモジュール名が空のセクションは無効であり、`ValueError` を送出する（Fail-Fast）。

| INIキー | 必須 | 型 | 説明 |
|---|---|---|---|
| `level` | 必須 | str | このモジュールのログレベル（カスタムレベル名も使用可能） |
| `path` | 任意 | str | 出力先パス。省略時はグローバルの `log_path` / `pg_name` を継承 |
| `routing_mode` | 任意 | str | `path` 指定時のみ有効。省略時は `none` |
| `max_bytes` | 任意 | int | `routing_mode=size` 時に必要 |
| `max_lines` | 任意 | int | `routing_mode=count` 時に必要 |
| `max_count` | 任意 | int or 省略 | サイクリック上限 |
| `suffix_digits` | 任意 | int | 省略時はグローバル値を継承 |
| `backup_count` | 任意 | int | 省略時はグローバル値を継承 |
| `archive_mode` | 任意 | bool | 省略時はグローバル値を継承 |

**`path` 省略時のルーティング**:
`path` を省略したモジュール別セクションは、レベルの変更のみを意図している。出力先はグローバル設定と同一ファイルになるため、独自のルーティングは意味を持たない。`path` 省略時に `routing_mode` 等のルーティング関連キーが指定された場合は **stderr に警告を出力し、当該キーを無視する**。

**`path` 指定時のデフォルトルーティング**:
`path` を指定して独自ファイルに出力するモジュールのデフォルトルーティングは `none`（ルーティングなし）とする。これは「出力先を分けるだけでローテーション不要」というシンプルなユースケースを想定したもの。ローテーションが必要な場合は `routing_mode` を明示的に指定する。

**ハッシュ生成のモジュール別制御**: ハッシュ生成はグローバル設定のみとする。モジュール別セクションでの `enable_hash` / `manifest_path` の個別指定は v15a でもサポートしない。全ルーティング対象ファイルに一律適用する方がシンプルで監査上も漏れがない。

**v23j: モジュール別設定の検証同等性**: `path` を持つ module-specific file sink は、routing / 世代管理 / hash / 数値範囲について global file sink と同じ検証を受ける。`level` は `path` の有無に関係なく `get_valid_level_names()` で検証し、未登録名は `ValueError` とする。multiprocess 版では module-specific `level` を worker attach 側の logger level にも反映する。

### 5.5. INIファイルと環境変数 `{prefix}_MODULES` のマージ優先順位

モジュール別設定は INI と環境変数 `{prefix}_MODULES` の両方で指定可能であり、環境変数が優先する。

```ini
; INI: myapp.db は DEBUG、独自ファイルに daily ルーティング
[dsafelogger:myapp.db]
level = DEBUG
path = /var/log/db.log
routing_mode = daily
```

```bash
# 環境変数: myapp.db のレベルを ERROR に緊急変更
D_LOG_MODULES=myapp.db:ERROR
```

この場合、`myapp.db` のレベルは `ERROR` に上書きされる。環境変数では `MOD:LEVEL` のみの指定（パスなし）であるため、INI側で設定された `path`、`routing_mode`、`max_bytes` 等の設定は**すべて維持される**。環境変数 `{prefix}_MODULES` はレベルと出力先パスのみを上書き対象とし、INI側のルーティング詳細は影響を受けない。

### 5.6. Zero Dependency を貫くINIパーサーの実装方針

外部ライブラリ（D-Settings等）を使わず、標準ライブラリの `configparser.ConfigParser(interpolation=None)` を用いた専用の極小INIローダーを D-SafeLogger 内部に内包する。

**設計根拠**: DRY原則（コードの重複排除）よりも、基盤ライブラリとしての「完全なポータビリティ（外部依存ゼロ）」を優先するための明確なトレードオフ。ロガーは全プロジェクトの最下層に位置する基盤であり、他のDエコシステムライブラリ（D-Settings等）がD-SafeLoggerに依存する可能性がある。循環依存を避けるためにも、ロガー自身は外部に一切依存してはならない。

**未知セクションの扱い**: `[global]` と `[dsafelogger:...]` 以外のセクションは stderr に警告出力した上で無視する。これにより、他ツールとの共存やコメント代替セクションの混在を許容しつつ、設定ミスは見逃さない。

### 5.7. 辞書ベース設定 (`config_dict`)

INIファイルの代替として、`ConfigureLogger` の `config_dict` 引数に辞書を直接渡すことで、コード内で完結する第2層設定が可能になる。テスト環境やプログラム的に設定を生成するユースケースで特に有用である。

#### 5.7.1. 辞書の構造

`config_dict` は `dict[str, dict[str, str]]` 型であり、INIファイルと同一のセクション/キー構造を持つ。

```python
ConfigureLogger(
    config_dict={
        'global': {
            'default_level': 'INFO',
            'log_path': './logs',
            'backup_count': '30',
            'sens_kws': 'my_secret, api_token',
        },
        'dsafelogger:myapp.db': {
            'level': 'DEBUG',
        },
        'dsafelogger:myapp.api': {
            'level': 'ERROR',
            'path': '/var/log/myapp/api.log',
            'routing_mode': 'size',
            'max_bytes': '10485760',
        },
    }
)
```

**全ての値は文字列型**: INIファイルから読み込んだ場合と完全に同一の型変換・バリデーションパイプラインを通すため、辞書内の全ての値は文字列として指定する。`int` や `bool` を直接渡すことは `TypeError` となる（Fail-Fast）。これにより、INIファイルと辞書のどちらを使用しても、型変換とバリデーションのコードパスが完全に統一される。

#### 5.7.2. セクション名とキーの規則

* **グローバルセクション**: キー名は `'global'` とする。§5.3 のキー一覧と同一のキーが使用可能
* **モジュール別セクション**: キー名は `'dsafelogger:モジュール名'` とする。§5.4 のキー一覧と同一
* **`diagnose` キー**: INIファイルと同様に無視される（聖域）
* **未知キー/未知セクション**: INIファイルと同一の扱い（未知キーは stderr 警告+無視、未知セクションも stderr 警告+無視）
* **空モジュール名**: `'dsafelogger:'`（モジュール名が空）は `ValueError`（INIと同一）

#### 5.7.3. `config_file` との排他制約

`config_file` と `config_dict` は**排他的**であり、両方を同時に指定した場合は `ValueError` を送出する。

```python
# OK: config_file のみ
ConfigureLogger(config_file='./config/logging.ini')

# OK: config_dict のみ
ConfigureLogger(config_dict={'global': {'default_level': 'DEBUG'}})

# NG: 両方指定 → ValueError
ConfigureLogger(config_file='./logging.ini', config_dict={'global': {'default_level': 'DEBUG'}})
```

**`{prefix}_CONFIG` 環境変数との関係**: `{prefix}_CONFIG` が設定されている場合、`config_file` と `config_dict` の双方を上書きし、環境変数で指定されたINIファイルが第2層として使用される。この場合、`config_file` と `config_dict` の排他チェックは行われない（環境変数が全てに優先するため、引数の排他違反は無関係になる）。

#### 5.7.4. バリデーション

`config_dict` に対しては以下のバリデーションが適用される（全て Fail-Fast）:

| 条件 | 例外 |
|------|------|
| `config_dict` が `dict` 型でない | `TypeError` |
| セクション値が `dict` 型でない | `TypeError` |
| 値が `str` 型でない | `TypeError` |
| `config_file` と同時に指定 | `ValueError` |
| 空モジュール名セクション `'dsafelogger:'` | `ValueError` |
| 値の型変換エラー（bool化、int化等） | `ValueError`（INIと同一） |

---

## 6. ログフォーマットと構造化ログ仕様

### 6.1. デフォルトフォーマット文字列
ファイルおよびコンソール（有効時）とも、デフォルトでは以下の統一フォーマットが出力される。
`%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s`
* **日時形式**: ISO8601 ライクな `%Y-%m-%d %H:%M:%S`
* **レベル名略称**: ビルトインの `DBG`, `INF`, `WAR`, `ERR`, `CRI` に加え、`register_level()` で登録されたカスタムレベルの3文字略称も同一形式で出力される。
* **Contextualize 情報**: メッセージ末尾に `[task_id:42 worker:db_sync]` の形式で付加される（仕様後述）。

### 6.2. カスタムログフォーマットの上書き設定 (fmt / datefmt)
`ConfigureLogger` の引数 `fmt` および `datefmt` に文字列を渡すことで、デフォルトのフォーマットを任意に上書きできる。

* **fmt (str | None)**: `logging.Formatter` の第1引数に対応。`%(message)s` 等を含むログメッセージ形式。
* **datefmt (str | None)**: `logging.Formatter` の第2引数に対応。`%(asctime)s` に適用される日時書式。

なお、詳細設計・実装においては、`fmt` 引数に直接 `logging.Formatter` (またはその派生クラス) の**インスタンス**を渡すことで、標準ライブラリの全機能を活用した高度なカスタマイズ（スタイル指定など）を許容する設計とする。

### 6.3. Formatter 個別指定（v20 新機能）

ファイル出力とコンソール出力に**個別の Formatter**を指定可能。OTel の trace_id をファイルにのみ JSON で出力し、コンソールには簡潔なテキストを維持する、といったユースケースに対応する。

```python
ConfigureLogger(
    file_fmt=StructuredFormatter(),     # ファイルには JSON
    console_fmt='%(levelname)s %(message)s',  # コンソールには簡潔テキスト
)
```

**解決優先度**:
```
file_fmt が指定 → ファイル Sink に使用
file_fmt が None または空文字列 → fmt にフォールバック
fmt も None → デフォルトフォーマット

console_fmt が指定 → コンソール Sink に使用
console_fmt が None または空文字列 → fmt にフォールバック
fmt も None → デフォルトフォーマット
```

* `fmt` は既存の全体デフォルト Formatter（後方互換維持）
* `file_fmt` / `console_fmt` は `str` または `logging.Formatter` インスタンスを受け付ける
* INI / config_dict でも `file_fmt`, `console_fmt` キーとして設定可能（§5.3 参照）
* INI / config_dict 由来で `fmt` / `file_fmt` / `console_fmt` / `datefmt` が空文字列の場合は「未指定」と同等に扱い、フォールバックを適用する
* `StructuredFormatter` は `contextualize()` 情報に加え、`LogRecord` の vendor-neutral な extra 属性を JSON トップレベルへ出力する（標準 `LogRecord` キーと内部 `_ds_*` 属性は除外）
* `file_fmt` / `console_fmt` を指定しなければ v18 と完全に同一の動作（非破壊的変更）

### 6.4. 構造化ログ（JSON Lines 出力）
`ConfigureLogger` に `structured: bool = False` を指定することで、JSON Lines形式（1行1JSON）での出力が可能になる。
構造化ログと Append-Only アーキテクチャは**完全に直交する**ため、ルーティングや世代管理等、下回りのファイル管理層（I/O層）は一切の変更なくそのまま動作する（出力が JSON に代わるだけである）。
`structured=True` 時、`contextualize()` で付与されたコンテキスト情報は、メッセージ末尾のサフィックスではなく、JSONオブジェクトのトップレベルフィールドとして出力される。
本機能（`structured=True`）と カスタムフォーマット（`fmt` / `file_fmt` / `console_fmt` パラメータへの文字列指定、および Formatter インスタンス指定の全ケース）の同時指定は排他指定違反として `ValueError` を送出する。

---

## 7. ログファイル名の決定とルーティング・世代管理仕様

### 7.1. ベースファイル名の決定規則 (pg_name)
モジュール別のフル指定がない場合、ログファイル名は `log_path`（出力先ディレクトリ）と `pg_name`（プログラム名）の組み合わせをベースに決定される。
* **基本構成**: `{log_path}/{pg_name}` （ディレクトリ不在時は `os.makedirs` で自動生成、サニタイズ実施）
* 実際の出力ファイル名は、このベースファイル名に特定のサフィックスが付与されたものになる。

**`pg_name` のサニタイズ規則**:
`pg_name` に OS のファイル名禁止文字（`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`）が含まれていた場合、それらは `_` に置換して使用する。これは Fail-Fast で弾くのではなく、ログ基盤として起動阻害を避けつつ安全なファイル名を生成するための仕様である。

### 7.2. Append-Only アーキテクチャの技術的背景
OSS公開にあたり、なぜ業界標準の「リネーム方式（rename）」を採用しないのかという判断を明確にする。
* **歴史的背景**: リネーム方式は「現在のログは常に `app.log`」という単純さから普及したが、ファイルロックが掛かる **Windows環境では、別の監視ツール等がファイルを開いているだけでリネームが Permission Error となり、バックエンドサービスごとダウンさせる致命的欠陥** を抱えている。
* **技術的優位点**: D-SafeLogger は **Append-Only（一切のリネームを行わず、最初から日付や連番を付与したファイルへストリームを切り替えるのみ）** をアーキテクチャの前提とし、このロック問題を O(1) で完全に排除している。同様の思想は Logback や Log4j2 等の特定オプションにも見られるが、これをデフォルトの核とした設計は Python エコシステムには存在しない。

### 7.3. ルーティングモード (routing_mode) 詳解

#### 7.3.1. ルーティングなし (`none`)
* **挙動**: デフォルト。単一のファイルに追記し続ける。サフィックスなし（`{pg_name}.log`）。
* **v22a: 外部 log rotation 共存**: Linux/Unix 系で `logrotate` 等の外部ローテーターと共存する場合は、本モードのみを正式サポート対象とする。外部側が rename + create を実行した後、アプリケーション側が `ReopenLogFiles()` を明示呼び出しして新しい inode を再 open する。
* **制約**: `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / cyclic 系など D-SafeLogger 自身がファイル切替を担う routing と、外部ローテーション運用は混在させない。`ReopenLogFiles()` は writer-side のいずれかの file sink が `routing_mode != 'none'` の場合 `ValueError` を送出する。

#### 7.3.2. 絶対日時ベース (`daily`, `hourly`, `min_interval`)
時計上の絶対時間に合わせてルーティング（切り替え）する。世代管理の対象となる。
* **daily**: 日付変更時に切り替え。サフィックス `YYYYMMDD`
* **hourly**: 毎正時（0分）に切り替え。サフィックス `YYYYMMDD_HH`
* **min_interval**: 指定された分数間隔で切り替え。サフィックス `YYYYMMDD_HHMM`
  * **[制約]**: 本モードにおいて引数 `interval` は**数値のみ（単位:分）**とし、正時に揃うよう 60 を割り切れる数のみ指定可能とする。有効値は `{1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}` である。

#### 7.3.3. 起動時刻（相対）ベース (`startup_interval`)
アプリケーションの起動時点を基点とし、指定された間隔でルーティングする。世代管理の対象となる。
* **単位・パラメータ**: 最小の切り替え単位は「分」。引数 `interval` には整数のほか、`'12h'` や `'1d'` のような文字列指定による柔軟な設定も受け付ける。
* **サフィックス**: 切り替えが実行された瞬間の絶対日時（`YYYYMMDD_HHMMSS`）を採用する。

#### 7.3.4. リソースベース (`size`, `count`)
ファイルサイズ（`max_bytes`）またはログ行数（`max_lines`）を閾値としてファイルを切り替える。本モードのサフィックスは数字連番となり、**桁数は引数 `suffix_digits`（デフォルト: 3）で制御され、すべての動作においてゼロ埋めが適用される。** `routing_mode='size'` の場合は `max_bytes > 0`、`routing_mode='count'` の場合は `max_lines > 0` が必須であり、0 以下は Fail-Fast（`ValueError`）とする。
パラメータ `max_count` の有無によって本質的な動作目的が分岐する。

* **サイクリックモード (`max_count` 指定あり)**
  * 用途: ディスクを満杯にせず、限定された領域内でログを循環させる。
  * サフィックスは `.000` ～ `.{max_count-1}` の範囲でサイクリックに付与される。（※もし `suffix_digits=2` の場合は `.00` ～ `.{max_count-1}` のようにフォーマットされる）
  * 上限到達後は `0` に戻り、既存ファイルを**上書き**して書き込みを継続する。世代管理機能の**対象外**。

* **上限到達エラーモード (`max_count` 指定なし/None)**
  * 用途: 「ログの欠損や意図しない上書きを絶対に防ぎたい」厳格なシステムの保険。
  * **設計意図**: 本モードは「全ログの欠損なき保持」が目的であり、古いファイルを消す世代管理とは設計意図が相反するため、同じく世代管理の**対象外**とする。`suffix_digits` による桁数指定は、システムが想定するファイル数の上限を設計者が明示するためのものである。
  * **挙動**: 連番は `suffix_digits` の最大値（3桁なら `.999`）までひたすら単調増加する。限界に到達した時点で「容量設計ミス」とみなし、ファイルの切り替え時に `OverflowError` を送出してアプリケーションの実行を停止させる。
  * **`backup_count` / `archive_mode` との関係**: 本モードは全ログ保持を目的とし、古いファイルを処理する世代管理とは設計意図が矛盾する。そのため、`backup_count > 0` または `archive_mode=True` が指定された場合は補正せず、`ConfigureLogger()` 時に Fail-Fast（`ValueError`）とする。

#### 7.3.5. 曜日・月サイクリックベース (`cyclic_weekday`, `cyclic_month`)
周期的な期間の中でログを循環させるモード。一周後は常に上書きし、世代管理の**対象外**。
* **cyclic_weekday**: 曜日。サフィックスは `sun`, `mon`, `tue` 等。
* **cyclic_month**: 月。サフィックスは `01` ～ `12` の数字。

### 7.4. ルーティング設定の典型的なユースケース（TIPS）
* **Webサービス / 常駐デーモン**:
  * `routing_mode='daily'`, `backup_count=30`, `archive_mode=True`
  * （意図：1日1回ファイル変更し、過去30日分については削除せずにZIPアーカイブ化して残す。ディスク圧迫を防ぐ最強の構成）
* **小規模なCLIツール / 短命なバッチ処理**:
  * `routing_mode='none'` （デフォルト）
  * （意図：ログの永続化よりも1ファイルの可読性。数キロバイトで終わるならルーティング動作自体が無駄）
* **超高頻度の Message IO デバッグ**:
  * `routing_mode='size'`, `max_bytes=10485760` (10MB), `max_count=10`
  * （意図：ディスクのパンクを防ぐためにサイクリックモードを使用。合計約100MBの領域内で直近ログだけを永遠に循環書き込みさせる）
* **大規模マイクロサービス（INI活用例）**:
  * INIファイルでモジュール別の出力先・レベルを一元管理し、障害対応時は環境変数で特定モジュールのレベルを上書きして再起動
  * （意図：設定の可視性と運用時の即応性を両立）
* **監査・コンプライアンス対応**:
  * `routing_mode='daily'`, `backup_count=365`, `archive_mode=True`, `enable_hash=True`, `manifest_path='./audit/checksums.txt'`
  * （意図：全ログを1年分保持し、ハッシュで改竄検知。マニフェストで全ファイルの存在確認とハッシュ履歴の一覧化）

### 7.5. ルーティング時の切り替えフローと世代管理（パージ／アーカイブ）仕様
世代管理（`backup_count > 0`）が設定されているルーティングモード（日時ベース等）では、以下のフローでファイルの「切り替え（Routing）」と「処理（Purge/Archive）」が行われる。

1. **切り替えトリガー**: ログの `emit` の直前に、Handler が各 Strategy に「切り替えが必要か」を問い合わせる。
2. **Append-Only ファイル変更**: 切り替えが必要な場合、直前のストリームを `close` し、サフィックスが更新された新しい名前のファイルを `open` する。
3. **ハッシュ生成（`enable_hash=True` 時）とバックグラウンド別スレッドの起動**:
   メインスレッドの I/O をブロックしないよう、切り替え直後にバックグラウンド worker を起動する。`enable_hash=True` かつ **non-cyclic** かつ `backup_count > 0` の場合は、パージ/アーカイブワーカー内でハッシュ生成を先行実行する。`enable_hash=True` かつ **non-cyclic** かつ `backup_count=0` の場合は、独立した `HashWorker` を起動する。cyclic 系ルーティング（`cyclic_weekday` / `cyclic_month` / `size|count + max_count 指定`）と `enable_hash=True` の組み合わせは、同一ファイル名の再利用で hash の意味論が崩れるため、`ConfigureLogger()` 時に Fail-Fast（`ValueError`）とする。これらの worker は safe shutdown 時の join 対象として管理される。ハッシュ生成の詳細は §7.6 を参照。
4. **世代管理における「対象ファイル」の特定**:
   ディレクトリ内の同系統ログファイルを更新日時順でソートし、`backup_count` の保持数を超えた「本来パージ＝削除されるべき古いログファイル群」を特定する。**対象ファイルの特定においては、`pg_name` の前方一致による誤マッチ（例: `pg_name='App'` のパターンが `AppServer_*.log` にもマッチする問題）を防止するため、`pg_name` に完全一致するファイル名プレフィックスのみを対象とする厳密なフィルタリングを行うこと。** 具体的には、対象ファイルは `{pg_name}.log`（NoneStrategy）または `{pg_name}_{サフィックス}.log`（その他の Strategy）のいずれかのパターンに正確に一致するもののみとする。
5. **古いファイルの最終処理 (削除 または アーカイブ)**:
   * **通常モード (`archive_mode=False`)**: 特定された古いファイルをそのまま `unlink`（削除）し、ディスクから完全に破棄する。**`enable_hash=True` の場合、対応する `.sha256` サイドカーファイルも連動して削除する。**
   * **アーカイブモード (`archive_mode=True`)**: 特定された古いファイルを削除する**代わりに**、ZIP形式等で圧縮し保存する。**`enable_hash=True` の場合、対応する `.sha256` サイドカーファイルもZIPに同梱し、元のサイドカーファイルを削除する。**
     * **[ストレージ枯渇の未然防止]**: アーカイブ化は作業領域を消費する。そのため、圧縮処理を開始する前にストレージの空き容量（`shutil.disk_usage` 等）を検証し、不足しそうな場合は処理を中止する。安全性を優先し、コンソール等に警告を送出する（処理自体はそこで中断される）。
6. **自己修復性**: Windows等で別プロセスのロックに阻まれ削除やアーカイブに失敗した場合は、エラーをコンソールに警告のみ出力し、次回の切り替えタイミングでの「リトライ（自己修復）」に委ねる。
7. **同一 family の maintenance 直列化**: 同一の `directory + pg_name` に属する purge/archive は並列実行させない。重複削除・重複ZIP化・競合警告の多発を避けるため、同一 family の maintenance は key 単位に直列化する。

### 7.6. ファイル完全性検証 (Integrity Verification) 仕様

`ConfigureLogger` の `enable_hash` パラメータにより、ルーティング時のファイル切り替え時に書き込み完了ファイルの SHA-256 ハッシュを自動生成する機能を提供する。本機能はオプトイン（デフォルト無効）であり、使用しない場合は一切の追加処理が発生しない。

#### 7.6.1. 設計思想
本機能は**書き込みの都度ではなく、ルーティングによりファイルが切り替わった時点**で、書き込み完了したファイルに対して SHA-256 ハッシュを生成する。

* **ログ本体への影響最小化**: ハッシュ計算は non-cyclic モードでのみ有効化され、パージ/アーカイブと同様に別スレッドで実行される。メインスレッドの I/O を一切ブロックしない（Fire-and-Forget）。ただし safe shutdown 時には bounded wait の対象となる。
* **ファイルの完全性保証**: 書き込みが完了した「確定済みファイル」のみを対象とするため、ハッシュの意味が明確
* **アクティブファイルにはハッシュが存在しない**: 現在書き込み中のファイルに対してはハッシュを生成しない。中間状態のハッシュには意味がないためである

#### 7.6.2. サイドカーファイル（`.sha256`）

ファイル切り替え時、切り替え元の書き込み完了ファイルに対して `{元ファイル名}.sha256` のサイドカーファイルを自動生成する。

**フォーマット**: `sha256sum -c` コマンド互換フォーマット（1行）
```
a1b2c3d4e5f6789...（64文字の16進SHA-256ハッシュ）  MyApp_20260328.log
```

* ハッシュとファイル名の区切りは **半角スペース2つ**（`sha256sum` 互換）
* ファイル名は**相対パス（ファイル名のみ）** を記載する。ログ一式を別の場所に移動（アーカイブ）しても検証が壊れない設計とする

検証方法:
```bash
cd logs/
sha256sum -c MyApp_20260328.log.sha256
# MyApp_20260328.log: OK
```

#### 7.6.3. マニフェストファイル

`manifest_path` が指定された場合に生成される、全ルーティング済みファイルのハッシュ履歴ファイル。

**フォーマット**:
```
[2026-03-28T23:59:59.123] a1b2c3d4e5f6789...  MyApp_20260328.log
[2026-03-29T23:59:59.456] b2c3d4e5f6789a1...  MyApp_20260329.log
```

各行の構成:

| フィールド | 内容 | 形式 |
|-----------|------|------|
| タイムスタンプ | ハッシュ確定日時 | `[ISO8601]`（ミリ秒付き） |
| ハッシュ値 | SHA-256（64文字） | 16進文字列 |
| ファイル名 | 対象ログファイル | 相対パス（ファイル名のみ） |

**動作仕様**:
* **追記（Append）形式**: ルーティングが発生するたびに1行追記する。上書きは行わない
* **タイムスタンプの付与**: ハッシュが確定した日時を記録し、「いつ書き込みが完了したか」の証跡とする
* **ディレクトリの自動生成**: `manifest_path` のディレクトリが存在しない場合は `os.makedirs(exist_ok=True)` で自動生成する
* **ファイル名は相対パス**: マニフェスト内のファイル名はファイル名のみ（ディレクトリ部分を含まない）とする
* **直列化**: 同一 `manifest_path` への追記は常に1 threadずつ行う。マニフェスト行の破損や行単位の競合を防ぐためである

**マニフェストの運用上の価値**:
* **ファイル消失の検知**: マニフェストに記載されているがディスク上に存在しないファイルは「削除された」と判定できる。サイドカーファイルのみでは、ファイルとサイドカーが一緒に削除された場合に検知不可能
* **改竄耐性の向上**: マニフェストをログ本体とは別ディレクトリ・別権限で保管することで、ログファイルが攻撃者に操作されてもマニフェストとの不整合で検知可能
* **履歴の俯瞰**: 過去N日分のログが全て揃っているかを、マニフェスト1ファイルの行数で即座に確認可能

#### 7.6.4. 実行順序とスレッドモデル

ハッシュ生成はパージ/アーカイブより先に完了している必要がある（パージがファイルを削除する前にハッシュを計算するため）。以下の方式で順序を保証する:

| 条件 | 実行方式 |
|------|---------|
| `enable_hash=True` かつ non-cyclic かつ `backup_count > 0` | `PurgeWorker` / `ArchiveWorker` 内でハッシュ生成を先行実行 |
| `enable_hash=True` かつ non-cyclic かつ `backup_count=0` | 独立した `HashWorker` を Fire-and-Forget で起動 |
| cyclic 系 routing かつ `enable_hash=True` | `ConfigureLogger()` 時に Fail-Fast（`ValueError`） |
| `enable_hash=False` | ハッシュ関連処理なし |

ハッシュ生成の失敗（`OSError` 等）は、パージの自己修復性と同様に stderr への警告出力のみで処理を続行する。

**sidecar 書き込みの原子性**: `.sha256` サイドカーは途中書き込み状態を外部へ見せないよう、一時ファイルへ書き込んだ後 `os.replace()` により本命ファイルへ原子的に差し替える方式を推奨する。

#### 7.6.5. サイクリックモードでの考慮

`cyclic_weekday` / `cyclic_month` および `size`/`count` の `max_count` 指定ありモード（`is_cyclic()=True`）では、ファイル名が再利用される。cyclic mode は「履歴を残さない」モードであり、ハッシュ検証の意味論を保てないため、v23j では `enable_hash=True` との併用を補正せず、`ConfigureLogger()` 時に Fail-Fast（`ValueError`）とする。マニフェスト / サイドカーファイルの意味論を曖昧にしないための設計判断である。

#### 7.6.6. バリデーション

| 条件 | 挙動 |
|------|------|
| `enable_hash=False` かつ `manifest_path` 指定あり | Fail-Fast（`ValueError`）。マニフェストだけを生成する意味論は持たない |
| `routing_mode='none'` かつ `enable_hash=True` | Fail-Fast（`ValueError`）。ルーティングが発生しないためハッシュ生成タイミングが存在しない |
| cyclic 系 routing かつ `enable_hash=True` | Fail-Fast（`ValueError`）。ファイル名再利用によりハッシュ検証の意味論を保てない |
| `routing_mode='size'` かつ `max_bytes <= 0` | `ConfigureLogger` 時に Fail-Fast（`ValueError`） |
| `routing_mode='count'` かつ `max_lines <= 0` | `ConfigureLogger` 時に Fail-Fast（`ValueError`） |
| `manifest_path` のディレクトリが書き込み不可 | `ConfigureLogger` 時に Fail-Fast（`PermissionError`） |

#### 7.6.7. スコープ外

* **HMAC署名**: 秘密鍵による HMAC 署名は、鍵管理（保存場所、環境変数渡し、ローテーション）という本質的に異なる責務を持ち込むため、D-SafeLogger の「軽量・Zero Dependency な基盤ライブラリ」という性格を超える。署名が必要なエンタープライズ用途は、D-SafeLogger が生成したハッシュを入力とする外部ツール（Dエコシステムの別ライブラリ等）で対応する方針とする。
* **CLI検証コマンド**: v15a では `dsafelogger` CLIへのハッシュ検証サブコマンドの追加は行わない。`sha256sum -c` 互換フォーマットの採用により、OS標準コマンドで即座に検証可能であるため。

---

## 8. CLI ツール (`dsafelogger`) の基本設計と実装方針
Append-Only ルーティングは致命的なファイルロックを回避する長所を持つ反面、「書き込み先のファイル名が動的に変わるため、常に同じ `app.log` を `tail -f` できない」という弱点を持つ。これを克服するため、**専用の CLI ユーティリティ群** をパッケージに同梱する。

### 8.1. 提供コマンド (サブコマンド)
CLIでのコマンド入力のしやすさ（タイピング時のハイフン省略）を優先し、コマンド名は PyPI パッケージ名 `d-safelogger` からハイフンを除外した `dsafelogger` を採用している。
* **`dsafelogger init`**: INI設定ファイルのテンプレートを **標準出力** に出力する。ファイルパスを引数に取らず、シェルリダイレクトでユーザーが保存先を自由に制御する設計とする。これにより、既存ファイルの上書き確認等の複雑さを回避し、パイプやリダイレクトとの組み合わせも容易になる。
* **`dsafelogger ls [log_dir]`**: 指定ディレクトリ内の D-SafeLogger ファイルをパースし、どのプログラムのどのログが最新のアクティブファイルかを一覧表示する。
* **`dsafelogger tail -f <log_dir> <pg_name> [options]`**: 指定されたプログラムの最新ログファイルを自動判定して追随（Follow）する。
  * **透過的なファイル追随:** 出力中に元アプリケーション側でログの「日跨ぎ」等によりファイルが切り替わった場合でも、CLIがそれを動的に検知し、透過的に `tail` 先を新ファイルへ差し替えて出力を継続し続ける。

#### 8.1.1. `dsafelogger init` の使用例

```bash
# テンプレートを生成してファイルに保存
dsafelogger init > ./config/logging.ini

# 中身を確認してから保存
dsafelogger init | less
```

#### 8.1.2. `dsafelogger init` の出力サンプル

テンプレートには全設定キーがコメントアウト状態で記載され、各キーの役割とオプション選択肢がインラインコメントで説明される。ユーザーは必要な行のコメントを外して値を編集するだけで設定ファイルを作成できる。

```ini
; =============================================================================
; D-SafeLogger configuration template
; Generated by: dsafelogger init
;
; Lines starting with ';' are comments.
; Uncomment and modify values as needed.
; =============================================================================

[global]

; --- Basic ---
; default_level = INFO
; log_path = .
; pg_name = Default
; env_prefix = D_LOG
; console_out = true
; is_async = false

; --- Log format (choose ONE) ---
;
;   Option A: Human-readable (default)
;     Customizable with fmt/datefmt.
;
; fmt = %(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s
; datefmt = %Y-%m-%d %H:%M:%S
;
;   Option B: Structured JSON Lines
;     Cannot be combined with fmt/datefmt.
;
; structured = false

; --- Routing mode (choose ONE) ---
;
;   'none'       : Single file, no switching (default)
;   'daily'      : Switch at midnight
;   'hourly'     : Switch every hour
;   'min_interval'      : Switch at fixed-minute boundaries
;   'startup_interval'  : Switch after elapsed time from startup
;   'size'       : Switch when file exceeds max_bytes
;   'count'      : Switch when file exceeds max_lines
;   'cyclic_weekday'    : Overwrite by day-of-week (7 files)
;   'cyclic_month'      : Overwrite by month (12 files)
;
; routing_mode = none

;   Parameters for 'min_interval':
;     interval must be a divisor of 60 (5, 10, 15, 20, 30, etc.)
; interval = 10

;   Parameters for 'startup_interval':
;     integer (minutes) or duration string ('12h', '1d')
; interval = 10

;   Parameters for 'size':
; max_bytes = 10485760

;   Parameters for 'count':
; max_lines = 10000

;   Parameters for 'size' / 'count' (cyclic mode):
;     Omit or leave empty for overflow-error mode (keep all files).
; max_count =
; suffix_digits = 3

; --- Retention (requires routing_mode != 'none') ---
;
;   backup_count: Number of old files to keep. 0 = no deletion.
;   archive_mode: If true, old files are ZIP-archived instead of deleted.
;                 Only meaningful when backup_count > 0.
;
; backup_count = 0
; archive_mode = false

; --- Integrity verification (requires routing_mode != 'none') ---
;
;   enable_hash:   Generate .sha256 sidecar on file switch.
;   manifest_path: Append hash history to this file.
;                  Only meaningful when enable_hash = true.
;
; enable_hash = false
; manifest_path =

; --- Console color palette ---
;
;   Customize ANSI color codes for each log level.
;   Values are SGR parameter numbers (without \033[ prefix and m suffix).
;   Only specified keys override defaults; omitted levels keep their colors.
;
;   Common codes:
;     30=black, 31=red, 32=green, 33=yellow, 34=blue, 35=magenta, 36=cyan, 37=white
;     90-97=bright variants (90=dark gray, 91=bright red, ...)
;     1=bold, 4=underline, 1;31=bold red
;     38;5;N=8-bit color, 38;2;R;G;B=24-bit true color
;     Empty value disables color for that level.
;
; color_dbg = 36
; color_inf = 32
; color_war = 33
; color_err = 31
; color_cri = 1;31

; --- Sensitive keyword customisation ---
;
;   sens_kws:         Comma-separated extra keywords added to
;                     the built-in 12 masking words.
;   sens_kws_replace: If true, built-in keywords are replaced
;                     entirely by sens_kws (default: false).
;
; sens_kws =
; sens_kws_replace = false

; =============================================================================
; Per-module settings
;
; Section name format: [dsafelogger:<module_name>]
;   <module_name> corresponds to GetLogger(__name__)
;
; 'level' is required. Other keys are optional.
; 'path' enables independent file output for this module.
;   - Filename only  : output under global log_path
;   - Full/abs path  : output to specified path directly
; Routing keys (routing_mode, max_bytes, etc.) are only valid
;   when 'path' is specified. Ignored otherwise.
; =============================================================================

; [dsafelogger:myapp.db]
; level = DEBUG

; [dsafelogger:myapp.api]
; level = ERROR
; path = /var/log/myapp/api.log
; routing_mode = size
; max_bytes = 10485760
; max_count = 5
; suffix_digits = 2
; backup_count = 10
```

### 8.2. 実装アーキテクチャ・ヒント
* **外部依存ゼロ**: `argparse` をはじめとする標準モジュールのみで構築する。
* **透過的なファイル追随の実装方針**: ファイル変更の検知は、対象ディレクトリ内を周期的に `os.stat` と名前でポーリングし「最新サフィックスに対応するファイル」に更新があったかを比較するアプローチを取る。これにより、外部監視ライブラリなしで安全なファイルスイッチを実現する。

---

## 9. 各種基盤機能の基本設計と実装ヒント

※ 本章では要件だけでなく、詳細設計者・実装者がコーディングする上での具体的な実装方針を併記する。

### 9.1. Fail-Fast: 初期化時の出力先パーミッションチェック
`ConfigureLogger` 実行時、「テストファイル作成」等を行ってパーミッションとディスク空き領域を即座に検証する。実行後数時間経ってログが吐けない事態を防ぎ、起動フェーズで早期にフェイタルエラー（Fail-Fast）を出す堅牢性を担保する。
`log_path` のディレクトリが存在しない場合は `os.makedirs(exist_ok=True)` で自動生成した上で検証する。
INIファイルで指定されたモジュール別の `path` についても同様のパーミッション検証を行う。
`manifest_path` が指定された場合は、そのディレクトリの書き込み可否も同時に検証する。

### 9.2. 初期化の冪等性とロガーの取得、標準互換性

* `ConfigureLogger` は複数回呼び出されても安全に動作する。**初期化状態は5状態で管理する:**
  * **`unconfigured`（未設定）**: 初期状態。`ConfigureLogger` はフル初期化を実行する。
  * **`auto`（自動発火済み）**: `GetLogger` が `ConfigureLogger` 前に呼ばれた際、デフォルト引数で自動的に初期化された状態。この状態からの明示的な `ConfigureLogger` 呼び出しは **再設定を許可する**（既存 `Pipeline` を `stop(timeout)` で停止・クリーンアップし、明示的に指定された引数で再初期化する）。
  * **`explicit`（明示的設定済み）**: アプリケーションコードから明示的に `ConfigureLogger` が呼ばれた状態。この状態からの2回目以降の `ConfigureLogger` 呼び出しは **No-Op** となる。
  * **`configuring`（初期化中）**: `ConfigureLogger` の実行途中状態。`_lifecycle_lock` を保持した単一オーナー状態であり、二重初期化や TOCTOU を防ぐための内部状態。
  * **`shutting_down`（終了中）**: `_shutdown()` の実行途中状態。終了競合を抑止するための内部状態。shutdown 完了後は `unconfigured` へ遷移し、再初期化を許可する。

> **v20 追加: 完全状態遷移表**
>
> | 現在 | イベント | 遷移先 |
> |------|---------|--------|
> | `unconfigured` | `ConfigureLogger()` | `configuring` |
> | `unconfigured` | `GetLogger()` 先行 | `configuring` (自動発火) |
> | `configuring` | 正常完了 | `explicit` or `auto` |
> | `configuring` | 例外発生 | `unconfigured` (rollback) |
> | `configuring` | 同一thread再入 | No-Op return |
> | `auto` | `ConfigureLogger()` | `configuring` (旧Pipeline停止→再初期化) |
> | `auto` | `_shutdown()` | `shutting_down` |
> | `explicit` | `ConfigureLogger()` | No-Op return |
> | `explicit` | `_shutdown()` | `shutting_down` |
> | `shutting_down` | 完了 | `unconfigured` |
> | `shutting_down` | `ConfigureLogger()` | No-Op |
>
> `configuring` 中の例外処理: `try/finally` により `_configure_state` が `configuring` のまま残ることを防止。
> `_lifecycle_lock` は `RLock` とし、同一スレッドの再入は No-Op return、別スレッドは lock acquire 待機後に状態を再評価する。

* `GetLogger` は標準の `logging.getLogger` をラップし、キャッシュされたロガーを返す（`name=''` はルートロガー）。まだ `ConfigureLogger` が呼ばれる前に `GetLogger` が実行された場合は、デフォルト引数を使用して内部で `ConfigureLogger` を自動発火させ（状態は `auto` に遷移）、初期化漏れによる動作不全を防ぐ。
* **5状態中の競合時挙動**:
  * `configuring` 中の追加 `ConfigureLogger` は、**別 thread では `_lifecycle_lock` の解放まで待機し、その後に状態を再評価する**。同一 thread の再入のみ安全な短絡 return を許可する。
  * `configuring` 中の `GetLogger` も、**別 thread では初期化完了まで待機**し、同一 thread の再入のみ既存 logger 返却で短絡する。
  * `shutting_down` 中の `ConfigureLogger` は新規初期化を行わず、No-Op または明示的拒否のいずれかで状態破壊を防ぐ。
  * `shutting_down` 中の `GetLogger` は既存 logger を返してよいが、新たな初期化を暗黙発火してはならない。
  * `shutting_down` 中の `register_level()` は `RuntimeError` とする。
* **標準互換性とテスト**: `DSafeLogger` は標準の `logging.Logger` 完全互換であるため、`pytest` の `caplog` フィクスチャや組み込みの `SMTPHandler` 等がそのまま機能する。
* **free-threaded 対応原則**: `_configure_state`、`_active_pipeline`、`_active_workers`、`_custom_levels` などの共有状態は明示ロックで保護する。GIL の存在や `list` / `dict` の内部ロックを安全性根拠にしてはならない。

### 9.3. Async Mode (非同期 I/O モード) と安全な終了
* `is_async=True` 時、ルートロガーには stdlib 既定の `QueueHandler` ではなく、D-SafeLogger 専用の queue hand-off 実装をバインドする。これは producer thread のコンテキスト情報と diagnose 情報を queue 越しに安全に伝搬させるためである。
* **コンテキスト hand-off**: async mode では、producer thread 側で `contextualize()` 情報を `LogRecord` の private 属性へスナップショットし、consumer thread 側ではそのスナップショットを優先的に使用する。これにより、async mode でも sync mode と一貫した contextualize 意味論を維持する。
* **diagnose の lazy path**: diagnose 用の重い `repr()` 展開は、`diagnose=True` かつ `exc_info` ありの場合にのみ producer thread 側で実行する。通常ログでは copy + context snapshot の軽量 hand-off を行う。
* **`QueueHandler.prepare()` の完全オーバーライド**: D-SafeLogger の queue hand-off は stdlib `QueueHandler.prepare()` をそのまま使わず、`super().prepare()` も呼ばない完全オーバーライドとする。これにより Python 3.11 / 3.13 / 3.14 間の stdlib 差異を意味論から切り離す。
* **安全な終了の保証レベル**:
  * **ログ本体の flush** は最優先。通常終了時は queue drain が成功した限り、shutdown 開始前に受理済みの queued log record の出力完了を目指す。
  * **housekeeping (`hash` / `purge` / `archive`)** は best-effort。bounded wait を行うが、timeout 時は warning を出して終了を優先する。
* **推奨終了順序**: 通常終了時は (1) 状態遷移と参照退避 → (2) queue drain → (3) worker join → (4) handler flush/close の順で処理する。特に worker join より先に listener を停止する。listener が最後の queued record を処理する過程で rollover を起こし、新しい worker を起動しうるためである。
* **`daemon=True` の位置づけ**: daemon thread は shutdown 時に abrupt に停止しうるため、通常終了時の安全性根拠にはしない。`daemon=True` は異常終了時の backstop にとどめる。
* **timeout と finalization**: shutdown では queue drain timeout と worker join timeout を分離する。late finalization により `join()` が継続不能な場合は warning に degrade し、終了を優先する。

### 9.4. Variable Dumping と Diagnose の実装方針
* 環境変数 `{prefix}_DIAGNOSE=1` が有効な場合、例外ログに対して専用のフォーマッタが適用され、`f_locals` を展開記録する。
* `structured=True` かつ `{prefix}_DIAGNOSE=1` の場合、`f_locals` 情報は展開文字列ではなく、JSONオブジェクトの `locals` フィールドとして包含出力される。
* **センシティブ情報の保護**: `f_locals` 展開時は、変数名にセンシティブ語を含む値を、そのまま出力せず `*** MASKED ***` へ置換する方針とする。
  * **ビルトインキーワード（12語）**: `password`, `passwd`, `pass`, `secret`, `token`, `key`, `api_key`, `apikey`, `auth`, `credential`, `private`, `cert`
  * **`sens_kws` によるカスタマイズ**: `ConfigureLogger` の `sens_kws` パラメータ（またはINI/辞書の `sens_kws` キー）でユーザー独自のセンシティブキーワードを追加指定可能。デフォルトでは指定されたキーワードがビルトインキーワードに**追加**される。
  * **`sens_kws_replace` による完全置換**: `sens_kws_replace=True` を明示的に指定した場合、ビルトインキーワードは破棄され、`sens_kws` で指定したキーワード**のみ**がマスキング対象となる。これにより「ビルトインの `key` が広すぎてマスキングされすぎる」等の問題をユーザーが完全に制御可能。
  * **マッチング**: 変数名に対する部分一致（大文字小文字不問）で判定する。例えば `password` は `user_password`, `PASSWORD_HASH`, `my_password_field` のいずれにもマッチする。
* **巨大reprの抑制**: 個々のローカル変数の `repr()` は一定長で打ち切り、巨大オブジェクトや過度に冗長なデータがログを汚染しないようにする。`repr()` 自体に失敗した場合も診断ログ全体を壊さず、失敗した旨をプレースホルダとして出力する。
* **cross-thread 安全性**: free-threaded build では、実行中の他 thread の frame に対する `f_locals` live 参照は unsafe である。したがって、queue を跨ぐ hand-off が発生する場合は producer thread 側で traceback と `f_locals` を安全なマスク済み repr スナップショットへ変換し、consumer thread 側では live 参照を行わない。
* **フォールバック規則**: formatter は (1) queue hand-off 済みの診断スナップショットがあればそれを使用、(2) 同一 thread 内で `exc_info` が保持されている場合のみ live 参照を許可、(3) それ以外は standard traceback のみを出力する。
* **[実装方針]**: diagnose の有効/無効は `ConfigureLogger` 実行時に `{prefix}_DIAGNOSE` から解決し、formatter / queue hand-off / diagnostic snapshot へ一貫して伝搬させる。heavy path は `exc_info` の存在時にのみ通す。

### 9.5. スレッド / 非同期コンテキスト (Contextualize) の実装方針
* **[実装方針]**: `contextvars.ContextVar[MappingProxyType]`（**FrozenContext**）を用いる（v20 変更）。v18 までの `ContextVar[dict]` を `MappingProxyType` に変更し、immutability を保証する。マルチスレッドだけでなく、`asyncio` のタスク間でも完全に独立したコンテキストが保証される。コンテキストマネージャ内部で `Token` による状態の保持と巻き戻しを実装する。
* **No-Copy Performance（v20 新規）**: `MappingProxyType` は immutable であるため、async mode でのコンテキスト snapshot はコピー不要の **O(1) 参照渡し**で済む（※ `contextualize()` 入口での新 MappingProxyType 生成自体は O(n) であり、v18 と同程度のコストが発生する。O(1) になるのは async mode での **snapshot 取得と消費側の参照** のみ）。v18 までは queue hand-off ごとに `dict.copy()` による O(n) コピーが必要だったが、FrozenContext により hand-off コストを削減できる。なお、`contextualize()` による更新時は新しい `dict` + `MappingProxyType` を生成するため write path 自体は O(n) のままである。
* **設計判断: sync mode では Formatter での直接取得、async mode では producer snapshot 優先**: サードパーティ標準 Logger への透過性を保つため、sync mode では formatter が `contextvars` から直接取得する。一方、async mode では consumer thread 側の `contextvars` を信頼せず、producer thread 側で `LogRecord` へ付与した `FrozenContext` 参照を優先する。コピーではなく参照渡しのため、hand-off のコストは O(1) である。
* **thread 境界の意味論**: ユーザーが生成した新規 thread への初期 context 継承は Python 本体仕様に従う。D-SafeLogger 自身が生成する内部 thread は、常に空 `Context` で開始する。これにより内部 thread への context 漏洩を防ぐ。

### 9.6. コンソールカラー出力と stderr への明示的出力設計
* コンソール出力のデフォルト先を **`sys.stderr`** と明記する。
* **[実装方針]**: ANSI カラーコードは、略称化済みの表示用レベル値に対して付与する。色付与は `DSafeFormatter` と同じ局所マッピング / 表示用 proxy 経路で解決し、`record.levelname` を直接変更しない。Windows 向けには初期化時に `os.system("")` で VT100 を有効化する等のハックを盛り込む。カスタムレベルの登録時に指定されたカラーコードも自動的に反映される（§9.9 参照）。
* **カラーパレット設定**: ビルトイン5段階のカラーパレットは、INI ファイルまたは config_dict の `[global]` セクションで `color_{略称の小文字}` キーにより変更可能（§5.3 参照）。値は ANSI SGR パラメータの数値部分（例: `36`, `1;31`, `38;5;208`）を指定する。カスタムレベルのカラーも同一の命名規則で上書き可能。この設定は第2層（INI/辞書）のみで対応し、環境変数・引数からの設定は意図的に非対応とする。カラーパレットのマージ順序は: (1) ビルトインデフォルト → (2) `register_level()` 指定カラー → (3) INI/辞書の `color_{略称}` キー（最終上書き）。

### 9.7. LogRecord の非破壊取り扱い（Formatter / Handler 実装指針）

`logging.LogRecord` は**全ハンドラ間で同一インスタンスが共有される**。Formatter や Handler が `record.levelname`、`record.msg` 等の属性を直接書き換えると、後続のハンドラに破壊的な副作用が伝播する。

**[必須実装パターン]**: Sink 側の表示整形（レベル略称変換、ANSI 色付与など）は、**共有 `LogRecord` を変更せず、render 時だけ一部フィールドを上書きして見せる局所マッピングまたは表示用 proxy** で解決すること。重要なのは `copy.copy(record)` かどうかではなく、**共有 `LogRecord` を破壊しないこと**である。なお、Transport 境界で hand-off 用レコードを生成する処理（例: `DSafeQueueHandler.prepare()`）は別論点であり、この節の対象外とする。

```python
class DisplayRecordProxy:
    def __init__(self, original: logging.LogRecord, overrides: dict[str, object]):
        self.__dict__ = original.__dict__.copy()
        self.__dict__.update(overrides)


class DSafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        display_level = self.LEVEL_MAP.get(record.levelname, record.levelname)
        display_record = DisplayRecordProxy(record, {'levelname': display_level})
        # ... コンテキスト情報の付与等 ...
        return super().format(display_record)
```

同様に `ColorStreamHandler.emit()` でも、色付き表示用の `levelname` を持つ局所 proxy を生成して `emit()` し、ANSI カラーコードの埋め込みがファイルハンドラ等の他のハンドラへ影響しないことを保証すること。

### 9.8. レベル名略称マッピングの実装方針

D-SafeLogger のレベル名略称（`DEBUG` → `DBG`, `INFO` → `INF` 等）の変換は、**表示解決時にのみ実行する**。テキスト formatter と console color の両方で、同一の局所マッピング / 表示用 proxy 経路を用いる。`logging.addLevelName()` によるグローバルなレベル名上書きは**使用しない**。

**設計根拠**: `addLevelName()` は `logging` モジュールのプロセスグローバルな状態を変更するため、同一プロセス内の全てのロガー（サードパーティライブラリ含む）に影響を及ぼす。D-SafeLogger の略称変換は自身の Formatter の責務範囲内で完結すべきであり、グローバルな副作用を避けることで、テストの独立性とサードパーティライブラリとの共存性を保つ。

**[実装方針]**: `LEVEL_MAP` はクラス変数ではなく**インスタンス変数**として、Formatter の初期化時にビルトイン5段階とカスタムレベルの統合マップを構築する（§9.9 の `get_all_level_map()` を使用）。同様に `ColorStreamHandler` の `COLOR_MAP` もインスタンス変数として統合マップを保持する。`logging.Formatter` が許容する `%` / `{}` / `$` の各 style に対して、同一の表示意味論を保証する。

> ※ ただし、`register_level()` 内部では `logging.addLevelName(value, name)` を呼び出し、標準 `logging` モジュールにカスタムレベルの数値→名前マッピングを登録する。これは `logger.log(value, msg)` や `isEnabledFor(value)` など、標準APIの正常動作に必要な登録であり、略称変換（`INFO` → `INF`）とは異なる。

### 9.9. カスタムログレベル (Custom Log Levels) 仕様

`register_level()` 関数により、標準の5段階（DEBUG/INFO/WARNING/ERROR/CRITICAL）に加えて任意の数値位置にカスタムログレベルを差し込み可能とする。本機能はオプトイン（`register_level` を呼ばなければ一切の影響なし）であり、使用しない場合は v14.5 と完全に同一の動作を維持する。

#### 9.9.1. 設計原則
* D-SafeLogger の3文字略称フォーマット（`DBG`, `INF` 等）の一貫性を維持する
* ビルトイン5段階は不可侵とし、破壊的変更を生じさせない
* Zero Dependency を維持する（標準 `logging` の仕組みのみで実現）
* 3層設定管理パイプライン（環境変数 > INI > 引数）との完全な整合を保つ
* レベルの**定義**はPythonコードでのみ行い、レベルの**適用**（フィルタリング設定）は3層パイプラインで制御可能とする

> **設計判断: レベル定義をコードに限定する理由**
>
> INIファイルや環境変数でレベルを「定義」させると、略称・数値・カラーの全てを外部設定で表現する必要があり、パース・バリデーションの複雑度が爆発する。また、便利メソッド（`logger.trace()`）の動的生成はPythonランタイムでしか実行できない。
> 「レベルの定義はコード、レベルの適用は設定」という分離は、SLF4J/Logback 等の成熟したフレームワークと同じ設計判断である。

#### 9.9.2. 呼び出し順序の強制

```
register_level()    ← 任意回数（0回でもよい）
     ↓
ConfigureLogger()   ← 1回のみ
     ↓
GetLogger()         ← 任意回数
```

`ConfigureLogger()` 後の `register_level()` は `RuntimeError` を送出する。この制約により、Formatter / Handler / バリデーションが初期化後に不整合を起こすことを構造的に防止する。

`shutting_down` 状態もこの禁止に含める。終了処理中の追加登録は shared state を不安定化させるため、明示的に拒否する。

#### 9.9.3. ビルトインレベルの保護

以下の操作は全て `ValueError` として拒否する:
* ビルトイン値（10, 20, 30, 40, 50）の上書き
* ビルトイン名（DEBUG, INFO, WARNING, ERROR, CRITICAL）の上書き
* ビルトイン略称（DBG, INF, WAR, ERR, CRI）の上書き

#### 9.9.4. 3層設定管理パイプラインとの整合

`register_level()` で登録されたカスタムレベル名は、3層パイプラインの全ての層で使用可能になる:

* **第3層（引数）**: `ConfigureLogger(default_level='TRACE', ...)` — カスタムレベル名が使用可能
* **第2層（INI）**: `default_level = TRACE` または `[dsafelogger:mod]` の `level = TRACE` — 登録済みであれば有効
* **第1層（環境変数）**: `D_LOG_LEVEL=TRACE` または `D_LOG_MODULES=mymod:TRACE` — 登録済みであれば有効

コード上で `register_level('TRACE', ...)` を呼ばずに、INIファイルや環境変数で `TRACE` を指定した場合は、有効なレベル名の集合に含まれないため、既存の Fail-Fast バリデーションにより `ValueError` が送出される。

#### 9.9.5. 便利メソッドの動的生成

`register_level('TRACE', value=5, ...)` を呼ぶと、`ConfigureLogger` の初期化処理において `DSafeLogger` クラスに `logger.trace(msg, *args, **kwargs)` メソッドが動的に追加される。

* 便利メソッド名はレベル名の小文字（`TRACE` → `trace`、`NOTICE` → `notice`）
* `DSafeLogger` クラス（および親クラス `logging.Logger`）に既に存在するメソッド名と同名の場合、便利メソッドの追加はスキップされる（既存の `logger.info()` 等は上書きされない）。カスタムレベル自体は登録され、`logger.log(value, msg)` で使用可能
* 動的生成メソッドは `mypy` / `pyright` で型エラーになる。対策として `logger.log(VALUE, msg)` の使用（型安全）または `# type: ignore[attr-defined]` の付与をドキュメントに記載する

#### 9.9.6. コンポーネントへの反映

登録されたカスタムレベルは以下の全コンポーネントに自動的に反映される:

| コンポーネント | 反映内容 |
|--------------|---------|
| `DSafeFormatter` / `StructuredFormatter` | `LEVEL_MAP` にカスタムレベルの名前→略称マッピングを追加（インスタンス変数） |
| `DiagnosticFormatter` / `DiagnosticStructuredFormatter` | 親クラスの `LEVEL_MAP` に追随 |
| `ColorStreamHandler` | `COLOR_MAP` にカスタムレベルの略称→ANSIカラーマッピングを追加（インスタンス変数） |
| `EnvParser` | `{prefix}_LEVEL` / `{prefix}_MODULES` のレベルバリデーションがカスタムレベル名を動的に受け付ける |
| `IniLoader` | `default_level` およびモジュール別 `level` のバリデーションが同上 |
| `ConfigureLogger` | `default_level` 引数のバリデーションが同上。便利メソッドの動的インストール |

**[実装方針]**: カスタムレベルの登録情報は内部モジュール（`_levels.py`）で一元管理する。`get_all_level_map()`, `get_all_color_map()`, `get_valid_level_names()` 等のクエリ関数を通じて各コンポーネントに統合マップを提供する。

---

## 10. 公開 API 構造

本章では、single-process 版 (`dsafelogger`) と multiprocess 版 (`dsafelogger.mp`) の公開 API を定義する。  
v22c では **single-process 版の API 契約を維持**しつつ、multiprocess 版を別 namespace に分離する。これにより、

- single-process 版は従来通り「1回の Configure と通常の GetLogger」で完結する
- multiprocess 版は `ctx` と `AttachCurrentProcess()` を介した attach 契約を明示する
- 両者は `logging.setLoggerClass()` による Drop-in Replacement を共有する

という整理を取る。

### 10.1. `dsafelogger.ConfigureLogger` 引数定義（single-process 版）
```python
def ConfigureLogger(
    default_level: str = 'INFO',
    log_path: str = '.',            # 出力先ディレクトリ
    pg_name: str = 'Default',       # ファイル名プレフィックス
    env_prefix: str = 'D_LOG',      # 制御用環境変数のプレフィックス
    config_file: str | None = None, # INI設定ファイルパス
    config_dict: dict[str, dict[str, str]] | None = None,  # 辞書ベース設定（INI代替、config_fileと排他）
    is_async: bool = False,         # 非同期 I/O モード
    backup_count: int = 0,          # 世代管理の保持数
    archive_mode: bool = False,     # 削除の代わりにZIPアーカイブ化を行うか
    routing_mode: str = 'none',     # ルーティングモード (daily, size 等)
    interval: str | int = 10,       # min_interval / startup_interval 用
    max_bytes: int = 0,             # size 用閾値
    max_lines: int = 0,             # count 用閾値
    max_count: int | None = None,   # 循環上限 (Noneは上限到達エラーモード)
    suffix_digits: int = 3,         # 連番桁数
    console_out: bool = True,       # stderr への出力
    structured: bool = False,       # 構造化ログを出力する (fmt等と併用不可)
    fmt: str | logging.Formatter | None = None, # 形式(str) または Formatterインスタンス
    file_fmt: str | logging.Formatter | None = None,    # ファイル出力専用 Formatter
    console_fmt: str | logging.Formatter | None = None, # コンソール出力専用 Formatter
    datefmt: str | None = None,     # 日時形式
    enable_hash: bool = False,      # ルーティング時にSHA-256ハッシュを生成するか
    manifest_path: str | None = None, # マニフェストファイルの出力先パス
    sens_kws: Sequence[str] | None = None,  # 追加のセンシティブキーワード
    sens_kws_replace: bool = False, # True時、ビルトインキーワードをsens_kwsで完全置換
) -> None:
    """
    アプリケーションの起動時に1度だけ実行し、D-SafeLogger の single-process runtime を初期化する。

    本関数の契約・挙動・バリデーションは v22a と同一であり、multiprocess 版の導入によって変更しない。
    multiprocess が必要な場合は `dsafelogger.mp.ConfigureLogger()` を使用すること。
    """
```

**設計判断**:
- single-process 版の `ConfigureLogger()` に `worker_model` や `ctx` の概念は持ち込まない
- 既存利用者の呼び出しを壊さないことを優先する
- multiprocess 版は別 namespace へ分離し、`ConfigureLogger()` という関数名だけを共有する

**`env_prefix` パラメータの設計根拠**: 全ての制御用環境変数（`_LEVEL`, `_MODULES`, `_CONFIG`, `_CONSOLE`, `_COLOR`, `_DIAGNOSE`, `_HASH`, `_MANIFEST`）はこのプレフィックスに基づいて命名される。デフォルトは `'D_LOG'`（例: `D_LOG_LEVEL`, `D_LOG_MODULES` 等）。異なるプレフィックスを指定することで、同一マシン上で複数の D-SafeLogger インスタンスの環境変数名前空間を分離できる。`NO_COLOR` は業界標準のため、プレフィックスの影響を受けない。

### 10.2. `dsafelogger.GetLogger`
```python
def GetLogger(name: str = '') -> logging.Logger:
    """内部的には DSafeLogger (Logger互換) クラスを返す。引数なしでルートロガーを取得。"""
    pass
```

single-process 版では v22a までの auto-fire 契約を維持する。すなわち、未初期化状態で `GetLogger()` が呼ばれた場合、デフォルト引数による暗黙初期化を許容する。

### 10.3. `dsafelogger.register_level`

**spawn worker における再 import ルール**:
- `spawn` worker の bootstrap では、モジュールトップレベルの `register_level()` が再実行されることがある
- **同一定義**（`name` / `value` / `abbreviation` / `color` が完全一致）の再登録は **冪等 no-op** として許容する
- **不一致再登録** は registry divergence とみなし **`RuntimeError`** とする
- これにより、モジュールトップレベルに `register_level()` を書く通常の記述スタイルを `spawn` 環境でも維持できる

```python
def register_level(
    name: str,
    value: int,
    abbreviation: str,
    color: str = '',
) -> None:
    """
    D-SafeLogger にカスタムログレベルを登録する。
    ConfigureLogger() 前に呼び出さなければならない。
    """
```

本関数の契約は v22a から変更しない。multiprocess 版でも同一の registry を前提とし、`ctx` には frozen registry とその hash を含める。

### 10.4. `dsafelogger.ReopenLogFiles`
```python
def ReopenLogFiles() -> None:
    """
    外部 log rotation 後に writer-side の file sink 群を reopen する。
    single-process 版では同期的に file handle を reopen する。
    multiprocess 版では Writer への control message を送信し ACK を待つ。
    """
```

**single-process 契約**:
- `routing_mode='none'` でない file sink が active の場合は `ValueError`
- writer-side file sink が存在しない場合は `RuntimeError`
- シグネチャは `ReopenLogFiles() -> None` で固定する

### 10.5. `dsafelogger.mp.ConfigureLogger`（multiprocess 版）
```python
def ConfigureLogger(
    default_level: str = 'INFO',
    log_path: str = '.',
    pg_name: str = 'Default',
    env_prefix: str = 'D_LOG',
    config_file: str | None = None,
    config_dict: dict[str, dict[str, str]] | None = None,
    is_async: bool = False,
    backup_count: int = 0,
    archive_mode: bool = False,
    routing_mode: str = 'none',
    interval: str | int = 10,
    max_bytes: int = 0,
    max_lines: int = 0,
    max_count: int | None = None,
    suffix_digits: int = 3,
    console_out: bool = True,
    structured: bool = False,
    fmt: str | logging.Formatter | None = None,
    file_fmt: str | logging.Formatter | None = None,
    console_fmt: str | logging.Formatter | None = None,
    datefmt: str | None = None,
    enable_hash: bool = False,
    manifest_path: str | None = None,
    sens_kws: Sequence[str] | None = None,
    sens_kws_replace: bool = False,
    worker_model: Literal['process', 'pool', 'executor'] = 'process',
    mp_context: multiprocessing.context.BaseContext | str | None = None,
    ipc_log_timeout: float = 0.5,
    ipc_log_queue_maxsize: int | None = None,
    ipc_client_queue_maxsize: int | None = None,
    writer_flush_batch: int | None = None,
) -> object:
    """
    multiprocess 版の entry point。
    呼び出し元 process で Writer runtime を起動し、opaque かつ picklable な bootstrap object `ctx` を返す。
    `ctx` は worker process を同一 Writer に attach するためだけに用いる。
    """
```

**設計判断**:
- multiprocess 版では `worker_model`、`mp_context`、`ipc_log_timeout`、`ipc_log_queue_maxsize`、`ipc_client_queue_maxsize`、`writer_flush_batch` を multiprocess 専用の開発者選択 API として公開する
- `ipc_log_timeout` は **通常ログの log plane queue** にのみ適用する
- `ipc_log_queue_maxsize` / `ipc_client_queue_maxsize` は bootstrap-time only の queue 容量契約であり、child 側環境変数で変更しない
- `writer_flush_batch=1` は既定の per-message flush、`2` 以上は明示 opt-in の batch flush とする
- internal transport backend は `multiprocessing.Queue` 固定とし、公開 API に出さない
- `mp_context=None` は Python 既定の context 解決に委ねる
- `mp_context` が `str` または `BaseContext` として指定された場合、その正規化結果を **log/control queue と Pipe reply path の全 IPC primitive 生成に一貫適用**する
- 同一 process で 2 回目の `dsafelogger.mp.ConfigureLogger()` は `RuntimeError`
- 生成した `ctx` はその場で pickle round-trip 検証し、失敗時は Fail-Fast とする
- Writer bootstrap ready ACK では、少なくとも `protocol_version` と `registry_hash` を caller 側と照合し、不一致は `RuntimeError` による Fail-Fast とする
- multiprocess 版の `fmt` / `file_fmt` / `console_fmt` は single-process 版と同じ型面を許容するが、process 境界で freeze / 再構築を許可するのは **`logging.Formatter` 本体および D-SafeLogger 組み込み Formatter 本体** のインスタンスに限る
- 上記 allow-list 以外の custom formatter instance（custom subclass を含む）は `TypeError` とし、Writer 側では `kind + constructor args` からなる picklable spec だけを受け渡す

### 10.6. `dsafelogger.mp.AttachCurrentProcess`
```python
def AttachCurrentProcess(ctx: object) -> None:
    """
    現在 process を `ctx` が指す Writer runtime に attach する。
    attach 成功後、この process 内の `logging.getLogger()` / `GetLogger()` は Writer へ集約される。
    """
```

**契約**:
- same `ctx` への再 attach は no-op（ただし process-local thread / transport の再生成が必要な場合はそれだけ実施する）
- 別 `ctx` への再 attach は `RuntimeError`
- fork により attach 状態が継承されている場合でも、**child は親の client identity を再利用してはならない**。同一 Writer session であることを確認した上で、child 専用の process-local client identity を確立し、Writer active client registry へ登録してから logging を再開する
- attach 成功時には process-local に `logging.setLoggerClass()` を適用する
- attach 成功時には `protocol_version` / `registry_hash` mismatch を Fail-Fast で検知する

### 10.7. `dsafelogger.mp.GetLogger`
```python
def GetLogger(name: str = '') -> logging.Logger:
    """
    attach 済み process に対して DSafeLogger (Logger互換) を返す。
    """
```

**契約**:
- multiprocess 版では auto-fire しない
- 未 attach 状態で呼び出した場合は `RuntimeError`
- 例外メッセージは attach 忘れを検知しやすいものとする（例: `Process not attached to Writer`）

### 10.8. `dsafelogger.mp.GetWorkerInitializer`
```python
def GetWorkerInitializer(ctx: object) -> tuple[Callable[..., None], tuple]:
    """
    `multiprocessing.Pool` / `concurrent.futures.ProcessPoolExecutor` の
    `initializer` / `initargs` へそのまま渡せる `(init_fn, init_args)` を返す。
    """
```

**返却契約**:
- `init_fn` は process 起動時に `AttachCurrentProcess(ctx)` と等価の attach を行う callbale
- `init_args` には `ctx` を含む
- `ctx` が pickle 不可能な場合はここではなく `mp.ConfigureLogger()` の時点で Fail-Fast とする

### 10.8a. `dsafelogger.mp.DetachCurrentProcess`
```python
def DetachCurrentProcess() -> None:
    """
    現在 process を Writer runtime から detach し、process-local transport / handler / state を解放する。
    """
```

**契約**:
- attach 済み process から呼ばれた場合、Writer へ `DETACH` control request を送り、成功 ACK 後に process-local state を破棄する
- `ConfigureLogger()` を呼んだ main process も、shutdown 開始時にはまず自 process client を detach 対象として扱う
- すでに detach 済み、または未 attach の場合は no-op として扱ってよい
- detach 完了後、その process での `mp.GetLogger()` は再び `RuntimeError` になる

## 11. マルチプロセス対応（v22i 正式設計）

### 11.1. 目的と設計姿勢

v22i における multiprocess 正式設計の目的は、**複数 process から発生したログを 1 つの Writer runtime へ安全に集約し、single-process 版が既に持つ file pipeline（routing / hash / manifest / archive / purge / reopen）を意味論そのままで再利用すること**である。

本章は「使い方の説明」ではなく、**ライブラリとして期待される構造と振る舞いの定義**を担う。したがって、外部 API の列挙だけではなく、次を本文として定義する。

- Capture / Transport / Sink のどこに責務が属するか
- client process と Writer runtime の役割境界
- なぜ `ctx` / attach モデルが必要になるのか
- 通常ログ plane と control plane をどう分離するか
- shutdown / reopen / crash 時の意味論
- OS / start method ごとの成立条件
- single-process 版と multiprocess 版がどこで連続し、どこで分岐するか

### 11.2. スコープ内 / スコープ外

**スコープ内**:
- 同一ホスト内 multiprocess logging
- 1 つの Writer runtime と複数 client process の構成
- `dsafelogger.mp` namespace による明示的 entry point 分離
- `worker_model` に応じた attach 契約
- internal transport としての `multiprocessing.Queue`
- 通常ログ用 log plane と制御コマンド用 control plane の分離
- single-process 版の routing / hash / manifest / archive / purge / reopen の継承
- `logging.setLoggerClass()` による Drop-in Replacement の multiprocess 版への継承

**スコープ外**:
- remote aggregation / network protocol
- 複数 Writer の分散構成
- 子 process が独自 file sink を直接所有するモード
- transport backend の公開切り替え
- security / auth / encrypted control plane
- 他ホストとの IPC

### 11.3. アーキテクチャ原則

multiprocess 版でも、v20 で確立した **Capture / Transport / Sink** の3層分離は維持する。ただし、single-process 版と multiprocess 版では Transport 層の境界が異なる。

#### 11.3.1. single-process 版
- Capture: `DSafeLogger`, `logging.setLoggerClass()`, `contextualize()`, `diagnose` snapshot
- Transport: `DirectTransport` / `QueueTransport`
- Sink: `FileSink` / `ConsoleSink`, routing, hash, manifest, reopen

#### 11.3.2. multiprocess 版
- **client 側 Capture**: `DSafeLogger`, `logging.setLoggerClass()`, `contextualize()`, `diagnose` snapshot, route 解決
- **client 側 Transport**: process-local async queue（必要時） + log plane `multiprocessing.Queue` への hand-off
- **Writer 側 Sink / Runtime**: routing, file open/close, hash, manifest, archive, purge, reopen, shutdown, control plane

> **設計原則**: multiprocess 版でも **`logging` 互換は Capture 層の責務** であり、Writer 側で `LogRecord` の Capture 意味論（logger 階層評価、`propagate` 判定、level 判定、`f_locals` 収集）を再実行してはならない。Writer 側は `LogEvent` を受け取り、route に従って sink 群へ dispatch するだけである。

### 11.4. なぜ `dsafelogger.mp` へ分離するのか

single-process 版は「1回の Configure と通常の GetLogger で完結する」という単純さを価値として持つ。multiprocess 版は、Writer runtime の起動、attach、process 間 protocol、shutdown 同期という **アプリケーションの process 起動モデルと接続する責務** を持つため、同じ namespace に混在させると意味論が濁る。

そのため v22i では、

- `dsafelogger` = single-process 版
- `dsafelogger.mp` = multiprocess 版

に入口を分離する。これにより、

- single-process 版では auto-fire を維持できる
- multiprocess 版では attach 忘れを Fail-Fast にできる
- `worker_model` / `ctx` / `AttachCurrentProcess()` / `DetachCurrentProcess()` を multiprocess 専用契約として扱える

という利点が得られる。

### 11.5. client / Writer モデル

v22h の multiprocess 設計では、OS 的な親子関係よりも **ロジック上の役割** を重視し、用語を次のように整理する。

| 用語 | 意味 |
|------|------|
| **client process** | ログ呼び出しを行う process。main process も worker process も含む |
| **Writer runtime** | file sink 群を所有し、client からのログを最終的に書き出す内部 process |
| **ctx** | client process が Writer runtime に参加するための opaque かつ picklable な bootstrap object |
| **log plane** | 通常ログ `LogEvent` を client → Writer へ運ぶ片方向経路 |
| **control plane** | reopen / detach / stop / status 等の制御メッセージをやり取りする経路 |

**重要**: Writer runtime はロガー内部の実装要素であり、開発者が明示的に `multiprocessing.Process` / `subprocess.Popen` 等を使って直接起動する対象ではない。開発者が知るべき契約は `ctx`、`AttachCurrentProcess()`、`DetachCurrentProcess()` に限定する。

### 11.6. multiprocess 全体像

```text
main process
  ├─ dsafelogger.mp.ConfigureLogger(...)
  │    ├─ config 3層解決
  │    ├─ Writer runtime 起動
  │    ├─ log plane queue 準備
  │    ├─ control plane request queue 準備
  │    ├─ 呼び出し元 process 用 reply endpoint 準備
  │    └─ ctx 生成 + pickle 検証
  │
  ├─ 自プロセス自身を attach 済みにする
  └─ worker process へ ctx を渡す

worker process
  ├─ AttachCurrentProcess(ctx)
  │    ├─ ctx 検証
  │    ├─ process-local reply endpoint 準備
  │    ├─ ATTACH control request を送信
  │    ├─ child 専用 client identity を active registry へ登録
  │    ├─ process-local attach 状態更新
  │    ├─ logging.setLoggerClass() 適用
  │    └─ Capture → Writer hand-off を有効化
  └─ GetLogger(__name__) で通常利用

Writer runtime
  ├─ active client registry を保持
  ├─ log plane から LogEvent を受信
  ├─ route に応じて sink group を選択
  ├─ control plane から ATTACH / DETACH / REOPEN / STOP を受信
  ├─ file switch / routing / hash / manifest / purge / archive
  ├─ reopen / shutdown の直列化
  └─ active client 数と stop 要求に基づいて安全終了
```

### 11.7. `ctx` は単なる Queue ではなく bootstrap object である

`ctx` は公開 API 上は opaque な object とし、開発者には queue や pipe の実体を見せない。理由は次の通り。

1. internal transport backend を将来差し替える余地を残すため
2. 開発者にとって本質なのは queue の種類ではなく **「現在 process をどう attach するか」** だから
3. `GetLogger()` に queue を渡す設計にすると `logging.getLogger()` を使うサードパーティログを取り込めないから

`ctx` に期待される情報は、基本設計レベルでは次のカテゴリを必須とする。

- protocol version
- Writer session identity
- log plane endpoint 参照
- control plane request endpoint 参照
- bootstrap ready / attach 時の `protocol_version` 照合情報
- default queue policy（maxsize / put timeout / overflow policy digest）
- resolved config digest
- custom level registry hash
- attach に必要な runtime metadata

ただし、具体フィールド名・内部表現・pickle 実装詳細は詳細設計書で定義する。基本設計で確定するのは、

- `ctx` は **opaque**
- `ctx` は **picklable**
- `ctx` は **Writer runtime の lifetime に束縛される**
- `ctx` は `ConfigureLogger()` 生成時に **pickle round-trip 検証**される
- `ctx` には **非 picklable な同期プリミティブ（`Event`, `Lock`, `Condition` 等）を含めてはならない**

の5点である。

#### registry hash 照合タイミング
- Writer bootstrap ready ACK 時: client が送った registry hash と Writer 側初期 registry を照合する
- `AttachCurrentProcess(ctx)` 実行時: 現在 process の registry と `ctx` 内 hash を照合する
- いずれの不一致も **`RuntimeError` による Fail-Fast** とする
- hash アルゴリズムは **SHA-256** とする

#### bootstrap payload 構築原則
- `ctx` に含める設定情報は **生の dict / プリミティブ値のみ** とする
- `Strategy` / `Formatter` の**生インスタンスは含めない**
- Formatter は `kind + constructor args` からなる picklable spec へ正規化する
- Writer 側で受信した raw config dict / formatter spec から `Strategy` / `Formatter` を再構築する
- これにより、Formatter カスタムサブクラスや closure に起因する pickle 不能問題を構造的に回避する
- `ResolvedConfig` も **pickle 可能な中間表現**として定義し、`Strategy` インスタンスを保持しない形へ再定義する

### 11.8. process 間 payload の基本スキーマ

v22h では、詳細設計へ進む前提として、process 境界を越える payload のカテゴリを基本設計レベルで固定する。

**共通制約**:
- process 境界を越える payload は **すべて picklable** でなければならない
- `ctx` / `LogEvent` / `ControlRequest` / `ControlAck` に **非 picklable な同期プリミティブ** を含めてはならない
- ACK は log plane ではなく **control plane の戻り経路**で返す

#### 11.8.1. `ctx` bootstrap object
前節の通り、opaque だが、以下の情報カテゴリを持つ。
- session 識別子
- picklable な endpoint / routing 情報
- protocol version
- resolved config digest
- registry hash
- runtime metadata

#### 11.8.2. `LogEvent`
通常ログ plane で client → Writer に送られる hand-off payload。少なくとも次の情報カテゴリを持つ。
- route identity（`_ds_route`）
- level / logger name / message
- file / line / function 等の source location
- process / thread metadata
- `_ds_context`
- `_ds_extra`
- `_ds_diag_frames`
- exception payload

**規約**: `_ds_context` と `_ds_extra` は常に key として存在し、空は `{}` で表現する。

> **補足**: この常在規約は v21 で確立した hasattr ベースの context snapshot fallback を IPC 境界で維持するために必要な規約である。pickle 経由で `LogEvent` を受け取った Writer 側では hasattr による区別が成立しないため、key 存在で「Capture 側で snapshot 取得済み」であることを明示し、Writer 側で live context 参照が発生しないことを保証する。

#### 11.8.3. `ControlRequest`
control plane で client → Writer に送る request payload。少なくとも次の情報カテゴリを持つ。
- request id
- client id
- command type（attach / detach / reopen / stop / status）
- command-specific payload
- picklable な reply endpoint

**v22i 固定**:
- reply endpoint は per-request の `multiprocessing.Pipe(duplex=False)` による reply path とする
- Queue を別 Queue の payload として送る Queue-in-Queue 方式は Python の `multiprocessing` 制約上成立しないため採用しない
- Pipe reply endpoint は request/ack 完了後に client / Writer の双方で close されることを前提とする

#### 11.8.4. `ControlAck`
control plane で Writer → 呼び出し元 client に返す ACK payload。少なくとも次の情報カテゴリを持つ。
- request id
- success flag
- error category
- error message
- command-specific result payload
- reply path 上で解釈可能な result metadata

### 11.9. log plane と control plane の分離

v22i では、通常ログ plane と control plane を明確に分離する。

#### 11.9.1. log plane
- client → Writer の片方向
- payload は `LogEvent`
- internal transport は **bounded `multiprocessing.Queue`**
- ファイル書き込み経路の主経路

#### 11.9.2. control plane
- reopen / attach / detach / stop / status を扱う
- request / ACK を持つ
- `ReopenLogFiles()` は **control plane を使う同期 API** である
- control plane は通常ログ plane と独立した queue / endpoint 群で構成する
- ACK は **control plane の Pipe reply path** を通って返される
- control plane は command 種別ごとに異なる QoS を持つ

> command 種別ごとの QoS 定義は **§11.16.3** を参照。

**設計原則**:
- control command を通常ログ queue に混在させない
- ACK を log plane に混在させない
- 非 picklable な同期オブジェクトを control payload に含めない
- Queue を別 Queue の payload として送らない
- Pipe send/recv failure は raw `BrokenPipeError` / `EOFError` のまま外へ漏らさず、control plane failure として `RuntimeError` 系へ正規化する

理由は、ACK timeout・request 直列化・QoS・エラー伝達が通常ログとは異なる意味論を持つためである。

### 11.10. attach モデルが必要になる理由

single-process 版では `GetLogger()` だけでロガー取得が完結する。しかし multiprocess 版では、worker process が Writer runtime の存在を知らなければログを集約できない。特に `spawn` では、親 process のメモリ状態は自動継承されない。

そのため v22h では、

- Writer runtime の起動 = `dsafelogger.mp.ConfigureLogger()`
- 現在 process の参加 = `AttachCurrentProcess(ctx)`
- ロガー取得 = `GetLogger()`

の 3 段に明示分離する。

この分離により、

- `GetLogger()` は Drop-in Replacement の意味論を維持できる
- attach 忘れを Fail-Fast に検知できる
- worker model ごとの差は `ctx` の渡し方に局所化できる

### 11.11. `worker_model` はなぜ公開 API に出るのか

internal transport backend はロガー内部の自由度として隠蔽できる。一方、`worker_model` は開発者が **どの API で worker process を生成するか** に直接現れるため、隠蔽できない。

したがって、v22h では開発者が選ぶものを

- `worker_model`
- `mp_context`

の 2 つに限定する。

#### 11.11.1. `worker_model='process'`
- `ctx` を worker target の引数として渡す
- worker 冒頭で `AttachCurrentProcess(ctx)` を呼ぶ
- デフォルト値とする

#### 11.11.2. `worker_model='pool'`
- `GetWorkerInitializer(ctx)` の返り値を `initializer / initargs` に渡す
- worker 本体は `GetLogger()` だけでよい

#### 11.11.3. `worker_model='executor'`
- ここでいう executor は **`concurrent.futures.ProcessPoolExecutor` のみ**を指す
- `ProcessPoolExecutor(initializer=..., initargs=...)` に `GetWorkerInitializer(ctx)` を渡す
- `Future` ベース運用向け
- `ThreadPoolExecutor` は **対象外** とする（スレッド並列は single-process 版の責務）

#### 11.11.4. default を `process` とする理由
- 最小の前提で attach 契約を説明できる
- テスト設計の基準ケースを作りやすい
- `ctx` の受け渡しと attach の順序が最も明示的

### 11.12. `mp_context` と start method

`mp_context` は **Writer runtime と worker process 群が共有すべき `multiprocessing` context** を表す。型としては、

- `None`
- `'spawn'`, `'fork'`, `'forkserver'`
- `multiprocessing.context.BaseContext`

を受け付ける。

**既定解決**:
- `mp_context=None` の場合、**Python 既定の context に委ねる**
- ライブラリが OS 判定により独自フォールバックを行わない

**理由**:
- アプリケーション全体の multiprocessing 方針と衝突しない
- ライブラリが勝手に `spawn` / `fork` を強制しない
- Zero Dependency と API 単純性を維持する

> **注意**: Python 既定の multiprocessing context は OS および Python バージョン依存である。`mp_context=None` のまま移植した場合、start method の差により attach 挙動や初期化要件が変化しうる。移植性が問題となる場合は `mp_context` を明示的に指定すること。examples は OS 別に提供する。

### 11.13. `AttachCurrentProcess()` の意味論

`AttachCurrentProcess(ctx)` は、現在 process を既存 Writer runtime に参加させる process-local 操作である。

#### 11.13.1. 具体責務
- `ctx` の検証
- process-local reply endpoint の生成
- ATTACH request の送信
- process-local attach 状態の更新
- `logging.setLoggerClass()` の process-local 適用
- Capture → Writer hand-off の有効化
- 必要な process-local handler / transport の attach

#### 11.13.2. 冪等性
- same `ctx` への再 attach は no-op（必要なら process-local thread / transport の再生成のみ実施）
- same Writer session への attach 継承（fork）では、親の client identity を流用しない。child は同一 session を確認した上で child 専用 `client_id` を Writer active registry へ登録し、必要な process-local thread / transport の再生成も実施する
- 別 `ctx` への再 attach は `RuntimeError`

#### 11.13.3. `fork` 継承との関係
POSIX `fork` では親 process の attach 状態が継承されうる。v22i ではこれを **正常ケース** として扱う。ただし `fork` は main thread しか複製しないため、`is_async=True` で使う process-local pump thread 等は子 process 側で再生成が必要である。したがって、fork 後に `AttachCurrentProcess(ctx)` を呼んだ場合は、同一 Writer session を確認した上で child 専用 `client_id` による再登録と、必要な process-local thread / transport の再生成を行って成功させる。

ただし、`ConfigureLogger()` / `AttachCurrentProcess()` 実行中に fork してはならない。
**要件**: `fork` を使う場合は、親側で logger 初期化および attach 完了後に child を fork すること。

**境界条件**: 上記の fork 継承 child 再登録は、元の Writer session が存続している間に限って成立する。親/Writer 側が `STOP` 受理済み・drain 中・終了済みの場合、子 process は同一 session を自動 resurrect してはならない。この場合の後続 `emit()` は通常の Writer unavailable 経路（drop + stderr warning）で扱い、継続運用は保証しない。

### 11.14. Drop-in Replacement の multiprocess 版における成立条件

D-SafeLogger の中核価値は `logging.setLoggerClass()` による標準 `logging` 互換である。multiprocess 版でもこの価値は維持するが、**各 process ごとに `logging.setLoggerClass()` が有効化されている必要がある。**

そのため、

- `dsafelogger.mp.ConfigureLogger()` は呼び出し元 process に対して `logging.setLoggerClass()` を適用する
- `AttachCurrentProcess(ctx)` も、attach 対象 process に対して process-local に再適用する

という設計を取る。

これにより、attach 完了後の worker process では、

- `GetLogger()`
- `logging.getLogger()`
- サードパーティライブラリが内部で呼ぶ `logging.getLogger()`

のいずれも Writer へ集約される。

> **保証**: worker process で `AttachCurrentProcess(ctx)` が成功した後、その process で発生する標準 `logging` ベースのログは、single-process 版と同じ Capture 意味論を経て Writer に集約される。

> **補足**: ここで言う「process-local 適用」とは、各 process 内で `logging` モジュールのグローバル状態（`_loggerClass`）を更新することを指す。各 process は独立した `logging` モジュール状態を持つため、片方の process での `setLoggerClass()` が他方へ直接影響することはない。`fork` では親の `logging` 状態が子へ継承されるが、process-local thread は継承されないため、fork 後の `AttachCurrentProcess(ctx)` は control plane の再 ATTACH を行わず、必要な process-local thread / transport の再生成だけを行って成功しうる。一方 `spawn` では子が新規 import するため `logging` 状態は初期値に戻り、`AttachCurrentProcess(ctx)` 実行時の再適用が Drop-in Replacement 成立条件となる。

### 11.15. internal transport を `multiprocessing.Queue` 固定とする理由

v22i では internal transport backend を公開 API に出さず、**bounded `multiprocessing.Queue` 固定**とする。

#### 理由
1. 複数 client process → 1 Writer runtime の fan-in に素直に適合する
2. `maxsize` により backpressure 方針を定義できる
3. `worker_model` の差とは独立に統一した hand-off 契約を持てる
4. 開発者が知るべき契約を `ctx` / attach に集中できる

### 11.16. queue capacity・`ipc_log_timeout`・backpressure 方針

運用上確実なニーズとして、キュー満杯時の振る舞いを v22h で明文化する。

#### 11.16.1. log plane queue
- internal log queue は **bounded** とする
- 既定 `maxsize` は **10000** とする（v23g で実装と整合。v22i〜v23b 実装値は 1000 であったが v23g にて仕様値 10000 に揃えた）
- v23h: log plane queue の実装は `multiprocessing.queues.Queue` 派生の **`TrackedQueue`** を用いる。コンストラクタで `super().qsize()` を **例外プローブ**して `NotImplementedError` を捕捉した場合のみ `multiprocessing.Value` カウンタへ自動 fallback する。OS 名（macOS など）には依存しない判別であるため、未来の or マイナーな未対応プラットフォームでも追加対応なしに正しく動作する
- `put()` は **無限 block しない**
- multiprocess 版 `ConfigureLogger()` は **`ipc_log_queue_maxsize`** を公開引数として受け取る（v23c 追加）
- 既定 `ipc_log_queue_maxsize` は **10000**（上記既定 maxsize と同値）
- 環境変数 `{prefix}_IPC_LOG_QUEUE_MAXSIZE` が指定されている場合は、`ipc_log_queue_maxsize` 引数より優先する
- `ipc_log_queue_maxsize <= 0` 指定は **`ValueError`**、`> 100000` で **stderr warning**
- v23h: 環境変数 `{prefix}_IPC_LOG_QUEUE_MAXSIZE` の値が int に解釈できない場合は **`ValueError`**（warning + ignore からの fail-fast 化）
- multiprocess 版 `ConfigureLogger()` は **`ipc_client_queue_maxsize`** を公開引数として受け取る（v23c 追加）
- `ipc_client_queue_maxsize` は process-local async queue（`is_async=True` 時の中間 buffer）の上限
- 既定 `ipc_client_queue_maxsize` は **`ipc_log_queue_maxsize` と同値**（未指定時）
- 環境変数 `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` が指定されている場合は、`ipc_client_queue_maxsize` 引数より優先する
- `ipc_client_queue_maxsize <= 0` 指定は **`ValueError`**
- v23h: 環境変数 `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` の値が int に解釈できない場合は **`ValueError`**
- multiprocess 版 `ConfigureLogger()` は **`ipc_log_timeout`** を公開引数として受け取る
- `ipc_log_timeout` は **通常ログ (`LOG`) の log plane queue** にのみ適用する
- 既定 `ipc_log_timeout` は **0.5 秒** とする
- 環境変数 `{prefix}_IPC_LOG_TIMEOUT` が指定されている場合は、`ipc_log_timeout` 引数より優先する
- `ipc_log_timeout <= 0`、または `None` 相当の指定は **`ValueError`**
- v23h: 環境変数 `{prefix}_IPC_LOG_TIMEOUT` の値が float に解釈できない場合は **`ValueError`**
- フレームワークの絶対防衛線として **`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0`** を持つ
- 実効値が `MAX_IPC_LOG_TIMEOUT_SECONDS` を超える場合は、stderr warning を出した上で **3.0 秒へクリップ**して初期化を継続する

> 設計判断: `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` は、通常ログの producer path を過度に長時間 block させないための絶対上限である。3.0 秒は queue 一時飽和からの自然回復を待つには十分に長く、一方で GUI thread や request handler thread を不可逆に固めるほど長くはない上限として採用する。

#### 11.16.2. overflow 時のポリシー
- `ipc_log_timeout` 超過、または `queue.Full` 時は **record を drop** する
- drop 時は **client 側 drop counter** を増分する
- 最初の drop 発生時、およびその後の要約タイミングで **stderr warning** を出す
- silent drop は行わない
- `ipc_log_timeout` は control plane command には適用しない

#### 11.16.3. control plane queue
- control queue も bounded とする
- reopen / stop / attach / detach / status の request は通常ログより優先度が高く、control plane で独立に処理する
- `ipc_log_timeout` は control plane queue の送信・ACK 待機には適用しない
- command 種別ごとの QoS を次のように固定する  
  - `ATTACH` / `DETACH` / `STOP`: **drop 不可**  
  - `REOPEN` / `STATUS`: **ACK 必須**  
  - `LOG` の overflow 方針は control plane command へ適用しない
- `ATTACH` / `DETACH` / `STOP` は、queue 飽和を理由に silent drop してはならない
- request 送信失敗は **RuntimeError** ではなく control plane failure として扱い、呼び出し元 API は対応する例外（`RuntimeError` / `TimeoutError` 等）に変換する

### 11.17. `is_async=True` との交絡仕様

multiprocess 版でも `is_async=True` は有効である。ただし意味は single-process 版と異なる。

- `is_async=False`:
  - Capture 後、現在 process から直接 log plane queue へ hand-off する
- `is_async=True`:
  - Capture 後、まず process-local async queue に積み、専用 worker が log plane queue へ hand-off する

したがって、multiprocess 版で `is_async=True` を使うと、

- process-local async queue
- multiprocess log queue
- Writer dispatch

の **二重キューイング** になる。

**設計上の意味**:
- multiprocess 版では既に process 境界 hand-off があるため、通常は `is_async=False` で十分
- `is_async=True` は、**log plane queue への `put()` 自体もメインスレッドから切り離したい場合**に限って使う

### 11.18. `GetLogger()` と auto-fire

multiprocess 版では、single-process 版の auto-fire を継承しない。

- multiprocess 版では auto-fire しない
- 現在 process が Writer に attach されていない状態で `GetLogger()` を呼んだ場合は **`RuntimeError`**
- 例外メッセージは attach 忘れを早期検知できる内容とする

**例外**: fork 継承により attach 状態が継承されている場合は正常動作する。

### 11.19. `GetWorkerInitializer(ctx)` の位置づけ

`GetWorkerInitializer(ctx)` は、`Pool` / `ProcessPoolExecutor` で attach 手順を誤りにくくするための補助 API である。

```python
ctx = dsafelogger.mp.ConfigureLogger(...)
init_fn, init_args = dsafelogger.mp.GetWorkerInitializer(ctx)
```

- 返り値の型は **`tuple[Callable[..., None], tuple]`** とする
- `init_fn` は process 起動時に `AttachCurrentProcess(ctx)` と等価の attach を行う callable
- `init_args` には `ctx` を含む
- `ctx` が pickle 不可能な場合は `GetWorkerInitializer()` ではなく `ConfigureLogger()` の時点で Fail-Fast とする

この関数は「別の attach 方式」を提供するのではなく、**`AttachCurrentProcess(ctx)` を各 executor API に自然に載せるための補助**である。

### 11.20. `ReopenLogFiles()` は control plane である

multiprocess 版における `ReopenLogFiles()` は、single-process 版のように現在 process の file handle を直接触る操作ではない。`ReopenLogFiles()` を呼んだ attached client process は、Writer runtime に **control request** を送り、対応する **ACK** を待つ。

#### 11.20.1. 基本契約
- **どの attached client process からでも呼び出し可能**
- reopen の直列化責務は **Writer 側**
- シグネチャは **`ReopenLogFiles() -> None`**

#### 11.20.2. 例外契約
- single / multiprocess 共通で、writer-side の file sink のいずれかが `routing_mode != 'none'` の場合は **`ValueError`**
- multiprocess 版で Writer runtime 不在 / attach 不正時は **`RuntimeError`**
- multiprocess 版で ACK timeout は **`TimeoutError`**

#### 11.20.3. ACK timeout
- multiprocess 版の ACK wait は内部定数 **`CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0`** を使う
- 公開 API シグネチャに timeout 引数は追加しない

> 設計判断: 5.0 秒の根拠は logrotate / cron 運用での postrotate スクリプト実行時間の典型値（数秒以内）と、Writer 側での reopen 処理時間（通常数十 ms）の余裕を加味した値である。
> 詳細設計書改訂時または運用実測を踏まえて再検討する余地を残す。

#### 11.20.4. ACK の意味
- ACK は reopen request の受理と処理結果を表す
- ACK は **control plane の Pipe reply path** で返され、通常ログ queue を経由しない
- reopen が失敗した場合は、Writer は error 情報付き ACK を返し、client 側は対応例外へ変換する
- ACK payload には、少なくとも request id / success flag / error category / error message が含まれる
- request/ack 完了後の Pipe endpoint close は control plane 実装責務とし、BrokenPipe/EOF は `RuntimeError` 系へ正規化する

### 11.21. shutdown 同期と active client 管理

複数 worker からの安全終了を成立させるため、Writer は **active client registry** を保持する。

#### 11.21.1. attach / detach
- `AttachCurrentProcess(ctx)` 成功時に Writer は client を active registry に登録する
- `AttachCurrentProcess(ctx)` が fork 継承 child で呼ばれた場合も、child 専用の `client_id` を active registry に登録する
- client 終了時には detach / close control request を送信する
- Writer は detach 受理後に active client 数を減算する
- `ConfigureLogger()` 呼び出し元 process も active registry 上の 1 client として数える

#### 11.21.2. stop 判定
Writer は次の両条件を満たしたとき shutdown へ進む。
1. main 側から stop request を受けたこと
2. active client 数が 0 であること

main process の shutdown helper は、Writer thread の join 待機に入る前に **自 process client の detach を完了**させなければならない。active client registry に main process 自身が残ったままの join 待機は設計違反とする。

#### worker crash 時の registry 整合
- worker process が `DETACH` を送らずに終了した場合、Writer の active client registry に残存が生じうる
- shutdown 中の active client 数 0 待ちには **内部 timeout** を設ける
- timeout 到達時は **stderr warning** を出し、強制 stop へ移行する
- **silent hang を起こしてはならない**
- 定期的な liveness probe による能動的残存検知は将来拡張とし、基本設計の必須要件とはしない

**重要**: shutdown 判定は sentinel 個数ではなく **active client registry** に基づいて行う。`STOP` は shutdown トリガーであり、drop 対象にしてはならない。

#### 11.21.3. shutdown ordering
1. client 側 async queue を drain
2. client から Writer への送信を完了
3. client が detach / close を送信
4. Writer 側が log plane queue を drain
5. Writer 側が sink handlers を close / hash / manifest finalize
6. Writer runtime が終了

### 11.22. Writer crash・drop counter・exit code

#### 11.22.1. client 側 drop counter
次のような事象で client 側 counter を増分する。
- log queue `put()` timeout / `queue.Full`
- attach 不在での送信失敗
- control plane 送信失敗に伴う command failure

#### 11.22.2. Writer 側 drop / reject counter
次のような事象で Writer 側 counter を増分する。
- protocol failure
- route failure（unknown route は reject counter 増分 + stderr warning。root への暗黙フォールバックは禁止）
- sink failure に伴う discard

#### 11.22.3. 出力先とタイミング
- 少なくとも **stderr warning** により可視化する
- shutdown 時には summary を出す
- public getter API は v22h 基本設計の必須要件とはしない

#### 11.22.4. Writer exit code
- 正常終了は **exit code 0**
- 異常終了は **非 0**
- 親 / 呼び出し元 process は、Writer exit code が非 0 の場合 stderr warning を出す

#### 11.22.5. Writer 死亡検知
- client 側は **log plane 送信失敗**, **control plane ACK timeout**, または **Writer 終了状態の観測** により Writer 死亡を検知する
- 送信失敗の具体例として `BrokenPipeError` / `EOFError` / queue 利用不能状態を含む
- 死亡検知後は再帰ロギングせず、以降の send は **drop + stderr warning** とする
- client 側 drop counter を増分する
- 定期的な liveness probe（healthcheck ping）は基本設計の必須要件としない
- 具体的な検知実装は詳細設計書で確定する

### 11.23. `ctx` lifetime と再利用制約

- `ctx` は **Writer runtime の lifetime に束縛される**
- Writer 終了後の `ctx` は invalid であり、attach は失敗する
- `ReopenLogFiles()` により `ctx` が invalidate されることはない
- 同一 process で 2 回目の `dsafelogger.mp.ConfigureLogger()` は **`RuntimeError`**

### 11.24. single-process 版との連続性

multiprocess 版は別入口であっても、single-process 版のコア価値を破壊してはならない。

継承すべきもの:
- 3 層設定管理パイプライン
- `register_level()`
- append-only routing
- structured JSONL
- diagnose / contextualize
- hash / manifest / archive / purge
- `ReopenLogFiles()` の single-process 契約
- Drop-in Replacement

multiprocess 版で追加されるのは、これらを **複数 process で安全に成立させるための attach / Writer runtime / control plane** に限る。

### 11.25. 期待されるモジュール構造

```text
dsafelogger/
  __init__.py                # single-process public API
  mp/__init__.py             # multiprocess public API
  _async.py                 # QueueHandler/QueueListener based async transport pieces
  _transport.py             # single-process transport
  _handler.py               # AppendOnlyFileHandler / required file sink
  _routing.py
  _formatter.py             # client-side console / shared pieces
  _writer_formatter.py      # Writer-side file formatting
  _integrity.py             # hash worker / manifest integrity support
  _purge.py                 # purge / archive workers
  _pipeline.py              # single-process pipeline
  _mp_queue.py              # TrackedQueue for qsize-visible log plane
  _mp_runtime.py            # Writer runtime / active client registry / shutdown
  _mp_attach.py             # AttachCurrentProcess / GetWorkerInitializer
  _mp_protocol.py           # ctx / LogEvent / ControlRequest / ControlAck contract
  _mp_control.py            # control plane helpers / request serialization
```

v23j では上記を物理ファイル構造の正とする。過去の設計メモに出てくる `_capture.py`, `_hash.py`, `_manifest.py` は概念分割名であり、現行実装では `_integrity.py` / `_handler.py` / `_transport.py` / `_pipeline.py` へ統合されている。

### 11.26. 設計の要点

v22h multiprocess 正式設計の要点は次の通りである。

- `dsafelogger.mp` に入口分離する
- internal transport は bounded `multiprocessing.Queue` 固定
- 通常ログ plane と control plane を分離する
- 開発者に選ばせるのは `worker_model` と `mp_context` のみ
- `ctx` は opaque かつ picklable な bootstrap object
- `AttachCurrentProcess(ctx)` が multiprocess 成立の鍵である
- Drop-in Replacement は process-local な `logging.setLoggerClass()` 再適用で維持する
- `ReopenLogFiles()` は control plane を使う同期 API である
- active client registry と detach / stop 同期で安全終了を成立させる
- overflow / drop / crash は silent failure にしない

### 11.27. Writer flush 戦略（v23g）

multiprocess 版 Writer の per-message flush は既定動作として維持する（§12.2「flush 契約の弱体化」厳守）。高スループット用途のため、`ConfigureLogger(writer_flush_batch=N)` で batch flush に opt-in できる。

| `writer_flush_batch` | 動作 | 想定用途 |
|---|---|---|
| `1`（既定） | per-message flush。Writer process crash 時の loss なし（Python buffer に残らない） | 高 durability 要求 |
| `2 – 64` | N 件ごと flush + queue empty 時 idle flush。process crash 時最大 N-1 件 loss 可能性 | スループット優先 |
| `> 64` | 同上、ただし可視性低下リスク高 | 特殊用途 |

環境変数 `{prefix}_WRITER_FLUSH_BATCH` で上書き可能。`<= 0` で `ValueError`、`> 1024` で warning。v23h: 環境変数の値が int に解釈できない場合も `ValueError`（warning + ignore からの fail-fast 化）。`WriterRuntime.__init__` でも `ctx.writer_flush_batch < 1` を `ValueError` として弾き、`BootstrapContext` 直接構築経路の安全網とする。

#### §12.3 用語との対応

- `writer_flush_batch=1` の場合: dispatch 完了 = `delivered_per_sink` と一致する
- `writer_flush_batch>1` の場合: batch flush 完了点を `delivered_per_sink` の到達点とする。ユーザーが opt-in した時点で per-message visibility は保証されない

#### Writer による Sink flush 制御の責務分担

multiprocess 経路では、Sink（`AppendOnlyFileHandler`）の `stream_flush_on_emit` を Configure 層（`mp/__init__.py` の `_build_writer_sink_groups`）が `False` に設定し、Writer（`_mp_runtime.py`）が batch / per-message を統一制御する。

これは §12.1「3層分離維持」の例外として明示する。理由:
- multiprocess Writer は単一スレッドで全 Sink への dispatch を serialize する設計上、Sink ごとの自律的 flush タイミングよりも Writer 集中制御が ordering 保証に有利
- 単一プロセス版（`is_async=False/True` 単独）では `stream_flush_on_emit=True`（既定）を維持し、Sink 自律 flush を行う（3層分離の原則）


## 12. v23 系設計方針

### 12.1 Writer 不変条件

v23 系の改善では、次の前提を崩さない。

| 項目 | 不変条件 |
|---|---|
| Writer ownership | file sink、routing、hash、manifest、archive、purge、reopen は Writer が一元所有する |
| Writer drain | Writer log plane は single serial drain を基本とする |
| Writer write | file への write は O_APPEND またはそれと等価な append-only 操作を維持する |
| Writer 並列化 | v23 系の改善対象に含めない |
| file write | 同一 log family / route / file への並列 write は行わない |
| append-only routing | rename/truncate に依存しない append-only routing 方針を維持する |
| Capture / Transport / Sink | 3層分離を維持し、責務を混在させない |
| logging 互換 | `logging.setLoggerClass()` による Drop-in Replacement を維持する |
| Zero dependency | 外部依存を追加せず、Python 標準ライブラリのみを使用し、サポート対象 Python バージョンで利用可能な API に限る |
| fail-safe | silent loss、silent hang、silent fallback を避ける |

サポート対象 Python バージョンの範囲は §1 の冒頭を参照する。v23 系ではこの範囲を拡大・縮小しない。変更が必要な場合はユーザー判断を仰ぐ。

Writer 並列化は Writer 単独所有による安全性と衝突しやすい。必要性が再浮上した場合も、v23 系の通常改善には含めず、別途ユーザー判断を仰ぐ。

注: この不変条件は、ベンチ結果で観測された p50 の child 数増加および throughput の parent 飽和を v23 系では根本解決しないことを意味する。これらは Writer single serial drain という設計選択の帰結である。v23 系は safety、sequence 完全性、shutdown/drain 契約、caller-side 固定費の可視化と安全な範囲での削減に焦点を置く。fan-in scalability の根本改善は Writer ownership モデルに関わるため v23 系外の判断事項とする。

---

### 12.2 v23 系でやらないこと

| 項目 | 理由 |
|---|---|
| Writer 並列化 | Writer ownership、ordering、manifest 整合性への影響が大きいため |
| flush 契約の弱体化 | durability / safety 契約が変わるため（注: opt-in 設定 `writer_flush_batch>1` による batch flush は §11.27 で許容する。既定動作は per-message flush を維持） |
| append-only routing の意味論変更 | 製品中核価値に関わるため |
| ベンチ結果だけを目的にした unsafe optimization | SafeLogger のブランドと矛盾するため |
| public JSON schema の破壊的変更を無断で行うこと | 外部連携への影響があるため |
| silent drop / silent fallback | fail-safe 方針に反するため |

---

### 12.3 配送契約の用語定義

用語は次の階層に分けて扱う。

| 階層 | 用語 |
|---|---|
| Lifecycle states | attempted / accepted / enqueued / delivered_per_sink / delivered |
| Terminal states | rejected / dropped / writer_reject / partial_delivered / unexpected_loss |
| Policy qualifier | overload_shed |

| 用語 | 定義 |
|---|---|
| attempted | user code が logger に渡したログ呼び出し。logger level filter 等により LogRecord 化されないものは配送責任の対象外 |
| accepted | level 判定および client-side logger filter を通過し、D-SafeLogger transport が配送責任を引き受けたログ。通常 shutdown で lossless 扱いにする場合、accepted log は delivered されなければならない |
| enqueued | accepted log が client-local queue または multiprocess log queue に投入された状態 |
| rejected | timeout、closed、invalid state、Writer unavailable 等により、配送責任を引き受けなかったログ |
| dropped | accepted 後または local queue 段階で破棄されたログ。dropped は silent にしてはならず、counter / warning / summary に反映する |
| delivered_per_sink | 対象 sink 単位で flush 契約上の完了点を通過した状態（注: multiprocess 経路で `writer_flush_batch>1` を opt-in した場合、batch flush 完了点をもって delivered_per_sink とする。§11.27 参照） |
| delivered | 対象 log event の required sink set すべてで delivered_per_sink が成立した状態 |
| partial_delivered | required sink set の一部には到達したが、全 required sink には到達していない状態。silent にしてはならず、counter / warning / summary に反映する |
| writer_reject | Writer 到達後に route / sink / writer-side policy により配送不能と判定されたログ。accepted とは別の terminal state として記録し、unexpected_loss にはしない |
| overload_shed | OOM、永久 block、本体巻き込み停止を避けるために、bounded queue / timeout 方針に従って rejected または dropped として明示的に捨てたログに付与する policy qualifier |
| unexpected_loss | accepted されたにもかかわらず、dropped / rejected / writer_reject / partial_delivered として記録されず、正常 shutdown 後にも delivered されないログ。これは設計または実装バグとして扱う |

required sink set は file sink を中心に定義する。console sink は best-effort / diagnostic sink とし、失敗時は warning / counter 対象にするが、file delivery の unexpected_loss とは分離する。module-specific file sink は route 設定上 required sink に含まれる場合のみ delivered 判定の対象に含める。

**sink 分類の実装（v23h）**

各 handler は `_ds_required: bool` クラス属性で required / best-effort を区別する。

| handler | `_ds_required` | 意味 |
|---|---|---|
| `AppendOnlyFileHandler` | `True`（既定） | required sink。delivered 判定の対象 |
| `ColorStreamHandler` | `False` | best-effort sink。delivered 判定外、失敗は別計上 |
| 利用者が独自に追加した `logging.Handler` 派生 | 属性なし → `True` 扱い | 独自 handler は default required。`_ds_required = False` を明示すれば best-effort として扱う |

`Writer` の per-record 計上規則:

- 全 required handler が成功 → `delivered`（counter 増分なし）
- 全 required handler が失敗 → `_reject_counter += 1`、`writer_sink_reject` または `writer_policy_reject` を増分（双方の原因が混在する record では両方を increment）
- 一部の required handler のみ成功 → `_writer_partial_delivered += 1`（terminal state は `partial_delivered` であり、`writer_sink_reject` / `writer_policy_reject` は increment しない）
- best-effort handler の失敗 → `_writer_best_effort_failures += 1` のみ（`reject_counter` への集約なし）

**partial_delivered と単一 handler route**

`partial_delivered` は required sink set 内で「成功と失敗が混在した」状態を示す terminal state である。required sink set が 1 個（典型的な `root` route や module route の file 単一構成）のときは partial の概念が成立しないため、counter は常に 0 のままである。partial が観測されるのは、利用者が同一 route に複数の required handler を登録した構成に限られる。

`attempted` から `accepted` に入る前の caller-side 脱落には、少なくとも次を含める。

| 脱落契機 | 扱い |
|---|---|
| `logging.Logger.isEnabledFor()` の level 判定 | accepted にならない |
| client-side logger filter が `False` を返すケース | accepted にならない |
| route 解決不能を caller 側で検知したケース | accepted にならない。Writer 到達後の unknown route は writer_reject として別扱い |
| transport closed / writer unavailable を caller 側で判定したケース | accepted にならず rejected として記録する |

handler-level filter、writer-side filter、route / sink / writer-side policy による拒否は Writer 到達後の `writer_reject` として扱う。

`writer_reject` は少なくとも次の内訳を持つ。初期実装で全分類を完全分離できない場合も、可能な粒度で counter / warning / STATUS に反映し、silent failure にしない。

| 分類 | 定義 | v23g 実装上の扱い |
|---|---|---|
| `writer_route_reject` | route 解決不能、または route 対象 sink 不在 | 専用 counter と stderr warning（rate-limited） |
| `writer_reconstruct_reject` | LogEvent の破損 / reconstruct failure（log plane の event path） | 専用 counter と stderr warning（rate-limited、v23h で `writer_event_reject` から分離） |
| `writer_close_marker_reject` | CloseMarker の不正（client_id 欠落 / session mismatch / 未知 client） | 専用 counter と stderr warning（rate-limited、v23h で `writer_event_reject` から分離） |
| `writer_sink_reject` | required sink が存在するが、emit / write / flush 等で失敗（per record で計上） | 専用 counter と stderr warning（rate-limited） |
| `writer_policy_reject` | required handler の filter または Writer 側 policy により配送拒否（per record で計上） | 専用 counter と stderr warning（rate-limited） |
| `writer_format_reject` | formatter / JSON encode 不能など、出力形式生成に失敗 | v23h では handler 例外として `writer_sink_reject` に畳み込む。必要なら後続版で分離 |
| `writer_best_effort_failures` | best-effort sink（console 等）の emit 失敗。`writer_reject` の terminal state には含めない。可視化のための counter のみ | stderr warning（rate-limited）と STATUS 公開のみ。`reject_counter` には集約しない |

同一 route の handler group 内で、一部 handler は成功し一部 handler は失敗または policy reject になった場合、Writer は `partial_delivered` counter を増分する。console sink は best-effort / diagnostic sink であるが、失敗は可視化対象であり、file sink の unexpected_loss とは分離して扱う。

---

### 12.4 Overload Policy と Survival-first 方針

v23 系では、ログ欠損を一律に同じ問題として扱わない。

| 分類 | 扱い |
|---|---|
| unexpected loss | バグ。accepted log が理由なく消えた状態であり、sequence 完全性検証で検出すべき対象 |
| policy-driven rejected | 配送責任を引き受ける前に、timeout / closed / writer unavailable 等で拒否した状態。明示記録が必要 |
| policy-driven dropped | bounded queue overflow 等で、本体保護のために明示的に捨てた状態。counter / warning / summary が必要 |

既定方針:

```text
bounded wait -> visible reject/drop -> process survives
```

これは、ログを無制限に保持して OOM する、または本体処理を永久 block してサービス停止を招くよりも、本体プロセスの生存を優先する方針である。

v23 系では以下をデフォルト禁止とする。

| 禁止事項 | 理由 |
|---|---|
| unbounded log queue | Writer 停止や出力先詰まり時に OOM リスクが無制限に増えるため |
| indefinite producer block | GUI / Web handler / worker loop をログ出力で巻き込むため |
| silent drop | 運用者がログ欠損を検知できないため |
| overflow を unexpected loss と混同すること | 設計バグと overload policy の判断を誤るため |

strict lossless mode、unbounded queue、OOM リスクを許容するモードを追加する場合は、D-SafeLogger の safety 方針に関わるため、必ずユーザー判断を仰ぐ。

#### 12.4.1 Bounded shutdown 契約（v23h）

正常終了経路の shutdown でも silent hang を起こしてはならない。`mp.ConfigureLogger()` は `atexit` で `_mp_shutdown` → `WriterRuntime.stop()` を呼び出すが、`stop()` は次の bounded 契約に従う。

- `stop(timeout)` は最大 `timeout` 秒（既定 `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`）だけ `log_thread` / `control_thread` の join を待つ
- timeout 後に thread が生存していた場合、**stderr に visible warning を出力する**（stuck thread 名を含めて、silent failure にしない）
- Writer の `log_thread` / `control_thread` は **`daemon=True`** で起動するため、stop() が drain を完了できなかった場合でも Python interpreter は exit できる（process survives 原則）
- これにより shutdown 経路は次の不変条件を満たす:

```text
bounded wait (≤ timeout) -> visible warning (drain incomplete を可視化) -> process exits
```

この設計により、drain 経路に未知の hang が混入した場合でも host process が永久に block することを禁止する。drain 完全性は `stop()` の serial drain ロジックが担保し、daemon フラグは fail-safe な escape のみに用いる。

---

## 13. 変更履歴
* **v6**: `overflow_mode` の廃止、`max_count` の導入による動作ルールの一貫性確保。
* **v7**: `pg_name` によるファイル名決定規則の明文化。環境変数による `diagnose` のオーバーライド規則追記。
* **v8 (v8a/v8b)**:
  * サフィックス定義や `startup_interval` の追加。
  * 「関心の分離」「Drop-in Replacementの利点」「パージの自己修復性」等、設計の重要思想と強みを仕様書へ再編入。
  * 環境変数の直感的なサンプル例を追加。
* **v9**:
  * 全体の章構成、リスト表記を読みやすい階層（見出し）に抜本的構造化（3章・5章）。
  * 誤解を招く `day` 表現を `weekday` (`cyclic_weekday`) へ修正。
  * カスタムフォーマット (`fmt`) の上書き仕様を復元・明記。
  * レイヤ分離の明確化のため、呼称を基本設計仕様書に改定。
* **v10**:
  * 誤用されていた「ローテーション」の用語を「ルーティング (Routing)」に統一。
  * リソースベースモード (`size`, `count`) において、`max_count` 未指定時の動作を「上限到達エラーモード」に再定義し、世代管理の対象外として `suffix_digits` で桁数を制御する設計に洗練。
  * 2章のアーキテクチャ概要で触れられていた機能（Async、Diagnostic、Contextualize 等）の具体的な技術仕様を6章へ新設し、基本設計の網羅性を向上。
  * 更新履歴（Changelog）の完全復元。
* **v11**:
  * Sonnet によるレビュー指摘の反映。
  * `interval` パラメータにおける `min_interval` と `startup_interval` の型・単位の整合性（厳密な区別）を定義。
  * 「上限到達エラーモード」において、なぜ世代管理と相反し無視されるかの設計意図を明文化。
  * `console_out` のデフォルト値（True）の設計根拠を 6.5 節として定義。
  * `GetLogger(name='')` に対する標準logging互換（ルートロガー返却）の挙動を仕様化。
* **v12**:
  * リソースベースのサイクリックモードでの `suffix_digits` の連動桁数仕様を明記。
  * `D_LOG_CONSOLE` によるコンソール出力の環境変数強制上書き機能を追加。
  * `ConfigureLogger` 時に Fail-Fast なストレージ状態事前検証仕様を追加。
  * ルーティング設定の典型的なユースケース（TIPS）と、切り替え動作・非同期別スレッド実行シーケンスの動作ドキュメントを大幅拡充。
  * 世代管理に付随する `archive_mode` の追加。および、「本来 backup_count を超過して削除される運命にある古いログファイルを、削除する代わりにZIPアーカイブ化して残す機能」であることを厳密に明文化。
  * ストレージ枯渇時のZIPアーカイブ保護（ランタイムエラーのフェイルセーフ）の安全策を追加定義。
* **v13 (安全・堅牢性 統合版)**:
  * プロダクト名変更、`diagnose` の環境変数オンリー化（安全設計）。
  * 構造化ログ対応 (`structured`)、`contextvars` 刷新、カラー出力と `sys.stderr` 明示。
  * `fmt` / `datefmt` の引数構成の適正化、および `logging.Formatter` インスタンス直接渡しの許容。
  * Append-Only 背景追記、専用 CLI ユーティリティ群 (`dsafelogger`) の設計追加。
  * 実装エンジニア向けの実装方針・アーキテクチャヒント（Formatter実装法等）の全編補完。
* **v14 (3層設定管理パイプライン)**:
  * 3層設定管理パイプライン（環境変数 > INI > 引数）の導入。`config_file` 引数および `{env_prefix}_CONFIG` 環境変数によるINI設定ファイルの読み込みをサポート。
  * `env_name` パラメータを `env_prefix` に変更。全環境変数名をプレフィックスベースで統一し、名前空間の一貫性を確保。
  * 環境変数の役割分離: `{prefix}_LEVEL` をグローバルレベル専用に限定し、モジュール別指定は新設の `{prefix}_MODULES` に移行。
  * INIファイルによるモジュール別セクション（`[dsafelogger:mod]`）で、レベル・出力先・独自ルーティングの個別設定が可能に。
  * INIパーサーは `configparser(interpolation=None)` で実装（Zero Dependency維持、`%` エスケープ不要）。不正値はサイレントフォールバックせず Fail-Fast で例外送出。
  * `{prefix}_DIAGNOSE` の聖域保護: INIファイルからの設定を一切許容せず、環境変数オンリーの安全設計を堅持。
  * `{prefix}_COLOR` の有効値を `{prefix}_CONSOLE` と統一（`"true"/"false"` も許容）。
* **v14.5 (v14 設計レビュー反映)**:
  * §7.3.2: `min_interval` の有効値を `{5, 10, 15, 20, 30}` から 60 の全約数 `{1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}` に拡張。
  * §7.5: 世代管理の対象ファイル特定において、`pg_name` の前方一致による誤マッチを防止する厳密なファイル名フィルタリング要件を追加。
  * §9.2: `ConfigureLogger` の冪等性管理を `bool` から多状態管理へ拡張する方向性を導入。v18 では 5 状態（`unconfigured` / `auto` / `explicit` / `configuring` / `shutting_down`）として確定した。
  * §9.7（新規）: `LogRecord` の非破壊取り扱い（局所マッピング / 表示用 proxy）を Formatter / Handler の必須実装指針として追加。
  * §9.8（新規）: レベル名略称マッピングは `format()` 内の `LEVEL_MAP.get()` のみで実行し、`addLevelName()` によるグローバル副作用を回避する方針を明確化。
* **v15 (カスタムログレベル & ファイル完全性検証)**:
  * `register_level()` 関数の追加（§9.9, §10.3）。任意の数値位置にカスタムログレベルを差し込み可能。3文字略称・ANSIカラー・便利メソッドの一括登録を、`ConfigureLogger` 前の単一呼び出しで完結。ビルトイン5段階（DEBUG/INFO/WARNING/ERROR/CRITICAL）は不可侵として保護。3層設定管理パイプラインとの完全整合: 登録済みカスタムレベルは環境変数・INI・引数の全てで使用可能。
  * ファイル完全性検証（Integrity Verification）機能の追加（§7.6）。`enable_hash=True` でルーティング時に SHA-256 サイドカーファイル（`.sha256`）を自動生成。`manifest_path` 指定で、全ファイルのハッシュ履歴をタイムスタンプ付きでマニフェストファイルに追記集約。サイドカーは `sha256sum -c` 互換フォーマット。パージ/アーカイブとの連動（削除時はサイドカーも連動削除、ZIP同梱）。
  * `{prefix}_HASH` / `{prefix}_MANIFEST` 環境変数の追加（§4.7, §4.8）。INIファイルの `enable_hash` / `manifest_path` キーの追加（§5.3）。
  * `ConfigureLogger` に `enable_hash` / `manifest_path` 引数を追加（§10.1）。
  * `LEVEL_MAP` / `COLOR_MAP` をクラス変数からインスタンス変数に変更し、カスタムレベルの統合マップを動的構築（§9.8）。
  * 非破壊的変更: 両機能ともオプトインであり、使用しない場合は v14.5 と完全に同一の動作。
* **v15a (基本設計の明確化補完)**:
  * 対象 Python バージョンを 3.11 以上と明記。
  * `pg_name` の禁止文字サニタイズ規則、`{prefix}_MODULES` の Windows 絶対パス対応、不正モジュールspecの扱い、`{prefix}_DIAGNOSE` の厳格な有効値、カラー自動判定の優先順位を仕様として明文化。
  * INI の bool 有効値、未知キー/未知セクションの扱い、空モジュール名セクションのエラー化を仕様として追加。
  * `size` / `count` の上限到達エラーモードと `backup_count` の関係、`log_path` 自動生成後の Fail-Fast 検証、非同期終了時のワーカー待機方針を明文化。
  * `contextualize` の Formatter 側直接取得方針、`diagnose` におけるセンシティブ情報マスキングと巨大 `repr` 抑制方針を基本設計へ昇格。
* **v15b (環境変数表現の明確化)**:
  * 環境変数による設定を「動的制御」ではなく「起動時設定上書き」として表現を統一。
  * 稼働中の自動反映を想起させる記述を除去し、変更反映には再起動または再初期化が必要であることを明記。
  * ユースケース記述および `console_out` の説明も、起動前設定として誤解のない文面へ修正。
* **v16 (センシティブキーワードのカスタマイズ & 辞書ベース設定)**:
  * `sens_kws` / `sens_kws_replace` パラメータの追加（§9.4, §10.1）。`f_locals` マスキングのセンシティブキーワードをユーザーがカスタマイズ可能に。デフォルトではビルトインキーワード（12語）に追加され、`sens_kws_replace=True` で完全置換。INI/辞書では `sens_kws` をカンマ区切り文字列で指定。
  * ビルトインセンシティブキーワードを12語に統一: `password`, `passwd`, `pass`, `secret`, `token`, `key`, `api_key`, `apikey`, `auth`, `credential`, `private`, `cert`
  * 辞書ベース設定（`config_dict`）の追加（§5.7, §10.1）。INIファイルの代替として `dict[str, dict[str, str]]` を `ConfigureLogger` に直接渡す機能。INIファイルと同一のセクション/キー構造・バリデーション・型変換パイプラインを共有。
  * `config_file` と `config_dict` の排他制約: 両方を同時に指定した場合は `ValueError`。`{prefix}_CONFIG` 環境変数が設定されている場合は双方を上書き。
  * 3層パイプラインの第2層を「INIファイルまたは辞書」に拡張（§3.1, §3.2, §3.4）。
  * `dsafelogger init` サブコマンドの追加（§8.1）。INI設定テンプレートを標準出力に出力する CLI コマンド。全設定キーをコメントアウト状態で記載し、インラインコメントで使い方を案内。`sens_kws` / `sens_kws_replace` を含む v16 全キーに対応。
  * §11（後方互換性への影響）を削除。
* **v17 (コンソールカラーパレット設定)**:
  * INI ファイルおよび config_dict の `[global]` セクションに `color_{略称}` キーを追加（§5.2, §5.3）。ビルトイン5段階（DBG/INF/WAR/ERR/CRI）のコンソールカラーを、ターミナル環境や視覚特性に応じて変更可能に。`register_level()` で登録されたカスタムレベルのカラーも同一の命名規則で上書き可能。
  * 3層パイプラインの第2層（INI/辞書）のみで対応。環境変数（第1層）・引数（第3層）には意図的に非対応とし、`ConfigureLogger` のシグネチャ変更なし（§9.6）。
  * `color_` プレフィックスのキーはパターンベースで認識され、固定キー一覧（`VALID_GLOBAL_KEYS`）には含まれない。未知略称・不正値は stderr に警告出力してスキップ（Fail-Fast ではない）。
  * カラーパレットのマージ順序: ビルトインデフォルト → `register_level()` 指定カラー → INI/辞書の `color_{略称}` キー。
  * `dsafelogger init` テンプレートにカラーパレットセクションを追加（§8.1.2）。
  * 非破壊的変更: `color_` キーを指定しなければ v16 と完全に同一の動作。
* **v18 (free-threaded Python 対応)**:
  * 通常 build に加え、Python 3.13+ の free-threaded build を設計対象に追加。
  * `_configure_state` を 5 状態（`unconfigured` / `auto` / `explicit` / `configuring` / `shutting_down`）へ拡張し、共有状態の安全性を GIL に依存しない方針を明記。
  * `_active_workers` を `list` から `set` に変更し、重複登録防止と `discard()` による終了競合時の例外回避を追加。
  * async mode の queue hand-off を見直し、producer thread 側で `contextualize` 情報をスナップショット化する設計へ更新。`QueueHandler.prepare()` は D-SafeLogger 独自の完全オーバーライド前提とした。
  * diagnose の cross-thread 安全化を追加。queue を跨ぐ場合は producer thread 側で traceback / `f_locals` を安全なスナップショットへ変換し、consumer thread 側では live `f_locals` 参照を行わない。
  * 内部 thread は常に空 `Context` で開始する方針を追加。ユーザー thread への初期 context 継承は Python 本体仕様に従う。
  * safe shutdown の保証レベルを「ログ本体の flush」と「housekeeping の best-effort」に分離し、queue drain → worker join → handler close の順序を仕様化。
  * integrity 周辺を強化し、同一 family maintenance の直列化、manifest 追記の直列化、`.sha256` sidecar の原子的書き込み方針を追加。
* **v20 (Capture/Transport/Sink 3層化・Vendor-Agnostic・FrozenContext)**:
  * 内部アーキテクチャを Capture / Transport / Sink の3層モデルに再構成（§11.2）。公開 API（`ConfigureLogger` / `GetLogger` / `register_level`）に変更なし。
  * `Transport` 抽象の導入（`DirectTransport` / `QueueTransport`）。将来の `IPCTransport`（マルチプロセス対応）追加を構造的に準備（§11.3, §11.4）。
  * Vendor-Agnostic 原則の明文化（§2, §11.5）。コアモジュールからのベンダー固有ロジック（OpenTelemetry 等）排除を設計ガードとして制度化。CI では AST / import ベースの静的検査を前提とする。
  * `file_fmt` / `console_fmt` パラメータの追加（§6.3, §10.1）。ファイルとコンソールに個別の Formatter を指定可能に。INI / config_dict の `[global]` セクションにも対応キーを追加（§5.3）。
  * コンテキスト管理を `contextvars.ContextVar[dict]` から `contextvars.ContextVar[MappingProxyType]`（FrozenContext）に変更（§9.5）。async mode の queue hand-off を O(1) の参照渡しに最適化し、producer 側の `dict.copy()` を不要化。
  * `structured=True` と `file_fmt` / `console_fmt` の排他制約を拡張。`structured=True` 時はファイル・コンソールともに JSON Lines 形式で出力する。なお、`file_fmt` / `console_fmt` に `logging.Formatter` インスタンスを渡した場合、`datefmt` 引数は無視される（インスタンスが持つ datefmt が優先）（§6.4）。
  * async mode + `contextualize()` の hand-off bug を FrozenContext 契約へ一本化して解消。
  * 非破壊的変更: `file_fmt` / `console_fmt` を指定しなければ v18 と完全に同一の動作。FrozenContext も外部 API に影響なし。
  * v17.x の async mode + contextualize コンテキスト喪失バグの完全解消（v18 で構造解決、v19 で snapshot コスト改善）。
* **v20 (レビュー指摘反映・堅牢性強化)**:
  * 状態マシンのエラーリカバリを完全定義。`configuring` 中の例外で `unconfigured` へロールバック、`shutting_down` 完了後は `unconfigured` へ遷移。完全状態遷移表を追加。
  * `_registry_lock` の新設によりデッドロックリスクを解消。`_get_manifest_lock()` / `_get_family_lock()` は `_lifecycle_lock` ではなく専用の `_registry_lock` を使用。
  * `register_level()` 全体を `_lifecycle_lock` で保護し、free-threaded Python での並行呼び出しによる `_custom_levels` 破損を防止。
  * `LogEvent` / `_event.py` を v20 本体から分離し、IPCTransport（Step 10 / v19.1）と同時導入に変更。v20 は `LogRecord` + `_ds_*` 属性の契約を維持。
  * PipelineBuilder / Pipeline / ResolvedConfig の詳細設計を追加（詳細設計書 §3.4）。
  * `StructuredFormatter` に vendor-neutral な extra フィールド抽出（`_merge_extra_fields`）を追加。`_STD_RECORD_KEYS` に Python 3.12+ の `taskName` を追加。
  * `RoutingStrategy` ABC に `advance()` をデフォルト no-op で追加（LSP 準拠）。
  * `CountStrategy.should_switch()` の CQS 違反を修正。カウント更新を `advance()` に移動。
  * `_switch_file()` のロールバック改善。新ファイル open を先行試行し、失敗時は旧ファイルへロールバック。
  * `DirectTransport.stop()` の部分失敗対応。個別 try/except で全ハンドラの処理を試行。
  * SHA-256 二重計算の排除。`write_sidecar()` / `append_manifest()` に `hash_value` 引数を追加。
  * `append_manifest()` の `datetime.now()` 二重呼出を修正（1回のみ呼出）。
  * FrozenContext の O(1) 表現を限定。「No-Copy Context」→「No-Copy Snapshot」。`contextualize()` 入口の O(n) コストを明記。
  * `MappingProxyType` の浅い不変性制約を明記（kwargs には immutable な値のみを渡すこと）。
  * `configuring` 状態の挙動を確定: `RLock` 再入は No-Op return、別スレッドは lock 待機。
  * `sens_kws` / `sens_kws_replace` / `file_fmt` / `console_fmt` の環境変数非対応を明記。
  * `env_prefix` の INI/config_dict 変更を禁止。
  * cyclic mode + `enable_hash=True` の旧挙動を整理。v23j の現行挙動は Fail-Fast（`ValueError`）とする（§3.4 / §7.6.6）。
  * `structured=True` 時のコンソール出力も JSON であることを明記。
  * Formatter インスタンス渡し時の `datefmt` 優先規則を明記。
  * Vendor-Agnostic CI grep を import 文に限定。
* **v21 (並行安全性・非破壊 level 表示・module Transport 統合)**:
  * `ConfigureLogger` の `_do_configure()` 全体を `_lifecycle_lock` 保持下で実行し、初期化中の中途状態読み取りを並行安全に防止。`GetLogger` は `'configuring'` 状態検出時に lock 構造待機。
  * `AppendOnlyFileHandler` の独立 `self._lock` を廃止し、親クラス `logging.Handler` の lock API に統一。
  * `DSafeFormatter.format()` および `ColorStreamHandler.emit()` で `record.levelname` を直接変更しない非破壊方式を導入。TLS proxy reuse パターン（`threading.local()` + `_DisplayRecordProxy`）により GC 圧を排除しつつ `%` / `{}` / `$` 全 style で同一意味論を保証。
  * `is_async=True` の意味論を module-specific path 経路にも一貫適用。`Pipeline` は `module_transports: dict[str, Transport]` を保持し、`stop()` で全 Transport を構造的に停止。
  * context snapshot fallback を `hasattr` ベース分岐に変更。`_ds_context` 属性が存在する場合は空の `MappingProxyType({})` でも authoritative な snapshot として扱う。
* **v22 (マルチプロセス対応正式設計)**:
  * Section 11 を「設計準備」から完全なマルチプロセス対応の正式設計へ改訂。
  * `ipc_mode` / `ipc_queue` / `ipc_queue_size` パラメータを `ConfigureLogger` に追加。`get_ipc_queue()` 公開関数を追加。
  * `IPCSendTransport`（子プロセス → 親プロセス送出）と `IPCListener`（親プロセス側 mp.Queue consumer + route-based dispatch）を新設。
  * `LogEvent` TypedDict（`total=True`）をプロセス境界越しの内部シリアライゼーション契約として定義。`_ds_route`（sink group identity）による dispatch destination の明示を追加。
  * `_ds_context` / `_ds_extra` は常にキーを持ち、空は `{}` で表現。receiver 側は key existence で authoritative snapshot として扱い、v21 `hasattr` 意味論を IPC 越しに維持。
  * `_ds_extra` の予約領域と衝突規則を定義（標準 LogRecord 属性 / `_ds_*` prefix の保護）。
  * `ipc_mode='child'` の role-specific `ConfigureLogger()` 動作を明文化（file sink / console sink / writer-side 検証 / worker 初期化を省略）。
  * child 側通常ログの console 出力を v22 初版では行わない。内部 warning のみ `print(..., file=sys.stderr)` で直接出力（ロガー再帰禁止）。
  * parent 側 `IPCListener` は Capture 層の意味論（level 判定、logger 階層評価、`propagate` 判定）を一切再実行しない。`_ds_route` に基づく direct dispatch のみ。
  * 親子 bootstrap invariants を定義（custom level 一致、routing topology 一致）。不一致時は誤配送ではなく skip + warning（Safe 原則）。
  * sentinel 投入は child 送信終了保証後とする shutdown race 対策を追加。
  * `{prefix}_IPC_MODE` 環境変数を追加。新規ファイル `_ipc.py` を追加。
* **v22a (外部 log rotation 共存)**:
  * `routing_mode='none'` に限定した外部 log rotation 共存を正式サポートし、公開 API `ReopenLogFiles()` を追加。
  * writer-side のいずれかの file sink が `routing_mode != 'none'`、または `ipc_mode='child'` の場合は `ReopenLogFiles()` を fail-fast とする契約を追加（v22h では single / multiprocess を通じて `routing_mode != 'none'` は `ValueError` へ整理）。
  * `ipc_mode='parent'` / `is_async=True` を含む writer-side sink 群（root / module 別 path / listener 側 file sink）を再 open 対象に含める。
  * signal handler の自動登録は行わず、`SIGHUP` 連携や `logrotate postrotate` からの呼び出しはアプリケーション/運用層の責務と明記。
  * Linux 運用チュートリアルでは `logrotate` と `ReopenLogFiles()` の組み合わせを説明し、ライブラリ内蔵 routing との混在禁止を明記する。
  * IPC では `queue.put()` 内部 pickle 失敗時の repr 再送、`ipc_mode='child'` 時の `is_async` 制約、`multiprocessing` current context 継承方針を明文化した。
  * `get_ipc_queue()` は current Pipeline の寿命に束縛され、再初期化や shutdown 後は再取得と child 側再配布が必要であることを明文化した。


* **v22c (dsafelogger.mp 再設計)**:
  * multiprocess 正式設計を `dsafelogger.mp` namespace に再編し、single-process 版 API 契約を完全維持したまま multiprocess 版を別入口へ分離。
  * multiprocess 公開 API を `ConfigureLogger()` / `AttachCurrentProcess()` / `DetachCurrentProcess()` / `GetWorkerInitializer()` / `GetLogger()` / `ReopenLogFiles()` として定義。
  * `worker_model` を開発者選択 API とし、internal transport backend は `multiprocessing.Queue` 固定として隠蔽。
  * client / Writer モデル、bootstrap object `ctx`、attach 契約、Drop-in Replacement の process-local 再適用、control plane としての `ReopenLogFiles()`、safe shutdown の基本意味論を追加。

* **v22d (control plane / QoS / active client registry 固定化)**:
  * 通常ログの log plane と control command 用 control plane を明確に分離し、混在を禁止。
  * `ControlRequest` / `ControlAck`、`ctx`、`LogEvent` の期待構造カテゴリを固定。
  * `ATTACH` / `DETACH` / `STOP` を drop 不可、`REOPEN` / `STATUS` を ACK 必須とする QoS 規則を明文化。
  * shutdown 判定を sentinel 個数ではなく active client registry に基づく方針へ固定。

* **v22e (IPC payload / executor 定義の拘束条件追加)**:
  * process 境界 payload を picklable に限定し、`Event` / `Lock` / `Condition` 等の非 picklable 同期オブジェクトを payload に含めることを禁止。
  * ACK は log plane ではなく control plane の戻り経路で返すことを明記。
  * `worker_model="executor"` は `concurrent.futures.ProcessPoolExecutor` のみを指し、`ThreadPoolExecutor` を対象外と明記。

* **v22f (registry / payload 構築原則 / Writer crash 補強)**:
  * registry hash 照合タイミング、spawn 再 import 時の `register_level()` 冪等再登録ルールを追加。
  * bootstrap payload に Strategy / Formatter インスタンスを含めず、生の dict / プリミティブ値のみを含める構築原則を追加。
  * `_ds_context` / `_ds_extra` 常在規約の理由、`logging.setLoggerClass()` の process-local 意味論、worker crash 時の active client registry 整合、Writer 死亡検知の補強を追加。

* **v22g (`ipc_log_timeout` と log plane backpressure 制御)**:
  * multiprocess 版 `ConfigureLogger()` に `ipc_log_timeout` を追加し、通常ログ (`LOG`) の log plane queue に対する送信待機時間を公開仕様化。
  * 環境変数 `{prefix}_IPC_LOG_TIMEOUT` による上書きを追加し、3層設定管理パイプラインの第1層で評価することを明記。
  * `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` のハードリミットを追加し、過大値は stderr warning + クリップで継続、`<=0` は Fail-Fast (`ValueError`) とする。
  * `ipc_log_timeout` は control plane には適用せず、`LOG` の backpressure 制御専用パラメータであることを明確化。

* **v22h (Writer 死亡検知 / ACK 根拠 / 版履歴整備)**:
  * §11.22 に Writer 死亡検知を追加し、送信失敗・ACK timeout・Writer 終了観測時の drop + stderr warning 方針を明記。
  * `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` の設計根拠を追記。
  * 変更履歴の版番号・順序を整理し、v22d / v22e / v22f の主要変更を個別エントリ化。
  * `AttachCurrentProcess()` の 3-phase 化、fork 継承時の process-local rehydrate、`_mp_lifecycle_lock` と `_lifecycle_lock` を同時取得しない不変条件を明文化。
  * `RoutingStrategy.on_emit()` による `CountStrategy` の CQS 整合、`AppendOnlyFileHandler.emit()` での `OverflowError` 再送出、`reopen()` の defense-in-depth を追記。
  * Writer log/control thread の non-daemon 化、`STOP` 後の control queue drain、process-local async queue の bounded 化、`stop()` 後 `emit()` の drop 契約を追記。
  * multiprocess Formatter freeze/rebuild 契約を allow-list と `FormatterSpec` ベースで具体化し、fork 継承 child が Writer 停止後に session を再生しない境界を明文化。
* **v22i (実装後知見の反映)**:
  * control plane reply channel を Queue ベースから Pipe(`multiprocessing.Connection`) ベースへ変更し、Queue-in-Queue 不成立問題を解消。
  * `reply_queue_factory_token` を廃止し、ACK 待機を `poll() + recv()` へ変更。
  * `_control_loop` の停止判定を loop 先頭から timeout 側へ移し、`STOP` 後の後発 `ATTACH` 拒否契約を実装可能な形に固定。
  * Python 3.14 差分として `logging.Formatter.defaults` の取得経路差異、および closed queue に対する `ValueError` を考慮する実装ノートを追加。
  * `DetachCurrentProcess()` を multiprocess 公開 API に追加し、active client registry ベース shutdown と公開契約を整合させた。
  * fork 継承 child は親の client identity を流用せず、同一 Writer session 上で child 専用 `client_id` を再登録する契約へ更新。
  * `mp_context` 指定時は log/control queue と Pipe reply path の全 IPC primitive へ一貫適用すること、bootstrap ready ACK で `protocol_version` / `registry_hash` を照合すること、unknown route の root fallback を禁止することを明文化。
* **v23 (v23 系設計方針・配送契約用語・Overload Policy baseline)**:
  * v22i 基本設計仕様書を v23 として複写し、v23 系設計方針を §12 として追加。挙動変更なし。
  * §12.1 Writer 不変条件: Writer ownership / single serial drain / append-only write / Writer 並列化除外を明文化。
  * §12.2 v23 系でやらないこと: Writer 並列化・flush 契約弱体化・silent drop 等を明示禁止。
  * §12.3 配送契約の用語定義: attempted / accepted / enqueued / rejected / dropped / delivered_per_sink / delivered / partial_delivered / writer_reject / overload_shed / unexpected_loss を定義。
  * §12.4 Overload Policy と Survival-first 方針: unexpected loss / policy-driven rejected / policy-driven dropped の区別、bounded wait 方針、unbounded queue / indefinite block / silent drop の禁止を明文化。
  * 実装との差分棚卸しを private planning notes に記録した。
* **v23a (benchmark sequence 完全性検証)**:
  * multiprocess benchmark に `run_id` / `repeat_index` / `worker_index` / `sequence_no` を導入し、行数一致から missing / duplicate / JSON parse failure / route mismatch 検証へ引き上げた。
  * benchmark profile を `integrity_profile` / `performance_profile` / `overload_profile` に分離した。
* **v23b (CloseMarker drain 契約)**:
  * Writer shutdown / drain 完了判定から `multiprocessing.Queue.empty()` 依存を廃止し、client ごとの CloseMarker 到達で drain を判定する設計へ更新した。
  * `close_marker_failed` と degraded shutdown の扱いを追加した。
* **v23c (queue 設定化・原因別 counter)**:
  * multiprocess 版 `ConfigureLogger()` に `ipc_log_queue_maxsize` / `ipc_client_queue_maxsize` を追加し、対応する環境変数を §4 / §11.16 に追加した。
  * client 側 drop counter を原因別に分離し、Writer 側 route/event reject counter を `STATUS` に公開した。
* **v23d (diagnostic benchmark)**:
  * production code を変更せず、diagnostic wrapper により capture / serialize / queue put / writer dispatch などの latency stage を分解測定する benchmark を追加した。
* **v23e (Writer flush 最適化)**:
  * Writer 側集中 flush 制御を導入し、file handler の `stream_flush_on_emit=False` と Writer batch / idle flush により dispatch 固定費を削減した。
* **v23f (`_ds_route` structured JSON leak 修正)**:
  * multiprocess internal routing field `_ds_route` を structured JSON public output から除外した。破壊度は軽微、ユーザー承認済みとして記録した。
* **v23g (監査対応・flush opt-in 化・仕様整合)**:
  * v23e の batch flush を `writer_flush_batch>1` の明示 opt-in に変更し、既定 `writer_flush_batch=1` で per-message flush 契約へ戻した。
  * `_LOG_QUEUE_MAXSIZE` を 10000 に揃え、§11.16.1 の既定値と実装を整合させた。
  * drain deadline residual queue、flush error、handler sink/policy reject、partial delivery を counter / warning / STATUS で可視化する方針へ更新した。
* **v23h (v23g 監査結果対応)**:
  * §12.3 を改定し、required / best-effort sink 分類と per-record 計上規則、`partial_delivered` の単一 handler 不成立を明記した。
  * `writer_event_reject` を `writer_reconstruct_reject`（LogEvent reconstruct path）と `writer_close_marker_reject`（CloseMarker validation path）に分離し、`writer_best_effort_failures` を新設した。
  * Writer 側の rate-limited stderr 規約（初回 + 100 件ごと）を `writer_sink_reject` / `writer_policy_reject` を含む全 reject counter に統一適用することを明文化した。
  * log_queue は `multiprocessing.queues.Queue` 派生の `TrackedQueue` で生成し、init 時例外プローブで native `qsize()` 対応を判定して未対応プラットフォームでは `multiprocessing.Value` カウンタへ自動 fallback する旨を §11.16.1 / 詳細設計 §15a.5 に追加した（OS 判定なし）。
  * env var `{prefix}_IPC_LOG_TIMEOUT` / `_IPC_LOG_QUEUE_MAXSIZE` / `_IPC_CLIENT_QUEUE_MAXSIZE` / `_WRITER_FLUSH_BATCH` の invalid 値は warning + ignore から `ValueError` 即時 raise に変更した（fail-fast）。
  * `WriterRuntime.__init__` で `ctx.writer_flush_batch < 1` を `ValueError` とし、`BootstrapContext` 直接構築時の安全網を追加した。
  * `_log_loop` の idle / shutdown flush は `_batch_flush_enabled = (writer_flush_batch > 1)` のフラグ制御に置き換え、per-message mode の dead branch を回避した。
  * §12.4.1 Bounded shutdown 契約を新設。`WriterRuntime` の `_log_thread` / `_control_thread` を **`daemon=True`** に変更し、`stop()` の join timeout 後に thread が生存していれば stuck thread 名を含む stderr visible warning を出すよう統一した。drain 完全性は引き続き `stop()` の serial drain ロジックが担保し、daemon フラグは §12.4 「process survives」原則に基づく fail-safe escape として用いる（**v22h で行った non-daemon 化の決定を v23h で撤回**。当時の決定根拠「通常終了の安全性を daemon thread に依存しない」は atexit による `runtime.stop()` 呼び出しが確立される前のものであり、現状は `stop()` が drain を担う構造のため daemon=True で支障がない）。
  * v23g 監査同期として、CloseMarker の `session_id` / expected client 検証、`mp.ConfigureLogger()` シグネチャ・環境変数一覧・benchmark profile queue 前提の同期を追加した。
* **v23j (OSS公開前 review 対応・公開運用固定)**:
  * 実装動作変更なし。v23h の Writer-owned sinks、CloseMarker drain、分類済み delivery-state counters、bounded shutdown 契約をそのまま正式仕様として公開する。
  * OSS Review の preview 推奨に対し、`dsafelogger.mp` は preview / experimental ではなく正式 API として扱う判断を記録した。理由は、MP の価値を raw throughput ではなく Writer-owned sinks と異常時 delivery state の可観測性として定義し直し、対応する resilience profile と標準品質ゲートを整備したためである。
  * OpenTelemetry / structlog coexistence tests は optional dependency の skip 対象ではなく、`dev` dependency group を入れた full test suite の一部として実行する方針に統一した。`optional_integration` marker は診断用選択 marker に限定する。
  * `tests/` から `multiprocessing.Queue.empty()` 依存を排除し、spawn E2E では `mp.ConfigureLogger(..., mp_context=ctx)` と worker process creation に同一 context を使う公開条件を明確化した。
  * benchmark 公開モデルを固定した。実行ごとの成果物は `benchmarks/results/<session>/`、公開代表 session は `benchmarks/summary/manifest.json`、生成 summary は `benchmarks/summary/*.md`、公開分析は手動編集の `BENCHMARK.md` とする。
  * package release version を `0.2.0` に確定し、`pyproject.toml` と `dsafelogger.__version__` を一致させる方針を記録した。

### v23j Publication Sync Addendum

公開前同期として、coverage 再生成、API docs 再生成、examples の formal MP / external rotation 追加、GitHub workflow gate 強化、`docs/design/` 公開設計書の readiness check を対象に含める。これらは runtime behavior を変更しない公開成果物同期であり、release version は `0.2.0` のまま維持する。
