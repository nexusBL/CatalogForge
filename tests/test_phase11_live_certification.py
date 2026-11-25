import time
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas import AuthUser, CatalogCreateResponse
from backend.services.grading_service import grade_catalogue
from backend.session import require_session
from backend.store import get_catalogue, save_catalogue
from backend.improvement.service import set_generator_factory
from backend.improvement.validate import validate_candidate, CandidateRejected
from backend.improvement.contract import GeneratorCandidate
from scraper.swiggy.models import RawSource
from scraper.zomato.parser import parse_zomato_catalogue
from tests.test_phase6_improvement import ScriptedGenerator, _client, _vision_ok

ZOMATO_BREW59_HTML = """
<html>
<body>
  <h1>Brew 59</h1>
  <p>Sadashiv Nagar, Belgaum</p>
</body>
</html>
"""

ZOMATO_BREW59_TEXT = """
Brew 59
Sadashiv Nagar, Belgaum
Drinks (5)
Starters (10)
Search within menu
Drinks
Fresh Lemonade
₹120
Chilled refreshing lemon drink
Starters
Paneer Tikka
₹249
Tandoori cottage cheese
"""


def test_live_owner_workflow_brew59_fresh_lemonade():
    # 1. SCRAPE / INGESTION
    raw = RawSource(
        source_url="https://www.zomato.com/belgaum/brew-59-sadashiv-nagar",
        access_status="ok",
        html=ZOMATO_BREW59_HTML,
        page_text=ZOMATO_BREW59_TEXT,
    )
    parsed = parse_zomato_catalogue(raw)
    assert parsed.extraction_status == "ok"
    assert parsed.restaurant.name == "Brew 59"
    assert parsed.item_count >= 2

    # Find Fresh Lemonade
    lemonade_item = None
    for category in parsed.categories:
        for item in category.items:
            if item.name == "Fresh Lemonade":
                lemonade_item = item
                break
    assert lemonade_item is not None
    assert lemonade_item.price == 120

    # Construct CatalogCreateResponse
    result_dict = parsed.to_dict()
    categories_list = result_dict.get("categories", [])
    for cat in categories_list:
        for item in cat.get("items", []):
            if item["name"] == "Fresh Lemonade":
                item["description"] = ""
                item["labels"] = []

    create_resp = CatalogCreateResponse(
        extraction_status="ok",
        source_type=parsed.source_type,
        restaurant_name="Brew 59",
        fssai_number="12345678901234",
        source_url="https://www.zomato.com/belgaum/brew-59-sadashiv-nagar",
        platform="zomato",
        catalogue_type="restaurant",
        restaurant=result_dict.get("restaurant"),
        categories=categories_list,
        item_count=sum(len(c.get("items", [])) for c in categories_list),
        image_count=parsed.image_count,
    )
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=create_resp,
    )
    assert stored.id is not None

    client = _client()

    # 2. CATALOGUE VIEW CLEANLINESS
    cat_resp = client.get(f"/catalogues/{stored.id}", params={"organization_id": "org_1"})
    assert cat_resp.status_code == 200
    cat_data = cat_resp.json()
    assert cat_data["result"]["restaurant_name"] == "Brew 59"
    assert len(cat_data["result"]["categories"]) > 0
    # Catalogue endpoint response contains catalogue data only, no grade dashboard
    assert "overall_grade" not in cat_data["result"]

    # 3. INITIAL GRADE & QUALITY EXPLANATION
    initial_grade = grade_catalogue(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=_vision_ok(),
    )
    assert initial_grade.grade is not None

    expl_resp = client.get(f"/catalogues/{stored.id}/grade-explanation", params={"organization_id": "org_1"})
    assert expl_resp.status_code == 200
    expl = expl_resp.json()
    assert expl["overall_grade"] in ["A", "B", "C", "D", "F"]

    # Verify missing description finding exists
    desc_findings = [f for f in expl["findings"] if f["check_id"] == "missing_description"]
    assert len(desc_findings) > 0

    # 4. FRESH LEMONADE DESCRIPTION IMPROVEMENT (AI PROPOSAL)
    gen = ScriptedGenerator(["Fresh Lemonade in Drinks."])
    set_generator_factory(lambda: gen)

    desc_path = "menus[0].categories[0].items[0].description"
    t0 = time.time()
    prop_resp = client.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "missing_description", "paths": [desc_path]},
    )
    t_elapsed = time.time() - t0
    assert t_elapsed < 1.0  # Fast response (< 1s)
    assert prop_resp.status_code == 200
    proposal = prop_resp.json()
    assert proposal["status"] == "READY"
    line = proposal["lines"][0]
    assert line["status"] == "READY"

    # 5. INSPECT THE ACTUAL AI OUTPUT PROSE
    proposed_text = line["proposed_value"]
    print("PROPOSED DESCRIPTION:", proposed_text)
    assert proposed_text == "Fresh Lemonade in Drinks."
    # Inspection checks:
    assert "Fresh Lemonade" in proposed_text
    assert len(proposed_text) < 100
    assert not any(claim in proposed_text.lower() for claim in ["organic", "vegan", "sugar-free", "gluten-free"])

    # 6. REPLACE WITH THIS (APPLY DESCRIPTION)
    apply_resp = client.post(
        f"/catalogues/{stored.id}/improvements/{proposal['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["proposal"]["status"] == "APPLIED"

    # Verify Persistence after Reload
    reloaded = get_catalogue("user_1", stored.id, "org_1")
    updated_item = reloaded.result.categories[0]["items"][0]
    assert updated_item["name"] == "Fresh Lemonade"
    assert updated_item["description"] == "Fresh Lemonade in Drinks."

    # Verify Re-grade
    new_grade = grade_catalogue(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=_vision_ok(),
    )
    assert new_grade.score >= initial_grade.score

    # 7. TAG IMPROVEMENT & REPLACE & PERSIST
    gen_tags = ScriptedGenerator([["Drinks", "Beverage"]])
    set_generator_factory(lambda: gen_tags)

    tag_path = "menus[0].categories[0].items[0].labels"
    tag_prop_resp = client.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "empty_item_labels", "paths": [tag_path]},
    )
    assert tag_prop_resp.status_code == 200
    tag_proposal = tag_prop_resp.json()
    assert tag_proposal["status"] == "READY"

    tag_apply_resp = client.post(
        f"/catalogues/{stored.id}/improvements/{tag_proposal['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert tag_apply_resp.status_code == 200

    # Reload & verify tags
    reloaded_tags = get_catalogue("user_1", stored.id, "org_1")
    tagged_item = reloaded_tags.result.categories[0]["items"][0]
    assert "drinks" in [str(lbl).lower() for lbl in (tagged_item.get("labels") or [])]

    # 8. IMAGE IMPROVEMENT & MEDIA JOB APPLY
    media_resp = client.post(
        f"/catalogues/{stored.id}/media-jobs",
        params={"organization_id": "org_1"},
        json={"path": "menus[0].categories[0].items[0].image_url", "operation": "generate_image"},
    )
    assert media_resp.status_code == 200
    job = media_resp.json()
    assert job["status"] == "READY"
    assert len(job["candidates"]) > 0

    media_apply_resp = client.post(
        f"/catalogues/{stored.id}/media-jobs/{job['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert media_apply_resp.status_code == 200
    new_media_url = media_apply_resp.json()["catalogue_url"]
    assert new_media_url.startswith("/catalogue-assets/")

    # Reload and verify live media updated on Fresh Lemonade
    reloaded_media = get_catalogue("user_1", stored.id, "org_1")
    image_item = reloaded_media.result.categories[0]["items"][0]
    assert image_item["image_url"] == new_media_url

    # 9. CANCEL TEST
    gen_cancel = ScriptedGenerator(["Fresh chilled lemonade."])
    set_generator_factory(lambda: gen_cancel)
    cancel_prop = client.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "missing_description", "paths": ["menus[0].categories[0].items[1].description"]},
    ).json()
    cancel_resp = client.post(
        f"/catalogues/{stored.id}/improvements/{cancel_prop['id']}/cancel",
        params={"organization_id": "org_1"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    # 9. IDEMPOTENT REPLAY TEST
    replay_resp = client.post(
        f"/catalogues/{stored.id}/improvements/{proposal['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json()["proposal"]["status"] == "APPLIED"
