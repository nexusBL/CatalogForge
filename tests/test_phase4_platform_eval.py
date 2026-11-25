from __future__ import annotations

import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from backend.canonical.adapter import to_canonical_from_response
from backend.grading.contract import ENGINE_VERSION
from backend.grading.formula import THRESHOLDS, WEIGHTS
from backend.main import app, require_session
from backend.migrate_catalogues import MIGRATION_ID, connect_catalogue_db, migrate_catalogue_db
from backend.platform_eval.adapters import UnsupportedPlatform, get_adapter, supported_platforms
from backend.platform_eval.contract import EVALUATION_VERSION, BabaScore
from backend.platform_eval.evaluate import evaluate_platforms, resolve_platforms
from backend.platform_eval.persist import (
    PlatformEvalPersistenceError,
    persist_evaluations,
    snapshot_catalogue,
)
from backend.platform_eval.signals import parse_native_score
from backend.schemas import AuthUser, CatalogCreateResponse
from backend.services.grading_service import get_catalogue_grade, grade_catalogue
from backend.services.platform_eval_service import evaluate_catalogue_platforms, get_catalogue_platform_evaluation
from backend.store import delete_catalogue, save_catalogue


def _result(
    *,
    source_url: str,
    platform: str = "swiggy",
    restaurant_id: str = "p4",
    restaurant_name: str = "Platform House",
    extra_restaurant: dict | None = None,
    categories: list | None = None,
    extraction_status: str = "ok",
) -> CatalogCreateResponse:
    restaurant = {
        "name": restaurant_name,
        "restaurant_id": restaurant_id,
        "address": "MG Road",
        "fssai_license": "12345678901234",
    }
    if extra_restaurant:
        restaurant.update(extra_restaurant)
    return CatalogCreateResponse(
        extraction_status=extraction_status,  # type: ignore[arg-type]
        restaurant_name=restaurant_name,
        fssai_number="12345678901234",
        source_url=source_url,
        platform=platform,  # type: ignore[arg-type]
        catalogue_type="restaurant",
        restaurant=restaurant,
        categories=categories
        if categories is not None
        else [{"name": "Mains", "items": [{"name": "Rice", "price": 199, "description": "Ghee rice", "additional_information": {"id": "m1"}}]}],
        item_count=1 if categories is None else sum(len(cat.get("items") or []) for cat in categories),
    )


def test_grading_v1_formula_unchanged_by_phase4():
    assert ENGINE_VERSION == "grading.v1"
    assert WEIGHTS == {"deterministic": 0.50, "nlp": 0.25, "vision": 0.25}
    assert THRESHOLDS[0] == (90.0, "A")
    assert EVALUATION_VERSION == "platform_eval.v1"
    assert EVALUATION_VERSION != ENGINE_VERSION


def test_registry_has_required_platforms_without_scattered_branching():
    assert supported_platforms() == ("magicpin", "swiggy", "zomato")
    for name in supported_platforms():
        adapter = get_adapter(name)
        assert adapter is not None
        assert adapter.platform == name
    with pytest.raises(UnsupportedPlatform):
        resolve_platforms(
            to_canonical_from_response(_result(source_url="https://www.swiggy.com/city/sample/reg-resta")),
            ["not-a-platform"],
        )


def test_parse_native_score_malformed_and_partial():
    assert parse_native_score(4.2) == (4.2, True)
    assert parse_native_score("4.5") == (4.5, True)
    assert parse_native_score("n/a") == (None, False)
    assert parse_native_score(None) == (None, False)
    assert parse_native_score(True) == (None, False)
    assert parse_native_score(float("nan"))[1] is False


def test_adapters_extract_evidence_and_never_set_baba_score():
    document = to_canonical_from_response(
        _result(
            source_url="https://www.swiggy.com/city/sample/ev-resta",
            extra_restaurant={
                "rating": 4.3,
                "rating_count": 120,
                "dining_rating": 4.1,
                "dining_rating_count": 40,
                "delivery_rating": 4.4,
                "delivery_rating_count": 80,
                "zomato_rating": 4.0,
                "magicpin_rating": 3.9,
            },
        )
    )
    evaluations = evaluate_platforms(
        document,
        catalogue_id="cat-1",
        evaluated_head_revision=0,
        evaluated_state_hash="abc",
        platforms=["swiggy", "zomato", "magicpin"],
    )
    by_platform = {item.platform: item for item in evaluations}
    assert set(by_platform) == {"swiggy", "zomato", "magicpin"}
    assert by_platform["swiggy"].source_listing is True
    assert by_platform["zomato"].source_listing is False
    assert by_platform["magicpin"].source_listing is False
    assert all(item.kind == "platform_evidence" for item in evaluations)
    assert all(item.baba_score is None for item in evaluations)
    swiggy_ids = {item.check_id for item in by_platform["swiggy"].evidence}
    assert "swiggy_native_rating_present" in swiggy_ids
    assert "swiggy_dining_delivery_split" in swiggy_ids
    zomato_ids = {item.check_id for item in by_platform["zomato"].evidence}
    assert "zomato_listed_on_foreign_listing" in zomato_ids
    assert any(signal.score == 4.3 for signal in by_platform["swiggy"].native_signals)


def test_missing_and_out_of_scale_platform_data():
    missing = to_canonical_from_response(_result(source_url="https://www.swiggy.com/city/sample/miss-resta", restaurant_id="miss"))
    missing_eval = evaluate_platforms(
        missing,
        catalogue_id="c",
        evaluated_head_revision=0,
        evaluated_state_hash="h",
        platforms=["swiggy"],
    )[0]
    present = {item.check_id: item.result for item in missing_eval.evidence}
    assert present["swiggy_native_rating_present"] == "fail"

    wild = to_canonical_from_response(
        _result(
            source_url="https://www.zomato.com/city/wild-resta",
            platform="zomato",
            restaurant_id="wild",
            extra_restaurant={"rating": 9.9},
        )
    )
    wild_eval = evaluate_platforms(
        wild,
        catalogue_id="c",
        evaluated_head_revision=0,
        evaluated_state_hash="h",
        platforms=["zomato"],
    )[0]
    scale = next(item for item in wild_eval.evidence if item.check_id == "zomato_declared_native_scale")
    assert scale.result == "fail"


def test_baba_score_independent_of_platform_rating():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(
            source_url="https://www.swiggy.com/city/sample/sep-resta",
            restaurant_id="sep",
            extra_restaurant={"rating": 4.9, "rating_count": 999},
            categories=[],
        ),
    )
    grade = grade_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    evaluation = evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    assert grade.grade == "F"
    assert evaluation.baba_score is not None
    assert evaluation.baba_score.kind == "baba_score"
    assert evaluation.baba_score.source == "grading.v1"
    assert evaluation.baba_score.letter == "F"
    assert evaluation.baba_score.score == grade.score
    swiggy = next(item for item in evaluation.platform_evaluations if item.platform == "swiggy")
    assert any(signal.score == 4.9 for signal in swiggy.native_signals)
    assert swiggy.baba_score is None
    assert evaluation.baba_score.letter != "A" or grade.grade == "A"


def test_platform_eval_does_not_write_catalogue_grades():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/nowrite-resta", restaurant_id="nw"),
    )
    evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    assert get_catalogue_grade(user_id="user-1", organization_id="org_1", catalogue_id=stored.id) is None
    connection = connect_catalogue_db()
    try:
        grades = connection.execute("SELECT COUNT(*) AS n FROM catalogue_grades WHERE catalogue_id = ?", (stored.id,)).fetchone()["n"]
        evals = connection.execute("SELECT COUNT(*) AS n FROM catalogue_platform_evaluations WHERE catalogue_id = ?", (stored.id,)).fetchone()["n"]
    finally:
        connection.close()
    assert grades == 0
    assert evals >= 1


def test_idempotent_same_revision_platform_and_version():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(
            source_url="https://www.magicpin.in/india/sample/idemp/store/1",
            platform="magicpin",
            restaurant_id="mp1",
            extra_restaurant={"rating": 3.5},
        ),
    )
    first = evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    second = evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    assert first.platform_evaluations == second.platform_evaluations
    connection = connect_catalogue_db()
    try:
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_platform_evaluations WHERE catalogue_id = ?",
            (stored.id,),
        ).fetchone()["n"]
    finally:
        connection.close()
    assert count == len(first.platform_evaluations)


def test_revision_change_creates_new_identity_not_overwrite():
    url = "https://www.swiggy.com/city/sample/rev-eval-resta"
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url=url, restaurant_id="re", extra_restaurant={"rating": 3.0}),
    )
    evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=first.id)
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url=url, restaurant_id="re", extra_restaurant={"rating": 4.2}),
    )
    assert second.id == first.id
    later = evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=first.id)
    assert later.evaluated_head_revision >= 1
    connection = connect_catalogue_db()
    try:
        rows = connection.execute(
            "SELECT evaluated_head_revision FROM catalogue_platform_evaluations WHERE catalogue_id = ? AND platform = 'swiggy' ORDER BY evaluated_head_revision",
            (first.id,),
        ).fetchall()
    finally:
        connection.close()
    assert [row["evaluated_head_revision"] for row in rows] == [0, later.evaluated_head_revision]


def test_concurrent_evaluations_do_not_duplicate_rows():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/conc-eval-resta", restaurant_id="ce", extra_restaurant={"rating": 4.1}),
    )
    errors: list[str] = []

    def run():
        try:
            evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
        except Exception as exc:
            errors.append(type(exc).__name__)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    connection = connect_catalogue_db()
    try:
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_platform_evaluations WHERE catalogue_id = ? AND platform = 'swiggy'",
            (stored.id,),
        ).fetchone()["n"]
    finally:
        connection.close()
    assert count == 1
    assert not errors


def test_delete_catalogue_removes_platform_evaluations():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/del-eval-resta", restaurant_id="de"),
    )
    evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    assert delete_catalogue("user-1", stored.id, "org_1") is True
    connection = connect_catalogue_db()
    try:
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_platform_evaluations WHERE catalogue_id = ?",
            (stored.id,),
        ).fetchone()["n"]
    finally:
        connection.close()
    assert count == 0


def test_phase4_ddl_does_not_repeat_phase1_backfill(tmp_path, monkeypatch):
    db = tmp_path / "phase4.sqlite"
    monkeypatch.setenv("CATALOGFORGE_CATALOGUE_DB", str(db))
    first = migrate_catalogue_db(db)
    assert first["id"] == MIGRATION_ID
    second = migrate_catalogue_db(db)
    assert second["skipped"] is True
    assert second["backfilled"] is False
    connection = sqlite3.connect(db)
    try:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        connection.close()
    assert "catalogue_platform_evaluations" in names
    assert "catalogue_grades" in names


def test_platform_eval_foreign_key_rejected_for_missing_catalogue():
    connection = connect_catalogue_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO catalogue_platform_evaluations (
                    id, catalogue_id, user_id, organization_id, evaluated_head_revision,
                    evaluated_state_hash, platform, evaluation_version, status, payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?)
                """,
                (
                    "pe-orphan",
                    "missing-catalogue",
                    "user-1",
                    "org_1",
                    0,
                    "hash",
                    "swiggy",
                    EVALUATION_VERSION,
                    "{}",
                    "2026-08-20T00:00:00+00:00",
                ),
            )
            connection.commit()
    finally:
        connection.close()


def test_n_plus_one_single_select_for_evaluations():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(
            source_url="https://www.swiggy.com/city/sample/n1-eval-resta",
            restaurant_id="n1",
            extra_restaurant={"rating": 4.0, "zomato_rating": 3.8, "magicpin_rating": 3.7},
        ),
    )
    evaluation = evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    from backend.platform_eval.persist import get_completed_evaluations

    queries: list[str] = []
    connection = connect_catalogue_db()
    try:
        connection.set_trace_callback(lambda sql: queries.append(sql))
        rows = get_completed_evaluations(
            connection,
            catalogue_id=stored.id,
            evaluated_head_revision=evaluation.evaluated_head_revision,
            evaluated_state_hash=evaluation.evaluated_state_hash,
        )
    finally:
        connection.set_trace_callback(None)
        connection.close()
    assert len(rows) == 3
    select_evals = [sql for sql in queries if "FROM catalogue_platform_evaluations" in sql]
    assert len(select_evals) == 1


def test_api_authz_validation_and_separation():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_result(
            source_url="https://www.swiggy.com/city/sample/api-eval-resta",
            restaurant_id="api",
            extra_restaurant={"rating": 4.2},
        ),
    )
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        denied = client.post(f"/catalogues/{stored.id}/platform-evaluation", params={"organization_id": "org_stranger"})
        assert denied.status_code == 403
        missing = client.post("/catalogues/nope/platform-evaluation", params={"organization_id": "org_1"})
        assert missing.status_code == 404
        bad = client.post(
            f"/catalogues/{stored.id}/platform-evaluation",
            params=[("organization_id", "org_1"), ("platform", "unknown")],
        )
        assert bad.status_code == 422
        response = client.post(f"/catalogues/{stored.id}/platform-evaluation", params={"organization_id": "org_1"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["baba_score"] is None
        assert all(item["kind"] == "platform_evidence" for item in body["platform_evaluations"])
        assert all(item["baba_score"] is None for item in body["platform_evaluations"])
        fetched = client.get(f"/catalogues/{stored.id}/platform-evaluation", params={"organization_id": "org_1"})
        assert fetched.status_code == 200
        baba = client.get(f"/catalogues/{stored.id}/baba-score", params={"organization_id": "org_1"})
        assert baba.status_code == 404
        client.post(f"/catalogues/{stored.id}/grade", params={"organization_id": "org_1"})
        baba_ok = client.get(f"/catalogues/{stored.id}/baba-score", params={"organization_id": "org_1"})
        assert baba_ok.status_code == 200
        score_body = baba_ok.json()
        assert score_body["kind"] == "baba_score"
        assert score_body["source"] == "grading.v1"
        BabaScore.model_validate(score_body)
        other = TestClient(app)
        app.dependency_overrides[require_session] = lambda: AuthUser(id="user_other", email="x@example.com")
        isolated = other.get(f"/catalogues/{stored.id}/platform-evaluation", params={"organization_id": "org_1"})
        assert isolated.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_applicable_platforms_do_not_invent_empty_foreign_rows():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/only-sw-resta", restaurant_id="os"),
    )
    evaluation = evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    assert [item.platform for item in evaluation.platform_evaluations] == ["swiggy"]


def test_stale_persist_returns_http_409(monkeypatch):
    url = "https://www.swiggy.com/city/sample/stale-eval-resta"
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_result(source_url=url, restaurant_id="stale1", extra_restaurant={"rating": 3.0}),
    )
    from backend.services import platform_eval_service as svc

    real_persist = svc.persist_evaluations

    def persist_after_revision(**kwargs):
        save_catalogue(
            user_id="user_1",
            organization_id="org_1",
            result=_result(source_url=url, restaurant_id="stale1", extra_restaurant={"rating": 4.8}),
        )
        return real_persist(**kwargs)

    monkeypatch.setattr(svc, "persist_evaluations", persist_after_revision)
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.post(f"/catalogues/{stored.id}/platform-evaluation", params={"organization_id": "org_1"})
        assert response.status_code == 409
        assert "revision" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_fk_integrity_error_is_not_treated_as_duplicate(monkeypatch):
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/fk-eval-resta", restaurant_id="fk1"),
    )
    result, revision, state_hash = snapshot_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    computed = evaluate_platforms(
        to_canonical_from_response(result),
        catalogue_id=stored.id,
        evaluated_head_revision=revision,
        evaluated_state_hash=state_hash,
        platforms=["swiggy"],
    )
    from backend.platform_eval import persist as persist_mod

    def raise_fk(_connection, _params):
        raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

    monkeypatch.setattr(persist_mod, "_insert_completed_evaluation", raise_fk)
    with pytest.raises(KeyError, match="Catalogue not found"):
        persist_evaluations(
            user_id="user-1",
            organization_id="org_1",
            catalogue_id=stored.id,
            expected_head_revision=revision,
            expected_state_hash=state_hash,
            evaluations=computed,
        )
    connection = connect_catalogue_db()
    try:
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_platform_evaluations WHERE catalogue_id = ?",
            (stored.id,),
        ).fetchone()["n"]
    finally:
        connection.close()
    assert count == 0


def test_unique_integrity_error_remains_idempotent(monkeypatch):
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/uniq-eval-resta", restaurant_id="uq1", extra_restaurant={"rating": 4.0}),
    )
    first = evaluate_catalogue_platforms(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    swiggy = next(item for item in first.platform_evaluations if item.platform == "swiggy")
    from backend.platform_eval import persist as persist_mod

    calls = {"n": 0}
    real_get = persist_mod.get_completed_evaluations

    def get_then_real(connection, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return []
        return real_get(connection, **kwargs)

    monkeypatch.setattr(persist_mod, "get_completed_evaluations", get_then_real)
    second = persist_evaluations(
        user_id="user-1",
        organization_id="org_1",
        catalogue_id=stored.id,
        expected_head_revision=first.evaluated_head_revision,
        expected_state_hash=first.evaluated_state_hash,
        evaluations=[swiggy],
    )
    assert second[0].platform == "swiggy"
    assert second[0].native_signals == swiggy.native_signals
    connection = connect_catalogue_db()
    try:
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_platform_evaluations WHERE catalogue_id = ? AND platform = 'swiggy'",
            (stored.id,),
        ).fetchone()["n"]
    finally:
        connection.close()
    assert count == 1


def test_unexpected_integrity_error_is_persistence_failure(monkeypatch):
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/chk-eval-resta", restaurant_id="chk1"),
    )
    result, revision, state_hash = snapshot_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    computed = evaluate_platforms(
        to_canonical_from_response(result),
        catalogue_id=stored.id,
        evaluated_head_revision=revision,
        evaluated_state_hash=state_hash,
        platforms=["swiggy"],
    )
    from backend.platform_eval import persist as persist_mod

    def raise_check(_connection, _params):
        raise sqlite3.IntegrityError("CHECK constraint failed")

    monkeypatch.setattr(persist_mod, "_insert_completed_evaluation", raise_check)
    with pytest.raises(PlatformEvalPersistenceError):
        persist_evaluations(
            user_id="user-1",
            organization_id="org_1",
            catalogue_id=stored.id,
            expected_head_revision=revision,
            expected_state_hash=state_hash,
            evaluations=computed,
        )


def test_rollback_after_begin_immediate_on_missing_catalogue(monkeypatch):
    events: list[str] = []
    from backend.platform_eval import persist as persist_mod

    real_begin = persist_mod._begin_immediate
    real_rollback = persist_mod._rollback

    def begin(connection):
        events.append("BEGIN")
        return real_begin(connection)

    def rollback(connection, original):
        events.append("ROLLBACK")
        return real_rollback(connection, original)

    monkeypatch.setattr(persist_mod, "_begin_immediate", begin)
    monkeypatch.setattr(persist_mod, "_rollback", rollback)
    with pytest.raises(KeyError):
        persist_evaluations(
            user_id="user-1",
            organization_id="org_1",
            catalogue_id="missing-eval-id",
            expected_head_revision=0,
            expected_state_hash="dead",
            evaluations=[],
        )
    assert events == ["BEGIN", "ROLLBACK"]


def test_adapter_exception_is_http_502_and_not_persisted(monkeypatch):
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/boom-eval-resta", restaurant_id="boom1"),
    )

    class Boom:
        def evaluate(self, document, context):
            raise RuntimeError("adapter down")

    monkeypatch.setattr("backend.platform_eval.evaluate.require_adapter", lambda _platform: Boom())
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.post(f"/catalogues/{stored.id}/platform-evaluation", params={"organization_id": "org_1"})
        assert response.status_code == 502
        assert response.json()["detail"] == "Platform evaluation could not be completed."
    finally:
        app.dependency_overrides.clear()
    connection = connect_catalogue_db()
    try:
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_platform_evaluations WHERE catalogue_id = ?",
            (stored.id,),
        ).fetchone()["n"]
    finally:
        connection.close()
    assert count == 0


def test_unauthenticated_phase4_requests_are_401():
    client = TestClient(app)
    posted = client.post("/catalogues/any/platform-evaluation", params={"organization_id": "org_1"})
    fetched = client.get("/catalogues/any/platform-evaluation", params={"organization_id": "org_1"})
    baba = client.get("/catalogues/any/baba-score", params={"organization_id": "org_1"})
    assert posted.status_code == 401
    assert fetched.status_code == 401
    assert baba.status_code == 401
    assert posted.json()["detail"] == "Not authenticated"


def test_corrupt_stored_payload_is_not_client_422():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/bad-json-eval-resta", restaurant_id="badj"),
    )
    connection = connect_catalogue_db()
    try:
        connection.execute("UPDATE catalogues SET payload = ? WHERE id = ?", ("not-json", stored.id))
        connection.commit()
    finally:
        connection.close()
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.post(f"/catalogues/{stored.id}/platform-evaluation", params={"organization_id": "org_1"})
        assert response.status_code == 502
        assert response.status_code != 422
        assert response.json()["detail"] == "Platform evaluation could not be completed."
    finally:
        app.dependency_overrides.clear()


def test_get_platform_evaluation_empty_list_is_200():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_result(source_url="https://www.swiggy.com/city/sample/empty-get-eval-resta", restaurant_id="emptyg"),
    )
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.get(f"/catalogues/{stored.id}/platform-evaluation", params={"organization_id": "org_1"})
        assert response.status_code == 200
        body = response.json()
        assert body["platform_evaluations"] == []
        assert body["baba_score"] is None
        assert body["catalogue_id"] == stored.id
    finally:
        app.dependency_overrides.clear()
