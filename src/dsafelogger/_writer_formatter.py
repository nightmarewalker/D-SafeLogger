"""Writer Formatter helper for D-SafeLogger multiprocess support.

Provides FormatterSpec (TypedDict) and helpers to freeze/rebuild
Formatter instances across process boundaries without pickle or
arbitrary import.

Allow-list (exact type match only):
    logging.Formatter
    DSafeFormatter
    DiagnosticFormatter
    StructuredFormatter
    DiagnosticStructuredFormatter

Custom subclasses raise TypeError at freeze time.
"""
from __future__ import annotations

import logging
from typing import Literal, TypedDict

from dsafelogger._formatter import (
    DSafeFormatter,
    DiagnosticFormatter,
    DiagnosticStructuredFormatter,
    StructuredFormatter,
)

_ALLOW_LIST: tuple[type, ...] = (
    logging.Formatter,
    DSafeFormatter,
    DiagnosticFormatter,
    StructuredFormatter,
    DiagnosticStructuredFormatter,
)

_KIND_MAP: dict[type, str] = {
    logging.Formatter: 'logging.Formatter',
    DSafeFormatter: 'DSafeFormatter',
    DiagnosticFormatter: 'DiagnosticFormatter',
    StructuredFormatter: 'StructuredFormatter',
    DiagnosticStructuredFormatter: 'DiagnosticStructuredFormatter',
}

# Map style class names (from logging internals) to style characters.
_STYLE_CLASS_TO_CHAR: dict[str, str] = {
    'PercentStyle': '%',
    'StrFormatStyle': '{',
    'StringTemplateStyle': '$',
}


class FormatterSpec(TypedDict, total=False):
    """Picklable specification of a Formatter for cross-process reconstruction."""

    kind: Literal[
        'logging.Formatter',
        'DSafeFormatter',
        'DiagnosticFormatter',
        'StructuredFormatter',
        'DiagnosticStructuredFormatter',
    ]
    fmt: str | None
    datefmt: str | None
    style: Literal['%', '{', '$']
    defaults: dict[str, object] | None
    sensitive_keywords: tuple[str, ...] | None


def freeze_formatter(instance: logging.Formatter) -> FormatterSpec:
    """Convert a Formatter instance to a picklable FormatterSpec.

    Only exact types in the allow-list are accepted; custom subclasses
    and any other types raise TypeError.

    Raises:
        TypeError: If ``type(instance)`` is not in the allow-list.
    """
    t = type(instance)
    if t not in _KIND_MAP:
        raise TypeError(
            f"freeze_formatter() accepts only exact allow-list types "
            f"({[c.__name__ for c in _ALLOW_LIST]}), got {t.__name__!r}. "
            "Custom subclasses are not supported."
        )

    kind = _KIND_MAP[t]
    spec: FormatterSpec = {'kind': kind}  # type: ignore[typeddict-item]

    if t in (logging.Formatter, DSafeFormatter):
        spec['fmt'] = getattr(instance, '_fmt', None)
        spec['datefmt'] = instance.datefmt
        style_cls_name = type(instance._style).__name__
        spec['style'] = _STYLE_CLASS_TO_CHAR.get(style_cls_name, '%')
        if t == logging.Formatter:
            # Python stores defaults on the _style object in 3.14+
            spec['defaults'] = (
                getattr(instance, 'defaults', None)
                or getattr(instance, '_defaults', None)
                or getattr(getattr(instance, '_style', None), '_defaults', None)
            )

    elif t == DiagnosticFormatter:
        # DiagnosticFormatter's constructor only accepts fmt/datefmt (no style).
        spec['fmt'] = getattr(instance, '_fmt', None)
        spec['datefmt'] = instance.datefmt
        skws = getattr(instance, '_sensitive_keywords', None)
        spec['sensitive_keywords'] = tuple(skws) if skws is not None else None

    elif t == DiagnosticStructuredFormatter:
        skws = getattr(instance, '_sensitive_keywords', None)
        spec['sensitive_keywords'] = tuple(skws) if skws is not None else None

    # StructuredFormatter: kind only — no constructor args.

    return spec


def rebuild_formatter(spec: FormatterSpec) -> logging.Formatter:
    """Reconstruct a Formatter instance from a FormatterSpec.

    Raises:
        ValueError: If ``kind`` is missing or not in the allow-list.
    """
    kind = spec.get('kind')
    if not kind:
        raise ValueError("FormatterSpec is missing the required 'kind' field.")

    fmt = spec.get('fmt')
    datefmt = spec.get('datefmt')
    style = spec.get('style', '%')
    defaults = spec.get('defaults')
    skws = spec.get('sensitive_keywords')

    if kind == 'logging.Formatter':
        return logging.Formatter(fmt=fmt, datefmt=datefmt, style=style, defaults=defaults)

    if kind == 'DSafeFormatter':
        return DSafeFormatter(fmt=fmt, datefmt=datefmt, style=style)

    if kind == 'DiagnosticFormatter':
        return DiagnosticFormatter(
            fmt=fmt,
            datefmt=datefmt,
            sensitive_keywords=frozenset(skws) if skws is not None else None,
        )

    if kind == 'StructuredFormatter':
        return StructuredFormatter()

    if kind == 'DiagnosticStructuredFormatter':
        return DiagnosticStructuredFormatter(
            sensitive_keywords=frozenset(skws) if skws is not None else None,
        )

    raise ValueError(
        f"Unknown FormatterSpec kind: {kind!r}. "
        f"Expected one of: {list(_KIND_MAP.values())}"
    )
