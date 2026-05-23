# v23k Runtime Warning Design

This supplement defines the runtime-warning path used by `dsafelogger.mp`.

## Goals

- Preserve runtime/transport warnings when stderr is unavailable.
- Keep runtime warnings out of the application log pipeline.
- Avoid recursive logging when a sink failure is the reason for the warning.
- Keep the logging path non-blocking when the warning queue is full.

## Output Contract

`runtime_warning_path` is a JSON Lines file. Each line is one warning payload with `schema_version`, timestamp, pid, component, event, and level. Optional fields include classification, reason, counter name/value, and context.

The Writer process owns the primary file handle. Worker processes normally send warning payloads through a dedicated warning queue. If the queue or IPC path fails, a worker writes a local fallback file:

```text
<runtime_warning_path>.<pid>.fallback.jsonl
```

## Queue And Fallback Semantics

- Worker warning enqueue uses `put_nowait`; it must not block application logging.
- Queue `Full`, broken pipe, EOF, OS, or closed-value failures fall back to the local file.
- Writer-side warnings write directly through `RuntimeWarningSink`.
- RuntimeWarningSink failures fall back only to stderr and must not call itself recursively.

## Shutdown Drain

During `WriterRuntime.stop()`, the warning consumer receives a sentinel and drains within a bounded window. If the window is exceeded, `WriterRuntime._warning_queue_drain_incomplete` becomes `True` and the shutdown report records `warning_queue_drain_incomplete: true`.

## Concept Boundary

`diagnose` enriches application log records. Runtime warnings describe D-SafeLogger runtime failures. Delivery status and shutdown report describe classified delivery accounting. These are separate observability channels.
