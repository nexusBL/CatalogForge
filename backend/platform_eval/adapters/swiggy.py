"""Swiggy-native evaluation rules. Does not produce a Baba Score."""

from __future__ import annotations

from backend.canonical.models import CanonicalDocument
from backend.platform_eval.adapters.base import PlatformEvaluationAdapter
from backend.platform_eval.contract import EvaluationContext, PlatformEvidenceItem


class SwiggyPlatformAdapter(PlatformEvaluationAdapter):
    platform = "swiggy"
    adapter_id = "swiggy.platform_eval.v1"

    def apply_rules(self, document: CanonicalDocument, context: EvaluationContext) -> list[PlatformEvidenceItem]:
        venue = self.venue_signals(context.native_signals)
        parseable = self.parseable_venue_scores(context.native_signals)
        items = [item for item in context.native_signals if item.kind == "item"]
        findings: list[PlatformEvidenceItem] = []

        if venue:
            findings.append(
                self.evidence(
                    check_id="swiggy_native_rating_present",
                    result="pass",
                    explanation="Swiggy-native rating signals are present on the catalogue.",
                    severity="info",
                    details={"kinds": [item.kind for item in venue]},
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="swiggy_native_rating_present",
                    result="fail",
                    explanation="No Swiggy-native venue rating was ingested.",
                    path="venue.ratings",
                )
            )

        if venue and parseable:
            findings.append(
                self.evidence(
                    check_id="swiggy_native_rating_parseable",
                    result="pass",
                    explanation="At least one Swiggy venue rating parsed as a finite number.",
                    severity="info",
                    details={"count": len(parseable)},
                )
            )
        elif venue:
            findings.append(
                self.evidence(
                    check_id="swiggy_native_rating_parseable",
                    result="fail",
                    explanation="Swiggy venue rating values were present but not parseable numbers.",
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="swiggy_native_rating_parseable",
                    result="skip",
                    explanation="No Swiggy venue rating to parse.",
                    severity="info",
                )
            )

        counted = [item for item in venue if item.count not in (None, "")]
        findings.append(
            self.evidence(
                check_id="swiggy_native_rating_count_present",
                result="pass" if counted else ("skip" if not venue else "fail"),
                explanation=(
                    "Swiggy rating counts were ingested."
                    if counted
                    else "No Swiggy rating count was ingested."
                ),
                severity="info" if counted or not venue else "ordinary",
                details={"with_count": len(counted)},
            )
        )

        kinds = {item.kind for item in parseable}
        if "dining" in kinds and "delivery" in kinds:
            findings.append(
                self.evidence(
                    check_id="swiggy_dining_delivery_split",
                    result="pass",
                    explanation="Swiggy dining and delivery ratings are both present as separate native signals.",
                    severity="info",
                    details={"kinds": sorted(kinds)},
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="swiggy_dining_delivery_split",
                    result="skip",
                    explanation="Swiggy dining/delivery split was not both present.",
                    severity="info",
                    details={"kinds": sorted(kinds)},
                )
            )

        out_of_scale = [item for item in parseable if item.in_declared_scale is False]
        if parseable and not out_of_scale:
            findings.append(
                self.evidence(
                    check_id="swiggy_declared_native_scale",
                    result="pass",
                    explanation="Parseable Swiggy venue scores lie on the declared native 0–5 observation scale. This is not a Baba Score.",
                    severity="info",
                )
            )
        elif out_of_scale:
            findings.append(
                self.evidence(
                    check_id="swiggy_declared_native_scale",
                    result="fail",
                    explanation="A Swiggy native score is outside the declared 0–5 observation scale. It is still not converted into a Baba Score.",
                    details={"values": [item.score for item in out_of_scale]},
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="swiggy_declared_native_scale",
                    result="skip",
                    explanation="No parseable Swiggy venue score to compare with the declared native scale.",
                    severity="info",
                )
            )

        findings.append(
            self.evidence(
                check_id="swiggy_item_ratings_observed",
                result="pass" if items else "skip",
                explanation=(
                    f"Observed {len(items)} Swiggy item-level native ratings."
                    if items
                    else "No Swiggy item-level native ratings were ingested."
                ),
                severity="info",
                details={"item_ratings": len(items)},
            )
        )

        if context.source_platform != self.platform:
            findings.append(
                self.evidence(
                    check_id="swiggy_listed_on_foreign_listing",
                    result="pass",
                    explanation="Swiggy signals were observed on a listing whose source platform is not Swiggy.",
                    severity="info",
                    details={"source_platform": context.source_platform},
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="swiggy_source_listing",
                    result="pass",
                    explanation="This catalogue's source listing is Swiggy.",
                    severity="info",
                    details={"source_url": document.provenance.source_url},
                )
            )
        return findings
