# dsafelogger._shutdown_report

**Module**: `dsafelogger._shutdown_report`

Atomic shutdown report writer for multiprocess delivery accounting.

## Classes

### `ShutdownReportWriter(path: 'str | os.PathLike[str]') -> 'None'`

Write a single JSON shutdown report using same-directory replace.

Public methods:

- `write(self, report: 'dict[str, Any]') -> 'None'`
