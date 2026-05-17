"""Path validation utilities for D-SafeLogger (Fail-Fast)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path


class PathValidator:
    """Validates filesystem paths for writability at startup time."""

    @staticmethod
    def validate_writable(directory: Path) -> None:
        """Validate that a directory is writable by creating a test file.

        If the directory does not exist, it is created automatically.

        Args:
            directory: Path to validate.

        Raises:
            PermissionError: If the directory is not writable.
            OSError: If the directory cannot be created or is otherwise unusable.
        """
        directory = Path(directory)

        # Create directory if it does not exist
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise PermissionError(
                f"Cannot create log directory '{directory}': permission denied"
            ) from None
        except OSError as e:
            raise OSError(
                f"Cannot create log directory '{directory}': {e}"
            ) from None

        # Write test file
        test_file = directory / f'.dsafelogger_test_{uuid.uuid4().hex[:8]}'
        try:
            test_file.write_text('test', encoding='utf-8')
        except PermissionError:
            raise PermissionError(
                f"Log directory '{directory}' is not writable"
            ) from None
        except OSError as e:
            raise OSError(
                f"Cannot write to log directory '{directory}': {e}"
            ) from None
        finally:
            try:
                test_file.unlink(missing_ok=True)
            except Exception:
                pass
