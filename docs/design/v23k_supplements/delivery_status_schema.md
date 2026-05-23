# D-SafeLogger Delivery Status Schema (Implementation Contract)

ステータス: **実装契約 (Implementation Contract)** — 計画段階の草案ではない。
対象バージョン: v23k(0.2.2 以降)
作成日: 2026-05-23
位置づけ: マルチプロセス配送状態の counter accounting、wire protocol 拡張、observability 出力 schema を一元的に定義する。Phase 1〜6 の実装はこの文書に絶対準拠する。
関連計画書: `plan/release_0.2.2/multiprocess_observability_implementation_plan.md`

---

## 1. 目的と適用範囲

D-SafeLogger のマルチプロセス配送結果を、stderr に依存せずに後から確認可能にする。具体的には以下の出力を提供する。

- **`mp.GetDeliveryStatus()`**: 実行中の `DeliveryStatus` snapshot を返す公開 API
- **`shutdown_report_path`**: 終了時の配送状態集計 JSON
- **`runtime_warning_path`**: stderr 相当の runtime warning を JSONL でファイル出力

本文書は上記 3 出力で使われる**全 field の意味**と**counter の加算地点**を実装契約として定義する。

### 適用範囲

- マルチプロセス runtime(`dsafelogger.mp`)のみ
- 単一プロセス API(`dsafelogger.ConfigureLogger` 直接呼び出し)は対象外

---

## 2. Accounting Invariant(実装の絶対基準)

### 2.1 Cut points

| Counter | 加算地点 | 説明 |
|---|---|---|
| `attempted` | `MPClientTransport._emit_record()` の入口 | logger level / filter を通過し MP proxy handler に到達した record 数。**`_drop()` 内では加算しない** |
| `accepted` | `WriterRuntime._log_loop()` が log_queue から item を取得し、`_is_close_marker(item)` が False と判定した直後、`_reconstruct_record(item)` の前 | Writer が配送責任を引き受けた log event 数。reconstruct_reject / route_reject / sink_reject / policy_reject は **すべて accepted の内側** に含まれる |
| `delivered` | `WriterRuntime._dispatch()` で `required_delivered == required_total` のとき | **全 required sink** への delivery が成功した record 数。「最低 1 sink 成功」ではない |
| `partial_delivered` | `WriterRuntime._dispatch()` で `0 < required_delivered < required_total` のとき | 一部 required sink にだけ届いた terminal state。**`delivered` にも `known_rejected` にも含めない**。既存 `_writer_partial_delivered` を公開 contract のソースとして再利用 |

### 2.2 Drop subcounter の出所別分類

```text
worker_known_dropped =
  worker_overload_shed
  + worker_transport_closed_drop
  + worker_writer_unavailable_drop
  + worker_timeout_drop

writer_known_dropped =
  writer_drain_deadline_loss
  (将来追加されうる Writer 側 drop counter もここに分類)
```

### 2.3 Reject subcounter

```text
known_rejected = writer_known_rejected =
  writer_route_reject
  + writer_reconstruct_reject
  + writer_close_marker_reject
  + writer_sink_reject
  + writer_policy_reject
```

reject は Writer 側でしか発生しない。

### 2.4 Invariant 8 条(実装契約)

```text
1. attempted は worker-side MP proxy handler に到達した record 数である。
   加算地点は MPClientTransport._emit_record() の入口とする。
   _drop() 内では加算しない。

2. accepted は Writer が log_queue から通常 LogEvent を取り出した数である。
   CloseMarker / STOP sentinel / control message は除外する。
   _reconstruct_record() の前に加算する。
   reconstruct_reject / route_reject / sink_reject / policy_reject は
   accepted の内側に含める(accepted >= known_rejected を保証)。

3. delivered は全 required sink への delivery が成功した record 数である。
   「最低 1 sink 成功」ではない。

4. partial_delivered は 0 < required_delivered < required_total の terminal state である。
   delivered にも known_rejected にも含めない。

5. known_rejected = sum(writer_reject_breakdown.values())
                  = writer_route_reject + writer_reconstruct_reject
                    + writer_close_marker_reject + writer_sink_reject
                    + writer_policy_reject

6. known_dropped = sum(worker_drop_breakdown.values())
                 + sum(writer_drop_breakdown.values())

7. shutdown 時の writer-side invariant:
     accepted = delivered + partial_delivered + writer_known_rejected
              + writer_known_dropped + unexplained_lost

8. attempted-side invariant:
     attempted = accepted + worker_known_dropped + unreported_worker_gap
   active worker / crash worker の未集約分がある場合、
   snapshot_complete は false とし、missing_detach_clients で明示する。
```

### 2.5 `unreported_worker_gap` の扱い

- active worker または crash worker の未集約分。
- `snapshot_complete: true`(全 worker が DETACH 済かつ `missing_detach_clients == 0`)のとき → `unreported_worker_gap == 0` が保証される
- それ以外のとき → `unreported_worker_gap` は **正確に算出不能**。`snapshot_complete: false` を立て `missing_detach_clients` で件数明示
- shutdown 時 `unexplained_lost` は writer-side invariant から逆算: `max(0, accepted - delivered - partial_delivered - known_rejected - writer_known_dropped)`

---

## 3. Counter Inventory

### 3.1 既存 counter(変更なし)

| Counter | 定義場所 | 用途 |
|---|---|---|
| `MPClientTransport._drop_counter` | `_mp_attach.py:69` | 全 worker drop の合計 |
| `MPClientTransport._overload_shed` | `_mp_attach.py:71` | process-local async queue full |
| `MPClientTransport._transport_closed_drop` | `_mp_attach.py:72` | transport closed |
| `MPClientTransport._writer_unavailable_drop` | `_mp_attach.py:73` | writer unavailable |
| `MPClientTransport._timeout_drop` | `_mp_attach.py:74` | log plane timeout/full |
| `WriterRuntime._reject_counter` | `_mp_runtime.py:73` | 全 writer reject の合計(既存内部用) |
| `WriterRuntime._writer_route_reject` | `_mp_runtime.py:74` | unknown route |
| `WriterRuntime._writer_reconstruct_reject` | `_mp_runtime.py:75` | LogEvent reconstruct 失敗 |
| `WriterRuntime._writer_close_marker_reject` | `_mp_runtime.py:76` | invalid CloseMarker |
| `WriterRuntime._writer_sink_reject` | `_mp_runtime.py:77` | required handler emit error |
| `WriterRuntime._writer_policy_reject` | `_mp_runtime.py:78` | required handler filter false |
| `WriterRuntime._writer_partial_delivered` | `_mp_runtime.py:79` | 公開 contract `partial_delivered` のソース |
| `WriterRuntime._writer_best_effort_failures` | `_mp_runtime.py:80` | best-effort sink failure(可視化のみ、accounting 外) |
| `WriterRuntime._writer_drain_deadline_loss` | `_mp_runtime.py:88` | drain deadline 超過の loss |
| `WriterRuntime._writer_flush_error_count` | `_mp_runtime.py:89` | flush 失敗(可視化のみ、accounting 外) |

### 3.2 新規 counter(Phase 2 で追加)

| Counter | 追加場所 | 加算地点 |
|---|---|---|
| `MPClientTransport._attempted: int` | `_mp_attach.py` `__init__` (L80 付近に追記) | `_emit_record()` 入口、現 L144 の `if self._closed or self._stopping:` の **直前**に `self._attempted += 1` を挿入 |
| `WriterRuntime._accepted: int` | `_mp_runtime.py` `__init__` (L72 付近に追記) | `_log_loop()` 内、現 L292 の `continue` 直後 / L293 の `try:` 直前に `self._accepted += 1` を挿入(close marker 判定が False になった分岐) |
| `WriterRuntime._delivered: int` | `_mp_runtime.py` `__init__` (L79 付近に追記) | `_dispatch()` 内、現 L388 の `if required_delivered == required_total:` ブロックで L389 の `return  # full delivery` の直前に `self._delivered += 1` を挿入 |
| `WriterRuntime._aggregate_worker_attempted: int` | `_mp_runtime.py` `__init__` | DETACH 受信時に `payload['local_drop_summary']['attempted']` を加算 |
| `WriterRuntime._aggregate_worker_drop_counter: int` | 同上 | DETACH 受信時に `payload['local_drop_summary']['drop_counter']` を加算 |
| `WriterRuntime._aggregate_worker_overload_shed: int` | 同上 | DETACH 受信時に同 field を加算 |
| `WriterRuntime._aggregate_worker_transport_closed_drop: int` | 同上 | 同上 |
| `WriterRuntime._aggregate_worker_writer_unavailable_drop: int` | 同上 | 同上 |
| `WriterRuntime._aggregate_worker_timeout_drop: int` | 同上 | 同上 |
| `WriterRuntime._warning_queue_drain_incomplete: bool` | `_mp_runtime.py` `__init__` | `stop()` 内の drain window 終了後、warning queue が空でなければ True に設定 |

### 3.3 ATTACH/DETACH ledger 拡張(`missing_detach_client_ids` のため)

既存 `WriterRuntime._active_clients: dict[str, dict[str, Any]]` (L66) に **`pid` field 必須化** を加える。

- 現状: ATTACH payload の `pid` は client 側から送られていない(`_make_attach_request` には pid 引数なし)→ Writer 側で `payload.get('pid', 0)` で 0 になる
- 変更: ATTACH payload に `os.getpid()` を含める → Writer 側で `_active_clients[client_id]['pid']` に正しい pid が記録される

shutdown 時:
- `_active_clients` に残っている entry = DETACH を受けていない client = `missing_detach_clients`
- それぞれの `client_id` を `missing_detach_client_ids` に、`pid` を `missing_detach_pids` に出力

---

## 4. Wire Protocol 変更

### 4.1 ATTACH payload 拡張

```python
# _mp_attach._do_attach() で送信
{
    'session_id': str,
    'protocol_version': int,
    'registry_hash': str,
    'pid': int,                    # ← 新規。os.getpid() で設定
}
```

`_make_attach_request()` のシグネチャに `pid: int` 引数を追加。

### 4.2 DETACH payload 拡張

```python
# _mp_attach._do_detach() で送信
{
    'close_marker_failed': bool,
    'local_drop_summary': {        # ← 新規
        'attempted':                int,
        'drop_counter':             int,
        'overload_shed':            int,
        'transport_closed_drop':    int,
        'writer_unavailable_drop':  int,
        'timeout_drop':             int,
        'module_transport_count':   int,    # 集約元の module_transport 数(0 = root のみ)
    },
}
```

`_make_detach_request()` のシグネチャに `local_drop_summary: dict[str, int]` 引数を追加。

**Writer 側受信** (`_cmd_detach()`):
```python
local = payload.get('local_drop_summary') or {}
self._aggregate_worker_attempted             += int(local.get('attempted', 0))
self._aggregate_worker_drop_counter          += int(local.get('drop_counter', 0))
self._aggregate_worker_overload_shed         += int(local.get('overload_shed', 0))
self._aggregate_worker_transport_closed_drop += int(local.get('transport_closed_drop', 0))
self._aggregate_worker_writer_unavailable_drop += int(local.get('writer_unavailable_drop', 0))
self._aggregate_worker_timeout_drop          += int(local.get('timeout_drop', 0))
```

payload に `local_drop_summary` が欠落していても KeyError にしない(将来追加 field 欠落への保険)。

### 4.3 WARN queue(新規、control queue とは分離)

#### 4.3.1 queue 自体

`BootstrapContext` に新 field を追加:

```python
@dataclass(frozen=True)
class BootstrapContext:
    ...
    warning_queue: Any  # multiprocessing.Queue — runtime warning plane (新規)
```

queue の生成は `mp/__init__.py::ConfigureLogger()` 内の queue 作成ブロック(現 L775-777 付近):

```python
warning_queue = ipc_mp_ctx.Queue(maxsize=_WARNING_QUEUE_MAXSIZE)  # 推奨: 1024
```

#### 4.3.2 RuntimeWarningPayload(TypedDict)

`src/dsafelogger/_runtime_warning.py`(新規)で定義:

```python
from typing import Any, Literal, TypedDict

class RuntimeWarningPayload(TypedDict, total=False):
    # 必須
    schema_version: int          # = 1
    ts: str                      # ISO 8601, timezone-aware
    pid: int
    component: Literal['writer', 'worker', 'control', 'shutdown']
    event: str
    level: Literal['warning', 'error']

    # 任意
    classification: Literal['KnownRejected', 'KnownDropped', 'UnexplainedLost'] | None
    reason: str | None
    counter_name: str | None
    counter_value: int | None
    context: dict[str, Any] | None
```

#### 4.3.3 送信 semantics(非 blocking 必須)

```python
# worker 側
try:
    ctx.warning_queue.put_nowait(payload)
except (queue.Full, BrokenPipeError, EOFError, OSError, ValueError):
    # IPC 障害 or queue 満杯 → fallback file 書き込みへ
    _write_fallback(payload, fallback_path)
```

**禁止事項**:
- `put(block=True)` 系の使用禁止(logging path を blocking させない)
- ACK 待ち禁止(`reply_to` 不要)
- 既存 `ControlRequest` の `command` Literal に WARN を追加することは禁止(control plane と完全分離)

#### 4.3.4 Writer 側 consumer

```python
# WriterRuntime._runtime_warning_consumer
def _runtime_warning_consumer(self) -> None:
    while True:
        try:
            payload = self._ctx.warning_queue.get(timeout=0.1)
        except queue.Empty:
            if self._stop_requested and self._consumer_drain_window_elapsed():
                return
            continue
        if payload is None:  # sentinel
            return
        self._runtime_warning_sink.write(payload)
```

- daemon=True
- stop_requested 後、`_DRAIN_WINDOW_SEC = 0.5` だけ drain
- drain window 内に空にならなければ `_warning_queue_drain_incomplete = True`

#### 4.3.5 Fallback file 命名

worker fallback path: `<runtime_warning_path>.<pid>.fallback.jsonl`
- 例: `runtime_warning_path = "./logs/MyApp.runtime-warnings.jsonl"` → fallback = `"./logs/MyApp.runtime-warnings.jsonl.42.fallback.jsonl"`
- parent directory は同じ。worker pid は数値そのまま挿入

---

## 5. BootstrapContext 拡張

### 5.1 新規 field

```python
@dataclass(frozen=True)
class BootstrapContext:
    ...  # 既存 field
    warning_queue: Any  # multiprocessing.Queue (新規)
```

### 5.2 `resolved_config` 拡張

`mp/__init__.py::ConfigureLogger()` の `worker_resolved_config` (現 L780-786) に追加:

```python
worker_resolved_config: dict[str, object] = {
    'is_async': bool(args_config['is_async']),
    'log_level': args_config['default_level'],
    'module_routes': module_routes,
    'module_levels': module_levels,
    'mp_start_method': ipc_mp_ctx.get_start_method(),
    # 新規(以下 2 つは絶対パス、None も許容)
    'runtime_warning_path': str | None,
    'shutdown_report_path': str | None,  # worker 側では使わないが digest 整合のため含める
}
```

### 5.3 絶対パス化責務

`mp.ConfigureLogger()` 内で、引数として受けた `runtime_warning_path` / `shutdown_report_path` を即座に絶対化:

```python
def _resolve_observability_path(path: str | None) -> str | None:
    if path is None:
        return None
    return str(Path(path).expanduser().resolve())
```

理由: worker は spawn 後の cwd が parent と異なる可能性があるため、相対パスのままだと fallback file が予期しない場所に書かれる。

### 5.4 digest 計算

`resolved_config_digest` (現 `mp/__init__.py:787-789`) は `worker_resolved_config` 全体の `json.dumps(..., sort_keys=True)` 上の SHA-256。新 path field も自動的に digest に含まれる。

---

## 6. Module transport 集約ルール

`_do_detach()` 内で `local_drop_summary` を作る際、`state.root_transport` と `state.module_transports.values()` の全 counter を合算する:

```python
def _build_local_drop_summary(state: MPProcessState) -> dict[str, int]:
    all_transports = [state.root_transport, *state.module_transports.values()]
    return {
        'attempted':                sum(t._attempted for t in all_transports),
        'drop_counter':             sum(t._drop_counter for t in all_transports),
        'overload_shed':            sum(t._overload_shed for t in all_transports),
        'transport_closed_drop':    sum(t._transport_closed_drop for t in all_transports),
        'writer_unavailable_drop':  sum(t._writer_unavailable_drop for t in all_transports),
        'timeout_drop':             sum(t._timeout_drop for t in all_transports),
        'module_transport_count':   len(state.module_transports),
    }
```

集約は `_do_detach()` Phase 3(`_make_detach_request` 呼び出し直前)で実行。

---

## 7. shutdown_report JSON Schema

### 7.1 Field 一覧

| Field | 型 | 意味 |
|---|---|---|
| `schema_version` | int | = 1 |
| `session_id` | str | Writer の `BootstrapContext.session_id` |
| `writer_pid` | int | Writer プロセスの pid |
| `started_at` | str (ISO 8601) | Writer 起動時刻 |
| `stopped_at` | str (ISO 8601) | Writer 停止時刻 |
| `duration_sec` | float | `stopped_at - started_at` |
| `active_clients_peak` | int | 同時 attach の最大数 |
| `attempted` | int | accounting invariant の attempted |
| `accepted` | int | 同 accepted |
| `delivered` | int | 同 delivered |
| `partial_delivered` | int | 同 partial_delivered |
| `known_rejected` | int | `sum(writer_reject_breakdown.values())` |
| `known_dropped` | int | `sum(worker_drop_breakdown.values()) + sum(writer_drop_breakdown.values())` |
| `unexplained_lost` | int | `max(0, accepted - delivered - partial_delivered - known_rejected - writer_known_dropped)` |
| `writer_reject_breakdown` | dict[str, int] | 5 種の writer reject 内訳 |
| `worker_drop_breakdown` | dict[str, int] | 4 種の worker drop 内訳(`writer_drain_deadline_loss` を含まない) |
| `writer_drop_breakdown` | dict[str, int] | Writer 由来 drop の内訳。現在は `writer_drain_deadline_loss` のみ |
| `best_effort_failures` | int | best-effort sink 失敗数(accounting 外、可視化のみ) |
| `flush_error_count` | int | flush 失敗数(accounting 外、可視化のみ) |
| `worker_crash_observed` | bool | `missing_detach_clients > 0` または `close_marker_failed=true` を含む場合 `true` |
| `missing_detach_clients` | int | DETACH を受けていない client 数 |
| `missing_detach_client_ids` | list[str] | 同 client の `client_id` リスト |
| `missing_detach_pids` | list[int] | 同 client の `pid` リスト |
| `snapshot_complete` | bool | `missing_detach_clients == 0` AND `shutdown_result != "drain_deadline_exceeded"` |
| `warning_queue_drain_incomplete` | bool | shutdown 時 warning queue が drain window 内に空にならなかった場合 `true` |
| `shutdown_result` | str | `"clean"` / `"clean_with_worker_crash"` / `"degraded"` / `"drain_deadline_exceeded"` |

### 7.2 例(invariant 準拠)

```json
{
  "schema_version": 1,
  "session_id": "5f4d3c2b1a098765f4d3c2b1a0987654",
  "writer_pid": 12345,
  "started_at": "2026-05-23T10:00:00.000+09:00",
  "stopped_at": "2026-05-23T11:00:00.000+09:00",
  "duration_sec": 3600.0,
  "active_clients_peak": 4,

  "attempted": 120000,
  "accepted": 119990,
  "delivered": 119980,
  "partial_delivered": 5,
  "known_rejected": 5,
  "known_dropped": 10,
  "unexplained_lost": 0,

  "writer_reject_breakdown": {
    "writer_route_reject": 0,
    "writer_reconstruct_reject": 0,
    "writer_close_marker_reject": 0,
    "writer_sink_reject": 5,
    "writer_policy_reject": 0
  },
  "worker_drop_breakdown": {
    "worker_overload_shed": 0,
    "worker_transport_closed_drop": 0,
    "worker_writer_unavailable_drop": 0,
    "worker_timeout_drop": 10
  },
  "writer_drop_breakdown": {
    "writer_drain_deadline_loss": 0
  },

  "best_effort_failures": 0,
  "flush_error_count": 0,

  "worker_crash_observed": false,
  "missing_detach_clients": 0,
  "missing_detach_client_ids": [],
  "missing_detach_pids": [],
  "snapshot_complete": true,

  "warning_queue_drain_incomplete": false,
  "shutdown_result": "clean"
}
```

### 7.3 整合検算(上記例)

**writer-side invariant**:
```
accepted = delivered + partial_delivered + known_rejected + writer_known_dropped + unexplained_lost
119990   = 119980    + 5                 + 5              + 0                    + 0
```
- `writer_known_dropped = sum(writer_drop_breakdown.values()) = 0`
- `known_rejected = sum(writer_reject_breakdown.values()) = 0+0+0+5+0 = 5`

**attempted-side invariant**(`snapshot_complete: true` のため厳密成立):
```
attempted = accepted + worker_known_dropped + unreported_worker_gap
120000    = 119990   + 10                   + 0
```
- `worker_known_dropped = sum(worker_drop_breakdown.values()) = 0+0+0+10 = 10`
- `unreported_worker_gap = 0`(snapshot_complete=true のとき必ず 0)

**派生値**:
- `known_dropped = worker_known_dropped + writer_known_dropped = 10 + 0 = 10` ✓

この JSON は実装の fixture / expected output として直接流用可能。

### 7.4 Atomic write 規約

- `tempfile.NamedTemporaryFile(dir=parent_dir, delete=False)` で同一ディレクトリに一時ファイル作成
- 内容書き出し完了後 `os.replace(tmp_path, shutdown_report_path)`
- **Windows での挙動**: `os.replace()` は target が `FILE_SHARE_DELETE` なしで他プロセスから open されていると `PermissionError` で失敗する → その場合は stderr fallback warning + `RuntimeWarningSink` への記録、shutdown 自体は完了させる

---

## 8. `mp.DeliveryStatus` (TypedDict)

### 8.1 定義

```python
# src/dsafelogger/mp/__init__.py
from typing import TypedDict

class DeliveryStatus(TypedDict):
    schema_version: int        # = 1
    session_id: str
    writer_pid: int
    active_clients: int

    # 公開 contract(アーキテクチャ不変、追加されない)
    attempted: int
    accepted: int
    delivered: int
    partial_delivered: int
    known_rejected: int
    known_dropped: int
    unexplained_lost: int

    # 実装詳細(counter 追加/分割で変わる、型保証なし)
    writer_reject_breakdown: dict[str, int]
    worker_drop_breakdown: dict[str, int]
    writer_drop_breakdown: dict[str, int]

    # 観測範囲メタ情報
    snapshot_complete: bool
    missing_detach_clients: int

    stop_requested: bool
```

### 8.2 shutdown_report との差分

| Field | DeliveryStatus | shutdown_report |
|---|---|---|
| `started_at` / `stopped_at` / `duration_sec` | ✗ | ✓ |
| `active_clients` | ✓(現在値) | `active_clients_peak`(最大値) |
| `missing_detach_client_ids` / `missing_detach_pids` | ✗(件数のみ) | ✓ |
| `warning_queue_drain_incomplete` | ✗(shutdown 後のみ判定可能) | ✓ |
| `worker_crash_observed` | ✗ | ✓ |
| `shutdown_result` | ✗ | ✓ |
| `best_effort_failures` / `flush_error_count` | ✗ | ✓ |
| `stop_requested` | ✓ | ✗(暗に "clean"/"clean_with_worker_crash"/等で表現) |

### 8.3 例(invariant 準拠)

```json
{
  "schema_version": 1,
  "session_id": "5f4d3c2b1a098765f4d3c2b1a0987654",
  "writer_pid": 12345,
  "active_clients": 0,

  "attempted": 119990,
  "accepted": 119990,
  "delivered": 119980,
  "partial_delivered": 5,
  "known_rejected": 5,
  "known_dropped": 0,
  "unexplained_lost": 0,

  "writer_reject_breakdown": {
    "writer_route_reject": 0,
    "writer_reconstruct_reject": 0,
    "writer_close_marker_reject": 0,
    "writer_sink_reject": 5,
    "writer_policy_reject": 0
  },
  "worker_drop_breakdown": {
    "worker_overload_shed": 0,
    "worker_transport_closed_drop": 0,
    "worker_writer_unavailable_drop": 0,
    "worker_timeout_drop": 0
  },
  "writer_drop_breakdown": {
    "writer_drain_deadline_loss": 0
  },

  "snapshot_complete": true,
  "missing_detach_clients": 0,

  "stop_requested": false
}
```

**整合検算**(上記 §8.3 例):

- writer-side: `accepted = delivered + partial_delivered + known_rejected + writer_known_dropped + unexplained_lost`
  - `119990 = 119980 + 5 + 5 + 0 + 0` ✓
- attempted-side: `attempted = accepted + worker_known_dropped + unreported_worker_gap`
  - `119990 = 119990 + 0 + 0` ✓(全 worker DETACH 済、`unreported_worker_gap = 0`)
- `known_dropped = sum(worker_drop_breakdown.values()) + sum(writer_drop_breakdown.values()) = 0 + 0 = 0` ✓

### 8.4 例外仕様

| 状況 | 例外型 | メッセージ例 |
|---|---|---|
| `ConfigureLogger` 未実行 | `RuntimeError` | `"multiprocess runtime is not configured"` |
| Writer 既停止 | `RuntimeError` | `"writer runtime has stopped"` |
| Control ACK timeout | `TimeoutError` | `"GetDeliveryStatus: STATUS ACK timed out"` |

---

## 9. `runtime_warning_path` JSONL Schema

### 9.1 1 行 1 イベント

```json
{
  "schema_version": 1,
  "ts": "2026-05-23T10:22:31.812+09:00",
  "pid": 12345,
  "component": "writer",
  "event": "sink_reject",
  "level": "warning",
  "classification": "KnownRejected",
  "reason": "PermissionError: [Errno 13] ...",
  "counter_name": "writer_sink_reject",
  "counter_value": 5,
  "context": {
    "sink_path": "./logs/MyApp_2026-05-23.log"
  }
}
```

### 9.2 必須/任意

- **必須**: `schema_version`, `ts`, `pid`, `component`, `event`, `level`
- **任意**: `classification`, `reason`, `counter_name`, `counter_value`, `context`

### 9.3 値域

| Field | 値域 |
|---|---|
| `component` | `"writer"` / `"worker"` / `"control"` / `"shutdown"` |
| `level` | `"warning"` / `"error"` |
| `classification` | `"KnownRejected"` / `"KnownDropped"` / `"UnexplainedLost"` / `null` |
| `event` | 下記表 |

### 9.4 `event` 値域(初期版)

| event | 発生元 | classification | 対応 counter |
|---|---|---|---|
| `sink_reject` | writer | KnownRejected | writer_sink_reject |
| `route_reject` | writer | KnownRejected | writer_route_reject |
| `reconstruct_reject` | writer | KnownRejected | writer_reconstruct_reject |
| `close_marker_reject` | writer | KnownRejected | writer_close_marker_reject |
| `policy_reject` | writer | KnownRejected | writer_policy_reject |
| `partial_delivered` | writer | (null) | writer_partial_delivered |
| `best_effort_failure` | writer | (null) | writer_best_effort_failures |
| `drain_deadline_loss` | writer | KnownDropped | writer_drain_deadline_loss |
| `flush_error` | writer | (null) | writer_flush_error_count |
| `overload_shed` | worker | KnownDropped | worker_overload_shed |
| `transport_closed_drop` | worker | KnownDropped | worker_transport_closed_drop |
| `writer_unavailable_drop` | worker | KnownDropped | worker_writer_unavailable_drop |
| `timeout_drop` | worker | KnownDropped | worker_timeout_drop |
| `worker_crash` | shutdown | (null) | missing_detach_clients |
| `shutdown_drain_timeout` | shutdown | (null) | warning_queue_drain_incomplete |

### 9.5 再帰回避の不変条件

`RuntimeWarningSink` は以下を保証する:

1. application log pipeline(`dsafelogger.GetLogger()`)を **絶対に呼ばない**
2. 内部で例外が発生しても `RuntimeWarningSink.write()` 自身を再帰的に呼ばない
3. ファイル書き込みエラー時は stderr fallback のみ(`RuntimeWarningSink` への self-record はしない)

### 9.6 出力先制御

- `runtime_warning_path is None`: 従来通り stderr のみ
- `runtime_warning_path` 指定: stderr **と** JSONL ファイル両方に出る(stderr 出力は維持する。supervisor/container 環境互換のため)

### 9.7 抑制ロジック

同一 `(component, event, reason)` の連続発火を抑制(初回 + 100 回ごと、既存 `_drop()` のパターンに揃える)。`counter_value` field で実発生回数を伝える。

---

## 10. 互換性方針

### 10.1 公開 contract field(変更 = SemVer bump 必須)

以下の 7 field(`DeliveryStatus` および `shutdown_report` の上位)は**アーキテクチャ不変** field。変更には SemVer bump を伴う:

```text
attempted, accepted, delivered, partial_delivered,
known_rejected, known_dropped, unexplained_lost
```

- 追加: MAJOR bump(これら以上の概念は存在しないと宣言済)
- 削除: MAJOR bump
- 型変更: MAJOR bump

### 10.2 breakdown field 内の key(変更 = MINOR bump or 不要)

`writer_reject_breakdown` / `worker_drop_breakdown` / `writer_drop_breakdown` の **dict 内 key** は実装詳細:

- 新 key 追加: MINOR bump 推奨(利用者が新 key を活用したいなら明示更新)
- 既存 key 削除/リネーム: MINOR bump 必須
- breakdown 自体の追加/削除: MAJOR bump

### 10.3 観測範囲メタ情報(変更 = MINOR bump)

```text
snapshot_complete, missing_detach_clients,
missing_detach_client_ids, missing_detach_pids,
warning_queue_drain_incomplete, worker_crash_observed,
shutdown_result, stop_requested
```

- 追加: MINOR bump
- 値域追加(例: `shutdown_result` に新 enum 値): MINOR bump
- 既存値域削除: MAJOR bump

### 10.4 `runtime_warning_path` JSONL schema

- 必須 field 追加/削除: MAJOR bump
- 任意 field 追加: 不要(前方互換)
- `event` enum 追加: 不要(前方互換)
- `event` enum 削除: MINOR bump

### 10.5 schema_version

- shutdown_report / DeliveryStatus / runtime_warning JSONL は全て `schema_version: 1` で開始
- 上記の MAJOR bump 案件発生時に `schema_version: 2` へ。MINOR bump は version 据え置き

---

## 11. Verification アプローチ

### 11.1 Invariant test(独立テスト、Phase 8 で必須)

以下を `tests/test_delivery_accounting_invariants.py`(新規)で網羅する:

```python
def test_writer_side_invariant_under_all_reject_types():
    """全 reject パターンで writer-side invariant が成立する"""

def test_attempted_side_invariant_when_snapshot_complete():
    """snapshot_complete=true 時に attempted-side invariant が厳密成立"""

def test_partial_delivered_not_double_counted():
    """partial 発生時、delivered と known_rejected の両方に加算されない"""

def test_writer_drop_breakdown_excludes_worker_counters():
    """writer_drop_breakdown に worker 由来 counter が混入しない"""

def test_worker_drop_breakdown_excludes_writer_counters():
    """worker_drop_breakdown に writer 由来 counter (drain_deadline_loss) が混入しない"""

def test_known_rejected_sum_equals_breakdown_sum():
    """known_rejected == sum(writer_reject_breakdown.values())"""

def test_known_dropped_sum_equals_both_breakdowns_sum():
    """known_dropped == sum(worker_drop_breakdown.values())
                       + sum(writer_drop_breakdown.values())"""
```

### 11.2 Phase 別の test 参照

| Phase | Test ファイル | 検証内容 |
|---|---|---|
| Phase 1 | `tests/test_runtime_warning.py` | RuntimeWarningSink 16 ケース(ケース網羅、再帰回避、drain) |
| Phase 2 | `tests/test_mp_attach.py` / `tests/test_mp_runtime.py` | DETACH payload 集約、新 counter 加算地点 |
| Phase 3 | `tests/test_shutdown_report.py` | shutdown_report 13 ケース(invariant 検算、Windows replace fallback) |
| Phase 4 | `tests/test_delivery_status_api.py` | GetDeliveryStatus 12 ケース(7 fields、3 breakdown、partial 分離) |
| Phase 6 | `benchmarks/run_multiprocess_compare_v23a.py` | resilience profile での 5 ケース |
| Phase 8 | `tests/test_delivery_accounting_invariants.py` | 上記 invariant test 7 種 |

---

## 12. 用語集

| 用語 | 定義 |
|---|---|
| accounting cut point | counter を +1 する具体的なコード地点 |
| invariant | 実装が常に満たさねばならない数式的関係 |
| `unreported_worker_gap` | active/crash worker の未集約分。snapshot_complete=true 時は必ず 0 |
| snapshot_complete | `missing_detach_clients == 0` AND `shutdown_result != "drain_deadline_exceeded"` |
| writer-side invariant | `accepted = delivered + partial_delivered + known_rejected + writer_known_dropped + unexplained_lost` |
| attempted-side invariant | `attempted = accepted + worker_known_dropped + unreported_worker_gap` |
| required sink | `getattr(handler, '_ds_required', True) == True` の sink。delivered/partial/reject の集計対象 |
| best-effort sink | `_ds_required = False` の sink。accounting 外、可視化のみ |

---

## 13. 改訂履歴

| 日付 | 変更 |
|---|---|
| 2026-05-23 | 初版(v23k 実装契約)。Phase 0.5 完了時点。`multiprocess_observability_implementation_plan.md` v2 レビュー反映後の確定版 |
