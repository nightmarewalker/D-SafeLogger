# Console Progress Coexistence

D-SafeLogger does not replace terminal UI tools. It keeps stdlib logging
compatibility so progress renderers can keep owning the console while
D-SafeLogger owns durable local files.

Ownership model:

- D-SafeLogger owns append-only local evidence.
- `tqdm` or Rich owns terminal rendering.
- `console_out=False` prevents D-SafeLogger from competing for the terminal.

## tqdm Progress With Durable JSONL

```python
from pathlib import Path

from tqdm import tqdm

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown

Path("logs").mkdir(parents=True, exist_ok=True)

ConfigureLogger(
    log_path="logs",
    pg_name="TqdmProgress",
    structured=True,
    console_out=False,
)

logger = GetLogger("jobs.tqdm")

for item in tqdm(range(3), desc="import"):
    logger.info("processed item", extra={"item": item, "renderer": "tqdm"})

SafeShutdown()
```

## Rich Progress With Durable JSONL

```python
import io
import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress

from dsafelogger import ConfigureLogger, GetLogger, SafeShutdown

Path("logs").mkdir(parents=True, exist_ok=True)

ConfigureLogger(
    log_path="logs",
    pg_name="RichProgress",
    structured=True,
    console_out=False,
)

console = Console(file=io.StringIO(), force_terminal=False)
rich_handler = RichHandler(console=console, show_time=False, show_path=False)
logging.getLogger().addHandler(rich_handler)

try:
    logger = GetLogger("jobs.rich")
    with Progress(console=console, transient=True) as progress:
        task = progress.add_task("export", total=3)
        for item in range(3):
            logger.info("processed item", extra={"item": item, "renderer": "rich"})
            progress.advance(task)
finally:
    logging.getLogger().removeHandler(rich_handler)
    rich_handler.close()
    SafeShutdown()
```

In both patterns, terminal progress remains readable and D-SafeLogger writes
structured local evidence that can be collected later.
