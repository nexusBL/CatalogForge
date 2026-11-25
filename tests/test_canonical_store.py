from __future__ import annotations

import sqlite3

import pytest

from backend.schemas import CatalogCreateResponse
from backend.store import CatalogueIdentityConflict, catalogue_db_path, list_catalogues, matching_catalogue_id, save_catalogue


def _ok(*, source_url: str, platform: str = "swiggy", restaurant_id: str | None = None, price: int = 100, name: str = "Rice"):
    restaurant = {"name": "Harbor Spice House"}
    if restaurant_id:
        restaurant["restaurant_id"] = restaurant_id
    return CatalogCreateResponse(
        extraction_status="ok",
        restaurant_name="Harbor Spice House",
        fssai_number="12345678901234",
        source_url=source_url,
        platform=platform,  # type: ignore[arg-type]
        catalogue_type="restaurant",
        restaurant=restaurant,
        categories=[{"name": "Mains", "items": [{"name": name, "price": price, "additional_information": {"id": "m1"}}]}],
        item_count=1,
    )


def _revision_count(catalogue_id: str) -> int:
    connection = sqlite3.connect(catalogue_db_path())
    try:
        row = connection.execute("SELECT COUNT(*) FROM catalogue_revisions WHERE catalogue_id = ?", (catalogue_id,)).fetchone()
        return int(row[0])
    finally:
        connection.close()


def test_identical_reingest_is_noop_without_revision():
    url = "https://www.swiggy.com/city/sample/price-stable-resta"
    first = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, restaurant_id="s1", price=100))
    second = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, restaurant_id="s1", price=100))
    assert first.id == second.id
    assert first.result.venue_id == second.result.venue_id
    assert len(list_catalogues("user-1", "org_1")) == 1
    assert _revision_count(first.id) == 0
    assert first.result.categories[0]["items"][0]["item_id"] == second.result.categories[0]["items"][0]["item_id"]


def test_price_change_updates_and_creates_revision():
    url = "https://www.swiggy.com/city/sample/price-change-resta"
    first = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, restaurant_id="s2", price=100))
    second = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, restaurant_id="s2", price=110))
    assert first.id == second.id
    assert first.result.venue_id == second.result.venue_id
    assert second.result.categories[0]["items"][0]["price"] == 110
    assert _revision_count(first.id) == 1
    assert first.result.categories[0]["items"][0]["item_id"] == second.result.categories[0]["items"][0]["item_id"]


def test_different_platforms_get_different_venues():
    url = "https://www.swiggy.com/city/sample/shared-url-resta"
    first = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, platform="swiggy", restaurant_id="1"))
    second = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, platform="zomato", restaurant_id="1"))
    assert first.id != second.id
    assert first.result.venue_id != second.result.venue_id


def test_item_without_source_id_need_not_keep_uuid():
    url = "https://www.swiggy.com/city/sample/no-item-id-resta"
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name="Harbor Spice House",
            fssai_number="12345678901234",
            source_url=url,
            restaurant={"name": "Harbor Spice House", "restaurant_id": "n1"},
            categories=[{"name": "Mains", "items": [{"name": "Rice", "price": 100}]}],
            item_count=1,
        ),
    )
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name="Harbor Spice House",
            fssai_number="12345678901234",
            source_url=url,
            restaurant={"name": "Harbor Spice House", "restaurant_id": "n1"},
            categories=[{"name": "Mains", "items": [{"name": "Rice", "price": 100}]}],
            item_count=1,
        ),
    )
    assert first.id == second.id
    assert _revision_count(first.id) == 0


def test_swiggy_additional_information_id_is_source_entity():
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name="Harbor Spice House",
            fssai_number="12345678901234",
            source_url="https://www.swiggy.com/city/sample/extra-id-one-resta",
            restaurant={"name": "Harbor Spice House", "additional_information": {"id": "999001"}},
            categories=[{"name": "Mains", "items": [{"name": "Rice"}]}],
            item_count=1,
        ),
    )
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name="Harbor Spice House",
            fssai_number="12345678901234",
            source_url="https://www.swiggy.com/city/sample/extra-id-two-resta",
            restaurant={"name": "Harbor Spice House", "additional_information": {"id": "999001"}},
            categories=[{"name": "Mains", "items": [{"name": "Rice"}]}],
            item_count=1,
        ),
    )
    assert first.id == second.id
    assert first.result.venue_id == second.result.venue_id


def test_write_failure_rolls_back_revision_and_payload():
    url = "https://www.swiggy.com/city/sample/rollback-resta"
    first = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, restaurant_id="rb1", price=100))

    def boom(*_args, **_kwargs):
        raise RuntimeError("forced write failure")

    import backend.store as store

    original = store._write_catalogue_update
    store._write_catalogue_update = boom  # type: ignore[method-assign]
    try:
        try:
            save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, restaurant_id="rb1", price=110))
            raise AssertionError("expected write failure")
        except RuntimeError:
            pass
    finally:
        store._write_catalogue_update = original  # type: ignore[method-assign]
    rows = list_catalogues("user-1", "org_1")
    assert len(rows) == 1
    assert rows[0].result.categories[0]["items"][0]["price"] == 100
    assert _revision_count(first.id) == 0


def _identity_counts() -> tuple[int, int, int]:
    connection = sqlite3.connect(catalogue_db_path())
    try:
        catalogues = connection.execute("SELECT COUNT(*) FROM catalogues").fetchone()[0]
        venues = connection.execute("SELECT COUNT(*) FROM venues").fetchone()[0]
        sources = connection.execute("SELECT COUNT(*) FROM venue_sources").fetchone()[0]
        return int(catalogues), int(venues), int(sources)
    finally:
        connection.close()


def _drop_unique_indexes() -> None:
    connection = sqlite3.connect(catalogue_db_path())
    try:
        for name in (
            "catalogues_ok_entity",
            "catalogues_ok_url",
            "venue_sources_entity",
            "venue_sources_url",
        ):
            connection.execute(f"DROP INDEX IF EXISTS {name}")
        connection.commit()
    finally:
        connection.close()


def _assert_crossing_conflict_is_rejected() -> None:
    url_x = "https://www.swiggy.com/city/sample/conflict-x-resta"
    url_y = "https://www.swiggy.com/city/sample/conflict-y-restb"
    alpha = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url=url_x, restaurant_id="123", price=100, name="A-dish"),
    )
    beta = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url=url_y, restaurant_id="456", price=200, name="B-dish"),
    )
    before = _identity_counts()
    alpha_payload = alpha.result.model_dump(mode="json")
    beta_payload = beta.result.model_dump(mode="json")
    with pytest.raises(CatalogueIdentityConflict) as caught:
        save_catalogue(
            user_id="user-1",
            organization_id="org_1",
            result=_ok(source_url=url_x, restaurant_id="456", price=300, name="C-dish"),
        )
    assert alpha.id in str(caught.value)
    assert beta.id in str(caught.value)
    assert "IntegrityError" not in type(caught.value).__name__
    rows = {row.id: row for row in list_catalogues("user-1", "org_1")}
    assert set(rows) == {alpha.id, beta.id}
    assert rows[alpha.id].result.model_dump(mode="json") == alpha_payload
    assert rows[beta.id].result.model_dump(mode="json") == beta_payload
    assert rows[alpha.id].result.restaurant["restaurant_id"] == "123"
    assert rows[beta.id].result.restaurant["restaurant_id"] == "456"
    assert _revision_count(alpha.id) == 0
    assert _revision_count(beta.id) == 0
    assert _identity_counts() == before


def test_crossing_url_and_source_id_is_identity_conflict():
    _assert_crossing_conflict_is_rejected()


def test_crossing_identity_conflict_without_unique_indexes():
    _drop_unique_indexes()
    _assert_crossing_conflict_is_rejected()


def test_url_and_source_id_same_catalogue_updates():
    url = "https://www.swiggy.com/city/sample/both-keys-resta"
    first = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, restaurant_id="same-1", price=100))
    second = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, restaurant_id="same-1", price=110))
    assert first.id == second.id
    assert second.result.categories[0]["items"][0]["price"] == 110
    assert _revision_count(first.id) == 1
    assert len(list_catalogues("user-1", "org_1")) == 1


def test_url_only_match_updates():
    url = "https://www.swiggy.com/city/sample/url-only-resta"
    first = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, price=100))
    second = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url, price=110))
    assert first.id == second.id
    assert len(list_catalogues("user-1", "org_1")) == 1
    assert second.result.categories[0]["items"][0]["price"] == 110


def test_source_id_only_match_updates_when_url_changes():
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url="https://www.swiggy.com/city/sample/id-only-a-resta", restaurant_id="id-only-7", price=100),
    )
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url="https://www.swiggy.com/city/sample/id-only-b-resta", restaurant_id="id-only-7", price=110),
    )
    assert first.id == second.id
    assert len(list_catalogues("user-1", "org_1")) == 1
    assert second.result.categories[0]["items"][0]["price"] == 110


def test_neither_url_nor_source_id_match_inserts():
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url="https://www.swiggy.com/city/sample/insert-a-resta", restaurant_id="ins-a", price=100),
    )
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url="https://www.swiggy.com/city/sample/insert-b-resta", restaurant_id="ins-b", price=110),
    )
    assert first.id != second.id
    assert len(list_catalogues("user-1", "org_1")) == 2


def test_matching_catalogue_id_raises_on_crossing_identity():
    catalogues = [
        {
            "id": "cat-a",
            "result": {
                "platform": "swiggy",
                "extraction_status": "ok",
                "source_url": "https://www.swiggy.com/city/sample/alpha-resta",
                "restaurant": {"restaurant_id": "123"},
            },
        },
        {
            "id": "cat-b",
            "result": {
                "platform": "swiggy",
                "extraction_status": "ok",
                "source_url": "https://www.swiggy.com/city/sample/beta-restb",
                "restaurant": {"restaurant_id": "456"},
            },
        },
    ]
    with pytest.raises(CatalogueIdentityConflict):
        matching_catalogue_id(
            catalogues,
            platform="swiggy",
            source_url="https://www.swiggy.com/city/sample/alpha-resta",
            restaurant_id="456",
        )
