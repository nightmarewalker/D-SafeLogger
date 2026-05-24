"""Generate GitHub Pages landing site for D-SafeLogger.

CLI:
  --output DIR     generate site into DIR
  --check          self-verify to a temp dir (does not touch working tree)
  --check-dir DIR  validate an already-generated site directory
"""
from __future__ import annotations

import argparse
import datetime
import html
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

BASE_URL = "https://nightmarewalker.github.io/D-SafeLogger"
GITHUB_URL = "https://github.com/nightmarewalker/D-SafeLogger"
PYPI_URL = "https://pypi.org/project/d-safelogger/"

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _get_version() -> str:
    try:
        with open(_REPO_ROOT / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        return str(data["project"]["version"])
    except Exception:
        return "unknown"


def _get_lastmod(readme_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", readme_path],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()[:10]
    except Exception:
        pass
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _validate_sources() -> list[str]:
    errors: list[str] = []
    required: list[tuple[str, bool]] = [
        ("README.md", False),
        ("README_ja.md", False),
        ("BENCHMARK.md", False),
        ("pyproject.toml", False),
        ("examples", True),
        ("examples/12_multiprocess_logging.md", False),
    ]
    for rel, is_dir in required:
        path = _REPO_ROOT / rel
        if not path.exists():
            errors.append(f"missing required {'directory' if is_dir else 'file'}: {rel}")

    readme = _REPO_ROOT / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8")
        for kw in ["D-SafeLogger", "ConfigureLogger", "GetLogger"]:
            if kw not in content:
                errors.append(f"README.md missing keyword: {kw}")
        content_lower = content.lower()
        if "stdlib logging-compatible" not in content_lower and "stdlib `logging` compatible" not in content_lower:
            errors.append("README.md missing keyword: stdlib logging-compatible")
        if "append-only routing" not in content_lower:
            errors.append("README.md missing keyword: append-only routing")

    readme_ja = _REPO_ROOT / "README_ja.md"
    if readme_ja.exists():
        content = readme_ja.read_text(encoding="utf-8")
        for kw in ["D-SafeLogger", "ConfigureLogger", "GetLogger"]:
            if kw not in content:
                errors.append(f"README_ja.md missing keyword: {kw}")
        if "stdlib logging 互換" not in content:
            errors.append("README_ja.md missing keyword: stdlib logging 互換")
        if "追記専用ルーティング" not in content:
            errors.append("README_ja.md missing keyword: 追記専用ルーティング")

    return errors


def _en_html(version: str) -> str:
    esc = html.escape
    v = esc(version)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>D-SafeLogger - stdlib-compatible Python logging without active-file rename rotation</title>
  <meta name="description" content="D-SafeLogger is a zero-runtime-dependency, stdlib-compatible Python logging library that uses append-only routing instead of renaming the active log file.">
  <link rel="canonical" href="{BASE_URL}/">
  <link rel="alternate" hreflang="en" href="{BASE_URL}/">
  <link rel="alternate" hreflang="ja" href="{BASE_URL}/ja/">
  <link rel="alternate" hreflang="x-default" href="{BASE_URL}/">
  <meta property="og:title" content="D-SafeLogger">
  <meta property="og:description" content="stdlib-compatible Python logging without active-file rename rotation">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{BASE_URL}/">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "SoftwareSourceCode",
    "name": "D-SafeLogger",
    "description": "Zero-runtime-dependency, stdlib-compatible Python logging library with append-only routing.",
    "codeRepository": "{GITHUB_URL}",
    "programmingLanguage": "Python",
    "license": "https://www.apache.org/licenses/LICENSE-2.0",
    "runtimePlatform": "Python 3.11+",
    "softwareVersion": "{v}",
    "url": "{BASE_URL}/"
  }}
  </script>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }}
    code, pre {{ background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.92em; }}
    pre {{ padding: 0.8em 1em; overflow-x: auto; }}
    h1 {{ font-size: 2rem; margin-bottom: 0.2em; }}
    .version {{ color: #666; font-size: 0.9em; }}
    ul {{ padding-left: 1.5em; }}
    a {{ color: #0066cc; }}
    nav {{ margin-top: 2rem; }}
    nav a {{ margin-right: 1em; }}
  </style>
</head>
<body>
  <h1>D-SafeLogger</h1>
  <p class="version">Source version: {v}</p>
  <p>A zero-runtime-dependency, stdlib-compatible Python logging library that uses <strong>append-only routing</strong> instead of renaming the active log file.</p>

  <h2>Key Properties</h2>
  <ul>
    <li>stdlib logging-compatible &mdash; drop-in for standard <code>logging</code></li>
    <li>Append-only routing &mdash; never renames the active log file</li>
    <li>Zero runtime dependencies</li>
    <li>Multiprocess-safe with an optional MP runtime</li>
    <li>Python 3.11+ (including free-threaded 3.13t / 3.14t)</li>
  </ul>

  <h2>Quick Start</h2>
  <pre><code>pip install d-safelogger</code></pre>
  <pre><code>from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path="./logs", pg_name="MyApp")

logger = GetLogger(__name__)
logger.info("Application started")</code></pre>

  <p>Output file:</p>
  <pre><code>./logs/MyApp.log</code></pre>
  <p>With daily routing:</p>
  <pre><code>./logs/MyApp_20260403.log</code></pre>

  <h2>Links</h2>
  <nav>
    <a href="{GITHUB_URL}">GitHub</a>
    <a href="{PYPI_URL}">PyPI</a>
    <a href="{GITHUB_URL}#readme">README</a>
    <a href="{GITHUB_URL}/blob/main/README_ja.md">&#26085;&#26412;&#35486; README</a>
    <a href="{GITHUB_URL}/tree/main/examples">Examples</a>
    <a href="{GITHUB_URL}/blob/main/BENCHMARK.md">Benchmarks</a>
    <a href="{GITHUB_URL}/blob/main/examples/12_multiprocess_logging.md">Multiprocess Logging</a>
  </nav>

  <p><a href="{BASE_URL}/ja/">&#26085;&#26412;&#35486;</a></p>
</body>
</html>"""


def _ja_html(version: str) -> str:
    esc = html.escape
    v = esc(version)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>D-SafeLogger - active log file を rename しない Python logging ライブラリ</title>
  <meta name="description" content="D-SafeLogger は、stdlib logging 互換の Python logging ライブラリです。active log file を rename せず、append-only routing で次の出力先へ書き込みます。">
  <link rel="canonical" href="{BASE_URL}/ja/">
  <link rel="alternate" hreflang="en" href="{BASE_URL}/">
  <link rel="alternate" hreflang="ja" href="{BASE_URL}/ja/">
  <link rel="alternate" hreflang="x-default" href="{BASE_URL}/">
  <meta property="og:title" content="D-SafeLogger">
  <meta property="og:description" content="active log file を rename しない stdlib logging 互換 Python ロガー">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{BASE_URL}/ja/">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "SoftwareSourceCode",
    "name": "D-SafeLogger",
    "description": "ゼロ依存、stdlib logging 互換の Python logging ライブラリ。追記専用ルーティングで active log file を rename しない。",
    "codeRepository": "{GITHUB_URL}",
    "programmingLanguage": "Python",
    "license": "https://www.apache.org/licenses/LICENSE-2.0",
    "runtimePlatform": "Python 3.11+",
    "softwareVersion": "{v}",
    "url": "{BASE_URL}/ja/"
  }}
  </script>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #222; }}
    code, pre {{ background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.92em; }}
    pre {{ padding: 0.8em 1em; overflow-x: auto; }}
    h1 {{ font-size: 2rem; margin-bottom: 0.2em; }}
    .version {{ color: #666; font-size: 0.9em; }}
    ul {{ padding-left: 1.5em; }}
    a {{ color: #0066cc; }}
    nav {{ margin-top: 2rem; }}
    nav a {{ margin-right: 1em; }}
  </style>
</head>
<body>
  <h1>D-SafeLogger</h1>
  <p class="version">Source version: {v}</p>
  <p>ゼロ依存・stdlib logging 互換の Python logging ライブラリです。<strong>追記専用ルーティング</strong>を使い、active log file を rename しません。</p>

  <h2>主な特徴</h2>
  <ul>
    <li>stdlib logging 互換 &mdash; 標準 <code>logging</code> のドロップイン代替</li>
    <li>追記専用ルーティング &mdash; active log file を rename しない</li>
    <li>ゼロランタイム依存</li>
    <li>オプションの MP ランタイムでマルチプロセス対応</li>
    <li>Python 3.11+ (free-threaded 3.13t / 3.14t 含む)</li>
  </ul>

  <h2>クイックスタート</h2>
  <pre><code>pip install d-safelogger</code></pre>
  <pre><code>from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path="./logs", pg_name="MyApp")

logger = GetLogger(__name__)
logger.info("Application started")</code></pre>

  <p>出力ファイル:</p>
  <pre><code>./logs/MyApp.log</code></pre>
  <p>日次ルーティングの場合:</p>
  <pre><code>./logs/MyApp_20260403.log</code></pre>

  <h2>リンク</h2>
  <nav>
    <a href="{GITHUB_URL}">GitHub</a>
    <a href="{PYPI_URL}">PyPI</a>
    <a href="{GITHUB_URL}#readme">README</a>
    <a href="{GITHUB_URL}/blob/main/README_ja.md">日本語 README</a>
    <a href="{GITHUB_URL}/tree/main/examples">Examples</a>
    <a href="{GITHUB_URL}/blob/main/BENCHMARK.md">ベンチマーク</a>
    <a href="{GITHUB_URL}/blob/main/examples/12_multiprocess_logging.md">マルチプロセスロギング</a>
  </nav>

  <p><a href="{BASE_URL}/">English</a></p>
</body>
</html>"""


def _robots_txt() -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n"


def _sitemap_xml(lastmod_en: str, lastmod_ja: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url>\n    <loc>{BASE_URL}/</loc>\n    <lastmod>{lastmod_en}</lastmod>\n  </url>\n"
        f"  <url>\n    <loc>{BASE_URL}/ja/</loc>\n    <lastmod>{lastmod_ja}</lastmod>\n  </url>\n"
        "</urlset>\n"
    )


def _generate_site(output_dir: Path) -> list[str]:
    errors = _validate_sources()
    if errors:
        return errors

    version = _get_version()
    lastmod_en = _get_lastmod("README.md")
    lastmod_ja = _get_lastmod("README_ja.md")

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ja").mkdir(parents=True, exist_ok=True)

    (output_dir / "index.html").write_text(_en_html(version), encoding="utf-8")
    (output_dir / "ja" / "index.html").write_text(_ja_html(version), encoding="utf-8")
    (output_dir / "robots.txt").write_text(_robots_txt(), encoding="utf-8")
    (output_dir / "sitemap.xml").write_text(_sitemap_xml(lastmod_en, lastmod_ja), encoding="utf-8")

    missing = [p for p in ["index.html", "ja/index.html", "robots.txt", "sitemap.xml"] if not (output_dir / p).exists()]
    return [f"failed to generate: {p}" for p in missing]


def _check_site_dir(site_dir: Path) -> list[str]:
    errors: list[str] = []

    required_files = ["index.html", "ja/index.html", "robots.txt", "sitemap.xml"]
    for rel in required_files:
        if not (site_dir / rel).exists():
            errors.append(f"missing: {rel}")
    if errors:
        return errors

    en_html = (site_dir / "index.html").read_text(encoding="utf-8")
    ja_html = (site_dir / "ja" / "index.html").read_text(encoding="utf-8")
    sitemap = (site_dir / "sitemap.xml").read_text(encoding="utf-8")
    robots = (site_dir / "robots.txt").read_text(encoding="utf-8")

    en_required = [
        ('<html lang="en">', "html lang=en"),
        ("D-SafeLogger", "D-SafeLogger"),
        ("ConfigureLogger", "ConfigureLogger"),
        ("GetLogger", "GetLogger"),
        ("append-only routing", "append-only routing"),
        ("stdlib-compatible", "stdlib-compatible"),
        ("Source version", "Source version"),
        ("softwareVersion", "softwareVersion"),
        (GITHUB_URL, "GitHub URL"),
        (PYPI_URL, "PyPI URL"),
        (f"{GITHUB_URL}/blob/main/BENCHMARK.md", "BENCHMARK URL"),
        (f"{GITHUB_URL}/blob/main/examples/12_multiprocess_logging.md", "MP example URL"),
        ("SoftwareSourceCode", "SoftwareSourceCode"),
        ('hreflang="ja"', 'hreflang="ja"'),
    ]
    for token, label in en_required:
        if token not in en_html:
            errors.append(f"index.html missing {label}")

    ja_required = [
        ('<html lang="ja">', "html lang=ja"),
        ("D-SafeLogger", "D-SafeLogger"),
        ("ConfigureLogger", "ConfigureLogger"),
        ("GetLogger", "GetLogger"),
        ("追記専用", "追記専用"),
        ("stdlib logging 互換", "stdlib logging 互換"),
        ("Source version", "Source version"),
        ("softwareVersion", "softwareVersion"),
        (GITHUB_URL, "GitHub URL"),
        (PYPI_URL, "PyPI URL"),
        ('hreflang="en"', 'hreflang="en"'),
    ]
    for token, label in ja_required:
        if token not in ja_html:
            errors.append(f"ja/index.html missing {label}")

    for url in [f"{BASE_URL}/", f"{BASE_URL}/ja/"]:
        if url not in sitemap:
            errors.append(f"sitemap.xml missing URL: {url}")

    if f"Sitemap: {BASE_URL}/sitemap.xml" not in robots:
        errors.append("robots.txt missing Sitemap directive")

    local_required: list[tuple[str, bool]] = [
        ("README.md", False),
        ("README_ja.md", False),
        ("BENCHMARK.md", False),
        ("examples", True),
        ("examples/12_multiprocess_logging.md", False),
        ("pyproject.toml", False),
    ]
    for rel, is_dir in local_required:
        if not (_REPO_ROOT / rel).exists():
            errors.append(f"repo missing required {'directory' if is_dir else 'file'}: {rel}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", metavar="DIR", help="Generate site into DIR")
    group.add_argument("--check", action="store_true", help="Self-verify to a temp dir (does not touch working tree)")
    group.add_argument("--check-dir", metavar="DIR", help="Validate an already-generated site directory")
    args = parser.parse_args()

    if args.output:
        errors = _generate_site(Path(args.output))
        if errors:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"Generated site: {args.output}")
        return 0

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "site"
            errors = _generate_site(site_dir)
            if not errors:
                errors = _check_site_dir(site_dir)
        if errors:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print("Pages site check passed")
        return 0

    if args.check_dir:
        errors = _check_site_dir(Path(args.check_dir))
        if errors:
            for e in errors:
                print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"Pages site verified: {args.check_dir}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
