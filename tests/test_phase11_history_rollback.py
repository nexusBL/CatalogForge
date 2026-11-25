from __future__ import annotations

import pytest

from backend.improvement.service import set_generator_factory
from backend.store import get_catalogue, save_catalogue
from tests.test_phase3_grading import _ok_result
from tests.test_phase6_improvement import ScriptedGenerator, _client, _grade, _safe_desc
from tests.test_phase10_mutation import _stored, _turn


@pytest.fixture(autouse=True)
def _reset_improvement_generator():
    set_generator_factory(None)
    yield
    set_generator_factory(None)


def test_improvement_apply_writes_history_and_rollback_restores_previous_value():
    set_generator_factory(lambda: ScriptedGenerator([_safe_desc("Ghee Rice")]))
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p11-hist-resta",
            restaurant_id="p11h",
            description="",
        ),
    )
    _grade(stored)
    client = _client()
    proposed = client.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "missing_description", "paths": ["menus[0].categories[0].items[0].description"]},
    )
    assert proposed.status_code == 200
    proposal_id = proposed.json()["id"]
    applied = client.post(
        f"/catalogues/{stored.id}/improvements/{proposal_id}/apply",
        params={"organization_id": "org_1"},
    )
    assert applied.status_code == 200, applied.text
    item = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    assert item["description"] == _safe_desc("Ghee Rice")
    history = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"})
    assert history.status_code == 200
    records = history.json()["records"]
    assert len(records) == 1
    row = records[0]
    assert row["source"] == "improvement"
    assert row["proposal_id"] == proposal_id
    assert row["previous_value"] in {"", None}
    assert row["new_value"] == _safe_desc("Ghee Rice")
    assert row["actor"] == "user_1"
    refused = client.post(
        f"/catalogues/{stored.id}/history/{row['id']}/rollback",
        params={"organization_id": "org_1"},
        json={"confirm": False},
    )
    assert refused.status_code == 409
    rolled = client.post(
        f"/catalogues/{stored.id}/history/{row['id']}/rollback",
        params={"organization_id": "org_1"},
        json={"confirm": True},
    )
    assert rolled.status_code == 200, rolled.text
    restored = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    assert not (restored.get("description") or "").strip()
    after = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"})
    sources = [item["source"] for item in after.json()["records"]]
    assert sources.count("improvement") == 1
    assert sources.count("rollback") == 1
    assert after.json()["records"][0]["rolled_back_history_id"] == row["id"]
    original = next(item for item in after.json()["records"] if item["id"] == row["id"])
    assert original["previous_value"] in {"", None}
    assert original["new_value"] == _safe_desc("Ghee Rice")


def test_mutation_price_history_and_rollback():
    stored = _stored(suffix="histprice")
    client = _client()
    proposed = _turn(client, stored.id, "Change Ghee Rice to 250 rupees")
    assert proposed.status_code == 200
    body = proposed.json()
    confirmed = client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{body['proposal']['proposal_id']}/confirm",
        params={"organization_id": "org_1"},
        json={"confirm_token": body["proposal"]["confirm_token"]},
    )
    assert confirmed.status_code == 200
    assert get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]["price"] == 250
    history = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    assert history
    row = history[0]
    assert row["source"] == "mutation"
    assert row["operation"] == "change_price"
    rolled = client.post(
        f"/catalogues/{stored.id}/history/{row['id']}/rollback",
        params={"organization_id": "org_1"},
        json={"confirm": True},
    )
    assert rolled.status_code == 200, rolled.text
    assert get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]["price"] == 199
    later = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    assert any(item["source"] == "rollback" for item in later)
    assert any(item["id"] == row["id"] for item in later)


def test_foreign_org_cannot_read_or_rollback_history():
    set_generator_factory(lambda: ScriptedGenerator([_safe_desc("Ghee Rice")]))
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p11-hist-org-resta",
            restaurant_id="p11o",
            description="",
        ),
    )
    _grade(stored)
    client = _client()
    proposed = client.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "missing_description", "paths": ["menus[0].categories[0].items[0].description"]},
    ).json()
    client.post(
        f"/catalogues/{stored.id}/improvements/{proposed['id']}/apply",
        params={"organization_id": "org_1"},
    )
    history = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    foreign = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_other"})
    assert foreign.status_code in {403, 404}
    rollback = client.post(
        f"/catalogues/{stored.id}/history/{history[0]['id']}/rollback",
        params={"organization_id": "org_other"},
        json={"confirm": True},
    )
    assert rollback.status_code in {403, 404}


def test_all_mutation_types_rollback():
    stored = _stored(suffix="histallmut")
    client = _client()

    # 1. Rename item and rollback
    proposed = _turn(client, stored.id, "Rename Ghee Rice to Royal Ghee Rice")
    assert proposed.status_code == 200
    prop_id = proposed.json()["proposal"]["proposal_id"]
    token = proposed.json()["proposal"]["confirm_token"]
    client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{prop_id}/confirm",
        params={"organization_id": "org_1"},
        json={"confirm_token": token},
    )
    assert get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]["name"] == "Royal Ghee Rice"

    history = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    row_rename = history[0]
    assert row_rename["operation"] == "rename_item"

    rolled_rename = client.post(
        f"/catalogues/{stored.id}/history/{row_rename['id']}/rollback",
        params={"organization_id": "org_1"},
        json={"confirm": True},
    )
    assert rolled_rename.status_code == 200, rolled_rename.text
    assert get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]["name"] == "Ghee Rice"

    # 2. Add item and rollback
    proposed_add = _turn(client, stored.id, "Add Jeera Rice for 150 to Mains")
    assert proposed_add.status_code == 200, proposed_add.text
    body_add = proposed_add.json()
    assert body_add.get("proposal"), body_add
    prop_id = body_add["proposal"]["proposal_id"]
    token = body_add["proposal"]["confirm_token"]
    client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{prop_id}/confirm",
        params={"organization_id": "org_1"},
        json={"confirm_token": token},
    )
    items_after_add = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"]
    assert any(item["name"] == "Jeera Rice" for item in items_after_add)

    history_add = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    row_add = history_add[0]
    assert row_add["operation"] == "add_item"

    rolled_add = client.post(
        f"/catalogues/{stored.id}/history/{row_add['id']}/rollback",
        params={"organization_id": "org_1"},
        json={"confirm": True},
    )
    assert rolled_add.status_code == 200, rolled_add.text
    items_after_add_rollback = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"]
    assert not any(item["name"] == "Jeera Rice" for item in items_after_add_rollback)

    # 3. Remove item and rollback
    proposed_rem = _turn(client, stored.id, "Remove Ghee Rice")
    assert proposed_rem.status_code == 200
    prop_id = proposed_rem.json()["proposal"]["proposal_id"]
    token = proposed_rem.json()["proposal"]["confirm_token"]
    client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{prop_id}/confirm",
        params={"organization_id": "org_1"},
        json={"confirm_token": token},
    )
    items_after_rem = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"]
    assert not any(item["name"] == "Ghee Rice" for item in items_after_rem)

    history_rem = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    row_rem = history_rem[0]
    assert row_rem["operation"] == "remove_item"

    rolled_rem = client.post(
        f"/catalogues/{stored.id}/history/{row_rem['id']}/rollback",
        params={"organization_id": "org_1"},
        json={"confirm": True},
    )
    assert rolled_rem.status_code == 200, rolled_rem.text
    items_after_rem_rollback = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"]
    assert any(item["name"] == "Ghee Rice" for item in items_after_rem_rollback)

