"""Extract platform-native signals from a canonical catalogue. No Baba Score."""

from __future__ import annotations

from typing import Any

from backend.canonical.models import CanonicalDocument
from backend.platform_eval.contract import (
    DECLARED_NATIVE_SCALE_MAX,
    DECLARED_NATIVE_SCALE_MIN,
    PlatformNativeSignal,
)


def parse_native_score(value: Any) -> tuple[float | None, bool]:
    if value is None or isinstance(value, bool):
        return None, False
    if isinstance(value, (int, float)):
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None, False
        return number, True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, False
        try:
            number = float(text)
        except ValueError:
            return None, False
        if number != number or number in (float("inf"), float("-inf")):
            return None, False
        return number, True
    return None, False


def in_declared_native_scale(score: float | None) -> bool | None:
    if score is None:
        return None
    return DECLARED_NATIVE_SCALE_MIN <= score <= DECLARED_NATIVE_SCALE_MAX


def _signal(*, platform: str, kind: str, score: Any, count: Any, path: str) -> PlatformNativeSignal | None:
    parsed, parseable = parse_native_score(score)
    if score is None and count is None:
        return None
    return PlatformNativeSignal(
        kind=kind,
        score=parsed,
        count=count,
        path=path,
        parseable=parseable,
        in_declared_scale=in_declared_native_scale(parsed) if parseable else None,
        raw={"platform": platform, "score": score, "count": count},
    )


def native_signals_for_platform(document: CanonicalDocument, platform: str) -> list[PlatformNativeSignal]:
    wanted = (platform or "").strip().lower()
    signals: list[PlatformNativeSignal] = []
    venue = document.venue
    for index, rating in enumerate(venue.ratings):
        if (rating.platform or "").strip().lower() != wanted:
            continue
        item = _signal(
            platform=wanted,
            kind=rating.kind or "unspecified",
            score=rating.score,
            count=rating.count,
            path=f"venue.ratings[{index}]",
        )
        if item is not None:
            signals.append(item)
    if (document.provenance.platform or "").strip().lower() == wanted:
        if venue.rating is not None or venue.rating_count is not None:
            if not any(item.kind == "primary" for item in signals):
                item = _signal(
                    platform=wanted,
                    kind="primary",
                    score=venue.rating,
                    count=venue.rating_count,
                    path="venue.rating",
                )
                if item is not None:
                    signals.append(item)
        if venue.dining_rating is not None or venue.dining_rating_count is not None:
            if not any(item.kind == "dining" for item in signals):
                item = _signal(
                    platform=wanted,
                    kind="dining",
                    score=venue.dining_rating,
                    count=venue.dining_rating_count,
                    path="venue.dining_rating",
                )
                if item is not None:
                    signals.append(item)
        if venue.delivery_rating is not None or venue.delivery_rating_count is not None:
            if not any(item.kind == "delivery" for item in signals):
                item = _signal(
                    platform=wanted,
                    kind="delivery",
                    score=venue.delivery_rating,
                    count=venue.delivery_rating_count,
                    path="venue.delivery_rating",
                )
                if item is not None:
                    signals.append(item)
    if (document.provenance.platform or "").strip().lower() == wanted:
        item_index = 0
        for menu in document.menus:
            for category in menu.categories:
                for menu_item in category.items:
                    if menu_item.rating is not None or menu_item.rating_count is not None:
                        item = _signal(
                            platform=wanted,
                            kind="item",
                            score=menu_item.rating,
                            count=menu_item.rating_count,
                            path=f"menus.item[{item_index}].rating",
                        )
                        if item is not None:
                            signals.append(item)
                    item_index += 1
    return signals


def platform_has_related_link(document: CanonicalDocument, platform: str) -> bool:
    wanted = (platform or "").strip().lower()
    return any((link.platform or "").strip().lower() == wanted for link in document.venue.source_links)


def applicable_platforms(document: CanonicalDocument, supported: tuple[str, ...]) -> list[str]:
    source = (document.provenance.platform or "").strip().lower()
    chosen: list[str] = []
    if source in supported:
        chosen.append(source)
    for platform in supported:
        if platform == source:
            continue
        if native_signals_for_platform(document, platform) or platform_has_related_link(document, platform):
            chosen.append(platform)
    return chosen
