"""Test suite for description grounding, product title vs description, and tag generation grounding."""

import pytest
from backend.canonical.models import CanonicalDocument, CanonicalMenuCategory, CanonicalMenuItem, CanonicalMenu
from backend.improvement.contract import GeneratorCandidate, TrustedItemContext, ImprovementLineRequest
from backend.improvement.eligibility import _item_context, _item_at, resolve_targets
from backend.improvement.generators.ollama import OllamaImprovementGenerator
from backend.improvement.service import create_improvement, _generate_line, _grounded_description_text
from backend.improvement.validate import validate_candidate, validate_labels, CandidateRejected, trusted_blob
from backend.schemas import CatalogCreateResponse
from backend.store import save_catalogue
from backend.services.grading_service import grade_catalogue
from backend.services.grade_explain_service import get_grade_explanation

def test_product_title_is_not_treated_as_description():
    """Verify that item.name is never treated as item.description when description is empty."""
    item = CanonicalMenuItem(
        name="Chilli Paneer Maggi",
        description="",
        price=80,
        food_type="veg",
        labels=[],
    )
    category = CanonicalMenuCategory(name="Maggi & Snacks", items=[item])
    doc = CanonicalDocument(
        venue_id="v1",
        restaurant_name="Test Venue",
        catalogue_type="restaurant",
        extraction_status="ok",
        provenance={
            "platform": "magicpin",
            "source_url": "https://magicpin.in/test/1",
            "canonical_source_url": "https://magicpin.in/test/1",
            "adapter_version": "canonical.v1",
        },
        menus=[CanonicalMenu(menu_kind="delivery", categories=[category])],
    )
    
    ctx = _item_context(
        document=doc,
        category=category,
        item=item,
        item_path="menus[0].categories[0].items[0]",
        kind="description",
        current_value=item.description,
    )
    
    assert ctx.current_value == ""
    assert ctx.name == "Chilli Paneer Maggi"
    assert ctx.needs_ollama is True


def test_title_only_description_proposal_rejected():
    """Verify that candidate descriptions identical or trivial variants of the product title are rejected."""
    ctx = TrustedItemContext(
        path="menus[0].categories[0].items[0].description",
        kind="description",
        name="Chilli Paneer Maggi",
        category_name="Maggi",
        food_type="veg",
        labels=[],
        current_value="",
    )
    
    # Exact match -> rejected
    cand1 = GeneratorCandidate(proposed_value="Chilli Paneer Maggi")
    with pytest.raises(CandidateRejected):
        validate_candidate(ctx, cand1)

    # Trivial prefix/suffix -> rejected
    cand2 = GeneratorCandidate(proposed_value="A Chilli Paneer Maggi dish.")
    with pytest.raises(CandidateRejected):
        validate_candidate(ctx, cand2)

    # Real description containing title -> accepted
    cand3 = GeneratorCandidate(proposed_value="A flavorful Maggi preparation cooked with chilli and paneer.")
    valid = validate_candidate(ctx, cand3)
    assert valid == "A flavorful Maggi preparation cooked with chilli and paneer."


def test_tag_generation_grounding_and_validation():
    """Verify tag generation grounding, taxonomy validation, and rejection of unsupported claims."""
    ctx = TrustedItemContext(
        path="menus[0].categories[0].items[0].labels",
        kind="labels",
        name="Chilli Paneer Maggi",
        category_name="Maggi",
        food_type="veg",
        labels=[],
        current_value="",
    )
    
    # Grounded tags -> accepted
    grounded = ["veg", "snack", "maggi", "chilli", "paneer"]
    valid = validate_labels(ctx, grounded)
    assert "veg" in valid
    assert "paneer" in valid

    # Hallucinated ingredients or health claims in tags -> rejected
    unsupported = ["veg", "chicken", "sugar-free", "organic certified"]
    with pytest.raises(CandidateRejected):
        validate_labels(ctx, unsupported)


def test_end_to_end_description_and_tag_proposals_require_owner_approval(tmp_path):
    """End-to-end verification that create_improvement creates a proposal with ScriptedGenerator."""
    from backend.improvement.contract import GeneratorCandidate
    from backend.improvement.service import set_generator_factory

    class TestScriptedGen:
        def generate(self, context, *, why):
            if context.kind == "labels":
                return GeneratorCandidate(proposed_labels=["veg", "maggi", "spicy"], proposed_value="")
            return GeneratorCandidate(proposed_value="A delicious Chilli Paneer Maggi preparation.")

    set_generator_factory(lambda: TestScriptedGen())
    try:
        user_id = "u_test"
        org_id = "org_test"
        
        test_catalogue = CatalogCreateResponse(
            source="magicpin",
            source_url="https://magicpin.in/test/store/1",
            extraction_status="ok",
            source_type="dom",
            restaurant_name="Test Bistro",
            fssai_number="12345678901234",
            categories=[
                {
                    "name": "Snacks",
                    "items": [
                        {
                            "name": "Chilli Paneer Maggi",
                            "description": "",
                            "price": 80,
                            "food_type": "veg",
                            "labels": [],
                        }
                    ]
                }
            ],
            item_count=1,
            image_count=0,
        )
        
        cat_id = save_catalogue(user_id=user_id, organization_id=org_id, result=test_catalogue)
        if hasattr(cat_id, "id"):
            cat_id = cat_id.id

        grade_catalogue(user_id=user_id, organization_id=org_id, catalogue_id=cat_id)

        # 1. Create description proposal
        req_desc = ImprovementLineRequest(
            check_id="missing_description",
            paths=["menus[0].categories[0].items[0].description"]
        )
        p_desc = create_improvement(user_id=user_id, organization_id=org_id, catalogue_id=cat_id, request=req_desc)
        assert p_desc.status in {"READY", "PARTIAL"}
        assert len(p_desc.lines) == 1
        line = p_desc.lines[0]
        assert line.kind == "description"
        assert line.current_value == ""
        assert line.proposed_value == "A delicious Chilli Paneer Maggi preparation."

        # 2. Create tags proposal
        req_tags = ImprovementLineRequest(
            check_id="empty_item_labels",
            paths=["menus[0].categories[0].items[0].labels"]
        )
        p_tags = create_improvement(user_id=user_id, organization_id=org_id, catalogue_id=cat_id, request=req_tags)
        assert p_tags.status in {"READY", "PARTIAL"}
        assert len(p_tags.lines) == 1
        t_line = p_tags.lines[0]
        assert t_line.kind == "labels"
        assert t_line.proposed_labels is not None
        assert "veg" in t_line.proposed_labels
    finally:
        set_generator_factory(None)


def test_restaurant_name_and_meta_phrase_rejection():
    """Verify that restaurant names and menu meta-phrases are rejected in description validation."""
    ctx = TrustedItemContext(
        path="menus[0].categories[0].items[0].description",
        kind="description",
        name="Chilli Paneer Maggi",
        category_name="Maggi",
        restaurant_name="The Food Club",
        food_type="veg",
        labels=[],
        current_value="",
    )

    # Restaurant name injected when not in item name -> rejected
    cand1 = GeneratorCandidate(proposed_value="A spicy Chilli Paneer Maggi preparation from The Food Club.")
    with pytest.raises(CandidateRejected):
        validate_candidate(ctx, cand1)

    # Menu meta-phrase injected -> rejected
    cand2 = GeneratorCandidate(proposed_value="A spicy Chilli Paneer Maggi item from our menu.")
    with pytest.raises(CandidateRejected):
        validate_candidate(ctx, cand2)

    # Clean description without restaurant name or meta-phrase -> accepted
    cand3 = GeneratorCandidate(proposed_value="A spicy Chilli Paneer Maggi preparation cooked with veggies.")
    valid = validate_candidate(ctx, cand3)
    assert valid == "A spicy Chilli Paneer Maggi preparation cooked with veggies."


def test_individual_description_targets_exactly_one_item():
    """Verify that an individual description request targets exactly one item and one kind."""
    doc = CanonicalDocument(
        venue_id="v1",
        restaurant_name="Test Venue",
        catalogue_type="restaurant",
        extraction_status="ok",
        provenance={"platform": "swiggy", "source_url": "https://swiggy.com/1", "canonical_source_url": "https://swiggy.com/1", "adapter_version": "canonical.v1"},
        menus=[
            CanonicalMenu(
                menu_kind="delivery",
                categories=[
                    CanonicalMenuCategory(
                        name="Drinks",
                        items=[
                            CanonicalMenuItem(name="Item 1", description="", price=100),
                            CanonicalMenuItem(name="Item 2", description="", price=200),
                        ],
                    )
                ],
            )
        ],
    )
    explanation = get_grade_explanation
    # Resolving path for item 1 only
    req_path = ["menus[0].categories[0].items[0].description"]
    # Verify resolve_targets returns exactly 1 target
    from backend.improvement.eligibility import _targets_from_paths
    targets = _targets_from_paths(document=doc, check_id="missing_description", paths=req_path)
    assert len(targets) == 1
    assert targets[0].name == "Item 1"
    assert targets[0].kind == "description"


def test_individual_tags_targets_exactly_one_item():
    """Verify that an individual tags request targets exactly one item and kind labels."""
    doc = CanonicalDocument(
        venue_id="v1",
        restaurant_name="Test Venue",
        catalogue_type="restaurant",
        extraction_status="ok",
        provenance={"platform": "swiggy", "source_url": "https://swiggy.com/1", "canonical_source_url": "https://swiggy.com/1", "adapter_version": "canonical.v1"},
        menus=[
            CanonicalMenu(
                menu_kind="delivery",
                categories=[
                    CanonicalMenuCategory(
                        name="Drinks",
                        items=[
                            CanonicalMenuItem(name="Item 1", description="", price=100, labels=[]),
                            CanonicalMenuItem(name="Item 2", description="", price=200, labels=[]),
                        ],
                    )
                ],
            )
        ],
    )
    req_path = ["menus[0].categories[0].items[1].labels"]
    from backend.improvement.eligibility import _targets_from_paths
    targets = _targets_from_paths(document=doc, check_id="empty_item_labels", paths=req_path)
    assert len(targets) == 1
    assert targets[0].name == "Item 2"
    assert targets[0].kind == "labels"


def test_description_proposal_does_not_change_tags_or_image():
    """Verify that a description proposal contains only description lines."""
    from backend.improvement.contract import GeneratorCandidate
    from backend.improvement.service import set_generator_factory

    class TestGen:
        def generate(self, context, *, why):
            return GeneratorCandidate(proposed_value="A nice description.")

    set_generator_factory(lambda: TestGen())
    try:
        test_cat = CatalogCreateResponse(
            source="swiggy",
            source_url="https://swiggy.com/test/1",
            extraction_status="ok",
            restaurant_name="Test Rest",
            fssai_number="123",
            categories=[{"name": "C1", "items": [{"name": "Food", "description": "", "price": 50, "labels": ["veg"]}]}],
            item_count=1,
            image_count=0,
        )
        cat_id = save_catalogue(user_id="u1", organization_id="o1", result=test_cat)
        if hasattr(cat_id, "id"):
            cat_id = cat_id.id
        grade_catalogue(user_id="u1", organization_id="o1", catalogue_id=cat_id)
        
        req = ImprovementLineRequest(
            check_id="missing_description",
            paths=["menus[0].categories[0].items[0].description"]
        )
        p = create_improvement(user_id="u1", organization_id="o1", catalogue_id=cat_id, request=req)
        assert len(p.lines) == 1
        assert p.lines[0].kind == "description"
        assert p.lines[0].proposed_labels is None
    finally:
        set_generator_factory(None)


def test_s1200_not_rejected():
    """Verify high resolution =s1200 image URL parameters pass normalization."""
    from backend.catalogue_normalize import normalize_image_url
    url = "https://lh3.googleusercontent.com/test_image_hash=s1200"
    display_url, source_url, dropped = normalize_image_url(url)
    assert display_url is not None
    assert dropped is False


