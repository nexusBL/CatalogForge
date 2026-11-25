# PHASE 11 / 12 — EDIT HISTORY, ROLLBACK, CLOSED-LOOP CERTIFICATION

Official record: `PHASE11_PHASE12_HISTORY_ROLLBACK_AUDIT.md`  
Status: **PASS — CLOSED**  
Scope: append-only edit history, owner-confirmed rollback, persisted before/after grades, mutation safety.

This does **not** reopen Phases 0–10. It does **not** start Phase 13 dashboard work.  
Runtime LLM remains Ollama `http://127.0.0.1:11434` / `llama3:latest`. No Gemini SDK, API, or keys were added.

Prior audits (`PHASE11_FINAL_AUDIT.md`, `PHASE12_AI_CATALOGUE_REFINEMENT_AUDIT.md`, `BABA_AI_FINAL_OWNER_WORKFLOW_AUDIT.md`) closed other slices (apply/re-grade UI, NL refinement, media studio). They did **not** prove field-level edit history or owner rollback. This document certifies those gaps as implemented and tested.

Regression evidence (this session):

```
python -m pytest tests/ -q --tb=line
526 passed in 64.70s
```

Focused evidence:

```
python -m pytest tests/test_database_mutation_safety.py tests/test_phase11_history_rollback.py tests/test_phase12_closed_loop.py tests/test_phase12_e2e.py -q
10 passed
```

Isolated Ollama check for `create_improvement` (Fresh Lemonade / missing description): status `READY`, provenance `generator=ollama`, `mode=LLM_GENERATED`, `model=llama3:latest`. An earlier e2e `FAILED` in a combined pytest run was leftover `ScriptedGenerator` pollution, not an Ollama outage. `set_generator_factory(None)` at the start of `test_phase12_e2e.py` restores the default generator.

---

## Audit matrix

| Requirement            | Actual implementation | Evidence/files | Tests | Status |
| ---------------------- | --------------------- | -------------- | ----- | ------ |
| Backend validation     | Allowlisted improvement kinds and typed mutation patches; apply rejects invalid/not-ready proposals | `backend/improvement/apply.py`, `backend/mutation/patch.py` | `tests/test_phase11_improvement.py`, `tests/test_phase10_mutation.py` | **PASS** |
| Proposal creation      | Phase 6/10 proposals persist separately from canonical payload | `backend/improvement/service.py`, `backend/mutation/service.py` | existing Phase 6/10/11 tests | **PASS** |
| Approval               | Owner HTTP apply / mutation confirm; Baba write-tool names refused | `backend/main.py`, `backend/assistant/contract.py` | `tests/test_database_mutation_safety.py` | **PASS** |
| Rejection              | Cancel sets `CANCELLED`; cancelled proposal cannot apply; catalogue unchanged | cancel endpoints + safety test | `test_rejected_improvement_does_not_write_catalogue`, `test_cancelled_mutation_does_not_write` | **PASS** (cancel, not a second “reject” verb) |
| Edit history           | Append-only `catalogue_edit_history`; inserts only | `backend/migrate_catalogues.py` `ensure_phase11_history_ddl`, `backend/history/persist.py` | `tests/test_phase11_history_rollback.py` | **PASS** |
| Rollback               | `POST .../history/{id}/rollback` with `{confirm: true}`; restores previous canonical value; new history row; original row kept | `backend/history/service.py` `rollback_history` | price 199→250→199; description apply→empty | **PASS** |
| Before value           | `previous_value` JSON on each history row | contract + persist | history tests | **PASS** |
| After value            | `new_value` JSON on each history row | contract + persist | history tests | **PASS** |
| Actor/source           | `actor` = session user id; `source` = improvement \| mutation \| media \| rollback | `EditHistoryRecord` | history tests | **PASS** |
| Provenance             | `provenance` JSON (proposal/mutation/media/rollback ids) | `record_change` | history tests | **PASS** |
| Proposal ID linkage    | `proposal_id` / `media_job_id` / `rolled_back_history_id` | schema + contract | idempotency test (one row per apply) | **PASS** |
| Re-grading             | `regrade_snapshot` after improvement apply, payload mutation confirm, media apply, and rollback | `backend/history/compare.py`; wired in improvement/mutation/media services | closed-loop + e2e | **PASS** |
| Resolved issues        | `resolved_issue_ids` from before/after fail/error finding ids | `backend/history/compare.py` | closed-loop stores the field | **PASS** |
| Overall score delta    | `overall_score_delta` = after − before from stored grade | `overall_delta` | closed-loop asserts after ≥ before and delta present | **PASS** |
| Section score delta    | `before_section_scores` / `after_section_scores` maps (delta is derived, not a separate column) | contract + persist | closed-loop | **PASS** |
| Mutation safety        | LLM/tools cannot execute writes; only proposal → validate → owner apply | `WRITE_TOOL_NAMES` includes `rollback_history`, `apply_rollback`, `rollback_edit` | `test_write_tool_names_cannot_execute` | **PASS** |
| Idempotency            | Second apply of APPLIED replays; does not duplicate history | improvement apply CAS | `test_apply_is_idempotent_and_does_not_duplicate_history` | **PASS** |
| Ambiguity resolution   | Existing Phase 10 resolver; duplicate names require category | `backend/mutation/resolve.py` | existing Phase 10 tests (unchanged) | **PASS** (preserved) |
| Conversational context | Existing OWNER_REFINED refinement | improvement NL path | `test_phase12_e2e.py` shorter + premium-style refine | **PASS** (preserved) |
| Media approval safety  | Generate stays READY; live URL changes only on apply; status persisted APPLIED | `cas_apply` READY→APPLIED | `test_media_generate_does_not_replace_until_apply_and_persists_applied` | **PASS** |

---

## What was missing (audit, then implement)

Proposals with `current_value` / `proposed_value` are **not** edit history. `catalogue_revisions` payload snapshots are **not** owner field history. Inverse mutation patches are **not** rollback. Re-grade in memory is **not** persisted before/after comparison.

Implemented only those gaps:

1. Append-only `catalogue_edit_history`
2. Record after owner-approved improvement / mutation / media apply
3. Owner-confirmed rollback that restores the recorded previous value, validates, appends a new row, re-grades
4. Mutation field paths include the field (`…items[0].price`), so price rollback restores price rather than rewriting name
5. Media job status persisted as `APPLIED`
6. Mutation confirm re-grades and records history (previously missing)

---

## API / tools

- `GET /catalogues/{catalogue_id}/history?organization_id=`
- `POST /catalogues/{catalogue_id}/history/{history_id}/rollback` body `{ "confirm": true }`
- Frontend proxy: `frontend/src/app/api/catalogues/[id]/history/route.ts` and `.../history/[historyId]/rollback/route.ts`
- Baba write-tool names `rollback_history`, `apply_rollback`, `rollback_edit` are refused

Rollback without `confirm: true` is rejected. Live value must still match recorded `new_value` or rollback is STALE/409.

---

## Database

Table `catalogue_edit_history` (DDL in `ensure_phase11_history_ddl`). Rows are inserted, never updated. Rollback inserts a second row with `source=rollback` and `rolled_back_history_id` pointing at the original.

---

## UI

Improvements page shows `EditHistoryPanel` with previous → new values, grade delta when present, and a confirm dialog before rollback. Browser click-through of Apply → history → rollback was not completed in this session (session/login). Behaviour is covered by HTTP tests.

---

## LLM / scrapers / Phase 13

- LLM: unchanged Ollama local `llama3:latest`
- Scrapers: not redesigned
- Phase 13: not started

---

## Security guarantees

LLM/agent → typed tool call → deterministic backend validation → proposal → owner approval → deterministic apply → database → re-grade.

The agent cannot write `catalogues.payload`. Cancelled proposals do not mutate the catalogue. Duplicate apply does not duplicate history.

---

## Exact phase status

| Slice | Status |
| ----- | ------ |
| Phase 11 apply / cancel / re-grade (prior) | already **PASS — CLOSED** (`PHASE11_FINAL_AUDIT.md`) |
| Phase 11 edit history + owner rollback | **PASS — CLOSED** (this record) |
| Phase 12 NL refine / media apply (prior) | already **PASS — CLOSED** (`PHASE12_AI_CATALOGUE_REFINEMENT_AUDIT.md`) |
| Phase 12 persisted closed-loop compare + rollback trail | **PASS — CLOSED** (this record) |
| Phase 13 dashboard | **NOT STARTED** |
