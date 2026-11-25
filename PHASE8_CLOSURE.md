# Phase 8 — Customer Review Intelligence
Status: PASS — CLOSED

Official name: Customer Review Intelligence.

Engine: `review_intel.v1.1` (`ANALYSIS_CONTRACT = signals.v1`).

This is the official Phase 8 handoff. Do not make further Phase 8 changes unless a later official phase names a concrete defect or required dependency.

Do not start Phase 9 without an official roadmap, audit, plan, review, and explicit approval.

==================================================
PROJECT PHASE STATUS
==================================================

PHASE 0–7 remain closed / implemented baselines. Phase 8 did not reopen them.

PHASE 8 — PASS / CLOSED

==================================================
## 1. Purpose
==================================================

Collect **first-party** customer written feedback in Hecto Baba and produce evidence-backed intelligence for the restaurant owner.

Primary input: written text. Optional: rating, photo (evidence only).

No third-party review scrape. No catalogue mutation. No chat, approval, apply, or re-grade.

==================================================
## 2. Official V1 identity
==================================================

**OFFICIAL:** Submitters must have an authenticated session authorized for the catalogue (`require_session` + organization membership + `get_catalogue` ownership). `author_key` is an opaque hash of the user id. Owners do not see email.

**OFFICIAL exclusion:** Guest / anonymous diner submit is **out of V1**. There is no public diner surface that can be authorized without inventing a weak anonymous token. Do not add one in Phase 8.

==================================================
## 3. Official taxonomies
==================================================

**Target** (what): `product_item` | `catalogue_menu` | `website_ux` | `restaurant_service` | `other`

**Aspect** (which part): `taste` | `quantity` | `value` | `service` | `catalogue_info` | `website_ux` | `other`

**Polarity** (aspect-level, then overall): `positive` | `negative` | `neutral` | `mixed`

Mixed feedback is **not** collapsed to a single aspect polarity. `"tastes good but quantity too small"` yields taste/positive and quantity/negative; overall polarity is `mixed`.

Numeric `observed_rating` is evidence only and is **not** converted to polarity.

**Intent:** `observation` | `praise` | `complaint` | `mixed` (from polarities). Independent **request:** `none` | `improvement_request`.

**Recurrence (stored-set policy, not the 1000 cap):**
- Population: reviews currently stored for that catalogue
- Window: none (no calendar window)
- Threshold: **2** distinct reviews in the same (target, item, aspect, polarity, linkage, request) group
- `one_off`: count 1
- `repeated`: count ≥ 2 and polarity is not negative
- `recurring_complaint`: count ≥ 2 and polarity is negative
- `positive_theme`: count ≥ 2 and polarity is positive

A single complaint must not be described as repeated.

==================================================
## 4. Linkage
==================================================

Exact → normalized → ambiguous → no_match. No fuzzy, embeddings, or LLM item guess.

==================================================
## 5. Recommendations
==================================================

Inspect-only advisory text with `evidence_review_ids`. No Approve / Apply / Modify / Publish. Does not write `catalogues.payload`. Does not call Phase 6/7/10/11/12.

==================================================
## 6. Explicitly out of V1
==================================================

- Guest/anonymous diner identity
- Third-party review APIs/scrapes
- Alias/fuzzy/semantic item match
- Review body updates (first-write-wins)
- Calendar recurrence windows
- Computer vision / OCR on photos
- Phase 9 chat, Phase 11 apply, Phase 12 re-grade, Phase 13 dashboard
- Phase 7 generate/edit jobs for diner photos
