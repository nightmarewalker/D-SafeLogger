from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SINGLE_BACKEND_ORDER = [
    ("D-SafeLogger", "sync"),
    ("D-SafeLogger", "async"),
    ("stdlib logging", "sync"),
    ("stdlib logging", "async"),
    ("loguru", "sync"),
    ("loguru", "async"),
    ("structlog", "sync"),
    ("structlog", "async"),
]
MULTIPROCESS_PATTERN_ORDER = ["root_p1", "root_p4", "root_p8", "module_p4"]
MULTIPROCESS_BACKEND_ORDER = ["D-SafeLogger", "stdlib logging", "loguru"]
SUMMARY_OUTPUTS = {
    "single_process": ("single_process.md", None),
    "multiprocess_integrity": ("multiprocess_integrity.md", "integrity_profile"),
    "multiprocess_performance": ("multiprocess_performance.md", "performance_profile"),
    "multiprocess_overload": ("multiprocess_overload.md", "overload_profile"),
    "multiprocess_resilience": ("multiprocess_resilience.md", "resilience_profile"),
}

def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _rel(repo_root: Path, path: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _link_from(doc_path: Path, repo_root: Path, target_path: Path) -> str:
    label = _rel(repo_root, target_path)
    href = os.path.relpath(target_path, start=doc_path.parent).replace(os.sep, "/")
    return f"[`{label}`]({href})"


def _latest_json(results_root: Path, predicate: Any) -> tuple[Path, dict[str, Any]] | None:
    latest: tuple[float, Path, dict[str, Any]] | None = None
    for path in results_root.rglob("summary.json"):
        data = _load_json(path)
        if data is None or not predicate(path, data):
            continue
        stamp = path.stat().st_mtime
        if latest is None or stamp > latest[0]:
            latest = (stamp, path, data)
    if latest is None:
        return None
    return latest[1], latest[2]


def _discover_single(results_root: Path) -> tuple[Path, dict[str, Any]] | None:
    return _latest_json(
        results_root,
        lambda _path, data: isinstance(data.get("environments"), list)
        and isinstance(data.get("summary_rows"), list)
        and any("workload" in row and "mode" in row for row in data.get("summary_rows", [])),
    )


def _discover_compare_by_profile(results_root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    found: dict[str, tuple[float, Path, dict[str, Any]]] = {}
    for path in results_root.rglob("summary.json"):
        data = _load_json(path)
        if data is None:
            continue
        config = data.get("configuration") or {}
        profile = config.get("profile")
        rows = data.get("summary_rows")
        if not profile or not isinstance(rows, list):
            continue
        if not any("pattern" in row and "backend" in row for row in rows):
            continue
        stamp = path.stat().st_mtime
        current = found.get(profile)
        if current is None or stamp > current[0]:
            found[profile] = (stamp, path, data)
    return {profile: (item[1], item[2]) for profile, item in found.items()}


def _session_links(doc_path: Path, repo_root: Path, summary_json_path: Path) -> str:
    parts = []
    summary_md_path = summary_json_path.with_name("summary.md")
    if summary_md_path.exists():
        parts.append(_link_from(doc_path, repo_root, summary_md_path))
    parts.append(_link_from(doc_path, repo_root, summary_json_path))
    return ", ".join(parts)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _throughput_text(row: dict[str, Any]) -> str:
    avg = row.get("throughput_avg")
    min_v = row.get("throughput_min")
    max_v = row.get("throughput_max")
    if avg is None or min_v is None or max_v is None:
        return "—"
    return f"{avg:,} ({min_v:,}-{max_v:,})"


def _metric_text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:.1f}"


def _winner_counts(rows: list[dict[str, Any]]) -> tuple[dict[str, int], int]:
    winners: dict[str, int] = {}
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "ok" or row.get("throughput_avg") is None:
            continue
        key = (row["python_label"], row["gil_label"], row["workload"], row["scenario"])
        best = groups.get(key)
        if best is None or row["throughput_avg"] > best["throughput_avg"]:
            groups[key] = row
    for row in groups.values():
        label = f"{row['backend']} {row['mode']}"
        winners[label] = winners.get(label, 0) + 1
    return winners, len(groups)


def _ds_async_vs_sync(rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = {}
    for row in rows:
        if row.get("backend") != "D-SafeLogger":
            continue
        key = (row["python_label"], row["gil_label"], row["workload"], row["scenario"])
        grouped.setdefault(key, {})[row["mode"]] = row
    throughput_wins = 0
    p50_wins = 0
    comparable = 0
    for modes in grouped.values():
        sync_row = modes.get("sync")
        async_row = modes.get("async")
        if not sync_row or not async_row:
            continue
        if sync_row.get("throughput_avg") is None or async_row.get("throughput_avg") is None:
            continue
        comparable += 1
        if async_row["throughput_avg"] > sync_row["throughput_avg"]:
            throughput_wins += 1
        sync_p50 = sync_row.get("p50_us")
        async_p50 = async_row.get("p50_us")
        if sync_p50 is not None and async_p50 is not None and async_p50 < sync_p50:
            p50_wins += 1
    return throughput_wins, p50_wins, comparable


def _render_single_section(
    repo_root: Path,
    summary_path: Path,
    summary: dict[str, Any],
    doc_path: Path,
) -> list[str]:
    config = summary.get("configuration", {})
    rows = summary.get("summary_rows", [])
    winner_counts, total_cells = _winner_counts(rows)
    throughput_wins, p50_wins, comparable = _ds_async_vs_sync(rows)
    winner_lines = ", ".join(
        f"{label} {count}/{total_cells}"
        for label, count in sorted(winner_counts.items(), key=lambda item: (-item[1], item[0]))[:4]
    ) or "no complete cells"
    lines = [
        "## Single-Process Comparison Analysis",
        "",
        f"- Latest session: `{summary.get('session', summary_path.parent.name)}`",
        f"- Artifacts: {_session_links(doc_path, repo_root, summary_path)}",
        f"- Scope: messages={config.get('messages', '?')}, repeat={config.get('repeat', '?')}, threads={config.get('threads', '?')}",
        f"- D-SafeLogger async beat D-SafeLogger sync on throughput in {throughput_wins}/{comparable} comparable cells.",
        f"- D-SafeLogger async beat D-SafeLogger sync on p50 latency in {p50_wins}/{comparable} comparable cells.",
        f"- Throughput leaders across the latest 3.13/3.14 x GIL x workload x scenario cells: {winner_lines}.",
        "",
    ]

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        key = (row["python_label"], row["gil_label"], row["workload"], row["scenario"])
        grouped.setdefault(key, []).append(row)

    lines += [
        "### Cell Winners",
        "",
        "| Python | GIL | Workload | Scenario | Top Throughput | Lowest p50 |",
        "|--------|-----|----------|----------|----------------|------------|",
    ]
    for key in sorted(grouped):
        python_label, gil_label, workload, scenario = key
        cell_rows = grouped[key]
        fastest = max(
            (row for row in cell_rows if row.get("throughput_avg") is not None),
            key=lambda row: row["throughput_avg"],
            default=None,
        )
        lowest_p50 = min(
            (row for row in cell_rows if row.get("p50_us") is not None),
            key=lambda row: row["p50_us"],
            default=None,
        )
        fastest_text = "—"
        if fastest is not None:
            fastest_text = f"{fastest['backend']} {fastest['mode']} ({fastest['throughput_avg']:,} msg/s)"
        p50_text = "—"
        if lowest_p50 is not None:
            p50_text = f"{lowest_p50['backend']} {lowest_p50['mode']} ({lowest_p50['p50_us']:.1f}µs)"
        workload_label = "single" if workload == "single" else "multi"
        lines.append(
            f"| {python_label} | {gil_label} | {workload_label} | {scenario} | {fastest_text} | {p50_text} |"
        )
    lines.append("")

    ds_best_throughput_wins = 0
    ds_best_p50_wins = 0
    ds_cells = 0
    for cell_rows in grouped.values():
        ds_rows = [row for row in cell_rows if row.get("backend") == "D-SafeLogger"]
        other_rows = [row for row in cell_rows if row.get("backend") != "D-SafeLogger"]
        if not ds_rows or not other_rows:
            continue
        ds_best_tp = max((row["throughput_avg"] for row in ds_rows if row.get("throughput_avg") is not None), default=None)
        other_best_tp = max((row["throughput_avg"] for row in other_rows if row.get("throughput_avg") is not None), default=None)
        ds_best_p50 = min((row["p50_us"] for row in ds_rows if row.get("p50_us") is not None), default=None)
        other_best_p50 = min((row["p50_us"] for row in other_rows if row.get("p50_us") is not None), default=None)
        if ds_best_tp is None or other_best_tp is None or ds_best_p50 is None or other_best_p50 is None:
            continue
        ds_cells += 1
        if ds_best_tp > other_best_tp:
            ds_best_throughput_wins += 1
        if ds_best_p50 < other_best_p50:
            ds_best_p50_wins += 1

    lines += [
        "### D-SafeLogger Position",
        "",
        f"- Best D-SafeLogger mode beat all non-D-SafeLogger backends on throughput in {ds_best_throughput_wins}/{ds_cells} cells.",
        f"- Best D-SafeLogger mode achieved the lowest p50 in {ds_best_p50_wins}/{ds_cells} cells.",
        "",
    ]

    lookup = {
        (
            row["python_label"],
            row["gil_label"],
            row["workload"],
            row["scenario"],
            row["backend"],
            row["mode"],
        ): row
        for row in rows
    }
    for python_label in ["3.13", "3.14"]:
        lines.append(f"### Python {python_label}")
        lines.append("")
        for gil_label in ["enabled", "disabled"]:
            lines.append(f"#### GIL {gil_label}")
            lines.append("")
            for workload in ["single", "multi"]:
                workload_label = "single-thread" if workload == "single" else "multi-thread"
                lines.append(f"##### {workload_label}")
                lines.append("")
                for scenario in ["text", "json"]:
                    lines.append(f"###### {scenario}")
                    lines.append("")
                    lines.append("| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |")
                    lines.append("|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|")
                    for backend, mode in SINGLE_BACKEND_ORDER:
                        row = lookup.get((python_label, gil_label, workload, scenario, backend, mode))
                        if row is None:
                            lines.append(f"| {backend} | {mode} | missing | 0/0 | — | — | — | — | no data |")
                            continue
                        runs_text = f"{row['successful_runs']}/{row['total_runs']}"
                        note = (row.get("note") or "").replace("\n", " ")
                        lines.append(
                            f"| {backend} | {mode} | {row['status']} | {runs_text} | {_throughput_text(row)} | "
                            f"{_metric_text(row.get('p50_us'))} | {_metric_text(row.get('p90_us'))} | {_metric_text(row.get('p99_us'))} | {note} |"
                        )
                    lines.append("")
    return lines


def _render_multiprocess_profile_tables(summary: dict[str, Any]) -> list[str]:
    rows = summary.get("summary_rows", [])
    if not rows:
        return ["- No rows found.", ""]

    lookup = {
        (
            row["python_label"],
            row["gil_label"],
            row["scenario"],
            row["pattern"],
            row["backend"],
            bool(row.get("is_async", False)),
        ): row
        for row in rows
    }
    async_modes = sorted({bool(row.get("is_async", False)) for row in rows})
    lines: list[str] = []
    for python_label in ["3.13", "3.14"]:
        lines.append(f"#### Python {python_label}")
        lines.append("")
        for gil_label in ["enabled", "disabled"]:
            lines.append(f"##### GIL {gil_label}")
            lines.append("")
            for scenario in ["text", "json"]:
                lines.append(f"###### {scenario}")
                lines.append("")
                lines.append("| Pattern | Backend | Mode | Procs | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Delivered | IntegrityFail | Notes |")
                lines.append("|---------|---------|------|------:|--------|------|---------------------------|---------:|---------:|---------:|----------:|--------------:|-------|")
                emitted = False
                for pattern in MULTIPROCESS_PATTERN_ORDER:
                    for backend in MULTIPROCESS_BACKEND_ORDER:
                        for is_async in async_modes:
                            row = lookup.get((python_label, gil_label, scenario, pattern, backend, is_async))
                            if row is None:
                                continue
                            emitted = True
                            runs_text = f"{row['successful_runs']}/{row['total_runs']}"
                            note = (row.get("note") or "").replace("\n", " ")
                            mode_text = "async" if is_async else "sync"
                            lines.append(
                                f"| {row['pattern']} | {row['backend']} | {mode_text} | {row['process_count']} | {row['status']} | {runs_text} | "
                                f"{_throughput_text(row)} | {_metric_text(row.get('p50_us'))} | {_metric_text(row.get('p90_us'))} | "
                                f"{_metric_text(row.get('p99_us'))} | {_metric_text(row.get('delivered_lines'))} | {row.get('integrity_failures', 0)} | {note} |"
                            )
                if not emitted:
                    lines.append("| no data | — | — | — | — | — | — | — | — | — | — | — | — |")
                lines.append("")
    return lines


def _render_resilience_profile_tables(summary: dict[str, Any]) -> list[str]:
    rows = summary.get("summary_rows", [])
    raw_runs = summary.get("raw_runs", [])
    scenarios = sorted({row.get("resilience_scenario") for row in rows if row.get("resilience_scenario")})
    lines: list[str] = []
    for python_label in ["3.13", "3.14"]:
        lines.append(f"#### Python {python_label}")
        lines.append("")
        for gil_label in ["enabled", "disabled"]:
            lines.append(f"##### GIL {gil_label}")
            lines.append("")
            lines.append(
                "| Scenario | Backend | Status | Runs | Attempted | Accepted | Delivered | "
                "KnownRejected | KnownDropped | UnexplainedLost | Shutdown | Observability | Notes |"
            )
            lines.append(
                "|----------|---------|--------|------|----------:|---------:|----------:|"
                "--------------:|-------------:|----------------:|----------|---------------|-------|"
            )
            for scenario in scenarios:
                for backend in MULTIPROCESS_BACKEND_ORDER:
                    row = next(
                        (
                            item for item in rows
                            if item.get("python_label") == python_label
                            and item.get("gil_label") == gil_label
                            and item.get("backend") == backend
                            and item.get("resilience_scenario") == scenario
                        ),
                        None,
                    )
                    if row is None:
                        lines.append(f"| {scenario} | {backend} | missing | 0/0 | — | — | — | — | — | — | — | — | no data |")
                        continue
                    matching_raw = [
                        raw for raw in raw_runs
                        if raw.get("python_label") == python_label
                        and raw.get("gil_label") == gil_label
                        and raw.get("backend") == backend
                        and (raw.get("resilience") or {}).get("scenario") == scenario
                    ]
                    observability = "—"
                    if matching_raw:
                        fields = (matching_raw[0].get("resilience") or {}).get("observability_fields_available") or []
                        observability = ", ".join(fields)
                    note = (row.get("note") or "").replace("\n", " ")
                    def _cell(value: Any) -> str:
                        return "—" if value is None else str(value)
                    lines.append(
                        f"| {scenario} | {backend} | {row['status']} | {row['successful_runs']}/{row['total_runs']} | "
                        f"{_cell(row.get('attempted_count'))} | {_cell(row.get('accepted_count'))} | {_cell(row.get('delivered_lines'))} | "
                        f"{_cell(row.get('known_rejected_count'))} | {_cell(row.get('known_dropped_count'))} | "
                        f"{_cell(row.get('unexplained_lost_count'))} | {_cell(row.get('shutdown_result'))} | {observability} | {note} |"
                    )
            lines.append("")
    return lines


def _render_compare_section(
    repo_root: Path,
    profile: str,
    summary_path: Path,
    summary: dict[str, Any],
    doc_path: Path,
) -> list[str]:
    rows = summary.get("summary_rows", [])
    raw_runs = summary.get("raw_runs", [])
    lines = [
        f"### {profile}",
        "",
        f"- Latest session: `{summary.get('session', summary_path.parent.name)}`",
        f"- Artifacts: {_session_links(doc_path, repo_root, summary_path)}",
    ]
    if profile == "integrity_profile":
        bad_rows = sum(1 for row in rows if row.get("integrity_failures", 0) or row.get("status") not in {"ok"})
        bad_raw = sum(1 for row in raw_runs if row.get("status") not in {"ok"})
        missing_total = sum(((row.get("integrity") or {}).get("missing_count") or 0) for row in raw_runs)
        dup_total = sum(((row.get("integrity") or {}).get("duplicate_count") or 0) for row in raw_runs)
        lines += [
            f"- Integrity summary rows: {len(rows)}. Bad rows: {bad_rows}.",
            f"- Raw runs: {len(raw_runs)}. Non-ok runs: {bad_raw}.",
            f"- Aggregate delivery anomalies: missing={missing_total}, duplicates={dup_total}.",
        ]
        backend_stats: dict[str, dict[str, int]] = {}
        for row in raw_runs:
            backend = row.get("backend", "?")
            stats = backend_stats.setdefault(
                backend,
                {"runs": 0, "missing": 0, "duplicates": 0, "json": 0, "route": 0, "failures": 0},
            )
            stats["runs"] += 1
            integ = row.get("integrity") or {}
            stats["missing"] += int(integ.get("missing_count") or 0)
            stats["duplicates"] += int(integ.get("duplicate_count") or 0)
            stats["json"] += int(integ.get("json_parse_failure_count") or 0)
            stats["route"] += int(integ.get("route_mismatch_count") or 0)
            if row.get("status") != "ok":
                stats["failures"] += 1
        lines += [
            "",
            "| Backend | Raw Runs | Failures | Missing | Duplicates | JSON Parse | Route Mismatch |",
            "|---------|---------:|---------:|--------:|-----------:|-----------:|---------------:|",
        ]
        for backend in sorted(backend_stats):
            stats = backend_stats[backend]
            lines.append(
                f"| {backend} | {stats['runs']} | {stats['failures']} | {stats['missing']} | {stats['duplicates']} | {stats['json']} | {stats['route']} |"
            )
    elif profile == "performance_profile":
        ok_rows = [row for row in rows if row.get("status") == "ok" and row.get("throughput_avg") is not None]
        fastest = sorted(ok_rows, key=lambda row: row["throughput_avg"], reverse=True)[:3]
        if fastest:
            lines.append(
                "- Highest-throughput rows: " + "; ".join(
                    f"{row['backend']} {('async' if row.get('is_async') else 'sync')} {row['pattern']} {row['scenario']} {row['python_label']}/{row['gil_label']}={row['throughput_avg']:,} msg/s"
                    for row in fastest
                )
                + "."
            )
        else:
            lines.append("- No successful performance rows found.")
        overall_wins: dict[str, int] = {}
        grouped_cells: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in ok_rows:
            key = (row["python_label"], row["gil_label"], row["pattern"], row["scenario"])
            grouped_cells.setdefault(key, []).append(row)
        for cell_rows in grouped_cells.values():
            winner = max(cell_rows, key=lambda row: row["throughput_avg"])
            overall_wins[winner["backend"]] = overall_wins.get(winner["backend"], 0) + 1
        if overall_wins:
            lines.append(
                "- Throughput winner counts across Python/GIL/pattern/scenario cells: "
                + ", ".join(f"{backend} {count}" for backend, count in sorted(overall_wins.items(), key=lambda item: (-item[1], item[0])))
                + "."
            )

        pattern_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in ok_rows:
            pattern_groups.setdefault((row["pattern"], row["scenario"]), []).append(row)
        lines += [
            "",
            "| Pattern | Scenario | D-SafeLogger avg | stdlib avg | loguru avg | Throughput Wins (DS/std/loguru) |",
            "|---------|----------|-----------------:|-----------:|-----------:|----------------------------------|",
        ]
        for pattern, scenario in sorted(pattern_groups):
            bucket = pattern_groups[(pattern, scenario)]
            means: dict[str, float | None] = {}
            wins = {"D-SafeLogger": 0, "stdlib logging": 0, "loguru": 0}
            env_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for row in bucket:
                env_groups.setdefault((row["python_label"], row["gil_label"]), []).append(row)
            for env_rows in env_groups.values():
                winner = max(env_rows, key=lambda row: row["throughput_avg"])
                wins[winner["backend"]] += 1
            for backend in ["D-SafeLogger", "stdlib logging", "loguru"]:
                values = [float(row["throughput_avg"]) for row in bucket if row.get("backend") == backend and row.get("throughput_avg") is not None]
                means[backend] = _mean(values)
            def _fmt_mean(value: float | None) -> str:
                return "—" if value is None else f"{value:,.0f}"
            win_text = f"{wins['D-SafeLogger']}/{wins['stdlib logging']}/{wins['loguru']}"
            lines.append(
                f"| {pattern} | {scenario} | {_fmt_mean(means['D-SafeLogger'])} | {_fmt_mean(means['stdlib logging'])} | {_fmt_mean(means['loguru'])} | {win_text} |"
            )
    elif profile == "overload_profile":
        shed_runs = [
            row for row in raw_runs
            if row.get("backend") == "D-SafeLogger"
            and isinstance(row.get("note"), str)
            and "overload_shed" in row["note"]
        ]
        lines.append(f"- D-SafeLogger overload_shed runs observed: {len(shed_runs)} / {len(raw_runs)} raw runs.")
    elif profile == "resilience_profile":
        ds_rows = [row for row in rows if row.get("backend") == "D-SafeLogger"]
        known_rows = [row for row in ds_rows if row.get("unexplained_lost_count") is not None]
        cleanly_explained = sum(1 for row in known_rows if row.get("unexplained_lost_count") == 0)
        lines.append(
            f"- D-SafeLogger produced classified loss/reject/drop fields for {len(known_rows)}/{len(ds_rows)} summary rows."
        )
        lines.append(f"- Fully explained D-SafeLogger rows: {cleanly_explained}/{len(known_rows)}.")
    else:
        lines.append(f"- Summary rows: {len(rows)}. Raw runs: {len(raw_runs)}.")
    lines.append("")
    if profile == "resilience_profile":
        lines += _render_resilience_profile_tables(summary)
    else:
        lines += _render_multiprocess_profile_tables(summary)
    return lines


def _summary_dir(repo_root: Path) -> Path:
    return repo_root / "benchmarks" / "summary"


def _manifest_path(repo_root: Path) -> Path:
    return _summary_dir(repo_root) / "manifest.json"


def load_summary_manifest(repo_root: Path) -> dict[str, Any]:
    path = _manifest_path(repo_root)
    data = _load_json(path)
    if data is None:
        raise FileNotFoundError(f"benchmark summary manifest not found or invalid: {path}")
    selected = data.get("selected")
    if not isinstance(selected, dict):
        raise ValueError("benchmark summary manifest must contain a 'selected' object")
    return data


def _selected_summary_path(repo_root: Path, session: str) -> Path:
    path = repo_root / "benchmarks" / "results" / session / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"selected benchmark summary does not exist: {path}")
    return path


def _summary_heading(key: str, profile: str | None) -> str:
    if key == "single_process":
        return "# Single-Process Benchmark Summary"
    label = profile or key
    return "# Multiprocess " + label.replace("_", " ").title() + " Summary"


def _render_selected_summary(repo_root: Path, key: str, session: str, doc_path: Path) -> str:
    output_name, profile = SUMMARY_OUTPUTS[key]
    summary_path = _selected_summary_path(repo_root, session)
    summary = _load_json(summary_path)
    if summary is None:
        raise ValueError(f"selected benchmark summary is invalid JSON: {summary_path}")
    if profile is None:
        lines = _render_single_section(repo_root, summary_path, summary, doc_path)
    else:
        actual_profile = (summary.get("configuration") or {}).get("profile")
        if actual_profile != profile:
            raise ValueError(
                f"manifest key {key!r} expects {profile!r}, got {actual_profile!r} from {summary_path}"
            )
        lines = _render_compare_section(repo_root, profile, summary_path, summary, doc_path)
    if lines:
        lines[0] = _summary_heading(key, profile)
    lines += [
        "## Source",
        "",
        f"- Manifest key: `{key}`",
        f"- Selected session: `{session}`",
        f"- Session artifacts: {_session_links(doc_path, repo_root, summary_path)}",
        "",
    ]
    return "\n".join(lines)


def render_benchmark_summaries(repo_root: Path) -> dict[Path, str]:
    manifest = load_summary_manifest(repo_root)
    selected = manifest["selected"]
    summary_dir = _summary_dir(repo_root)
    rendered: dict[Path, str] = {}
    index_rows: list[tuple[str, str, str, Path]] = []
    for key, session in selected.items():
        if key not in SUMMARY_OUTPUTS:
            continue
        if not isinstance(session, str) or not session:
            raise ValueError(f"manifest selected.{key} must be a non-empty session name")
        output_name, profile = SUMMARY_OUTPUTS[key]
        output_path = summary_dir / output_name
        rendered[output_path] = _render_selected_summary(repo_root, key, session, output_path)
        index_rows.append((key, session, profile or "single_process", output_path))

    index_lines = [
        "# Benchmark Summary Index",
        "",
        "This directory is generated from `benchmarks/summary/manifest.json`.",
        "`BENCHMARK.md` is a manually edited public analysis document and is not generated by benchmark runners.",
        "",
        "- Results root: `benchmarks/results`",
        "",
        "| Manifest Key | Selected Session | Profile | Summary |",
        "|--------------|------------------|---------|---------|",
    ]
    for key, session, profile, output_path in index_rows:
        index_lines.append(
            f"| `{key}` | `{session}` | `{profile}` | {_link_from(summary_dir / 'index.md', repo_root, output_path)} |"
        )
    index_lines.append("")
    rendered[summary_dir / "index.md"] = "\n".join(index_lines)
    return rendered


def write_benchmark_summaries(repo_root: Path, *, check: bool = False) -> list[Path]:
    rendered = render_benchmark_summaries(repo_root)
    changed: list[Path] = []
    for path, content in rendered.items():
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != content:
            changed.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
    if check and changed:
        rels = ", ".join(_rel(repo_root, path) for path in changed)
        raise RuntimeError(f"benchmark summaries are out of date: {rels}")
    return sorted(rendered)


def render_single_session_markdown(
    summary: dict[str, Any],
    raw_rel_paths: dict[str, str],
) -> str:
    lines: list[str] = []
    config = summary["configuration"]
    summary_rows = summary["summary_rows"]
    lookup = {
        (
            row["python_label"],
            row["gil_label"],
            row["workload"],
            row["scenario"],
            row["backend"],
            row["mode"],
        ): row
        for row in summary_rows
    }
    lines.append("# Benchmark Session")
    lines.append("")
    lines.append(f"Session: `{summary['session']}`")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(f"- Generated: {summary['generated_at_utc']}")
    lines.append("- Python versions: 3.13 and 3.14")
    lines.append("- Interpreter builds: free-threaded executables with `PYTHON_GIL=1/0`")
    lines.append("- GIL states: enabled and disabled")
    lines.append("- Workloads: single-thread and multi-thread")
    lines.append("- Scenarios: text and JSON")
    lines.append("- Backends: D-SafeLogger, stdlib logging, loguru, structlog")
    lines.append("- Modes: sync and async")
    lines.append(f"- Messages per run: {config['messages']:,}")
    lines.append(f"- Measured runs per combination: {config['repeat']}")
    lines.append(f"- Multi-thread worker count: {config['threads']}")
    lines.append(f"- Scratch output root: `{config['scratch_root']}`")
    lines.append("")
    lines.append("## Recording Rules")
    lines.append("")
    lines.append("- Throughput: multi-run average with min-max range")
    lines.append("- `p50` / `p90` / `p99`: median of per-run percentile values")
    lines.append("- Async / queue throughput is producer-side call-return throughput")
    lines.append("")
    lines.append("## Runtime Matrix")
    lines.append("")
    lines.append("| Python | GIL | Version | Runtime GIL | Build FT | Target Python | Raw Results |")
    lines.append("|--------|-----|---------|-------------|----------|---------------|-------------|")
    for env in sorted(summary["environments"], key=lambda item: (item["python_label"], item["gil_label"])):
        key = f"py{env['python_label'].replace('.', '')}_gil_{env['gil_label']}"
        raw_link = raw_rel_paths.get(key, "")
        runtime_gil = env["runtime_gil_enabled"]
        runtime_gil_text = "enabled" if runtime_gil is True else "disabled" if runtime_gil is False else "unknown"
        build_ft_text = "yes" if env["build_free_threaded"] else "no"
        raw_cell = f"[`{key}.json`]({raw_link})" if raw_link else "—"
        lines.append(
            f"| {env['python_label']} | {env['gil_label']} | {env['python_version']} | "
            f"{runtime_gil_text} | {build_ft_text} | `{env['target_python']}` | {raw_cell} |"
        )
    lines.append("")

    for python_label in ["3.13", "3.14"]:
        lines.append(f"## Python {python_label}")
        lines.append("")
        for gil_label in ["enabled", "disabled"]:
            lines.append(f"### GIL {gil_label}")
            lines.append("")
            for workload in ["single", "multi"]:
                workload_label = "single-thread" if workload == "single" else "multi-thread"
                lines.append(f"#### {workload_label}")
                lines.append("")
                for scenario in ["text", "json"]:
                    lines.append(f"##### {scenario}")
                    lines.append("")
                    lines.append("| Backend | Mode | Status | Runs | Throughput avg (min-max) | p50 (us) | p90 (us) | p99 (us) | Notes |")
                    lines.append("|---------|------|--------|------|---------------------------|---------:|---------:|---------:|-------|")
                    for backend, mode in SINGLE_BACKEND_ORDER:
                        row = lookup.get((python_label, gil_label, workload, scenario, backend, mode))
                        if row is None:
                            lines.append(f"| {backend} | {mode} | missing | 0/0 | — | — | — | — | no data |")
                            continue
                        runs_text = f"{row['successful_runs']}/{row['total_runs']}"
                        note = (row.get("note") or "").replace("\n", " ")
                        lines.append(
                            f"| {backend} | {mode} | {row['status']} | {runs_text} | "
                            f"{_throughput_text(row)} | {_metric_text(row.get('p50_us'))} | {_metric_text(row.get('p90_us'))} | "
                            f"{_metric_text(row.get('p99_us'))} | {note} |"
                        )
                    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append(
        f"- Combined summary JSON: [`benchmarks/results/{summary['session']}/summary.json`](benchmarks/results/{summary['session']}/summary.json)"
    )
    for _key, rel_path in sorted(raw_rel_paths.items()):
        lines.append(f"- Raw environment JSON: [`{rel_path}`]({rel_path})")
    lines.append("")
    return "\n".join(lines)
