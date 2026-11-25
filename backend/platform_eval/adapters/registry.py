"""Adapter registry. Platform-specific classes are selected here, not via scattered if/elif."""

from __future__ import annotations

from backend.platform_eval.adapters.base import PlatformEvaluationAdapter

_ADAPTERS: dict[str, PlatformEvaluationAdapter] = {}


class UnsupportedPlatform(ValueError):
    def __init__(self, platform: str):
        self.platform = platform
        super().__init__(f"Unsupported platform for evaluation: {platform}")


def register_adapter(adapter: PlatformEvaluationAdapter) -> None:
    key = adapter.platform.strip().lower()
    if key in _ADAPTERS:
        raise ValueError(f"duplicate platform evaluation adapter for {key}")
    _ADAPTERS[key] = adapter


def get_adapter(platform: str) -> PlatformEvaluationAdapter | None:
    return _ADAPTERS.get((platform or "").strip().lower())


def require_adapter(platform: str) -> PlatformEvaluationAdapter:
    adapter = get_adapter(platform)
    if adapter is None:
        raise UnsupportedPlatform(platform)
    return adapter


def supported_platforms() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))
