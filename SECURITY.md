# Security Policy

## Supported Versions

Security reports are accepted for the current public release line of D-SafeLogger. The project may ask reporters to verify issues against the latest released version or the current `main` branch before triage is finalized.

## Reporting a Vulnerability

If you believe you have found a security issue, please do not open a public issue containing exploit details, sensitive log content, credentials, tokens, or private operational data.

Report the issue privately through the repository maintainer contact channel or GitHub's private vulnerability reporting feature if it is enabled for the repository. Include:

- affected version or commit,
- Python version and operating system,
- minimal reproduction steps,
- expected and observed behavior,
- whether sensitive log data, credentials, or filesystem paths are involved.

## Sensitive Logs

D-SafeLogger is a logging library. Security reports often involve log content, diagnostic output, paths, environment variables, or application context values. Redact secrets before sharing reproductions. Do not attach production logs unless they have been reviewed and sanitized.

## Scope

In scope:

- runtime behavior of the `dsafelogger` package,
- `dsafelogger.mp` multiprocess behavior,
- diagnostic masking behavior,
- packaging or distribution issues that could affect users,
- documentation or examples that would lead users to unsafe configurations.

Out of scope:

- vulnerabilities in external log collectors, metrics systems, tracing backends, or deployment platforms,
- application-specific misuse outside D-SafeLogger's documented contract,
- claims that require D-SafeLogger to provide access control, encryption, network transport, or durable storage guarantees beyond its stated non-goals.

## Expected Response

The maintainer will review reports on a best-effort basis, may ask for additional reproduction details, and will coordinate public disclosure after a fix or documentation update is available when appropriate.
