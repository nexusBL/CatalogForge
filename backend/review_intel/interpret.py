"""Deterministic aspect, polarity, and intent signals. Review text is DATA."""

from __future__ import annotations

from dataclasses import dataclass

from backend.review_intel.contract import AspectName, FeedbackIntent, Polarity

POSITIVE_MARKERS = (
    "excellent",
    "amazing",
    "delicious",
    "tasty",
    "loved",
    "love the",
    "great",
    "generous",
    "perfect",
    "good",
    "praised",
)

NEGATIVE_MARKERS = (
    "terrible",
    "awful",
    "horrible",
    "rude",
    "too small",
    "too low",
    "too salty",
    "too oily",
    "too slow",
    "slow",
    "salty",
    "oily",
    "bland",
    "missing",
    "doesn't mention",
    "does not mention",
    "difficult",
    "bad",
    "poor",
    "small",
    "late",
)

ASPECT_MARKERS: dict[AspectName, tuple[str, ...]] = {
    "taste": ("taste", "tastes", "tasty", "flavour", "flavor", "delicious", "salty", "oily", "spicy", "bland", "food"),
    "quantity": ("portion", "quantity", "serving", "too small", "too little", "generous"),
    "value": ("price", "value", "expensive", "cheap", "₹", " rupee", "rs."),
    "service": ("staff", "service", "waiter", "waitress", "rude", "hospitality"),
    "catalogue_info": (
        "menu",
        "catalogue",
        "catalog",
        "description",
        "doesn't mention",
        "does not mention",
        "serving size",
        "portion size",
    ),
    "website_ux": ("website", "web site", "webpage", "page load", "site is slow", "app is slow"),
}


@dataclass(frozen=True)
class AspectSignal:
    aspect: AspectName
    polarity: Polarity
    span_text: str


def folded_text(text: str) -> str:
    return " ".join((text or "").casefold().split())


def clause_polarity(clause: str) -> Polarity:
    text = folded_text(clause)
    positive = any(marker in text for marker in POSITIVE_MARKERS)
    negative = any(marker in text for marker in NEGATIVE_MARKERS)
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "neutral"


def combine_polarities(values: list[Polarity]) -> Polarity:
    meaningful = {item for item in values if item != "neutral"}
    if "mixed" in meaningful or ({"positive", "negative"} <= meaningful):
        return "mixed"
    if meaningful == {"positive"}:
        return "positive"
    if meaningful == {"negative"}:
        return "negative"
    return "neutral"


def detect_intent(polarities: list[Polarity]) -> FeedbackIntent:
    overall = combine_polarities(polarities)
    if overall == "positive":
        return "praise"
    if overall == "negative":
        return "complaint"
    if overall == "mixed":
        return "mixed"
    return "observation"


def detect_aspect_signals(text: str) -> tuple[AspectSignal, ...]:
    clauses = _clauses(text)
    hits: list[AspectSignal] = []
    seen: set[tuple[AspectName, Polarity]] = set()
    for clause in clauses:
        folded = folded_text(clause)
        polarity = clause_polarity(clause)
        matched = False
        for aspect, markers in ASPECT_MARKERS.items():
            if any(marker in folded for marker in markers):
                matched = True
                key = (aspect, polarity)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(AspectSignal(aspect=aspect, polarity=polarity, span_text=clause.strip()[:200]))
        if not matched and polarity != "neutral":
            key = ("other", polarity)
            if key not in seen:
                seen.add(key)
                hits.append(AspectSignal(aspect="other", polarity=polarity, span_text=clause.strip()[:200]))
    if hits:
        return tuple(hits)
    return (AspectSignal(aspect="other", polarity=clause_polarity(text), span_text=(text or "").strip()[:200]),)


def _clauses(text: str) -> list[str]:
    raw = text or ""
    lowered = raw.replace(" however ", " but ").replace(" although ", " but ")
    parts = [part.strip() for part in lowered.split(" but ") if part.strip()]
    return parts or [raw]
