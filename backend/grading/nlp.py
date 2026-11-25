"""Local NLP text-quality grader.

Approved Phase 3 implementation: on-host text-content quality heuristics
(coverage, length, placeholders, exact-repeat descriptions, malformed/empty
text, Unicode, long-text caps). No external NLP provider. No neural/LLM model
is required for Phase 3.
"""

from __future__ import annotations

from collections import Counter

from backend.canonical.models import CanonicalDocument
from backend.grading.contract import StageSignals
from backend.grading.document import iter_menu_items
from backend.grading.evidence import evidence

MAX_TEXT_CHARS = 50_000
PLACEHOLDERS = frozenset(
    {
        "n/a",
        "na",
        "none",
        "null",
        "test",
        "asdf",
        "lorem ipsum",
        "todo",
        ".",
        "..",
        "...",
        "-",
        "--",
    }
)


class NLPGrader:
    def grade(self, document: CanonicalDocument) -> StageSignals:
        findings = []
        texts: list[tuple[str, str]] = []

        venue_name = (document.restaurant_name or document.venue.name or "").strip()
        if venue_name:
            texts.append(("restaurant_name", venue_name))

        item_total = 0
        described = 0
        descriptions: list[str] = []
        for path, _category, item in iter_menu_items(document):
            item_total += 1
            name = (item.name or "").strip()
            if name:
                texts.append((f"{path}.name", name))
            description = (item.description or "").strip()
            if description:
                described += 1
                descriptions.append(description.casefold())
                texts.append((f"{path}.description", description))

        if item_total == 0:
            findings.append(
                evidence(
                    category="nlp",
                    check_id="no_item_text",
                    severity="ordinary",
                    result="skip",
                    explanation="No menu item text was present to evaluate.",
                    path="menus",
                )
            )
            name_score = 100.0 if venue_name and not _is_placeholder(venue_name) else 0.0
            return StageSignals(score=name_score, evidence=findings)

        coverage = 100.0 * described / item_total
        findings.append(
            evidence(
                category="nlp",
                check_id="description_coverage",
                severity="ordinary",
                result="pass" if coverage >= 70 else "fail",
                explanation="Share of menu items that include a description.",
                path="menus",
                details={"described": described, "item_total": item_total, "coverage": round(coverage, 4)},
            )
        )

        placeholder_hits = 0
        long_truncated = 0
        malformed = 0
        quality_points = 0.0
        quality_n = 0
        for path, text in texts:
            analyzed, truncated = _clip(text)
            if truncated:
                long_truncated += 1
            if _is_malformed(analyzed):
                malformed += 1
                findings.append(
                    evidence(
                        category="nlp",
                        check_id="malformed_text",
                        severity="ordinary",
                        result="fail",
                        explanation="Text has no usable letters or digits.",
                        path=path,
                        details={"length": len(text)},
                    )
                )
                quality_n += 1
                continue
            if _is_placeholder(analyzed):
                placeholder_hits += 1
                findings.append(
                    evidence(
                        category="nlp",
                        check_id="placeholder_text",
                        severity="ordinary",
                        result="fail",
                        explanation="Text matches a placeholder token.",
                        path=path,
                        details={"value": analyzed[:80]},
                    )
                )
                quality_n += 1
                continue
            quality_points += _length_score(analyzed)
            quality_n += 1

        if long_truncated:
            findings.append(
                evidence(
                    category="nlp",
                    check_id="very_long_text",
                    severity="info",
                    result="pass",
                    explanation="Over-long fields were truncated for analysis; grading still completed.",
                    details={"truncated_fields": long_truncated, "max_chars": MAX_TEXT_CHARS},
                )
            )

        repeats = [value for value, count in Counter(descriptions).items() if value and count > 1]
        if repeats:
            findings.append(
                evidence(
                    category="nlp",
                    check_id="repeated_description",
                    severity="ordinary",
                    result="fail",
                    explanation="Identical item descriptions are repeated (exact match, not fuzzy).",
                    details={"repeated_count": len(repeats)},
                )
            )

        # _length_score is already 0–100. Do not scale the mean by 100 again
        # (that produced stage scores in the thousands and clamped overall to A).
        text_quality = 100.0 if quality_n == 0 else quality_points / quality_n
        if placeholder_hits:
            text_quality = max(0.0, text_quality - min(40.0, 10.0 * placeholder_hits))
        if repeats:
            text_quality = max(0.0, text_quality - 15.0)
        if malformed:
            text_quality = max(0.0, text_quality - min(30.0, 10.0 * malformed))

        score = round(0.6 * coverage + 0.4 * text_quality, 4)
        return StageSignals(score=score, evidence=findings)


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS], True


def _is_placeholder(text: str) -> bool:
    return text.strip().casefold() in PLACEHOLDERS


def _is_malformed(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return not any(ch.isalnum() for ch in stripped)


def _length_score(text: str) -> float:
    length = len(text.strip())
    if length == 0:
        return 0.0
    if length < 3:
        return 20.0
    if length < 12:
        return 60.0
    if length <= 400:
        return 100.0
    if length <= 2000:
        return 80.0
    return 50.0
