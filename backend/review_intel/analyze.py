"""Deterministic Phase 8 analysis. Review text is DATA, never instructions."""

from __future__ import annotations

import hashlib
import json

from backend.canonical.models import CanonicalDocument
from backend.review_intel.contract import (
    ENGINE_VERSION,
    RECURRENCE_THRESHOLD,
    FeedbackTarget,
    Polarity,
    RecurrenceLabel,
    ReviewEvidence,
    ReviewIntelligence,
    ReviewLinkage,
    ReviewObservation,
    ReviewRecommendation,
    StoredReview,
)
from backend.review_intel.interpret import combine_polarities, detect_aspect_signals, detect_intent
from backend.review_intel.link import catalogue_item_refs, link_review_text
from backend.review_intel.target import detect_improvement_request, detect_targets, kind_for_target


def reviews_fingerprint(reviews: list[StoredReview]) -> str:
    rows = [
        {
            "external_id": row.external_id,
            "source": row.source,
            "body": row.body,
            "posted_at": row.posted_at,
            "observed_rating": row.observed_rating,
            "photo_id": row.photo_id or "",
        }
        for row in sorted(reviews, key=lambda item: item.external_id)
    ]
    encoded = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def analyze_reviews(
    *,
    analysis_id: str,
    catalogue_id: str,
    organization_id: str,
    source_head_revision: int,
    source_state_hash: str,
    reviews: list[StoredReview],
    document: CanonicalDocument,
    created_at: str,
) -> ReviewIntelligence:
    items = catalogue_item_refs(document)
    grouped: dict[tuple[str, str, str, str, str, str | None, str], ReviewObservation] = {}
    overall_polarities: list[Polarity] = []
    for review in reviews:
        linkages = link_review_text(review.body, items)
        request_kind = detect_improvement_request(review.body)
        signals = detect_aspect_signals(review.body)
        intent = detect_intent([row.polarity for row in signals])
        overall_polarities.append(combine_polarities([row.polarity for row in signals]))
        for target in detect_targets(review.body, linkages):
            for linkage in _linkages_for_target(target, linkages):
                for signal in signals:
                    key = (
                        target,
                        signal.aspect,
                        signal.polarity,
                        linkage.status,
                        linkage.item_id or "",
                        linkage.path,
                        request_kind,
                    )
                    observation = grouped.get(key)
                    if observation is None:
                        observation = ReviewObservation(
                            observation_id=_observation_id(catalogue_id, key),
                            kind=kind_for_target(target),
                            target=target,
                            request_kind=request_kind,
                            intent=intent,
                            aspect=signal.aspect,
                            polarity=signal.polarity,
                            item_id=linkage.item_id,
                            item_name=linkage.item_name,
                            path=linkage.path,
                            linkage_status=linkage.status,
                            review_count=0,
                            polarity_status=signal.polarity,
                            aspect_status=signal.aspect,
                        )
                        grouped[key] = observation
                    observation.review_count += 1
                    if review.observed_rating is not None:
                        observation.observed_ratings.append(review.observed_rating)
                    observation.evidence.append(
                        ReviewEvidence(
                            review_id=review.id,
                            posted_at=review.posted_at,
                            span_text=signal.span_text or linkage.span_text,
                            observed_rating=review.observed_rating,
                            photo_id=review.photo_id,
                            target=target,
                            request_kind=request_kind,
                            intent=intent,
                            aspect=signal.aspect,
                            polarity=signal.polarity,
                            polarity_status=signal.polarity,
                            aspect_status=signal.aspect,
                            linkage=linkage,
                        )
                    )

    observations = []
    for observation in grouped.values():
        recurrence = _recurrence(observation.review_count, observation.polarity)
        theme = "positive_theme" if recurrence != "one_off" and observation.polarity == "positive" else "none"
        observations.append(
            observation.model_copy(
                update={
                    "recurrence_status": recurrence,
                    "positive_theme_status": theme,
                }
            )
        )
    observations = sorted(
        observations,
        key=lambda row: (-row.review_count, row.target, row.aspect, row.linkage_status, row.item_name or "", row.observation_id),
    )
    recommendations = [_recommendation(row) for row in observations if row.evidence]
    recurrences = [row.recurrence_status for row in observations]
    overall_recurrence: RecurrenceLabel = "one_off"
    if "recurring_complaint" in recurrences:
        overall_recurrence = "recurring_complaint"
    elif "repeated" in recurrences:
        overall_recurrence = "repeated"
    return ReviewIntelligence(
        id=analysis_id,
        catalogue_id=catalogue_id,
        organization_id=organization_id,
        engine_version=ENGINE_VERSION,
        source_head_revision=source_head_revision,
        source_state_hash=source_state_hash,
        reviews_fingerprint=reviews_fingerprint(reviews),
        status="READY",
        polarity_status=combine_polarities(overall_polarities),
        aspect_status="ok",
        recurrence_status=overall_recurrence,
        positive_theme_status="positive_theme" if any(row.positive_theme_status == "positive_theme" for row in observations) else "none",
        review_count=len(reviews),
        observations=observations,
        recommendations=recommendations,
        created_at=created_at,
        updated_at=created_at,
    )


def _recurrence(count: int, polarity: Polarity) -> RecurrenceLabel:
    if count < RECURRENCE_THRESHOLD:
        return "one_off"
    if polarity == "negative":
        return "recurring_complaint"
    return "repeated"


def _linkages_for_target(target: FeedbackTarget, linkages: list[ReviewLinkage]) -> list[ReviewLinkage]:
    if target == "product_item":
        matched = [row for row in linkages if row.status in {"exact", "normalized", "ambiguous"}]
        return matched or [ReviewLinkage(status="no_match")]
    unmatched = [row for row in linkages if row.status == "no_match"]
    if unmatched:
        return unmatched[:1]
    return [ReviewLinkage(status="no_match")]


def _observation_id(catalogue_id: str, key: tuple[str, str, str, str, str, str | None, str]) -> str:
    encoded = f"{catalogue_id}:{':'.join(part or '' for part in key)}".encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _recommendation(observation: ReviewObservation) -> ReviewRecommendation:
    ids = [row.review_id for row in observation.evidence]
    action = _action_for(observation)
    if len(set(observation.observed_ratings)) > 1:
        action = f"{action} Observed ratings in the evidence are not identical."
    if observation.request_kind == "improvement_request":
        action = f"{action} Customer requested an improvement. Do not apply changes."
    return ReviewRecommendation(
        recommendation_id=f"rec:{observation.observation_id}",
        observation_id=observation.observation_id,
        action=action,
        target=observation.target,
        request_kind=observation.request_kind,
        intent=observation.intent,
        aspect=observation.aspect,
        polarity=observation.polarity,
        recurrence_status=observation.recurrence_status,
        positive_theme_status=observation.positive_theme_status,
        evidence_review_ids=ids,
    )


def _action_for(observation: ReviewObservation) -> str:
    name = observation.item_name or "this catalogue item"
    if observation.positive_theme_status == "positive_theme":
        return (
            f"Customers independently praised {name} ({observation.aspect}). "
            "Inspect the supporting feedback."
        )
    if observation.recurrence_status == "recurring_complaint":
        if observation.target == "catalogue_menu":
            return "Investigate repeated complaints about catalogue/menu information. Inspect only; do not apply catalogue changes."
        if observation.target == "website_ux":
            return "Investigate repeated complaints about website performance. Inspect only; do not apply changes."
        if observation.target == "restaurant_service":
            return "Review repeated complaints about service."
        if observation.linkage_status in {"exact", "normalized"}:
            return f"Investigate repeated complaints about {name} {observation.aspect}."
        return "Investigate repeated customer complaints. No catalogue item was selected."
    if observation.target == "catalogue_menu":
        return "Inspect catalogue/menu customer feedback. Inspect only; do not apply catalogue changes."
    if observation.target == "website_ux":
        return "Inspect website/UX customer feedback. Inspect only; do not apply changes."
    if observation.target == "restaurant_service":
        return "Inspect restaurant/service customer feedback."
    if observation.linkage_status == "ambiguous":
        return (
            "Inspect stored customer feedback that matched more than one catalogue item. "
            "No item was selected."
        )
    if observation.linkage_status == "no_match":
        return "Inspect stored customer feedback that did not match a catalogue item."
    return f"Inspect stored customer feedback for {name}."
