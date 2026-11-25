# Phase 8 — Customer Review Intelligence

Status: **PASS — CLOSED**. Official handoff: `PHASE8_CLOSURE.md`.

Engine: `review_intel.v1.1`. First-party customer written feedback is the review source. Third-party scrape remains rejected.

This file retains discovery history. The closure file is authoritative for V1 contracts.

==================================================
## Discovery findings
==================================================

### 1. Existing repository baseline — INFERRED

CatalogForge / Hecto Baba is a restaurant and Dineout catalogue intelligence system. Closed phases 0–6 have official records. Phase 7 media is implemented and used as a closure baseline in this prompt; there is no `PHASE7_CLOSURE.md` in the repository.

### 2. Existing review-related functionality — OFFICIAL (repository evidence at discovery)

**Discovery-time (before Phase 8 code):** there was no customer-review collector, store, sentiment engine, aspect taxonomy, theme detector, or review-to-item linker.

Hits for “review” elsewhere remain UI preview copy, discovery skip-slugs (`"reviews"` on Zomato/Magicpin), and **numeric platform ratings** (`SourceRating`, item `rating` / `rating_count`). Those ratings are Phase 4 evidence, not review text.

**Current V1 (not a live source):** supplied-review ingest, analysis jobs, linkage, and inspect recommendations exist under `review_intel.v1`. Live platform collection remains **UNKNOWN**.

### 3. Existing catalogue models — OFFICIAL (`PHASE1_CLOSURE.md`)

Canonical path: Restaurant/venue → menus → categories → items. Item identity is `item_id` reused only via `source_item_id`. **No fuzzy / name / price identity** for catalogue persistence. Phase 8 linkage **references** these entities and does not rewrite them.

### 4. Organization boundaries — OFFICIAL

Better Auth organization membership (`require_organization_member`). Catalogue rows are `user_id` + `organization_id`. Cross-org access returns the same-class 404 used elsewhere.

### 5. Ingestion infrastructure — OFFICIAL

Phase 2: scrape → raw capture → validate/normalize → `ExistingCatalogueAdapter` → Phase 1 `save_catalogue`. Scrapers extract menus and venue ratings, not review bodies.

### 6. AI / provider infrastructure — OFFICIAL

Phase 3 local heuristic NLP (catalogue text quality, not sentiment). Phase 6 untrusted Ollama + validation. Phase 7 local/hosted media providers. **Phase 8 does not call any of these.**

### 7. Jobs / idempotency — OFFICIAL

`BEGIN IMMEDIATE`, unique `request_key`, `claim_token` CAS (grades, improvements, media). Phase 8 analysis reuses that pattern.

### 8. What Phase 8 receives — OFFICIAL (this phase prompt) + UNKNOWN (source)

Receives stored review text scoped to an authorized catalogue. Live platform collection is **UNKNOWN**.

### 9. What Phase 8 must produce — OFFICIAL

Sentiment/aspect analysis **when a contract exists**; themes/complaints; catalogue linkage; evidence-backed recommendations. Must not mutate the catalogue or invoke Phases 6/10/11/12/13.

### 10. Review collection source — OFFICIAL (V1)

First-party ingest: `source=customer`. Operator paste: `source=supplied`. Third-party scrape is rejected. `collection_source` remains `unresolved` (no platform collector).

### 11. Sentiment contract — OFFICIAL

Aspect-level `positive` | `negative` | `neutral` | `mixed`. Overall mixed when aspects disagree. Ratings are not mapped to polarity.

### 12. Aspect contract — OFFICIAL

`taste` | `quantity` | `value` | `service` | `catalogue_info` | `website_ux` | `other`

### 13. Recurrence contract — OFFICIAL

Threshold **2** distinct stored reviews in the same signal group. No calendar window. `MAX_STORED_REVIEWS` is not the threshold. Labels: `one_off` | `repeated` | `recurring_complaint`. Positive theme: count ≥ 2 and polarity positive.

### 14. Positive-theme contract — OFFICIAL

Evidence-backed only when recurrence policy labels `positive_theme`.

### 25. Closed V1 exclusions (not UNKNOWN)

Guest diner identity, fuzzy/semantic match, source-review updates, calendar recurrence windows, Phase 7/9–13 work. See `PHASE8_CLOSURE.md`.

### 15. Catalogue-linkage contract — OFFICIAL requirement; PROPOSED algorithm

Must handle exact, normalized, ambiguous, and no-match without silently choosing among candidates. Organization isolation: items only from the authorized catalogue.

Implemented: substring match on stripped item name (exact) then casefolded whitespace-normalized name; longer matches suppress contained shorter ones; shared names with multiple item ids → `ambiguous`.

Not implemented: alias, fuzzy, semantic/embedding match.

### 16. Evidence model — PROPOSED (minimum)

`review_id`, optional `posted_at`, `span_text`, optional `observed_rating`, optional `photo_id`, target, aspect, polarity, intent, request, linkage. No invented confidence field.

### 17. Recommendation contract — PROPOSED (minimum)

Inspect stored feedback for a linked item, unmatched text, or ambiguous match. Optional factual note when observed ratings in that group are not identical. Never apply catalogue changes.

### 18. Persistence — PROPOSED

Additive `catalogue_reviews` and `catalogue_review_analyses`. Unique review identity `(catalogue_id, organization_id, source, external_id)`. Analysis identity `catalogue_id + revision + state hash + reviews fingerprint + review_intel.v1.1`. Does not write `catalogues.payload`.

### 19. API boundaries — PROPOSED

- `POST /catalogues/{id}/reviews/collect`
- `POST /catalogues/{id}/customer-feedback`
- `GET /catalogues/{id}/customer-feedback-photos/{photo_id}`
- `GET /catalogues/{id}/reviews` (paginated, max 50)
- `POST /catalogues/{id}/review-intelligence`
- `GET /catalogues/{id}/review-intelligence`

Authz matches other catalogue routes.

### 20. UI boundaries — PROPOSED

Catalogue workspace **Reviews** tab. Store supplied text, list reviews, show recommendations. Not chat, not approval, not dashboard.

### 21. Security — OFFICIAL requirements; implemented controls

Review text is DATA. Not executed, not sent to Ollama/media. Size caps. Parameterized SQL. Org/user catalogue scope. No URL fetch from review content (no SSRF surface in Phase 8). React text rendering for HTML. IDOR tests included.

### 22. Concurrency / idempotency — PROPOSED using existing patterns

Duplicate `external_id` (or derived hash) replays the stored row. Same analysis identity replays. In-flight analysis → 409. CAS finish on `GENERATING` + `claim_token`. First-write-wins: V1 does **not** update review bodies.

### 23. Performance — PROPOSED

One catalogue snapshot; one review list query; in-memory linkage. Pagination on list (max **50**). Batch collect max **200**. Review body max **8,000** characters. Engineering store cap **1,000** reviews per catalogue (`MAX_STORED_REVIEWS`; not a recurrence threshold). No vector DB.

### 24. Testing — implemented for the foundation

Collection, duplicate, first-write-wins, targets, aspects, mixed polarity, recurrence threshold, positive themes, guest 401, IDOR, prompt-injection, photos, CAS/STALE/FAILED. Full Phase 0–7 suite must still pass.

==================================================
## V1 implementation
==================================================

Engine: `review_intel.v1.1`

Pipeline:

```
Customer feedback (source=customer) and/or supplied ingest
        ↓
Deterministic target detection
        ↓
Deterministic aspect + polarity + intent (no LLM)
        ↓
Deterministic item linkage
        ↓
Recurrence / positive theme (threshold 2, stored set)
        ↓
Inspect-style recommendations (not applied)
```

Guest/unauthenticated diner submit is **out of V1**; submitters must already be authorized to the catalogue.
