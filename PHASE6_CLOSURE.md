# Phase 6 — AI Improvement Engine
Status: PASS — CLOSED

This is the official Phase 6 handoff for future phases.

Do NOT make further Phase 6 changes unless a future official phase identifies a concrete defect or required dependency.

==================================================
PROJECT PHASE STATUS
==================================================

PHASE 0 — PASS / CLOSED

PHASE 1 — PASS / CLOSED

PHASE 2 — PASS / CLOSED

PHASE 3 — PASS / CLOSED

PHASE 4 — PASS / CLOSED

PHASE 5 — PASS / CLOSED

PHASE 6 — PASS / CLOSED

Phase 0–5 remain closed baselines. Phase 6 did not reopen them.

==================================================
## 1. Purpose
==================================================

Move from identifying problems to proposing improvements.

Official name: AI Improvement Engine.

Official flow:

```
Problem (Phase 5 finding or catalogue-state eligibility)
        ↓
AI Improvement
        ↓
Proposed Change
        ↓
Preview
        ↓
Later Approval / Application (not Phase 6)
```

Phase 6 is **propose + preview** only.

==================================================
## 2. Official V1 scope (final implemented)
==================================================

Implemented:

- preview-only improvement proposals over Phase 5 findings and one catalogue-state driver
- description improvement
- tag / labels improvement (`labels[]`, not a `grading.v1` section)
- category-name improvement (safe menu-structure V1)
- item-content improvement limited to descriptions and trusted `original_price` copy
- explicit improvement-kind allowlist (`KIND_REGISTRY` / `DRIVER_KIND`)
- Phase 7 media **handoff** (no generation)
- untrusted local Ollama adapter + mandatory backend validation
- separate proposal persistence (`catalogue_improvement_proposals`)
- catalogue-detail preview: Current → Proposed → Why / originating finding → Status
- organization-scoped APIs: POST/GET `/catalogues/{id}/improvements`, GET by proposal id
- `BEGIN IMMEDIATE` `GENERATING` reservation before generator invocation
- unique `request_key` idempotency; STALE when revision/state diverges

Explicitly not implemented (later phases / boundaries, not defects):

- approval or apply (Phase 11)
- image or video generation (Phase 7)
- re-grading or closed-loop optimization (Phase 12)
- Baba dashboard (Phase 13)
- item move/order when no safe source+target exists
- invented item names (`missing_item_name`)
- invented selling prices (LLM never sets price)
- arbitrary JSON patch / edit-any-field
- chat mutation, agents, LangGraph
- `grading.v1` changes, Baba Score changes, Phase 5 explanation/recommendation changes
- canonical `catalogues.payload` writes

==================================================
## 3. Architecture
==================================================

```
Phase 5 grade_explain.v1 finding
  or catalogue-state driver (empty_item_labels)
        ↓
eligibility + trusted catalogue context (DATA, not instructions)
        ↓
KIND_REGISTRY / DRIVER_KIND (allowlisted kind only)
        ↓
BEGIN IMMEDIATE + GENERATING reservation (unique request_key)
        ↓
Ollama candidate when NL generation is useful
  (skipped for media_handoff, item_price, deterministic food_type labels)
        ↓
backend validation (authoritative)
        ↓
finalize READY / PARTIAL / FAILED on catalogue_improvement_proposals
        ↓
preview UI (Current → Proposed → Why → Status)
```

Canonical catalogue payload is never written on this path.

==================================================
## 4. Implemented capabilities
==================================================

### 4.1 Description improvement

Supported Phase 5 drivers:

- `missing_description`
- `description_coverage`
- `placeholder_text`
- `malformed_text`
- `repeated_description`

Flow: Phase 5 finding → eligibility → Ollama candidate → backend validation → proposal → preview.

### 4.2 Tag / labels improvement

Supported catalogue-state driver:

- `empty_item_labels`

Uses canonical `labels[]`. Tags are **catalogue content**. Tags are **not** a `grading.v1` section. No new grading check was added to make tags work.

Requirements (implemented):

- preserve existing labels
- structured `proposed_labels`
- backend validation
- reject malformed output
- reject unsupported claims
- reject hallucinated allergens / dietary claims
- Ollama only when natural-language generation is useful (e.g. no trusted `food_type` to copy)
- preview only
- no canonical mutation

### 4.3 Menu structure

Supported safe V1 capability:

- category-name improvement (`missing_category_name`)

Item moves and ordering are **not** implemented. Where a structural target cannot be safely identified, `category_count_mismatch` is rejected (HTTP 422). Phase 6 does not invent a destination category or order.

### 4.4 Item content

Supported:

- description improvement (same drivers as §4.1)
- selling-price proposal only by **copying trusted `original_price`** (`kind=item_price`; Phase 5 `missing_price` / `invalid_price` when that value is coercible)

The LLM must not invent prices. `missing_item_name` remains unsupported: there is no trusted value from which to safely generate or copy a name.

### 4.5 Other catalogue content

Phase 6 is **not** arbitrary JSON patching.

Allowlist:

- `KIND_REGISTRY`
- `DRIVER_KIND`

Registered kinds:

| Kind | Role |
|------|------|
| `description` | NL item description preview |
| `category_name` | NL empty category name preview |
| `labels` | Structured labels preview |
| `media_handoff` | Phase 7 image/video improvement handoff |
| `item_price` | Deterministic copy of `original_price` |

Each kind defines eligibility, canonical path, input/output types, validation, preview representation, provenance, and no-apply behavior.

==================================================
## 5. Media / Phase 7 boundary
==================================================

Phase 6 **connects** image/video improvement. It does **not** generate media.

Supported vision / image findings:

- `missing_item_image`
- `image_missing`
- `image_invalid`
- `image_unreadable`
- `image_low_quality`
- `no_images_present`

A persisted media handoff includes catalogue identity, revision/state identity, affected canonical path, current media reference if present, originating `check_id` / why, media type/capability, and `phase7_required`.

Phase 6 does not:

- generate images or videos
- call image-generation or video-generation models
- mutate catalogue media

Actual image/video improvement belongs to **Phase 7 — Image Improvement + Video**.

==================================================
## 6. Preview
==================================================

Preview is mandatory before any later application.

UI:

- Current
- Proposed
- Why / originating finding
- Status (`READY` / `FAILED` / `PARTIAL` / `STALE`)

Phase 6 does not apply changes. There is no Phase 6 approval endpoint and no Phase 6 apply endpoint.

==================================================
## 7. Persistence and identity
==================================================

Canonical source of truth for the live catalogue remains `catalogues.payload`. Phase 6 **never writes** that column.

Proposals persist in `catalogue_improvement_proposals` (additive DDL in `ensure_phase6_ddl`). Identity includes catalogue id, organization, `source_head_revision`, and `source_state_hash`.

If the catalogue revision or state hash changes after generation, the proposal surfaces as **STALE**. Phase 6 does not silently apply stale proposals.

==================================================
## 8. Ollama
==================================================

Default V1 generator: local Ollama adapter (`llama3:latest`, 60s timeout, env-overridable URL/model/timeout).

Ollama is an **untrusted candidate generator only**.

The backend remains authoritative for authorization, organization scope, catalogue identity, revision, path, operation, type, validation, content safety, and persistence.

The model cannot authorize, choose another catalogue or organization, choose arbitrary paths, write SQLite, mutate the catalogue, or execute tools. Catalogue text is DATA, not instructions.

Invalid or unsafe model output becomes FAILED / UNSUPPORTED. There is no fake fallback description.

Timeout, unavailable, and missing-model conditions are explicit FAILED lines (no silent substitute).

==================================================
## 9. Concurrency / idempotency
==================================================

Final race-condition solution:

```
BEGIN IMMEDIATE
  → insert GENERATING reservation (unique request_key)
  → generator call (if this request owns the reservation)
  → finalize READY / PARTIAL / FAILED
```

Concurrent identical requests reuse the reservation, do not call the generator twice, and return the same persisted proposal. Unique `request_key` is the database safeguard.

Stuck `GENERATING` rows have **intentional recovery** after the configured timeout window (steal / retry). That is recovery behavior, not a Phase 6 defect.

Synchronous V1. Maximum 5 paths per request (more → HTTP 422). Duplicate requests do not regenerate.

==================================================
## 10. Security
==================================================

- session authentication (`require_session`)
- organization membership (`require_organization_member`)
- catalogue ownership / org scoping on snapshot and proposal rows
- model output untrusted; never executed; never used for authorization
- prompt-injection resistance (catalogue text is DATA; injection-like output rejected)
- malformed JSON / extra fields rejected
- hallucinated claims, allergens, dietary claims, invented ingredients rejected
- no direct model database access
- no arbitrary JSON patching

==================================================
## 11. Performance (V1)
==================================================

- synchronous HTTP (no queue / worker)
- maximum 5 paths per request
- one generator call per eligible natural-language line
- duplicate requests do not regenerate
- one catalogue snapshot per request
- proposal list is a single query (no SQL N+1)

==================================================
## 12. APIs
==================================================

| Method | Path | Role |
|--------|------|------|
| POST | `/catalogues/{id}/improvements` | Create or replay a preview proposal |
| GET | `/catalogues/{id}/improvements` | List proposals for this catalogue/org |
| GET | `/catalogues/{id}/improvements/{proposal_id}` | Fetch one proposal |

No apply, approve, or re-grade routes in Phase 6.

==================================================
## 13. Test results (closure audit)
==================================================

Backend: **398 passed** (`pytest`).

Frontend: **148 passed** (Vitest).

TypeScript: pre-existing failure in `frontend/src/lib/progress.test.ts`. **Not a Phase 6 failure.**

Lint: pre-existing failures in `frontend/src/app/error.tsx` and `frontend/src/app/global-error.tsx` (`no-console`). **Not a Phase 6 failure.**

Vite CJS Node API deprecation: warning only / environment tooling.

==================================================
## 14. Final engineering audit
==================================================

| Gate | Result |
|------|--------|
| Correctness | PASS |
| Completeness | PASS for approved V1 |
| Race conditions | PASS |
| Atomicity | PASS |
| Idempotency | PASS |
| Dead code | PASS |
| Unused imports | PASS |
| Security | PASS |
| Performance | PASS |
| N+1 | PASS |
| Uncaught errors | PASS |
| Type errors | FINDING — pre-existing repository TypeScript failure only |

==================================================
## 15. Known V1 limitations (phase boundaries, not defects)
==================================================

- no arbitrary catalogue editing
- no item move/order where a safe target does not exist
- no invented item names
- no invented prices
- no image generation
- no video generation
- no approval
- no apply
- no re-grade
- no chat mutation
- no dashboard
- no agents / LangGraph
- no `grading.v1` modification

==================================================
## 16. Later-phase boundaries
==================================================

| Phase | Responsibility |
|-------|----------------|
| 6 (this phase, CLOSED) | Propose + preview |
| 7 | Image improvement + video (generation) |
| 11 | Controlled tool execution + owner approval |
| 12 | Re-grading + closed-loop optimization |
| 13 | Final Baba dashboard |

Do not absorb Phase 7, 11, 12, or 13 into Phase 6.

==================================================
## 17. Regression
==================================================

Phase 0–5 remain CLOSED. Phase 6 did not change `grading.v1`, Baba Score, `grade_explain.v1`, or Phase 5 recommendation semantics. Canonical catalogue payload is unchanged by preview generation.

==================================================
## 18. Closure instruction
==================================================

PHASE 6 IS CLOSED.

Future chats MUST treat Phase 6 as an established baseline.

Do not reopen Phase 6 for cosmetic improvements, unrelated debt, speculative refactoring, architecture experiments, or later-phase functionality.

If a future phase requires a change:

1. Identify the exact requirement from that phase's official roadmap.
2. Explain why Phase 6 behavior must change.
3. Preserve Phase 6 guarantees wherever possible.
4. Do not silently reopen Phase 6.

Related records:

- `PHASE1_CLOSURE.md`
- `PHASE2_CLOSURE.md`
- `PHASE3_CLOSURE.md`
- `PHASE4_CLOSURE.md`
- `PHASE5_CLOSURE.md`
- `.cursor/rules/phase6-closed.mdc`

END OF PHASE 6 CLOSURE RECORD.
