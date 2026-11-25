from __future__ import annotations

import pytest

from backend.assistant.contract import ALLOWED_TOOLS, WRITE_TOOL_NAMES
from backend.assistant.tools import ToolRejected, TurnCache, execute_tool
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


def test_write_tool_names_cannot_execute():
    cache = TurnCache(user_id="user_1", organization_id="org_1", catalogue_id="c1", stored=None)
    for name in ("apply_improvement", "update_catalogue", "rollback_history", "apply_rollback", "rollback_edit"):
        assert name in WRITE_TOOL_NAMES
        assert name not in ALLOWED_TOOLS
        try:
            execute_tool(name, cache)
            raise AssertionError(f"{name} must be rejected")
        except ToolRejected:
            pass


def test_rejected_improvement_does_not_write_catalogue():
    set_generator_factory(lambda: ScriptedGenerator([_safe_desc("Ghee Rice")]))
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/safety-cancel-resta",
            restaurant_id="safc",
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
    cancelled = client.post(
        f"/catalogues/{stored.id}/improvements/{proposed.json()['id']}/cancel",
        params={"organization_id": "org_1"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    item = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    assert not (item.get("description") or "").strip()
    blocked = client.post(
        f"/catalogues/{stored.id}/improvements/{proposed.json()['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert blocked.status_code == 409
    item = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    assert not (item.get("description") or "").strip()


def test_apply_is_idempotent_and_does_not_duplicate_history():
    set_generator_factory(lambda: ScriptedGenerator([_safe_desc("Ghee Rice")]))
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/safety-idem-resta",
            restaurant_id="safi",
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
    first = client.post(
        f"/catalogues/{stored.id}/improvements/{proposed['id']}/apply",
        params={"organization_id": "org_1"},
    )
    second = client.post(
        f"/catalogues/{stored.id}/improvements/{proposed['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["proposal"]["status"] == "APPLIED"
    history = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"})
    assert history.status_code == 200
    records = [row for row in history.json()["records"] if row["proposal_id"] == proposed["id"]]
    assert len(records) == 1


def test_cancelled_mutation_does_not_write():
    stored = _stored(suffix="safmut")
    client = _client()
    before = get_catalogue("user_1", stored.id, "org_1").result.model_dump()
    proposed = _turn(client, stored.id, "Change Ghee Rice to 250 rupees").json()
    cancelled = client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{proposed['proposal']['proposal_id']}/cancel",
        params={"organization_id": "org_1"},
        json={"confirm_token": proposed["proposal"]["confirm_token"]},
    )
    assert cancelled.status_code == 200
    assert get_catalogue("user_1", stored.id, "org_1").result.model_dump() == before
