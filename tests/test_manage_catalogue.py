from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.mutation.contract import OwnerCatalogueMutationRequest
from backend.mutation.service import _cas_identity
from backend.schemas import AuthUser
from backend.session import require_session
from backend.store import get_catalogue, save_catalogue, update_catalogue
from tests.test_phase3_grading import _ok_result


def _client(user_id: str = "user_1") -> TestClient:
    app.dependency_overrides[require_session] = lambda: AuthUser(id=user_id, email="o@example.com")
    return TestClient(app)


def _stored(*, suffix: str, org: str = "org_1"):
    return save_catalogue(
        user_id="user_1",
        organization_id=org,
        result=_ok_result(
            source_url=f"https://www.swiggy.com/city/sample/manage-{suffix}-resta",
            restaurant_id=f"mg{suffix}"[:12],
        ),
    )


def _identity(catalogue_id: str, stored):
    revision, state_hash = _cas_identity(catalogue_id, stored.result)
    return revision, state_hash


def _apply(client: TestClient, catalogue_id: str, body: dict, org: str = "org_1"):
    return client.post(
        f"/catalogues/{catalogue_id}/catalogue-mutations",
        params={"organization_id": org},
        json=body,
    )


def _price(stored_id: str) -> object:
    return get_catalogue("user_1", stored_id, "org_1").result.categories[0]["items"][0]["price"]


def test_owner_add_item():
    stored = _stored(suffix="add")
    revision, state_hash = _identity(stored.id, stored)
    client = _client()
    before_count = stored.result.item_count
    response = _apply(
        client,
        stored.id,
        {
            "source_head_revision": revision,
            "source_state_hash": state_hash,
            "draft": {
                "operation": "add_item",
                "item_name": "Filter Coffee",
                "category_name": "Mains",
                "price": 90,
                "description": "Hot filter coffee.",
            },
        },
    )
    assert response.status_code == 200
    after = get_catalogue("user_1", stored.id, "org_1")
    assert after is not None
    assert after.result.item_count == before_count + 1
    names = [item["name"] for cat in after.result.categories for item in cat.get("items", [])]
    assert "Filter Coffee" in names


def test_owner_change_price():
    stored = _stored(suffix="price")
    revision, state_hash = _identity(stored.id, stored)
    client = _client()
    item = stored.result.categories[0]["items"][0]
    item_id = str(item.get("item_id") or item.get("id") or "")
    response = _apply(
        client,
        stored.id,
        {
            "source_head_revision": revision,
            "source_state_hash": state_hash,
            "item_id": item_id or None,
            "draft": {
                "operation": "change_price",
                "item_name": item["name"],
                "category_name": stored.result.categories[0]["name"],
                "price": 275,
            },
        },
    )
    assert response.status_code == 200
    assert _price(stored.id) == 275


def test_owner_remove_item():
    stored = _stored(suffix="remove")
    revision, state_hash = _identity(stored.id, stored)
    client = _client()
    item = stored.result.categories[0]["items"][0]
    before = stored.result.item_count
    response = _apply(
        client,
        stored.id,
        {
            "source_head_revision": revision,
            "source_state_hash": state_hash,
            "draft": {
                "operation": "remove_item",
                "item_name": item["name"],
                "category_name": stored.result.categories[0]["name"],
            },
        },
    )
    assert response.status_code == 200
    after = get_catalogue("user_1", stored.id, "org_1")
    assert after.result.item_count == before - 1


def test_owner_mutation_rejects_stale_revision():
    stored = _stored(suffix="stale")
    revision, state_hash = _identity(stored.id, stored)
    client = _client()
    item = stored.result.categories[0]["items"][0]
    mutated = stored.result.model_copy(
        update={
            "categories": [
                {
                    **stored.result.categories[0],
                    "items": [{**item, "price": 175}],
                }
            ]
        }
    )
    update_catalogue(user_id="user_1", catalogue_id=stored.id, organization_id="org_1", result=mutated)
    assert _price(stored.id) == 175
    response = _apply(
        client,
        stored.id,
        {
            "source_head_revision": revision,
            "source_state_hash": state_hash,
            "draft": {
                "operation": "change_price",
                "item_name": item["name"],
                "category_name": stored.result.categories[0]["name"],
                "price": 250,
            },
        },
    )
    assert response.status_code == 409
    assert _price(stored.id) == 175


def test_owner_mutation_succeeds_when_revision_matches():
    stored = _stored(suffix="fresh")
    revision, state_hash = _identity(stored.id, stored)
    client = _client()
    item = stored.result.categories[0]["items"][0]
    response = _apply(
        client,
        stored.id,
        {
            "source_head_revision": revision,
            "source_state_hash": state_hash,
            "draft": {
                "operation": "change_price",
                "item_name": item["name"],
                "category_name": stored.result.categories[0]["name"],
                "price": 240,
            },
        },
    )
    assert response.status_code == 200
    assert _price(stored.id) == 240
    body = response.json()
    assert body["head_revision"] == revision + 1


def test_owner_mutation_rejects_foreign_org():
    stored = _stored(suffix="auth")
    revision, state_hash = _identity(stored.id, stored)
    client = _client()
    response = _apply(
        client,
        stored.id,
        {
            "source_head_revision": revision,
            "source_state_hash": state_hash,
            "draft": {
                "operation": "change_price",
                "item_name": stored.result.categories[0]["items"][0]["name"],
                "category_name": stored.result.categories[0]["name"],
                "price": 200,
            },
        },
        org="org_other",
    )
    assert response.status_code in {403, 404}


def test_owner_mutation_contract_validates():
    OwnerCatalogueMutationRequest.model_validate(
        {
            "source_head_revision": 1,
            "source_state_hash": "abc123",
            "draft": {
                "operation": "add_item",
                "item_name": "Tea",
                "category_name": "Mains",
                "price": 50,
            },
        }
    )
