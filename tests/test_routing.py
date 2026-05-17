"""Tests for dsafelogger._routing (RoutingStrategy implementations)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from dsafelogger._routing import (
    CountStrategy,
    CyclicMonthStrategy,
    CyclicWeekdayStrategy,
    DailyStrategy,
    HourlyStrategy,
    MinIntervalStrategy,
    NoneStrategy,
    SizeStrategy,
    StartupIntervalStrategy,
    create_strategy,
)


class TestNoneStrategy:
    def test_path_generation(self, tmp_path):
        s = NoneStrategy(tmp_path, 'MyApp')
        assert s.get_current_path() == tmp_path / 'MyApp.log'

    def test_should_switch_always_false(self, tmp_path):
        s = NoneStrategy(tmp_path, 'MyApp')
        assert s.should_switch() is False


class TestDailyStrategy:
    def test_path_format(self, tmp_path):
        s = DailyStrategy(tmp_path, 'MyApp')
        path = s.get_current_path()
        today = datetime.now().strftime('%Y%m%d')
        assert path == tmp_path / f'MyApp_{today}.log'

    def test_should_switch_same_day(self, tmp_path):
        s = DailyStrategy(tmp_path, 'MyApp')
        assert s.should_switch() is False

    def test_should_switch_next_day(self, tmp_path):
        s = DailyStrategy(tmp_path, 'MyApp')
        s._current_date = '20200101'
        assert s.should_switch() is True


class TestHourlyStrategy:
    def test_path_format(self, tmp_path):
        s = HourlyStrategy(tmp_path, 'MyApp')
        path = s.get_current_path()
        now = datetime.now()
        expected = tmp_path / f'MyApp_{now.strftime("%Y%m%d_%H")}.log'
        assert path == expected


class TestMinIntervalStrategy:
    def test_valid_interval_10(self, tmp_path):
        s = MinIntervalStrategy(tmp_path, 'MyApp', 10)
        assert s.should_switch() is False

    def test_invalid_interval_7(self, tmp_path):
        with pytest.raises(ValueError, match='divisor of 60'):
            MinIntervalStrategy(tmp_path, 'MyApp', 7)

    def test_invalid_interval_0(self, tmp_path):
        with pytest.raises(ValueError):
            MinIntervalStrategy(tmp_path, 'MyApp', 0)

    def test_valid_intervals(self, tmp_path):
        for i in [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60]:
            s = MinIntervalStrategy(tmp_path, 'MyApp', i)
            assert s.should_switch() is False


class TestStartupIntervalStrategy:
    def test_integer_interval(self, tmp_path):
        s = StartupIntervalStrategy(tmp_path, 'MyApp', 60)
        assert s.should_switch() is False

    def test_hours_string(self, tmp_path):
        s = StartupIntervalStrategy(tmp_path, 'MyApp', '12h')
        assert s._interval_minutes == 720

    def test_days_string(self, tmp_path):
        s = StartupIntervalStrategy(tmp_path, 'MyApp', '1d')
        assert s._interval_minutes == 1440

    def test_numeric_string(self, tmp_path):
        s = StartupIntervalStrategy(tmp_path, 'MyApp', '60')
        assert s._interval_minutes == 60


class TestSizeStrategy:
    def test_path_format_3_digits(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 1024, None, 3)
        assert s.get_current_path() == tmp_path / 'MyApp_000.log'

    def test_path_format_5_digits(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 1024, None, 5)
        assert s.get_current_path() == tmp_path / 'MyApp_00000.log'

    def test_should_switch_no_file(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 1024, None, 3)
        assert s.should_switch() is False

    def test_should_switch_under_limit(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 1024, None, 3)
        path = s.get_current_path()
        path.write_text('x' * 100)
        assert s.should_switch() is False

    def test_should_switch_over_limit(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 100, None, 3)
        path = s.get_current_path()
        path.write_text('x' * 150)
        assert s.should_switch() is True

    def test_advance_sequential(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 100, None, 3)
        new_path = s.advance()
        assert new_path == tmp_path / 'MyApp_001.log'

    def test_advance_cyclic(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 100, 3, 3)
        assert s.is_cyclic() is True
        s.advance()  # 1
        s.advance()  # 2
        p = s.advance()  # 0 (wraps)
        assert p == tmp_path / 'MyApp_000.log'

    def test_overflow_error(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 100, None, 2)
        for _ in range(99):
            s.advance()
        with pytest.raises(OverflowError):
            s.advance()

    def test_is_cyclic_with_max_count(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 100, 3, 3)
        assert s.is_cyclic() is True

    def test_is_cyclic_without_max_count(self, tmp_path):
        s = SizeStrategy(tmp_path, 'MyApp', 100, None, 3)
        assert s.is_cyclic() is False


class TestCountStrategy:
    def test_should_switch_under(self, tmp_path):
        s = CountStrategy(tmp_path, 'MyApp', 10, None, 3)
        assert s.should_switch() is False

    def test_should_switch_over(self, tmp_path):
        s = CountStrategy(tmp_path, 'MyApp', 3, None, 3)
        for _ in range(3):
            s.increment_line_count()
        assert s.should_switch() is True

    def test_advance_resets_count(self, tmp_path):
        s = CountStrategy(tmp_path, 'MyApp', 3, None, 3)
        for _ in range(3):
            s.increment_line_count()
        s.advance()
        assert s._line_count == 0


class TestCyclicWeekdayStrategy:
    def test_is_cyclic(self, tmp_path):
        s = CyclicWeekdayStrategy(tmp_path, 'MyApp')
        assert s.is_cyclic() is True

    def test_should_switch_same_day(self, tmp_path):
        s = CyclicWeekdayStrategy(tmp_path, 'MyApp')
        assert s.should_switch() is False


class TestCyclicMonthStrategy:
    def test_is_cyclic(self, tmp_path):
        s = CyclicMonthStrategy(tmp_path, 'MyApp')
        assert s.is_cyclic() is True

    def test_path_format(self, tmp_path):
        s = CyclicMonthStrategy(tmp_path, 'MyApp')
        month = datetime.now().month
        assert s.get_current_path() == tmp_path / f'MyApp_{month:02d}.log'


class TestCreateStrategy:
    def test_none(self, tmp_path):
        s = create_strategy('none', tmp_path, 'A')
        assert isinstance(s, NoneStrategy)

    def test_daily(self, tmp_path):
        s = create_strategy('daily', tmp_path, 'A')
        assert isinstance(s, DailyStrategy)

    def test_unknown_raises(self, tmp_path):
        with pytest.raises(ValueError, match='Unknown routing_mode'):
            create_strategy('weekly', tmp_path, 'A')
