from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from backend.grade_explain.explain import IncompleteGradePayload, explain_grade
from backend.grade_explain.recommend import priority_sort_key, recommendation_action
from backend.grading.contract import ENGINE_VERSION, EvidenceItem, GradingResult
from backend.grading.evidence import evidence
from backend.grading.formula import THRESHOLDS, WEIGHTS, letter_for_score
from backend.grading.vision import VisionGrader
from backend.main import app, require_session
from backend.migrate_catalogues import connect_catalogue_db
from backend.schemas import AuthUser
from backend.services.grade_explain_service import get_grade_explanation
from backend.services.grading_service import grade_catalogue
from backend.store import save_catalogue
from tests.test_phase3_grading import _ok_result, png_bytes


def _grade_result(
    *,
    grade: str = "B",
    score: float = 80.0,
    signals: dict[str, float] | None = None,
    deterministic: list[EvidenceItem] | None = None,
    nlp: list[EvidenceItem] | None = None,
    vision: list[EvidenceItem] | None = None,
    hard: list[EvidenceItem] | None = None,
    revision: int = 0,
    state_hash: str = "hash0",
) -> GradingResult:
    return GradingResult(
        catalogue_id="cat_explain",
        graded_head_revision=revision,
        graded_state_hash=state_hash,
        grade=grade,  # type: ignore[arg-type]
        score=score,
        signals=signals
        or {
            "deterministic": 80.0,
            "nlp": 80.0,
            "vision": 80.0,
            "combined": score,
        },
        hard_failures=hard or [],
        deterministic_evidence=deterministic or [],
        nlp_evidence=nlp or [],
        vision_evidence=vision or [],
        grading_metadata={"engine_version": ENGINE_VERSION},
    )


def test_phase5_does_not_change_grading_v1_formula():
    assert ENGINE_VERSION == "grading.v1"
    assert WEIGHTS == {"deterministic": 0.50, "nlp": 0.25, "vision": 0.25}
    assert THRESHOLDS == ((90.0, "A"), (75.0, "B"), (60.0, "C"), (40.0, "D"), (0.0, "F"))


def test_explain_copies_overall_grade_without_recalculation():
    result = _grade_result(grade="C", score=61.2)
    explanation = explain_grade(result)
    assert explanation.overall_grade == "C"
    assert explanation.overall_score == 61.2
    assert explanation.catalogue_id == result.catalogue_id
    assert explanation.graded_head_revision == result.graded_head_revision
    assert explanation.graded_state_hash == result.graded_state_hash
    assert explanation.engine_version == ENGINE_VERSION
    assert explanation.derived is True


def test_section_grades_use_stored_stage_scores_and_frozen_letter_floors():
    result = _grade_result(signals={"deterministic": 91.0, "nlp": 74.9, "vision": 40.0, "combined": 70.0})
    explanation = explain_grade(result)
    by_section = {row.section: row for row in explanation.section_grades}
    assert by_section["deterministic"].letter == letter_for_score(91.0) == "A"
    assert by_section["nlp"].letter == letter_for_score(74.9) == "C"
    assert by_section["vision"].letter == letter_for_score(40.0) == "D"
    assert [row.section for row in explanation.section_grades] == ["deterministic", "nlp", "vision"]
    assert [row.label for row in explanation.section_grades] == ["Deterministic", "Text", "Images"]


def test_missing_section_score_is_not_fabricated():
    result = _grade_result(signals={"deterministic": 80.0, "vision": 80.0, "combined": 80.0})
    try:
        explain_grade(result)
        raise AssertionError("expected IncompleteGradePayload")
    except IncompleteGradePayload as exc:
        assert "nlp" in str(exc)


def test_out_of_range_section_score_is_not_explained():
    result = _grade_result(signals={"deterministic": 69.0, "nlp": 3829.7212, "vision": 0.0, "combined": 100.0})
    try:
        explain_grade(result)
        raise AssertionError("expected IncompleteGradePayload")
    except IncompleteGradePayload as exc:
        assert "nlp" in str(exc)


def test_evidence_mapping_and_reason_from_actual_findings():
    items = [
        evidence(
            category="deterministic",
            check_id="missing_description",
            severity="ordinary",
            result="fail",
            explanation="Item description is missing.",
            path="menus[0].categories[0].items[0].description",
        ),
        evidence(
            category="deterministic",
            check_id="missing_description",
            severity="ordinary",
            result="fail",
            explanation="Item description is missing.",
            path="menus[0].categories[0].items[1].description",
        ),
        evidence(
            category="deterministic",
            check_id="missing_description",
            severity="ordinary",
            result="fail",
            explanation="Item description is missing.",
            path="menus[0].categories[0].items[2].description",
        ),
        evidence(
            category="deterministic",
            check_id="missing_description",
            severity="ordinary",
            result="fail",
            explanation="Item description is missing.",
            path="menus[0].categories[0].items[3].description",
        ),
        evidence(
            category="deterministic",
            check_id="deterministic_clean",
            severity="info",
            result="pass",
            explanation="No deterministic rule failures.",
        ),
    ]
    explanation = explain_grade(_grade_result(deterministic=items))
    assert len(explanation.findings) == 1
    finding = explanation.findings[0]
    assert finding.check_id == "missing_description"
    assert finding.evidence.affected_count == 4
    assert finding.evidence.failed_criterion == "missing_description"
    assert finding.evidence.affected_field == "description"
    assert "Item description is missing." in finding.why
    assert "Affected count: 4" in finding.why
    assert finding.recommendation is not None
    assert finding.recommendation.action == "Add descriptions for the 4 items that have none."


def test_pass_and_skip_evidence_are_not_recommendations():
    result = _grade_result(
        nlp=[
            evidence(
                category="nlp",
                check_id="no_item_text",
                severity="ordinary",
                result="skip",
                explanation="No menu item text was present to evaluate.",
                path="menus",
            )
        ]
    )
    explanation = explain_grade(result)
    assert explanation.findings == []
    assert explanation.recommendations == []
    assert explanation.fix_first is None
    assert "No failing evidence" in explanation.overall_why


def test_severity_reuses_phase3_hard_ordinary_info():
    result = _grade_result(
        grade="F",
        deterministic=[
            evidence(
                category="deterministic",
                check_id="empty_menu",
                severity="hard",
                result="fail",
                explanation="Restaurant catalogue has no menu items.",
                path="menus",
                details={"item_count": 0},
            ),
            evidence(
                category="deterministic",
                check_id="missing_fssai",
                severity="ordinary",
                result="fail",
                explanation="FSSAI license number is missing.",
                path="fssai_number",
            ),
        ],
        hard=[
            evidence(
                category="deterministic",
                check_id="empty_menu",
                severity="hard",
                result="fail",
                explanation="Restaurant catalogue has no menu items.",
                path="menus",
            ),
            evidence(
                category="aggregation",
                check_id="hard_failure_forces_f",
                severity="hard",
                result="fail",
                explanation="A hard failure forces grade F and cannot be overridden by score aggregation.",
            ),
        ],
    )
    explanation = explain_grade(result)
    assert explanation.findings[0].severity == "hard"
    assert explanation.findings[0].check_id == "empty_menu"
    assert explanation.fix_first is not None
    assert explanation.fix_first.check_id == "empty_menu"
    assert "hard failure" in explanation.overall_why.lower() or "Hard failure" in explanation.overall_why


def test_prioritization_hard_before_ordinary_then_stage_weight_then_count():
    result = _grade_result(
        deterministic=[
            evidence(
                category="deterministic",
                check_id="missing_price",
                severity="ordinary",
                result="fail",
                explanation="Selling price is missing.",
                path="menus[0].categories[0].items[0].price",
            ),
            evidence(
                category="deterministic",
                check_id="empty_menu",
                severity="hard",
                result="fail",
                explanation="Restaurant catalogue has no menu items.",
                path="menus",
            ),
        ],
        nlp=[
            evidence(
                category="nlp",
                check_id="placeholder_text",
                severity="ordinary",
                result="fail",
                explanation="Text matches a placeholder token.",
                path="menus[0].categories[0].items[0].description",
            ),
            evidence(
                category="nlp",
                check_id="placeholder_text",
                severity="ordinary",
                result="fail",
                explanation="Text matches a placeholder token.",
                path="menus[0].categories[0].items[1].description",
            ),
        ],
        vision=[
            evidence(
                category="vision",
                check_id="image_low_quality",
                severity="ordinary",
                result="fail",
                explanation="Image is too small to be a useful catalogue photo.",
                path="menus[0].categories[0].items[0].image_url",
            )
        ],
    )
    explanation = explain_grade(result)
    ids = [item.check_id for item in explanation.recommendations]
    assert ids[0] == "empty_menu"
    assert ids[1] == "missing_price"
    assert "placeholder_text" in ids
    assert ids.index("placeholder_text") < ids.index("image_low_quality")
    assert explanation.fix_first is not None
    assert explanation.fix_first.priority == 1
    assert list(range(1, len(explanation.recommendations) + 1)) == [row.priority for row in explanation.recommendations]
    assert priority_sort_key(severity="hard", section="nlp", affected_count=99, check_id="z") < priority_sort_key(
        severity="ordinary", section="deterministic", affected_count=1, check_id="a"
    )


def test_recommendation_action_is_evidence_backed():
    assert recommendation_action(
        check_id="description_coverage",
        affected_count=6,
        details={"described": 4, "item_total": 10, "coverage": 40.0},
        explanation="coverage",
    ) == "Add descriptions until at least 70% of items have one (4 of 10 currently described)."
    assert recommendation_action(
        check_id="unknown_check",
        affected_count=2,
        details={},
        explanation="Custom stored explanation.",
    ) == "Fix 2 failing unknown_check finding(s): Custom stored explanation."


def test_unmapped_check_id_still_gets_evidence_backed_recommendation():
    result = _grade_result(
        deterministic=[
            evidence(
                category="deterministic",
                check_id="brand_new_phase3_check",
                severity="ordinary",
                result="fail",
                explanation="Stored explanation from grading.v1.",
                path="menus[0].categories[0].items[0].name",
            )
        ]
    )
    explanation = explain_grade(result)
    assert len(explanation.findings) == 1
    assert explanation.fix_first is not None
    assert explanation.fix_first.check_id == "brand_new_phase3_check"
    assert explanation.fix_first.action == (
        "Fix 1 failing brand_new_phase3_check finding(s): Stored explanation from grading.v1."
    )
    assert "unrelated" not in explanation.fix_first.action


def test_info_fail_can_be_fix_first_when_it_is_the_only_actionable_finding():
    result = _grade_result(
        nlp=[
            evidence(
                category="nlp",
                check_id="very_long_text",
                severity="info",
                result="fail",
                explanation="Over-long fields were truncated for analysis; grading still completed.",
                details={"truncated_fields": 2},
            )
        ]
    )
    explanation = explain_grade(result)
    assert explanation.fix_first is not None
    assert explanation.fix_first.severity == "info"
    assert explanation.fix_first.check_id == "very_long_text"


def test_explain_is_idempotent_and_deterministic():
    result = _grade_result(
        deterministic=[
            evidence(
                category="deterministic",
                check_id="missing_address",
                severity="ordinary",
                result="fail",
                explanation="Venue address is missing.",
                path="venue.address",
            )
        ]
    )
    first = explain_grade(result)
    second = explain_grade(result)
    assert first.model_dump() == second.model_dump()


def test_incomplete_data_does_not_invent_findings():
    explanation = explain_grade(_grade_result())
    assert explanation.findings == []
    assert explanation.recommendations == []
    assert explanation.overall_grade == "B"


def test_large_finding_set_aggregates_without_per_item_records():
    items = [
        evidence(
            category="deterministic",
            check_id="missing_item_image",
            severity="ordinary",
            result="fail",
            explanation="Dish image is missing.",
            path=f"menus[0].categories[0].items[{index}].image_url",
        )
        for index in range(400)
    ]
    started = time.perf_counter()
    explanation = explain_grade(_grade_result(deterministic=items, signals={"deterministic": 75.0, "nlp": 100.0, "vision": 0.0, "combined": 62.5}))
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0
    assert len(explanation.findings) == 1
    assert explanation.findings[0].evidence.affected_count == 400
    assert len(explanation.findings[0].evidence.paths) == 400


def test_grading_v1_to_explanation_to_api():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/phase5-api-resta",
            restaurant_id="p5a",
            description="",
            extra_items=[
                {"name": "Plain Rice", "price": 99, "description": "", "additional_information": {"id": "m2"}},
                {"name": "Curd Rice", "price": 89, "description": "n/a", "additional_information": {"id": "m3"}},
            ],
        ),
    )
    grade = grade_catalogue(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=VisionGrader(fetch=lambda _url: png_bytes(120, 120)),
    )
    explanation = explain_grade(grade)
    assert explanation.overall_grade == grade.grade
    assert explanation.overall_score == grade.score
    assert explanation.graded_state_hash == grade.graded_state_hash
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        missing = client.get(f"/catalogues/{stored.id}/grade-explanation", params={"organization_id": "org_1"})
        assert missing.status_code == 200
        body = missing.json()
        assert body["overall_grade"] == grade.grade
        assert body["section_grades"]
        assert body["fix_first"]["action"]
        assert any(finding["why"] for finding in body["findings"])
        assert body["catalogue_id"] == stored.id
        assert body["graded_head_revision"] == grade.graded_head_revision
        denied = client.get(f"/catalogues/{stored.id}/grade-explanation", params={"organization_id": "org_stranger"})
        assert denied.status_code == 403
        other = client.get(f"/catalogues/{stored.id}/grade-explanation", params={"organization_id": "org_1"})
        app.dependency_overrides[require_session] = lambda: AuthUser(id="user_2", email="x@example.com")
        cross = client.get(f"/catalogues/{stored.id}/grade-explanation", params={"organization_id": "org_1"})
        assert cross.status_code == 404
        malformed = client.get(f"/catalogues/{stored.id}/grade-explanation")
        assert malformed.status_code == 422
    finally:
        app.dependency_overrides.clear()
    assert other.status_code == 200


def test_missing_grade_is_404_not_fabricated():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/phase5-miss-resta", restaurant_id="p5m"),
    )
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.get(f"/catalogues/{stored.id}/grade-explanation", params={"organization_id": "org_1"})
        assert response.status_code == 404
        assert response.json()["detail"] == "No completed grade for this catalogue revision."
        unknown = client.get("/catalogues/nope/grade-explanation", params={"organization_id": "org_1"})
        assert unknown.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_stale_revision_does_not_explain_previous_grade():
    url = "https://www.swiggy.com/city/sample/phase5-stale-resta"
    first = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(source_url=url, restaurant_id="p5s", price=100),
    )
    vision = VisionGrader(fetch=lambda _url: png_bytes(120, 120))
    grade_catalogue(user_id="user_1", organization_id="org_1", catalogue_id=first.id, vision_grader=vision)
    save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(source_url=url, restaurant_id="p5s", price=150),
    )
    assert get_grade_explanation(user_id="user_1", organization_id="org_1", catalogue_id=first.id) is None
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.get(f"/catalogues/{first.id}/grade-explanation", params={"organization_id": "org_1"})
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_unauthenticated_explanation_is_401():
    client = TestClient(app)
    response = client.get("/catalogues/any/grade-explanation", params={"organization_id": "org_1"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_incomplete_grade_payload_is_502(monkeypatch):
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/phase5-bad-resta", restaurant_id="p5b"),
    )
    broken = _grade_result(signals={"deterministic": 50.0, "combined": 50.0})
    monkeypatch.setattr(
        "backend.services.grade_explain_service.get_catalogue_grade",
        lambda **_kwargs: broken,
    )
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.get(f"/catalogues/{stored.id}/grade-explanation", params={"organization_id": "org_1"})
        assert response.status_code == 502
        assert response.json()["detail"] == "Grade explanation could not be completed."
    finally:
        app.dependency_overrides.clear()


def test_corrupt_stored_grade_json_is_502():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/phase5-corrupt-resta", restaurant_id="p5k"),
    )
    grade_catalogue(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=VisionGrader(fetch=lambda _url: png_bytes(120, 120)),
    )
    connection = connect_catalogue_db()
    try:
        connection.execute("UPDATE catalogue_grades SET payload = ? WHERE catalogue_id = ?", ("not-json", stored.id))
        connection.commit()
    finally:
        connection.close()
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.get(f"/catalogues/{stored.id}/grade-explanation", params={"organization_id": "org_1"})
        assert response.status_code == 502
        assert response.json()["detail"] == "Grade explanation could not be completed."
    finally:
        app.dependency_overrides.clear()


def test_concurrent_duplicate_reads_converge():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/phase5-conc-resta", restaurant_id="p5c"),
    )
    grade_catalogue(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=VisionGrader(fetch=lambda _url: png_bytes(120, 120)),
    )
    results: list[dict] = []
    errors: list[BaseException] = []

    def _read() -> None:
        try:
            row = get_grade_explanation(user_id="user_1", organization_id="org_1", catalogue_id=stored.id)
            assert row is not None
            results.append(row.model_dump())
        except BaseException as exc:  # noqa: BLE001 — collect worker failures for the assertion below
            errors.append(exc)

    workers = [threading.Thread(target=_read) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert errors == []
    assert len(results) == 8
    assert all(row == results[0] for row in results)


def test_phase5_adds_no_explanation_table():
    connection = connect_catalogue_db()
    try:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    finally:
        connection.close()
    assert "catalogue_grade_explanations" not in names
    assert "catalogue_recommendations" not in names


def test_explanation_does_not_recompute_or_regrade(monkeypatch):
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/phase5-nplus-resta", restaurant_id="p5n"),
    )
    grade_catalogue(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=VisionGrader(fetch=lambda _url: png_bytes(120, 120)),
    )

    def boom(*_args, **_kwargs):
        raise AssertionError("Phase 5 must not invoke grading.v1 compute")

    monkeypatch.setattr("backend.grading.orchestrator.grade_canonical_document", boom)
    monkeypatch.setattr("backend.grading.deterministic.grade_deterministic", boom)
    explanation = get_grade_explanation(user_id="user_1", organization_id="org_1", catalogue_id=stored.id)
    assert explanation is not None
    assert explanation.overall_grade in {"A", "B", "C", "D", "F"}


def test_no_new_phase5_tables_after_explain_flow():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/phase5-ddl-resta", restaurant_id="p5d"),
    )
    grade_catalogue(
        user_id="user_1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=VisionGrader(fetch=lambda _url: png_bytes(120, 120)),
    )
    get_grade_explanation(user_id="user_1", organization_id="org_1", catalogue_id=stored.id)
    connection = connect_catalogue_db()
    try:
        names = sorted(row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
    finally:
        connection.close()
    assert "catalogue_grades" in names
    assert all("explain" not in name for name in names)
