from __future__ import annotations

import pytest

from backend.improvement.service import set_generator_factory
from backend.store import get_catalogue, save_catalogue
from tests.test_phase3_grading import _ok_result
from tests.test_phase6_improvement import ScriptedGenerator, _client, _grade, _safe_desc


@pytest.fixture(autouse=True)
def _reset_improvement_generator():
    set_generator_factory(None)
    yield
    set_generator_factory(None)


def test_closed_loop_improve_apply_regrade_compare_rollback():
    set_generator_factory(lambda: ScriptedGenerator([_safe_desc("Ghee Rice")]))
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p12-loop-resta",
            restaurant_id="p12l",
            description="",
        ),
    )
    before_grade = _grade(stored)
    client = _client()
    proposed = client.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "missing_description", "paths": ["menus[0].categories[0].items[0].description"]},
    )
    assert proposed.status_code == 200
    line = proposed.json()["lines"][0]
    assert line.get("current_value") in {"", None}
    assert line["proposed_value"] == _safe_desc("Ghee Rice")
    applied = client.post(
        f"/catalogues/{stored.id}/improvements/{proposed.json()['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert applied.status_code == 200, applied.text
    live = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    assert live["description"] == _safe_desc("Ghee Rice")
    history = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    assert history
    row = history[0]
    assert row["before_grade_score"] == before_grade.score or row["before_grade_score"] is not None
    assert row["after_grade_score"] is not None
    assert row["overall_score_delta"] is not None
    assert row["after_grade_score"] >= row["before_grade_score"]
    rolled = client.post(
        f"/catalogues/{stored.id}/history/{row['id']}/rollback",
        params={"organization_id": "org_1"},
        json={"confirm": True},
    )
    assert rolled.status_code == 200, rolled.text
    restored = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    assert not (restored.get("description") or "").strip()
    later = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    assert later[0]["source"] == "rollback"
    assert later[0]["after_grade_score"] is not None
    assert any(item["id"] == row["id"] for item in later)


def test_media_generate_does_not_replace_until_apply_and_persists_applied():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p12-media-resta",
            restaurant_id="p12m",
            image_url=None,
        ),
    )
    _grade(stored)
    client = _client()
    created = client.post(
        f"/catalogues/{stored.id}/media-jobs",
        params={"organization_id": "org_1"},
        json={"path": "menus[0].categories[0].items[0].image_url", "operation": "generate_image"},
    )
    assert created.status_code == 200, created.text
    job = created.json()
    assert job["status"] == "READY"
    live_before = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0].get("image_url")
    assert not live_before
    fetched = client.get(
        f"/catalogues/{stored.id}/media-jobs/{job['id']}",
        params={"organization_id": "org_1"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "READY"
    applied = client.post(
        f"/catalogues/{stored.id}/media-jobs/{job['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["job"]["status"] == "APPLIED"
    persisted = client.get(
        f"/catalogues/{stored.id}/media-jobs/{job['id']}",
        params={"organization_id": "org_1"},
    )
    assert persisted.status_code == 200
    assert persisted.json()["status"] == "APPLIED"
    live = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0].get("image_url")
    assert live
    history = client.get(f"/catalogues/{stored.id}/history", params={"organization_id": "org_1"}).json()["records"]
    assert any(row["source"] == "media" and row["media_job_id"] == job["id"] for row in history)
