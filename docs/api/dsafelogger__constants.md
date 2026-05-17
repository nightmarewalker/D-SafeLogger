# Constants

**Module**: `dsafelogger._constants`

Constants for D-SafeLogger.

## Constants

| Name | Type | Value |
|---|---|---|
| `BUILTIN_SENSITIVE_KEYWORDS` | `frozenset` | `frozenset({'access_key', 'api_key', 'apikey', 'auth', 'cookie', 'credential',...` |
| `DEFAULT_DATEFMT` | `str` | `'%Y-%m-%d %H:%M:%S'` |
| `DEFAULT_FMT` | `str` | `'%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName...` |
| `IPC_DRAIN_TIMEOUT_SEC` | `float` | `15.0` |
| `IPC_PUT_TIMEOUT_SEC` | `float` | `5.0` |
| `IPC_QUEUE_DEFAULT_SIZE` | `int` | `10000` |
| `MASK_STRING` | `str` | `'*** MASKED ***'` |
| `MIN_FREE_SPACE_BYTES` | `int` | `10485760` |
| `QUEUE_DRAIN_TIMEOUT_SEC` | `float` | `10.0` |
| `REPR_TRUNCATE_LIMIT` | `int` | `200` |
| `SHA256_CHUNK_SIZE` | `int` | `65536` |
| `VALID_MIN_INTERVAL_DIVISORS` | `frozenset` | `frozenset({1, 10, 12, 15, 2, 20, 3, 30, 4, 5, 6, 60})` |
| `VALID_ROUTING_MODES` | `frozenset` | `frozenset({'count', 'cyclic_month', 'cyclic_weekday', 'daily', 'hourly', 'min...` |
| `WEEKDAY_SUFFIXES` | `tuple` | `('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')` |
| `WORKER_JOIN_TIMEOUT_SEC` | `float` | `5.0` |
