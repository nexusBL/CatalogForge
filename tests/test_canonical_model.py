from __future__ import annotations

from backend.canonical.identity import assign_item_ids, source_entity_id_from_result, source_item_id_from_item


def test_source_entity_id_ignores_parent_and_name():
    result = {
        "restaurant": {
            "name": "Chain",
            "additional_information": {"parentId": "chain-1", "id": "outlet-9"},
        }
    }
    assert source_entity_id_from_result(result) == "outlet-9"


def test_source_item_id_from_additional_information():
    assert source_item_id_from_item({"name": "Rice", "additional_information": {"id": "m1"}}) == "m1"
    assert source_item_id_from_item({"name": "Rice"}) is None


def test_assign_item_ids_reuses_only_source_item_id():
    previous = assign_item_ids(
        [{"name": "Mains", "items": [{"name": "Rice", "additional_information": {"id": "m1"}, "price": 100}]}]
    )
    first_id = previous[0]["items"][0]["item_id"]
    again = assign_item_ids(
        [{"name": "Mains", "items": [{"name": "Rice", "additional_information": {"id": "m1"}, "price": 110}]}],
        previous={source_item_id_from_item(previous[0]["items"][0]): first_id},
    )
    assert again[0]["items"][0]["item_id"] == first_id


def test_assign_item_ids_does_not_match_name_and_price():
    previous = assign_item_ids([{"name": "Mains", "items": [{"name": "Rice", "price": 100}]}])
    first_id = previous[0]["items"][0]["item_id"]
    again = assign_item_ids(
        [{"name": "Mains", "items": [{"name": "Rice", "price": 100}]}],
        previous={},
    )
    assert again[0]["items"][0]["item_id"] != first_id
