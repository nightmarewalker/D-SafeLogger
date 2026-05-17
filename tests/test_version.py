from __future__ import annotations

from importlib import metadata

import dsafelogger


def test_package_metadata_version_matches_public_version() -> None:
    assert dsafelogger.__version__ == metadata.version('D-SafeLogger')
