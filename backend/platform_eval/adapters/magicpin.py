"""Magicpin-native evaluation rules. Does not produce a Baba Score."""

from __future__ import annotations

from backend.canonical.models import CanonicalDocument
from backend.platform_eval.adapters.base import PlatformEvaluationAdapter
from backend.platform_eval.contract import EvaluationContext, PlatformEvidenceItem


class MagicpinPlatformAdapter(PlatformEvaluationAdapter):
    platform = "magicpin"
    adapter_id = "magicpin.platform_eval.v1"

    def apply_rules(self, document: CanonicalDocument, context: EvaluationContext) -> list[PlatformEvidenceItem]:
        venue = self.venue_signals(context.native_signals)
        parseable = self.parseable_venue_scores(context.native_signals)
        listed = [item for item in venue if item.kind == "listed"]
        findings: list[PlatformEvidenceItem] = []

        if venue:
            findings.append(
                self.evidence(
                    check_id="magicpin_native_rating_present",
                    result="pass",
                    explanation="Magicpin-native rating signals are present.",
                    severity="info",
                    details={"kinds": [item.kind for item in venue]},
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="magicpin_native_rating_present",
                    result="fail",
                    explanation="No Magicpin-native venue rating was ingested.",
                    path="venue.ratings",
                )
            )

        if venue and parseable:
            findings.append(
                self.evidence(
                    check_id="magicpin_native_rating_parseable",
                    result="pass",
                    explanation="At least one Magicpin venue rating parsed as a finite number.",
                    severity="info",
                )
            )
        elif venue:
            findings.append(
                self.evidence(
                    check_id="magicpin_native_rating_parseable",
                    result="fail",
                    explanation="Magicpin venue rating values were present but not parseable numbers.",
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="magicpin_native_rating_parseable",
                    result="skip",
                    explanation="No Magicpin venue rating to parse.",
                    severity="info",
                )
            )

        if listed and context.source_platform != self.platform:
            findings.append(
                self.evidence(
                    check_id="magicpin_listed_on_foreign_listing",
                    result="pass",
                    explanation="Magicpin rating is listed on another platform's source listing. It remains Magicpin evidence, not Baba Score.",
                    severity="info",
                    details={"source_platform": context.source_platform},
                )
            )
        elif context.source_platform != self.platform:
            findings.append(
                self.evidence(
                    check_id="magicpin_listed_on_foreign_listing",
                    result="skip",
                    explanation="Magicpin is not this catalogue's source platform and no listed Magicpin rating was found.",
                    severity="info",
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="magicpin_source_listing",
                    result="pass",
                    explanation="This catalogue's source listing is Magicpin.",
                    severity="info",
                    details={"source_url": document.provenance.source_url},
                )
            )

        split_kinds = {item.kind for item in parseable if item.kind in {"dining", "delivery"}}
        findings.append(
            self.evidence(
                check_id="magicpin_single_listing_score",
                result="pass" if parseable and not split_kinds else "skip",
                explanation=(
                    "Magicpin evidence uses listing/primary native scores rather than a dining/delivery split."
                    if parseable and not split_kinds
                    else "Magicpin dining/delivery native kinds were observed; they remain Magicpin evidence."
                    if split_kinds
                    else "No parseable Magicpin venue score for listing-score observation."
                ),
                severity="info",
                details={"kinds": sorted({item.kind for item in parseable})},
            )
        )

        out_of_scale = [item for item in parseable if item.in_declared_scale is False]
        if parseable and not out_of_scale:
            findings.append(
                self.evidence(
                    check_id="magicpin_declared_native_scale",
                    result="pass",
                    explanation="Parseable Magicpin venue scores lie on the declared native 0–5 observation scale. This is not a Baba Score.",
                    severity="info",
                )
            )
        elif out_of_scale:
            findings.append(
                self.evidence(
                    check_id="magicpin_declared_native_scale",
                    result="fail",
                    explanation="A Magicpin native score is outside the declared 0–5 observation scale. It is still not converted into a Baba Score.",
                    details={"values": [item.score for item in out_of_scale]},
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="magicpin_declared_native_scale",
                    result="skip",
                    explanation="No parseable Magicpin venue score to compare with the declared native scale.",
                    severity="info",
                )
            )
        return findings
