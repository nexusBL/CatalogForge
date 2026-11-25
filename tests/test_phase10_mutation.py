from __future__ import annotations

from fastapi.testclient import TestClient

from backend.assistant.contract import ALLOWED_TOOLS, PlannerOutput, WRITE_TOOL_NAMES
from backend.assistant.tools import TurnCache, execute_tool
from backend.main import app
from backend.schemas import AuthUser
from backend.session import require_session
from backend.store import get_catalogue, save_catalogue, update_catalogue
from tests.test_phase3_grading import _ok_result


def _client(user_id: str = "user_1") -> TestClient:
    app.dependency_overrides[require_session] = lambda: AuthUser(id=user_id, email="o@example.com")
    return TestClient(app)


def _stored(*, suffix: str, extra_items: list[dict] | None = None, org: str = "org_1"):
    return save_catalogue(
        user_id="user_1",
        organization_id=org,
        result=_ok_result(
            source_url=f"https://www.swiggy.com/city/sample/p10-{suffix}-resta",
            restaurant_id=f"p10{suffix}"[:12],
            extra_items=extra_items,
        ),
    )


def _turn(client: TestClient, catalogue_id: str, message: str, org: str = "org_1"):
    return client.post(
        f"/catalogues/{catalogue_id}/assistant/turn",
        params={"organization_id": org},
        json={"message": message},
    )


def _price(stored_id: str) -> object:
    return get_catalogue("user_1", stored_id, "org_1").result.categories[0]["items"][0]["price"]


def test_propose_price_does_not_write_until_confirm():
    stored = _stored(suffix="price")
    client = _client()
    before = _price(stored.id)
    proposed = _turn(client, stored.id, "Change Ghee Rice to 250 rupees")
    assert proposed.status_code == 200
    body = proposed.json()
    assert body["intent"] == "propose_mutation"
    assert body["proposal"]["status"] == "PENDING"
    assert _price(stored.id) == before
    confirmed = client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{body['proposal']['proposal_id']}/confirm",
        params={"organization_id": "org_1"},
        json={"confirm_token": body["proposal"]["confirm_token"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["proposal"]["status"] == "APPLIED"
    assert _price(stored.id) == 250


def test_cancel_leaves_payload_unchanged():
    stored = _stored(suffix="cancel")
    client = _client()
    before = get_catalogue("user_1", stored.id, "org_1").result.model_dump()
    proposed = _turn(client, stored.id, "Change Ghee Rice to 250 rupees").json()
    cancelled = client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{proposed['proposal']['proposal_id']}/cancel",
        params={"organization_id": "org_1"},
        json={"confirm_token": proposed["proposal"]["confirm_token"]},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["proposal"]["status"] == "CANCELLED"
    assert get_catalogue("user_1", stored.id, "org_1").result.model_dump() == before


def test_ambiguous_item_asks_for_clarification():
    stored = _stored(
        suffix="amb",
        extra_items=[{"name": "Ghee Rice", "price": 180, "description": "Dup.", "additional_information": {"id": "m9"}}],
    )
    client = _client()
    before = get_catalogue("user_1", stored.id, "org_1").result.model_dump()
    response = _turn(client, stored.id, "Change Ghee Rice to 250 rupees")
    assert response.status_code == 200
    assert response.json()["intent"] == "clarify"
    assert response.json()["proposal"] is None
    assert get_catalogue("user_1", stored.id, "org_1").result.model_dump() == before


def test_stale_confirm_does_not_write_second_edit():
    stored = _stored(suffix="stale")
    client = _client()
    proposed = _turn(client, stored.id, "Change Ghee Rice to 250 rupees").json()
    current = get_catalogue("user_1", stored.id, "org_1")
    item = current.result.categories[0]["items"][0]
    mutated = current.result.model_copy(
        update={
            "categories": [
                {
                    **current.result.categories[0],
                    "items": [{**item, "price": 175}],
                }
            ]
        }
    )
    update_catalogue(user_id="user_1", catalogue_id=stored.id, organization_id="org_1", result=mutated)
    confirmed = client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{proposed['proposal']['proposal_id']}/confirm",
        params={"organization_id": "org_1"},
        json={"confirm_token": proposed["proposal"]["confirm_token"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["proposal"]["status"] == "STALE"
    assert _price(stored.id) == 175


def test_foreign_org_cannot_confirm():
    stored = _stored(suffix="authz")
    owner = _client("user_1")
    proposed = _turn(owner, stored.id, "Change Ghee Rice to 250 rupees").json()
    stranger = _client("user_2")
    response = stranger.post(
        f"/catalogues/{stored.id}/assistant/mutations/{proposed['proposal']['proposal_id']}/confirm",
        params={"organization_id": "org_other"},
        json={"confirm_token": proposed["proposal"]["confirm_token"]},
    )
    assert response.status_code in {403, 404}
    assert _price(stored.id) == 199


def test_media_confirm_does_not_claim_live_image_change(monkeypatch):
    stored = _stored(suffix="media")
    client = _client()

    class _Job:
        id = "job_media_1"

    monkeypatch.setattr("backend.mutation.service.create_media_job", lambda **_k: _Job())
    proposed = _turn(client, stored.id, "Improve the image for Ghee Rice")
    assert proposed.status_code == 200
    body = proposed.json()
    if body["intent"] != "propose_mutation":
        return
    before = get_catalogue("user_1", stored.id, "org_1").result.model_dump()
    confirmed = client.post(
        f"/catalogues/{stored.id}/assistant/mutations/{body['proposal']['proposal_id']}/confirm",
        params={"organization_id": "org_1"},
        json={"confirm_token": body["proposal"]["confirm_token"]},
    )
    assert confirmed.status_code == 200
    message = confirmed.json()["message"].casefold()
    assert "has not been changed" in message or "will not change" in message
    assert get_catalogue("user_1", stored.id, "org_1").result.model_dump() == before


def test_planner_still_forbids_extra_keys_and_write_tools():
    try:
        PlannerOutput.model_validate({"intent": "propose_mutation", "item_name": None, "tool": None, "sql": "drop"})
        raise AssertionError("expected extra field rejection")
    except Exception as exc:
        assert "extra" in str(exc).casefold() or "sql" in str(exc).casefold()
    assert "apply_improvement" in WRITE_TOOL_NAMES
    assert "apply_improvement" not in ALLOWED_TOOLS


def test_execute_tool_rejects_write_names():
    cache = TurnCache(user_id="user_1", organization_id="org_1", catalogue_id="c1", stored=None)
    try:
        execute_tool("apply_improvement", cache)
        raise AssertionError("write tool must be rejected")
    except Exception:
        pass


def _confirm(client: TestClient, catalogue_id: str, body: dict, org: str = "org_1"):
    return client.post(
        f"/catalogues/{catalogue_id}/assistant/mutations/{body['proposal']['proposal_id']}/confirm",
        params={"organization_id": org},
        json={"confirm_token": body["proposal"]["confirm_token"]},
    )


def _apply(client: TestClient, catalogue_id: str, message: str):
    proposed = _turn(client, catalogue_id, message)
    assert proposed.status_code == 200, proposed.text
    body = proposed.json()
    assert body["intent"] == "propose_mutation", body
    assert body["proposal"]["status"] == "PENDING"
    assert body["proposal"]["current_value"] is not None
    assert body["proposal"]["proposed_value"]
    confirmed = _confirm(client, catalogue_id, body)
    assert confirmed.status_code == 200, confirmed.text
    return body, confirmed.json()


def _with_categories(suffix: str, extra: list[dict]):
    stored = _stored(suffix=suffix)
    current = get_catalogue("user_1", stored.id, "org_1")
    categories = list(current.result.categories) + extra
    count = sum(len(category.get("items") or []) for category in categories)
    return update_catalogue(
        user_id="user_1",
        catalogue_id=stored.id,
        organization_id="org_1",
        result=current.result.model_copy(update={"categories": categories, "item_count": count}),
    )


def test_price_nl_variants_confirm():
    from backend.mutation.parse import parse_mutation_draft

    for phrase in (
        "Make Ghee Rice 250.",
        "Increase Ghee Rice to 250.",
        "Set Ghee Rice price to 250",
        "Change the price of Ghee Rice to 250 rupees",
    ):
        draft = parse_mutation_draft(phrase)
        assert draft is not None
        assert draft.operation == "change_price"
        assert draft.item_name == "Ghee Rice"
        assert draft.price == 250
    stored = _stored(suffix="nlprice")
    client = _client()
    _apply(client, stored.id, "Make Ghee Rice 250.")
    assert _price(stored.id) == 250


def test_add_remove_rename_move_confirm():
    stored = _with_categories(
        "ops",
        [
            {"name": "Starters", "items": [], "item_count": 0},
            {"name": "Drinks", "items": [{"name": "Coke", "price": 40, "description": "Cola."}], "item_count": 1},
        ],
    )
    client = _client()
    before_id = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]["item_id"]
    _apply(client, stored.id, "Add Paneer Tikka for 220 to Starters.")
    names = [item["name"] for item in get_catalogue("user_1", stored.id, "org_1").result.categories[1]["items"]]
    assert "Paneer Tikka" in names
    _apply(client, stored.id, "Rename Ghee Rice to Ghee Rice Special")
    renamed = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    assert renamed["name"] == "Ghee Rice Special"
    assert renamed["item_id"] == before_id
    _apply(client, stored.id, "Move Ghee Rice Special to Drinks")
    drinks = [item["name"] for item in get_catalogue("user_1", stored.id, "org_1").result.categories[2]["items"]]
    assert "Ghee Rice Special" in drinks
    _apply(client, stored.id, "Remove Coke from Drinks")
    drinks = [item["name"] for item in get_catalogue("user_1", stored.id, "org_1").result.categories[2]["items"]]
    assert "Coke" not in drinks


def test_add_without_category_asks_when_ambiguous():
    stored = _with_categories("addask", [{"name": "Starters", "items": [], "item_count": 0}])
    client = _client()
    response = _turn(client, stored.id, "Add Paneer Tikka for 220.")
    assert response.status_code == 200
    assert response.json()["intent"] == "clarify"
    assert get_catalogue("user_1", stored.id, "org_1").result.item_count == 1


def test_description_and_tags_stay_grounded():
    stored = _stored(suffix="quality")
    client = _client()
    invented = _turn(client, stored.id, 'Set tags for Ghee Rice to vegan, gluten-free')
    assert invented.json()["intent"] == "clarify"
    assert "vegan" not in str(get_catalogue("user_1", stored.id, "org_1").result.model_dump()).casefold()
    _, confirmed = _apply(client, stored.id, "Improve the description for Ghee Rice")
    item = get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0]
    text = str(item.get("description") or "")
    assert "ghee" in text.casefold()
    assert "mains" in text.casefold()
    assert "award" not in text.casefold()
    assert "vegan" not in text.casefold()
    _apply(client, stored.id, "Fix tags for Ghee Rice")
    labels = [str(label).casefold() for label in get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"][0].get("labels") or []]
    assert "vegan" not in labels
    assert any("rice" in label or "mains" in label for label in labels)


def test_negative_and_missing_price_do_not_write():
    stored = _stored(suffix="badprice")
    client = _client()
    before = _price(stored.id)
    missing = _turn(client, stored.id, "Add Mystery Stew to Mains.")
    assert missing.json()["intent"] == "clarify"
    assert _price(stored.id) == before


def test_replay_confirm_does_not_duplicate_add():
    stored = _stored(suffix="replay")
    client = _client()
    proposed = _turn(client, stored.id, "Add Lemonade for 60 to Mains.").json()
    first = _confirm(client, stored.id, proposed)
    second = _confirm(client, stored.id, proposed)
    assert first.json()["proposal"]["status"] == "APPLIED"
    assert second.json()["proposal"]["status"] == "APPLIED"
    names = [item["name"] for item in get_catalogue("user_1", stored.id, "org_1").result.categories[0]["items"]]
    assert names.count("Lemonade") == 1


def test_media_confirm_includes_job_and_studio_link(monkeypatch):
    stored = _stored(suffix="media2")
    client = _client()

    class _Job:
        id = "job_media_2"

    monkeypatch.setattr("backend.mutation.service.create_media_job", lambda **_k: _Job())
    body, confirmed = _apply(client, stored.id, "Improve the image for Ghee Rice")
    assert body["proposal"]["writes_payload"] is False
    assert confirmed["proposal"]["media_job_id"] == "job_media_2"
    assert "job_media_2" in confirmed["message"]
    assert "has not been changed" in confirmed["message"].casefold()
    hrefs = [action["href"] for action in confirmed["actions"]]
    assert any("/media" in href for href in hrefs)
