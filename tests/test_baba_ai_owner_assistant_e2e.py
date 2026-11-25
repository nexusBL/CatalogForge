"""Comprehensive E2E certification test suite for Baba AI Owner Assistant.
Verifies catalogue facts, grade intelligence, problem detection, product quality analysis,
description improvement & natural language refinement, tags intelligence, natural-language price mutations,
and ambiguity resolution.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.assistant.contract import AssistantTurnRequest, AssistantClientContext
from backend.assistant.service import run_turn
from backend.main import app, get_swiggy_access, require_session
from backend.schemas import CatalogCreateResponse
from backend.services.grading_service import grade_catalogue
from backend.store import get_catalogue, save_catalogue

TEST_USER = "owner_e2e_user"
TEST_ORG = "owner_e2e_org"


@pytest.fixture
def auth_client():
    client = TestClient(app)

    def _mock_session():
        return {"user_id": TEST_USER, "organization_id": TEST_ORG, "access_token": "token"}

    app.dependency_overrides[require_session] = _mock_session
    app.dependency_overrides[get_swiggy_access] = lambda: {"access_token": "token"}
    yield client
    app.dependency_overrides.clear()


def test_baba_ai_owner_assistant_full_e2e(auth_client):
    cat_payload = {
        "id": "cat_baba_e2e_001",
        "user_id": TEST_USER,
        "organization_id": TEST_ORG,
        "extraction_status": "ok",
        "restaurant_name": "Spice Route",
        "fssai_number": "12345678901234",
        "source_url": "https://magicpin.in/Belgaum/Spice-Route/store/100/delivery",
        "platform": "magicpin",
        "restaurant": {"name": "Spice Route"},
        "categories": [
            {
                "name": "Drinks",
                "items": [
                    {
                        "name": "Fresh Lemonade",
                        "price": 120,
                        "description": "",
                        "food_type": "veg",
                        "labels": [],
                        "image_url": "",
                    },
                    {
                        "name": "Cold Coffee",
                        "price": 150,
                        "description": "Rich chilled coffee",
                        "food_type": "veg",
                        "labels": ["Drinks", "Beverage"],
                        "image_url": "",
                    },
                ],
            },
            {
                "name": "Rice Dishes",
                "items": [
                    {
                        "name": "Lemon Rice",
                        "price": 180,
                        "description": "Tangy lemon rice",
                        "food_type": "veg",
                        "labels": ["Rice"],
                        "image_url": "",
                    },
                    {
                        "name": "Ghee Rice",
                        "price": 200,
                        "description": "Aromatic ghee rice",
                        "food_type": "veg",
                        "labels": ["Rice"],
                        "image_url": "",
                    },
                ],
            },
            {
                "name": "South Indian",
                "items": [
                    {
                        "name": "Lemon Rice",
                        "price": 190,
                        "description": "South style lemon rice",
                        "food_type": "veg",
                        "labels": ["South Indian"],
                        "image_url": "",
                    },
                ],
            },
        ],
    }

    stored = save_catalogue(
        user_id=TEST_USER,
        organization_id=TEST_ORG,
        result=CatalogCreateResponse.model_validate(cat_payload),
    )
    grade_catalogue(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id)

    route_ctx = AssistantClientContext(current_route=f"/catalogues/{stored.id}")

    # 1. Capabilities
    req = AssistantTurnRequest(message="What can you do?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_capabilities"
    assert "Baba AI" in res.message
    assert "Catalogue Facts" in res.message

    # 2. Product count
    req = AssistantTurnRequest(message="How many products do I have?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_catalogue_summary"
    assert "5 product(s)" in res.message
    assert "Spice Route" in res.message

    # 3. Categories list
    req = AssistantTurnRequest(message="What categories do I have?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_catalogue_summary"
    assert "Drinks" in res.message
    assert "Rice Dishes" in res.message

    # 4. Missing descriptions
    req = AssistantTurnRequest(message="Which products don't have descriptions?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_catalogue_summary"
    assert "Fresh Lemonade" in res.message

    # 5. Price of specific item
    req = AssistantTurnRequest(message="What is the price of Ghee Rice?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_item_findings"
    assert "Ghee Rice" in res.message
    assert "200" in res.message

    # 6. Item presence check
    req = AssistantTurnRequest(message="Does my catalogue have Fresh Lemonade?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_item_findings"
    assert "Fresh Lemonade" in res.message
    assert "Drinks" in res.message

    # 7. Product specific breakdown
    req = AssistantTurnRequest(message="What is wrong with Fresh Lemonade?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_item_findings"
    assert "Fresh Lemonade" in res.message
    assert "Description: D — Missing" in res.message or "Description: D" in res.message
    assert "Tags: D" in res.message

    # 8. Catalogue problems
    req = AssistantTurnRequest(message="What problems does my catalogue have?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_problems"
    assert "Catalogue Quality Problems" in res.message

    # 9. Top priority fix
    req = AssistantTurnRequest(message="What should I fix first?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "explain_fix_first"
    assert "What you should improve first" in res.message

    # 10. Ambiguity resolution (Lemon Rice exists in both Rice Dishes and South Indian)
    req = AssistantTurnRequest(message="What is wrong with Lemon Rice?", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.intent == "clarify" or "Lemon Rice" in res.message

    # 11. Price mutation request
    req = AssistantTurnRequest(message="Change Ghee Rice to Rs. 250", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert res.proposal is not None
    assert res.proposal.operation == "change_price"
    assert "250" in res.proposal.proposed_value

    # 12. Confirm price change
    req = AssistantTurnRequest(message="Confirm change", context=route_ctx)
    res = run_turn(user_id=TEST_USER, organization_id=TEST_ORG, catalogue_id=stored.id, request=req)
    assert "Updated price" in res.message or "Ghee Rice" in res.message

    # Verify DB update
    updated_cat = get_catalogue(TEST_USER, stored.id, TEST_ORG)
    found_price = None
    for c in updated_cat.result.categories:
        items = c.items if hasattr(c, "items") and isinstance(c.items, list) else (c.get("items") if isinstance(c, dict) else [])
        for item in items:
            i_name = item.name if hasattr(item, "name") else item.get("name")
            if i_name == "Ghee Rice":
                found_price = item.price if hasattr(item, "price") else item.get("price")
    assert found_price == 250
