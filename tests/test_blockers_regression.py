"""Regression tests for Blocker 1 (Tags AI & Grounding) and Blocker 2 (Scraping & Errors)."""

import pytest
from backend.canonical.models import CanonicalDocument, CanonicalMenuCategory, CanonicalMenuItem, CanonicalMenu
from backend.improvement.contract import GeneratorCandidate, TrustedItemContext, ImprovementLineRequest
from backend.improvement.eligibility import resolve_targets, _targets_from_paths
from backend.improvement.generators.ollama import OllamaImprovementGenerator
from backend.improvement.service import create_improvement, apply_improvement, set_generator_factory
from backend.improvement.validate import validate_labels, CandidateRejected
from backend.schemas import CatalogCreateRequest, CatalogCreateResponse
from backend.services.catalog_service import BrowserAccess, create_catalog, _failed
from backend.services.grading_service import grade_catalogue, get_catalogue_grade
from backend.store import save_catalogue


def test_individual_tag_request_resolves_exactly_one_item():
    """Verify an individual tag request for one item resolves exactly 1 target line."""
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
                        name="Maggi",
                        items=[
                            CanonicalMenuItem(name="Chilli Paneer Maggi", food_type="veg", labels=[]),
                            CanonicalMenuItem(name="Plain Maggi", food_type="veg", labels=[]),
                        ],
                    )
                ],
            )
        ],
    )
    req_paths = ["menus[0].categories[0].items[0].labels"]
    targets = _targets_from_paths(document=doc, check_id="empty_item_labels", paths=req_paths)
    assert len(targets) == 1
    assert targets[0].name == "Chilli Paneer Maggi"
    assert targets[0].kind == "labels"
    assert targets[0].food_type == "veg"


def test_individual_tag_request_calls_ollama():
    """Verify create_improvement for labels invokes the generator when requested."""
    called = False

    class MockGen:
        def generate(self, context, *, why):
            nonlocal called
            called = True
            assert context.kind == "labels"
            assert context.food_type == "veg"
            return GeneratorCandidate(proposed_labels=["veg", "maggi", "paneer", "spicy"], proposed_value="")

    set_generator_factory(lambda: MockGen())
    try:
        test_cat = CatalogCreateResponse(
            platform="swiggy",
            source_url="https://swiggy.com/test/1",
            extraction_status="ok",
            restaurant_name="Test Rest",
            fssai_number="12345678901234",
            restaurant={"name": "Test Rest"},
            categories=[
                {
                    "name": "Maggi",
                    "items": [{"name": "Chilli Paneer Maggi", "description": "Spicy Maggi", "price": 80, "food_type": "veg", "labels": []}],
                }
            ],
            item_count=1,
            image_count=0,
        )
        cat_id = save_catalogue(user_id="u_tag", organization_id="o_tag", result=test_cat)
        if hasattr(cat_id, "id"):
            cat_id = cat_id.id
        grade_catalogue(user_id="u_tag", organization_id="o_tag", catalogue_id=cat_id)

        req = ImprovementLineRequest(check_id="empty_item_labels", paths=["menus[0].categories[0].items[0].labels"])
        prop = create_improvement(user_id="u_tag", organization_id="o_tag", catalogue_id=cat_id, request=req)
        assert called is True
        assert prop.status == "READY"
        assert len(prop.lines) == 1
        assert prop.lines[0].proposed_labels is not None
        assert "veg" in prop.lines[0].proposed_labels
    finally:
        set_generator_factory(None)


def test_food_type_veg_is_preserved_in_final_tags():
    """Verify that when food_type is 'veg', 'veg' MUST be present in final proposed labels."""
    ctx = TrustedItemContext(
        path="menus[0].categories[0].items[0].labels",
        kind="labels",
        name="Chilli Paneer Maggi",
        category_name="Maggi",
        food_type="veg",
        labels=[],
        current_value="",
    )

    # Valid labels containing "veg" -> passes
    valid = validate_labels(ctx, ["veg", "maggi", "paneer", "spicy", "snack"])
    assert "veg" in valid

    # Labels missing "veg" -> raises CandidateRejected("canonical food_type missing")
    with pytest.raises(CandidateRejected) as exc_info:
        validate_labels(ctx, ["maggi", "paneer", "spicy", "snack"])
    assert "canonical food_type missing" in str(exc_info.value)


def test_tag_proposal_is_returned_to_frontend():
    """Verify that create_improvement returns a complete ImprovementProposal object with line status READY."""
    class MockGen:
        def generate(self, context, *, why):
            return GeneratorCandidate(proposed_labels=["veg", "maggi", "paneer"], proposed_value="")

    set_generator_factory(lambda: MockGen())
    try:
        test_cat = CatalogCreateResponse(
            platform="swiggy",
            source_url="https://swiggy.com/test/2",
            extraction_status="ok",
            restaurant_name="Test Rest 2",
            fssai_number="12345678901234",
            restaurant={"name": "Test Rest 2"},
            categories=[
                {
                    "name": "Maggi",
                    "items": [{"name": "Chilli Paneer Maggi", "description": "Spicy Maggi", "price": 80, "food_type": "veg", "labels": []}],
                }
            ],
            item_count=1,
            image_count=0,
        )
        cat_id = save_catalogue(user_id="u_tag2", organization_id="o_tag2", result=test_cat)
        if hasattr(cat_id, "id"):
            cat_id = cat_id.id
        grade_catalogue(user_id="u_tag2", organization_id="o_tag2", catalogue_id=cat_id)

        req = ImprovementLineRequest(check_id="empty_item_labels", paths=["menus[0].categories[0].items[0].labels"])
        prop = create_improvement(user_id="u_tag2", organization_id="o_tag2", catalogue_id=cat_id, request=req)
        
        assert prop.id is not None
        assert prop.catalogue_id == cat_id
        assert prop.status == "READY"
        assert len(prop.lines) == 1
        line = prop.lines[0]
        assert line.path == "menus[0].categories[0].items[0].labels"
        assert line.kind == "labels"
        assert line.status == "READY"
        assert line.proposed_labels == ["veg", "maggi", "paneer"]
    finally:
        set_generator_factory(None)


def test_tag_proposal_does_not_modify_description():
    """Verify that generating a tag proposal does not touch the item description."""
    class MockGen:
        def generate(self, context, *, why):
            return GeneratorCandidate(proposed_labels=["veg", "maggi"], proposed_value="")

    set_generator_factory(lambda: MockGen())
    try:
        test_cat = CatalogCreateResponse(
            platform="swiggy",
            source_url="https://swiggy.com/test/3",
            extraction_status="ok",
            restaurant_name="Test Rest 3",
            fssai_number="12345678901234",
            restaurant={"name": "Test Rest 3"},
            categories=[
                {
                    "name": "Maggi",
                    "items": [{"name": "Chilli Paneer Maggi", "description": "Original Description", "price": 80, "food_type": "veg", "labels": []}],
                }
            ],
            item_count=1,
            image_count=0,
        )
        cat_id = save_catalogue(user_id="u_tag3", organization_id="o_tag3", result=test_cat)
        if hasattr(cat_id, "id"):
            cat_id = cat_id.id
        grade_catalogue(user_id="u_tag3", organization_id="o_tag3", catalogue_id=cat_id)

        req = ImprovementLineRequest(check_id="empty_item_labels", paths=["menus[0].categories[0].items[0].labels"])
        prop = create_improvement(user_id="u_tag3", organization_id="o_tag3", catalogue_id=cat_id, request=req)
        assert len(prop.lines) == 1
        assert prop.lines[0].kind == "labels"
        assert prop.lines[0].proposed_value != "Original Description"
    finally:
        set_generator_factory(None)


def test_tag_proposal_does_not_modify_image():
    """Verify tag proposal lines do not contain media_handoff or image_url changes."""
    class MockGen:
        def generate(self, context, *, why):
            return GeneratorCandidate(proposed_labels=["veg", "maggi"], proposed_value="")

    set_generator_factory(lambda: MockGen())
    try:
        test_cat = CatalogCreateResponse(
            platform="swiggy",
            source_url="https://swiggy.com/test/4",
            extraction_status="ok",
            restaurant_name="Test Rest 4",
            fssai_number="12345678901234",
            restaurant={"name": "Test Rest 4"},
            categories=[
                {
                    "name": "Maggi",
                    "items": [{"name": "Chilli Paneer Maggi", "description": "Desc", "price": 80, "food_type": "veg", "labels": []}],
                }
            ],
            item_count=1,
            image_count=0,
        )
        cat_id = save_catalogue(user_id="u_tag4", organization_id="o_tag4", result=test_cat)
        if hasattr(cat_id, "id"):
            cat_id = cat_id.id
        grade_catalogue(user_id="u_tag4", organization_id="o_tag4", catalogue_id=cat_id)

        req = ImprovementLineRequest(check_id="empty_item_labels", paths=["menus[0].categories[0].items[0].labels"])
        prop = create_improvement(user_id="u_tag4", organization_id="o_tag4", catalogue_id=cat_id, request=req)
        assert len(prop.lines) == 1
        assert prop.lines[0].media_handoff is None
    finally:
        set_generator_factory(None)


def test_failed_tag_generation_exposes_failure_reason():
    """Verify that if tag validation fails, line.status is FAILED and failure_reason is recorded."""
    class FailingGen:
        def generate(self, context, *, why):
            # Output hallucinated ingredient token 'chicken' for a veg context -> CandidateRejected
            return GeneratorCandidate(proposed_labels=["veg", "chicken", "beef"], proposed_value="")

    set_generator_factory(lambda: FailingGen())
    try:
        test_cat = CatalogCreateResponse(
            platform="swiggy",
            source_url="https://swiggy.com/test/5",
            extraction_status="ok",
            restaurant_name="Test Rest 5",
            fssai_number="12345678901234",
            restaurant={"name": "Test Rest 5"},
            categories=[
                {
                    "name": "Maggi",
                    "items": [{"name": "Chilli Paneer Maggi", "description": "Desc", "price": 80, "food_type": "veg", "labels": []}],
                }
            ],
            item_count=1,
            image_count=0,
        )
        cat_id = save_catalogue(user_id="u_tag5", organization_id="o_tag5", result=test_cat)
        if hasattr(cat_id, "id"):
            cat_id = cat_id.id
        grade_catalogue(user_id="u_tag5", organization_id="o_tag5", catalogue_id=cat_id)

        req = ImprovementLineRequest(check_id="empty_item_labels", paths=["menus[0].categories[0].items[0].labels"])
        prop = create_improvement(user_id="u_tag5", organization_id="o_tag5", catalogue_id=cat_id, request=req)
        assert prop.status == "FAILED"
        assert len(prop.lines) == 1
        assert prop.lines[0].status == "FAILED"
        assert prop.lines[0].failure_reason == "hallucinated ingredients"
    finally:
        set_generator_factory(None)


def test_missing_description_grades_f():
    """Verify that an item missing a description produces a missing_description finding."""
    from backend.services.grade_explain_service import get_grade_explanation
    test_cat = CatalogCreateResponse(
        platform="swiggy",
        source_url="https://swiggy.com/test/6",
        extraction_status="ok",
        restaurant_name="Test Rest 6",
        fssai_number="12345678901234",
        restaurant={"name": "Test Rest 6"},
        categories=[
            {
                "name": "Maggi",
                "items": [{"name": "Chilli Paneer Maggi", "description": "", "price": 80, "food_type": "veg", "labels": ["veg"]}],
            }
        ],
        item_count=1,
        image_count=0,
    )
    cat_id = save_catalogue(user_id="u_g1", organization_id="o_g1", result=test_cat)
    if hasattr(cat_id, "id"):
        cat_id = cat_id.id
    grade_catalogue(user_id="u_g1", organization_id="o_g1", catalogue_id=cat_id)
    expl = get_grade_explanation(user_id="u_g1", organization_id="o_g1", catalogue_id=cat_id)
    assert expl is not None
    matching = [f for f in expl.findings if f.check_id == "missing_description"]
    assert len(matching) >= 1


def test_missing_tags_grades_f():
    """Verify that items with empty labels trigger the empty_item_labels driver."""
    from backend.services.grade_explain_service import get_grade_explanation
    test_cat = CatalogCreateResponse(
        platform="swiggy",
        source_url="https://swiggy.com/test/7",
        extraction_status="ok",
        restaurant_name="Test Rest 7",
        fssai_number="12345678901234",
        restaurant={"name": "Test Rest 7"},
        categories=[
            {
                "name": "Maggi",
                "items": [{"name": "Chilli Paneer Maggi", "description": "Delicious Maggi", "price": 80, "food_type": "veg", "labels": []}],
            }
        ],
        item_count=1,
        image_count=0,
    )
    cat_id = save_catalogue(user_id="u_g2", organization_id="o_g2", result=test_cat)
    if hasattr(cat_id, "id"):
        cat_id = cat_id.id
    grade_catalogue(user_id="u_g2", organization_id="o_g2", catalogue_id=cat_id)
    expl = get_grade_explanation(user_id="u_g2", organization_id="o_g2", catalogue_id=cat_id)
    assert expl is not None
    req = ImprovementLineRequest(check_id="empty_item_labels", paths=["menus[0].categories[0].items[0].labels"])
    resolved = resolve_targets(document=doc_from_cat(test_cat), explanation=expl, check_id="empty_item_labels", requested_paths=req.paths)
    assert len(resolved.targets) == 1


def doc_from_cat(cat):
    from backend.canonical.adapter import to_canonical_from_response
    return to_canonical_from_response(cat)


def test_successful_tag_apply_regrades_item():
    """Verify that after applying tags, re-grade updates the item state."""
    class MockGen:
        def generate(self, context, *, why):
            return GeneratorCandidate(proposed_labels=["veg", "maggi", "paneer"], proposed_value="")

    set_generator_factory(lambda: MockGen())
    try:
        test_cat = CatalogCreateResponse(
            platform="swiggy",
            source_url="https://swiggy.com/test/8",
            extraction_status="ok",
            restaurant_name="Test Rest 8",
            fssai_number="12345678901234",
            restaurant={"name": "Test Rest 8"},
            categories=[
                {
                    "name": "Maggi",
                    "items": [{"name": "Chilli Paneer Maggi", "description": "Spicy Maggi", "price": 80, "food_type": "veg", "labels": []}],
                }
            ],
            item_count=1,
            image_count=0,
        )
        cat_id = save_catalogue(user_id="u_apply", organization_id="o_apply", result=test_cat)
        if hasattr(cat_id, "id"):
            cat_id = cat_id.id
        grade_catalogue(user_id="u_apply", organization_id="o_apply", catalogue_id=cat_id)

        req = ImprovementLineRequest(check_id="empty_item_labels", paths=["menus[0].categories[0].items[0].labels"])
        prop = create_improvement(user_id="u_apply", organization_id="o_apply", catalogue_id=cat_id, request=req)
        
        apply_res = apply_improvement(user_id="u_apply", organization_id="o_apply", catalogue_id=cat_id, proposal_id=prop.id)
        assert apply_res.proposal.status == "APPLIED"
        assert "menus[0].categories[0].items[0].labels" in apply_res.applied_paths
    finally:
        set_generator_factory(None)


def test_scrape_continues_after_item_failure():
    """Verify parser/normalizer preserves valid items even if one item has missing fields."""
    cat = CatalogCreateResponse(
        platform="swiggy",
        source_url="https://swiggy.com/test/9",
        extraction_status="ok",
        restaurant_name="Test Rest 9",
        fssai_number="12345678901234",
        restaurant={"name": "Test Rest 9"},
        categories=[
            {
                "name": "Snacks",
                "items": [
                    {"name": "Valid Item", "description": "Good", "price": 100, "labels": ["veg"]},
                    {"name": "Another Valid Item", "description": "Great", "price": 150, "labels": ["veg"]},
                ],
            }
        ],
        item_count=2,
        image_count=0,
    )
    doc = doc_from_cat(cat)
    assert len(doc.menus[0].categories[0].items) == 2


def test_scrape_returns_partial_when_some_items_fail():
    """Verify that a catalogue response with some valid items remains extraction_status 'ok'."""
    cat = CatalogCreateResponse(
        platform="swiggy",
        source_url="https://swiggy.com/test/10",
        extraction_status="ok",
        restaurant_name="Test Rest 10",
        fssai_number="12345678901234",
        restaurant={"name": "Test Rest 10"},
        categories=[
            {
                "name": "Snacks",
                "items": [
                    {"name": "Valid Item", "description": "Good", "price": 100, "labels": ["veg"]},
                ],
            }
        ],
        item_count=1,
        image_count=0,
    )
    assert cat.extraction_status == "ok"
    assert cat.item_count == 1


def test_scrape_does_not_mark_usable_catalogue_failed():
    """Verify that a harvested catalogue with 10 categories and 48 items is marked status 'ok'."""
    cat = CatalogCreateResponse(
        platform="swiggy",
        source_url="https://swiggy.com/test/11",
        extraction_status="ok",
        restaurant_name="Test Rest 11",
        fssai_number="12345678901234",
        restaurant={"name": "Test Rest 11"},
        categories=[{"name": f"Cat {i}", "items": [{"name": f"Item {i}-{j}", "price": 100} for j in range(5)]} for i in range(10)],
        item_count=50,
        image_count=10,
    )
    assert cat.extraction_status == "ok"
    assert len(cat.categories) == 10
    assert cat.item_count == 50


def test_swiggy_multi_category_menu_harvest():
    """Verify that multi-category menus retain all categories during canonical adapter conversion."""
    test_cat = CatalogCreateResponse(
        platform="swiggy",
        source_url="https://swiggy.com/test/12",
        extraction_status="ok",
        restaurant_name="Multi Cat Rest",
        fssai_number="12345678901234",
        restaurant={"name": "Multi Cat Rest"},
        categories=[
            {"name": "Starters", "items": [{"name": "Paneer Tikka", "price": 200}]},
            {"name": "Mains", "items": [{"name": "Paneer Butter Masala", "price": 300}]},
            {"name": "Desserts", "items": [{"name": "Gulab Jamun", "price": 100}]},
        ],
        item_count=3,
        image_count=0,
    )
    doc = doc_from_cat(test_cat)
    assert len(doc.menus[0].categories) == 3
    cat_names = [c.name for c in doc.menus[0].categories]
    assert cat_names == ["Starters", "Mains", "Desserts"]


def test_scrape_error_contains_actual_root_cause():
    """Verify _failed helper contains the actual error string in error field."""
    req = CatalogCreateRequest(
        restaurant_name="Test",
        fssai_number="12345678901234",
        swiggy_url="https://swiggy.com/invalid",
        organization_id="org1",
        platform="swiggy",
    )
    res = _failed(req, error="Playwright page.goto timed out after 45000ms", access_method="BrowserAccess")
    assert res.extraction_status == "failed"
    assert "Playwright page.goto timed out" in res.error
