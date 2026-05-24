# Debugging in Production

The most dangerous bugs are the ones you can only reproduce in production. You need to see local
variables in the stack trace — but you absolutely cannot leak passwords, API keys, or session tokens
into a log file. D-SafeLogger's diagnostic mode gives you full `f_locals` expansion while
automatically masking sensitive data, and custom log levels let you add fine-grained tracing without
affecting your existing log levels.

---

## The Sanctuary Pattern

Diagnostic mode is deliberately hard to enable. This is by design — it's a safety mechanism:

- **A developer can't accidentally enable it in code** — there is no Python parameter for it.
- **An INI config can't turn it on** — the setting is not recognized in config files.
- **ONLY an operator setting `D_LOG_DIAGNOSE=1` can activate it.**

This prevents the single most common source of credential leaks: "debug mode left on in production."
The operator who sets the environment variable knows exactly what they're doing, and they remove it
as soon as the debugging session is over.

---

## What Diagnostic Mode Shows

Consider this function:

```python
def process_payment(user_id: int, api_key: str, amount: float):
    token = 'tok_live_abc123'
    if amount > 10000:
        raise ValueError('Amount exceeds daily limit')
```

When this raises an exception and `D_LOG_DIAGNOSE=1` is set, the error log includes local
variables — with sensitive ones masked:

```
2026-04-03 09:15:22.738 [ERR][payment.py:5:process_payment] Payment failed
Traceback (most recent call last):
  File "payment.py", line 4, in process_payment
    raise ValueError('Amount exceeds daily limit')
ValueError: Amount exceeds daily limit

--- Local Variables (payment.py:5) ---
  user_id = 42
  api_key = *** MASKED ***
  amount = 15000.0
  token = *** MASKED ***
```

`api_key` matches the built-in keyword `api_key`. `token` matches `token`. Both are replaced with
`*** MASKED ***` automatically — no configuration needed.

---

## Built-in Sensitive Keywords

D-SafeLogger ships with 12 keywords that trigger automatic masking:

| Category 1 | Category 2 | Category 3 |
|---|---|---|
| `password` | `passwd` | `secret` |
| `token` | `api_key` | `apikey` |
| `access_key` | `private_key` | `credential` |
| `auth` | `session_id` | `cookie` |

Any local variable whose name contains one of these words (case-insensitive) is masked in
diagnostic output.

---

## What Is NOT Masked

Masking applies only to **diagnostic-mode local variables** (`f_locals`) whose **variable names**
match the built-in or custom keyword list.

These are **not** auto-masked:

- Message text that you pass to `logger.info(...)`, `logger.error(...)`, etc.
- Fields added through `extra=...`, `contextualize()`, or structured JSON output.
- Normal non-diagnostic logging when `D_LOG_DIAGNOSE` is off.

If you place a secret directly in the message body or extra fields, it is logged **as-is**.
Keep secrets in variables whose names match your masking rules, or redact them before logging.

---

## Custom Keywords

Add domain-specific keywords to extend (or replace) the built-in list:

```python
from dsafelogger import ConfigureLogger

# Add to the built-in list (12 defaults + your extras)
ConfigureLogger(sens_kws=['ssn', 'credit_card', 'account_number'])

# Or replace the built-in list entirely
ConfigureLogger(sens_kws=['ssn'], sens_kws_replace=True)
```

Use `sens_kws_replace=True` only when you need precise control over which keywords are masked.
In most cases, extending the default list is safer.

---

## Custom Levels for Production Tracing

Register fine-grained levels to control verbosity without code changes:

```python
from dsafelogger import ConfigureLogger, GetLogger, RegisterLevel

# TRACE below DEBUG — extremely verbose, off by default
RegisterLevel('TRACE', 5, 'TRC', '\033[90m')

# AUDIT above WARNING — always visible in normal operation
RegisterLevel('AUDIT', 35, 'AUD', '\033[95m')

# RegisterLevel must be called BEFORE ConfigureLogger
ConfigureLogger(
    log_path='./logs', pg_name='MyApp',
    default_level='INFO',
)

logger = GetLogger('app')
logger.trace('Entering request handler for /api/users')   # filtered out (5 < 20)
logger.info('Request processed')                           # visible (20 >= 20)
logger.audit('User exported PII data')                     # visible (35 >= 20)
```

In normal operation, TRACE is invisible. During an emergency:

```bash
D_LOG_LEVEL=TRACE python app.py
```

Now every TRACE message appears — without changing a single line of code.

---

## The Emergency Debugging Workflow

When a critical bug surfaces in production:

1. **Bug reported** — users see errors, metrics spike.
2. **Operator sets environment variables:**
   ```bash
   # Linux / macOS
   export D_LOG_LEVEL=TRACE
   export D_LOG_DIAGNOSE=1

   # Windows (cmd)
   set D_LOG_LEVEL=TRACE
   set D_LOG_DIAGNOSE=1

   # Windows (PowerShell)
   $env:D_LOG_LEVEL = 'TRACE'
   $env:D_LOG_DIAGNOSE = '1'
   ```
3. **Reproduce the bug** — full TRACE output plus local variables (with sensitive data masked).
4. **Analyze the logs** — find the root cause.
5. **Remove the env vars** — service returns to normal INFO logging immediately.

**No code change. No redeploy. No pull request. No CI/CD pipeline wait.**

---

## Complete Runnable Example

Save this as `debug_demo.py`:

```python
"""Demonstrates diagnostic mode with sensitive masking and custom levels."""

import os
from dsafelogger import ConfigureLogger, GetLogger, RegisterLevel

# Register TRACE level before ConfigureLogger
RegisterLevel('TRACE', 5, 'TRC', '\033[90m')

ConfigureLogger(
    log_path='./logs', pg_name='DebugDemo',
    default_level='INFO',
    sens_kws=['credit_card', 'ssn'],   # add custom keywords
)

logger = GetLogger('demo')


def authenticate_user(username: str, password: str, session_id: str):
    """Simulate authentication — password and session_id will be masked."""
    logger.trace(f'authenticate_user called for {username}')
    if username != 'alice':
        raise PermissionError(f'Unknown user: {username}')
    logger.info(f'User {username} authenticated')
    return True


def process_order(user: str, api_key: str, credit_card: str, amount: float):
    """Simulate order processing — api_key and credit_card will be masked."""
    logger.trace(f'process_order called: user={user}, amount={amount}')
    if amount > 10000:
        raise ValueError(f'Order amount {amount} exceeds daily limit')
    logger.info(f'Order processed for {user}: ${amount:.2f}')


def main():
    diagnose = os.environ.get('D_LOG_DIAGNOSE', '0')
    level = os.environ.get('D_LOG_LEVEL', 'INFO')
    print(f'Running with D_LOG_DIAGNOSE={diagnose}, D_LOG_LEVEL={level}')
    print()

    # Successful authentication
    try:
        authenticate_user('alice', 's3cret!pass', 'sess_abc123xyz')
    except Exception:
        logger.exception('Authentication failed')

    # Failed order — will trigger diagnostic output
    try:
        process_order('alice', 'sk_live_key789', '4111-1111-1111-1111', 15000.0)
    except Exception:
        logger.exception('Order processing failed')

    # Successful order
    try:
        process_order('alice', 'sk_live_key789', '4111-1111-1111-1111', 99.99)
    except Exception:
        logger.exception('Order processing failed')

    logger.info('Demo complete')


if __name__ == '__main__':
    main()
```

---

## How to Run

**Normal mode** — only INFO and above, no diagnostics:

```bash
python debug_demo.py
```

**Full diagnostic mode** — TRACE output + local variable expansion with masking:

```bash
# Linux / macOS
D_LOG_DIAGNOSE=1 D_LOG_LEVEL=TRACE python debug_demo.py

# Windows (cmd)
set D_LOG_DIAGNOSE=1 && set D_LOG_LEVEL=TRACE && python debug_demo.py

# Windows (PowerShell)
$env:D_LOG_DIAGNOSE='1'; $env:D_LOG_LEVEL='TRACE'; python debug_demo.py
```

Compare the two outputs. In diagnostic mode you'll see:

- TRACE messages that were previously hidden
- Local variables in the stack trace for the failed `process_order` call
- `api_key`, `password`, `session_id`, and `credit_card` all replaced with `*** MASKED ***`

This is the power of D-SafeLogger's approach: maximum visibility when you need it, zero risk of
credential leaks, and no code changes required.
