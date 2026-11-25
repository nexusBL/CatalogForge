# Phase 10 final hardening audit — Baba AI typed catalogue mutation

Status: **PASS — CLOSED**

Official name: Baba AI typed catalogue mutation (Propose → Confirm → Apply).

This is the hardening handoff for Phase 10. Do not start Phase 11 (improvement approve/apply) from this record. Phases 0–9 remain closed baselines.

==================================================
PROJECT PHASE STATUS
==================================================

PHASE 0–9 — PASS / CLOSED (unchanged)

PHASE 10 — PASS / CLOSED (hardened)

PHASE 11–13 — NOT STARTED

==================================================
## Verdict
==================================================

Typed catalogue mutations work end to end on the server for every V1 operation: natural-language parse → pending proposal with visible current and proposed values → confirm → persist (or honest media-job start). Regression coverage is `tests/test_phase10_mutation.py` plus `tests/test_phase9_assistant.py` (**50 passed**).

Browser click-through of the dock/workspace was not available in this hardening pass. Catalogue UI refresh after confirm is wired (`persistCatalogueAfterMutation` + `CATALOGUES_CHANGED_EVENT` on the catalogue detail page). Residual: live browser confirmation of that refresh.

==================================================
## Boundary kept
==================================================

- Payload writes happen only after Propose → Confirm → Apply for: `add_item`, `remove_item`, `rename_item`, `change_price`, `update_description`, `update_labels`, `move_item`.
- Not a Phase 6 apply engine. `apply_improvement` / grade / publish / SQL stay refused. Phase 9 GET tools and `execute_tool` were not given mutation tools. Planner `extra="forbid"` remains.
- Phase 7 media jobs may start after confirm. Copy and tests require that live catalogue image/video **has not been changed**. `writes_payload` is false; `apply_patch` is a no-op for media ops.
- Auth: session + organization membership + `get_catalogue` on propose and confirm.
- Names resolved server-side (exact/normalized). Ambiguous items/categories clarify. Model IDs ignored.
- SQLite `catalogue_mutation_proposals`, PENDING → APPLIED/CANCELLED/STALE/EXPIRED, one-use token, revision + state-hash CAS.
- Confirm does not hold `BEGIN IMMEDIATE` across `update_catalogue` (avoids SQLite deadlock).
- Description/tags use verified catalogue facts only (`backend/mutation/quality.py`). Unsupported claims (vegan/award/etc. without evidence) are refused. No fabricated A-grade copy.
- No Graphify/Redis/Celery. `grading.v1` unchanged.

==================================================
## Operation matrix (NL → propose → confirm → persist)
==================================================

| Operation | Example NL | Propose shows before/after | Confirm persists | Notes |
|---|---|---|---|---|
| `change_price` | Change / set / make / increase Ghee Rice … 250 | Current ₹199 → proposed ₹250 | Yes | Trailing amount and “price of” forms parse the item name |
| `add_item` | Add Paneer Tikka for 220 to Starters | `(none)` → name · price · category | Yes | Missing category with multiple sections → clarify. Missing price → clarify |
| `remove_item` | Remove Coke from Drinks | Destructive warning | Yes | Item deleted from payload |
| `rename_item` | Rename Ghee Rice to Ghee Rice Special | Old → new name | Yes | `item_id` reused via `source_item_id`, not name |
| `move_item` | Move Ghee Rice Special to Drinks | Source category → dest | Yes | Same-category move refused |
| `update_description` | Improve the description for Ghee Rice | Current text → grounded polish | Yes | Invented claims refused; quoted owner text still validated |
| `update_labels` | Fix tags for Ghee Rice | Current tags → suggested from facts | Yes | Explicit vegan/gluten-free without evidence → clarify |
| `improve_image` | Improve the image for Ghee Rice | Honesty line | Job id only | Live `image_url` unchanged; Open Media action |
| `generate_video` | Generate a video for Ghee Rice | Honesty line | Job id only | Same media honesty |

Security / CAS (existing + replay):

| Case | Result |
|---|---|
| Confirm before propose | No write |
| Cancel | Payload unchanged |
| Ambiguous duplicate item name | `clarify`, no proposal |
| Stale revision/hash | STALE, no second write |
| Foreign org confirm | 403/404, no write |
| Replay confirm after add | APPLIED replay, no duplicate row |
| Apply improvement / publish / SQL | `refuse_mutation` or extra=forbid |

==================================================
## UI
==================================================

- Confirm card shows item, category, field, current → proposed, destructive warning, media honesty, Confirm / Cancel.
- After APPLIED payload writes, dock and `/baba-ai` refetch the catalogue into local store.
- Catalogue detail listens for `catalogforge:catalogues-changed` and reloads the catalogue.

==================================================
## Media honesty
==================================================

Confirm starts `create_media_job` (image: `generate_image`, then `edit` if unsupported; video: `image_to_video`). Success copy includes the job id and states the live catalogue image/video has not changed. Actions use server-built `/catalogues/{id}/media` (item path when known). Failures surface as clarify, not fake live-media success.

==================================================
## Known limits (not Phase 11)
==================================================

- Deterministic NL is incomplete (unusual phrasing still falls through to Phase 9).
- Live item photo/video in `catalogues.payload` does not change in V1; owners apply candidates in Media.
- Browser E2E of dock confirm → visible catalogue row was not executed in this pass.
- Phase 11 improvement approve/apply remains out of scope.
