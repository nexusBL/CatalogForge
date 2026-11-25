from __future__ import annotations

from fastapi.testclient import TestClient

from backend.improvement.service import set_generator_factory
from backend.main import app
from backend.schemas import AuthUser
from backend.session import require_session
from backend.services.grading_service import grade_catalogue
from backend.store import get_catalogue, save_catalogue, update_catalogue
from tests.test_phase3_grading import _ok_result, png_bytes
from tests.test_phase6_improvement import ScriptedGenerator, _client, _grade, _safe_desc, _vision_ok


def test_description_apply_writes_catalogue_and_regrades():
    gen = ScriptedGenerator([_safe_desc("Ghee Rice")])
    set_generator_factory(lambda: gen)
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p11-desc-resta",
            restaurant_id="p11d",
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
    body = proposed.json()
    assert body["lines"][0]["proposed_value"] == _safe_desc("Ghee Rice")
    applied = client.post(
        f"/catalogues/{stored.id}/improvements/{body['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["proposal"]["status"] == "APPLIED"
    item = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    assert item["description"] == _safe_desc("Ghee Rice")
    after_grade = grade_catalogue(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=_vision_ok(),
    )
    assert after_grade.score >= before_grade.score
    replay = client.post(
        f"/catalogues/{stored.id}/improvements/{body['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert replay.status_code == 200
    assert replay.json()["proposal"]["status"] == "APPLIED"


def test_labels_cancel_then_apply():
    gen = ScriptedGenerator([["Mains", "Rice"]])
    set_generator_factory(lambda: gen)
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p11-lab-resta",
            restaurant_id="p11l",
        ),
    )
    _grade(stored)
    client = _client()
    first = client.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "empty_item_labels", "paths": ["menus[0].categories[0].items[0].labels"]},
    )
    assert first.status_code == 200
    cancelled = client.post(
        f"/catalogues/{stored.id}/improvements/{first.json()['id']}/cancel",
        params={"organization_id": "org_1"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    second = client.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "empty_item_labels", "paths": ["menus[0].categories[0].items[0].labels"]},
    )
    applied = client.post(
        f"/catalogues/{stored.id}/improvements/{second.json()['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert applied.status_code == 200, applied.text
    labels = [str(label).casefold() for label in get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0].get("labels") or []]
    assert "vegan" not in labels
    assert labels


def test_stale_and_foreign_org_cannot_apply():
    gen = ScriptedGenerator([_safe_desc("Ghee Rice")])
    set_generator_factory(lambda: gen)
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p11-stale-resta",
            restaurant_id="p11s",
            description="",
        ),
    )
    _grade(stored)
    owner = _client()
    proposed = owner.post(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
        json={"check_id": "missing_description", "paths": ["menus[0].categories[0].items[0].description"]},
    ).json()
    current = get_catalogue("user_1", stored.id, "org_1")
    item = current.result.categories[0]["items"][0]
    mutated = current.result.model_copy(
        update={
            "categories": [
                {**current.result.categories[0], "items": [{**item, "description": "Owner typed this first."}]}
            ]
        }
    )
    update_catalogue(user_id="user_1", catalogue_id=stored.id, organization_id="org_1", result=mutated)
    stale = owner.post(
        f"/catalogues/{stored.id}/improvements/{proposed['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert stale.status_code == 409
    assert get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]["description"] == "Owner typed this first."
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_2", email="x@example.com")
    stranger = TestClient(app)
    blocked = stranger.post(
        f"/catalogues/{stored.id}/improvements/{proposed['id']}/apply",
        params={"organization_id": "org_other"},
    )
    assert blocked.status_code in {403, 404}


def test_media_apply_updates_live_image(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path))
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p11-img-resta",
            restaurant_id="p11i",
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
    applied = client.post(
        f"/catalogues/{stored.id}/media-jobs/{job['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert applied.status_code == 200, applied.text
    url = applied.json()["catalogue_url"]
    assert url.startswith("/catalogue-assets/")
    live = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0].get("image_url")
    assert live == url
    assert (tmp_path / stored.id / url.rsplit("/", 1)[-1]).is_file()


def test_nl_improve_item_creates_proposal_without_applying():
    gen = ScriptedGenerator([_safe_desc("Ghee Rice")])
    set_generator_factory(lambda: gen)
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p11-nl-resta",
            restaurant_id="p11n",
            description="",
        ),
    )
    _grade(stored)
    client = _client()
    before = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0].get("description")
    response = client.post(
        f"/catalogues/{stored.id}/assistant/turn",
        params={"organization_id": "org_1"},
        json={"message": "Improve Ghee Rice"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "open_improvements"
    assert "not live" in body["message"].casefold() or "preview" in body["message"].casefold()
    after = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0].get("description")
    assert after == before
    listed = client.get(
        f"/catalogues/{stored.id}/improvements",
        params={"organization_id": "org_1"},
    )
    assert listed.status_code == 200
    assert listed.json()["proposals"] or listed.json().get("items") or listed.json()


def test_video_apply_updates_live_media(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path))
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/p11-vid-resta",
            restaurant_id="p11v",
            image_url="https://cdn.example/dish.png",
        ),
    )
    _grade(stored)
    monkeypatch.setattr(
        "backend.media.service.load_image_bytes",
        lambda url, catalogue_id=None: png_bytes(80, 80),
    )
    client = _client()
    created = client.post(
        f"/catalogues/{stored.id}/media-jobs",
        params={"organization_id": "org_1"},
        json={
            "path": "menus[0].categories[0].items[0].image_url",
            "operation": "image_to_video",
            "prompt": "Subtle movement around the plated dish.",
        },
    )
    assert created.status_code == 200, created.text
    job = created.json()
    assert job["status"] == "READY"
    applied = client.post(
        f"/catalogues/{stored.id}/media-jobs/{job['id']}/apply",
        params={"organization_id": "org_1"},
    )
    assert applied.status_code == 200, applied.text
    item = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    live = item.get("video_url") or item.get("gif_url") or item.get("image_url")
    assert live
    assert str(live).startswith("/catalogue-assets/") or str(live).startswith("/catalogue-assets/")
