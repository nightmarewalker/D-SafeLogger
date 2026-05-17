"""Environment variable parser for D-SafeLogger."""

from __future__ import annotations

import sys


class EnvParser:
    """Parse D-SafeLogger environment variables."""

    @staticmethod
    def parse_global_level(env_value: str) -> str | None:
        """Parse {prefix}_LEVEL value.

        Accepts only a single global level name. Comma-separated module
        specs are rejected with a migration guide.

        Returns:
            Uppercase level string, or None if empty.

        Raises:
            ValueError: If value contains commas (old module-style format).
        """
        if not env_value or not env_value.strip():
            return None

        value = env_value.strip()

        if ',' in value:
            raise ValueError(
                f"{value!r} contains comma-separated module specs. "
                f"Use the _MODULES env var for per-module settings. "
                f"Example: _LEVEL=INFO  _MODULES=ModuleA:DEBUG,ModuleB:ERROR"
            )

        return value.upper()

    @staticmethod
    def parse_modules_env(env_value: str) -> dict[str, dict]:
        """Parse {prefix}_MODULES value.

        Format: MOD:LEVEL[,MOD:LEVEL[:PATH],...]

        Returns:
            {module_name: {'level': str, 'path': str | None}}
        """
        if not env_value or not env_value.strip():
            return {}

        parts = [p.strip() for p in env_value.split(',')]
        module_configs: dict[str, dict] = {}

        for part in parts:
            if not part:
                continue

            # Windows abs path: split max 2 (e.g., 'mod:DEBUG:C:\\path\\log.log' → 3 segments)
            segments = part.split(':', 2)
            if len(segments) == 2:
                mod_name, level = segments
                module_configs[mod_name] = {'level': level.upper(), 'path': None}
            elif len(segments) == 3:
                mod_name, level, path = segments
                module_configs[mod_name] = {'level': level.upper(), 'path': path}
            else:
                print(
                    f'[D-SafeLogger] Invalid module spec in env, skipped: {part}',
                    file=sys.stderr,
                )

        return module_configs

    @staticmethod
    def parse_bool_env(env_value: str | None) -> bool | None:
        """Parse boolean env var ({prefix}_CONSOLE / {prefix}_COLOR).

        Returns:
            True, False, or None (don't override).
        """
        if env_value is None:
            return None
        v = env_value.strip().lower()
        if v in ('1', 'true'):
            return True
        if v in ('0', 'false'):
            return False
        return None

    @staticmethod
    def parse_config_path(env_value: str | None) -> str | None:
        """Parse {prefix}_CONFIG value. Empty string → None."""
        if env_value is None:
            return None
        v = env_value.strip()
        return v if v else None

    @staticmethod
    def resolve_env_names(env_prefix: str) -> dict[str, str]:
        """Derive env var names from prefix.

        Returns:
            {'level': 'D_LOG_LEVEL', 'modules': 'D_LOG_MODULES', ...}
        """
        return {
            'level': f'{env_prefix}_LEVEL',
            'modules': f'{env_prefix}_MODULES',
            'config': f'{env_prefix}_CONFIG',
            'console': f'{env_prefix}_CONSOLE',
            'color': f'{env_prefix}_COLOR',
            'diagnose': f'{env_prefix}_DIAGNOSE',
            'hash': f'{env_prefix}_HASH',
            'manifest': f'{env_prefix}_MANIFEST',
        }

    @staticmethod
    def parse_hash_env(env_value: str | None) -> bool | None:
        """Parse {prefix}_HASH value."""
        if env_value is None:
            return None
        v = env_value.strip().lower()
        if v in ('1', 'true'):
            return True
        if v in ('0', 'false'):
            return False
        return None

    @staticmethod
    def parse_manifest_env(env_value: str | None) -> str | None:
        """Parse {prefix}_MANIFEST value. Empty string → None."""
        if env_value is None:
            return None
        v = env_value.strip()
        return v if v else None


