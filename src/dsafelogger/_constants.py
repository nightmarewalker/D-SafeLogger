"""Constants for D-SafeLogger."""

from __future__ import annotations

# ── Default format strings ──
DEFAULT_FMT = '%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s'
DEFAULT_DATEFMT = '%Y-%m-%d %H:%M:%S'

# ── Timeouts ──
QUEUE_DRAIN_TIMEOUT_SEC = 10.0
WORKER_JOIN_TIMEOUT_SEC = 5.0
# v22: IPC Transport timeouts
IPC_QUEUE_DEFAULT_SIZE = 10000   # multiprocessing.Queue の maxsize デフォルト
IPC_DRAIN_TIMEOUT_SEC = 15.0     # IPCListener スレッドの join タイムアウト
IPC_PUT_TIMEOUT_SEC = 5.0        # mp.Queue.put() のタイムアウト（bounded wait + warning + drop）

# ── Valid routing modes ──
VALID_ROUTING_MODES = frozenset({
    'none', 'daily', 'hourly', 'min_interval',
    'startup_interval', 'size', 'count',
    'cyclic_weekday', 'cyclic_month',
})

# ── Built-in sensitive keywords for f_locals masking (12 words) ──
BUILTIN_SENSITIVE_KEYWORDS: frozenset[str] = frozenset({
    'password', 'passwd', 'secret', 'token',
    'api_key', 'apikey', 'access_key', 'private_key',
    'credential', 'auth', 'session_id', 'cookie',
})

# ── repr truncation limit for diagnostic formatter ──
REPR_TRUNCATE_LIMIT = 200
MASK_STRING = '*** MASKED ***'

# ── SHA-256 chunk size ──
SHA256_CHUNK_SIZE = 65536  # 64KB

# ── Minimum free disk space for archive (bytes) ──
MIN_FREE_SPACE_BYTES = 10 * 1024 * 1024  # 10 MB

# ── Valid interval divisors of 60 for min_interval ──
VALID_MIN_INTERVAL_DIVISORS = frozenset({1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60})

# ── Weekday suffixes ──
WEEKDAY_SUFFIXES = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')

# ── Dynamic Flags (Mutable via ConfigureLogger but kept here for fast top-level import) ──
_diagnose_enabled = False
_resolved_sensitive_keywords: frozenset[str] = BUILTIN_SENSITIVE_KEYWORDS
