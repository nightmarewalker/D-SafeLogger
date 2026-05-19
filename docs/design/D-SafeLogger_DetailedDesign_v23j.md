# D-SafeLogger 詳細設計書 v23

本文書は `D_SafeLogger_Specification_v22i_full.md` を基本設計とし、実装に必要な内部設計を定義する。
対象 Python バージョンは **3.11 以上**（型ヒント `X | Y` 構文の完全活用を理由とする）。

---

## 1. モジュール構成

```
dsafelogger/
  __init__.py          # single-process 公開 API (ConfigureLogger, GetLogger, register_level, ReopenLogFiles)
  _logger.py           # DSafeLogger クラス（logging.Logger 拡張）
  _handler.py          # AppendOnlyFileHandler
  _async.py            # DSafeQueueHandler / DSafeQueueListener / safe shutdown
  _formatter.py        # DSafeFormatter, DiagnosticFormatter, StructuredFormatter
  _writer_formatter.py # Writer runtime で使用する formatter spec 解決 helper
  _color.py            # ColorStreamHandler, ANSI カラーマッピング, Windows VT100 有効化
  _routing.py          # RoutingStrategy 群（ファイル名決定ロジック）
  _sink.py             # FileSink / ConsoleSink / SinkGroup（writer-side sink graph の中心抽象）
  _purge.py            # PurgeWorker（削除）/ ArchiveWorker（ZIP圧縮）
  _transport.py        # single-process Transport 抽象（DirectTransport / QueueTransport）
  _pipeline.py         # single-process ResolvedConfig / PipelineBuilder / Pipeline
  _context.py          # contextvars ベースのコンテキスト管理（FrozenContext）
  _levels.py           # カスタムログレベル登録・管理（register_level, get_all_level_map 等）
  _integrity.py        # ファイル完全性検証（compute_sha256, write_sidecar, append_manifest, HashWorker）
  _env_parser.py       # single-process / multiprocess 共通の環境変数パーサ
  _ini_loader.py       # INIファイルローダー（configparser ベース、Fail-Fast バリデーション）
  _constants.py        # 定数定義（レベル名マッピング、カラーコード等）
  _validator.py        # Fail-Fast パーミッション・ディスク容量検証
  _cli.py              # dsafelogger CLI エントリポイント（argparse サブコマンド）
  mp/
    __init__.py        # multiprocess 公開 API (ConfigureLogger, AttachCurrentProcess, DetachCurrentProcess, GetLogger, GetWorkerInitializer, ReopenLogFiles)
  _mp_protocol.py      # BootstrapContext / LogEvent / ControlRequest / ControlAck
  _mp_attach.py        # AttachCurrentProcess / DetachCurrentProcess / GetWorkerInitializer / process-local attach state
  _mp_runtime.py       # Writer runtime / active client registry / shutdown / reopen / counters
  _mp_control.py       # control plane request/ack helpers
```

---

## 2. クラス設計

### 2.1. クラス一覧と責務

| クラス名 | 責務 | 継承元 | モジュール |
|----------|------|--------|-----------|
| `DSafeLogger` | Logger 拡張。`contextualize()` メソッド提供 | `logging.Logger` | `_logger.py` |
| `AppendOnlyFileHandler` | Append-Only ファイル書き込み。RoutingStrategy に基づきファイル名決定・切り替え | `logging.FileHandler` | `_handler.py` |
| `DSafeQueueHandler` | async mode 用。producer thread 側で context/diagnose snapshot を付与して queue へ渡す | `logging.handlers.QueueHandler` | `_async.py` |
| `DSafeQueueListener` | async mode 用。safe shutdown と queue drain を考慮した listener | `logging.handlers.QueueListener` | `_async.py` |
| `DSafeFormatter` | カスタムレベル名・コンテキストサフィックス出力対応フォーマッタ | `logging.Formatter` | `_formatter.py` |
| `DiagnosticFormatter` | `DSafeFormatter` + `f_locals` 展開（`{prefix}_DIAGNOSE=1` 時） | `DSafeFormatter` | `_formatter.py` |
| `StructuredFormatter` | JSON Lines 形式出力。contextualize はトップレベルフィールド化 | `logging.Formatter` | `_formatter.py` |
| `DiagnosticStructuredFormatter` | `StructuredFormatter` + `f_locals` を `locals` フィールドとしてJSON出力 | `StructuredFormatter` | `_formatter.py` |
| `FileSink` | writer-side file ownership の中心抽象。append / switch / reopen / maintenance 起動を担当 | - | `_sink.py` |
| `ConsoleSink` | writer-side stderr 出力の低位抽象 | - | `_sink.py` |
| `SinkGroup` | route ごとの writer-side sink graph を束ねる構造 | `dataclass` | `_sink.py` |
| `ColorStreamHandler` | ANSI カラー付き stderr 出力 | `logging.StreamHandler` | `_color.py` |
| `RoutingStrategy` (ABC) | ファイル名サフィックス決定の抽象基底 | `abc.ABC` | `_routing.py` |
| `NoneStrategy` | ルーティングなし | `RoutingStrategy` | `_routing.py` |
| `DailyStrategy` | 日次ルーティング | `RoutingStrategy` | `_routing.py` |
| `HourlyStrategy` | 時間次ルーティング | `RoutingStrategy` | `_routing.py` |
| `MinIntervalStrategy` | N分間隔ルーティング | `RoutingStrategy` | `_routing.py` |
| `StartupIntervalStrategy` | 起動時刻ベースルーティング | `RoutingStrategy` | `_routing.py` |
| `SizeStrategy` | ファイルサイズベースルーティング | `RoutingStrategy` | `_routing.py` |
| `CountStrategy` | 行数ベースルーティング | `RoutingStrategy` | `_routing.py` |
| `CyclicWeekdayStrategy` | 曜日サイクリック | `RoutingStrategy` | `_routing.py` |
| `CyclicMonthStrategy` | 月サイクリック | `RoutingStrategy` | `_routing.py` |
| `PurgeWorker` | 非同期ファイル削除（世代管理） | `threading.Thread` | `_purge.py` |
| `ArchiveWorker` | 非同期 ZIP アーカイブ化（`archive_mode=True` 時） | `threading.Thread` | `_purge.py` |
| `HashWorker` | Fire-and-Forget SHA-256 ハッシュ生成（サイドカー・マニフェスト書き込み） | `threading.Thread` | `_integrity.py` |
| `Transport` (ABC) | Capture → Sink 間のイベント転送抽象（v20 新規） | `abc.ABC` | `_transport.py` |
| `DirectTransport` | sync mode 用。Handler へ直接委譲（v20 新規） | `Transport` | `_transport.py` |
| `QueueTransport` | async mode 用。Queue 経由の転送（v20 新規） | `Transport` | `_transport.py` |
| `TransportFactory` | single-process の `is_async` から適切な `Transport` 実装を生成する | - | `_transport.py` |
| `ResolvedConfig` | 3層マージ後の確定設定を保持し、`PipelineBuilder` に渡す内部データクラス | `dataclass` | `_pipeline.py` |
| `PipelineBuilder` | Handler / Formatter / Transport を組み立て、内部パイプラインを構築する | - | `_pipeline.py` |
| `Pipeline` | Capture / Transport / Sink の起動・停止・writer-side file sink reopen を束ねる内部ファサード | - | `_pipeline.py` |
| `ContextManager` | `contextvars.ContextVar[MappingProxyType]` ラッパー（v20: FrozenContext） | - | `_context.py` |
| `EnvParser` | 環境変数パース（{prefix}_LEVEL / _MODULES / _CONSOLE / _COLOR / _DIAGNOSE / _CONFIG / _HASH / _MANIFEST / _IPC_LOG_TIMEOUT） | - | `_env_parser.py` |
| `IniLoader` | INIファイル読み込みとFail-Fastバリデーション | - | `_ini_loader.py` |
| `DictLoader` | 辞書ベース設定の読み込みとFail-Fastバリデーション（IniLoader と同一の型変換ルールを委譲適用） | - | `_ini_loader.py` |
| `PathValidator` | Fail-Fast パーミッション・ディスク容量検証 | - | `_validator.py` |
| `BootstrapContext` | Writer runtime に attach するための opaque かつ picklable な bootstrap object | `dataclass` | `_mp_protocol.py` |
| `LogEvent` | client → Writer の通常ログ hand-off payload | `TypedDict` | `_mp_protocol.py` |
| `ControlRequest` | client → Writer の control plane request | `TypedDict` | `_mp_protocol.py` |
| `ControlAck` | Writer → client の control plane ACK | `TypedDict` | `_mp_protocol.py` |
| `MPClientTransport` | attached client process から Writer へ hand-off する multiprocess transport | - | `_mp_attach.py` |
| `WriterRuntime` | log plane / control plane / sink 群 / active client registry を所有する Writer 実行体 | - | `_mp_runtime.py` |

### 2.1a. v22i における Sink の中心性

v22i では、single-process 版の `AppendOnlyFileHandler` を維持しつつも、**Writer/runtime 側の正式な中心抽象は `FileSink` / `ConsoleSink` / `SinkGroup`** とする。

- `logging` 互換は Capture 層の責務
- `Transport` は hand-off の責務
- `routing` / `hash` / `manifest` / `archive` / `purge` / `reopen` は Sink/Writer 側の責務

したがって multiprocess 版では、`WriterRuntime` が `SinkGroup` を所有し、`LogRecord` の logger 階層評価や level 判定を再実行せず、route ごとに sink graph へ dispatch する。`AppendOnlyFileHandler` は single-process 互換のために残るが、Writer/runtime 全体の中心抽象ではない。

### 2.1b. v18 追加の共有状態

| 変数 | 用途 | 推奨型 |
|------|------|--------|
| `_lifecycle_lock` | Configure / GetLogger / register_level / shutdown の状態遷移保護 | `threading.RLock` |
| `_workers_lock` | active worker 集合の add/discard/snapshot | `threading.Lock` |
| `_active_workers` | `HashWorker` / `PurgeWorker` / `ArchiveWorker` の追跡 | `set[threading.Thread]` |
| `_active_pipeline` | 現在有効な Capture / Transport / Sink パイプライン参照 | `Pipeline | None` |
| `_atexit_registered` | shutdown 登録の重複防止 | `bool` |
| `_registry_lock` | lock registry（`_manifest_locks`/`_family_locks`）の遅延初期化保護専用。v20 追加 | `threading.Lock` |
| `_manifest_locks` | manifest path ごとの直列化 lock | `dict[Path, threading.Lock]` |
| `_family_locks` | `directory + pg_name` ごとの maintenance lock | `dict[tuple[Path, str], threading.Lock]` |
| `_diagnose_enabled` | 診断モードの有効/無効フラグ。`_constants.py` に配置（v20: 性能最適化）。 | `bool` |
| `_resolved_sensitive_keywords` | 解決済みセンシティブキーワード。`ConfigureLogger` で確定。v18 追加 | `frozenset[str]` |
| `_mp_lifecycle_lock` | multiprocess attach/configure/shutdown の process-local 状態遷移保護 | `threading.RLock` |
| `_mp_runtime_state` | 現在 process の multiprocess attach/configure 状態（attach 済み `ctx`、`client_id`、client transport 群を含む） | `MPProcessState | None` |

> v18: `_active_workers` は `list` ではなく `set` を用いる。これにより重複登録を防ぎ、終了競合時の unregister は `discard()` で安全に扱う。
>
> **lock acquisition order**: `_lifecycle_lock` → `_workers_lock` → `_family_lock` → `_manifest_lock`。逆順取得は禁止し、いずれの lock 保持中も `join()`、queue drain、重い I/O を行わない。
>
> `_mp_lifecycle_lock` は上記順序の外側にある process-local state guard であり、`_lifecycle_lock` と同時取得しない。multiprocess 側が single-process 共通の設定マージや registry 参照を再利用する場合も、`_mp_lifecycle_lock` を解放してから実行する。
>
> `_registry_lock` は上記順序の外側に位置する独立の lock であり、`_manifest_locks`/`_family_locks` の registry lookup のみに使用する。`_registry_lock` 保持中に他の lock を取得してはならない。
>
> **v0.2.0 性能向上対策**:
> `_diagnose_enabled` は `_async.py` 内部（10万回オーダーで呼ばれるホットパス）で参照される。マルチスレッド環境下での Python インポートロック競合を回避するため、本フラグは `_constants.py` に配置し、ホットパス内でのローカルインポートを排除した。🤟🔥

### 2.1c. v18 追加の内部 helper

```python
import contextvars
import threading

_manifest_locks: dict[Path, threading.Lock] = {}
_family_locks: dict[tuple[Path, str], threading.Lock] = {}


def _run_in_empty_context(target, /, *args, **kwargs):
    """内部 thread を空 Context で開始するための共通 helper。"""
    return contextvars.Context().run(target, *args, **kwargs)


def _snapshot_context() -> MappingProxyType | None:
    """producer thread 時点の contextualize 情報を取得する。
    v20: FrozenContext (MappingProxyType) は immutable のため、コピー不要。
    参照をそのまま返す O(1) 操作。"""
    ctx = _log_context.get()
    if not ctx:
        return None
    return ctx  # MappingProxyType は immutable なので dict(ctx) のコピーは不要


def _snapshot_diagnostic_frames(
    exc_info,
    *,
    sensitive_keywords: frozenset[str],
) -> tuple[str, list[dict[str, object]]]:
    """producer thread で traceback 文字列と locals snapshot を生成する。"""
    formatter = DiagnosticFormatter(sensitive_keywords=sensitive_keywords)
    exc_text = formatter.formatException(exc_info)
    frames = _extract_masked_locals(exc_info[2], sensitive_keywords=sensitive_keywords)
    return exc_text, frames


def _extract_masked_locals(
    tb,
    *,
    sensitive_keywords: frozenset[str],
) -> list[dict[str, object]]:
    """traceback からマスク済み locals snapshot を抽出する。"""
    frames: list[dict[str, object]] = []
    while tb is not None:
        frame = tb.tb_frame
        variables: dict[str, str] = {}
        for key, value in frame.f_locals.items():
            lower = key.lower()
            if any(kw in lower for kw in sensitive_keywords):
                variables[key] = '*** MASKED ***'
                continue
            try:
                repr_value = repr(value)
                if len(repr_value) > 200:
                    repr_value = repr_value[:200] + '...'
                variables[key] = repr_value
            except Exception:
                variables[key] = '<repr failed>'
        frames.append({
            'frame': f'{frame.f_code.co_filename}:{tb.tb_lineno} in {frame.f_code.co_name}',
            'variables': variables,
        })
        tb = tb.tb_next
    return frames


def _get_manifest_lock(path: Path) -> threading.Lock:
    """manifest path 単位で共有する lock を返す。
    v20: _lifecycle_lock ではなく _registry_lock を使用し、デッドロックを防止する。"""
    resolved = path.resolve()
    with _registry_lock:
        lock = _manifest_locks.get(resolved)
        if lock is None:
            lock = threading.Lock()
            _manifest_locks[resolved] = lock
        return lock


def _get_family_lock(directory: Path, pg_name: str) -> threading.Lock:
    """同一 family の purge/archive/hash 競合を避ける lock を返す。
    v20: _lifecycle_lock ではなく _registry_lock を使用し、デッドロックを防止する。"""
    key = (directory.resolve(), pg_name)
    with _registry_lock:
        lock = _family_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _family_locks[key] = lock
        return lock
```

- `_snapshot_context()` は queue hand-off 時の immutable snapshot を作るため、listener 側で live `ContextVar` を参照しない
- `_snapshot_diagnostic_frames()` は `diagnose=True` かつ `exc_info` ありのケースでのみ呼ぶ
- manifest lock / family lock の registry lookup / 遅延生成は `_registry_lock` で保護する。取得後の実 I/O は各 lock のみで直列化し、`_lifecycle_lock` 保持中に重い I/O や join を行わない
- lock table はモジュールレベル shared state として保持し、`_shutdown()` とテスト fixture では必要に応じて clear する

### 2.2. クラス図（テキスト表現）

```
logging.Logger
  └── DSafeLogger
        ├── contextualize(**kwargs) -> ContextManager
        └── _context_var: contextvars.ContextVar[MappingProxyType]  # v20: FrozenContext

logging.FileHandler
  └── AppendOnlyFileHandler
        ├── _strategy: RoutingStrategy
        ├── _current_path: Path
        ├── _backup_count: int
        ├── _archive_mode: bool
        ├── _enable_hash: bool
        ├── _manifest_path: Path | None
        └── emit(record) -> None

logging.Formatter
  ├── DSafeFormatter
  │     └── DiagnosticFormatter
  └── StructuredFormatter
        └── DiagnosticStructuredFormatter

logging.StreamHandler
  └── ColorStreamHandler
        ├── _color_map: dict[str, str]
        ├── _color_overrides: dict[str, str] | None   # v17: INI/辞書からのカラーオーバーライド
        └── emit(record) -> None

RoutingStrategy (ABC)
  ├── NoneStrategy
  ├── DailyStrategy
  ├── HourlyStrategy
  ├── MinIntervalStrategy
  ├── StartupIntervalStrategy
  ├── SizeStrategy
  ├── CountStrategy
  ├── CyclicWeekdayStrategy
  └── CyclicMonthStrategy

threading.Thread
  ├── PurgeWorker
  ├── ArchiveWorker
  └── HashWorker
        ├── _file_path: Path
        ├── _manifest_path: Path | None
        └── run() -> None

IniLoader          ← INIファイル読み込みとバリデーション
DictLoader         ← 辞書ベース設定の読み込みとバリデーション（v16追加）
ResolvedConfig     ← v20: 3層マージ後の確定設定 dataclass
PipelineBuilder    ← v20: ResolvedConfig から Pipeline を構築
Pipeline           ← v20: start/stop/get_root_handlers の内部ファサード

Transport (ABC)    ← v20: single-process Capture → Sink 間のイベント転送抽象
  ├── DirectTransport  ← sync mode: Handler へ直接委譲
  └── QueueTransport   ← async mode: Queue 経由の転送
TransportFactory   ← v20: is_async から Transport を生成
EnvParser          ← 環境変数パース（プレフィックスベース）
PathValidator      ← Fail-Fast 検証

BootstrapContext   ← Writer attach 用 bootstrap object
LogEvent           ← client → Writer の hand-off payload
ControlRequest     ← control plane request
ControlAck         ← control plane ack
MPClientTransport  ← process-local async queue + log plane hand-off
WriterRuntime      ← active client registry / log plane / control plane / sink 管理

_levels.py（ユーティリティモジュール）
  ├── register_level(name, value, abbreviation, color)
  ├── get_all_level_map() -> dict[str, str]
  ├── get_all_color_map(overrides=None) -> dict[str, str]   # v17: overrides 引数追加
  ├── get_valid_level_names() -> set[str]
  ├── get_valid_abbreviations() -> set[str]                  # v17: カラーパレットバリデーション用
  └── install_convenience_methods(logger_class)

_integrity.py（ユーティリティモジュール）
  ├── compute_sha256(file_path) -> str
  ├── write_sidecar(file_path) -> None
  └── append_manifest(file_path, manifest_path) -> None
```

---

## 3. 公開 API 詳細設計

### 3.1. `dsafelogger.ConfigureLogger`（single-process 版）

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
) -> None:
```

v22i でも single-process 版の公開契約は維持する。multiprocess 専用の `ctx` / attach / control plane は `dsafelogger.mp` namespace に分離し、single-process 版へは持ち込まない。

#### 処理フロー（3層設定管理パイプライン）

```
1. `_lifecycle_lock` 取得 + 冪等性チェック（5状態管理）
   ├── _configure_state == 'explicit'      → 即座に return（No-Op）
   ├── _configure_state == 'auto'          → 既存 `_active_pipeline` を停止・クリーンアップしてから再初期化
   ├── _configure_state == 'unconfigured'  → フル初期化を実行
   ├── _configure_state == 'configuring'   → 同一 thread 再入のみ No-Op / 既存 logger 返却。別 thread は lock 待機後に再評価
   └── _configure_state == 'shutting_down' → 新規初期化を拒否（No-Op または RuntimeError）し、状態破壊を防止

1a. `_configure_state = 'configuring'` へ遷移（step 14 完了まで `_lifecycle_lock` を保持）
1b. [`_configure_state == 'auto'`] 旧 `Pipeline` を detach → stop → close してから再構成へ進む

2. 引数バリデーション
   ├── routing_mode / default_level / interval / suffix_digits / env_prefix / config_file / config_dict を検証
   ├── structured=True と fmt / file_fmt / console_fmt の排他を検証
   ├── config_file と config_dict の同時指定を禁止
   ├── enable_hash=False + manifest_path 指定時は `ValueError`
   └── routing_mode='none' + enable_hash=True は `ValueError`

3. 第2層設定ソースの解決（config_file / config_dict / {env_prefix}_CONFIG）
4. 第2層: IniLoader または DictLoader による読み込みとマージ
5. 第1層: `{prefix}_LEVEL` / `_MODULES` / `_DIAGNOSE` / `_CONSOLE` / `_COLOR` / `_HASH` / `_MANIFEST` の適用
6. マージ済み設定の最終バリデーション
   ├── archive_mode=True + backup_count=0 は `ValueError`
   ├── size/count + max_count=None + backup_count>0 は `ValueError`
   ├── cyclic 系 + enable_hash=True は `ValueError`
   └── `env_prefix` 自体は INI / config_dict / 環境変数から変更させない

7. Fail-Fast パーミッション検証
   ├── `log_path`
   ├── module-specific path
   └── `manifest_path`

8. `logging.setLoggerClass(DSafeLogger)` と便利メソッドの適用
9. センシティブキーワードの最終解決
10. `ResolvedConfig` 構築
11. `PipelineBuilder.build(resolved_config)` で single-process `Pipeline` を構築
12. `pipeline.start()` → root / module logger へ attach
13. `is_async=True` の場合のみ `atexit.register(_shutdown)`
14. `_configure_state = 'auto'` または `'explicit'` を確定
```

#### `ResolvedConfig` と `PipelineBuilder` への委譲境界

single-process 版では従来通り、`__init__.py` は状態管理・3層マージ・Fail-Fast バリデーション・`ResolvedConfig` 生成までを担い、Sink / Formatter / Transport の具象生成は `_pipeline.py` に委譲する。

```python
@dataclass(frozen=True)
class ResolvedConfig:
    default_level: str
    log_path: Path
    pg_name: str
    is_async: bool
    console_out: bool
    structured: bool
    fmt: str | logging.Formatter | None
    file_fmt: str | logging.Formatter | None
    console_fmt: str | logging.Formatter | None
    datefmt: str | None
    routing_strategy: RoutingStrategy
    backup_count: int
    archive_mode: bool
    enable_hash: bool
    manifest_path: Path | None
    diagnose: bool
    sensitive_keywords: frozenset[str]
    color_overrides: dict[str, str] | None
    module_configs: dict[str, dict[str, object]]
```

```python
class PipelineBuilder:
    def build(self, resolved_config: ResolvedConfig) -> Pipeline:
        # 1. file / console 用 Formatter を解決
        # 2. root sink handler 群を生成
        # 3. root transport を生成（DirectTransport or QueueTransport）
        # 4. module-specific path ごとに sink handler + transport を生成
        # 5. Pipeline を返す
        ...


class Pipeline:
    def __init__(self, transport: Transport, module_transports: dict[str, Transport]) -> None:
        self.transport = transport
        self.module_transports = module_transports

    def start(self) -> None:
        ...

    def stop(self, timeout: float) -> bool:
        ...

    def get_root_handlers(self) -> list[logging.Handler]:
        ...

    def get_module_handler(self, mod_name: str) -> logging.Handler | None:
        ...

    def reopen_file_sinks(self) -> int:
        """writer-side file sink を重複排除して reopen し、対象数を返す。"""
        ...
```

#### lock 保持区間の原則

- `ConfigureLogger()` は step 14 完了まで `_lifecycle_lock` を保持する
- `_shutdown()` は「lock 下で状態更新・参照退避」→「lock 外で `Pipeline.stop()` / worker join / handler close」→「lock 下で最終確定」の 3 phase とする
- `_workers_lock` 保持中に `join()` や `close()` を行わない
- heavy な diagnose snapshot は lock 外で行う
- auto → explicit 再初期化では旧 `Pipeline.stop(timeout)` を必須とする

#### バリデーション規則（single-process）

| 引数 | 検証内容 | 不正時の挙動 |
|------|----------|-------------|
| `default_level` | `get_valid_level_names()` に含まれるレベル名 | `ValueError` |
| `log_path` | パスとして有効な文字列 | ディレクトリ不在時は自動作成、書き込み不可は `PermissionError` |
| `pg_name` | OS 禁止文字を `_` に置換 | サイレント置換 |
| `env_prefix` | 空でない文字列 | `ValueError` |
| `config_file` | `None` またはファイルパス文字列 | 不在時 `FileNotFoundError` |
| `config_dict` | `None` または `dict[str, dict[str, str]]` | 型不正時 `TypeError` |
| `routing_mode` | `none/daily/hourly/min_interval/startup_interval/size/count/cyclic_weekday/cyclic_month` | `ValueError` |
| `interval` | routing ごとの契約に適合 | `ValueError` |
| `max_count` | `None` または正整数 | `ValueError` |
| `max_bytes` | 0 または正整数 | `ValueError` |
| `max_lines` | 0 または正整数 | `ValueError` |
| `suffix_digits` | 1 以上の整数 | `ValueError` |
| `structured` + `fmt` / `file_fmt` / `console_fmt` | 同時指定禁止 | `ValueError` |
| `manifest_path` | `None` またはファイルパス文字列 | 書き込み不可時 `PermissionError` |
| `sens_kws_replace=True` + `sens_kws` 空 | 完全置換なのにキーワードなし | `ValueError` |

#### v23j: merge 後正規化・無効組み合わせ検証

`ConfigureLogger()` は Layer 3 引数、Layer 2 INI/config_dict、Layer 1 環境変数を merge した後、最終的な root file sink と module-specific file sink に同一の検証を適用する。検証は `src/dsafelogger/_config_validation.py` に集約し、single-process と multiprocess の両方から利用する。

```python
def is_cyclic_config(routing_mode: str, max_count: int | None) -> bool:
    return (
        routing_mode in ('cyclic_weekday', 'cyclic_month')
        or (routing_mode in ('size', 'count') and max_count is not None)
    )


def is_overflow_error_config(routing_mode: str, max_count: int | None) -> bool:
    return routing_mode in ('size', 'count') and max_count is None


def is_generation_managed_config(routing_mode: str, max_count: int | None) -> bool:
    return routing_mode in ('daily', 'hourly', 'min_interval', 'startup_interval')
```

以下は指定元に関係なく `ValueError` とする。

```text
routing_mode='none' + enable_hash=True
routing_mode='none' + backup_count > 0
routing_mode='none' + archive_mode=True
cyclic 系 + enable_hash=True
cyclic 系 + backup_count > 0
cyclic 系 + archive_mode=True
size/count + max_count=None + backup_count > 0
size/count + max_count=None + archive_mode=True
archive_mode=True + backup_count=0
manifest_path 指定 + enable_hash=False
structured=True + fmt/file_fmt/console_fmt
未登録 default_level / module level
backup_count < 0
max_count < 1
suffix_digits < 1
startup_interval interval < 1
```

Python API 直指定の bool 引数は `bool` 型のみを受け付ける。INI/config_dict の文字列 bool 変換は loader の責務であり、API 層では `'false'` のような非空文字列を truthy として扱わない。

### 3.2. `dsafelogger.GetLogger`（single-process 版）

```python
def GetLogger(name: str = '') -> DSafeLogger:
```

- `logging.getLogger(name)` のラッパー
- `ConfigureLogger` 完了後は `DSafeLogger` を返す
- 未初期化時は **auto-fire** を維持し、デフォルト引数による `ConfigureLogger()` を内部実行する
- `_configure_state == 'configuring'` では、同一 thread 再入のみ短絡し、別 thread は lock 解放待ちを行う
- `_configure_state == 'shutting_down'` では新規 auto-fire を行わず既存 logger 返却に限定する

### 3.3. `dsafelogger.ReopenLogFiles`（single-process 版）

```python
def ReopenLogFiles() -> None:
    """外部 log rotation 後に writer-side の file sink を reopen する。"""
```

- `ConfigureLogger()` 完了後のみ使用可能
- writer-side の file sink のいずれかが `routing_mode != 'none'` の場合は **`ValueError`**
- writer-side file sink が 1 つも存在しない場合は **`RuntimeError`**
- `_lifecycle_lock` 下で `reopened = _active_pipeline.reopen_file_sinks()` を呼ぶ
- `reopened == 0` を API 層で `RuntimeError` に変換する
- signal handler 自動登録は行わない
- `AppendOnlyFileHandler.reopen()` の自己排他契約に依存し、外側で追加 lock は取らない

### 3.4. `dsafelogger.mp.ConfigureLogger`（multiprocess 版）

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
) -> BootstrapContext:
```

#### 処理フロー

```
1. process-local multiprocess state を検査
   ├── 既に同 process で mp.ConfigureLogger 済み → RuntimeError
   └── single-process runtime と同居しないことを確認

2. single-process 版と同一の 3 層設定マージを実行
   ├── 共通引数バリデーション
   ├── IniLoader / DictLoader / EnvParser の適用
   └── writer-side resolved config raw dict を構築

3. multiprocess 固有バリデーション
   ├── worker_model が `process/pool/executor` のいずれか
   ├── mp_context の正規化
   ├── 以後に生成する log/control queue と Pipe reply path の共通 context を確定
   ├── ipc_log_timeout の解決（env 優先）
   ├── ipc_log_timeout <= 0 → ValueError
   └── MAX_IPC_LOG_TIMEOUT_SECONDS 超過時は stderr warning + clip

4. Writer runtime 用 endpoint 群を生成
   ├── bounded log plane queue
   ├── bounded control request queue
   ├── 呼び出し元 process 用 bootstrap ready reply endpoint 情報
   └── session_id / registry_hash / resolved_config_digest を確定

5. Writer runtime を起動
   ├── writer-side sink graph を単独で構築
   ├── active client registry を空で開始
   ├── log plane loop / control plane loop を開始
   └── bootstrap ready まで待機

6. `BootstrapContext` を生成し、pickle round-trip を即時検証
7. Writer bootstrap ready ACK を受理し、Writer 側が返す `protocol_version` / registry hash を caller 側と照合
8. 呼び出し元 process 自身に対して `AttachCurrentProcess(ctx)` 相当を適用
9. process-local attach state を記録し、`ctx` を返す
```

#### v22i 固有の要件

- `ctx` は opaque だが picklable でなければならない
- `ctx` に `Event` / `Lock` / `Condition` 等の非 picklable 同期オブジェクトを含めない
- Writer runtime は file sink 群を唯一所有する
- `is_async=True` は process-local async queue を追加するだけであり、Writer 側 file sink ownership を変えない
- `_mp_lifecycle_lock` は process-local state 判定/確定専用であり、`_lifecycle_lock` とネストさせず、control plane ACK 待機にもまたがらせない
- `mp_context` が指定された場合、`ConfigureLogger()` / `AttachCurrentProcess()` / control plane helper が生成する Queue / Pipe はその正規化結果を一貫利用する
- multiprocess 版の `fmt` / `file_fmt` / `console_fmt` は single-process 版と同じ型面（`str | logging.Formatter | None`）を持つ
- process 境界で freeze 対象として受理する exact instance type は `logging.Formatter`, `DSafeFormatter`, `DiagnosticFormatter`, `StructuredFormatter`, `DiagnosticStructuredFormatter` に限る
- freeze 形式は `kind` と picklable な constructor args のみからなる `FormatterSpec` とし、Writer 側で同値再構築する
- `logging.Formatter` の custom subclass を含む上記 allow-list 外の custom formatter instance、または picklable spec へ還元できない state を持つ instance は `TypeError` とする
- Writer bootstrap ready ACK 時にも `protocol_version` / registry hash を照合し、mismatch は Fail-Fast とする

### 3.5. `dsafelogger.mp.AttachCurrentProcess`

```python
def AttachCurrentProcess(ctx: BootstrapContext) -> None:
```

- 現在 process を既存 Writer runtime に参加させる process-local 操作
- `ctx` 検証、reply endpoint 準備、ATTACH request 送信、ACK 待機、process-local attach state 更新、`logging.setLoggerClass()` の再適用を行う
- same `ctx` への再 attach は no-op（ただし process-local thread / transport の再生成が必要な場合はそれだけ実行する）
- fork 継承で既に同一 Writer session へ attach 済みの場合でも、child は親の `client_id` を再利用せず、child 専用の `client_id` を生成して Writer active registry へ再登録する
- 別 `ctx` への再 attach は `RuntimeError`

### 3.5a. `dsafelogger.mp.DetachCurrentProcess`

```python
def DetachCurrentProcess() -> None:
```

- 現在 process の `client_id` に対する `DETACH` control request を Writer へ送り、ACK 成功後に process-local transport / handler / state を破棄する
- 未 attach 時は no-op として扱ってよい
- `_mp_shutdown()` は Writer thread join より前に、この API と等価な detach 手順で main process 自身を active registry から外す

### 3.6. `dsafelogger.mp.GetLogger`

```python
def GetLogger(name: str = '') -> DSafeLogger:
```

- `logging.getLogger(name)` の multiprocess 版ラッパー
- **auto-fire しない**
- 現在 process が attach 済みでない場合は `RuntimeError`
- attach 完了後は `GetLogger()` / `logging.getLogger()` / サードパーティ logger いずれも Writer runtime へ集約される

### 3.7. `dsafelogger.mp.GetWorkerInitializer`

```python
def GetWorkerInitializer(ctx: BootstrapContext) -> tuple[Callable[..., None], tuple]:
```

- `multiprocessing.Pool` / `ProcessPoolExecutor` の `initializer` / `initargs` へそのまま渡せる `(init_fn, init_args)` を返す
- `init_fn(*init_args)` は `AttachCurrentProcess(ctx)` と等価
- `ctx` の pickle 可否はこの関数ではなく `mp.ConfigureLogger()` で Fail-Fast 済みであることを前提とする

### 3.8. `dsafelogger.mp.ReopenLogFiles`

```python
def ReopenLogFiles() -> None:
```

- attached client process から Writer runtime へ `REOPEN` control request を送り、ACK を待つ同期 API
- writer-side file sink のいずれかが `routing_mode != 'none'` の場合は **`ValueError`**
- Writer runtime 不在または attach 不正時は **`RuntimeError`**
- ACK timeout は **`TimeoutError`**
- ACK wait timeout は `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` 固定とし、公開引数は持たない
- reopen の直列化責務は Writer 側に置く

### 3.9. DSafeLogger.contextualize

```python
@contextmanager
def contextualize(self, **kwargs) -> Generator[None, None, None]:
```

#### 内部動作

```python
import contextvars

# モジュールレベルで定義（_context.py と共有）
from types import MappingProxyType

_EMPTY_CONTEXT: MappingProxyType = MappingProxyType({})

_log_context: contextvars.ContextVar[MappingProxyType] = contextvars.ContextVar(
    'dsafelogger_context', default=_EMPTY_CONTEXT
)

class DSafeLogger(logging.Logger):

    @contextmanager
    def contextualize(self, **kwargs):
        # v22h: Fail-Fast。代表的な mutable 値は拒否する。
        for key, value in kwargs.items():
            if isinstance(value, (list, dict, set, bytearray)):
                raise TypeError(
                    f"contextualize() value for {key!r} must be immutable, "
                    f"got {type(value).__name__}"
                )
        # v20: FrozenContext — MappingProxyType は immutable なので、
        # 更新時は 1 回だけ dict へ展開して新しい MappingProxyType を生成する。
        # No-Copy 化の対象は async mode の snapshot hand-off であり、
        # contextualize() の write path 自体は O(n) コピーを伴う。
        current = dict(_log_context.get())  # MappingProxyType -> dict へ展開
        current.update(kwargs)
        frozen = MappingProxyType(current)   # 新しい FrozenContext を生成
        token = _log_context.set(frozen)
        try:
            yield
        finally:
            _log_context.reset(token)
```

`contextvars.ContextVar` を用いることで、マルチスレッドだけでなく `asyncio` のタスク間でも完全に独立したコンテキストが保証される。`Token` による `reset()` で、`with` ブロック脱出時にコンテキストが正確に巻き戻される。

#### v22h 追加: mutable 値 Fail-Fast

- `contextualize()` に渡す値は `str`, `int`, `float`, `tuple` 等の immutable 値を前提とする
- `list`, `dict`, `set`, `bytearray` などの代表的 mutable 値は入口で `TypeError` を送出する
- これは `MappingProxyType` の浅い不変性だけでは防げない、値オブジェクトの事後変更漏洩を防ぐための Fail-Fast 契約である

> **設計判断: Formatter での直接取得**
> 旧設計では `DSafeLogger.makeRecord` 内でコンテキストを `LogRecord` に注入していたが、
> この方式では `SQLAlchemy` や `Django` 等のサードパーティライブラリが `logging.getLogger` で
> 生成した標準 Logger を経由したログにはコンテキストが付与されない問題があった。
> v18 では sync mode では **各 Formatter の `format` メソッド内で直接 `_log_context.get()` を呼び出す**設計を維持しつつ、
> async mode では producer thread 側で `LogRecord` に付与された `_ds_context` を優先使用する。
> `makeRecord` のオーバーライドは廃止する。

---

## 4. Formatter 詳細設計

### 4.1. カスタムレベル名マッピング

| 標準レベル | 数値 | D-SafeLogger 略称 |
|-----------|------|------------------|
| DEBUG | 10 | `DBG` |
| INFO | 20 | `INF` |
| WARNING | 30 | `WAR` |
| ERROR | 40 | `ERR` |
| CRITICAL | 50 | `CRI` |

実装: `Formatter.format()` メソッド内で `LEVEL_MAP` 辞書によるルックアップで略称変換を行う。`logging.addLevelName()` によるグローバルなレベル名上書きは使用しない（§9.8 準拠）。

### 4.2. DSafeFormatter

```python
import threading
from dsafelogger._context import _log_context
from dsafelogger._levels import get_all_level_map


class _DisplayRecordProxy(logging.LogRecord):
    """共有 LogRecord を変更せず、render 時だけ表示用フィールドを上書きする。

    `logging.LogRecord` を継承することで `getMessage()` 等のクラスメソッドが
    MRO 経由で解決される。`object` を継承すると `getMessage()` が見つからず
    `AttributeError` になるため LogRecord 継承が必須。

    `__new__` で元 record の `__dict__` をコピーし overrides を適用する。
    `LogRecord.__init__` の呼び出しは不要なため `__init__` は空にしてスキップする。
    """

    def __new__(
        cls,
        original: logging.LogRecord,
        overrides: dict[str, object],
    ) -> '_DisplayRecordProxy':
        obj = object.__new__(cls)
        obj.__dict__.update(original.__dict__)
        obj.__dict__.update(overrides)
        return obj

    def __init__(
        self,
        original: logging.LogRecord,
        overrides: dict[str, object],
    ) -> None:
        pass  # __new__ で完結; LogRecord.__init__ はスキップ


def _make_proxy_tls() -> threading.local:
    """スレッドローカル _DisplayRecordProxy 再利用スロットを生成する。

    クラス変数として使用することで、クラスごとに独立した threading.local
    インスタンス（= TLS スロット）を保持できる。
    `DSafeFormatter._proxy_tls` と `ColorStreamHandler._proxy_tls` を
    それぞれ別の呼び出しで生成することで self-reference corruption を防ぐ。
    """
    return threading.local()


class DSafeFormatter(logging.Formatter):
    DEFAULT_FMT = '%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s'
    DEFAULT_DATEFMT = '%Y-%m-%d %H:%M:%S'

    # クラス変数はビルトインのみ保持（後方互換・フォールバック用）
    _BUILTIN_LEVEL_MAP = {
        'DEBUG': 'DBG', 'INFO': 'INF', 'WARNING': 'WAR',
        'ERROR': 'ERR', 'CRITICAL': 'CRI',
    }
    # スレッドローカル proxy 再利用（ColorStreamHandler とは別スロット）
    _proxy_tls: threading.local = _make_proxy_tls()

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: str = '%',
    ) -> None:
        # % style のみ DEFAULT_FMT を適用。{} / $ style は fmt=None を渡して
        # logging が各 style のデフォルト（'{message}' / '${message}'）を使う。
        super().__init__(
            fmt=fmt or (self.DEFAULT_FMT if style == '%' else None),
            datefmt=datefmt or self.DEFAULT_DATEFMT,
            style=style,
        )
        # インスタンス変数として統合マップを構築（ビルトイン + カスタムレベル）
        self.LEVEL_MAP = get_all_level_map()

    def format(self, record: logging.LogRecord) -> str:
        # v21: shared LogRecord は変更しない。略称は render 時だけ上書きする。
        # スレッドローカル proxy を再利用することで per-call アロケーションをなくし、
        # 高スループット・多スレッド環境での GC 圧力を排除する。
        abbr = self.LEVEL_MAP.get(record.levelname, record.levelname)
        proxy = getattr(self._proxy_tls, 'instance', None)
        if proxy is None:
            proxy = object.__new__(_DisplayRecordProxy)
            self._proxy_tls.instance = proxy
        proxy.__dict__.clear()
        proxy.__dict__.update(record.__dict__)
        proxy.__dict__['levelname'] = abbr
        result = super().format(proxy)

        # async mode では _ds_context が付与済みの場合はそれを authoritative として使用。
        # _ds_context 属性が存在しない場合（Transport を経由しない直接呼び出し）のみ
        # get_context() にフォールバックする。空の MappingProxyType でも snapshot として扱う。
        if hasattr(record, '_ds_context'):
            ctx = record._ds_context
        else:
            ctx = _log_context.get()
        if ctx:
            suffix = ' [' + ' '.join(f'{k}:{v}' for k, v in ctx.items()) + ']'
            result += suffix

        return result
```

#### 出力例

```
2026-03-28 14:30:05.123 [INF][myapp.py:42:process] Processing started [task_id:42 worker:db_sync]
2026-03-28 14:30:05.456 [ERR][db.py:128:connect] Connection failed
```

> **v21 実装方針**: `_DisplayRecordProxy` は `logging.LogRecord` を継承し、`__new__` で元 record の `__dict__` をフルコピーして overrides を適用する。`DSafeFormatter` と `ColorStreamHandler` はクラスレベルの TLS（`threading.local`）を用いてスレッドごとに proxy を 1 個だけ保持し、呼び出し毎に `clear()` + `update()` でインプレース更新する。これにより per-call アロケーションがなく GC 圧力を排除しつつ、共有 `LogRecord` を変更せず `%` / `{}` / `$` 全 style で同一の表示意味論が保証される。

### 4.3. DiagnosticFormatter（f_locals 展開）

> **v15 変更**: `DSafeFormatter` を継承しているため、`__init__` 経由で `self.LEVEL_MAP = get_all_level_map()` が自動的に適用される。
> **v16 変更**: `_SENSITIVE_KEYWORDS` をクラス変数（frozenset）からインスタンス変数に変更。`__init__` で `sensitive_keywords` パラメータを受け取り、`ConfigureLogger` が解決した `sens_kws` / `sens_kws_replace` の結果を注入できるようにした。`_is_sensitive` はクラスメソッドからインスタンスメソッドに変更。

```python
class DiagnosticFormatter(DSafeFormatter):
    # ビルトインセンシティブキーワード（12語、v16で統一）
    _BUILTIN_SENSITIVE_KEYWORDS = frozenset({
        'pass', 'password', 'passwd', 'secret', 'token',
        'key', 'apikey', 'api_key', 'auth', 'credential',
        'private', 'cert',
    })

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        sensitive_keywords: frozenset[str] | None = None,
    ):
        super().__init__(fmt=fmt, datefmt=datefmt)
        # v16: ConfigureLogger が解決済みのキーワードセットを注入する。
        # None の場合はビルトインをフォールバックとして使用。
        self._sensitive_keywords: frozenset[str] = (
            sensitive_keywords
            if sensitive_keywords is not None
            else self._BUILTIN_SENSITIVE_KEYWORDS
        )

    def _is_sensitive(self, var_name: str) -> bool:
        """変数名にセンシティブキーワードが含まれるか判定する（大文字小文字不問）。"""
        lower = var_name.lower()
        return any(kw in lower for kw in self._sensitive_keywords)

    def format(self, record: logging.LogRecord) -> str:
        record = copy.copy(record)

        if getattr(record, '_ds_exc_text', None) is not None:
            record.exc_text = record._ds_exc_text
            record.exc_info = None
        elif record.exc_info and record.thread != threading.get_ident():
            record.exc_text = logging.Formatter.formatException(self, record.exc_info)
            record.exc_info = None

        return super().format(record)

    def formatException(self, ei) -> str:
        """標準のトレースバックに加え、各フレームのローカル変数を展開する。
        センシティブな変数名（password, token, key 等）は値をマスキングする。"""
        standard_tb = super().formatException(ei)

        if ei[2] is None:
            return standard_tb

        lines = [standard_tb, '', '--- Local Variables ---']
        tb = ei[2]
        while tb is not None:
            frame = tb.tb_frame
            lines.append(f'  Frame: {frame.f_code.co_filename}:{tb.tb_lineno}'
                        f' in {frame.f_code.co_name}')
            for key, value in frame.f_locals.items():
                if self._is_sensitive(key):
                    lines.append(f'    {key} = *** MASKED ***')
                    continue
                try:
                    repr_value = repr(value)
                    if len(repr_value) > 200:
                        repr_value = repr_value[:200] + '...'
                    lines.append(f'    {key} = {repr_value}')
                except Exception:
                    lines.append(f'    {key} = <repr failed>')
            tb = tb.tb_next

        return '\n'.join(lines)
```

#### v18 追加: DiagnosticFormatter のフォールバック規則

- `_ds_exc_text` があれば、それを最優先で `record.exc_text` として使用する
- `_ds_exc_text` がなく、かつ `record.thread == threading.get_ident()` の同一 thread 条件を満たす場合のみ live `f_locals` 参照を許可する
- thread が異なる場合は `formatException()` を live locals 展開に使わず、standard traceback のみを扱う

### 4.4. StructuredFormatter（JSON Lines 出力）

```python
import json
import logging
from dsafelogger._context import _log_context
from dsafelogger._levels import get_all_level_map

class StructuredFormatter(logging.Formatter):
    """JSON Lines 形式で1行1JSONオブジェクトを出力するフォーマッタ。"""

    # クラス変数はビルトインのみ保持（後方互換・フォールバック用）
    _BUILTIN_LEVEL_MAP = {
        'DEBUG': 'DBG', 'INFO': 'INF', 'WARNING': 'WAR',
        'ERROR': 'ERR', 'CRITICAL': 'CRI',
    }

    def __init__(self, fmt: str | None = None, datefmt: str | None = None):
        super().__init__(fmt=fmt, datefmt=datefmt)
        # インスタンス変数として統合マップを構築（ビルトイン + カスタムレベル）
        self.LEVEL_MAP = get_all_level_map()
        self._STD_RECORD_KEYS = frozenset({
            'name', 'msg', 'args', 'levelname', 'levelno',
            'pathname', 'filename', 'module', 'exc_info', 'exc_text',
            'stack_info', 'lineno', 'funcName', 'created', 'msecs',
            'relativeCreated', 'thread', 'threadName',
            'processName', 'process', 'message', 'asctime',
            'taskName',  # Python 3.12+
        })

    def _merge_extra_fields(self, record: logging.LogRecord, data: dict[str, object]) -> None:
        """vendor-neutral な LogRecord extra 属性を JSON トップレベルへ載せる。
        標準 LogRecord キーと内部 `_ds_*` 属性は除外し、既存キーは上書きしない。"""
        for key, value in record.__dict__.items():
            if key in self._STD_RECORD_KEYS or key.startswith('_ds_'):
                continue
            if key not in data:
                data[key] = value

    def format(self, record: logging.LogRecord) -> str:
        data = {
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S') + f'.{int(record.msecs):03d}',
            'level': self.LEVEL_MAP.get(record.levelname, record.levelname),
            'logger': record.name,
            'file': record.filename,
            'line': record.lineno,
            'function': record.funcName,
            'message': record.getMessage(),
        }

        # async mode では producer 側 snapshot を優先し、なければ現行 context を参照
        if hasattr(record, '_ds_context'):
            ctx = record._ds_context
        else:
            ctx = _log_context.get()
        if ctx:
            data.update(ctx)

        self._merge_extra_fields(record, data)

        # 例外情報
        if record.exc_info and record.exc_info[0] is not None:
            data['exception'] = self.formatException(record.exc_info)

        return json.dumps(data, ensure_ascii=False, default=str)
```

### 4.5. DiagnosticStructuredFormatter

> **v15 変更**: `StructuredFormatter` を継承しているため、`__init__` 経由で `self.LEVEL_MAP = get_all_level_map()` が自動的に適用される。
> **v16 変更**: `DiagnosticFormatter` と同様に `sensitive_keywords` パラメータを `__init__` で受け取り、インスタンス変数として保持するように変更。`_BUILTIN_SENSITIVE_KEYWORDS` は `DiagnosticFormatter` から参照し一元管理する。

```python
class DiagnosticStructuredFormatter(StructuredFormatter):
    """structured=True かつ {prefix}_DIAGNOSE=1 時のフォーマッタ。
    f_locals 情報をJSONの locals フィールドとして包含出力する。
    センシティブな変数名（password, token, key 等）は値をマスキングする。"""

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        sensitive_keywords: frozenset[str] | None = None,
    ):
        super().__init__(fmt=fmt, datefmt=datefmt)
        # v16: DiagnosticFormatter と同じビルトインキーワードをフォールバックに使用
        self._sensitive_keywords: frozenset[str] = (
            sensitive_keywords
            if sensitive_keywords is not None
            else DiagnosticFormatter._BUILTIN_SENSITIVE_KEYWORDS
        )

    def _is_sensitive(self, var_name: str) -> bool:
        lower = var_name.lower()
        return any(kw in lower for kw in self._sensitive_keywords)

    def format(self, record: logging.LogRecord) -> str:
        data = json.loads(super().format(record))

        if getattr(record, '_ds_diag_frames', None) is not None:
            data['locals'] = record._ds_diag_frames
            return json.dumps(data, ensure_ascii=False, default=str)

        if record.exc_info and record.exc_info[2] is not None and record.thread == threading.get_ident():
            locals_data = []
            tb = record.exc_info[2]
            while tb is not None:
                frame = tb.tb_frame
                frame_locals = {}
                for key, value in frame.f_locals.items():
                    if self._is_sensitive(key):
                        frame_locals[key] = '*** MASKED ***'
                        continue
                    try:
                        repr_value = repr(value)
                        if len(repr_value) > 200:
                            repr_value = repr_value[:200] + '...'
                        frame_locals[key] = repr_value
                    except Exception:
                        frame_locals[key] = '<repr failed>'
                locals_data.append({
                    'frame': f'{frame.f_code.co_filename}:{tb.tb_lineno} in {frame.f_code.co_name}',
                    'variables': frame_locals,
                })
                tb = tb.tb_next
            data['locals'] = locals_data

        return json.dumps(data, ensure_ascii=False, default=str)
```

#### v18 追加: diagnose のフォールバック規則

- `_ds_diag_frames` / `_ds_exc_text` があれば、それを最優先で使用する
- それがなく、かつ `record.thread == threading.get_ident()` の同一 thread 条件を満たす場合のみ live `f_locals` 参照を許可する
- それ以外では standard traceback のみを出力する

---

## 5. RoutingStrategy 詳細設計

### 5.1. 抽象基底クラス

```python
from abc import ABC, abstractmethod
from pathlib import Path

class RoutingStrategy(ABC):
    def __init__(self, base_dir: Path, pg_name: str, **kwargs):
        self.base_dir = base_dir
        self.pg_name = pg_name

    @abstractmethod
    def get_current_path(self) -> Path:
        """現在の書き込み先ファイルパスを返す。"""
        ...

    @abstractmethod
    def should_switch(self, record: logging.LogRecord) -> bool:
        """ファイル切り替えが必要か判定する。"""
        ...

    def advance(self) -> None:
        """v20: ファイル切り替え後の状態更新。デフォルトは no-op。
        SizeStrategy / CountStrategy / StartupIntervalStrategy 等がオーバーライドする。"""
        pass

    def on_emit(self) -> None:
        """v22h: レコード1件の正常書き込み後に呼ばれる hook。デフォルトは no-op。"""
        pass

    def is_cyclic(self) -> bool:
        """サイクリックモードか（世代管理対象外か）を返す。"""
        return False
```

### 5.2. 各ストラテジのサフィックス規則

| routing_mode | サフィックス形式 | 例 |
|-------------|----------------|--------|
| `none` | なし | `Default.log` |
| `daily` | `_YYYYMMDD` | `Default_20260328.log` |
| `hourly` | `_YYYYMMDD_HH` | `Default_20260328_14.log` |
| `min_interval` | `_YYYYMMDD_HHMM` | `Default_20260328_1430.log` |
| `startup_interval` | `_YYYYMMDD_HHMMSS` | `Default_20260328_143005.log` |
| `size` | `_NNN` (suffix_digits桁連番) | `Default_000.log` |
| `count` | `_NNN` (suffix_digits桁連番) | `Default_000.log` |
| `cyclic_weekday` | `_ddd` (曜日略称) | `Default_thu.log` |
| `cyclic_month` | `_MM` (月番号) | `Default_03.log` |

### 5.3. NoneStrategy

```python
class NoneStrategy(RoutingStrategy):
    def get_current_path(self) -> Path:
        return self.base_dir / f'{self.pg_name}.log'

    def should_switch(self, record) -> bool:
        return False  # 切り替えなし
```

### 5.4. DailyStrategy

```python
class DailyStrategy(RoutingStrategy):
    def __init__(self, base_dir, pg_name, **kwargs):
        super().__init__(base_dir, pg_name)
        self._current_date: str = ''

    def get_current_path(self) -> Path:
        today = datetime.now().strftime('%Y%m%d')
        self._current_date = today
        return self.base_dir / f'{self.pg_name}_{today}.log'

    def should_switch(self, record) -> bool:
        today = datetime.now().strftime('%Y%m%d')
        return today != self._current_date
```

### 5.5. HourlyStrategy

```python
class HourlyStrategy(RoutingStrategy):
    def __init__(self, base_dir, pg_name, **kwargs):
        super().__init__(base_dir, pg_name)
        self._current_hour: str = ''

    def get_current_path(self) -> Path:
        now = datetime.now()
        key = now.strftime('%Y%m%d_%H')
        self._current_hour = key
        return self.base_dir / f'{self.pg_name}_{key}.log'

    def should_switch(self, record) -> bool:
        key = datetime.now().strftime('%Y%m%d_%H')
        return key != self._current_hour
```

### 5.6. MinIntervalStrategy

```python
class MinIntervalStrategy(RoutingStrategy):
    VALID_INTERVALS = {1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}

    def __init__(self, base_dir, pg_name, *, interval: int, **kwargs):
        super().__init__(base_dir, pg_name)
        if interval not in self.VALID_INTERVALS:
            raise ValueError(
                f'min_interval の interval は 60 の約数（{sorted(self.VALID_INTERVALS)}）のいずれかでなければなりません: {interval}'
            )
        self._interval = interval
        self._current_slot: str = ''

    def _get_slot(self) -> str:
        now = datetime.now()
        rounded_minute = (now.minute // self._interval) * self._interval
        return now.strftime('%Y%m%d_%H') + f'{rounded_minute:02d}'

    def get_current_path(self) -> Path:
        self._current_slot = self._get_slot()
        return self.base_dir / f'{self.pg_name}_{self._current_slot}.log'

    def should_switch(self, record) -> bool:
        return self._get_slot() != self._current_slot
```

### 5.7. StartupIntervalStrategy

```python
class StartupIntervalStrategy(RoutingStrategy):
    def __init__(self, base_dir, pg_name, *, interval: str | int, **kwargs):
        super().__init__(base_dir, pg_name)
        self._interval_minutes = self._parse_interval(interval)
        self._start_time = datetime.now()
        self._last_switch_time = self._start_time
        self._current_suffix: str = self._start_time.strftime('%Y%m%d_%H%M%S')

    @staticmethod
    def _parse_interval(interval: str | int) -> int:
        """interval を分数に変換する。整数はそのまま分、文字列は '12h','1d' 等をパースする。"""
        if isinstance(interval, int):
            if interval < 1:
                raise ValueError(f'interval は1以上の整数でなければなりません: {interval}')
            return interval
        if isinstance(interval, str):
            interval = interval.strip().lower()
            if interval.endswith('d'):
                return int(interval[:-1]) * 1440
            elif interval.endswith('h'):
                return int(interval[:-1]) * 60
            elif interval.endswith('m'):
                return int(interval[:-1])
            else:
                return int(interval)  # 数値文字列は分として扱う
        raise ValueError(f'interval の型が不正です: {type(interval)}')

    def get_current_path(self) -> Path:
        return self.base_dir / f'{self.pg_name}_{self._current_suffix}.log'

    def should_switch(self, record) -> bool:
        elapsed = (datetime.now() - self._last_switch_time).total_seconds()
        return elapsed >= self._interval_minutes * 60

    def advance(self) -> None:
        self._last_switch_time = datetime.now()
        self._current_suffix = self._last_switch_time.strftime('%Y%m%d_%H%M%S')
```

### 5.8. SizeStrategy

```python
class SizeStrategy(RoutingStrategy):
    def __init__(self, base_dir, pg_name, *,
                 max_bytes: int, max_count: int | None, suffix_digits: int = 3, **kwargs):
        super().__init__(base_dir, pg_name)
        self._max_bytes = max_bytes
        self._max_count = max_count
        self._suffix_digits = suffix_digits
        self._current_index: int = 0
        if max_count is None:
            self._upper_limit = 10 ** suffix_digits  # 3桁なら 1000 (0-999)
        else:
            self._upper_limit = max_count

    def get_current_path(self) -> Path:
        suffix = f'{self._current_index:0{self._suffix_digits}d}'
        return self.base_dir / f'{self.pg_name}_{suffix}.log'

    def should_switch(self, record) -> bool:
        current = self.get_current_path()
        if current.exists() and current.stat().st_size >= self._max_bytes:
            return True
        return False

    def advance(self) -> None:
        """次のファイルインデックスに進める。"""
        self._current_index += 1
        if self._max_count is not None:
            # サイクリックモード
            self._current_index %= self._max_count
        elif self._current_index >= self._upper_limit:
            raise OverflowError(
                f'ログファイル連番が {self._suffix_digits} 桁の上限 '
                f'({self._upper_limit - 1}) を超過しました（pg_name={self.pg_name}）。'
                f'容量設計を見直すか、max_count を指定してサイクリックモードを有効にしてください。'
            )

    def is_cyclic(self) -> bool:
        return self._max_count is not None
```

### 5.9. CountStrategy

```python
class CountStrategy(RoutingStrategy):
    """行数ベースのルーティング。サフィックス管理は SizeStrategy と同等。"""

    def __init__(self, base_dir, pg_name, *,
                 max_lines: int, max_count: int | None, suffix_digits: int = 3, **kwargs):
        super().__init__(base_dir, pg_name)
        self._max_lines = max_lines
        self._max_count = max_count
        self._suffix_digits = suffix_digits
        self._current_index: int = 0
        self._line_count: int = 0
        if max_count is None:
            self._upper_limit = 10 ** suffix_digits
        else:
            self._upper_limit = max_count

    def get_current_path(self) -> Path:
        suffix = f'{self._current_index:0{self._suffix_digits}d}'
        return self.base_dir / f'{self.pg_name}_{suffix}.log'

    def should_switch(self, record) -> bool:
        # v22h: CQS 準拠。クエリのみ。カウント更新は on_emit() で行う。
        return self._line_count >= self._max_lines

    def on_emit(self) -> None:
        self._line_count += 1

    def advance(self) -> None:
        self._current_index += 1
        self._line_count = 0
        if self._max_count is not None:
            self._current_index %= self._max_count
        elif self._current_index >= self._upper_limit:
            raise OverflowError(
                f'ログファイル連番が {self._suffix_digits} 桁の上限を超過しました（pg_name={self.pg_name}）。'
            )

    def is_cyclic(self) -> bool:
        return self._max_count is not None
```

### 5.10. CyclicWeekdayStrategy / CyclicMonthStrategy

```python
class CyclicWeekdayStrategy(RoutingStrategy):
    _DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

    def __init__(self, base_dir, pg_name, **kwargs):
        super().__init__(base_dir, pg_name)
        self._current_day: str = ''

    def get_current_path(self) -> Path:
        day_name = self._DAYS[datetime.now().weekday()]
        self._current_day = day_name
        return self.base_dir / f'{self.pg_name}_{day_name}.log'

    def should_switch(self, record) -> bool:
        day_name = self._DAYS[datetime.now().weekday()]
        return day_name != self._current_day

    def is_cyclic(self) -> bool:
        return True


class CyclicMonthStrategy(RoutingStrategy):
    def __init__(self, base_dir, pg_name, **kwargs):
        super().__init__(base_dir, pg_name)
        self._current_month: str = ''

    def get_current_path(self) -> Path:
        month = datetime.now().strftime('%m')
        self._current_month = month
        return self.base_dir / f'{self.pg_name}_{month}.log'

    def should_switch(self, record) -> bool:
        month = datetime.now().strftime('%m')
        return month != self._current_month

    def is_cyclic(self) -> bool:
        return True
```

---

## 6. AppendOnlyFileHandler 詳細設計

> **v18 追加方針**: `AppendOnlyFileHandler` は stdlib `logging.Handler.handle()` が提供する handler-level lock の内側で `emit()` を実行する前提とする。`_strategy.should_switch()`、`advance()`、`get_current_path()`、`_current_path` / `stream` / `baseFilename` の更新は、この lock に保護された区間でのみ行う。strategy 自体に別 lock は追加しない。

> **v21 変更**: `self._lock = threading.RLock()` を廃止した。`emit()` はすでに `logging.Handler.handle()` が保持する `self.lock`（`Handler.createLock()` で生成）の内側で呼び出されるため、独立した `RLock` は冗長であり、sync path では毎レコードで二重 lock 取得のオーバーヘッドを生んでいた。`close()` / `flush()` では `self.acquire()` / `self.release()` を使用する。

### 6.1. クラス定義

```python
from dsafelogger._integrity import HashWorker

class AppendOnlyFileHandler(logging.FileHandler):
    def __init__(self, strategy: RoutingStrategy, backup_count: int = 0,
                 archive_mode: bool = False, enable_hash: bool = False,
                 manifest_path: str | None = None, encoding: str = 'utf-8'):
        self._strategy = strategy
        self._backup_count = backup_count
        self._archive_mode = archive_mode
        self._enable_hash = enable_hash
        self._manifest_path = Path(manifest_path) if manifest_path else None
        self._current_path = strategy.get_current_path()

        # ディレクトリの自動作成
        self._current_path.parent.mkdir(parents=True, exist_ok=True)

        super().__init__(str(self._current_path), mode='a', encoding=encoding)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._strategy.should_switch(record):
                self._switch_file()
            super().emit(record)
            self._strategy.on_emit()
        except OverflowError:
            # v22h: 上限到達エラーモードは fail-fast とし、handleError() に吸い込ませない
            raise
        except Exception:
            self.handleError(record)

    def reopen(self) -> None:
        """外部 rotation 後に現在ファイルを再 open する。
        routing_mode='none' 前提。reopen 自身が handler-level lock を取得する。"""
        self.acquire()
        try:
            if not isinstance(self._strategy, NoneStrategy):
                raise ValueError("ReopenLogFiles() requires routing_mode='none'")
            old_stream = self.stream
            old_base = self.baseFilename
            current_path = self._current_path
            try:
                if old_stream:
                    old_stream.flush()
                    old_stream.close()
                self.baseFilename = str(current_path)
                self.stream = self._open()
            except OSError:
                self.baseFilename = old_base
                self.stream = old_stream
                raise
        finally:
            self.release()

    def _switch_file(self) -> None:
        """ファイル切り替え処理。Append-Only のため一切のリネームを行わない。"""
        old_path = self._current_path

        # ストラテジのインデックス進行（size/count/startup_interval の場合）
        if hasattr(self._strategy, 'advance'):
            self._strategy.advance()

        new_path = self._strategy.get_current_path()

        if new_path == old_path:
            return

        # v20: 新ファイルを先に試行し、成功後に旧ストリームを閉じる（ロールバック安全性）
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_stream = self.stream
        old_base = self.baseFilename
        old_current = self._current_path
        self._current_path = new_path
        self.baseFilename = str(new_path)
        try:
            self.stream = self._open()
        except OSError:
            # 新ファイル open 失敗 → 旧ファイルへロールバック
            self._current_path = old_current
            self.baseFilename = old_base
            self.stream = old_stream
            print(
                f'[D-SafeLogger] File switch failed: {new_path} → rollback to {old_current}',
                file=sys.stderr,
            )
            return
        # 新ファイル open 成功 → 旧ストリームを安全に close
        if old_stream:
            try:
                old_stream.flush()
                old_stream.close()
            except OSError:
                pass

        # ── v15 追加: ハッシュ生成 + パージ/アーカイブ ──
        # cyclic + enable_hash は ConfigureLogger 側の Fail-Fast 検証で拒否済み
        if not self._strategy.is_cyclic() and self._backup_count > 0:
            # パージ/アーカイブワーカー内でハッシュ生成を先行実行
            self._start_purge(old_path.parent, switched_file=old_path)
        elif not self._strategy.is_cyclic() and self._enable_hash and old_path.exists():
            # backup_count=0 の非 cyclic モードは独立した HashWorker を起動
            self._start_hash_worker(old_path)

    def _start_purge(self, directory: Path, switched_file: Path | None = None) -> None:
        """Fire-and-Forget パージ/アーカイブスレッドを起動。"""
        if self._archive_mode:
            worker = ArchiveWorker(
                directory=directory,
                pg_name=self._strategy.pg_name,
                backup_count=self._backup_count,
                enable_hash=self._enable_hash,
                manifest_path=self._manifest_path,
                switched_file=switched_file,
            )
        else:
            worker = PurgeWorker(
                directory=directory,
                pg_name=self._strategy.pg_name,
                backup_count=self._backup_count,
                enable_hash=self._enable_hash,
                manifest_path=self._manifest_path,
                switched_file=switched_file,
            )
        worker.daemon = True
        _register_worker(worker)
        worker.start()
        # join しない（Fire-and-Forget）

    def _start_hash_worker(self, file_path: Path) -> None:
        """Fire-and-Forget ハッシュ生成スレッドを起動。
        backup_count=0 かつ enable_hash=True の場合に使用。"""
        worker = HashWorker(
            file_path=file_path,
            manifest_path=self._manifest_path,
        )
        worker.daemon = True
        _register_worker(worker)
        worker.start()
```

- `reopen()` は **メソッド自身が** `self.acquire()` / `self.release()` を実行し、`emit()` と競合しても stream 差し替えが直列化される
- reopen はファイル descriptor / inode の張り替えのみを目的とし、`RoutingStrategy.advance()` や purge / archive / hash を起動しない
- reopen 失敗時は `OSError` をそのまま伝播し、運用層に fail-fast させる

---

## 7. 非同期パージ・アーカイブ詳細設計

### 7.1. PurgeWorker（通常モード: 削除）

```python
from dsafelogger._integrity import write_sidecar, append_manifest

class PurgeWorker(threading.Thread):
    def __init__(self, directory: Path, pg_name: str, backup_count: int,
                 enable_hash: bool = False, manifest_path: Path | None = None,
                 switched_file: Path | None = None):
        super().__init__(daemon=True)
        self.directory = directory
        self.pg_name = pg_name
        self.backup_count = backup_count
        self._enable_hash = enable_hash
        self._manifest_path = manifest_path
        self._switched_file = switched_file

    def run(self) -> None:
        try:
            family_lock = _get_family_lock(self.directory, self.pg_name)

            def _run_body() -> None:
                # Lock ordering: family_lock -> manifest_lock (never reverse)
                # Do NOT acquire _lifecycle_lock while holding this lock
                with family_lock:
                    if self._enable_hash and self._switched_file and self._switched_file.exists():
                        try:
                            # v20: ハッシュ値を1回だけ計算し、sidecar/manifest に共有
                            hv = compute_sha256(self._switched_file)
                            write_sidecar(self._switched_file, hash_value=hv)
                            if self._manifest_path:
                                append_manifest(self._switched_file, self._manifest_path, hash_value=hv)
                        except OSError as e:
                            print(
                                f'[D-SafeLogger] Hash generation failed for '
                                f'{self._switched_file.name}: {e}',
                                file=sys.stderr,
                            )

                    pattern = f'{self.pg_name}_*.log'
                    log_files = sorted(
                        self.directory.glob(pattern),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )

                    files_to_delete = log_files[self.backup_count:]
                    for f in files_to_delete:
                        try:
                            f.unlink()
                            sidecar = f.with_suffix(f.suffix + '.sha256')
                            sidecar.unlink(missing_ok=True)
                        except PermissionError:
                            print(f'[D-SafeLogger] Purge skipped (locked): {f}',
                                  file=sys.stderr)
                        except OSError as e:
                            print(f'[D-SafeLogger] Purge failed: {f} ({e})',
                                  file=sys.stderr)

            _run_in_empty_context(_run_body)
        except Exception as e:
            print(f'[D-SafeLogger] Purge worker error: {e}', file=sys.stderr)
        finally:
            _unregister_worker(self)
```

### 7.2. ArchiveWorker（アーカイブモード: ZIP圧縮）

```python
import zipfile
import shutil
from dsafelogger._integrity import write_sidecar, append_manifest

class ArchiveWorker(threading.Thread):
    """archive_mode=True 時に使用。
    backup_count を超過した古いファイルを削除する代わりに ZIP アーカイブ化する。
    daemon=True で Fire-and-Forget 起動するが、_shutdown() から join() による
    フェイルセーフ待機が呼び出されることで壊れたZIPの生成を防ぐ。"""

    # アーカイブ処理に必要な最低空き容量（対象ファイルサイズの2倍を安全マージンとする）
    SAFETY_MARGIN_RATIO = 2.0

    def __init__(self, directory: Path, pg_name: str, backup_count: int,
                 enable_hash: bool = False, manifest_path: Path | None = None,
                 switched_file: Path | None = None):
        super().__init__(daemon=True)
        self.directory = directory
        self.pg_name = pg_name
        self.backup_count = backup_count
        self._enable_hash = enable_hash
        self._manifest_path = manifest_path
        self._switched_file = switched_file
        self._started_at: float = 0.0

    def start(self) -> None:
        import time
        self._started_at = time.monotonic()
        super().start()

    def run(self) -> None:
        try:
            family_lock = _get_family_lock(self.directory, self.pg_name)

            def _run_body() -> None:
                # Lock ordering: family_lock -> manifest_lock (never reverse)
                # Do NOT acquire _lifecycle_lock while holding this lock
                with family_lock:
                    if self._enable_hash and self._switched_file and self._switched_file.exists():
                        try:
                            # v20: ハッシュ値を1回だけ計算し、sidecar/manifest に共有
                            hv = compute_sha256(self._switched_file)
                            write_sidecar(self._switched_file, hash_value=hv)
                            if self._manifest_path:
                                append_manifest(self._switched_file, self._manifest_path, hash_value=hv)
                        except OSError as e:
                            print(
                                f'[D-SafeLogger] Hash generation failed for '
                                f'{self._switched_file.name}: {e}',
                                file=sys.stderr,
                            )

                    pattern = f'{self.pg_name}_*.log'
                    log_files = sorted(
                        self.directory.glob(pattern),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )

                    files_to_archive = log_files[self.backup_count:]
                    if not files_to_archive:
                        return

                    total_size = sum(f.stat().st_size for f in files_to_archive)
                    disk_usage = shutil.disk_usage(self.directory)
                    required = int(total_size * self.SAFETY_MARGIN_RATIO)
                    if disk_usage.free < required:
                        print(
                            f'[D-SafeLogger] Archive aborted: insufficient disk space '
                            f'(free={disk_usage.free}, required={required})',
                            file=sys.stderr,
                        )
                        return

                    for f in files_to_archive:
                        zip_path = f.with_suffix('.log.zip')
                        try:
                            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                                zf.write(f, f.name)
                                sidecar = f.with_suffix(f.suffix + '.sha256')
                                if sidecar.exists():
                                    zf.write(sidecar, sidecar.name)
                            f.unlink()
                            sidecar = f.with_suffix(f.suffix + '.sha256')
                            sidecar.unlink(missing_ok=True)
                        except PermissionError:
                            print(f'[D-SafeLogger] Archive skipped (locked): {f}',
                                  file=sys.stderr)
                        except OSError as e:
                            print(f'[D-SafeLogger] Archive failed: {f} ({e})',
                                  file=sys.stderr)

            _run_in_empty_context(_run_body)
        except Exception as e:
            print(f'[D-SafeLogger] Archive worker error: {e}', file=sys.stderr)
        finally:
            _unregister_worker(self)
```

---

## 8. 非同期モード（QueueHandler/Listener）詳細設計

### 8.1. セットアップフロー

```
[is_async=True の場合]

1. queue.Queue() を生成（上限なし）
2. 実 Handler（AppendOnlyFileHandler, ColorStreamHandler）を生成
3. DSafeQueueHandler(queue) をルートロガーに追加
4. DSafeQueueListener(queue, *実Handlers) を開始
5. atexit.register(_shutdown) で終了処理を登録（重複防止あり）
```

### 8.2. DSafeQueueHandler

```python
import copy
import logging.handlers


class DSafeQueueHandler(logging.handlers.QueueHandler):
    """producer thread 側で context / diagnose 情報を安全に snapshot 化して queue へ渡す。"""

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        # v18: stdlib QueueHandler.prepare() は呼ばない。完全オーバーライドする。
        prepared = copy.copy(record)
        prepared._ds_context = _snapshot_context()

        if _diagnose_enabled and prepared.exc_info:
            prepared._ds_exc_text, prepared._ds_diag_frames = _snapshot_diagnostic_frames(
                prepared.exc_info,
                sensitive_keywords=_resolved_sensitive_keywords,
            )
        else:
            prepared._ds_exc_text = None
            prepared._ds_diag_frames = None

        return prepared
```

- `super().prepare()` は呼ばない
- `diagnose=False` の通常系は copy + context snapshot のみの fast path とする
- `diagnose=True` かつ `exc_info` ありの場合のみ heavy な traceback / locals snapshot を生成する

### 8.3. DSafeQueueListener

```python
import contextvars
import logging.handlers
import threading


class DSafeQueueListener(logging.handlers.QueueListener):
    """monitor thread を空 Context で開始し、safe shutdown 用 timeout stop を提供する。"""

    def start(self):
        if self._thread is not None:
            raise RuntimeError('Listener already started')

        def _monitor_in_empty_context():
            return _run_in_empty_context(self._monitor)

        self._thread = t = threading.Thread(target=_monitor_in_empty_context)
        t.daemon = True
        t.start()

    def stop_with_timeout(self, timeout: float) -> bool:
        self.enqueue_sentinel()
        self._thread.join(timeout=timeout)
        alive = self._thread.is_alive()
        if not alive:
            self._thread = None
        return not alive
```

#### 8.3a. async writer 側 reopen

- `ReopenLogFiles()` が `QueueTransport` に到達した場合、対象は producer 側 `DSafeQueueHandler` ではなく `DSafeQueueListener` が保持する実 file handler 群である
- 各 file handler の `reopen()` は handler-level lock で直列化されるため、listener thread の `handle(record)` と同時実行されても stream 差し替えの整合性を保つ
- reopen 中も queue 自体は停止しない。producer 側は従来通り enqueue を継続し、listener 側で短時間の逐次化が発生するのみとする

### 8.4. シャットダウン処理

```python
import threading

_lifecycle_lock = threading.RLock()
_workers_lock = threading.Lock()
_active_pipeline: Pipeline | None = None
_active_workers: set[threading.Thread] = set()

QUEUE_DRAIN_TIMEOUT_SEC = 10.0
WORKER_JOIN_TIMEOUT_SEC = 5.0
# multiprocess runtime 側の定数は `dsafelogger.mp` 実装へ分離する


def _register_worker(worker: threading.Thread) -> None:
    with _workers_lock:
        _active_workers.add(worker)


def _unregister_worker(worker: threading.Thread) -> None:
    with _workers_lock:
        _active_workers.discard(worker)


def _shutdown() -> None:
    """通常終了時の safe shutdown。
    Phase A: lock 下で状態確定と参照退避
    Phase B: lock 外で pipeline stop / worker join / handler close
    Phase C: 必要なら lock 下で最終状態を確定
    """
```

#### 8.4.1. safe shutdown の順序

1. `_lifecycle_lock` 下で `_configure_state = 'shutting_down'` とし、`_active_pipeline` / フラグをローカルへ退避して global から切り離す
2. root logger から `pipeline.get_root_handlers()` を切り離し、新規 enqueue を停止
3. `pipeline.stop(QUEUE_DRAIN_TIMEOUT_SEC)` を lock 外で実行（内部で transport stop / listener drain / transport 配下 handler close を行う）
4. `_workers_lock` 下で `_active_workers` の snapshot を取得し、lock 外で各 worker を `join(timeout=WORKER_JOIN_TIMEOUT_SEC)` する
5. root logger に残っている handler を flush / close する
6. `_lifecycle_lock` 下で `_configure_state = 'unconfigured'` へ遷移し、再初期化を許可する

#### 8.4.2. safe shutdown の注意点

- worker join より先に `pipeline.stop()` を完了させる。transport 停止の過程で最後の queued record が処理され、新しい worker が起動しうるため
- `_lifecycle_lock` / `_workers_lock` 保持中に `join()`、queue drain、I/O を行わない
- `HashWorker` も `_active_workers` に含め、shutdown 時の join 対象へ統一する
- `daemon=True` は backstop にすぎず、通常終了の安全性根拠にはしない
- `PythonFinalizationError` 等で join 継続不能な場合は warning に degrade する
- `_shutdown()` は idempotent とし、`atexit` の重複起動や明示呼び出しとの競合では 2 回目以降を No-Op とする
- queue drain timeout 発生時は warning を出し、未排出レコードの best-effort を断念して handler close へ進む

#### 8.4.3. 保証範囲

- 通常終了時、shutdown 開始前に受理済みの queued record は queue drain 成功時に出力完了を目指す
- `hash` / `purge` / `archive` は bounded wait の best-effort とする
- SIGKILL、`os._exit()`、interpreter crash 等は保証対象外

#### 8.4.4. atexit / finalization の扱い

- `atexit.register(_shutdown)` は `_atexit_registered` で 1 回だけ登録する
- interpreter finalization の進行により lock / join / stderr 出力の一部が失敗しうるため、その場合は例外を再送出せず warning に degrade する
- finalization 中に listener thread や worker thread の完了確認が不能でも、プロセス終了を妨げない

### 8.5. v23b CloseMarker 送信プロトコル

drain 完了判定は `Queue.empty()` ではなく、各 client が DETACH 前に log_queue へ投入する CloseMarker の Writer 側受信をもって行う（v23b）。

**is_async=False の場合**

```
1. client が最後の log を log_queue に put（synchronous）
2. client が CloseMarker を log_queue に put
3. client が DETACH を control_queue に put（close_marker_failed=False）
```

**is_async=True の場合**

```
1. client が pump thread を join（local queue → log_queue の forwarding 完了待ち）
2. client が CloseMarker を log_queue に put
3. client が DETACH を control_queue に put
```

log_queue は FIFO であるため、CloseMarker は当該 client の全 LogEvent の後に Writer へ到達することが保証される。

**CloseMarker 送信失敗時**

- client は DETACH payload に `close_marker_failed=True` を載せる
- Writer は当該 client を `_close_marker_failed_clients` に追加し、`_close_marker_degraded = True` フラグを立てる
- stderr に warning を出力（silent failure 禁止）

**drain deadline 超過時（§11.21 / v23g / v23h）**

- Writer は outstanding close marker を stderr に列挙する
- v23g 以降は `log_queue.qsize()` を試みて残メッセージ数も報告する（`_writer_drain_deadline_loss` カウンター）
- v23h: log_queue は `TrackedQueue` で生成されるため、Linux/Windows ではネイティブ `qsize()`、macOS 等で native 不在の場合は init 時にプローブして自前カウンターへ自動 fallback する（OS 判定なし、例外プローブ）。これにより -1 報告は基本的に発生しない
- それでも qsize() が `NotImplementedError` / `OSError` を投げた場合は `-1` を表示して続行する（fail-safe）

**CloseMarker と DETACH の到着順 race**

control plane と log plane は独立したキューであるため、DETACH が CloseMarker より先に到着する可能性がある。`_active_lock` で保護された状態遷移により、いずれの到着順でも drain 完了判定は正しく動作する。

---

## 9. INIファイルローダー詳細設計

### 9.1. IniLoader クラス

```python
import configparser
from pathlib import Path

class IniLoader:
    """INIファイルの読み込みとFail-Fastバリデーションを行う。
    configparser.ConfigParser(interpolation=None) を使用し、
    % エスケープを不要にする。"""

    MODULE_SECTION_PREFIX = 'dsafelogger:'

    # [global] セクションで有効なキー
    VALID_GLOBAL_KEYS = frozenset({
        'default_level', 'log_path', 'pg_name', 'env_prefix',
        'is_async', 'backup_count', 'archive_mode', 'routing_mode',
        'interval', 'max_bytes', 'max_lines', 'max_count',
        'suffix_digits', 'console_out', 'structured',
        'fmt', 'file_fmt', 'console_fmt', 'datefmt',
        'enable_hash', 'manifest_path',
        'sens_kws', 'sens_kws_replace',  # v16 追加
    })
    # ※ color_ プレフィックスのキーはパターンベースで認識するため、
    #   VALID_GLOBAL_KEYS には含めない（v17 追加）

    # v17: color_ キーのパターン認識用
    COLOR_KEY_PREFIX = 'color_'

    # 聖域: 記載されても無視されるキー
    IGNORED_KEYS = frozenset({'diagnose'})

    # 型変換ルール
    BOOL_KEYS = frozenset({'is_async', 'archive_mode', 'console_out', 'structured', 'enable_hash', 'sens_kws_replace'})  # v16: sens_kws_replace 追加
    INT_KEYS = frozenset({'backup_count', 'max_bytes', 'max_lines', 'suffix_digits'})
    OPTIONAL_INT_KEYS = frozenset({'max_count'})  # 空値は None として扱う
    OPTIONAL_STR_NONE_KEYS = frozenset({'fmt', 'file_fmt', 'console_fmt', 'datefmt'})
    CSV_KEYS = frozenset({'sens_kws'})  # v16: カンマ区切り文字列 → list[str] に変換
    STR_KEYS = frozenset({
        'default_level', 'log_path', 'pg_name', 'env_prefix',
        'routing_mode', 'interval', 'fmt', 'file_fmt', 'console_fmt', 'datefmt',
        'manifest_path',
    })

    # モジュール別セクションで有効なキー
    VALID_MODULE_KEYS = frozenset({
        'level', 'path', 'routing_mode', 'max_bytes', 'max_lines',
        'max_count', 'suffix_digits', 'backup_count', 'archive_mode',
    })
    MODULE_ROUTING_KEYS = frozenset({
        'routing_mode', 'max_bytes', 'max_lines', 'max_count',
        'suffix_digits', 'backup_count', 'archive_mode',
    })

    @classmethod
    def load(cls, file_path: str) -> tuple[dict, dict[str, dict]]:
        """INIファイルを読み込み、グローバル設定とモジュール別設定を返す。

        Args:
            file_path: INIファイルのパス

        Returns:
            (global_config, module_configs)
            global_config: {key: converted_value} - [global] セクションの設定
            module_configs: {module_name: {key: converted_value}} - モジュール別設定

        Raises:
            FileNotFoundError: ファイルが存在しない
            ValueError: 型変換エラー、不正な値
            OSError: ファイル読み込み失敗
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(
                f"INI config file not found: '{file_path}'"
            )

        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(str(path), encoding='utf-8')
        except configparser.Error as e:
            raise ValueError(f"INI config parse error: {e}") from e

        global_config = cls._parse_global_section(parser)
        module_configs = cls._parse_module_sections(parser)

        return global_config, module_configs

    @classmethod
    def _parse_global_section(cls, parser: configparser.ConfigParser) -> dict:
        """[global] セクションを解析し、型変換済みの辞書を返す。"""
        config = {}

        if not parser.has_section('global'):
            return config

        for key, raw_value in parser.items('global'):
            # 聖域キー: 無視（警告もエラーもなし）
            if key in cls.IGNORED_KEYS:
                continue

            # v17: color_ プレフィックスのキーはパターンベースで認識
            #      → _parse_color_palette() で別途処理するため、ここではスキップ
            if key.startswith(cls.COLOR_KEY_PREFIX):
                continue

            # 未知のキー: 警告出力
            if key not in cls.VALID_GLOBAL_KEYS:
                print(
                    f'[D-SafeLogger] INI: unknown key in [global]: {key!r} (ignored)',
                    file=sys.stderr,
                )
                continue

            config[key] = cls._convert_value(key, raw_value, section='global')

        return config

    @classmethod
    def _parse_module_sections(cls, parser: configparser.ConfigParser) -> dict[str, dict]:
        """[dsafelogger:mod] セクション群を解析し、モジュール別設定辞書を返す。"""
        module_configs = {}

        for section in parser.sections():
            if not section.startswith(cls.MODULE_SECTION_PREFIX):
                if section != 'global':
                    print(
                        f'[D-SafeLogger] INI: unknown section [{section}] (ignored)',
                        file=sys.stderr,
                    )
                continue

            module_name = section[len(cls.MODULE_SECTION_PREFIX):]
            if not module_name:
                raise ValueError(
                    f"INI: empty module name in section [{section}]"
                )

            mod_config = {}
            has_path = parser.has_option(section, 'path')

            for key, raw_value in parser.items(section):
                if key not in cls.VALID_MODULE_KEYS:
                    print(
                        f'[D-SafeLogger] INI: unknown key in [{section}]: {key!r} (ignored)',
                        file=sys.stderr,
                    )
                    continue

                # path 省略時にルーティング関連キーが指定された場合は警告
                if not has_path and key in cls.MODULE_ROUTING_KEYS:
                    print(
                        f'[D-SafeLogger] INI: [{section}] key {key!r} requires '
                        f"'path' to be set (ignored)",
                        file=sys.stderr,
                    )
                    continue

                mod_config[key] = cls._convert_module_value(
                    key, raw_value, section=section
                )

            # level は必須
            if 'level' not in mod_config:
                raise ValueError(
                    f"INI: [{section}] requires 'level' key"
                )

            module_configs[module_name] = mod_config

        return module_configs

    # --- v17 追加: カラーパレット解析 ---

    @classmethod
    def _parse_color_palette(
        cls,
        parser: configparser.ConfigParser,
        valid_abbreviations: set[str],
    ) -> dict[str, str]:
        """[global] セクションから color_{略称} キーを抽出し、
        {略称(大文字): ANSIコード数値部分} の辞書を返す。

        color_ プレフィックスのキーは VALID_GLOBAL_KEYS には含まれず、
        パターンベースで動的に認識される。

        Args:
            parser: 読み込み済みの ConfigParser
            valid_abbreviations: 有効な略称の集合（ビルトイン + カスタムレベル）

        Returns:
            カラーオーバーライド辞書。例: {'ERR': '91', 'CRI': '1;91'}
            color_ キーが1つもなければ空辞書。
        """
        import re
        VALID_VALUE_PATTERN = re.compile(r'^[0-9;]*$')

        if not parser.has_section('global'):
            return {}

        overrides: dict[str, str] = {}
        for key, raw_value in parser.items('global'):
            if not key.startswith(cls.COLOR_KEY_PREFIX):
                continue

            abbr = key[len(cls.COLOR_KEY_PREFIX):].upper()

            # 未知略称チェック
            if abbr not in valid_abbreviations:
                print(
                    f'[D-SafeLogger] INI: unknown color key {key!r} '
                    f'(abbreviation {abbr!r} is not registered). Ignoring.',
                    file=sys.stderr,
                )
                continue

            # 空文字列は有効（カラー無効化）
            value = raw_value.strip()
            if value == '':
                overrides[abbr] = ''
                continue

            # 不正文字チェック（0-9 と ; のみ許容）
            if not VALID_VALUE_PATTERN.match(value):
                print(
                    f'[D-SafeLogger] INI: invalid ANSI code {value!r} '
                    f'for {key!r}. Only digits and semicolons are allowed. Ignoring.',
                    file=sys.stderr,
                )
                continue

            overrides[abbr] = value

        return overrides

    @classmethod
    def _convert_value(cls, key: str, raw_value: str, section: str) -> object:
        """[global] セクションの値を適切な型に変換する。"""
        if key in cls.BOOL_KEYS:
            return cls._parse_bool(key, raw_value, section)
        if key in cls.INT_KEYS:
            return cls._parse_int(key, raw_value, section)
        if key in cls.OPTIONAL_INT_KEYS:
            return cls._parse_optional_int(key, raw_value, section)
        if key in cls.OPTIONAL_STR_NONE_KEYS:
            return cls._parse_optional_str(raw_value)
        if key in cls.CSV_KEYS:
            return cls._parse_csv(key, raw_value, section)
        # OPTIONAL_STR_NONE_KEYS 以外の STR_KEYS はそのまま文字列として返す
        return raw_value

    @staticmethod
    def _parse_optional_str(raw_value: str) -> str | None:
        """空文字列（空白のみ含む）は None として扱う。"""
        return None if raw_value.strip() == '' else raw_value

    @classmethod
    def _convert_module_value(cls, key: str, raw_value: str, section: str) -> object:
        """モジュール別セクションの値を適切な型に変換する。"""
        if key == 'level':
            return raw_value.upper()
        if key == 'path':
            return raw_value
        if key in ('routing_mode',):
            return raw_value
        if key in ('max_bytes', 'max_lines', 'suffix_digits', 'backup_count'):
            return cls._parse_int(key, raw_value, section)
        if key in ('max_count',):
            return cls._parse_optional_int(key, raw_value, section)
        if key in ('archive_mode',):
            return cls._parse_bool(key, raw_value, section)
        return raw_value

    @staticmethod
    def _parse_bool(key: str, raw_value: str, section: str) -> bool:
        """真偽値の変換。Fail-Fast。"""
        v = raw_value.strip().lower()
        if v in ('true', '1', 'yes', 'on'):
            return True
        if v in ('false', '0', 'no', 'off'):
            return False
        raise ValueError(
            f"INI key '{key}' in [{section}]: expected bool, got {raw_value!r}"
        )

    @staticmethod
    def _parse_int(key: str, raw_value: str, section: str) -> int:
        """整数値の変換。Fail-Fast。"""
        raw_value = raw_value.strip()
        try:
            return int(raw_value)
        except ValueError:
            raise ValueError(
                f"INI key '{key}' in [{section}]: expected int, got {raw_value!r}"
            ) from None

    @staticmethod
    def _parse_optional_int(key: str, raw_value: str, section: str) -> int | None:
        """オプショナル整数値の変換。空値は None。Fail-Fast。"""
        raw_value = raw_value.strip()
        if not raw_value:
            return None
        try:
            return int(raw_value)
        except ValueError:
            raise ValueError(
                f"INI key '{key}' in [{section}]: expected int or empty, got {raw_value!r}"
            ) from None

    @staticmethod
    def _parse_csv(key: str, raw_value: str, section: str) -> list[str]:
        """カンマ区切り文字列を list[str] に変換する。v16 追加。
        各要素は strip() され、空文字列の要素は除外される。"""
        raw_value = raw_value.strip()
        if not raw_value:
            return []
        items = [item.strip() for item in raw_value.split(',')]
        return [item for item in items if item]
```

### 9.2. グローバル設定のマージロジック

```python
def _merge_ini_global(args_config: dict, ini_config: dict) -> dict:
    """第3層（引数）に第2層（INI）をマージする。
    INIに存在するキーのみ上書きし、存在しないキーは引数値を維持する。"""
    merged = args_config.copy()
    for key, value in ini_config.items():
        if key in merged:
            merged[key] = value
    return merged
```

### 9.3. モジュール別設定のマージロジック

```python
def _merge_module_configs(
    ini_modules: dict[str, dict],
    env_modules: dict[str, dict],
) -> dict[str, dict]:
    """INI（第2層）のモジュール別設定に環境変数（第1層）をマージする。
    環境変数で指定されたフィールド（level/path）のみを上書きし、
    INI側のルーティング詳細は維持する。"""
    merged = {}

    # まずINIの全モジュールをコピー
    for mod, config in ini_modules.items():
        merged[mod] = config.copy()

    # 環境変数の上書き
    for mod, env_config in env_modules.items():
        if mod in merged:
            # 既存モジュール: 指定フィールドのみ上書き
            if 'level' in env_config:
                merged[mod]['level'] = env_config['level']
            if 'path' in env_config and env_config['path'] is not None:
                merged[mod]['path'] = env_config['path']
        else:
            # 新規モジュール（INIにない、環境変数のみ）
            merged[mod] = env_config

    return merged
```

### 9.4. DictLoader クラス（v16 追加）

> `config_dict` パラメータで渡された辞書を、IniLoader と同等のバリデーション・型変換パイプラインで処理するクラス。IniLoader が `configparser` 経由でINIファイルを読むのに対し、DictLoader は既にメモリ上にある `dict[str, dict[str, str]]` を入力とする。出力形式（`global_config`, `module_configs`）は IniLoader と完全に同一であり、下流のマージロジックを共有できる。

```python
class DictLoader:
    """辞書ベース設定の読み込みとFail-Fastバリデーションを行う。
    IniLoader と同じキーセット・型変換ルール・聖域保護を適用する。"""

    @classmethod
    def load(cls, config_dict: dict[str, dict[str, str]]) -> tuple[dict, dict[str, dict]]:
        """辞書を読み込み、グローバル設定とモジュール別設定を返す。

        Args:
            config_dict: {'global': {key: value}, 'dsafelogger:mod': {key: value}, ...}
                         全ての値は str 型でなければならない。

        Returns:
            (global_config, module_configs) — IniLoader.load() と同一形式

        Raises:
            TypeError: 辞書の構造が不正（値が str でない等）
            ValueError: 型変換エラー、不正な値
        """
        # 構造バリデーション: トップレベル
        if not isinstance(config_dict, dict):
            raise TypeError(
                f"config_dict must be dict[str, dict[str, str]], "
                f"got {type(config_dict).__name__}"
            )

        for section_name, section_value in config_dict.items():
            if not isinstance(section_name, str):
                raise TypeError(
                    f"config_dict section key must be str, "
                    f"got {type(section_name).__name__}: {section_name!r}"
                )
            if not isinstance(section_value, dict):
                raise TypeError(
                    f"config_dict section '{section_name}' must be dict[str, str], "
                    f"got {type(section_value).__name__}"
                )
            for key, value in section_value.items():
                if not isinstance(key, str):
                    raise TypeError(
                        f"config_dict key in ['{section_name}'] must be str, "
                        f"got {type(key).__name__}: {key!r}"
                    )
                if not isinstance(value, str):
                    raise TypeError(
                        f"config_dict value for '{key}' in ['{section_name}'] must be str, "
                        f"got {type(value).__name__}: {value!r}"
                    )

        global_config = cls._parse_global_section(config_dict)
        module_configs = cls._parse_module_sections(config_dict)

        return global_config, module_configs

    @classmethod
    def _parse_global_section(cls, config_dict: dict[str, dict[str, str]]) -> dict:
        """'global' セクションを解析し、型変換済みの辞書を返す。
        IniLoader と同じ VALID_GLOBAL_KEYS / IGNORED_KEYS / 型変換ルールを適用する。"""
        config = {}
        default_section = config_dict.get('global', {})

        for key, raw_value in default_section.items():
            key_lower = key.lower()

            # 聖域キー: 無視（警告もエラーもなし）
            if key_lower in IniLoader.IGNORED_KEYS:
                continue

            # v17: color_ プレフィックスのキーはパターンベースで認識
            #      → _parse_color_palette() で別途処理するため、ここではスキップ
            if key_lower.startswith(IniLoader.COLOR_KEY_PREFIX):
                continue

            # 未知のキー: 警告出力
            if key_lower not in IniLoader.VALID_GLOBAL_KEYS:
                print(
                    f'[D-SafeLogger] config_dict: unknown key in [global]: {key!r} (ignored)',
                    file=sys.stderr,
                )
                continue

            config[key_lower] = IniLoader._convert_value(key_lower, raw_value, section='global')

        return config

    @classmethod
    def _parse_module_sections(cls, config_dict: dict[str, dict[str, str]]) -> dict[str, dict]:
        """'dsafelogger:' プレフィックスのセクションを解析する。
        IniLoader と同じ VALID_MODULE_KEYS / MODULE_ROUTING_KEYS を適用する。"""
        module_configs = {}

        for section_name, section_data in config_dict.items():
            if not section_name.startswith(IniLoader.MODULE_SECTION_PREFIX):
                if section_name != 'global':
                    print(
                        f'[D-SafeLogger] config_dict: unknown section [{section_name}] (ignored)',
                        file=sys.stderr,
                    )
                continue

            module_name = section_name[len(IniLoader.MODULE_SECTION_PREFIX):]
            if not module_name:
                raise ValueError(
                    f"config_dict: empty module name in section [{section_name}]"
                )

            mod_config = {}
            has_path = 'path' in section_data

            for key, raw_value in section_data.items():
                key_lower = key.lower()

                if key_lower not in IniLoader.VALID_MODULE_KEYS:
                    print(
                        f'[D-SafeLogger] config_dict: unknown key in [{section_name}]: '
                        f'{key!r} (ignored)',
                        file=sys.stderr,
                    )
                    continue

                # path 省略時にルーティング関連キーが指定された場合は警告
                if not has_path and key_lower in IniLoader.MODULE_ROUTING_KEYS:
                    print(
                        f'[D-SafeLogger] config_dict: [{section_name}] key {key!r} requires '
                        f"'path' to be set (ignored)",
                        file=sys.stderr,
                    )
                    continue

                mod_config[key_lower] = IniLoader._convert_module_value(
                    key_lower, raw_value, section=section_name
                )

            # level は必須
            if 'level' not in mod_config:
                raise ValueError(
                    f"config_dict: [{section_name}] requires 'level' key"
                )

            module_configs[module_name] = mod_config

        return module_configs

    # --- v17 追加: カラーパレット解析 ---

    @classmethod
    def _parse_color_palette(
        cls,
        config_dict: dict[str, dict[str, str]],
        valid_abbreviations: set[str],
    ) -> dict[str, str]:
        """'global' セクションから color_{略称} キーを抽出し、
        {略称(大文字): ANSIコード数値部分} の辞書を返す。
        IniLoader._parse_color_palette() と同一のバリデーションロジックを適用する。

        Args:
            config_dict: 入力辞書
            valid_abbreviations: 有効な略称の集合（ビルトイン + カスタムレベル）

        Returns:
            カラーオーバーライド辞書。例: {'ERR': '91', 'CRI': '1;91'}
        """
        import re
        VALID_VALUE_PATTERN = re.compile(r'^[0-9;]*$')

        default_section = config_dict.get('global', {})
        overrides: dict[str, str] = {}

        for key, raw_value in default_section.items():
            key_lower = key.lower()
            if not key_lower.startswith(IniLoader.COLOR_KEY_PREFIX):
                continue

            abbr = key_lower[len(IniLoader.COLOR_KEY_PREFIX):].upper()

            # 未知略称チェック
            if abbr not in valid_abbreviations:
                print(
                    f'[D-SafeLogger] config_dict: unknown color key {key!r} '
                    f'(abbreviation {abbr!r} is not registered). Ignoring.',
                    file=sys.stderr,
                )
                continue

            # 空文字列は有効（カラー無効化）
            value = raw_value.strip()
            if value == '':
                overrides[abbr] = ''
                continue

            # 不正文字チェック
            if not VALID_VALUE_PATTERN.match(value):
                print(
                    f'[D-SafeLogger] config_dict: invalid ANSI code {value!r} '
                    f'for {key!r}. Only digits and semicolons are allowed. Ignoring.',
                    file=sys.stderr,
                )
                continue

            overrides[abbr] = value

        return overrides
```

> **設計判断**: DictLoader は IniLoader の型変換メソッド群（`_convert_value`, `_convert_module_value`, `_parse_bool`, `_parse_int` 等）を直接委譲呼び出しする。これにより、INI と辞書で型変換ロジックが乖離するリスクを構造的に排除する。将来的に両者を共通基底クラスに抽出するリファクタリングも可能だが、現時点では委譲方式で十分である。DictLoader._parse_color_palette() も IniLoader._parse_color_palette() と同一のバリデーションルールを適用する（v17 追加）。

---

## 10. 環境変数パーサ詳細設計

### 10.1. EnvParser

```python
class EnvParser:
    """環境変数のパース処理。env_prefix ベースで全ての環境変数名を導出する。"""

    @staticmethod
    def parse_global_level(env_value: str) -> str | None:
        """
        {prefix}_LEVEL 環境変数の値をパースする。
        グローバルレベルのみを受け付け、カンマ区切りのモジュール別構文は拒否する。

        Returns:
            グローバルレベル文字列 or None（空文字列の場合）

        Raises:
            ValueError: カンマが含まれている場合（移行ガイド付きエラー）
        """
        if not env_value or not env_value.strip():
            return None

        value = env_value.strip()

        # カンマを含む場合は Fail-Fast
        if ',' in value:
            raise ValueError(
                f"{value!r} contains comma-separated module specs. "
                f"Use the _MODULES env var for per-module settings. "
                f"Example: _LEVEL=INFO  _MODULES=ModuleA:DEBUG,ModuleB:ERROR"
            )

        return value.upper()

    @staticmethod
    def parse_modules_env(env_value: str) -> dict[str, dict]:
        """
        {prefix}_MODULES 環境変数の値をパースする。

        書式: MOD:LEVEL[,MOD:LEVEL[:PATH],...]

        Returns:
            {module_name: {'level': str, 'path': str | None}}
        """
        if not env_value or not env_value.strip():
            return {}

        parts = [p.strip() for p in env_value.split(',')]
        module_configs = {}

        for part in parts:
            if not part:
                continue

            # Windows 絶対パス対応: 最大2分割（例: 'mod:DEBUG:C:\path\log.log' → 3要素）
            segments = part.split(':', 2)
            if len(segments) == 2:
                mod_name, level = segments
                module_configs[mod_name] = {'level': level.upper(), 'path': None}
            elif len(segments) == 3:
                mod_name, level, path = segments
                module_configs[mod_name] = {'level': level.upper(), 'path': path}
            else:
                print(f'[D-SafeLogger] Invalid module spec in env, skipped: {part}',
                      file=sys.stderr)

        return module_configs

    @staticmethod
    def parse_bool_env(env_value: str | None) -> bool | None:
        """{prefix}_CONSOLE / {prefix}_COLOR 用の真偽値パーサ。
        "1"/"true" → True, "0"/"false" → False, それ以外/None → None（上書きしない）"""
        if env_value is None:
            return None
        v = env_value.strip().lower()
        if v in ('1', 'true'):
            return True
        if v in ('0', 'false'):
            return False
        return None

    @staticmethod
    def parse_config_path(env_value: str | None) -> str | None:
        """{prefix}_CONFIG 環境変数の値をパースする。
        空文字列は None として扱う。"""
        if env_value is None:
            return None
        v = env_value.strip()
        return v if v else None

    @staticmethod
    def parse_ipc_log_timeout(env_value: str | None) -> float | None:
        """{prefix}_IPC_LOG_TIMEOUT 環境変数の値をパースする。
        multiprocess log plane の put timeout を秒で受け取る。"""
        if env_value is None:
            return None
        v = env_value.strip()
        if not v:
            return None
        timeout = float(v)
        if timeout <= 0:
            raise ValueError(f'ipc_log_timeout must be > 0, got {env_value!r}')
        return timeout

    @staticmethod
    def resolve_env_names(env_prefix: str) -> dict[str, str]:
        """env_prefix から各環境変数名を導出する。

        Returns:
            {'level': 'D_LOG_LEVEL', 'modules': 'D_LOG_MODULES', ...}
        """
        return {
            'level': f'{env_prefix}_LEVEL',
            'modules': f'{env_prefix}_MODULES',
            'config': f'{env_prefix}_CONFIG',
            'console': f'{env_prefix}_CONSOLE',
            'color': f'{env_prefix}_COLOR',
            'diagnose': f'{env_prefix}_DIAGNOSE',
            'hash': f'{env_prefix}_HASH',
            'manifest': f'{env_prefix}_MANIFEST',
            'ipc_log_timeout': f'{env_prefix}_IPC_LOG_TIMEOUT',
        }

    @staticmethod
    def parse_hash_env(env_value: str | None) -> bool | None:
        """{prefix}_HASH 環境変数の値をパースする。
        "1"/"true" → True, "0"/"false" → False, それ以外/None → None（上書きしない）"""
        if env_value is None:
            return None
        v = env_value.strip().lower()
        if v in ('1', 'true'):
            return True
        if v in ('0', 'false'):
            return False
        return None

    @staticmethod
    def parse_manifest_env(env_value: str | None) -> str | None:
        """{prefix}_MANIFEST 環境変数の値をパースする。
        空文字列は None として扱う。"""
        if env_value is None:
            return None
        v = env_value.strip()
        return v if v else None
```

### 10.2. `{prefix}_DIAGNOSE` のパース

- `os.environ.get(f'{env_prefix}_DIAGNOSE')` の値が文字列 `"1"` の場合のみ有効化する。
- `"true"`, `"yes"`, `"True"` 等は有効としない（明示的かつ最小限のインターフェース）。
- **`ConfigureLogger` の引数およびINIファイルからは設定不可**（聖域保護）。

### 10.3. `{prefix}_COLOR` / `NO_COLOR` の優先順位

```
NO_COLOR が設定されている（値を問わない） → カラー無効（業界標準 https://no-color.org/）
  ↓ (NO_COLOR 未設定時)
{prefix}_COLOR が設定されている → parse_bool_env() の結果に従う
  ↓ ({prefix}_COLOR 未設定時)
sys.stderr.isatty() → True ならカラー有効（TTY判定）
```

---

## 11. コンテキスト管理詳細設計

### 11.1. contextvars ベースの実装

`threading.local()` からの移行。`contextvars.ContextVar` は Python 3.7 以降で使用可能であり、以下の利点を持つ：

- **asyncio タスク間でのコンテキスト分離**: `asyncio.create_task()` 時に自動的にコンテキストがコピーされ、タスク間で独立する。
- **`Token` による巻き戻し**: `ContextVar.set()` が返す `Token` を `reset()` に渡すことで、正確に元の状態に復元される。ネストした `contextualize()` でも安全。

### 11.2. ContextVar の定義とライフサイクル

```python
# _context.py
import contextvars
from types import MappingProxyType

_EMPTY_CONTEXT: MappingProxyType = MappingProxyType({})

_log_context: contextvars.ContextVar[MappingProxyType] = contextvars.ContextVar(
    'dsafelogger_context', default=_EMPTY_CONTEXT
)

def get_context() -> MappingProxyType:
    return _log_context.get()

def set_context(data: MappingProxyType) -> contextvars.Token:
    return _log_context.set(data)

def reset_context(token: contextvars.Token) -> None:
    _log_context.reset(token)
```

---

## 12. コンソールカラー出力詳細設計

### 12.1. ANSI カラーマッピング

| レベル略称 | ANSI コード | 色 |
|-----------|------------|-----|
| `DBG` | `\033[36m` | シアン |
| `INF` | `\033[32m` | グリーン |
| `WAR` | `\033[33m` | イエロー |
| `ERR` | `\033[31m` | レッド |
| `CRI` | `\033[1;31m` | ボールドレッド |

リセット: `\033[0m`

### 12.2. ColorStreamHandler

```python
from dsafelogger._levels import get_all_color_map, get_all_level_map

class ColorStreamHandler(logging.StreamHandler):
    # クラス変数はビルトインのみ保持（後方互換・フォールバック用）
    _BUILTIN_COLOR_MAP = {
        'DBG': '\033[36m', 'INF': '\033[32m', 'WAR': '\033[33m',
        'ERR': '\033[31m', 'CRI': '\033[1;31m',
    }
    RESET = '\033[0m'
    # スレッドローカル proxy 再利用（DSafeFormatter._proxy_tls とは別スロット）
    _proxy_tls: threading.local = _make_proxy_tls()

    def __init__(
        self,
        stream=None,
        color_enabled: bool = True,
        color_overrides: dict[str, str] | None = None,  # v17: INI/辞書からのカラーオーバーライド
    ):
        super().__init__(stream or sys.stderr)
        self._color_enabled = color_enabled
        # インスタンス変数として統合カラーマップを構築（ビルトイン + カスタムレベル + INI/辞書オーバーライド）
        self.COLOR_MAP = get_all_color_map(overrides=color_overrides)
        self.LEVEL_MAP = get_all_level_map()

    def emit(self, record: logging.LogRecord) -> None:
        if self._color_enabled:
            resolved_level = self.LEVEL_MAP.get(record.levelname, record.levelname)
            color = self.COLOR_MAP.get(resolved_level, '')
            if color:
                # v21: ANSI 付き levelname も render 時だけ上書きする。
                # 共有 LogRecord を変更せず、DSafeFormatter と同じ表示解決経路に合わせる。
                # TLS proxy を再利用して per-call アロケーションを排除する。
                coloured_level = f'{color}{resolved_level}{self.RESET}'
                proxy = getattr(self._proxy_tls, 'instance', None)
                if proxy is None:
                    proxy = object.__new__(_DisplayRecordProxy)
                    self._proxy_tls.instance = proxy
                proxy.__dict__.clear()
                proxy.__dict__.update(record.__dict__)
                proxy.__dict__['levelname'] = coloured_level
                super().emit(proxy)
                return
        super().emit(record)
```

> **v21 実装方針**: `ColorStreamHandler` は ANSI 色付きの表示用 `levelname` を proxy 上でのみ解決する。TLS proxy 再利用により per-call アロケーションがなく、file handler / JSON formatter / 他の consumer に ANSI コードが漏れない。`_proxy_tls` は `DSafeFormatter._proxy_tls` とは別の `threading.local` インスタンスを使うことで、`DSafeFormatter` がこのハンドラのフォーマッタとして設定された場合の self-reference corruption を防ぐ。

### 12.3. Windows VT100 有効化

```python
def _enable_windows_vt100() -> None:
    """Windows 10+ で ANSI エスケープシーケンスを有効化するハック。"""
    if sys.platform == 'win32':
        os.system('')  # conhost.exe に VT100 モードを有効化させる
```

`ConfigureLogger` の初期化フローで `console_out=True` かつカラー有効時に一度だけ呼び出す。

---

## 13. CLI ツール (`dsafelogger`) 詳細設計

### 13.1. エントリポイント

`pyproject.toml` の `[project.scripts]` セクション:
```toml
[project.scripts]
dsafelogger = "dsafelogger._cli:main"
```

### 13.2. argparse サブコマンド設計

```python
import argparse

def main():
    parser = argparse.ArgumentParser(
        prog='dsafelogger',
        description='D-SafeLogger CLI ユーティリティ',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # init サブコマンド
    subparsers.add_parser('init', help='INI設定テンプレートを標準出力に出力')

    # ls サブコマンド
    ls_parser = subparsers.add_parser('ls', help='ログファイル一覧を表示')
    ls_parser.add_argument('log_dir', nargs='?', default='.',
                          help='ログディレクトリのパス（デフォルト: カレント）')

    # tail サブコマンド
    tail_parser = subparsers.add_parser('tail', help='ログファイルをリアルタイム追随')
    tail_parser.add_argument('-f', '--follow', action='store_true', required=True,
                            help='ファイルを追随する')
    tail_parser.add_argument('log_dir', help='ログディレクトリのパス')
    tail_parser.add_argument('pg_name', help='追随対象のプログラム名（pg_name）')
    tail_parser.add_argument('-n', '--lines', type=int, default=10,
                            help='初期表示行数（デフォルト: 10）')
    tail_parser.add_argument('--poll-interval', type=float, default=0.5,
                            help='ポーリング間隔秒（デフォルト: 0.5）')

    args = parser.parse_args()

    if args.command == 'init':
        cmd_init()
    elif args.command == 'ls':
        cmd_ls(args.log_dir)
    elif args.command == 'tail':
        cmd_tail(args.log_dir, args.pg_name, args.lines, args.poll_interval)
```

### 13.3. `init` コマンド実装方針

テンプレート文字列をモジュール定数として保持し、標準出力に `print()` するだけの単純な実装とする。ファイルパスを引数に取らないため、上書き確認等のロジックは不要。ユーザーはシェルリダイレクト (`> file`) やパイプ (`| less`) で出力先を制御する。

```python
INI_TEMPLATE = """\
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
; file_fmt =
; console_fmt =
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
;   Values are SGR parameter numbers (without \\033[ prefix and m suffix).
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
"""


def cmd_init() -> None:
    """INI設定ファイルのテンプレートを標準出力に出力する。"""
    print(INI_TEMPLATE, end='')
```

### 13.4. `ls` コマンド実装方針

```python
def cmd_ls(log_dir: str) -> None:
    """ディレクトリ内の D-SafeLogger ファイルを解析し、
    pg_name ごとに最新のアクティブファイルを一覧表示する。"""
    from pathlib import Path

    log_path = Path(log_dir)
    if not log_path.is_dir():
        print(f'Error: "{log_dir}" is not a directory.', file=sys.stderr)
        sys.exit(1)

    # *.log ファイルを pg_name ごとにグルーピング
    files = sorted(log_path.glob('*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
    groups: dict[str, list[Path]] = {}
    for f in files:
        # サフィックスからpg_nameを推定（最後の _ 以前の部分）
        name = f.stem
        # ... pg_name の抽出ロジック ...
        groups.setdefault(pg_name, []).append(f)

    for pg_name, file_list in groups.items():
        latest = file_list[0]
        print(f'{pg_name:20s}  {latest.name:40s}  '
              f'{latest.stat().st_size:>10,} bytes  '
              f'{datetime.fromtimestamp(latest.stat().st_mtime):%Y-%m-%d %H:%M:%S}')
```

### 13.5. `tail -f` コマンド：透過的ファイル追随の実装方針

```python
def cmd_tail(log_dir: str, pg_name: str, initial_lines: int, poll_interval: float) -> None:
    """最新ログファイルを追随し、ファイル切り替え時も透過的に追随を継続する。"""
    from pathlib import Path
    import time

    log_path = Path(log_dir)
    current_file: Path | None = None
    file_handle = None
    position: int = 0

    try:
        while True:
            # 最新ファイルを特定（pg_name にマッチする最新の *.log）
            candidates = sorted(
                log_path.glob(f'{pg_name}_*.log'),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not candidates:
                # none モードの単一ファイルもチェック
                single = log_path / f'{pg_name}.log'
                if single.exists():
                    candidates = [single]

            if not candidates:
                time.sleep(poll_interval)
                continue

            latest = candidates[0]

            # ファイル切り替え検知
            if latest != current_file:
                # 切り替え前に旧ファイルの未読行を読み切る（ログ欠損防止）
                if file_handle:
                    file_handle.seek(position)
                    remaining = file_handle.readlines()
                    for line in remaining:
                        print(line, end='')
                    file_handle.close()

                current_file = latest
                file_handle = open(current_file, 'r', encoding='utf-8')
                # 初回（または新ファイル）は末尾 N 行を表示
                lines = file_handle.readlines()
                for line in lines[-initial_lines:]:
                    print(line, end='')
                position = file_handle.tell()
            else:
                # 同一ファイルの新規行を読み取り
                file_handle.seek(position)
                new_lines = file_handle.readlines()
                for line in new_lines:
                    print(line, end='')
                position = file_handle.tell()

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        pass
    finally:
        if file_handle:
            file_handle.close()
```

---

## 14. カスタムログレベル管理 (`_levels.py`) 詳細設計

### 14.1. モジュール概要

`_levels.py` はカスタムログレベルの登録情報を一元管理するモジュールである。`register_level()` 公開API関数の実体と、各コンポーネントが統合マップを取得するためのクエリ関数群を提供する。

### 14.2. 内部データ構造

```python
import logging

# ビルトインレベルの不可侵セット
_BUILTIN_VALUES: frozenset[int] = frozenset({10, 20, 30, 40, 50})
_BUILTIN_ABBREVIATIONS: frozenset[str] = frozenset({'DBG', 'INF', 'WAR', 'ERR', 'CRI'})
_BUILTIN_NAMES: frozenset[str] = frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'})

# カスタムレベルの登録ストア
# key: name (str), value: (value: int, abbreviation: str, color: str)
_custom_levels: dict[str, tuple[int, str, str]] = {}
```

### 14.3. `register_level` 関数

```python
def register_level(
    name: str,
    value: int,
    abbreviation: str,
    color: str = '',
) -> None:
    from dsafelogger import _configure_state, _lifecycle_lock

    # v20: free-threaded Python 対応。全体を _lifecycle_lock で保護
    with _lifecycle_lock:
        # ── Fail-Fast: ConfigureLogger 呼び出し後の登録を禁止 ──
        if _configure_state != 'unconfigured':
            raise RuntimeError(
                'register_level() must be called before ConfigureLogger(). '
                'Custom levels cannot be added after logger initialization.'
            )

        # ── バリデーション ──
        name_upper = name.strip().upper()
        abbr_upper = abbreviation.strip().upper()

        if not name_upper:
            raise ValueError('name must not be empty')

        if value <= 0:
            raise ValueError(f'value must be > 0, got {value}')

        if value in _BUILTIN_VALUES:
            raise ValueError(
                f'Cannot override built-in level value {value}. '
                f'Built-in values are: {sorted(_BUILTIN_VALUES)}'
            )

        if name_upper in _BUILTIN_NAMES:
            raise ValueError(
                f'Cannot override built-in level name {name_upper!r}'
            )

        if len(abbr_upper) != 3:
            raise ValueError(
                f'abbreviation must be exactly 3 characters, got {abbr_upper!r} '
                f'(length={len(abbr_upper)})'
            )

        if abbr_upper in _BUILTIN_ABBREVIATIONS:
            raise ValueError(
                f'abbreviation {abbr_upper!r} conflicts with built-in abbreviation'
            )

        # 既登録との重複チェック
        for existing_name, (existing_value, existing_abbr, _) in _custom_levels.items():
            if value == existing_value:
                if name_upper == existing_name and abbr_upper == existing_abbr:
                    return  # v22h: spawn 再 import 対応。same-definition 再登録は no-op
                raise RuntimeError(
                    f'value {value} conflicts with existing level {existing_name!r}'
                )
            if abbr_upper == existing_abbr:
                if name_upper == existing_name and value == existing_value:
                    return  # same-definition 再登録
                raise RuntimeError(
                    f'abbreviation {abbr_upper!r} conflicts with existing level {existing_name!r}'
                )
            if name_upper == existing_name:
                if value == existing_value and abbr_upper == existing_abbr:
                    return  # same-definition 再登録
                raise RuntimeError(
                    f'level {name_upper!r} is already registered with a different definition'
                )

        # ── 標準 logging への登録 ──
        logging.addLevelName(value, name_upper)

        # ── 内部ストアへの登録 ──
        _custom_levels[name_upper] = (value, abbr_upper, color)
```

> v20: `register_level()` 全体を `_lifecycle_lock` で保護し、free-threaded Python (3.13+) での並行呼び出しによる `_custom_levels` 破損を防止する。

- `_configure_state == 'shutting_down'` も上記の拒否条件に含む。終了処理中の追加登録は shared state の整合を壊しうるため認めない。
- `spawn` による worker 再 import を考慮し、**同一定義**（name/value/abbreviation/color が一致）の再登録は no-op とする。一方、不一致再登録は registry divergence とみなし `RuntimeError` とする。

### 14.4. クエリ関数群

```python
def get_all_level_map() -> dict[str, str]:
    """ビルトイン + カスタムの統合 LEVEL_MAP を返す。
    Formatter 初期化時に呼び出される。"""
    merged = {
        'DEBUG': 'DBG', 'INFO': 'INF', 'WARNING': 'WAR',
        'ERROR': 'ERR', 'CRITICAL': 'CRI',
    }
    for name, (_, abbr, _) in _custom_levels.items():
        merged[name] = abbr
    return merged


def get_all_color_map(
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """ビルトイン + カスタム + INI/辞書オーバーライドの統合 COLOR_MAP を返す。
    ColorStreamHandler 初期化時に呼び出される。

    Args:
        overrides: INI/辞書から読み込まれた {略称(大文字): ANSIコード数値部分} の辞書。
                   ビルトイン・カスタムのカラーを上書きする。None の場合は上書きなし。
                   （v17 追加: overrides 引数。引数なし呼び出しは後方互換を維持）
    """
    merged = {
        'DBG': '\033[36m', 'INF': '\033[32m', 'WAR': '\033[33m',
        'ERR': '\033[31m', 'CRI': '\033[1;31m',
    }
    for name, (_, abbr, color) in _custom_levels.items():
        if color:
            merged[abbr] = color

    # v17: INI/辞書からのオーバーライド
    if overrides:
        for abbr, code in overrides.items():
            if code == '':
                # 空文字列 = カラー無効化（キーを削除）
                merged.pop(abbr, None)
            else:
                merged[abbr] = f'\033[{code}m'

    return merged


def get_valid_level_names() -> set[str]:
    """バリデーションで有効なレベル名の集合を返す。
    EnvParser / IniLoader のレベルバリデーションで使用。"""
    names = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    names.update(_custom_levels.keys())
    return names


def get_valid_abbreviations() -> set[str]:
    """有効な略称の集合を返す（ビルトイン5段階 + カスタムレベル）。
    v17: カラーパレットの color_{略称} キーのバリデーションで使用。
    IniLoader._parse_color_palette() / DictLoader._parse_color_palette() に渡される。"""
    abbrs = {'DBG', 'INF', 'WAR', 'ERR', 'CRI'}
    for _, (_, abbr, _) in _custom_levels.items():
        abbrs.add(abbr)
    return abbrs
```

### 14.5. 便利メソッドインストール

```python
def install_convenience_methods(logger_class: type) -> None:
    """DSafeLogger クラスにカスタムレベルの便利メソッドを動的に追加する。
    ConfigureLogger 内の setLoggerClass 直後に呼び出される。

    例: register_level('TRACE', 5, 'TRC') → logger.trace(msg, *args, **kwargs)
    """
    for name, (value, _, _) in _custom_levels.items():
        method_name = name.lower()

        # 既存メソッドとの衝突を防止
        if hasattr(logger_class, method_name):
            continue

        def _make_log_method(level_value: int):
            def log_method(self, msg, *args, **kwargs):
                if self.isEnabledFor(level_value):
                    self._log(level_value, msg, args, **kwargs)
            return log_method

        setattr(logger_class, method_name, _make_log_method(value))
```

### 14.6. 呼び出し順序の制約

```
register_level()    ← 任意回数（0回でもよい）
     ↓
ConfigureLogger()   ← 1回のみ（冪等性チェックあり）
     ↓
GetLogger()         ← 任意回数
```

`ConfigureLogger()` 後の `register_level()` は `RuntimeError`。この制約により、Formatter / Handler / バリデーションが初期化後に不整合を起こすことを構造的に防止する。

---

## 15. ファイル完全性検証 (`_integrity.py`) 詳細設計

### 15.1. モジュール概要

`_integrity.py` はファイル完全性検証に関する処理を提供するモジュールである。SHA-256 ハッシュの計算、サイドカーファイルの生成、マニフェストファイルへの追記、および非同期ハッシュ生成ワーカースレッドを実装する。

### 15.2. ハッシュ計算関数

```python
import hashlib
import os
from datetime import datetime
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    """ファイルの SHA-256 ハッシュを計算する。
    大容量ファイル対応のためチャンク読みする（64KB 単位）。"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(65536)  # 64KB チャンク
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()
```

### 15.3. サイドカーファイル生成

```python
def write_sidecar(file_path: Path, hash_value: str | None = None) -> None:
    """対象ファイルの .sha256 サイドカーファイルを生成する。
    出力フォーマットは sha256sum -c 互換（ハッシュ + スペース2つ + ファイル名）。
    v20: hash_value を引数で受け取り、二重計算を防止。未指定時は内部計算。"""
    if hash_value is None:
        hash_value = compute_sha256(file_path)
    sidecar_path = file_path.with_suffix(file_path.suffix + '.sha256')
    temp_path = sidecar_path.with_suffix(sidecar_path.suffix + '.tmp')
    temp_path.write_text(
        f'{hash_value}  {file_path.name}\n',
        encoding='utf-8',
    )
    os.replace(temp_path, sidecar_path)
```

#### 出力例

```
a1b2c3d4e5f6789...（64文字の16進SHA-256ハッシュ）  MyApp_20260328.log
```

検証: `sha256sum -c MyApp_20260328.log.sha256`

### 15.4. マニフェスト追記

```python
def append_manifest(file_path: Path, manifest_path: Path, hash_value: str | None = None) -> None:
    """マニフェストファイルにハッシュエントリを追記する。
    ディレクトリが存在しない場合は自動生成する。
    v20: hash_value を引数で受け取り、二重計算を防止。未指定時は内部計算。"""
    if hash_value is None:
        hash_value = compute_sha256(file_path)
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%dT%H:%M:%S.') + f'{now.microsecond // 1000:03d}'
    entry = f'[{timestamp}] {hash_value}  {file_path.name}\n'

    # ディレクトリの自動生成
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    lock = _get_manifest_lock(manifest_path.resolve())
    # Lock ordering: family_lock -> manifest_lock (never reverse)
    # Do NOT acquire family maintenance lock while holding this lock
    with lock:
        with open(manifest_path, 'a', encoding='utf-8') as f:
            f.write(entry)
```

#### v18 追加

- 同一 `manifest_path` への追記は key 単位 lock で直列化する
- `.sha256` sidecar は temp file + `os.replace()` により原子的に更新する

#### マニフェストフォーマット

```
[2026-03-28T23:59:59.123] a1b2c3d4e5f6789...  MyApp_20260328.log
[2026-03-29T23:59:59.456] b2c3d4e5f6789a1...  MyApp_20260329.log
```

各行の構成: `[ISO8601タイムスタンプ] SHA-256ハッシュ  ファイル名`

### 15.5. HashWorker スレッド

```python
import threading
import sys


class HashWorker(threading.Thread):
    """Fire-and-Forget でハッシュ生成を行うワーカースレッド。
    backup_count=0 かつ enable_hash=True の場合に使用される。
    backup_count > 0 の場合はPurgeWorker/ArchiveWorker 内でハッシュ生成が先行実行される。"""

    def __init__(self, file_path: Path, manifest_path: Path | None = None):
        super().__init__(daemon=True, name=f'HashWorker-{file_path.name}')
        self._file_path = file_path
        self._manifest_path = manifest_path

    def run(self) -> None:
        try:
            def _run_body() -> None:
                write_sidecar(self._file_path)

                if self._manifest_path is not None:
                    append_manifest(self._file_path, self._manifest_path)

            _run_in_empty_context(_run_body)

        except OSError as e:
            # パージの自己修復性と同様、失敗時は警告のみで続行
            print(
                f'[D-SafeLogger] Hash generation failed for '
                f'{self._file_path.name}: {e}',
                file=sys.stderr,
            )
        finally:
            _unregister_worker(self)
```

### 15.6. 実行方式の判定

| 条件 | 実行方式 |
|------|---------|
| `enable_hash=True` かつ non-cyclic かつ `backup_count > 0` | `PurgeWorker` / `ArchiveWorker` 内でハッシュ生成を先行実行 |
| `enable_hash=True` かつ non-cyclic かつ `backup_count=0` | 独立した `HashWorker` を Fire-and-Forget で起動 |
| cyclic 系 routing かつ `enable_hash=True` | `ConfigureLogger()` 時に Fail-Fast（`ValueError`） |
| `enable_hash=False` | ハッシュ関連処理なし（v14 と同一動作） |

---

## 15a. Transport 層詳細設計（v20 新規）

### 15a.1. Transport 抽象基底クラス

```python
from abc import ABC, abstractmethod

class Transport(ABC):
    """Capture 層から Sink 層へのイベント転送を抽象化する。
    v20 で導入。将来の IPCTransport 追加を最小変更で実現可能にする。"""

    @abstractmethod
    def start(self) -> None:
        """トランスポートを開始する。"""
        ...

    @abstractmethod
    def stop(self, timeout: float) -> bool:
        """トランスポートを停止する。
        Returns: True なら正常停止、False ならタイムアウト。"""
        ...

    @abstractmethod
    def get_root_handlers(self) -> list[logging.Handler]:
        """root logger へ attach すべき Handler 群を返す。"""
        ...

    @abstractmethod
    def get_sink_handlers(self) -> list[logging.Handler]:
        """writer-side の実 Sink Handler 群を返す。
        ReopenLogFiles() は本メソッドで収集した handler を対象にする。"""
        ...
```

### 15a.2. DirectTransport (sync mode)

```python
class DirectTransport(Transport):
    """sync mode 用。Capture 層から Sink Handler へ直接委譲する。
    v18 までの同期モードと同一の動作。"""

    def __init__(self, handlers: list[logging.Handler]):
        self._handlers = handlers

    def start(self) -> None:
        pass  # sync は開始処理不要

    def stop(self, timeout: float) -> bool:
        # v20: 部分失敗時も全 handler の処理を試行
        errors: list[Exception] = []
        for h in self._handlers:
            try:
                h.flush()
                h.close()
            except Exception as e:
                errors.append(e)
        if errors:
            print(
                f'[D-SafeLogger] DirectTransport.stop: {len(errors)} handler(s) failed',
                file=sys.stderr,
            )
        return not errors

    def get_root_handlers(self) -> list[logging.Handler]:
        return self._handlers

    def get_sink_handlers(self) -> list[logging.Handler]:
        return self._handlers
```

### 15a.3. QueueTransport (async mode)

```python
class QueueTransport(Transport):
    """async mode 用。DSafeQueueHandler / DSafeQueueListener をラップする。
    v18 までの非同期モードを Transport 抽象で包装。"""

    def __init__(self, handlers: list[logging.Handler], **kwargs):
        self._queue = queue.Queue(-1)
        self._queue_handler = DSafeQueueHandler(self._queue, **kwargs)
        self._listener = DSafeQueueListener(self._queue, *handlers)

    def start(self) -> None:
        self._listener.start()

    def stop(self, timeout: float) -> bool:
        return self._listener.stop_with_timeout(timeout)

    def get_root_handlers(self) -> list[logging.Handler]:
        return [self._queue_handler]

    def get_sink_handlers(self) -> list[logging.Handler]:
        return list(self._listener.handlers)
```

### 15a.4. TransportFactory

```python
class TransportFactory:
    """single-process の is_async に応じて適切な Transport を生成する。"""

    @staticmethod
    def create(
        is_async: bool,
        handlers: list[logging.Handler],
        **kwargs,
    ) -> Transport:
        if is_async:
            return QueueTransport(handlers, **kwargs)
        return DirectTransport(handlers)
```

`TransportFactory` は single-process runtime 専用である。multiprocess hand-off は `dsafelogger.mp` 側の attach/runtime 層が担当し、この factory に multiprocess 分岐は持ち込まない。

### 15a.5. multiprocess runtime 詳細設計（v22i 正式設計）

#### 15a.5.1. protocol payload

```python
@dataclass(frozen=True)
class BootstrapContext:
    protocol_version: int
    session_id: str
    writer_pid: int
    log_queue: multiprocessing.Queue
    control_queue: multiprocessing.Queue
    resolved_config: dict[str, object]
    resolved_config_digest: str
    registry_hash: str
    log_queue_maxsize: int
    ipc_log_timeout: float
    overflow_policy: Literal['drop']

# v22i: control plane reply path は per-request の Pipe(duplex=False) を使う。
# Queue を別 Queue の payload に含める Queue-in-Queue 方式は
# multiprocessing の ForkingPickler 制約により成立しないため採用しない。


class LogEvent(TypedDict):
    name: str
    levelno: int
    levelname: str
    pathname: str
    filename: str
    module: str
    lineno: int
    funcName: str
    msg: str
    created: float
    msecs: float
    relativeCreated: float
    process: int
    processName: str
    thread: int
    threadName: str
    _ds_route: str
    _ds_context: dict[str, Any]
    _ds_exc_text: str | None
    _ds_diag_frames: list[dict[str, Any]] | None
    _ds_extra: dict[str, Any]


class ControlRequest(TypedDict):
    request_id: str
    client_id: str
    command: Literal['ATTACH', 'DETACH', 'REOPEN', 'STOP', 'STATUS']
    reply_to: Any  # multiprocessing.connection.Connection (Pipe send end)
    payload: dict[str, Any]


class ControlAck(TypedDict):
    request_id: str
    success: bool
    error_category: str | None
    error_message: str | None
    result: dict[str, Any]
```

#### 15a.5.2. `_serialize_record()` / `_reconstruct_record()`

- `LogEvent` は client 側 Capture 境界で確定する
- `_ds_context` と `_ds_extra` は常に key を持ち、空は `{}` とする
- diagnose snapshot は client 側で確定し、Writer 側で live traceback / live context を再評価しない
- `_reconstruct_record()` は `logging.makeLogRecord()` を使って sink dispatch 用 `LogRecord` を復元するだけであり、logger 階層評価や level 判定は再実行しない

#### 15a.5.2a. `_writer_formatter.py`

- `_writer_formatter.py` は、Writer runtime が sink graph を構築する際の formatter 解決 helper を提供する
- client 側の `fmt` / `file_fmt` / `console_fmt` 由来 raw spec を Writer 側で再構築し、root / module sink group に適用する
- Writer runtime 自体は `LogEvent` を `LogRecord` に再構築して既存 formatter / handler 群へ dispatch するため、`_writer_formatter.py` は独立の公開 formatter クラスを提供する必須モジュールではない

```python
class FormatterSpec(TypedDict, total=False):
    kind: Literal[
        'logging.Formatter',
        'DSafeFormatter',
        'DiagnosticFormatter',
        'StructuredFormatter',
        'DiagnosticStructuredFormatter',
    ]
    fmt: str | None
    datefmt: str | None
    style: Literal['%', '{', '$']
    defaults: dict[str, object] | None
    sensitive_keywords: tuple[str, ...] | None
```

- freeze 許容は **exact type 一致** のみとし、custom subclass は `kind` が同名でも受理しない
- `logging.Formatter` / `DSafeFormatter` は `fmt` / `datefmt` / `style`（必要なら `defaults`）を spec へ落とす
- `defaults` 取得時は Python バージョン差異を吸収するため、`instance.defaults` / `instance._defaults` / `instance._style._defaults` の順で探索する
- `DiagnosticFormatter` は上記に加えて `sensitive_keywords` を spec 化する
- `StructuredFormatter` は `kind='StructuredFormatter'` のみで再構築できる
- `DiagnosticStructuredFormatter` は `kind='DiagnosticStructuredFormatter'` と `sensitive_keywords` で再構築する
- Writer 側は `FormatterSpec.kind` に基づく固定ディスパッチで再構築し、任意 class import や pickle 復元には依存しない

```python
_STD_RECORD_RESERVED_KEYS: frozenset[str] = frozenset({
    'name', 'msg', 'args', 'levelname', 'levelno',
    'pathname', 'filename', 'module', 'exc_info', 'exc_text',
    'stack_info', 'lineno', 'funcName', 'created', 'msecs',
    'relativeCreated', 'thread', 'threadName', 'process',
    'processName', 'message', 'asctime', 'taskName',
})


def _is_reserved_key(key: str) -> bool:
    return key in _STD_RECORD_RESERVED_KEYS or key.startswith('_ds_')
```

#### 15a.5.3. client-side transport

```python
class MPClientTransport:
    def __init__(self, ctx: BootstrapContext, *, is_async: bool, ds_route: str) -> None:
        self._ctx = ctx
        self._is_async = is_async
        self._ds_route = ds_route
        self._local_queue = queue.Queue(maxsize=ctx.ipc_client_queue_maxsize) if is_async else None
        self._pump_thread: threading.Thread | None = None
        self._drop_counter = 0
        self._overload_shed = 0
        self._transport_closed_drop = 0
        self._writer_unavailable_drop = 0
        self._timeout_drop = 0
        self._closed = False
        self._stopping = False
        self._writer_dead = False

    def start(self) -> None:
        if self._local_queue is None:
            return
        if self._pump_thread is not None and self._pump_thread.is_alive():
            return
        self._pump_thread = threading.Thread(
            target=lambda: _run_in_empty_context(self._pump_loop),
            name='D-SafeLogger-MPClientPump',
            daemon=True,
        )
        self._pump_thread.start()

    def stop(self, timeout: float) -> bool:
        if self._closed:
            return True
        self._stopping = True
        if self._local_queue is not None:
            try:
                self._local_queue.put(None, timeout=timeout)
            except queue.Full:
                self._closed = True
                return False
        else:
            self._closed = True
            return True
        if self._pump_thread is None:
            self._closed = True
            return True
        self._pump_thread.join(timeout)
        stopped = not self._pump_thread.is_alive()
        self._closed = True
        return stopped

    def emit(self, record: logging.LogRecord) -> None:
        if self._closed or self._stopping:
            self._record_drop('transport closed')
            return
        if self._writer_dead:
            self._record_drop('writer unavailable')
            return
        event = _serialize_record(record, self._ds_route)
        if self._local_queue is None:
            self._send_log_event(event)
            return
        try:
            self._local_queue.put_nowait(event)
        except queue.Full:
            self._record_drop('process-local async queue full')

    def _pump_loop(self) -> None:
        while True:
            event = self._local_queue.get()
            if event is None:
                return
            self._send_log_event(event)

    def _send_log_event(self, event: LogEvent) -> None:
        if self._closed:
            self._record_drop('transport closed')
            return
        try:
            self._ctx.log_queue.put(event, block=True, timeout=self._ctx.ipc_log_timeout)
        except queue.Full:
            self._record_drop('log plane timeout/full')
        except (BrokenPipeError, EOFError, OSError, ValueError):
            self._writer_dead = True
            self._record_drop('writer unavailable')

    def _record_drop(self, reason: str) -> None:
        self._drop_counter += 1
        if reason == 'process-local async queue full':
            self._overload_shed += 1
        elif reason == 'transport closed':
            self._transport_closed_drop += 1
        elif reason == 'writer unavailable':
            self._writer_unavailable_drop += 1
        elif reason == 'log plane timeout/full':
            self._timeout_drop += 1
        if self._drop_counter == 1 or self._drop_counter % 100 == 0:
            print(
                f'[D-SafeLogger] multiprocess log dropped ({reason}, count={self._drop_counter})',
                file=sys.stderr,
            )
```

- process-local async queue は **bounded** とし、`ctx.ipc_client_queue_maxsize` を用いる。未指定時は `ipc_client_queue_maxsize == ipc_log_queue_maxsize` となる
- `stop()` 後の `emit()` は event を local queue へ積まず、drop + warning とする

#### 15a.5.4. `AttachCurrentProcess()`

```python
@dataclass
class MPProcessState:
    session_id: str
    ctx: BootstrapContext
    client_id: str
    root_transport: MPClientTransport
    module_transports: dict[str, MPClientTransport]


def AttachCurrentProcess(ctx: BootstrapContext) -> None:
    # v22i: 3-phase。lock 下での state 判定と予約、lock 外で control plane ACK 待機、
    # 最後に lock 下で process-local state を確定する。
    with _mp_lifecycle_lock:
        if _mp_runtime_state is not None and _mp_runtime_state.session_id == ctx.session_id:
            # v22i: same process の再 attach だけを no-op とする。fork child は
            # 親の client_id を流用せず、新しい client_id で ATTACH し直す。
            if _same_process_identity(_mp_runtime_state):
                _rehydrate_fork_inherited_runtime_if_needed(_mp_runtime_state)
                return
        if _mp_runtime_state is not None and _mp_runtime_state.session_id != ctx.session_id:
            raise RuntimeError('Current process already attached to another Writer session')

        _validate_bootstrap_context(ctx)
        _validate_protocol_version(ctx.protocol_version)
        _validate_registry_hash(ctx.registry_hash)
        send_conn, recv_conn = multiprocessing.Pipe(duplex=False)
        req = _make_attach_request(ctx, send_conn)
    _send_control_request(ctx.control_queue, req)
    ack = _wait_control_ack(recv_conn, req['request_id'])
    _raise_for_failed_ack(ack)
    _validate_attach_ack(
        ack,
        expected_protocol_version=ctx.protocol_version,
        expected_registry_hash=ctx.registry_hash,
    )

    with _mp_lifecycle_lock:
        logging.setLoggerClass(DSafeLogger)
        install_convenience_methods(DSafeLogger)
        _mp_runtime_state = MPProcessState(
            session_id=ctx.session_id,
            ctx=ctx,
            client_id=req['client_id'],
            root_transport=_build_mp_client_transport(ctx, ds_route='root'),
            module_transports=_build_mp_module_transports(ctx),
        )
```

- ACK 待機は `_mp_lifecycle_lock` の外で行う。lock 保持中に control plane I/O を待機してはならない。
- same process / same `ctx` の再 attach だけが純粋 no-op である
- fork 継承 child は同一 session でも `client_id` を再生成して `ATTACH` し、active client registry と shutdown 判定を壊さない
- ただし `is_async=True` で process-local pump thread が fork により失われている場合、attach 完了後に `_rehydrate_fork_inherited_runtime_if_needed()` が transport / pump thread を再生成してから返る
- fork 継承 child の再登録は元の Writer session が存続している間に限る。Writer が既に stop/drain 中または終了済みであれば session の自動 resurrection は行わず、後続 send failure / liveness loss は通常の `_writer_dead=True` 経路へ畳み込む

#### 15a.5.5. Writer runtime

```python
class WriterRuntime:
    def __init__(
        self,
        ctx: BootstrapContext,
        sink_groups: dict[str, list[logging.Handler]],
    ) -> None:
        self._ctx = ctx
        self._sink_groups = sink_groups
        self._active_clients: dict[str, dict[str, object]] = {}
        self._active_lock = threading.Lock()
        self._reopen_lock = threading.Lock()
        self._stop_requested = False
        self._accept_new_clients = True
        # v23h: validate flush batch size (was previously trusted blindly).
        if ctx.writer_flush_batch < 1:
            raise ValueError(
                f'writer_flush_batch must be >= 1, got {ctx.writer_flush_batch}'
            )
        self._reject_counter = 0
        self._writer_route_reject = 0
        # v23h M4: writer_event_reject was split into reconstruct/close-marker.
        self._writer_reconstruct_reject = 0     # LogEvent reconstruct failure
        self._writer_close_marker_reject = 0    # invalid CloseMarker
        # v23h H2/M1: required sink set vs best-effort.
        self._writer_sink_reject = 0            # required handler emit error (per record)
        self._writer_policy_reject = 0          # required handler filter false (per record)
        self._writer_partial_delivered = 0      # required sink set partial
        self._writer_best_effort_failures = 0   # best-effort sink failure (visibility only)
        self._messages_since_flush = 0
        self._writer_flush_batch = ctx.writer_flush_batch
        # v23h L1: hoisted flag controls idle / shutdown flush dead-code paths.
        self._batch_flush_enabled = self._writer_flush_batch > 1
        self._writer_drain_deadline_loss = 0
        self._writer_flush_error_count = 0
        self._expected_close_markers: set[str] = set()
        self._close_markers_received: set[str] = set()
        self._close_marker_failed_clients: set[str] = set()
        self._drain_deadline: float | None = None
        self._close_marker_degraded = False

    def start(self) -> None:
        # v23h: threads are daemon=True. Drain is guaranteed by the explicit
        # stop() call (atexit-registered _mp_shutdown), the daemon flag is
        # the §12.4 bounded-shutdown safety net.
        if self._log_thread is not None or self._control_thread is not None:
            if self._log_thread.is_alive() and self._control_thread.is_alive():
                return
            raise RuntimeError('WriterRuntime cannot be restarted after stop')
        self._log_thread = threading.Thread(target=self._log_loop, name='D-SafeLogger-WriterLog', daemon=True)
        self._control_thread = threading.Thread(target=self._control_loop, name='D-SafeLogger-WriterControl', daemon=True)
        self._log_thread.start()
        self._control_thread.start()

    def _drain_complete(self) -> bool:
        if not self._stop_requested:
            return False
        with self._active_lock:
            if self._active_clients:
                return False
            pending = self._expected_close_markers - (
                self._close_markers_received | self._close_marker_failed_clients
            )
            if not pending:
                return True
        # v23g/v23h: degraded shutdown — report residual queue size inline.
        # On platforms where qsize() is not implemented, `-1` is reported and
        # the counter is left untouched (TrackedQueue normally avoids this on
        # all supported platforms).
        deadline = self._drain_deadline
        if deadline is not None and time.monotonic() >= deadline:
            with self._active_lock:
                remaining = self._expected_close_markers - (
                    self._close_markers_received | self._close_marker_failed_clients
                )
            try:
                queued_loss = self._ctx.log_queue.qsize()
            except (NotImplementedError, OSError):
                queued_loss = -1
            if queued_loss > 0:
                self._writer_drain_deadline_loss += queued_loss
            if remaining or queued_loss != 0:
                print(
                    f'[D-SafeLogger] drain deadline reached; '
                    f'{len(remaining)} close marker(s) outstanding: {remaining!r}; '
                    f'{queued_loss} message(s) remained in log queue',
                    file=sys.stderr,
                )
            return True
        return False

    def _log_loop(self) -> None:
        # v23h L1: per-message mode (writer_flush_batch == 1) skips the always-False
        # idle/shutdown flush checks; the batch-flush flag is hoisted out of the loop.
        do_idle_flush = self._batch_flush_enabled  # == (self._writer_flush_batch > 1)
        while True:
            if self._drain_complete():
                if do_idle_flush and self._messages_since_flush > 0:
                    self._flush_all_sinks()
                return
            try:
                item = self._ctx.log_queue.get(timeout=0.05)
            except Exception:
                # Catch broadly: queue.Empty (timeout), OSError / ValueError /
                # BrokenPipeError on closed queue. The loop continues and exits
                # via _drain_complete() when shutdown progresses.
                if do_idle_flush and self._messages_since_flush > 0:
                    self._flush_all_sinks()
                continue
            if _is_close_marker(item):
                self._record_close_marker(item)
                continue
            try:
                record = _reconstruct_record(item)
                self._dispatch(record)  # v23h: dispatch counter accounting per-record
                self._messages_since_flush += 1
                if self._messages_since_flush >= self._writer_flush_batch:
                    self._flush_all_sinks()
            except Exception as e:
                self._reject_counter += 1
                # v23h M4: split from _writer_event_reject (LogEvent reconstruct path).
                self._writer_reconstruct_reject += 1
                self._maybe_warn(
                    self._writer_reconstruct_reject,
                    f'Writer rejected LogEvent: {e!r}',
                )

    def _control_loop(self) -> None:
        while True:
            try:
                req = self._ctx.control_queue.get(timeout=0.2)
            except Exception:
                if self._stop_requested and not self._has_active_clients():
                    return
                continue
            ack = self._handle(req)
            _send_control_ack(req['reply_to'], ack)
```

- Writer process の main thread は `WriterRuntime.start()` 後に `_log_thread` / `_control_thread` を `join()` し、通常終了時の安全性を daemon thread に依存しない
- `STOP` request を受理した時点で `_accept_new_clients=False` とし、以後の `ATTACH` request は validation error ACK で拒否する

WriterRuntime の責務は次の通り。

- active client registry の保持
- log plane / control plane の分離実行
- `ATTACH` / `DETACH` / `REOPEN` / `STOP` / `STATUS` の直列処理
- bootstrap ready ACK 時の registry hash 照合
- route ごとの sink group dispatch
- reopen の直列化
- shutdown 時の active client 数 0 待ち
- drop / reject counter の集計と stderr 可視化

補足:

- `STOP` 受理後は `_accept_new_clients=False` とし、後発 `ATTACH` は validation error ACK で拒否する
- v23h: `_log_thread` / `_control_thread` は **`daemon=True`** で起動する。drain 完全性は `runtime.stop()`（atexit 経由で必ず呼ばれる `_mp_shutdown` から呼び出される）が serial drain と join で保証する。daemon フラグは §12.4「bounded shutdown」の安全網であり、stop() が timeout 内に drain を完了できなかった場合に **silent hang を避けて process を exit させる**ことを目的とする
- v23h: `runtime.stop()` は join timeout 後に thread が生存していれば、stuck thread 名（`log_thread` / `control_thread`）を含む stderr warning を出力する。silent hang は禁止

#### 15a.5.6. control plane / ACK

```python
CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0
MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0
WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0


def _send_control_request(control_queue, req: ControlRequest) -> None:
    control_queue.put(req, block=True)


def _wait_control_ack(recv_conn, request_id: str) -> ControlAck:
    if not recv_conn.poll(CONTROL_PLANE_ACK_TIMEOUT_SEC):
        raise TimeoutError('control plane ACK timed out')
    ack = recv_conn.recv()
    if ack['request_id'] != request_id:
        raise RuntimeError('control plane request/ack mismatch')
    return ack


def _raise_for_failed_ack(ack: ControlAck) -> None:
    if ack['success']:
        return
    if ack['error_category'] == 'timeout':
        raise TimeoutError(ack['error_message'])
    if ack['error_category'] == 'validation':
        raise ValueError(ack['error_message'])
    raise RuntimeError(ack['error_message'])
```

`WriterRuntime._handle_control_request()` の command-specific 契約:

- `ATTACH`: `_accept_new_clients=True` の間のみ success ACK。`STOP` 受理後は validation error ACK で拒否する
- `DETACH`: active client registry から削除し success ACK
- `REOPEN`: `_reopen_lock` 下で reopen を直列実行し、validation/runtime error は error ACK に変換
- `STATUS`: counters / active client 数 / queue policy を result payload に詰めて返す
- `STOP`: `_stop_requested=True`, `_accept_new_clients=False` を記録して success ACK を返す

補足:

- control plane reply path は per-request Pipe send end に対して `send()` する
- Queue-in-Queue を避けるため、`multiprocessing.Queue` 自体を `ControlRequest` payload に含めてはならない
- `send()` / `recv()` 完了後は Pipe endpoint を close し、ACK wait/signal failure は `RuntimeError` 系へ正規化する

#### 15a.5.7. backpressure / active client registry / Writer crash

- log plane queue は bounded `multiprocessing.Queue(maxsize=10000)` を既定とする
- `is_async=True` 時の process-local async queue も bounded とし、既定では log plane queue と同じ上限を用いる
- `ipc_log_timeout` は `LOG` hand-off 専用であり、control plane command には適用しない
- overflow 時は record を drop し、client 側 counter を増やして stderr warning を出す
- `ATTACH` / `DETACH` / `STOP` は drop 不可、`REOPEN` / `STATUS` は ACK 必須
- shutdown 判定は sentinel 数ではなく active client registry に基づく
- unknown route は root fallback せず reject counter 増分 + stderr warning とする
- worker crash により `DETACH` が欠落した場合は timeout 後に warning を出して強制 stop へ移行する
- Writer crash は client 側の `BrokenPipeError` / `EOFError` / `OSError` / `ValueError` / ACK timeout / Writer 終了状態観測で検知し、以後は再帰ロギングせず drop + stderr warning とする
- `STOP` 受理後に到着した `ATTACH` は validation error ACK とし、silent accept しない

---

## 16. エラーハンドリング方針

| 状況 | 挙動 |
|------|------|
| `ConfigureLogger` への不正引数 | `ValueError` を発生 |
| `env_prefix` が空文字列 | `ValueError` を発生 |
| `config_file` 指定だがファイル不在 | `FileNotFoundError` を発生（Fail-Fast） |
| `{prefix}_CONFIG` 指定だがファイル不在 | `FileNotFoundError` を発生（Fail-Fast） |
| INIファイルの型変換エラー | `ValueError` を発生（Fail-Fast） |
| INIファイルの `diagnose` キー | 無視（警告もエラーもなし） |
| INIファイルの未知のキー | stderr に警告出力、キーを無視 |
| INIモジュールセクションに `level` なし | `ValueError` を発生（Fail-Fast） |
| INIモジュールで `path` なしに `routing_mode` 指定 | stderr に警告出力、キーを無視 |
| `{prefix}_LEVEL` にカンマ含む | `ValueError`（移行ガイド付きメッセージ） |
| `log_path` ディレクトリ不在 | 自動作成 (`os.makedirs(exist_ok=True)`) |
| `log_path` への書き込み権限なし | `PermissionError` を発生（Fail-Fast） |
| モジュール別 `path` への書き込み権限なし | `PermissionError` を発生（Fail-Fast） |
| ディスク空き容量不足（初期化時） | `OSError` を発生（Fail-Fast） |
| ファイル書き込み失敗（権限等） | `logging.Handler.handleError()` に委譲（stderr 出力） |
| パージ時のファイルロック | stderr 警告、次回の自己修復に委ねる |
| アーカイブ時のストレージ不足 | stderr 警告、圧縮処理を中止 |
| `suffix_digits` 桁数超過（上限到達エラーモード） | `OverflowError` を発生 |
| 環境変数の不正フォーマット | stderr に警告し、該当部分をスキップ |
| `structured=True` + `fmt` / `file_fmt` / `console_fmt` 同時指定 | `ValueError` を発生 |
| `GetLogger` が `ConfigureLogger` 前に呼ばれた | デフォルト引数で `ConfigureLogger` を自動発火 |
| `register_level()` が `ConfigureLogger` 後に呼ばれた | `RuntimeError` を発生 |
| `register_level()` でビルトイン値/名前/略称の上書き | `ValueError` を発生 |
| `register_level()` で略称が3文字でない | `ValueError` を発生 |
| `register_level()` の same-definition 再登録 | no-op |
| `register_level()` の不一致再登録 | `RuntimeError` を発生 |
| ハッシュ生成（サイドカー/マニフェスト）の失敗 | stderr 警告、処理続行（パージの自己修復性と同方針） |
| `manifest_path` のディレクトリが書き込み不可 | `PermissionError` を発生（Fail-Fast） |
| `enable_hash=False` かつ `manifest_path` 指定あり | stderr に警告出力（`manifest_path` は無視） |
| `routing_mode='none'` かつ `enable_hash=True` | stderr に警告出力（ハッシュ生成機会なし） |
| `ReopenLogFiles()` を初期化前に呼ぶ | `RuntimeError` を発生 |
| `ReopenLogFiles()` 実行対象に `routing_mode != 'none'` の writer-side file sink が含まれる | `ValueError` を発生 |
| single-process `ReopenLogFiles()` 実行時に writer-side file sink が存在しない | `RuntimeError` を発生 |
| `config_dict` の型が `dict[str, dict[str, str]]` でない | `TypeError` を発生（Fail-Fast） |
| `config_dict` の値が `str` でない | `TypeError` を発生（Fail-Fast） |
| `config_file` と `config_dict` の同時指定（`{prefix}_CONFIG` なし） | `ValueError` を発生（排他違反） |
| `config_dict` の型変換エラー | `ValueError` を発生（IniLoader と同一バリデーション） |
| `config_dict` の `diagnose` キー | 無視（聖域保護、警告もエラーもなし） |
| `config_dict` の未知のキー | stderr に警告出力、キーを無視 |
| `config_dict` モジュールセクションに `level` なし | `ValueError` を発生（Fail-Fast） |
| `sens_kws` の型が `Sequence[str]` でない | `TypeError` を発生 |
| `sens_kws` の要素が空文字列 | `ValueError` を発生 |
| `sens_kws_replace=True` かつ `sens_kws` が `None` または空 | `ValueError` を発生 |
| shutdown 中の `join()` が finalization で継続不能 | stderr に warning 出力し、best-effort で続行 |
| queue drain timeout | stderr に warning 出力し、handler close へ進む |
| INI/辞書の `color_` キーの略称がビルトイン・登録済みカスタムレベルに不一致 | stderr に警告出力、キーを無視（処理継続） |
| INI/辞書の `color_` キーの値に `0-9` と `;` 以外の文字を含む | stderr に警告出力、キーを無視（処理継続） |
| INI/辞書の `color_` キーの値が空文字列 | 有効（該当レベルのカラー化を無効にする） |
| multiprocess `worker_model` が `process/pool/executor` 以外 | `ValueError` を発生 |
| multiprocess `ipc_log_timeout <= 0` | `ValueError` を発生 |
| multiprocess `ipc_log_timeout > MAX_IPC_LOG_TIMEOUT_SECONDS` | stderr warning + clip して継続 |
| multiprocess `GetLogger()` を未 attach 状態で呼ぶ | `RuntimeError` を発生 |
| `AttachCurrentProcess(ctx)` を別 session の `ctx` で再実行 | `RuntimeError` を発生 |
| `BootstrapContext` の pickle round-trip 検証失敗 | `RuntimeError` を発生（Fail-Fast） |
| bootstrap ready ACK の `protocol_version` / registry hash mismatch | `RuntimeError` を発生 |
| attach ACK の `protocol_version` / registry hash mismatch | `RuntimeError` を発生 |
| client の log plane `put()` が timeout / `queue.Full` | drop counter を増分し、stderr に warning を出して当該 `LogEvent` を drop |
| client が `BrokenPipeError` / `EOFError` / queue 利用不能で Writer 死亡を検知 | 以後の send を drop + stderr warning とする |
| control plane ACK timeout | 呼び出し元 API で `TimeoutError` に変換 |
| Writer が `REOPEN` request を受理したが file sink 不在 | error ACK を返し、client 側で `RuntimeError` に変換 |
| Writer が `REOPEN` request を受理したが `routing_mode != 'none'` の sink を検知 | error ACK を返し、client 側で `ValueError` に変換 |
| `_reconstruct_record()` 失敗 | Writer reject counter を増分し、stderr に warning を出して当該 event を skip |
| `_ds_route` が Writer 側に存在しない sink group を指す | Writer reject counter を増分し、stderr に warning を出して skip |
| Pipe ACK send/recv failure | `RuntimeError` 系へ正規化し、Pipe endpoint は close する |
| `_ds_extra` に予約キーを含む（sender 側で生成した場合） | 予約キーを除外して格納（silent skip）。receiver 側でも予約キーへの setattr を skip |

---

## 17. 状態遷移図：ファイル切り替え

```
[書き込み中]
    │
    ├── should_switch() == False ──→ [同一ファイルに追記]
    │
    └── should_switch() == True
            │
            ├── advance() 成功
            │     │
            │     ├── 新ファイルパス算出
            │     ├── 現ストリーム close
            │     ├── 新ストリーム open (mode='a')
            │     │
            │     ├── is_cyclic() == True  ──→ [パージなし。書き込み継続]
            │     │
            │     └── is_cyclic() == False
            │           │
            │           ├── backup_count > 0
            │           │     │
            │           │     ├── archive_mode == False
            │           │     │     └── PurgeWorker 起動 (daemon=True, Fire-and-Forget)
            │           │     │           ├── [enable_hash] 切替直後ファイルのハッシュ生成（先行）
            │           │     │           │     ├── write_sidecar()
            │           │     │           │     └── append_manifest()（manifest_path 指定時）
            │           │     │           └── 古いファイルを unlink（削除）
            │           │     │                 └── [enable_hash] 対応 .sha256 も連動削除
            │           │     │
            │           │     └── archive_mode == True
            │           │           └── ArchiveWorker 起動 (daemon=True, Fire-and-Forget)
            │           │                 ├── [enable_hash] 切替直後ファイルのハッシュ生成（先行）
            │           │                 ├── ストレージ空き容量検証
            │           │                 │   ├── 不足 → stderr 警告、中止
            │           │                 │   └── 十分 → ZIP 圧縮（.sha256 も同梱）→ 元ファイル削除
            │           │                 └── ロック時 → stderr 警告、次回に委ねる
            │           │
            │           └── backup_count == 0 かつ enable_hash == True
            │                 └── HashWorker 起動 (daemon=True, Fire-and-Forget)
            │                       ├── write_sidecar()
            │                       └── append_manifest()（manifest_path 指定時）
            │
            └── advance() 失敗 (OverflowError)
                  └── caller へ再送出（fail-fast）
```

---

## 18. スレッドモデル

```
[メインスレッド / アプリスレッド]
    │
    ├── logger.info("msg")
    │     │
    │     ├── [is_async=False] → 同期的に Handler.emit() → ファイル書き込み
    │     │
    │     └── [is_async=True]  → DSafeQueueHandler.emit() → context/diagnose snapshot 付与 → Queue に投入（ノンブロッキング）
    │
    └── (メインスレッドは即座に継続)

[QueueListener スレッド] (is_async=True 時のみ、空 Context)
    │
    └── Queue からレコードを取り出し → 実 Handler.emit() → ファイル書き込み

[PurgeWorker スレッド] (ファイル切り替え時に一時的に起動、backup_count > 0、空 Context)
    │
    ├── [enable_hash=True] → 切り替え前ファイルのハッシュ生成（サイドカー＋マニフェスト）
    └── 古いファイルを削除（.sha256 サイドカーも連動削除） → 完了後にスレッド終了

[ArchiveWorker スレッド] (archive_mode=True 時のファイル切り替え時、backup_count > 0、空 Context)
    │
    ├── [enable_hash=True] → 切り替え前ファイルのハッシュ生成（サイドカー＋マニフェスト）
    └── 古いファイルを ZIP 圧縮（.sha256 サイドカーも同梱） → 元ファイル削除 → 完了後にスレッド終了

[HashWorker スレッド] (enable_hash=True かつ backup_count=0 時のファイル切り替え時、空 Context)
    │
    └── 切り替え前ファイルのハッシュ生成 → サイドカー書き出し → マニフェスト追記 → 完了後にスレッド終了

[attached client process] (`dsafelogger.mp`, process-local)
    │
    ├── AttachCurrentProcess(ctx)
    │     ├── control plane で ATTACH request 送信
    │     ├── ACK 受信
    │     └── process-local transport を有効化
    │
    └── logger.info("msg")
          ├── _serialize_record(record, ds_route)
          ├── [is_async=False] → log plane queue へ直接 put
          └── [is_async=True]  → process-local async queue → pump thread → log plane queue

[WriterRuntime スレッド群] (`dsafelogger.mp.ConfigureLogger()` 呼出元が起動)
    │
    ├── [Writer log thread]
    │     ├── log plane queue から LogEvent を取得
    │     ├── _reconstruct_record(event) で LogRecord を復元
    │     └── route に応じて sink group へ direct dispatch
    │           ├── 'root'          → root sink group
    │           ├── 'module:<name>' → module sink group
    │           └── unknown route   → reject counter++ / stderr warning
    │
    └── [Writer control thread]
          ├── ATTACH / DETACH / REOPEN / STOP / STATUS を処理
          ├── active client registry を更新
          ├── REOPEN は writer-side で直列化
          └── ControlAck を reply path へ返送

[CLI: dsafelogger tail -f] (別プロセス)
    │
    └── メインスレッドでポーリングループ
          ├── os.stat / glob で最新ファイル特定
          ├── ファイル切り替え検知 → 新ファイルの open
          └── 新規行の読み取り → stdout に出力
```

> **v18 更新**: `HashWorker` はファイル切り替え時に起動される独立スレッドであり、`backup_count > 0` の場合はハッシュ生成が `PurgeWorker` / `ArchiveWorker` 内に統合されるため起動されない。ハッシュ関連スレッドは `daemon=True` を維持するが、通常終了時の安全性は `_active_workers` 管理と `_shutdown()` からの join により担保する。
>
> **v23j 更新**: multiprocess 版では `IPCListener` ではなく `WriterRuntime` が log plane と control plane を分離して管理する。v22h の non-daemon 方針は v23h/v23j で撤回済みであり、Writer log/control thread は `daemon=True` で起動する。通常終了時の安全性は daemon flag ではなく、active client registry、CloseMarker drain、`DETACH` / `STOP` 同期、`runtime.stop(timeout)` の bounded join / visible warning により担保する。`daemon=True` は stuck thread による process exit 不能を避ける backstop である。

> **v23j benchmark publication model**: benchmark runner は `BENCHMARK.md` を直接生成しない。実行ごとの完全な成果物は `benchmarks/results/<session>/` に保存し、公開・代表として採用する session は `benchmarks/summary/manifest.json` で固定する。`benchmarks/summary/*.md` は manifest から生成されるカテゴリ別 summary であり、`BENCHMARK.md` はそれらを参照する手動編集の公開分析文書とする。

---

## 19. モジュール別設定の Transport 統合管理

モジュール別に個別ファイルが指定された場合（INIファイル・辞書設定または環境変数 `{prefix}_MODULES` 経由）：

- single-process 版では各モジュール経路を **raw Handler 直結ではなく `Transport` 配下** で構築する
- multiprocess 版では client 側に file sink を持たせず、route identity を `'module:<name>'` として `LogEvent` に載せる
- WriterRuntime は `'module:<name>'` → module sink group の対応表を保持し、writer-side のみで module file sink を所有する
- module 固有の `RoutingStrategy` は INI/辞書で指定された設定を用い、環境変数のみで path が上書きされた場合は `NoneStrategy` を既定とする
- モジュールロガーの `propagate` は `False` に設定し、ルートロガーへの二重出力を防止する
- PATH がファイル名のみの場合は `log_path` 直下、ディレクトリ構造を含む場合は指定パスへ直接出力する
- single-process `Pipeline` と multiprocess `WriterRuntime` のどちらでも、reopen 対象は writer-side handler 集合から重複排除して求める

### モジュール別設定の来源と優先順位

```
{prefix}_MODULES 環境変数 （最優先、レベルとパスのみ上書き）
  ↓ マージ
INIファイルまたは辞書 [dsafelogger:mod] セクション （ルーティング詳細含む）
  ↓ フォールバック
未設定（モジュール別設定なし = グローバル設定に従う）
```

---

## 20. 設定の優先順位まとめ

```
環境変数 ({prefix}_LEVEL / _MODULES / _DIAGNOSE / _CONSOLE / _COLOR / _CONFIG / _HASH / _MANIFEST / _IPC_LOG_TIMEOUT)  ← 最優先（第1層）
  ↓ 上書き
INIファイルまたは辞書 ([global] / [dsafelogger:mod])  ← 運用ベースライン（第2層）
  ↓ 上書き
ConfigureLogger 引数  ← デフォルト（第3層）
  ↓ フォールバック
ハードコードされたデフォルト値  ← 最終フォールバック
```

環境変数が部分的に指定された場合（グローバルレベルのみ等）、指定されていない部分はINIファイルまたは `ConfigureLogger` の引数値を維持する。

### 各環境変数の挙動まとめ

| 環境変数 | 有効値 | 上書き対象 |
|----------|--------|-----------|
| `{prefix}_LEVEL` | `DEBUG`〜`CRITICAL`＋カスタムレベル名（単一値のみ） | `default_level`（グローバルレベル） |
| `{prefix}_MODULES` | `MOD:LEVEL[,MOD:LEVEL[:PATH],...]` | INIおよび引数のモジュール別設定（レベル/パスのみ） |
| `{prefix}_CONFIG` | ファイルパス | `config_file` 引数（`config_dict` も無視される） |
| `{prefix}_DIAGNOSE` | `"1"` のみ | 診断モード（API引数・INIからの設定不可、聖域） |
| `{prefix}_CONSOLE` | `"1"/"true"/"0"/"false"` (大文字小文字不問) | `console_out` |
| `{prefix}_COLOR` | `"1"/"true"/"0"/"false"` (大文字小文字不問) | カラー出力有効/無効 |
| `{prefix}_HASH` | `"1"/"true"/"0"/"false"` (大文字小文字不問) | `enable_hash`（ファイル完全性検証の有効/無効） |
| `{prefix}_MANIFEST` | ファイルパス | `manifest_path`（マニフェストファイル出力先） |
| `{prefix}_IPC_LOG_TIMEOUT` | 正の浮動小数点秒数 | multiprocess `ipc_log_timeout`（`LOG` hand-off 専用） |
| `NO_COLOR` | 設定されていれば（値不問） | カラー出力を強制無効化（`{prefix}_COLOR` より優先） |

---

## 変更履歴

| バージョン | 日付 | 内容 |
|---|---|---|
| v23j | 2026-05-05 | OSS公開前 review 対応として、実装動作は v23h から変更せず、公開運用と品質ゲートを固定した。`dsafelogger.mp` は preview / experimental ではなく正式 API として公開する判断を記録し、価値訴求を raw throughput ではなく Writer-owned sinks と classified delivery-state observability に置く。OpenTelemetry / structlog coexistence tests は `dev` dependency group の full test suite に含め、`optional_integration` marker は診断用選択 marker とする。spawn E2E は Writer IPC primitives と worker creation で同一 `multiprocessing` context を使う。`tests/` から `multiprocessing.Queue.empty()` 依存を排除した。benchmark runner は `BENCHMARK.md` を生成せず、`benchmarks/results/<session>/`、`benchmarks/summary/manifest.json`、`benchmarks/summary/*.md`、手動編集 `BENCHMARK.md` の4層 publication model を採用する。release version は `0.2.0` とし、`pyproject.toml` と `dsafelogger.__version__` を一致させる。 |
| v23j-publication-sync | 2026-05-06 | 公開前同期として、API docs 生成、design docs sync check、examples 更新、GitHub workflow gate、coverage 再生成を追加する。これらは detailed runtime design を変更しない公開成果物同期であり、`dsafelogger.mp` formal API、dev full-test policy、benchmark publication model、release version `0.2.0` の判断を維持する。 |
| v23 | 2026-04-25 | v22i 詳細設計書を v23 として複写。v23 系設計方針（Writer 不変条件・配送契約用語・Overload Policy）は基本設計書 §12 を参照。実装との差分棚卸しを private planning notes に記録した。挙動変更なし。 |
| v23b | 2026-04-25 | `_log_loop` の `Queue.empty()` 依存を廃止し、client close marker 機構を実装した（差分棚卸し #4 対応）。各 client は DETACH 前に `CloseMarker` を log_queue に投入する。Writer は全 ATTACH 済み client の `CloseMarker` 受信（または `close_marker_failed` 確認）を drain 完了条件とする。`is_async=True` は pump thread join 後に CloseMarker を送信し、ordering を保証する。`close_marker_failed` は silent にならず、degraded shutdown として `_close_marker_degraded` フラグと stderr に反映する。drain deadline（`WRITER_STOP_WAIT_TIMEOUT_SEC`）超過時は outstanding marker を警告しつつ終了する。変更対象: `_mp_protocol.py`（`CloseMarker`, `_is_close_marker`）、`_mp_runtime.py`（`_drain_complete`, `_record_close_marker`, `_expected_close_markers`, `_close_markers_received`, `_close_marker_failed_clients`, `_drain_deadline`）、`_mp_attach.py`（`send_close_marker`, `_do_detach` フェーズ再構築）、`_mp_control.py`（`_make_detach_request` の `close_marker_failed` 引数）。 |
| v23c | 2026-04-26 | queue サイズをユーザー設定可能にし、drop/reject カウンターを原因別に分離した（差分棚卸し #1・#5・#7 対応）。`mp.ConfigureLogger()` に `ipc_log_queue_maxsize: int | None` と `ipc_client_queue_maxsize: int | None` を追加。env var `{prefix}_IPC_LOG_QUEUE_MAXSIZE` / `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` で上書き可能。既定値は `ipc_log_queue_maxsize=1000`（v22i 実装値を継承）、`ipc_client_queue_maxsize` は未指定時 `ipc_log_queue_maxsize` に揃える。`BootstrapContext` に `ipc_client_queue_maxsize: int` フィールドを追加。`MPClientTransport` の process-local async queue を `ctx.ipc_client_queue_maxsize` で生成するよう変更。`MPClientTransport._drop()` に原因別カウンター（`_overload_shed`, `_transport_closed_drop`, `_writer_unavailable_drop`, `_timeout_drop`）を追加。`WriterRuntime` に `_writer_route_reject`, `_writer_event_reject` を追加し `STATUS` レスポンスに反映。制御 queue（256）は内部定数のまま維持（根拠不明を棚卸し #2 に記録済み）。 |
| v23d | 2026-04-26 | stage 別 latency 計装を実装し、Writer dispatch が p50 の支配因子であることを定量化した（実装コード変更なし）。`benchmarks/run_multiprocess_v23d_diagnostic.py` を新規作成。diagnostic wrapper（monkey-patching）で `_emit_record` / `_reconstruct_record` / `_dispatch` を計測。root_p1: writer_dispatch p50=185.8µs が全体の ~62% を占める。root_p4/root_p8: IPC queue backpressure（queue.put p50=1085/1972µs）が多 worker 時の劣化原因。v23e 最適化候補として Writer バッチ flush を特定。計測結果の詳細は private test-design notes に記録。 |
| v23e | 2026-04-26 | Writer バッチ flush を実装し、per-message flush を廃止した。`AppendOnlyFileHandler` に `stream_flush_on_emit: bool = True` パラメータを追加（既定 True で既存動作維持）。`_build_writer_sink_groups` はファイルハンドラを `stream_flush_on_emit=False` で生成するよう変更。`WriterRuntime._log_loop` に `_WRITER_FLUSH_BATCH=16` カウンターおよびアイドル flush（queue empty 検出）を追加。`_flush_all_sinks()` ヘルパーを追加。queue.get timeout を 0.2s → 0.05s に短縮（アイドル flush の最大待機時間を短縮）。効果: writer_dispatch p50 が 185.8µs → 11.5µs（**16x 削減**）。root_p8 child_emit p50 が 2019µs → 386µs（**5x 削減**）。sequence 完全性: integrity_profile 全パターンで missing=0 を確認。変更対象: `_handler.py`, `_mp_runtime.py`, `mp/__init__.py`。 |
| v23f | 2026-04-26 | `_ds_route` structured JSON leak を修正した（差分棚卸し #3 対応）。`_formatter.py` の `_DSAFE_INTERNAL_FIELDS` に `'_ds_route'` を追加（3要素 → 4要素）。これにより multiprocess + structured JSON 経路で `_ds_route` が public output に出力されなくなった。`_ds_extra` は `_reconstruct_record()` が record 属性として設定しないため修正不要と確認。破壊的変更: `_ds_route` を明示採用していた利用者は JSON 出力からこのフィールドが消える。単一プロセスパスへの影響なし（`_ds_route` は mp 内部専用）。テスト: `test_formatter.py` に `test_ds_route_not_in_structured_output` / `test_ds_internal_fields_not_in_structured_output` / `test_user_extra_field_still_included` を追加。破壊度評価: 軽微（`_ds_route` は mp 内部 routing 情報、外部利用想定外、利用者ドキュメントなし）。ユーザー判断: 影響軽微のため変更を承認（2026-04-27）。移行ガイダンス: `_ds_route` を JSON ログから取得していた利用者は `logger.name` 等で代替する。 |
| v23g | 2026-04-27 | 監査結果への対応。① v23e batch flush を §12.2「flush 契約の弱体化」厳守のため opt-in 化: `ConfigureLogger(writer_flush_batch=N)` 引数追加、既定 1 で per-message flush 復帰、env var `{prefix}_WRITER_FLUSH_BATCH` 対応。`BootstrapContext` に `writer_flush_batch: int` フィールド追加。② `_LOG_QUEUE_MAXSIZE` 1000 → 10000 で基本設計 §11.16.1 と一致（差分棚卸し #1 完全解消）。③ drain deadline 超過時の log_queue 残数を stderr 報告し `_writer_drain_deadline_loss` カウンター新設、STATUS API 公開（監査 #2 対応）。④ `_flush_all_sinks` の flush エラーを `_writer_flush_error_count` カウンターと stderr 警告で可視化（監査 #6 対応）。⑤ `stop()` と `_log_loop` の二重 flush 解消：`stop()` から `h.flush()` を削除し `h.close()` のみとした（監査 #9）。⑥ 文書: 基本設計 §11.16.1 を v23c 新規 API・maxsize 10000 で改定、§11.27「Writer flush 戦略」新設、§12.3 / §12.2 に opt-in 注記追加、詳細設計 §8.5 に CloseMarker 送信プロトコル追記、inventory #3 / v23f changelog にユーザー承認記録追加・予定変更理由追記。⑦ テスト: writer_flush_batch 設定テスト（5件）・v23g カウンターテスト（5件）・per-message flush テスト（1件）計 11 件追加、テスト設計書 v23b / v23c / v23e / v23f 新規作成。変更対象: `_mp_protocol.py`, `_mp_runtime.py`, `mp/__init__.py`, テストファイル。 |
| v23g-audit-sync | 2026-04-27 | v23 最新設計書一式と実装の再精査結果を反映。詳細設計本文に残っていた旧 `Queue.empty()` 疑似コード、`ctx.log_queue_maxsize` 参照、旧 `MPClientTransport.stop()` 順序を v23g 実装へ同期。基本設計の `mp.ConfigureLogger()` シグネチャ、環境変数一覧、v23a〜v23g changelog を補完。CloseMarker の `session_id` / expected client 検証を実装し、invalid marker を `_writer_event_reject` と stderr warning に反映。Writer handler emit error / handler filter reject / partial delivery を `_writer_sink_reject` / `_writer_policy_reject` / `_writer_partial_delivered` として STATUS に公開。benchmark runner の queue=1000 前提を v23g queue=10000 と explicit profile queue sizing へ修正し、v23d diagnostic に `--writer-flush-batch` と `writer: flush sinks` stage を追加。`D-SafeLogger_TestDesign_v23g.md` を新規作成し、v23g 固有 DOD と T14〜T16 ベンチ結果を記録した。T14: `benchmark_v23g_integrity` で repeat=3 / 288 raw runs / bad=0。T15: `v23g_default_flushstage` で per-message flush p50 約187〜200µs。T16: `v23g_batch16_flushstage` for dispatch p50 約11〜12µs。 |
| v23h | 2026-04-29 | v23g 監査の H1〜H3 / M1〜M5 / L1〜L5 指摘へのユーザー判断対応。① **H1**: 詳細設計 §15a.5.5 / §16.5 の WriterRuntime 疑似コードを実装名（`_dispatch`、`except Exception`、`_drain_complete` インライン展開）に同期した。② **H2 / M1 / L5**: `_handler.py:AppendOnlyFileHandler._ds_required = True` と `_color.py:ColorStreamHandler._ds_required = False` で sink 分類を導入。`WriterRuntime._dispatch` を required-sink-centric に書き直し、partial / sink_reject / policy_reject は required sink set 内のみで増分する per-record 計上に統一した。best-effort sink 失敗は `_writer_best_effort_failures` で可視化（`_reject_counter` には集約しない）。Nuitka `--windows-console-mode=disable` で console emit が失敗するシナリオでも file delivery が成功すれば partial にしない契約を確立した。③ **H3**: `_writer_sink_reject` / `_writer_policy_reject` / `_writer_route_reject` / `_writer_reconstruct_reject` / `_writer_close_marker_reject` / `_writer_best_effort_failures` の stderr warning を `_maybe_warn(count, msg)` ヘルパで統一し、初回 + 100 件ごとの rate limit を適用した。④ **M3**: `src/dsafelogger/_mp_queue.py` に `TrackedQueue(multiprocessing.queues.Queue)` を新設。`__init__` で例外プローブ（`super().qsize()` → `NotImplementedError` 捕捉）により native 対応を判定し、対応プラットフォームではネイティブ `qsize()`、未対応プラットフォームでは `multiprocessing.Value` カウンタへ自動 fallback する。`mp/__init__.py` で log_queue を `TrackedQueue` で生成するよう変更（control_queue は引き続き ipc_mp_ctx.Queue）。OS 判定はせず例外プローブのみで判別するため macOS 以外のマイナー OS でも自動的に正しく動作する。⑤ **M4**: `_writer_event_reject` を `_writer_reconstruct_reject`（LogEvent reconstruct path）と `_writer_close_marker_reject`（CloseMarker validation path）に分離。STATUS API も両カウンタを公開する。後方互換は不要との判断（プロジェクト未公開）により旧名は保持しない。⑥ **M5**: `D-SafeLogger_TestDesign_v23e.md` の batch flush テスト記述を `D-SafeLogger_TestDesign_v23g.md` および本ファイル `_v23h.md` への redirect スタブへ縮約した（v23g がある後で v23e を更新する不整合を解消）。⑦ **L1**: `_log_loop` の idle / shutdown flush は `_batch_flush_enabled = (writer_flush_batch > 1)` フラグで制御し、`writer_flush_batch == 1` 時は dead branch を踏まない。⑧ **L2**: `mp.ConfigureLogger()` の env var パース（`{prefix}_IPC_LOG_TIMEOUT` / `_IPC_LOG_QUEUE_MAXSIZE` / `_IPC_CLIENT_QUEUE_MAXSIZE` / `_WRITER_FLUSH_BATCH`）を「invalid 時は warning + ignore」から「`ValueError` を raise」へ統一した（fail-fast）。⑨ **L3**: `WriterRuntime.__init__` で `ctx.writer_flush_batch < 1` を `ValueError` に。`mp.ConfigureLogger()` 経由で公開済みのバリデーションに加え、`BootstrapContext` 直接構築時の安全網を追加した。⑩ **L4**: `D-SafeLogger_v23_baseline_diff_inventory.md` 差分 #1 の v23c 経緯記述を「ユーザー判断による据え置き」から「v22i 実装値の継承（当時のユーザー判断は得ていない）」へ訂正した。⑪ **L5**: 仕様書 §12.3 を改定し、required sink set が単一の場合 `partial_delivered` は概念上 0 のままで増分しないことを明示した。⑫ **§12.4.1 Bounded shutdown（v23h 追加項目、ユーザー判断「正常終了時のシャットダウンでハングアップは許されない」を受けた追加対応）**: `WriterRuntime._log_thread` / `_control_thread` を **`daemon=True`** に変更（v22h で行った non-daemon 化の決定を v23h で撤回。v22h の選定根拠「通常終了の安全性を daemon thread に依存しない」は atexit による `runtime.stop()` 呼び出しが未確立だった当時のものであり、現状は `_mp_shutdown` 経由で `stop()` が必ず呼ばれる構造のため daemon=True で支障がない）。`runtime.stop()` の join timeout 経過後に thread が生存していれば、stuck thread 名（`log_thread` / `control_thread`）を含む stderr visible warning を出力する `silent hang 禁止`の bounded shutdown 契約を実装した。仕様書 §12.4.1 と本詳細設計 §15a.5 の補足に明記。テスト変更: 既存 `_writer_event_reject` 参照テストを split 後の counter に追従、env var fall-back テストを raise 期待に書き換え、v23h 用クラス `TestV23HValidation` / `TestTrackedQueue` / `TestSinkClassification` および per-record 計上テスト・rate-limit テスト・best-effort 非計上テスト・`test_writer_threads_are_daemon`（旧 `test_writer_threads_are_nondaemon` 置換）・`test_stop_emits_bounded_warning_when_threads_stuck` / `test_stop_emits_no_warning_on_clean_shutdown` を新設。変更対象: `_handler.py`, `_color.py`, `_mp_queue.py`（新規）, `_mp_runtime.py`, `mp/__init__.py`, `tests/test_mp_runtime.py`, `tests/test_mp_attach.py`, private detailed design note, private specification note, private baseline diff inventory, private test-design note（redirect 化）, private test-design note（新規）。 |
