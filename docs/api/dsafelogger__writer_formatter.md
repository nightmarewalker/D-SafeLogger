# Writer Formatter Utilities

**Module**: `dsafelogger._writer_formatter`

Writer Formatter helper for D-SafeLogger multiprocess support.

Provides FormatterSpec (TypedDict) and helpers to freeze/rebuild
Formatter instances across process boundaries without pickle or
arbitrary import.

Allow-list (exact type match only):
    logging.Formatter
    DSafeFormatter
    DiagnosticFormatter
    StructuredFormatter
    DiagnosticStructuredFormatter

Custom subclasses raise TypeError at freeze time.

## Functions

### `freeze_formatter(instance: 'logging.Formatter') -> 'FormatterSpec'`

Convert a Formatter instance to a picklable FormatterSpec.

Only exact types in the allow-list are accepted; custom subclasses
and any other types raise TypeError.

Raises:
    TypeError: If ``type(instance)`` is not in the allow-list.

### `rebuild_formatter(spec: 'FormatterSpec') -> 'logging.Formatter'`

Reconstruct a Formatter instance from a FormatterSpec.

Raises:
    ValueError: If ``kind`` is missing or not in the allow-list.

## Classes

### `FormatterSpec(...)`

Picklable specification of a Formatter for cross-process reconstruction.
