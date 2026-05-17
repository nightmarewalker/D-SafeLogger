"""Routing strategies for D-SafeLogger file switching."""

from __future__ import annotations

import abc
import math
from datetime import datetime
from pathlib import Path

from dsafelogger._config_validation import parse_startup_interval_minutes
from dsafelogger._constants import (
    VALID_MIN_INTERVAL_DIVISORS,
    WEEKDAY_SUFFIXES,
)


class RoutingStrategy(abc.ABC):
    """Abstract base class for file routing strategies."""

    def __init__(self, base_dir: Path, pg_name: str) -> None:
        self._base_dir = base_dir
        self._pg_name = pg_name
        self._current_path: Path | None = None

    @abc.abstractmethod
    def get_current_path(self) -> Path:
        """Return the current log file path."""

    @abc.abstractmethod
    def should_switch(self) -> bool:
        """Return True if a file switch should occur."""

    @abc.abstractmethod
    def advance(self) -> Path:
        """Advance the routing state (e.g. index) after a file switch.

        Returns:
            The new file path.
        """
        return self.get_current_path()

    def is_cyclic(self) -> bool:
        """Return True if this strategy overwrites old files cyclically."""
        return False

    def on_emit(self) -> None:
        """Called once per successfully written record (CQS: side-effect hook).

        Override in subclasses that need to update state after each write
        (e.g. CountStrategy increments its line counter here).
        """


class NoneStrategy(RoutingStrategy):
    """No switching: single file forever."""

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._current_path = self._base_dir / f'{self._pg_name}.log'
        return self._current_path

    def should_switch(self) -> bool:
        return False

    def advance(self) -> Path:
        pass


class DailyStrategy(RoutingStrategy):
    """Switch at midnight: {pg_name}_{YYYYMMDD}.log"""

    def __init__(self, base_dir: Path, pg_name: str) -> None:
        super().__init__(base_dir, pg_name)
        self._current_date: str = ''
        self._update_date()

    def _update_date(self) -> None:
        self._current_date = datetime.now().strftime('%Y%m%d')
        self._current_path = self._base_dir / f'{self._pg_name}_{self._current_date}.log'

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._update_date()
        return self._current_path  # type: ignore[return-value]

    def should_switch(self) -> bool:
        return datetime.now().strftime('%Y%m%d') != self._current_date

    def advance(self) -> Path:
        self._update_date()
        return self._current_path  # type: ignore[return-value]


class HourlyStrategy(RoutingStrategy):
    """Switch every hour: {pg_name}_{YYYYMMDD_HH}.log"""

    def __init__(self, base_dir: Path, pg_name: str) -> None:
        super().__init__(base_dir, pg_name)
        self._current_hour: str = ''
        self._update_hour()

    def _update_hour(self) -> None:
        now = datetime.now()
        self._current_hour = now.strftime('%Y%m%d_%H')
        self._current_path = self._base_dir / f'{self._pg_name}_{self._current_hour}.log'

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._update_hour()
        return self._current_path  # type: ignore[return-value]

    def should_switch(self) -> bool:
        return datetime.now().strftime('%Y%m%d_%H') != self._current_hour

    def advance(self) -> Path:
        self._update_hour()
        return self._current_path  # type: ignore[return-value]


class MinIntervalStrategy(RoutingStrategy):
    """Switch at fixed minute boundaries: {pg_name}_{YYYYMMDD_HHMM}.log"""

    def __init__(self, base_dir: Path, pg_name: str, interval: int) -> None:
        if interval not in VALID_MIN_INTERVAL_DIVISORS:
            raise ValueError(
                f"interval must be a divisor of 60, got {interval}. "
                f"Valid values: {sorted(VALID_MIN_INTERVAL_DIVISORS)}"
            )
        super().__init__(base_dir, pg_name)
        self._interval = interval
        self._current_slot: str = ''
        self._update_slot()

    def _get_slot(self) -> str:
        now = datetime.now()
        rounded_minute = (now.minute // self._interval) * self._interval
        return now.strftime('%Y%m%d_%H') + f'{rounded_minute:02d}'

    def _update_slot(self) -> None:
        self._current_slot = self._get_slot()
        self._current_path = self._base_dir / f'{self._pg_name}_{self._current_slot}.log'

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._update_slot()
        return self._current_path  # type: ignore[return-value]

    def should_switch(self) -> bool:
        return self._get_slot() != self._current_slot

    def advance(self) -> Path:
        self._update_slot()
        return self._current_path  # type: ignore[return-value]


class StartupIntervalStrategy(RoutingStrategy):
    """Switch after elapsed time from startup: {pg_name}_{YYYYMMDD_HHMMSS}.log"""

    def __init__(self, base_dir: Path, pg_name: str, interval: str | int) -> None:
        super().__init__(base_dir, pg_name)
        self._interval_minutes = self._parse_interval(interval)
        self._startup_time = datetime.now()
        self._last_switch = self._startup_time
        self._update_path()

    @staticmethod
    def _parse_interval(interval: str | int) -> int:
        """Parse interval value to minutes."""
        return parse_startup_interval_minutes(interval)

    def _update_path(self) -> None:
        now = datetime.now()
        suffix = now.strftime('%Y%m%d_%H%M%S')
        self._current_path = self._base_dir / f'{self._pg_name}_{suffix}.log'

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._update_path()
        return self._current_path  # type: ignore[return-value]

    def should_switch(self) -> bool:
        elapsed = (datetime.now() - self._last_switch).total_seconds()
        return elapsed >= self._interval_minutes * 60

    def advance(self) -> Path:
        self._last_switch = datetime.now()
        self._update_path()
        return self._current_path  # type: ignore[return-value]


class SizeStrategy(RoutingStrategy):
    """Switch when file exceeds max_bytes: {pg_name}_{NNN}.log"""

    def __init__(
        self,
        base_dir: Path,
        pg_name: str,
        max_bytes: int,
        max_count: int | None,
        suffix_digits: int,
    ) -> None:
        super().__init__(base_dir, pg_name)
        self._max_bytes = max_bytes
        self._max_count = max_count
        self._suffix_digits = suffix_digits
        self._index = 0
        self._update_path()

    def _update_path(self) -> None:
        suffix = str(self._index).zfill(self._suffix_digits)
        self._current_path = self._base_dir / f'{self._pg_name}_{suffix}.log'

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._update_path()
        return self._current_path  # type: ignore[return-value]

    def should_switch(self) -> bool:
        path = self.get_current_path()
        if not path.exists():
            return False
        try:
            return path.stat().st_size >= self._max_bytes
        except OSError:
            return False

    def advance(self) -> Path:
        if self._max_count is not None:
            # Cyclic mode
            self._index = (self._index + 1) % self._max_count
        else:
            # Overflow-error mode
            self._index += 1
            max_index = 10 ** self._suffix_digits - 1
            if self._index > max_index:
                raise OverflowError(
                    f"Suffix digits exhausted: {self._suffix_digits} digits "
                    f"cannot represent index {self._index}"
                )
        self._update_path()
        return self._current_path  # type: ignore[return-value]

    def is_cyclic(self) -> bool:
        return self._max_count is not None


class CountStrategy(RoutingStrategy):
    """Switch when line count exceeds max_lines: {pg_name}_{NNN}.log"""

    def __init__(
        self,
        base_dir: Path,
        pg_name: str,
        max_lines: int,
        max_count: int | None,
        suffix_digits: int,
    ) -> None:
        super().__init__(base_dir, pg_name)
        self._max_lines = max_lines
        self._max_count = max_count
        self._suffix_digits = suffix_digits
        self._index = 0
        self._line_count = 0
        self._update_path()

    def _update_path(self) -> None:
        suffix = str(self._index).zfill(self._suffix_digits)
        self._current_path = self._base_dir / f'{self._pg_name}_{suffix}.log'

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._update_path()
        return self._current_path  # type: ignore[return-value]

    def increment_line_count(self) -> None:
        """Increment the line counter after each write."""
        self._line_count += 1

    def on_emit(self) -> None:
        self._line_count += 1

    def should_switch(self) -> bool:
        return self._line_count >= self._max_lines

    def advance(self) -> Path:
        self._line_count = 0
        if self._max_count is not None:
            self._index = (self._index + 1) % self._max_count
        else:
            self._index += 1
            max_index = 10 ** self._suffix_digits - 1
            if self._index > max_index:
                raise OverflowError(
                    f"Suffix digits exhausted: {self._suffix_digits} digits "
                    f"cannot represent index {self._index}"
                )
        self._update_path()
        return self._current_path  # type: ignore[return-value]

    def is_cyclic(self) -> bool:
        return self._max_count is not None


class CyclicWeekdayStrategy(RoutingStrategy):
    """Overwrite by day of week (7 files): {pg_name}_{dow}.log"""

    def __init__(self, base_dir: Path, pg_name: str) -> None:
        super().__init__(base_dir, pg_name)
        self._current_weekday: int = -1
        self._update_weekday()

    def _update_weekday(self) -> None:
        self._current_weekday = datetime.now().weekday()
        suffix = WEEKDAY_SUFFIXES[self._current_weekday]
        self._current_path = self._base_dir / f'{self._pg_name}_{suffix}.log'

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._update_weekday()
        return self._current_path  # type: ignore[return-value]

    def should_switch(self) -> bool:
        return datetime.now().weekday() != self._current_weekday

    def advance(self) -> Path:
        self._update_weekday()
        return self._current_path  # type: ignore[return-value]

    def is_cyclic(self) -> bool:
        return True


class CyclicMonthStrategy(RoutingStrategy):
    """Overwrite by month (12 files): {pg_name}_{MM}.log"""

    def __init__(self, base_dir: Path, pg_name: str) -> None:
        super().__init__(base_dir, pg_name)
        self._current_month: int = -1
        self._update_month()

    def _update_month(self) -> None:
        self._current_month = datetime.now().month
        self._current_path = self._base_dir / f'{self._pg_name}_{self._current_month:02d}.log'

    def get_current_path(self) -> Path:
        if self._current_path is None:
            self._update_month()
        return self._current_path  # type: ignore[return-value]

    def should_switch(self) -> bool:
        return datetime.now().month != self._current_month

    def advance(self) -> Path:
        self._update_month()
        return self._current_path  # type: ignore[return-value]

    def is_cyclic(self) -> bool:
        return True


def create_strategy(
    routing_mode: str,
    base_dir: Path,
    pg_name: str,
    interval: str | int = 10,
    max_bytes: int = 0,
    max_lines: int = 0,
    max_count: int | None = None,
    suffix_digits: int = 3,
) -> RoutingStrategy:
    """Factory function to create the appropriate routing strategy."""
    if routing_mode == 'none':
        return NoneStrategy(base_dir, pg_name)
    elif routing_mode == 'daily':
        return DailyStrategy(base_dir, pg_name)
    elif routing_mode == 'hourly':
        return HourlyStrategy(base_dir, pg_name)
    elif routing_mode == 'min_interval':
        int_interval = int(interval) if isinstance(interval, str) else interval
        return MinIntervalStrategy(base_dir, pg_name, int_interval)
    elif routing_mode == 'startup_interval':
        return StartupIntervalStrategy(base_dir, pg_name, interval)
    elif routing_mode == 'size':
        return SizeStrategy(base_dir, pg_name, max_bytes, max_count, suffix_digits)
    elif routing_mode == 'count':
        return CountStrategy(base_dir, pg_name, max_lines, max_count, suffix_digits)
    elif routing_mode == 'cyclic_weekday':
        return CyclicWeekdayStrategy(base_dir, pg_name)
    elif routing_mode == 'cyclic_month':
        return CyclicMonthStrategy(base_dir, pg_name)
    else:
        raise ValueError(f"Unknown routing_mode: {routing_mode!r}")
