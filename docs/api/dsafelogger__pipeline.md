# Configuration Pipeline

**Module**: `dsafelogger._pipeline`

Pipeline abstraction for D-SafeLogger.

Coordinates Capture, Transport, and Sink layers.
reopen_file_sinks() supports external log rotation coexistence.

## Classes

### `FormatterConfigDict(...)`

dict() -> new empty dictionary
dict(mapping) -> new dictionary initialized from a mapping object's
    (key, value) pairs
dict(iterable) -> new dictionary initialized as if via:
    d = {}
    for k, v in iterable:
        d[k] = v
dict(**kwargs) -> new dictionary initialized with the name=value pairs
    in the keyword argument list.  For example:  dict(one=1, two=2)

### `Pipeline(transport: 'Transport', module_transports: 'dict[str, Transport]') -> 'None'`

Active logging pipeline encompassing Transport and Root attach points.

Public methods:

- `get_module_handler(self, mod_name: 'str') -> 'logging.Handler | None'`
- `get_root_handler(self) -> 'logging.Handler'`
- `reopen_file_sinks(self) -> 'int'`
- `start(self) -> 'None'`
- `stop(self, timeout: 'float | None' = None) -> 'None'`

### `PipelineBuilder()`

Builder for constructing a Pipeline from a ResolvedConfig.

Public methods:

- `build(self, config: 'ResolvedConfig') -> 'Pipeline'`

### `ResolvedConfig(pg_name: 'str', log_dir: 'Path', file_fmt: 'str | FormatterConfigDict | logging.Formatter', console_fmt: 'str | FormatterConfigDict | logging.Formatter', routing_mode: 'str', routing_kwargs: 'dict', backup_count: 'int', archive_mode: 'bool', enable_hash: 'bool', manifest_path: 'Path | None', encoding: 'str', diagnose: 'bool', max_level: 'str', console: 'bool', is_async: 'bool', queue_size: 'int', log_level: 'str', color_stream: 'bool', module_configs: 'dict[str, dict]', color_overrides: 'dict[str, str]', datefmt: 'str | None' = None, sensitive_keywords: 'frozenset[str]' = frozenset({'access_key', 'api_key', 'apikey', 'auth', 'cookie', 'credential', 'passwd', 'password', 'private_key', 'secret', 'session_id', 'token'})) -> None`

Resolved configuration holding 3-layer merged parameters.

## Constants

| Name | Type | Value |
|---|---|---|
| `BUILTIN_SENSITIVE_KEYWORDS` | `frozenset` | `frozenset({'access_key', 'api_key', 'apikey', 'auth', 'cookie', 'credential',...` |
| `DEFAULT_FMT` | `str` | `'%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName...` |
