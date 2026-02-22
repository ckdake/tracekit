"""Shared utility functions for the tracekit package."""

from __future__ import annotations

from typing import Any


def sort_providers(providers: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Sort providers by priority (lowest number = highest priority).

    Enabled providers are sorted by their ``priority`` value; disabled
    providers are appended at the end in arbitrary order.

    Args:
        providers: Mapping of provider name → provider config dict.

    Returns:
        Ordered list of (name, config) tuples.
    """
    enabled: list[tuple[int, str, dict[str, Any]]] = []
    disabled: list[tuple[str, dict[str, Any]]] = []
    for name, cfg in providers.items():
        if cfg.get("enabled", False):
            enabled.append((cfg.get("priority", 999), name, cfg))
        else:
            disabled.append((name, cfg))
    enabled.sort(key=lambda x: x[0])
    result: list[tuple[str, dict[str, Any]]] = [(name, cfg) for _, name, cfg in enabled]
    result.extend(disabled)
    return result
