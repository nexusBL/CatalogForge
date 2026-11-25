"""Tests for Hero Image Editing UX Correction.

Verifies:
1. Catalogue hero path scoping (`path=restaurant.image_url`).
2. Correct target information in Media Studio (`catalogue_id`, restaurant name, hero image URL).
3. Media safety contract: Generate creates candidate but does NOT modify live hero image; Apply updates live hero image.
4. Multi-tenancy / Authorization: another organization cannot access or modify hero image.
5. Existing Media Studio regression: menu item image editing continues working.
6. Grade page regression: grading works without requiring hero image editing steps.
"""

from io import BytesIO
import pytest
from PIL import Image

from backend.main import app
from backend.media.contract import MediaJobRequest
from backend.media.service import (
    apply_media_job,
    create_media_job,
    get_media_studio,
)
from backend.schemas import CatalogCreateResponse
from backend.services.grade_explain_service import get_grade_explanation
from backend.services.grading_service import grade_catalogue
from backend.store import get_catalogue, save_catalogue
from scraper.swiggy.assets import assets_root


def _create_catalogue_asset_png(cat_id: str, filename: str, color: str = "blue") -> str:
    dest_dir = assets_root() / cat_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    file_path = dest_dir / filename
    img = Image.new("RGB", (100, 100), color=color)
    img.save(file_path, format="PNG")
    return f"/catalogue-assets/{cat_id}/{filename}"


@pytest.fixture
def sample_hero_catalogue():
    cat_id = "cat_hero_ux_1"
    user_id = "user_hero_1"
    org_id = "org_hero_1"

    hero_asset_url = _create_catalogue_asset_png(cat_id, "hero.png", color="blue")
    dish_asset_url = _create_catalogue_asset_png(cat_id, "dish.png", color="green")

    cat_data = {
        "id": cat_id,
        "user_id": user_id,
        "organization_id": org_id,
        "extraction_status": "ok",
        "restaurant_name": "Spice Garden",
        "fssai_number": "12345678901234",
        "source_url": "https://www.swiggy.com/restaurants/spice-garden-101",
        "platform": "swiggy",
        "restaurant": {
            "name": "Spice Garden",
            "image_url": hero_asset_url,
        },
        "categories": [
            {
                "name": "Starters",
                "items": [
                    {
                        "name": "Paneer Tikka",
                        "price": 250,
                        "description": "Grilled cottage cheese with aromatic spices",
                        "image_url": dish_asset_url,
                    }
                ],
            }
        ],
    }
    return save_catalogue(
        user_id=user_id,
        organization_id=org_id,
        result=CatalogCreateResponse.model_validate(cat_data),
    )


def test_get_media_studio_hero_scoping(sample_hero_catalogue):
    """Verify Media Studio returns the hero item targeted when path=restaurant.image_url is passed."""
    studio = get_media_studio(
        user_id="user_hero_1",
        organization_id="org_hero_1",
        catalogue_id=sample_hero_catalogue.id,
        path="restaurant.image_url",
    )
    assert studio.catalogue_id == sample_hero_catalogue.id
    assert studio.restaurant_name == "Spice Garden"

    # Find the hero item in items
    hero_item = next((item for item in studio.items if item.path in ("restaurant.image_url", "venue.image_url")), None)
    assert hero_item is not None
    assert hero_item.name == "Spice Garden"
    assert hero_item.image_url == sample_hero_catalogue.result.restaurant["image_url"]
    assert hero_item.has_usable_image is True


def test_hero_image_generate_does_not_modify_live_apply_does(sample_hero_catalogue):
    """Verify Generate creates a candidate without modifying live hero image, and Apply updates live hero image."""
    original_url = sample_hero_catalogue.result.restaurant["image_url"]

    # 1. Generate media job on restaurant.image_url
    job = create_media_job(
        user_id="user_hero_1",
        organization_id="org_hero_1",
        catalogue_id=sample_hero_catalogue.id,
        request=MediaJobRequest(
            path="restaurant.image_url",
            operation="enhance",
            prompt="Make hero photo vibrant and high resolution",
        ),
    )

    assert job.status == "READY"
    assert len(job.candidates) == 1
    candidate_id = job.candidates[0].id

    # VERIFY SAFETY: Saved catalogue in DB STILL has the original hero image
    stored_before = get_catalogue("user_hero_1", sample_hero_catalogue.id, "org_hero_1")
    assert stored_before.result.restaurant["image_url"] == original_url

    # 2. Owner explicitly applies candidate
    res = apply_media_job(
        user_id="user_hero_1",
        organization_id="org_hero_1",
        catalogue_id=sample_hero_catalogue.id,
        job_id=job.id,
        candidate_id=candidate_id,
    )

    assert res.job.status == "APPLIED"
    assert res.catalogue_url.startswith("/catalogue-assets/")

    # VERIFY APPLIED: Live hero image in DB is now updated
    stored_after = get_catalogue("user_hero_1", sample_hero_catalogue.id, "org_hero_1")
    assert stored_after.result.restaurant["image_url"] == res.catalogue_url
    assert stored_after.result.restaurant["image_url"] != original_url


def test_hero_image_authorization_isolation(sample_hero_catalogue):
    """Verify another organization cannot access or modify the restaurant's hero image."""
    with pytest.raises(KeyError):
        get_media_studio(
            user_id="user_hero_2",
            organization_id="org_other",
            catalogue_id=sample_hero_catalogue.id,
            path="restaurant.image_url",
        )

    with pytest.raises(KeyError):
        create_media_job(
            user_id="user_hero_2",
            organization_id="org_other",
            catalogue_id=sample_hero_catalogue.id,
            request=MediaJobRequest(
                path="restaurant.image_url",
                operation="enhance",
            ),
        )


def test_existing_item_image_editing_regression(sample_hero_catalogue):
    """Verify dish item image editing continues working in Media Studio."""
    item_path = "menus[0].categories[0].items[0].image_url"
    studio = get_media_studio(
        user_id="user_hero_1",
        organization_id="org_hero_1",
        catalogue_id=sample_hero_catalogue.id,
        path=item_path,
    )

    dish_item = next((item for item in studio.items if item.path == item_path), None)
    assert dish_item is not None
    assert dish_item.name == "Paneer Tikka"

    job = create_media_job(
        user_id="user_hero_1",
        organization_id="org_hero_1",
        catalogue_id=sample_hero_catalogue.id,
        request=MediaJobRequest(
            path=item_path,
            operation="enhance",
        ),
    )
    assert job.status == "READY"


def test_grade_page_regression(sample_hero_catalogue):
    """Verify Grade / AI Improvements functionality continues working independently."""
    grade_catalogue(user_id="user_hero_1", organization_id="org_hero_1", catalogue_id=sample_hero_catalogue.id)
    explanation = get_grade_explanation(
        user_id="user_hero_1", organization_id="org_hero_1", catalogue_id=sample_hero_catalogue.id
    )
    assert explanation is not None
    assert explanation.overall_grade in {"A", "B", "C", "D", "F"}
