from __future__ import annotations

import json
import sqlite3
import struct
import threading
import zlib

import pytest
from fastapi.testclient import TestClient

from backend.canonical.adapter import to_canonical_from_response
from backend.canonical.models import CanonicalMenuItem
from backend.grading.contract import EvidenceItem, StageSignals
from backend.grading.deterministic import grade_deterministic
from backend.grading.formula import aggregate_grade, combine_scores, letter_for_score
from backend.grading.nlp import NLPGrader
from backend.grading.orchestrator import GradingCancelled, GradingStageFailure, grade_canonical_document
from backend.grading.persist import GradePersistenceError, StaleClaim, claim_grade_job, finish_grade_job
from backend.grading.vision import VisionGrader, inspect_image_bytes
from backend.main import app, require_session
from backend.migrate_catalogues import MIGRATION_ID, connect_catalogue_db, migrate_catalogue_db
from backend.schemas import AuthUser, CatalogCreateResponse
from backend.services.grading_service import GradeCancelled, get_catalogue_grade, grade_catalogue
from backend.store import delete_catalogue, save_catalogue
from scraper.swiggy.assets import assets_root


def png_bytes(width: int, height: int, rgb: tuple[int, int, int] = (12, 80, 200)) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + (bytes(rgb) * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def avif_bytes(width: int = 120, height: int = 120) -> bytes:
    def box(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", 8 + len(payload)) + tag + payload

    ispe = box(b"ispe", b"\x00\x00\x00\x00" + struct.pack(">II", width, height))
    ipco = box(b"ipco", ispe)
    iprp = box(b"iprp", ipco)
    meta = box(b"meta", b"\x00\x00\x00\x00" + iprp)
    ftyp = box(b"ftyp", b"avif" + struct.pack(">I", 0) + b"avifmif1")
    return ftyp + meta


def _ok_result(
    *,
    source_url: str,
    restaurant_id: str = "g1",
    price: int | None = 199,
    name: str = "Ghee Rice",
    description: str = "Fragrant basmati rice cooked in ghee.",
    image_url: str | None = None,
    item_count: int | None = None,
    extra_items: list[dict] | None = None,
    extraction_status: str = "ok",
    restaurant_name: str = "Harbor Spice House",
    address: str = "MG Road",
    fssai: str = "12345678901234",
    catalogue_type: str = "restaurant",
) -> CatalogCreateResponse:
    item = {
        "name": name,
        "price": price,
        "description": description,
        "additional_information": {"id": "m1"},
    }
    if image_url:
        item["image_url"] = image_url
    items = [item]
    if extra_items:
        items.extend(extra_items)
    return CatalogCreateResponse(
        extraction_status=extraction_status,  # type: ignore[arg-type]
        restaurant_name=restaurant_name,
        fssai_number=fssai,
        source_url=source_url,
        platform="swiggy",
        catalogue_type=catalogue_type,  # type: ignore[arg-type]
        restaurant={"name": restaurant_name, "restaurant_id": restaurant_id, "address": address, "fssai_license": fssai},
        categories=[{"name": "Mains", "items": items, "item_count": len(items)}],
        item_count=item_count if item_count is not None else len(items),
    )


def _stage(score: float, hard: bool = False) -> StageSignals:
    evidence = []
    hard_ids = []
    if hard:
        hard_ids = ["forced"]
        evidence = [
            EvidenceItem(
                category="deterministic",
                check_id="forced",
                severity="hard",
                result="fail",
                explanation="hard",
            )
        ]
    return StageSignals(score=score, evidence=evidence, hard_failures=hard_ids)


def test_deterministic_valid_and_repeated_execution():
    result = _ok_result(source_url="https://www.swiggy.com/city/sample/grade-valid-resta")
    stored = save_catalogue(user_id="user-1", organization_id="org_1", result=result)
    document = to_canonical_from_response(stored.result)
    first = grade_deterministic(document)
    second = grade_deterministic(document)
    assert first.model_dump() == second.model_dump()
    assert first.score > 50
    assert "empty_menu" not in first.hard_failures


def test_deterministic_missing_incomplete_malformed_and_boundaries():
    missing = to_canonical_from_response(
        _ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-miss-resta",
            price=None,
            description="",
            name="",
            address="",
            fssai="",
        )
    )
    missing_signals = grade_deterministic(missing)
    codes = {item.check_id for item in missing_signals.evidence if item.result == "fail"}
    assert "missing_item_name" in codes
    assert "missing_fssai" in codes
    assert "missing_address" in codes

    document = to_canonical_from_response(
        _ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-bad-price-resta",
            restaurant_id="badp",
        )
    )
    dumped = document.menus[0].categories[0].items[0].model_dump()
    dumped["price"] = "not-a-price"

    document.menus[0].categories[0].items[0] = CanonicalMenuItem.model_construct(**dumped)
    bad_price = grade_deterministic(document)
    assert any(item.check_id == "invalid_price" for item in bad_price.evidence)

    empty = to_canonical_from_response(
        CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name="Empty Place",
            fssai_number="12345678901234",
            source_url="https://www.swiggy.com/city/sample/grade-empty-resta",
            restaurant={"name": "Empty Place", "restaurant_id": "empty1", "address": "A"},
            categories=[],
            item_count=0,
        )
    )
    empty_signals = grade_deterministic(empty)
    assert "empty_menu" in empty_signals.hard_failures

    blocked = to_canonical_from_response(
        CatalogCreateResponse(
            extraction_status="blocked",
            restaurant_name="Blocked",
            fssai_number="12345678901234",
            source_url="https://www.swiggy.com/city/sample/grade-block-resta",
            error="blocked",
        )
    )
    blocked_signals = grade_deterministic(blocked)
    assert "extraction_not_ok" in blocked_signals.hard_failures


def test_hard_failure_forces_f_and_cannot_be_overridden():
    letter, score, hard = aggregate_grade(
        deterministic=_stage(100, hard=True),
        nlp=_stage(100),
        vision=_stage(100),
    )
    assert letter == "F"
    assert score == 100
    assert any(item.check_id == "hard_failure_forces_f" for item in hard)
    ordinary = aggregate_grade(deterministic=_stage(80), nlp=_stage(80), vision=_stage(80))
    assert ordinary[0] == "B"
    assert not ordinary[2]


def test_aggregate_every_letter():
    assert letter_for_score(90) == "A"
    assert letter_for_score(75) == "B"
    assert letter_for_score(60) == "C"
    assert letter_for_score(40) == "D"
    assert letter_for_score(39.99) == "F"
    assert aggregate_grade(deterministic=_stage(100), nlp=_stage(100), vision=_stage(100))[0] == "A"
    assert aggregate_grade(deterministic=_stage(80), nlp=_stage(80), vision=_stage(80))[0] == "B"
    assert aggregate_grade(deterministic=_stage(60), nlp=_stage(60), vision=_stage(60))[0] == "C"
    assert aggregate_grade(deterministic=_stage(40), nlp=_stage(40), vision=_stage(40))[0] == "D"
    assert aggregate_grade(deterministic=_stage(10), nlp=_stage(10), vision=_stage(10))[0] == "F"


def test_nlp_good_poor_empty_malformed_unicode_long_and_failure():
    nlp = NLPGrader()
    good = to_canonical_from_response(
        _ok_result(source_url="https://www.swiggy.com/city/sample/nlp-good-resta", restaurant_id="ng")
    )
    good_signals = nlp.grade(good)
    assert good_signals.score > 70
    assert 0 <= good_signals.score <= 100

    poor = to_canonical_from_response(
        _ok_result(
            source_url="https://www.swiggy.com/city/sample/nlp-poor-resta",
            restaurant_id="np",
            description="n/a",
            name="测试菜",
        )
    )
    poor_signals = nlp.grade(poor)
    assert any(item.check_id == "placeholder_text" for item in poor_signals.evidence)
    assert poor_signals.score < good_signals.score

    empty = to_canonical_from_response(
        CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name="Only Name",
            fssai_number="1",
            source_url="https://www.swiggy.com/city/sample/nlp-empty-resta",
            restaurant={"name": "Only Name", "restaurant_id": "ne"},
            categories=[],
            item_count=0,
        )
    )
    empty_signals = nlp.grade(empty)
    assert any(item.check_id == "no_item_text" for item in empty_signals.evidence)

    malformed_doc = to_canonical_from_response(
        _ok_result(
            source_url="https://www.swiggy.com/city/sample/nlp-mal-resta",
            restaurant_id="nm",
            description="***",
        )
    )
    malformed_doc.menus[0].categories[0].items[0].description = "!!!"
    malformed = nlp.grade(malformed_doc)
    assert any(item.check_id == "malformed_text" for item in malformed.evidence)

    long_doc = to_canonical_from_response(
        _ok_result(
            source_url="https://www.swiggy.com/city/sample/nlp-long-resta",
            restaurant_id="nl",
            description="word " * 20000,
        )
    )
    long_signals = nlp.grade(long_doc)
    assert any(item.check_id == "very_long_text" for item in long_signals.evidence)

    class Boom(NLPGrader):
        def grade(self, document):
            raise RuntimeError("provider down")

    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/nlp-boom-resta", restaurant_id="nb"),
    )
    with pytest.raises(GradingStageFailure):
        grade_canonical_document(
            to_canonical_from_response(stored.result),
            catalogue_id=stored.id,
            graded_head_revision=0,
            graded_state_hash="x",
            nlp_grader=Boom(),
            vision_grader=VisionGrader(fetch=lambda _url: png_bytes(100, 100)),
        )


def test_vision_valid_missing_invalid_unreadable_low_quality_multiple_fetch_ssrf():
    ok_png = png_bytes(120, 120)
    tiny = png_bytes(10, 10)
    assert inspect_image_bytes(ok_png)["status"] == "ok"
    assert inspect_image_bytes(tiny)["status"] == "low_quality"
    assert inspect_image_bytes(b"not-image")["status"] == "invalid"
    assert inspect_image_bytes(b"\x89PNG\r\n\x1a\n")["status"] == "unreadable"
    avif = inspect_image_bytes(avif_bytes(512, 512))
    assert avif["status"] == "ok"
    assert avif["format"] == "avif"
    assert avif["width"] == 512

    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/vis-ok-resta",
            restaurant_id="vo",
            image_url="https://cdn.example/ok.png",
            extra_items=[
                {
                    "name": "Extra",
                    "price": 80,
                    "description": "Side dish with enough text.",
                    "image_url": "https://cdn.example/second.png",
                    "additional_information": {"id": "m2"},
                }
            ],
        ),
    )
    document = to_canonical_from_response(stored.result)
    grader = VisionGrader(fetch=lambda url: ok_png if "ok.png" in url or "second.png" in url else None)
    ok_signals = grader.grade(document, catalogue_id=stored.id)
    assert ok_signals.score == 100
    assert sum(1 for item in ok_signals.evidence if item.check_id == "image_ok") == 2

    missing_doc = to_canonical_from_response(
        _ok_result(source_url="https://www.swiggy.com/city/sample/vis-miss-resta", restaurant_id="vm")
    )
    missing = VisionGrader(fetch=lambda _url: ok_png).grade(missing_doc, catalogue_id="x")
    assert any(item.check_id == "image_missing" for item in missing.evidence)
    assert missing.status == "completed"

    invalid = VisionGrader(fetch=lambda _url: b"nope").grade(document, catalogue_id=stored.id)
    assert any(item.check_id == "image_invalid" for item in invalid.evidence)
    assert invalid.status == "completed"

    unreadable = VisionGrader(fetch=lambda _url: b"\x89PNG\r\n\x1a\n").grade(document, catalogue_id=stored.id)
    assert any(item.check_id == "image_unreadable" for item in unreadable.evidence)
    assert unreadable.status == "completed"

    low = VisionGrader(fetch=lambda _url: tiny).grade(document, catalogue_id=stored.id)
    assert any(item.check_id == "image_low_quality" for item in low.evidence)
    assert low.status == "completed"

    failed = VisionGrader(fetch=lambda _url: None).grade(document, catalogue_id=stored.id)
    assert any(item.check_id == "image_fetch_failed" for item in failed.evidence)
    assert failed.status == "failed"

    ssrf_doc = to_canonical_from_response(
        _ok_result(
            source_url="https://www.swiggy.com/city/sample/vis-ssrf-resta",
            restaurant_id="vs",
            image_url="http://127.0.0.1/secret.png",
        )
    )
    ssrf = VisionGrader().grade(ssrf_doc, catalogue_id="x")
    assert any(item.check_id == "image_fetch_blocked" for item in ssrf.evidence)
    assert ssrf.status == "failed"

    class BoomVision(VisionGrader):
        def grade(self, document, *, catalogue_id=None):
            raise RuntimeError("vision backend failed")

    with pytest.raises(GradingStageFailure):
        grade_canonical_document(
            document,
            catalogue_id=stored.id,
            graded_head_revision=0,
            graded_state_hash="x",
            vision_grader=BoomVision(),
        )


def test_local_asset_image_and_path_confinement():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/vis-local-resta", restaurant_id="vl"),
    )
    dest = assets_root() / stored.id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "dish.png").write_bytes(png_bytes(100, 100))
    stored.result.categories[0]["items"][0]["image_url"] = f"/catalogue-assets/{stored.id}/dish.png"
    document = to_canonical_from_response(stored.result)
    signals = VisionGrader(fetch=lambda _url: None).grade(document, catalogue_id=stored.id)
    assert any(item.check_id == "image_ok" for item in signals.evidence)

    document.menus[0].categories[0].items[0].image_url = "/catalogue-assets/../dish.png"
    confined = VisionGrader(fetch=lambda _url: None).grade(document, catalogue_id=stored.id)
    assert not any(item.check_id == "image_ok" for item in confined.evidence)


def test_grade_persists_and_is_idempotent_for_same_revision():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-idemp-resta",
            restaurant_id="gi",
            image_url="https://cdn.example/ok.png",
        ),
    )
    vision = VisionGrader(fetch=lambda _url: png_bytes(120, 120))
    first = grade_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=stored.id, vision_grader=vision)
    second = grade_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=stored.id, vision_grader=vision)
    assert first.grade == second.grade
    assert first.graded_state_hash == second.graded_state_hash
    assert first.grading_metadata["grade_id"] == second.grading_metadata["grade_id"]
    connection = connect_catalogue_db()
    try:
        count = connection.execute("SELECT COUNT(*) FROM catalogue_grades WHERE catalogue_id = ?", (stored.id,)).fetchone()[0]
    finally:
        connection.close()
    assert count == 1


def test_grade_stays_on_revision_after_catalogue_change():
    url = "https://www.swiggy.com/city/sample/grade-rev-resta"
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(source_url=url, restaurant_id="gr", price=100, image_url="https://cdn.example/ok.png"),
    )
    vision = VisionGrader(fetch=lambda _url: png_bytes(120, 120))
    grade_v0 = grade_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=first.id, vision_grader=vision)
    assert grade_v0.graded_head_revision == 0
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(source_url=url, restaurant_id="gr", price=150, image_url="https://cdn.example/ok.png"),
    )
    assert second.id == first.id
    grade_v1 = grade_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=first.id, vision_grader=vision)
    assert grade_v1.graded_head_revision == 1
    assert grade_v1.graded_state_hash != grade_v0.graded_state_hash
    current = get_catalogue_grade(user_id="user-1", organization_id="org_1", catalogue_id=first.id)
    assert current is not None
    assert current.graded_state_hash == grade_v1.graded_state_hash
    connection = connect_catalogue_db()
    try:
        rows = connection.execute(
            "SELECT graded_head_revision FROM catalogue_grades WHERE catalogue_id = ? ORDER BY graded_head_revision",
            (first.id,),
        ).fetchall()
    finally:
        connection.close()
    assert [row["graded_head_revision"] for row in rows] == [0, 1]


def test_failed_grading_does_not_store_completed_a():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/grade-fail-resta", restaurant_id="gf"),
    )

    class Boom(NLPGrader):
        def grade(self, document):
            raise RuntimeError("nlp down")

    with pytest.raises(GradingStageFailure):
        grade_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=stored.id, nlp_grader=Boom())
    assert get_catalogue_grade(user_id="user-1", organization_id="org_1", catalogue_id=stored.id) is None
    connection = connect_catalogue_db()
    try:
        status = connection.execute(
            "SELECT status FROM catalogue_grade_jobs WHERE catalogue_id = ? ORDER BY created_at DESC LIMIT 1",
            (stored.id,),
        ).fetchone()
    finally:
        connection.close()
    assert status["status"] == "FAILED"


def test_cancelled_grading_is_not_completed(monkeypatch):
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-cancel-resta",
            restaurant_id="gc",
            image_url="https://cdn.example/ok.png",
        ),
    )

    def always_cancel():
        return True

    monkeypatch.setattr("backend.services.grading_service.job_is_cancelled", lambda _job_id: True)
    with pytest.raises(GradeCancelled):
        grade_catalogue(
            user_id="user-1",
            organization_id="org_1",
            catalogue_id=stored.id,
            vision_grader=VisionGrader(fetch=lambda _url: png_bytes(120, 120)),
        )
    assert get_catalogue_grade(user_id="user-1", organization_id="org_1", catalogue_id=stored.id) is None


def test_stale_running_job_can_be_reclaimed(monkeypatch):
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-stale-resta",
            restaurant_id="gs",
            image_url="https://cdn.example/ok.png",
        ),
    )
    monkeypatch.setattr("backend.grading.persist.STALE_CLAIM_SECONDS", 0)
    first_job, existing, *_a, token_a = claim_grade_job(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    assert existing is None
    second_job, existing2, *_b, token_b = claim_grade_job(user_id="user-1", organization_id="org_1", catalogue_id=stored.id)
    assert existing2 is None
    assert second_job == first_job
    assert token_a != token_b


def test_concurrent_claims_do_not_duplicate_completed_grades():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-conc-resta",
            restaurant_id="gco",
            image_url="https://cdn.example/ok.png",
        ),
    )
    vision = VisionGrader(fetch=lambda _url: png_bytes(120, 120))
    errors: list[str] = []

    def run():
        try:
            grade_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=stored.id, vision_grader=vision)
        except Exception as exc:
            errors.append(type(exc).__name__)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    connection = connect_catalogue_db()
    try:
        count = connection.execute("SELECT COUNT(*) AS n FROM catalogue_grades WHERE catalogue_id = ?", (stored.id,)).fetchone()["n"]
    finally:
        connection.close()
    assert count == 1
    assert not any(name not in {"GradeInProgress", "StaleClaim"} for name in errors)


def test_delete_catalogue_removes_grades():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-del-resta",
            restaurant_id="gd",
            image_url="https://cdn.example/ok.png",
        ),
    )
    grade_catalogue(
        user_id="user-1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=VisionGrader(fetch=lambda _url: png_bytes(120, 120)),
    )
    assert delete_catalogue("user-1", stored.id, "org_1") is True
    connection = connect_catalogue_db()
    try:
        grades = connection.execute("SELECT COUNT(*) AS n FROM catalogue_grades WHERE catalogue_id = ?", (stored.id,)).fetchone()["n"]
        jobs = connection.execute("SELECT COUNT(*) AS n FROM catalogue_grade_jobs WHERE catalogue_id = ?", (stored.id,)).fetchone()["n"]
    finally:
        connection.close()
    assert grades == 0
    assert jobs == 0


def test_grade_api_authz_and_structured_response():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-api-resta",
            restaurant_id="ga",
        ),
    )
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        denied = client.post(f"/catalogues/{stored.id}/grade", params={"organization_id": "org_stranger"})
        assert denied.status_code == 403
        missing = client.post("/catalogues/nope/grade", params={"organization_id": "org_1"})
        assert missing.status_code == 404
        response = client.post(f"/catalogues/{stored.id}/grade", params={"organization_id": "org_1"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["grade"] in {"A", "B", "C", "D", "F"}
        assert "deterministic_evidence" in body
        assert body["catalogue_id"] == stored.id
        fetched = client.get(f"/catalogues/{stored.id}/grade", params={"organization_id": "org_1"})
        assert fetched.status_code == 200
        listed = client.get("/catalogues", params={"organization_id": "org_1"})
        assert listed.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_phase3_ddl_does_not_repeat_phase1_backfill(tmp_path, monkeypatch):
    db = tmp_path / "phase3.sqlite"
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
    assert "catalogue_grades" in names
    assert "catalogue_grade_jobs" in names


def test_ingest_does_not_require_grading():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(source_url="https://www.swiggy.com/city/sample/grade-ingest-resta", restaurant_id="gin"),
    )
    assert stored.result.extraction_status == "ok"
    assert get_catalogue_grade(user_id="user-1", organization_id="org_1", catalogue_id=stored.id) is None


def test_cancellation_mid_pipeline_does_not_emit_letter_a():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-mid-resta",
            restaurant_id="gm",
            image_url="https://cdn.example/ok.png",
        ),
    )
    calls = {"n": 0}

    def cancel_after_det():
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(GradingCancelled):
        grade_canonical_document(
            to_canonical_from_response(stored.result),
            catalogue_id=stored.id,
            graded_head_revision=0,
            graded_state_hash="hash",
            cancel_check=cancel_after_det,
            vision_grader=VisionGrader(fetch=lambda _url: png_bytes(120, 120)),
        )


def _vision_ok():
    return VisionGrader(fetch=lambda _url: png_bytes(120, 120))


def test_fetch_failure_fails_job_not_quality_grade():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-fetchfail-resta",
            restaurant_id="gff",
            image_url="https://cdn.example/ok.png",
        ),
    )
    with pytest.raises(GradingStageFailure):
        grade_catalogue(
            user_id="user-1",
            organization_id="org_1",
            catalogue_id=stored.id,
            vision_grader=VisionGrader(fetch=lambda _url: None),
        )
    assert get_catalogue_grade(user_id="user-1", organization_id="org_1", catalogue_id=stored.id) is None
    connection = connect_catalogue_db()
    try:
        status = connection.execute(
            "SELECT status FROM catalogue_grade_jobs WHERE catalogue_id = ? ORDER BY created_at DESC LIMIT 1",
            (stored.id,),
        ).fetchone()
        grades = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_grades WHERE catalogue_id = ?", (stored.id,)
        ).fetchone()["n"]
    finally:
        connection.close()
    assert status["status"] == "FAILED"
    assert grades == 0


def test_poor_quality_image_still_completes():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-lowimg-resta",
            restaurant_id="glq",
            image_url="https://cdn.example/tiny.png",
        ),
    )
    result = grade_catalogue(
        user_id="user-1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=VisionGrader(fetch=lambda _url: png_bytes(10, 10)),
    )
    assert result.grade in {"A", "B", "C", "D", "F"}
    assert any(item.check_id == "image_low_quality" for item in result.vision_evidence)
    assert get_catalogue_grade(user_id="user-1", organization_id="org_1", catalogue_id=stored.id) is not None


def test_duplicate_image_urls_fetched_once():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-dupimg-resta",
            restaurant_id="gdu",
            image_url="https://cdn.example/same.png",
            extra_items=[
                {
                    "name": "Second",
                    "price": 80,
                    "description": "Another dish with a description.",
                    "image_url": "https://cdn.example/same.png",
                    "additional_information": {"id": "m2"},
                }
            ],
        ),
    )
    calls = {"n": 0}

    def fetch(_url: str) -> bytes:
        calls["n"] += 1
        return png_bytes(120, 120)

    document = to_canonical_from_response(stored.result)
    signals = VisionGrader(fetch=fetch).grade(document, catalogue_id=stored.id)
    assert calls["n"] == 1
    assert signals.status == "completed"
    assert signals.score == 100


def test_remote_image_budget_is_a_processing_failure():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-budget-resta",
            restaurant_id="gb",
            image_url="https://cdn.example/one.png",
            extra_items=[
                {
                    "name": "Two",
                    "price": 80,
                    "description": "Second dish description text.",
                    "image_url": "https://cdn.example/two.png",
                    "additional_information": {"id": "m2"},
                },
                {
                    "name": "Three",
                    "price": 80,
                    "description": "Third dish description text.",
                    "image_url": "https://cdn.example/three.png",
                    "additional_information": {"id": "m3"},
                },
            ],
        ),
    )
    calls = {"n": 0}

    def fetch(_url: str) -> bytes:
        calls["n"] += 1
        return png_bytes(120, 120)

    document = to_canonical_from_response(stored.result)
    signals = VisionGrader(fetch=fetch, max_remote_images=2).grade(document, catalogue_id=stored.id)
    assert signals.status == "failed"
    assert any(item.check_id == "image_fetch_budget_exceeded" for item in signals.evidence)
    assert calls["n"] == 2


def test_vision_timeout_and_oversized_are_processing_failures():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-timeout-resta",
            restaurant_id="gt",
            image_url="https://cdn.example/ok.png",
        ),
    )
    document = to_canonical_from_response(stored.result)

    def boom_timeout(_url: str) -> bytes:
        raise TimeoutError("slow")

    timed = VisionGrader(fetch=boom_timeout).grade(document, catalogue_id=stored.id)
    assert timed.status == "failed"
    assert any(item.check_id == "image_fetch_timeout" for item in timed.evidence)

    huge = VisionGrader(fetch=lambda _url: b"x" * 64, max_bytes=16).grade(document, catalogue_id=stored.id)
    assert huge.status == "failed"
    assert any(item.check_id == "image_oversized" for item in huge.evidence)


def test_stale_worker_cannot_overwrite_reclaimed_claim(monkeypatch):
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-cas-resta",
            restaurant_id="gcas",
            image_url="https://cdn.example/ok.png",
        ),
    )
    monkeypatch.setattr("backend.grading.persist.STALE_CLAIM_SECONDS", 0)
    job_id, existing, _snap, revision, state_hash, token_a = claim_grade_job(
        user_id="user-1", organization_id="org_1", catalogue_id=stored.id
    )
    assert existing is None
    job_b, existing_b, _snap_b, revision_b, hash_b, token_b = claim_grade_job(
        user_id="user-1", organization_id="org_1", catalogue_id=stored.id
    )
    assert job_b == job_id
    assert existing_b is None
    assert token_a != token_b
    document = to_canonical_from_response(stored.result)
    result = grade_canonical_document(
        document,
        catalogue_id=stored.id,
        graded_head_revision=revision,
        graded_state_hash=state_hash,
        vision_grader=_vision_ok(),
    )
    with pytest.raises(StaleClaim):
        finish_grade_job(
            job_id=job_id,
            user_id="user-1",
            organization_id="org_1",
            catalogue_id=stored.id,
            expected_head_revision=revision,
            expected_state_hash=state_hash,
            claim_token=token_a,
            result=result,
            status="COMPLETED",
        )
    with pytest.raises(StaleClaim):
        finish_grade_job(
            job_id=job_id,
            user_id="user-1",
            organization_id="org_1",
            catalogue_id=stored.id,
            expected_head_revision=revision,
            expected_state_hash=state_hash,
            claim_token=token_a,
            result=None,
            status="FAILED",
            error="nope",
        )
    with pytest.raises(StaleClaim):
        finish_grade_job(
            job_id=job_id,
            user_id="user-1",
            organization_id="org_1",
            catalogue_id=stored.id,
            expected_head_revision=revision,
            expected_state_hash=state_hash,
            claim_token=token_a,
            result=None,
            status="CANCELLED",
        )
    persisted = finish_grade_job(
        job_id=job_b,
        user_id="user-1",
        organization_id="org_1",
        catalogue_id=stored.id,
        expected_head_revision=revision_b,
        expected_state_hash=hash_b,
        claim_token=token_b,
        result=result,
        status="COMPLETED",
    )
    assert persisted is not None
    connection = connect_catalogue_db()
    try:
        job = connection.execute("SELECT status, claim_token FROM catalogue_grade_jobs WHERE id = ?", (job_id,)).fetchone()
        grades = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_grades WHERE catalogue_id = ?", (stored.id,)
        ).fetchone()["n"]
    finally:
        connection.close()
    assert job["status"] == "COMPLETED"
    assert job["claim_token"] == token_b
    assert grades == 1


def test_unexpected_integrity_error_marks_job_failed(monkeypatch):
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-integrity-resta",
            restaurant_id="ginteg",
            image_url="https://cdn.example/ok.png",
        ),
    )
    job_id, existing, _snap, revision, state_hash, token = claim_grade_job(
        user_id="user-1", organization_id="org_1", catalogue_id=stored.id
    )
    assert existing is None
    document = to_canonical_from_response(stored.result)
    result = grade_canonical_document(
        document,
        catalogue_id=stored.id,
        graded_head_revision=revision,
        graded_state_hash=state_hash,
        vision_grader=_vision_ok(),
    )
    from backend.grading import persist as persist_mod

    real_connect = persist_mod.connect_catalogue_db

    class ConnProxy:
        def __init__(self, real):
            object.__setattr__(self, "_real", real)

        def execute(self, sql, *args):
            if isinstance(sql, str) and "INSERT INTO catalogue_grades" in sql:
                raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")
            return self._real.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __setattr__(self, name, value):
            setattr(self._real, name, value)

    monkeypatch.setattr(persist_mod, "connect_catalogue_db", lambda: ConnProxy(real_connect()))
    with pytest.raises(GradePersistenceError):
        finish_grade_job(
            job_id=job_id,
            user_id="user-1",
            organization_id="org_1",
            catalogue_id=stored.id,
            expected_head_revision=revision,
            expected_state_hash=state_hash,
            claim_token=token,
            result=result,
            status="COMPLETED",
        )
    connection = connect_catalogue_db()
    try:
        job = connection.execute("SELECT status FROM catalogue_grade_jobs WHERE id = ?", (job_id,)).fetchone()
        grades = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_grades WHERE catalogue_id = ?", (stored.id,)
        ).fetchone()["n"]
    finally:
        connection.close()
    assert job["status"] == "FAILED"
    assert grades == 0


def test_duplicate_completed_grade_is_idempotent_on_finish():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-dupfin-resta",
            restaurant_id="gdf",
            image_url="https://cdn.example/ok.png",
        ),
    )
    first = grade_catalogue(user_id="user-1", organization_id="org_1", catalogue_id=stored.id, vision_grader=_vision_ok())
    _job_id, existing, _snap, _revision, _state_hash, token = claim_grade_job(
        user_id="user-1", organization_id="org_1", catalogue_id=stored.id
    )
    assert existing is not None
    assert existing.grading_metadata["grade_id"] == first.grading_metadata["grade_id"]
    assert token == ""


def test_grade_api_fetch_failure_is_not_http_success():
    stored = save_catalogue(
        user_id="user_1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/grade-api-fail-resta",
            restaurant_id="gaf",
            image_url="https://cdn.example/ok.png",
        ),
    )
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="o@example.com")
    try:
        response = client.post(f"/catalogues/{stored.id}/grade", params={"organization_id": "org_1"})
        assert response.status_code == 502
        missing = client.get(f"/catalogues/{stored.id}/grade", params={"organization_id": "org_1"})
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
    connection = connect_catalogue_db()
    try:
        job = connection.execute(
            "SELECT status FROM catalogue_grade_jobs WHERE catalogue_id = ? ORDER BY created_at DESC LIMIT 1",
            (stored.id,),
        ).fetchone()
        grades = connection.execute(
            "SELECT COUNT(*) AS n FROM catalogue_grades WHERE catalogue_id = ?", (stored.id,)
        ).fetchone()["n"]
    finally:
        connection.close()
    assert job["status"] == "FAILED"
    assert grades == 0


def test_nlp_stage_score_stays_on_unit_scale_for_many_fields():
    extra = [
        {
            "name": f"Dish {index}",
            "price": 80,
            "description": "A full sentence describing this vegetarian south indian dish for lunch.",
            "image_url": f"https://cdn.example/d{index}.png",
            "additional_information": {"id": f"m{index}"},
        }
        for index in range(40)
    ]
    document = to_canonical_from_response(
        _ok_result(
            source_url="https://www.swiggy.com/city/sample/nlp-scale-resta",
            restaurant_id="nscale",
            extra_items=extra,
        )
    )
    score = NLPGrader().grade(document).score
    assert 0 <= score <= 100


def test_combine_scores_does_not_treat_illegal_nlp_as_extra_credit():
    assert combine_scores(69.0, 3829.7212, 0.0) == 59.5
    assert letter_for_score(combine_scores(69.0, 3829.7212, 0.0)) == "D"


def test_out_of_range_persisted_nlp_is_recomputed_on_regrade():
    stored = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok_result(
            source_url="https://www.swiggy.com/city/sample/nlp-recompute-resta",
            restaurant_id="nre",
            image_url="https://cdn.example/ok.png",
        ),
    )
    first = grade_catalogue(
        user_id="user-1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=_vision_ok(),
    )
    assert 0 <= first.signals["nlp"] <= 100
    connection = connect_catalogue_db()
    try:
        row = connection.execute(
            "SELECT payload FROM catalogue_grades WHERE catalogue_id = ? AND status = 'COMPLETED'",
            (stored.id,),
        ).fetchone()
        payload = json.loads(row["payload"])
        payload["signals"]["nlp"] = 3829.7212
        payload["score"] = 100.0
        payload["grade"] = "A"
        connection.execute(
            "UPDATE catalogue_grades SET payload = ? WHERE catalogue_id = ? AND status = 'COMPLETED'",
            (json.dumps(payload), stored.id),
        )
        connection.commit()
    finally:
        connection.close()
    assert get_catalogue_grade(user_id="user-1", organization_id="org_1", catalogue_id=stored.id) is None
    recomputed = grade_catalogue(
        user_id="user-1",
        organization_id="org_1",
        catalogue_id=stored.id,
        vision_grader=_vision_ok(),
    )
    assert 0 <= recomputed.signals["nlp"] <= 100
    assert recomputed.signals["nlp"] != 3829.7212

