"""Zomato-native evaluation rules. Does not produce a Baba Score."""

from __future__ import annotations

from backend.canonical.models import CanonicalDocument
from backend.platform_eval.adapters.base import PlatformEvaluationAdapter
from backend.platform_eval.contract import EvaluationContext, PlatformEvidenceItem


class ZomatoPlatformAdapter(PlatformEvaluationAdapter):
    platform = "zomato"
    adapter_id = "zomato.platform_eval.v1"

    def apply_rules(self, document: CanonicalDocument, context: EvaluationContext) -> list[PlatformEvidenceItem]:
        venue = self.venue_signals(context.native_signals)
        parseable = self.parseable_venue_scores(context.native_signals)
        listed = [item for item in venue if item.kind == "listed"]
        findings: list[PlatformEvidenceItem] = []

        if venue:
            findings.append(
                self.evidence(
                    check_id="zomato_native_rating_present",
                    result="pass",
                    explanation="Zomato-native rating signals are present.",
                    severity="info",
                    details={"kinds": [item.kind for item in venue]},
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="zomato_native_rating_present",
                    result="fail",
                    explanation="No Zomato-native venue rating was ingested.",
                    path="venue.ratings",
                )
            )

        if venue and parseable:
            findings.append(
                self.evidence(
                    check_id="zomato_native_rating_parseable",
                    result="pass",
                    explanation="At least one Zomato venue rating parsed as a finite number.",
                    severity="info",
                )
            )
        elif venue:
            findings.append(
                self.evidence(
                    check_id="zomato_native_rating_parseable",
                    result="fail",
                    explanation="Zomato venue rating values were present but not parseable numbers.",
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="zomato_native_rating_parseable",
                    result="skip",
                    explanation="No Zomato venue rating to parse.",
                    severity="info",
                )
            )

        if listed and context.source_platform != self.platform:
            findings.append(
                self.evidence(
                    check_id="zomato_listed_on_foreign_listing",
                    result="pass",
                    explanation="Zomato rating is listed on another platform's source listing. It remains Zomato evidence, not Baba Score.",
                    severity="info",
                    details={"source_platform": context.source_platform},
                )
            )
        elif context.source_platform != self.platform:
            findings.append(
                self.evidence(
                    check_id="zomato_listed_on_foreign_listing",
                    result="skip",
                    explanation="Zomato is not this catalogue's source platform and no listed Zomato rating was found.",
                    severity="info",
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="zomato_source_listing",
                    result="pass",
                    explanation="This catalogue's source listing is Zomato.",
                    severity="info",
                    details={"source_url": document.provenance.source_url},
                )
            )

        kinds = {item.kind for item in parseable}
        if "dining" in kinds and "delivery" in kinds:
            findings.append(
                self.evidence(
                    check_id="zomato_dining_delivery_split",
                    result="pass",
                    explanation="Zomato dining and delivery ratings are both present as separate native signals.",
                    severity="info",
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="zomato_dining_delivery_split",
                    result="skip",
                    explanation="Zomato dining/delivery split was not both present.",
                    severity="info",
                    details={"kinds": sorted(kinds)},
                )
            )

        out_of_scale = [item for item in parseable if item.in_declared_scale is False]
        if parseable and not out_of_scale:
            findings.append(
                self.evidence(
                    check_id="zomato_declared_native_scale",
                    result="pass",
                    explanation="Parseable Zomato venue scores lie on the declared native 0–5 observation scale. This is not a Baba Score.",
                    severity="info",
                )
            )
        elif out_of_scale:
            findings.append(
                self.evidence(
                    check_id="zomato_declared_native_scale",
                    result="fail",
                    explanation="A Zomato native score is outside the declared 0–5 observation scale. It is still not converted into a Baba Score.",
                    details={"values": [item.score for item in out_of_scale]},
                )
            )
        else:
            findings.append(
                self.evidence(
                    check_id="zomato_declared_native_scale",
                    result="skip",
                    explanation="No parseable Zomato venue score to compare with the declared native scale.",
                    severity="info",
                )
            )
        return findings
