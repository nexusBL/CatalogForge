# Phase 10 audit — Baba AI typed catalogue mutation

Status: implemented against the approved product boundary. Phase 11 (improvement apply / approve) was not started.

## Boundary kept

- Payload writes happen only after Propose → Confirm → Apply for typed ops: add_item, remove_item, rename_item, change_price, update_description, update_labels, move_item.
- Phase 6 improvement proposal apply semantics are untouched. `apply_improvement` / grade / publish / SQL remain refused.
- Phase 7 media jobs may start after confirm. Copy states that the live catalogue image/video did not change unless a payload write actually occurred (media ops set `writes_payload=false` and `apply_patch` is a no-op).
- Propose and confirm both use session + organization membership + `get_catalogue`.
- Item/category names are resolved server-side with existing exact/normalized matching. Ambiguous matches ask for clarification. Model IDs are ignored.
- SQLite `catalogue_mutation_proposals` with PENDING → APPLIED / CANCELLED / STALE / EXPIRED, single-use confirm token, revision + state-hash CAS.
- Phase 9 GET tool allowlist and `execute_tool` were not given mutation tools. Planner `extra="forbid"` remains. Sibling pipeline from `run_turn` via `maybe_handle_turn`.
- Patches are field-scoped around `update_catalogue`. No Graphify/Redis/Celery. Grading, ingest identity, and review intelligence were not changed.

## Implementation notes (not silent redesign)

- Confirm does **not** hold `BEGIN IMMEDIATE` across `update_catalogue`. Nested IMMEDIATE on a second connection to the same SQLite file deadlocks. Identity is re-checked, the payload write runs, then PENDING→APPLIED CAS. Concurrent confirm of the same proposal is serialized by CAS; a lost race after an identical write replays APPLIED.
- Owner-supplied tags are normalized and length-capped. They are not run through Phase 6 LLM `validate_labels`, which treats the model as untrusted. Owner-supplied description text is still length-checked; missing quoted text refuses invention.

## Remaining product limits

- Natural-language coverage is deterministic and incomplete (quoted description/tags, explicit add-to-category, etc.).
- Media confirm starts the existing job system only; live `image_url` does not change in V1.
- No Phase 11 improvement apply.
