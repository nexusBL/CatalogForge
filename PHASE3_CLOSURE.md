# Phase 3 — Baba Grading Engine
Status: PASS — CLOSED

This is the official Phase 3 handoff for future phases.

Do NOT make further Phase 3 changes unless a future official phase identifies a concrete defect or required dependency.

==================================================
PROJECT PHASE STATUS
==================================================

PHASE 0 — PASS / CLOSED

PHASE 1 — PASS / CLOSED

PHASE 2 — PASS / CLOSED

PHASE 3 — PASS / CLOSED

Phase 4 has not started.

Phase 0, Phase 1, Phase 2, and Phase 3 are closed baselines. Do not reopen or modify them unless the official requirements of a future phase explicitly require a change.

==================================================
## Purpose
==================================================

Determine catalogue quality.

==================================================
## Architecture
==================================================

Canonical Catalogue
        ↓
Deterministic Rules
        ↓
NLP / Vision
        ↓
Grading Engine
        ↓
A / B / C / D / F
        +
Evidence

Production path:

`POST /catalogues/{id}/grade` (session + organization membership)
        ↓
load stored canonical catalogue (Phase 1 persist; not a second ingest path)
        ↓
claim job (`BEGIN IMMEDIATE`, `claim_token`)
        ↓
deterministic → local NLP → local vision (network/image I/O outside the DB transaction)
        ↓
aggregate A–F + evidence (`grading.v1`)
        ↓
persist `catalogue_grades` then mark job COMPLETED only if the grade row exists

`GET /catalogues/{id}/grade` returns the completed grade for the current head revision and state hash.

Grading is not invoked from `POST /catalog/create`.

==================================================
## Deterministic grading
==================================================

Implemented in `backend/grading/deterministic.py`. Rule-based, reproducible, no fuzzy matching.

Hard failures (any one forces letter F at aggregation):

- `extraction_not_ok` — `extraction_status` is not `ok`
- `missing_restaurant_name` — restaurant name missing when extraction is ok
- `missing_source_url` — source URL missing when extraction is ok
- `empty_menu` — restaurant or both catalogue has no menu items when extraction is ok

Ordinary deductions (capped; reduce the deterministic score, do not by themselves force F):

- `missing_fssai`
- `missing_address`
- `missing_category_name`
- `category_count_mismatch`
- `missing_item_name`
- `missing_price`
- `invalid_price` (selling price or MRP)
- `missing_item_image`
- `missing_description`

==================================================
## NLP grading
==================================================

Approved Phase 3 implementation: local/on-host text-content quality heuristics in `backend/grading/nlp.py`.

Covered:

- description coverage
- placeholder detection
- exact-repeat descriptions (not fuzzy)
- malformed/empty text handling
- Unicode handling
- long-text handling (analysis cap; grading still completes)

No external NLP provider.

No neural/LLM model required for Phase 3.

==================================================
## Vision grading
==================================================

Approved Phase 3 implementation: local image analysis in `backend/grading/vision.py`.

Covered:

- image decoding
- supported format checks (PNG/JPEG/GIF/WebP)
- dimensions
- image size
- missing / invalid / unreadable / low-quality detection
- SSRF-safe remote fetching (`assert_public_http_url`, `fetch_public_http_bytes`)
- duplicate URL caching (unique URLs fetched once)
- remote image count bound (default 500; `CATALOGFORGE_GRADE_MAX_REMOTE_IMAGES`)
- byte limit (8MB, shared `MAX_BYTES`)
- timeout (15 seconds, shared `DEFAULT_TIMEOUT`)
- local `/catalogue-assets/` path confinement

Quality findings complete the vision stage and contribute to the score.

Processing failures (`ssrf`, `fetch_failed`, `processing_failed`, `oversized`, `timeout`, `budget_exceeded`) fail the stage and the job. They must not produce a successful COMPLETED grade.

No external vision provider.

No neural CV model required for Phase 3.

==================================================
## Grading formula
==================================================

Official approved Phase 3 formula (`ENGINE_VERSION = grading.v1`):

Deterministic = 50%
NLP = 25%
Vision = 25%

A >= 90
B >= 75
C >= 60
D >= 40
F < 40

Engine version:

grading.v1

Do not replace this formula in place. Changing weights or thresholds requires a new `ENGINE_VERSION` and explicit product approval. Do not create `grading.v2` without that approval.

==================================================
## Hard failures
==================================================

Any evidence item with `severity=hard` and `result=fail` forces letter **F**, regardless of combined score.

Implemented hard-failure conditions (deterministic):

- extraction not ok
- missing restaurant name
- missing source URL
- empty restaurant/both menu

Aggregation records `hard_failure_forces_f` in addition to the originating checks.

Ordinary quality failures only reduce scores.

==================================================
## Structured evidence
==================================================

Each finding is an `EvidenceItem`:

- category
- check_id
- severity
- result
- explanation
- path
- details

Persisted on `GradingResult` as `deterministic_evidence`, `nlp_evidence`, `vision_evidence`, and `hard_failures`. Stored in `catalogue_grades.payload`.

==================================================
## Persistence
==================================================

Additive tables (Phase 1 migrator id unchanged: `phase1_canonical_v1`):

- `catalogue_grades`
- `catalogue_grade_jobs`

Identity / idempotency key:

`catalogue_id` + `graded_head_revision` + `graded_state_hash` + `engine_version`

- `graded_head_revision` = `MAX(catalogue_revisions.revision)` for that catalogue
- `graded_state_hash` = SHA-256 of the Phase 1 canonical state payload
- `engine_version` = `grading.v1`

Unique completed grades and unique running jobs are enforced by partial unique indexes.

Repeating grade for the same identity returns the existing completed result.

Deleting a catalogue also deletes its grade jobs and grades.

==================================================
## Concurrency
==================================================

- `BEGIN IMMEDIATE` on claim and finish
- Snapshot of catalogue payload, head revision, and state hash under that lock
- `claim_token` issued on claim / reclaim
- Finish COMPLETED / FAILED / CANCELLED uses CAS: `status = 'RUNNING' AND claim_token = ?`
- Zero rows → `StaleClaim` (HTTP 409); the worker must not overwrite another claim
- Stale RUNNING jobs may be reclaimed with token rotation
- Concurrent grade of the same identity: in-flight → 409; completed → return existing row
- Concurrent catalogue revision changes the identity; a finish against a stale snapshot is rejected
- Concurrent delete: missing catalogue is not a successful grade

==================================================
## Error handling
==================================================

- Job **FAILED** on NLP/vision/deterministic stage failure, vision processing failure, and persistence failure
- Stale claim → safe rejection (`StaleClaim`, HTTP 409)
- Cancellation → job CANCELLED when the owning claim still holds; HTTP 409 to the caller
- Unexpected exceptions must not report canonical success
- **COMPLETED requires a persisted valid grade row.** `get_completed_grade` must confirm the row before (and after) marking the job COMPLETED. Unexpected `IntegrityError` without a duplicate row marks FAILED. The service refuses a COMPLETED finish that returns no payload.

==================================================
## Security
==================================================

- Session required on grade POST/GET
- Organization membership required (`require_organization_member`)
- Catalogue scoped by user + organization
- SSRF protection on remote image URLs
- Local asset paths confined under catalogue assets
- Parameterized SQL
- Remote image count, byte, and timeout limits
- External HTTP details for stage/persist failure: generic 502 (`Grading could not be completed.`)

==================================================
## Performance
==================================================

- Duplicate URL caching (one fetch per unique remote URL)
- 500 default remote-image limit
- 8MB image limit
- 15-second timeout
- Network fetch outside the DB transaction
- No per-item SQL N+1 (document is snapshotted once; graders iterate in memory)

==================================================
## Tests
==================================================

Closure verification (2026-08-20), working directory CatalogForge:

1. `python -m pytest tests/test_phase3_grading.py -q --tb=line` — **27 passed**
2. `python -m pytest -q --tb=line` — **323 passed**
3. `python -m compileall backend scraper tests -q` — **PASS** (exit 0)

`ruff`, `mypy`, `pyright`, `flake8`, `pylint` were not installed in this environment and are not claimed.

Frontend has no grading UI or grade tests; frontend suite was not required for this closure.

==================================================
## Backward compatibility
==================================================

Phase 0 remains closed.

Phase 1 remains closed.

Phase 2 remains closed.

No Phase 0–2 architecture or contracts were reopened.

Preserved:

- Phase 1 catalogue identity, revision semantics, persistence, and migration id
- Phase 2 normalization, raw capture, adapter boundary, and ingestion path
- Phase 0 security, concurrency, cancellation, crash-recovery, and idempotency guarantees as they apply to ingest

Phase 3 is additive and downstream.

==================================================
## Scope exclusions
==================================================

Phase 3 does NOT include:

- recommendations
- auto-correction
- ranking
- fuzzy identity
- cross-platform identity
- scraper rewrite
- persistence rewrite
- Phase 4 functionality
- neural/LLM NLP
- neural computer-vision models
- external NLP/vision providers
- `grading.v2`

==================================================
PHASE 3 CLOSURE RULE
==================================================

PHASE 3 IS CLOSED.

Future chats MUST treat Phase 3 as an established baseline.

Do not reopen Phase 3 for cosmetic improvements, unrelated debt, speculative refactoring, architecture experiments, or later-phase functionality.

Do not change `grading.v1` casually. Formula changes require a new `ENGINE_VERSION` and explicit product approval. Substantial new grading capability belongs to a future approved phase.

If a future phase requires a change:

1. Identify the exact requirement from that phase's official roadmap.
2. Explain why Phase 3 behavior must change.
3. Preserve Phase 3 guarantees wherever possible.
4. Do not silently reopen Phase 3.

PHASE 4 HAS NOT STARTED.

Do not implement Phase 4 until its official roadmap is provided, audited, planned, reviewed, and explicitly approved.

Related records:

- `PHASE1_CLOSURE.md`
- `PHASE2_CLOSURE.md`
- `.cursor/rules/phase1-closed.mdc`
- `.cursor/rules/phase2-closed.mdc`
- `.cursor/rules/phase3-closed.mdc`
- `AGENT.md`

END OF PHASE 3 CLOSURE RECORD.
