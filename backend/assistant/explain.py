"""Grounded assistant copy from tool payloads. Templates only (no second LLM call)."""

from __future__ import annotations

from typing import Any

from backend.assistant.contract import AssistantIntent


def explain_turn(
    intent: AssistantIntent,
    facts: dict[str, Any],
    *,
    item_name: str | None = None,
) -> tuple[str, str | None]:
    """Return (message, unavailable)."""
    if intent == "refuse_mutation":
        return (
            "I can't apply improvements, publish, grade, or run database commands from Baba AI. "
            "I can propose typed catalogue edits such as price, name, tags, or items after you confirm.",
            None,
        )
    if intent == "clarify":
        if facts.get("needs_venue"):
            return ("Which restaurant do you want me to check?", None)
        return ("Do you mean your overall catalogue grade or a specific item?", None)
    if intent == "unsupported":
        return (
            "I can help with this catalogue's grade, Baba Score, reviews, recommendations, and image improvement workspace.",
            None,
        )
    if intent == "open_catalogue":
        return ("I can take you to this catalogue.", None)
    if intent == "open_grade":
        return _grade_open(facts)
    if intent == "open_improvements":
        return _improvements_open(facts)
    if intent == "open_reviews":
        return _reviews_open(facts)
    if intent == "open_media":
        name = item_name or "this item"
        if facts.get("linkage") == "ambiguous":
            return ("Several menu items match that name. Which one do you mean?", None)
        if facts.get("linkage") == "no_match" and item_name:
            return (f"I couldn't find {item_name} on this catalogue.", "I couldn't uniquely identify that item.")
        return (f"I can take you to the image improvement workspace for {name}.", None)
    if intent == "show_baba_score":
        return _baba_score(facts)
    if intent == "explain_catalogue_grade":
        return _explain_grade(facts)
    if intent == "explain_fix_first":
        return _explain_fix_first(facts)
    if intent == "explain_review_complaints":
        return _explain_complaints(facts)
    if intent == "explain_items_attention":
        return _explain_attention(facts)
    if intent == "explain_item_findings":
        return _explain_item(facts, item_name)
    if intent == "explain_org_grades":
        return _explain_org_grades(facts)
    if intent == "explain_capabilities":
        return _explain_capabilities()
    if intent == "explain_catalogue_summary":
        return _explain_summary(facts)
    if intent == "explain_problems":
        return _explain_problems(facts)
    return ("I can help you understand this catalogue.", None)


def _grade_open(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("unavailable"):
        return ("I don't have enough information to answer that reliably.", str(facts["unavailable"]))
    if facts.get("missing"):
        return (
            "This venue hasn't been graded yet. There is no completed grade for this catalogue revision. You can grade it from the Grading workspace.",
            "No completed grade for this catalogue revision.",
        )
    letter = facts.get("overall_grade")
    why = facts.get("overall_why")
    if letter and why:
        return (f"Your catalogue is graded {letter}. {why}", None)
    if letter:
        return (f"Your catalogue is graded {letter}.", None)
    return ("I can take you to the Grade workspace.", None)


def _improvements_open(facts: dict[str, Any]) -> tuple[str, str | None]:
    count = facts.get("count")
    if isinstance(count, int):
        return (f"I found {count} improvement preview(s) for this catalogue.", None)
    return ("I can take you to the AI Improvements workspace.", None)


def _reviews_open(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("missing"):
        return (
            "Review intelligence has not been generated for this catalogue yet.",
            "No review intelligence for this catalogue.",
        )
    if facts.get("stale"):
        return (
            "Review intelligence is stale for the current catalogue or stored reviews. It is not current.",
            "Review intelligence is stale.",
        )
    return ("I can take you to the Reviews workspace.", None)


def _baba_score(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("missing"):
        return (
            "This venue hasn't been graded yet. There is no completed Baba Score for this catalogue revision. Baba Score comes from the stored catalogue grade.",
            "No completed Baba Score for this catalogue revision.",
        )
    letter = facts.get("letter")
    score = facts.get("score")
    if letter is None:
        return ("I can take you to the Grade workspace to see Baba Score.", None)
    extra = f" (score {score})" if score is not None else ""
    return (
        f"Baba Score for this catalogue is {letter}{extra}. It is independent of platform-native ratings.",
        None,
    )


def _explain_grade(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("unavailable"):
        return ("I don't have enough information to answer that reliably.", str(facts["unavailable"]))
    if facts.get("missing"):
        return (
            "This venue hasn't been graded yet. There is no completed grade for this catalogue revision. You can grade it from the Grading workspace.",
            "No completed grade for this catalogue revision.",
        )
    letter = facts.get("overall_grade")
    why = facts.get("overall_why") or ""
    findings = facts.get("findings") or []
    score = facts.get("overall_score")
    venue = facts.get("venue_name")
    heading = f"Your listing is currently Grade {letter}."
    if venue:
        heading = f"{venue} is currently Grade {letter}."
    if isinstance(score, (int, float)):
        display = int(round(score)) if score > 1 else int(round(score * 100))
        heading = f"{heading[:-1]} ({display} / 100)."
    lines = [heading]
    if why:
        lines.append(why)
    if findings:
        lines.append("The main issues identified are:")
        for index, finding in enumerate(findings, start=1):
            check = finding.get("check_id")
            detail = finding.get("why") or check
            names = [name for name in (finding.get("item_names") or []) if name]
            if names:
                detail = f"{detail} Affected dishes include: {', '.join(names[:5])}."
            lines.append(f"{index}. {detail}")
    first = facts.get("fix_first")
    if first:
        lines.append(f"The highest-priority issue is: {first}")
    lines.append("I can take you to Grading or AI Improvements to review this. Baba AI cannot apply catalogue changes yet.")
    return ("\n".join(lines), None)


def _explain_fix_first(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("unavailable"):
        return ("I don't have enough information to answer that reliably.", str(facts["unavailable"]))
    if facts.get("missing"):
        return (
            "This venue hasn't been graded yet. There is no completed grade for this catalogue revision, so I cannot rank what to fix first.",
            "No completed grade for this catalogue revision.",
        )
    first = facts.get("fix_first")
    if first:
        return (f"What you should improve first: {first}", None)
    return ("There is no prioritized fix-first recommendation on the stored grade explanation.", None)


def _explain_complaints(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("missing"):
        return (
            "Review intelligence has not been generated for this catalogue yet.",
            "No review intelligence for this catalogue.",
        )
    if facts.get("stale"):
        return (
            "Review intelligence is stale for the current catalogue or stored reviews. I will not treat those themes as current.",
            "Review intelligence is stale.",
        )
    recurring = [
        obs
        for obs in (facts.get("observations") or [])
        if obs.get("recurrence_status") == "recurring_complaint"
    ]
    actions = [row for row in (facts.get("recommendation_actions") or []) if row]
    if not recurring and not actions:
        return ("I did not find recurring complaint themes in the available review intelligence.", None)
    lines = ["I found recurring complaint themes in your available customer feedback:"]
    for index, obs in enumerate(recurring, start=1):
        target = obs.get("item_name") or obs.get("target") or "feedback"
        aspect = obs.get("aspect")
        count = obs.get("review_count")
        lines.append(f"{index}. {target} ({aspect}, {count} reviews)")
    for action in actions[:3]:
        lines.append(action)
    return ("\n".join(lines), None)


def _explain_attention(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("unavailable"):
        return ("I don't have enough information to answer that reliably.", str(facts["unavailable"]))
    if facts.get("missing"):
        return (
            "This venue hasn't been graded yet. There is no completed grade for this catalogue revision, so I cannot list items that need attention from grading.",
            "No completed grade for this catalogue revision.",
        )
    findings = facts.get("findings") or []
    if not findings:
        return ("The stored grade explanation does not list item-level attention findings.", None)
    lines = ["Items and fields that need attention according to the stored grade explanation:"]
    for index, finding in enumerate(findings, start=1):
        detail = finding.get("why") or finding.get("check_id")
        names = [name for name in (finding.get("item_names") or []) if name]
        if names:
            detail = f"{detail} Dishes: {', '.join(names[:5])}."
        lines.append(f"{index}. {detail}")
    intel = facts.get("intel") if isinstance(facts.get("intel"), dict) else None
    if intel and intel.get("stale"):
        lines.append("Review intelligence is stale and is not treated as current.")
    return ("\n".join(lines), None)


def _explain_capabilities() -> tuple[str, str | None]:
    msg = (
        "I am Baba AI, your intelligent catalogue assistant for HectoBaba. Here is how I can help you:\n\n"
        "• Catalogue Facts: Check product counts, categories, item prices, missing descriptions, images, or tags.\n"
        "• Quality & Grading: Explain your catalogue grade, Baba Score, and what is lowering your score.\n"
        "• Priority Fixes: Recommend what issues to fix first to improve your grade.\n"
        "• Item Analysis: Inspect individual dishes (e.g. 'What is wrong with Fresh Lemonade?') for detailed quality breakdowns.\n"
        "• AI Improvements: Generate grounded descriptions and tags with live before/after previews and natural language refinement.\n"
        "• Media & Images: Route items to AI image enhancement, background removal, cropping, or GIF creation.\n"
        "• Catalogue Edits: Propose price changes, adding/removing items, renaming, or moving categories for your confirmation.\n"
        "• Customer Feedback: Summarize customer reviews and recurring complaints."
    )
    return (msg, None)


def _explain_summary(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("missing"):
        return ("Catalogue information is not available for this venue.", None)

    venue = facts.get("restaurant_name") or "Your catalogue"
    item_count = facts.get("item_count", 0)
    category_count = facts.get("category_count", 0)
    categories = facts.get("categories") or []
    largest = facts.get("largest_category")
    missing_desc = facts.get("missing_descriptions") or []
    missing_img = facts.get("missing_images") or []
    missing_tags = facts.get("missing_tags") or []
    most_expensive = facts.get("most_expensive")
    cheapest = facts.get("cheapest")

    lines = [f"{venue} currently has {item_count} product(s) across {category_count} category/categories."]

    if categories:
        cat_str = ", ".join(f"{c['name']} ({c['count']} items)" for c in categories[:8])
        lines.append(f"Categories: {cat_str}.")

    if largest:
        lines.append(f"Largest category: {largest['name']} with {largest['count']} products.")

    if most_expensive and cheapest:
        lines.append(
            f"Price range: Cheapest is {cheapest['name']} (₹{cheapest['price']}), Most expensive is {most_expensive['name']} (₹{most_expensive['price']})."
        )

    if missing_desc:
        sample = ", ".join(missing_desc[:5])
        more = f" and {len(missing_desc)-5} more" if len(missing_desc) > 5 else ""
        lines.append(f"Missing descriptions ({len(missing_desc)} items): {sample}{more}.")
    else:
        lines.append("Descriptions: All products have descriptions!")

    if missing_img:
        sample = ", ".join(missing_img[:5])
        more = f" and {len(missing_img)-5} more" if len(missing_img) > 5 else ""
        lines.append(f"Missing images ({len(missing_img)} items): {sample}{more}.")
    else:
        lines.append("Images: All products have images!")

    if missing_tags:
        sample = ", ".join(missing_tags[:5])
        more = f" and {len(missing_tags)-5} more" if len(missing_tags) > 5 else ""
        lines.append(f"Missing tags ({len(missing_tags)} items): {sample}{more}.")

    return ("\n".join(lines), None)


def _explain_problems(facts: dict[str, Any]) -> tuple[str, str | None]:
    if facts.get("unavailable"):
        return ("I don't have enough information to answer that reliably.", str(facts["unavailable"]))
    if facts.get("missing"):
        return (
            "This venue hasn't been graded yet. There is no completed grade for this catalogue revision.",
            "No completed grade for this catalogue revision.",
        )
    letter = facts.get("overall_grade")
    score = facts.get("overall_score")
    findings = facts.get("findings") or []
    fix_first = facts.get("fix_first")

    display_score = f" (score {int(round(score))}/100)" if isinstance(score, (int, float)) else ""
    lines = [f"Catalogue Quality Problems (Grade {letter}{display_score}):"]

    if findings:
        for idx, finding in enumerate(findings, start=1):
            why = finding.get("why") or finding.get("check_id")
            count = finding.get("affected_count")
            count_str = f" ({count} affected)" if count else ""
            names = [n for n in (finding.get("item_names") or []) if n]
            items_str = f" Dishes: {', '.join(names[:5])}." if names else ""
            lines.append(f"{idx}. {why}{count_str}.{items_str}")
    else:
        lines.append("No major grade problems were identified on this catalogue revision.")

    if fix_first:
        lines.append(f"\nHighest impact opportunity: {fix_first}")

    return ("\n".join(lines), None)


def _explain_item(facts: dict[str, Any], item_name: str | None) -> tuple[str, str | None]:
    name = facts.get("item_name") or item_name or "that item"
    if facts.get("linkage") == "ambiguous":
        return (f"Several menu items match {name}. Which one do you mean?", None)
    if facts.get("linkage") == "no_match":
        return (f"I couldn't find {name} on this catalogue.", "I couldn't uniquely identify that item.")

    if facts.get("grade_missing"):
        grade_line = "There is no completed catalogue grade for this revision."
        unavailable = "No completed grade for this catalogue revision."
    else:
        letter = facts.get("catalogue_grade")
        why = facts.get("catalogue_why")
        grade_line = f"Your catalogue is currently graded {letter}."
        if why:
            grade_line = f"{grade_line} {why}"
        unavailable = None

    cat = facts.get("category") or "Menu"
    price = facts.get("price")
    price_str = f" — ₹{price}" if isinstance(price, (int, float)) else ""

    has_desc = facts.get("has_description")
    has_img = facts.get("has_image")
    has_tags = facts.get("has_tags")
    labels = facts.get("labels") or []

    desc_letter = "A" if has_desc else "D"
    desc_status = "Present" if has_desc else "Missing"
    tags_letter = "A" if has_tags else "D"
    tags_status = f"Present ({', '.join(labels)})" if has_tags else "Missing / Weak"
    img_letter = "A" if has_img else "D"
    img_status = "Present" if has_img else "Missing"
    price_letter = "A" if price is not None else "D"
    price_status = f"Present (₹{price})" if price is not None else "Missing"

    lines = [
        grade_line,
        f"\n{name} ({cat}{price_str}):",
        f"• Description: {desc_letter} — {desc_status}",
        f"• Tags: {tags_letter} — {tags_status}",
        f"• Image: {img_letter} — {img_status}",
        f"• Price: {price_letter} — {price_status}",
    ]

    findings = facts.get("findings") or []
    if findings:
        lines.append("\nSpecific findings from grade:")
        for finding in findings:
            lines.append(f"• {finding.get('why') or finding.get('check_id')}")

    if not has_desc:
        lines.append(f'\nThe biggest issue is the missing description. You can ask me to "Improve {name}" to generate a grounded AI description.')
    elif not has_tags:
        lines.append(f'\nThe main improvement opportunity is tags. You can ask me to "Improve {name} tags".')
    elif not has_img:
        lines.append(f'\nThe main improvement opportunity is image quality. You can ask me to "Improve {name} image".')

    return ("\n".join(lines), unavailable)


def _explain_org_grades(facts: dict[str, Any]) -> tuple[str, str | None]:
    venues = facts.get("venues") or []
    if not venues:
        return ("I don't have any restaurants or dineouts in this organization yet.", None)
    poor = [
        row
        for row in venues
        if row.get("graded") and row.get("overall_grade") in {"C", "D", "F"}
    ]
    ungraded = [row for row in venues if not row.get("graded")]
    lines = ["Here are the stored grades I can see for your venues:"]
    for row in venues:
        kind = row.get("catalogue_type") or "venue"
        if not row.get("graded"):
            lines.append(f"• {row.get('name')} ({kind}): this venue hasn't been graded yet.")
            continue
        letter = row.get("overall_grade")
        lines.append(f"• {row.get('name')} ({kind}): Grade {letter}.")
    if poor:
        lines.append("Venues with weaker stored grades are listed above. I can open Grading for any of them.")
    elif ungraded and not poor:
        lines.append("I don't have poor stored grades to highlight. Some venues haven't been graded yet.")
    lines.append("These letters come from the existing grading engine. Baba AI does not invent or recalculate grades.")
    return ("\n".join(lines), None)
