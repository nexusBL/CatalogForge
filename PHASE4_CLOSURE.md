# Phase 4 — Baba Score + Platform Evaluation
Status: PASS — CLOSED

This is the official Phase 4 handoff for future phases.

Do NOT make further Phase 4 changes unless a future official phase identifies a concrete defect or required dependency.

==================================================
PROJECT PHASE STATUS
==================================================

PHASE 0 — PASS / CLOSED

PHASE 1 — PASS / CLOSED

PHASE 2 — PASS / CLOSED

PHASE 3 — PASS / CLOSED

PHASE 4 — PASS / CLOSED

PHASE 5 — NOT STARTED

Phase 0, Phase 1, Phase 2, and Phase 3 remain closed baselines. Phase 4 did not reopen them.

==================================================
## 1. Purpose
==================================================

Separate Baba's own evaluation from platform-native signals.

Official name: Baba Score + Platform Evaluation.

==================================================
## 2. Official scope
==================================================

Implemented:

- platform evaluation adapter interface and registry
- Swiggy, Zomato, and Magicpin adapters
- platform-specific rules isolated per adapter
- platform-native scores/rules as EVIDENCE
- Baba Score as an independent projection of `grading.v1`

Explicitly not implemented (deferred / out of scope):

- detailed score calibration or blending
- copying platform ratings into Baba Score
- live platform HTTP
- agents / LLM orchestration
- Phase 5 work

==================================================
## 3. Architecture
==================================================

```
SOURCE → INGESTION → RAW → NORMALIZATION → CANONICAL CATALOGUE
                                                    |
                                              grading.v1 (unchanged)
                                                    |
                          +-------------------------+-------------------------+
                          |                                                   |
                     BABA SCORE                                    PLATFORM EVALUATION
                     (projection of                                 adapter registry
                      grading.v1)                                         |
                                                           Swiggy / Zomato / Magicpin
                                                                          |
                                                                  PLATFORM EVIDENCE
```

Phase 4 is downstream of Phase 1 persist and sibling to Phase 3 grading. It is not invoked from `POST /catalog/create`. It does not modify `grading.v1`.

Production path:

`POST /catalogues/{id}/platform-evaluation` (session + organization membership)
        ↓
snapshot stored canonical catalogue (`BEGIN IMMEDIATE`; hash after COMMIT)
        ↓
resolve applicable platforms via adapter registry (no scattered if/elif)
        ↓
run platform adapters in memory (no live platform HTTP)
        ↓
persist `catalogue_platform_evaluations` under `BEGIN IMMEDIATE`
        ↓
UNIQUE duplicate → existing COMPLETED row; FK failure → missing catalogue; other IntegrityError → persist failure
        ↓
attach Baba Score only if a completed `grading.v1` row exists (read-only projection)

==================================================
## 4. Baba Score independence invariant
==================================================

    Platform Score != Baba Score

Baba Score is a labeled projection of Phase 3 `grading.v1` only:

- `kind = baba_score`
- `source = grading.v1`
- `independent_of_platform = true`
- letter and numerical score from `catalogue_grades`

It is never computed from Swiggy, Zomato, or Magicpin ratings.

Platform evaluation payloads set `baba_score = null`. Persist refuses a non-null Baba Score on a platform row. Phase 4 does not write `catalogue_grades`.

==================================================
## 5. Platform adapters
==================================================

Interface: `PlatformEvaluationAdapter` (`backend/platform_eval/adapters/base.py`).

Registry: `backend/platform_eval/adapters/registry.py`.

Implemented:

- `swiggy.platform_eval.v1` — primary / dining / delivery native ratings, counts, declared 0–5 observation scale, item ratings, source-listing flag
- `zomato.platform_eval.v1` — native or listed Zomato ratings, dining/delivery split, listed-on-foreign-listing, declared scale
- `magicpin.platform_eval.v1` — native or listed Magicpin ratings, listing-score observation, listed-on-foreign-listing, declared scale

Each adapter consumes already-stored canonical/platform evidence. Adapters do not mutate Baba Score and do not overwrite another platform's row (identity includes `platform`).

Unsupported platform → `UnsupportedPlatform` → HTTP 422.

Default POST evaluates the source platform always, plus other registered platforms only when native signals or related links exist.

The declared 0–5 check is an observation of common ingested food-app scales. It is **not** calibration into Baba's 0–100 / A–F scale.

==================================================
## 6. Platform evidence model
==================================================

Each persisted evaluation is `kind = platform_evidence` (`PlatformEvaluation`):

- `platform`, `adapter_id`, `evaluation_version` (`platform_eval.v1`)
- `native_signals` (parsed score/count/path/parseable/in_declared_scale)
- structured `evidence` items (check_id, result pass/fail/skip, explanation)
- `source_listing` (whether this platform owns the catalogue listing)
- `baba_score` always null

Missing or malformed native data is represented as evidence, not as a Baba letter.

==================================================
## 7. Evaluation identity
==================================================

`catalogue_id` + `evaluated_head_revision` + `evaluated_state_hash` + `platform` + `platform_eval.v1`

- `evaluated_head_revision` = `MAX(catalogue_revisions.revision)`
- `evaluated_state_hash` = SHA-256 of the Phase 1 canonical state payload (same helper as Phase 3)
- `evaluation_version` = `platform_eval.v1`

==================================================
## 8. APIs
==================================================

Authorization matches catalogue/grade routes: session authentication, organization membership, catalogue scoped to user + organization.

- `POST /catalogues/{id}/platform-evaluation` — compute and persist platform evidence for applicable (or requested) platforms. Query `platform` may be repeated; unknown platform is 422.
- `GET /catalogues/{id}/platform-evaluation` — completed evidence for the current head revision and state hash. **HTTP 200 with `platform_evaluations: []`** means the catalogue exists and no evaluation row has been stored yet. That empty list is the contract (not 404). `baba_score` is null until a completed `grading.v1` row exists.
- `GET /catalogues/{id}/baba-score` — Baba Score projection only. 404 if no completed grade for this revision.

Not invoked from ingest. No Phase 4 frontend UI. No public cancel-evaluation route.

Error mapping (POST):

- missing catalogue / FK after delete → 404
- unsupported platform → 422
- stale catalogue revision/hash → 409
- persist failure, corrupt stored payload, adapter stage failure → 502 (`Platform evaluation could not be completed.`)
- unauthenticated → 401
- wrong organization → 403

==================================================
## 9. Database changes
==================================================

Additive table (Phase 1 migrator id unchanged: `phase1_canonical_v1`):

- `catalogue_platform_evaluations`

Partial unique index on COMPLETED identity:

`(catalogue_id, evaluated_head_revision, evaluated_state_hash, platform, evaluation_version) WHERE status = 'COMPLETED'`

Foreign key: `catalogue_id` → `catalogues(id)`.

`status` is always written as `COMPLETED`. Phase 4 has no FAILED/RUNNING evaluation-job lifecycle; the column is retained only for a possible later lifecycle, not as a second grading-job state machine.

Deleting a catalogue also deletes its platform evaluations (`store.delete_catalogue`). Additive DDL via `ensure_phase4_ddl`; no Phase 1 backfill rewrite.

==================================================
## 10. Concurrency / atomicity
==================================================

- `BEGIN IMMEDIATE` on snapshot and persist
- persist re-reads catalogue revision and state hash in the same transaction as INSERT
- exception after BEGIN → explicit ROLLBACK, then re-raise (does not rely on connection close)
- UNIQUE conflict → load existing COMPLETED row (idempotent)
- FOREIGN KEY failure → not treated as a duplicate; rollback; missing-catalogue error
- unexpected IntegrityError → rollback; persist failure (502)
- concurrent same-identity evaluates: one INSERT wins; the other unique-conflicts or sees the row
- concurrent catalogue revision: persist against a stale snapshot → `StaleCatalogueState` (HTTP 409)

Phase 3 `claim_token` jobs were not copied. Evaluation is CPU-only from stored canonical data.

==================================================
## 11. Idempotency
==================================================

Repeating POST for the same identity returns the existing COMPLETED payload and does not create a second row.

A new catalogue revision or state hash is a new identity. A different platform is a different row. Compute failure before INSERT leaves no row; retry may insert. COMPLETED then retry returns the existing row.

==================================================
## 12. Security
==================================================

- Session required
- Organization membership required
- Catalogue scoped by user + organization
- **No live platform HTTP in Phase 4** (no new SSRF surface)
- Parameterized SQL
- Platform identifiers restricted to the adapter registry
- Generic 502 for persist/adapter/corrupt-payload failure (no internal SQLite/Pydantic dump to the client)

==================================================
## 13. Error handling
==================================================

- Missing / unauthorized catalogue → 404 / 403 (same class as other catalogue endpoints)
- Unsupported platform → 422
- Stale revision → 409
- Corrupt stored catalogue or evaluation JSON → persist error → 502 (not client 422)
- Adapter exception → `PlatformEvalStageFailure` → 502; no evaluation row
- Missing native scores → COMPLETED evidence fail/skip
- Malformed native scores → evidence `parseable=false`
- No Phase 4 `except Exception: pass` on the success path
- Rollback failure is attached to the original exception (`add_note`); the original error is preserved

==================================================
## 14. Performance
==================================================

- No per-item SQL (document snapshotted once; adapters iterate in memory)
- One SELECT loads all platform evaluation rows for a catalogue identity
- No network inside database transactions
- Snapshot hashing runs after COMMIT on the copied payload
- Persist hashing remains inside the write lock so stale detection and INSERT share one transaction
- No caching added
- N+1: not introduced (no per-item DB or network)

==================================================
## 15. Tests and exact results
==================================================

Closure verification (2026-08-20), working directory CatalogForge.

Focused tests include Baba Score independence, adapter isolation, unique vs FK IntegrityError, explicit rollback, stale persist 409, adapter 502, unauthenticated 401, corrupt payload 502, GET empty-list 200, concurrent duplicate-row, delete cascade, and org isolation.

Recorded after remediation and again at official closure:

1. `python -m pytest tests/test_phase3_grading.py tests/test_phase4_platform_eval.py -q --tb=line` — **52 passed**
2. `python -m pytest -q --tb=line` — **348 passed**
3. `python -m compileall backend scraper tests -q` — **PASS** (exit 0)

`ruff`, `mypy`, `pyright`, `flake8`, `pylint` were not installed. Static type checking: **NOT AVAILABLE IN ENVIRONMENT**. Compileall is bytecode compile only.

Frontend was not changed; frontend suite was not required for this closure.

==================================================
## 16. Audit results
==================================================

Independent adversarial audit found P0/P1 issues (UNIQUE vs FK mapping, missing explicit rollback on KeyError, broad POST `ValueError` → 422, dead code, incomplete failure-path tests). Remediation fixed those without redesigning Phase 4 or reopening Phase 0–3.

Post-remediation / closure categories:

1. Closed-phase integrity — **PASS** (`grading.v1` unchanged)
2. Baba Score independence — **PASS**
3. Platform adapter isolation — **PASS**
4. Database correctness — **PASS**
5. Transactions / rollback — **PASS**
6. Race conditions — **PASS**
7. Atomicity — **PASS**
8. Idempotency — **PASS**
9. N+1 — **PASS**
10. Uncaught errors / API mapping — **PASS** after remediation
11. Security — **PASS**
12. Type safety — **NOT AVAILABLE IN ENVIRONMENT**
13. Dead code — **PASS** after remediation
14. Performance — **PASS** (persist hash under lock retained for correctness)
15. Test coverage of failure paths — **PASS** after remediation
16. Full regression — **PASS** (348)

==================================================
## 17. Known limitations
==================================================

- No FAILED/RUNNING evaluation jobs; `status` is always COMPLETED.
- Persist hashing is inside `BEGIN IMMEDIATE` (required for stale check + INSERT atomicity).
- GET `/platform-evaluation` returns 200 and an empty list when unevaluated; GET `/baba-score` / GET `/grade` 404 when no grade exists.
- No Phase 4 UI.
- Related/listed ratings on a foreign listing are evidence for that platform, not a second canonical venue.
- Static type checkers were not available at closure.

These limitations are not automatic Phase 5 work.

==================================================
## 18. Explicitly deferred calibration
==================================================

Detailed score calibration is deferred. Do not invent formulas that map platform 0–5 ratings onto Baba 0–100 or A–F. Do not blend platform scores into `grading.v1`.

==================================================
## 19. Explicitly out of scope
==================================================

Phase 4 does NOT include:

- detailed calibration / Baba–platform blending
- live platform API calls
- LLM agents, agent planners, tool-calling agents, chatbots, prompt orchestration
- frontend Baba Score or platform-evidence UI
- recommendations, ranking, auto-correction
- fuzzy or cross-platform identity
- `grading.v2` or in-place `grading.v1` changes
- Phase 5 functionality

==================================================
## 20. Phase 4 final status
==================================================

**PHASE 4 — PASS / CLOSED**

`grading.v1` remains frozen. Baba Score remains a projection. Platform scores remain evidence.

==================================================
PHASE 4 CLOSURE RULE
==================================================

PHASE 4 IS CLOSED.

Future chats MUST treat Phase 4 as an established baseline.

Do not reopen Phase 4 for cosmetic improvements, unrelated debt, speculative refactoring, architecture experiments, or later-phase functionality.

Do not invent calibration formulas. Do not copy platform ratings into Baba Score. Do not add agents or live platform HTTP as a silent Phase 4 change.

If a future phase requires a change:

1. Identify the exact requirement from that phase's official roadmap.
2. Explain why Phase 4 behavior must change.
3. Preserve Phase 4 guarantees wherever possible.
4. Do not silently reopen Phase 4.

PHASE 5 HAS NOT STARTED.

Do not implement Phase 5 until its official roadmap is provided, audited, planned, reviewed, and explicitly approved.

Related records:

- `PHASE1_CLOSURE.md`
- `PHASE2_CLOSURE.md`
- `PHASE3_CLOSURE.md`
- `.cursor/rules/phase1-closed.mdc`
- `.cursor/rules/phase2-closed.mdc`
- `.cursor/rules/phase3-closed.mdc`
- `.cursor/rules/phase4-closed.mdc`
- `AGENT.md`

END OF PHASE 4 CLOSURE RECORD.
