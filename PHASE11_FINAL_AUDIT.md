# PHASE 11 FINAL AUDIT

Status: **PASS — CLOSED**

Official name: AI Catalogue Improvement, Grade & Apply.

Phase 10 remains CLOSED. Phase 9 remains CLOSED (read-only tools; `apply_improvement` is still a refused write-tool name). Phase 12 is NOT STARTED.

==================================================
## 1. Discovery Summary
==================================================

Phase 6 already generated allowlisted proposals (description, labels, category name, trusted price copy, media handoff) with Current → Proposed preview. Apply was deferred. Phase 7 generated media jobs and artifacts but did not replace live catalogue media. Phase 10 typed owner edits are a separate Propose → Confirm → Apply path and were not reused as the improvement engine.

The Grade / AI Improvements UI listed findings and generated previews. “Proposal created” was not live catalogue change. “Job created” was not a live image/video replacement.

Phase 11 adds authorized apply + cancel on the existing proposal table, live media apply into catalogue-assets, re-grade via the frozen `grading.v1` engine, UI Apply/Cancel/Improve, and natural-language “Improve {item}” that creates the same proposal (does not apply from chat).

==================================================
## 2. Existing Architecture Reused
==================================================

- Phase 6 `catalogue_improvement_proposals`, `create_improvement`, validators, Ollama/scripted generators, path allowlist
- Phase 5 `grade_explain.v1` findings as drivers
- Phase 3 `grade_catalogue` after successful apply (no second engine)
- Phase 7 media jobs, artifacts, studio preview
- Phase 9 assistant turn (sibling handler after Phase 10 mutation parse); GET tools unchanged
- Phase 1 `update_catalogue` for scoped payload writes
- Catalogue-assets confinement so vision grading can read applied local media

==================================================
## 3. Missing Functionality Found
==================================================

- No HTTP apply/cancel for improvements (explicit Phase 6 deferral)
- Media jobs never wrote `image_url` / `video_url` on the live payload
- UI copy and tests treated the page as preview-only (no Apply)
- NL “Improve Ghee Rice” opened improvements or clarified; it did not generate a Phase 6 proposal
- GIF/video apply required treating `media_kind == video` as live video/gif replacement even when the artifact is `image/gif`

==================================================
## 4. Implementation Changes
==================================================

- `POST /catalogues/{id}/improvements/{proposal_id}/apply` and `/cancel`
- Field-scoped apply of READY lines; `media_handoff` skipped (must apply from Generated Media)
- CAS READY/PARTIAL → APPLIED; replay of APPLIED is idempotent; STALE/foreign org refused
- Cancel then same `request_key` regenerates instead of resurrecting CANCELLED
- `POST /catalogues/{id}/media-jobs/{job_id}/apply` copies artifact into catalogue-assets and updates live media field, then re-grades
- Frontend: Improve, Apply to catalogue, Cancel, live media apply, recalculated grade line
- `maybe_handle_quality_improve` after Phase 10: named-item improve generates a stored proposal and before/after text; does not write the catalogue

==================================================
## 5. Improvement Matrix
==================================================

| Improvement | Generate | Before/After | Approve | Apply | Real data changed | Re-grade | Status |
|---|---|---|---|---|---|---|---|
| Description | Yes | Yes | Owner Apply | HTTP apply | `description` | `grade_catalogue` | Done |
| Tags/labels | Yes | Yes | Owner Apply | HTTP apply | `labels` | `grade_catalogue` | Done |
| Category name | Yes (existing driver) | Yes | Owner Apply | HTTP apply | category `name` | `grade_catalogue` | Done |
| Trusted price copy | Yes (existing driver) | Yes | Owner Apply | HTTP apply | `price` from original only | `grade_catalogue` | Done |
| Metadata (arbitrary JSON) | No | — | — | Refused | — | — | Out of scope |
| Overall quality | Via supported findings | Per line | Per proposal | Per apply | Only allowlisted fields | Yes | Done |

==================================================
## 6. AI Quality Examples
==================================================

**Description (fixture Ghee Rice, Mains, empty description)**

- BEFORE: empty
- AFTER (scripted/grounded generator, same contract as live Ollama + validator): `Ghee Rice from the Mains menu.`
- Why better: fills the Phase 5 `missing_description` gap using only verified name + category. No invented ingredients, awards, or diet claims. `validate_candidate` still rejects hallucinated claims if a model emits them.

**Tags**

- BEFORE: empty labels
- AFTER: category-grounded labels such as `Mains`, `Rice` (not `vegan` unless already a catalogue fact)
- Why better: discoverability without unsupported claims. Cancel-then-regenerate is covered so a cancelled proposal cannot be applied.

==================================================
## 7. Media Matrix
==================================================

| Media | Generate | Preview | Approve | Apply | Live media changed | Status |
|---|---|---|---|---|---|---|
| Image | Phase 7 job | Studio + artifact GET | Apply to live catalogue | Writes `/catalogue-assets/…` and `image_url` | Yes | Done |
| Video/GIF | `image_to_video` job (GIF artifact in V1) | Preview bytes | Apply | Live `video_url` when kind is video (incl. GIF) | Yes | Done |
| Improvement `media_handoff` line | Handoff only | Link to studio | Not via improvement apply | Must use media apply | Honest skip | Done |

==================================================
## 8. Grade Results
==================================================

`test_description_apply_writes_catalogue_and_regrades` grades before apply (empty description) and after apply with the same `grading.v1` + vision stub. Assertion: `after_grade.score >= before_grade.score`. Letter is whatever the frozen engine emits; tests do not force A.

Filling a missing description removes a real NLP finding when the rest of the catalogue already satisfies hard checks. A-grade is not claimed unless that engine output is A.

==================================================
## 9. Security Tests
==================================================

Covered in `tests/test_phase11_improvement.py` and Phase 6/9/10 suites:

- Foreign organization apply → 403/404
- Stale proposal after owner edit → 409, live text preserved
- Replay apply → 200 APPLIED, no double-corruption of unrelated fields
- `apply_improvement` remains in write-tool names and out of allowlisted GET tools
- Prompt/SQL/arbitrary JSON still not an apply path (allowlisted kinds + paths only)

==================================================
## 10. End-to-End Tests
==================================================

| Example | Test |
|---|---|
| Description improve → apply → payload → re-grade → replay | `test_description_apply_writes_catalogue_and_regrades` |
| Labels cancel → new proposal → apply | `test_labels_cancel_then_apply` |
| Stale + foreign org | `test_stale_and_foreign_org_cannot_apply` |
| Image job → apply → file + live URL | `test_media_apply_updates_live_image` |
| NL Improve item → proposal, catalogue unchanged | `test_nl_improve_item_creates_proposal_without_applying` |
| Video/GIF job → apply | `test_video_apply_updates_live_media` |

API + pytest are the executed E2E. In-browser click-through of Improve → Apply was not run in this pass (no guaranteed live session against a seeded catalogue).

==================================================
## 11. Regression Tests
==================================================

150 passed: Phase 3, 5, 6, 7, 9, 10, 11 (`pytest` 34.59s).

Phase 6 create still does not apply or re-grade. Phase 7 generate still does not write payload until apply. Phase 9 read-only tools unchanged. Phase 10 mutation parse still owns explicit description/image/video owner edits.

==================================================
## 12. Bugs Found and Fixed
==================================================

- Preview-only apply gap (the Phase 11 product hole)
- CANCELLED `request_key` replay blocking a new Improve
- STALE overlay on APPLIED rows
- Media apply writing outside catalogue-assets (would break vision confinement)
- GIF video treated as non-video because content-type was `image/gif`
- NL “improve those descriptions” stealing Phase 9 `open_improvements` (now only intercepts when an item path resolves)
- Frontend Apply hidden unless `onApply` is passed; page now passes apply/cancel and shows recalculated grade from apply result

==================================================
## 13. Remaining Limitations
==================================================

- Live Ollama quality depends on the local model; CI uses a scripted generator with the same validator
- V1 “video” is the Phase 7 GIF motion preview, not a separate MP4 pipeline
- `media_handoff` cannot apply from the improvements POST; owner must generate then apply in Generated Media
- Baba chat never applies (approval stays on the improvements/media UI)
- Browser session E2E not executed here
- Arbitrary metadata JSON is still refused (correct)

==================================================
## 14. Phase Boundary Audit
==================================================

- Phase 9 = CLOSED (read-only; no write tools)
- Phase 10 = CLOSED (typed owner mutations unchanged)
- Phase 11 = COMPLETE (improvement + media apply + re-grade)
- Phase 12 = NOT STARTED (no closed-loop optimizer, no `grading.v1` formula change)

==================================================
## 15. FINAL VERDICT
==================================================

**PASS — CLOSED**

The owner path Generate preview → Current/Proposed → Apply → live catalogue/media write → `grading.v1` recalculation is implemented and covered by tests. Proposal-only and job-only are no longer treated as done.
