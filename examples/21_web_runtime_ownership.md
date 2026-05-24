# Web Runtime Ownership

<!-- example-test: docs-only; web framework startup is outside D-SafeLogger scope -->

## 1. What this guide covers

This guide explains ownership boundaries when D-SafeLogger is used inside web
and task runtimes. It is docs-only because starting real web servers, reloaders,
process managers, and task workers is outside D-SafeLogger's test scope.

## 2. The ownership problem

Web runtimes already own some logs. D-SafeLogger should not fight them for
access logs, server lifecycle messages, or framework bootstrap output.

| Runtime | Runtime-owned logs | D-SafeLogger-owned logs |
|---|---|---|
| Uvicorn | access log, server startup/shutdown, reload | application business logs |
| Gunicorn | master/worker lifecycle, access/error | worker application durable logs |
| Django | framework logger / `LOGGING` dictConfig | selected application loggers |
| Celery | worker/task bootstrap, task metadata | task durable application evidence |

## 3. Uvicorn / FastAPI

Let Uvicorn keep server and access logs. Configure D-SafeLogger in application
startup for application loggers only.

<!-- example-test: docs-only; web framework startup is outside D-SafeLogger scope -->

```python
from fastapi import FastAPI
from dsafelogger import ConfigureLogger, GetLogger

app = FastAPI()


@app.on_event("startup")
def configure_application_logging() -> None:
    ConfigureLogger(
        log_path="./logs",
        pg_name="FastAPIApp",
        structured=True,
        console_out=False,
    )


@app.get("/checkout/{order_id}")
def checkout(order_id: str) -> dict[str, str]:
    logger = GetLogger("app.checkout")
    logger.info("checkout requested", extra={"order_id": order_id})
    return {"status": "ok"}
```

## 4. Gunicorn

Gunicorn owns master/worker lifecycle logs. If each worker is a normal
single-process web worker, configure D-SafeLogger inside the worker process and
write application evidence to local files.

<!-- example-test: docs-only; web framework startup is outside D-SafeLogger scope -->

```python
def post_worker_init(worker) -> None:
    from dsafelogger import ConfigureLogger

    ConfigureLogger(
        log_path="./logs",
        pg_name=f"GunicornWorker{worker.pid}",
        structured=True,
        console_out=False,
    )
```

Use `dsafelogger.mp` only when one parent-side Writer is intentionally managing
file sinks for multiple worker processes.

## 5. Django

Django's `LOGGING` dictConfig owns framework logger configuration. Use
D-SafeLogger for selected application entry points where durable local evidence
is required.

<!-- example-test: docs-only; web framework startup is outside D-SafeLogger scope -->

```python
from dsafelogger import ConfigureLogger, GetLogger


def ready() -> None:
    ConfigureLogger(
        log_path="./logs",
        pg_name="DjangoApp",
        structured=True,
        console_out=False,
    )


def handle_checkout(order_id: str) -> None:
    GetLogger("orders.checkout").info("checkout handled", extra={"order_id": order_id})
```

## 6. Celery

Celery owns worker and task bootstrap logs. Use D-SafeLogger inside task logic
for durable application evidence, and keep the task runtime's own output under
Celery control.

<!-- example-test: docs-only; web framework startup is outside D-SafeLogger scope -->

```python
from celery import Celery
from dsafelogger import ConfigureLogger, GetLogger

app = Celery("tasks")


@app.task
def reconcile_account(account_id: str) -> None:
    ConfigureLogger(
        log_path="./logs",
        pg_name="CeleryTask",
        structured=True,
        console_out=False,
    )
    GetLogger("tasks.reconcile").info(
        "reconciliation started",
        extra={"account_id": account_id},
    )
```

## 7. Multiprocess considerations

Do not mix a framework process manager's worker lifecycle with
`dsafelogger.mp` unless you explicitly own the parent process that starts the
Writer and passes the `BootstrapContext` to workers. For Uvicorn/Gunicorn/Celery
managed processes, the simpler ownership model is often per-worker
single-process D-SafeLogger plus an external collector.

## 8. Boundaries

D-SafeLogger does not own web server lifecycle, access log formatting, reload
behavior, task queue semantics, or framework startup. It owns durable local
application evidence when you configure it inside the appropriate process.

## See also

- [Multiprocess Logging](12_multiprocess_logging.md)
- [Container and Collector Coexistence](17_container_collector_coexistence.md)
- [Testing and Warnings](20_testing_and_warnings.md)
