# Formatters

**Module**: `dsafelogger._formatter`

Formatters for D-SafeLogger.

# ============================================================================
# [DESIGN GUARD] VENDOR-AGNOSTIC PRINCIPLE
# ============================================================================
# This module must NOT contain any third-party structured logging imports
# (e.g., structlog, loguru) or hardcoded dependencies on their internal structures.
# All extraction must be done via standard logging.LogRecord attributes
# and generic dictionary extractions (e.g. _extract_structured_extra_fields).
# ============================================================================

## Functions

### `_extract_structured_extra_fields(record: 'logging.LogRecord') -> 'dict[str, Any]'`

Collect non-standard LogRecord attributes for structured output.

### `_make_proxy_tls() -> 'threading.local'`

Return a new threading.local for per-thread _DisplayRecordProxy reuse.

Usage (class level)::

    _proxy_tls: threading.local = _make_proxy_tls()

In the hot path::

    proxy = getattr(cls._proxy_tls, 'instance', None)
    if proxy is None:
        proxy = object.__new__(_DisplayRecordProxy)
        cls._proxy_tls.instance = proxy
    proxy.__dict__.clear()
    proxy.__dict__.update(record.__dict__)
    proxy.__dict__['levelname'] = override_value

Each thread gets its own proxy; the proxy dict is updated in-place so
no new Python objects are allocated per call, eliminating GC pressure
in high-throughput multi-threaded scenarios.

## Classes

### `DSafeFormatter(fmt: 'str | None' = None, datefmt: 'str | None' = None, style: "Literal['%', '{', '$']" = '%') -> 'None'`

Standard D-SafeLogger formatter with level abbreviation and context suffix.

Public methods:

- `format(self, record: 'logging.LogRecord') -> 'str'`

### `DiagnosticFormatter(fmt: 'str | None' = None, datefmt: 'str | None' = None, sensitive_keywords: 'frozenset[str] | None' = None) -> 'None'`

Extended formatter that expands f_locals on exceptions.

Used when {prefix}_DIAGNOSE=1 (sanctuary: env-only).

Public methods:

- `format(self, record: 'logging.LogRecord') -> 'str'`

### `DiagnosticStructuredFormatter(sensitive_keywords: 'frozenset[str] | None' = None) -> 'None'`

Structured JSON formatter with f_locals expansion.

Public methods:

- `format(self, record: 'logging.LogRecord') -> 'str'`

### `StructuredFormatter() -> 'None'`

JSON Lines formatter for structured logging.

Public methods:

- `format(self, record: 'logging.LogRecord') -> 'str'`

### `_DisplayRecordProxy(original: 'logging.LogRecord', overrides: 'dict[str, object]') -> "'_DisplayRecordProxy'"`

Display-only view of a LogRecord with attribute overrides.

Copies the original record's __dict__ and applies overrides (e.g.
abbreviated or colourised levelname).  The original record is never
mutated, so concurrent handlers each see the correct display value
without interfering with one another.

Inherits from LogRecord so that class-level methods (e.g. getMessage)
are reachable via normal MRO lookup.  Initialisation is done entirely
in __new__; LogRecord.__init__ is skipped.

Hot path: formatters that call this frequently should use
_make_proxy_tls() to reuse one proxy object per thread rather than
constructing a new instance on every format call.

## Constants

| Name | Type | Value |
|---|---|---|
| `DEFAULT_DATEFMT` | `str` | `'%Y-%m-%d %H:%M:%S'` |
| `DEFAULT_FMT` | `str` | `'%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName...` |
| `MASK_STRING` | `str` | `'*** MASKED ***'` |
| `REPR_TRUNCATE_LIMIT` | `int` | `200` |
