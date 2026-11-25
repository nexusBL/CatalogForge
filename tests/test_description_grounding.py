"""Tests for Description Grounding Audit & Fix.

Verifies:
1. Item grounding: generation context receives canonical item facts (name, category, price, existing_description, food_type, labels).
2. No 'free menu' contamination: generic menu filler phrases are eliminated.
3. No hallucinated facts: candidates with ungrounded claims or hallucinated ingredients are rejected.
4. Existing description improvement: existing descriptions are preserved semantically.
5. Empty description: generation creates a grounded item-centric description from available facts.
6. Refinement: 'Make it shorter' refines the proposal without losing canonical grounding.
7. Refinement cannot introduce unsupported facts: repeated refinement continues enforcing validation.
8. Wrong item isolation: generating for Item A uses ONLY Item A's facts.
9. Ambiguous item: path-based target resolution isolates items sharing the same name in different categories.
10. Owner approval: generated descriptions remain proposals until explicit owner apply/approval.
"""

import pytest

from backend.improvement.contract import GeneratorCandidate, ImprovementLineRequest, TrustedItemContext
from backend.improvement.eligibility import resolve_targets
from backend.improvement.generators.ollama import _system_prompt
from backend.improvement.service import _grounded_description_text, apply_improvement, create_improvement
from backend.improvement.validate import CandidateRejected, trusted_blob, validate_candidate
from backend.schemas import CatalogCreateResponse
from backend.services.grading_service import grade_catalogue
from backend.store import get_catalogue, save_catalogue
from tests.test_phase6_improvement import ScriptedGenerator, set_generator_factory, _vision_ok


@pytest.fixture(autouse=True)
def _reset_gen():
    yield
    set_generator_factory(None)


@pytest.fixture
def sample_catalogue():
    cat_data = {
        "id": "cat_grounding_1",
        "user_id": "user_1",
        "organization_id": "org_1",
        "extraction_status": "ok",
        "restaurant_name": "Lemon Tree Cafe",
        "fssai_number": "12345678901234",
        "source_url": "https://www.swiggy.com/restaurants/lemon-tree-cafe-101",
        "platform": "swiggy",
        "restaurant": {"name": "Lemon Tree Cafe"},
        "categories": [
            {
                "name": "Drinks",
                "items": [
                    {
                        "name": "Fresh Lemonade",
                        "price": 120,
                        "description": "",
                        "food_type": "veg",
                        "labels": ["Beverage", "Chilled"],
                    }
                ],
            },
            {
                "name": "Starters",
                "items": [
                    {
                        "name": "Paneer Tikka",
                        "price": 250,
                        "description": "",
                        "food_type": "veg",
                        "labels": ["Spicy"],
                    },
                    {
                        "name": "Fresh Lemonade",  # Ambiguous name in different category
                        "price": 150,
                        "description": "",
                        "food_type": "veg",
                        "labels": ["Special"],
                    },
                ],
            },
        ],
    }
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=CatalogCreateResponse.model_validate(cat_data),
    )
    grade_catalogue(user_id="user_1", organization_id="org_1", catalogue_id=stored.id, vision_grader=_vision_ok())
    return stored


def test_1_item_grounding(sample_catalogue):
    """Verify generation context receives canonical item facts."""
    stored = sample_catalogue
    doc = get_catalogue("user_1", stored.id, "org_1").result
    from backend.grading.document import canonical_document_from_result
    from backend.services.grade_explain_service import get_grade_explanation

    canonical_doc = canonical_document_from_result(doc)
    explanation = get_grade_explanation(user_id="user_1", organization_id="org_1", catalogue_id=stored.id)

    resolved = resolve_targets(
        document=canonical_doc,
        explanation=explanation,
        check_id="missing_description",
        requested_paths=["menus[0].categories[0].items[0].description"],
    )
    assert len(resolved.targets) == 1
    target = resolved.targets[0]

    assert target.name == "Fresh Lemonade"
    assert target.category_name == "Drinks"
    assert target.original_price == "120"
    assert "Beverage" in target.labels

    blob = trusted_blob(target)
    assert "Fresh Lemonade" in blob
    assert "Drinks" in blob
    assert "120" in blob


def test_2_no_free_menu_contamination():
    """Verify generic menu filler phrases like 'from the Drinks menu' or 'free menu' are eliminated."""
    context = TrustedItemContext(
        path="menus[0].categories[0].items[0].description",
        kind="description",
        name="Fresh Lemonade",
        category_name="Drinks",
        current_value="",
    )
    text = _grounded_description_text(context)
    assert "menu" not in text.lower()
    assert text == "Fresh Lemonade in Drinks."

    # Verify prompt contains clean instructions
    prompt = _system_prompt("description", has_instruction=False)
    assert "free menu" not in prompt.lower()
    assert "describe the item itself, not the menu" in prompt


def test_3_no_hallucinated_facts():
    """Verify candidates with ungrounded claims or hallucinated ingredients are rejected."""
    context = TrustedItemContext(
        path="menus[0].categories[0].items[0].description",
        kind="description",
        name="Fresh Lemonade",
        category_name="Drinks",
        current_value="Fresh lemon juice with mint.",
        original_price="120",
    )

    # Hallucinated ingredient
    with pytest.raises(CandidateRejected):
        validate_candidate(context, GeneratorCandidate(proposed_value="Fresh lemon juice with strawberry and mint."))

    # Unsupported claim
    with pytest.raises(CandidateRejected):
        validate_candidate(context, GeneratorCandidate(proposed_value="Fresh lemon juice with mint. Organic award winner."))


def test_4_existing_description_improvement():
    """Verify existing description is preserved when present."""
    context = TrustedItemContext(
        path="menus[0].categories[0].items[0].description",
        kind="description",
        name="Fresh Lemonade",
        category_name="Drinks",
        current_value="Freshly squeezed lemons with mint.",
    )
    text = _grounded_description_text(context)
    assert text == "Freshly squeezed lemons with mint."


def test_5_empty_description(sample_catalogue):
    """Verify description proposal generation works for an item with an empty description."""
    gen = ScriptedGenerator(["Spicy Paneer Tikka in Starters."])
    set_generator_factory(lambda: gen)

    proposal = create_improvement(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=sample_catalogue.id,
        request=ImprovementLineRequest(
            check_id="missing_description",
            paths=["menus[0].categories[1].items[0].description"],
        ),
    )
    assert proposal.status == "READY"
    assert proposal.lines[0].proposed_value == "Spicy Paneer Tikka in Starters."


def test_6_refinement(sample_catalogue):
    """Verify 'Make it shorter' refines proposal without losing canonical grounding."""
    gen1 = ScriptedGenerator(["Fresh Lemonade in Drinks."])
    set_generator_factory(lambda: gen1)

    p1 = create_improvement(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=sample_catalogue.id,
        request=ImprovementLineRequest(
            check_id="missing_description",
            paths=["menus[0].categories[0].items[0].description"],
        ),
    )
    assert p1.status == "READY"

    gen2 = ScriptedGenerator(["Fresh Lemonade beverage."])
    set_generator_factory(lambda: gen2)

    p2 = create_improvement(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=sample_catalogue.id,
        request=ImprovementLineRequest(
            check_id="missing_description",
            paths=["menus[0].categories[0].items[0].description"],
            instruction="Make it shorter",
            refining_proposal_id=p1.id,
        ),
    )
    assert p2.status == "READY"
    assert p2.lines[0].proposed_value == "Fresh Lemonade beverage."
    assert p2.lines[0].provenance.get("mode") == "OWNER_REFINED"
    assert p2.lines[0].provenance.get("owner_instruction") == "Make it shorter"


def test_7_refinement_cannot_introduce_unsupported_facts():
    """Verify repeated refinement continues enforcing validation against trusted facts."""
    context = TrustedItemContext(
        path="menus[0].categories[0].items[0].description",
        kind="description",
        name="Fresh Lemonade",
        category_name="Drinks",
        current_value="Fresh lemon juice.",
        current_proposal_value="Fresh Lemonade in Drinks.",
        instruction="Add health claims",
    )
    with pytest.raises(CandidateRejected):
        validate_candidate(context, GeneratorCandidate(proposed_value="Fresh Lemonade in Drinks. Organic award winner."))


def test_8_wrong_item_isolation(sample_catalogue):
    """Verify generating for Item A uses ONLY Item A's facts."""
    stored = sample_catalogue
    doc = get_catalogue("user_1", stored.id, "org_1").result
    from backend.grading.document import canonical_document_from_result
    from backend.services.grade_explain_service import get_grade_explanation

    canonical_doc = canonical_document_from_result(doc)
    explanation = get_grade_explanation(user_id="user_1", organization_id="org_1", catalogue_id=stored.id)

    res_a = resolve_targets(
        document=canonical_doc,
        explanation=explanation,
        check_id="missing_description",
        requested_paths=["menus[0].categories[0].items[0].description"],  # Fresh Lemonade
    )
    res_b = resolve_targets(
        document=canonical_doc,
        explanation=explanation,
        check_id="missing_description",
        requested_paths=["menus[0].categories[1].items[0].description"],  # Paneer Tikka
    )

    target_a = res_a.targets[0]
    target_b = res_b.targets[0]

    assert target_a.name == "Fresh Lemonade"
    assert target_a.category_name == "Drinks"
    assert target_a.original_price == "120"

    assert target_b.name == "Paneer Tikka"
    assert target_b.category_name == "Starters"
    assert target_b.original_price == "250"


def test_9_ambiguous_item(sample_catalogue):
    """Verify path-based target resolution isolates items sharing the same name in different categories."""
    stored = sample_catalogue
    doc = get_catalogue("user_1", stored.id, "org_1").result
    from backend.grading.document import canonical_document_from_result
    from backend.services.grade_explain_service import get_grade_explanation

    canonical_doc = canonical_document_from_result(doc)
    explanation = get_grade_explanation(user_id="user_1", organization_id="org_1", catalogue_id=stored.id)

    # Category 0: Drinks -> Fresh Lemonade (price 120)
    res_0 = resolve_targets(
        document=canonical_doc,
        explanation=explanation,
        check_id="missing_description",
        requested_paths=["menus[0].categories[0].items[0].description"],
    )
    # Category 1: Starters -> Fresh Lemonade (price 150)
    res_1 = resolve_targets(
        document=canonical_doc,
        explanation=explanation,
        check_id="missing_description",
        requested_paths=["menus[0].categories[1].items[1].description"],
    )

    assert res_0.targets[0].category_name == "Drinks"
    assert res_0.targets[0].original_price == "120"

    assert res_1.targets[0].category_name == "Starters"
    assert res_1.targets[0].original_price == "150"


def test_10_owner_approval(sample_catalogue):
    """Verify generated descriptions remain proposals until explicit owner apply/approval."""
    gen = ScriptedGenerator(["Paneer Tikka in Starters."])
    set_generator_factory(lambda: gen)

    proposal = create_improvement(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=sample_catalogue.id,
        request=ImprovementLineRequest(
            check_id="missing_description",
            paths=["menus[0].categories[1].items[0].description"],
        ),
    )
    assert proposal.status == "READY"

    # Database catalogue is NOT modified yet
    stored_before = get_catalogue("user_1", sample_catalogue.id, "org_1")
    item_before = stored_before.result.categories[1]["items"][0]
    assert item_before.get("description") in {None, ""}

    # Owner applies proposal
    res = apply_improvement(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=sample_catalogue.id,
        proposal_id=proposal.id,
    )
    assert res.proposal.status == "APPLIED"

    # Database catalogue is now updated
    stored_after = get_catalogue("user_1", sample_catalogue.id, "org_1")
    item_after = stored_after.result.categories[1]["items"][0]
    assert item_after["description"] == "Paneer Tikka in Starters."
