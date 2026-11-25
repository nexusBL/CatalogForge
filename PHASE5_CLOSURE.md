# Phase 5 — Grade Explanation & Recommendations
Status: PASS — CLOSED

This is the official Phase 5 handoff for future phases.

Do NOT make further Phase 5 changes unless a future official phase identifies a concrete defect or required dependency.

==================================================
PROJECT PHASE STATUS
==================================================

PHASE 0 — PASS / CLOSED

PHASE 1 — PASS / CLOSED

PHASE 2 — PASS / CLOSED

PHASE 3 — PASS / CLOSED

PHASE 4 — PASS / CLOSED

PHASE 5 — PASS / CLOSED

Phase 0–4 remain closed baselines. Phase 5 did not reopen them.

==================================================
## 1. Purpose
==================================================

Make the existing `grading.v1` grade understandable and actionable.

Official name: Grade Explanation & Recommendations.

The user can see overall grade, section grades, evidence, severity, reasons, and prioritized recommended actions, answering **Why?** and **What should I fix first?**

==================================================
## 2. Official scope
==================================================

Implemented:

- read-time `grade_explain.v1` projection of a completed `grading.v1` row
- GET `/catalogues/{id}/grade-explanation`
- Grade UI on the catalogue detail page
- deterministic findings, reasons, severity, recommendations, and `fix_first`

Explicitly not implemented (out of scope):

- a new grading engine or `grading.v2`
- Description/Menu/Tags letter taxonomy
- agents / LLMs
- auto-correction
- Phase 5 persistence tables
- Baba Score or platform-evidence UI (Phase 4 limitation unchanged)

==================================================
## 3. Architecture
==================================================

```
persisted grading.v1 (catalogue_grades)
        ↓
pure function explain_grade(GradingResult)
        ↓
GET /catalogues/{id}/grade-explanation
        ↓
Grade UI
```

Overall letter and score are copied from the grade row. Section letters use frozen `letter_for_score` on stored stage scores. Findings are grouped fail/error evidence. No compute of `grading.v1` on the explanation path.

==================================================
## 4. Section taxonomy
==================================================

`grading.v1` stage scores, not an invented product taxonomy:

| section id     | UI label       |
|----------------|----------------|
| deterministic  | Deterministic  |
| nlp            | Text           |
| vision         | Images         |

==================================================
## 5. Severity
==================================================

Reuses Phase 3 `EvidenceSeverity`: `hard`, `ordinary`, `info`.

==================================================
## 6. Priority rule
==================================================

Actionable: `result` in `{fail, error}`.

Order:

1. severity: hard, then ordinary, then info
2. higher `grading.v1` stage weight (deterministic 0.50, nlp 0.25, vision 0.25)
3. higher affected_count
4. section id ascending
5. check_id ascending

`fix_first` is recommendation priority 1.

==================================================
## 7. Persistence
==================================================

None. No Phase 5 tables.

Identity is inherited from the grade row:

`catalogue_id + graded_head_revision + graded_state_hash + engine_version`

GET uses the same current-head lookup as GET `/grade` (`get_catalogue_grade`). A grade for revision N is not returned for revision N+1.

==================================================
## 8. API
==================================================

`GET /catalogues/{id}/grade-explanation?organization_id=`

Authz matches catalogue/grade routes.

- 200: explanation of the completed grade for this revision
- 404: missing catalogue, or no completed grade for this revision
- 401: unauthenticated
- 403: wrong organization
- 422: missing organization_id
- 502: stored payload cannot be explained honestly

POST `/grade` remains the Phase 3 compute path.

==================================================
## 9. UI
==================================================

Catalogue detail (`/catalogues/[id]`): overall grade, section grades, overall why, findings (Why?, evidence, severity, action, priority), “What should I fix first?”, Grade / re-grade.

Load failures other than 404 are shown as errors, not as a missing grade.

==================================================
## 10. Concurrency / atomicity
==================================================

Phase 5 performs no writes. Write atomicity is **not applicable**.

A single explanation GET loads the current catalogue (authz), then head revision, then the matching COMPLETED grade. Mismatched revision/hash yields no row (404). Concurrent GETs are read-only and converge.

UI catalogue GET and explanation GET are separate HTTP calls; each request is fail-closed. Concurrent catalogue mutation during those two UI calls can show an ungraded new revision (404/empty explanation) rather than mixing grade N+1 into revision N identity on the API.

==================================================
## 11. Idempotency
==================================================

Phase 5 explanation generation is derived/read-time; no persistent generation operation exists, therefore no new Phase 5 idempotency key is required.

Repeating GET or `explain_grade` on the same `GradingResult` yields the same logical payload.

==================================================
## 12. Security
==================================================

Session required. Organization membership required. Grade row scoped by catalogue_id + user_id + organization_id. Cross-user access is 404. Wrong org is 403. Parameterized SQL via existing grade load. No new network, SSRF, LLM, or tool surface.

==================================================
## 13. Performance / N+1
==================================================

Same query path as GET `/grade` (catalogue + head revision + one grade row). Evidence is in the grade JSON; grouping is in memory by check_id. The UI issues one explanation GET on load, not per finding. 400 aggregated image findings explained in under 1s in tests. No cache added.

==================================================
## 14. Error handling
==================================================

Missing grade → 404. Incomplete/corrupt/non-numeric section scores → 502. KeyError missing catalogue → 404. SQLite operational errors on the shared grade-load path are not specially remapped (same class as GET `/grade`).

==================================================
## 15. Tests and exact results
==================================================

Closure verification (2026-08-20), working directory CatalogForge, after audit fixes:

1. `python -m pytest tests/test_phase3_grading.py tests/test_phase4_platform_eval.py tests/test_phase5_grade_explain.py -q --tb=line` — **75 passed**
2. `python -m pytest -q --tb=line` — **371 passed**
3. `python -m compileall backend scraper tests -q` — **PASS** (exit 0)
4. Frontend `npm test` — **144 passed**

Counts rose from the implementation report (73 / 369 / 143) because the audit added two backend tests and one frontend test; no Phase 0–4 tests were removed.

`ruff`, `mypy`, `pyright`, `flake8`, `pylint`: **NOT INSTALLED**.

Frontend `tsc --noEmit`: **PRE-EXISTING FAILURE** in `src/lib/progress.test.ts` (`query` is not a known property). No Phase 5 file error.

Frontend `next lint`: **PRE-EXISTING FAILURE** (`profile/page.tsx` hook warning, `error.tsx` / `global-error.tsx` `no-console`, `area-jobs.test.ts` unused var). No Phase 5 file reported.

==================================================
## 16. Audit results
==================================================

Independent Phase 5 final audit (2026-08-20):

1. Closed-phase integrity — **PASS** (no edits to `backend/grading` formula/orchestrator/persist, platform_eval, canonical identity, or ingest semantics; additive `main.py` route only)
2. Requirements completeness — **PASS**
3. Stale revision — **PASS** (404)
4. Concurrency / atomicity — **PASS** (read-only; fail-closed identity)
5. Idempotency — **N/A** (derived; no generation key)
6. Security — **PASS**
7. N+1 — **PASS**
8. Uncaught invalid payload — **PASS** after audit fix (non-numeric scores and corrupt JSON → 502)
9. UI error mapping — **PASS** after audit fix (502/403 not shown as missing grade)
10. Type safety — **NOT AVAILABLE** (Python); frontend tsc **PRE-EXISTING FAIL**
11. Full regression — **PASS** (371)

==================================================
## 17. Known limitations
==================================================

- Explanation GET is not a single SQLite snapshot with catalogue+revision+grade (three reads, fail-closed on mismatch), matching GET `/grade`.
- SQLite operational errors on the shared load path are uncaught HTTP 500, as with GET `/grade`.
- UI still fetches catalogue and explanation in parallel (two requests).
- Static Python type checkers were not installed at closure.
- Frontend `tsc` / `next lint` still fail on pre-existing non-Phase-5 files.

These limitations are not automatic later-phase work.

==================================================
## 18. Explicitly out of scope
==================================================

- `grading.v2`
- invented Tags/Menu section letters
- agents / LLM copy
- auto-fix
- Baba–platform blending
- live platform HTTP

==================================================
## 19. Phase 5 final status
==================================================

**PHASE 5 — PASS / CLOSED**

`grading.v1` remains frozen. Baba Score remains a projection. Platform scores remain evidence. Phase 5 is a derived explanation layer.

==================================================
PHASE 5 CLOSURE RULE
==================================================

PHASE 5 IS CLOSED.

Future chats MUST treat Phase 5 as an established baseline.

Do not reopen Phase 5 for cosmetic improvements, unrelated debt, speculative refactoring, architecture experiments, or later-phase functionality.

If a future phase requires a change:

1. Identify the exact requirement from that phase's official roadmap.
2. Explain why Phase 5 behavior must change.
3. Preserve Phase 5 guarantees wherever possible.
4. Do not silently reopen Phase 5.

Related records:

- `PHASE1_CLOSURE.md`
- `PHASE2_CLOSURE.md`
- `PHASE3_CLOSURE.md`
- `PHASE4_CLOSURE.md`
- `.cursor/rules/phase5-closed.mdc`
- `AGENT.md`

END OF PHASE 5 CLOSURE RECORD.
