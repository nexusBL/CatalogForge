# CatalogForge / Hecto Baba — Agent Context

## 1. Project Purpose

CatalogForge (product UI: **Hecto Baba**) is a catalogue/discovery extraction system. A restaurant operator pastes a platform URL, chooses a platform and catalogue type, and the app extracts structured restaurant and/or Dineout data for display and later area-wise/city-wise scraping.

It is intended to support:

- restaurants (delivery/order menus, dishes, prices, offers, restaurant identity)
- Dineout (venue identity, offers, photos, menu pages, amenities, location)
- menu/catalogue data
- multiple platforms
- area / city-wise venue discovery and queued scraping (fixture-tested; not live-verified)

Current platforms:

- Swiggy
- Zomato
- Magicpin

Current catalogue types:

- Restaurant
- Dineout
- Both

Zomato and Magicpin have implemented parsers and fixture tests. They are **not** documented as live-verified unless a later change-log entry records an actual live scrape and frontend card check.

## PROJECT PHASE STATUS

- Phase 0 — PASS / CLOSED
- Phase 1 — PASS / CLOSED
- Phase 2 — PASS / CLOSED
- Phase 3 — PASS / CLOSED
- Phase 4 — PASS / CLOSED
- Phase 5 — PASS / CLOSED
- Phase 6 — PASS / CLOSED
- Phase 7 — IMPLEMENTED / CLOSURE BASELINE (no `PHASE7_CLOSURE.md` in repo)
- Phase 8 — PASS / CLOSED (`PHASE8_CLOSURE.md`)
- Phase 9 — IMPLEMENTED (not CLOSED; awaiting review)

Phase 0–6 are completed phases. They are closed baselines.

Do not reopen them for:

- cosmetic changes
- unrelated refactoring
- speculative improvements
- new features
- future-phase requirements

Any substantial change to a closed phase requires an explicitly approved change request or new official phase scope.

Official records: `PHASE1_CLOSURE.md`, `PHASE2_CLOSURE.md`, `PHASE3_CLOSURE.md`, `PHASE4_CLOSURE.md`. Cursor rules: `.cursor/rules/phase1-closed.mdc`, `.cursor/rules/phase2-closed.mdc`, `.cursor/rules/phase3-closed.mdc`, `.cursor/rules/phase4-closed.mdc`. There is no separate `PHASE0_CLOSURE.md`; Phase 0 guarantees are preserved in later closures. Later-phase scope comes only from that phase’s official roadmap after audit, plan, review, and explicit approval.

## CLOSED PHASES — CANONICAL HANDOFF

This section is the high-level project handoff through Phase 5. Detail for closed phases lives in the official closure files; this file must not contradict them.

### Phase 0 — foundation (PASS / CLOSED)

Phase 0 established operational guarantees that later ingest and grading must preserve:

- concurrency
- atomicity
- cancellation
- crash recovery
- security
- idempotency

Phase 3 did not reopen or rewrite these foundations.

### Phase 1 — Canonical Catalogue (PASS / CLOSED)

Official record: `PHASE1_CLOSURE.md`. Rule: `.cursor/rules/phase1-closed.mdc`.

Phase 1 established the canonical catalogue model (additive dual-write with legacy JSON projection):

RAW PLATFORM DATA → PLATFORM PARSER / ADAPTER → CANONICAL MODEL → PERSISTENCE → LEGACY API PROJECTION → EXISTING FRONTEND

Preserve:

- stable catalogue UUID
- `venue_id` = organization + platform + source listing (not a cross-platform restaurant)
- no fuzzy / name / price item identity
- provenance (platform, source URL, source entity ID, timestamps, source metadata)
- current state + revision history (material change records a revision; identical content does not)
- `CatalogueIdentityConflict` before mutation (HTTP 409, rollback, no third row)
- `BEGIN IMMEDIATE` + re-check + IntegrityError
- explicit `python -m backend.migrate_catalogues` (`MIGRATION_ID` = `phase1_canonical_v1`; not `_connect()` backfill)
- `PRAGMA foreign_keys = ON` on app connections
- adapter input may be shared `scraper.swiggy.models`

Phase 1 closure tests (historical): backend **280 passed**. Do not treat Phase 1 known limitations as automatic later-phase work.

Phase 3 consumes stored canonical catalogues. It did not rewrite identity, revision semantics, provenance, transactional persistence, or migration behavior.

### Phase 2 — Catalogue Ingestion & Normalization (PASS / CLOSED)

Official record: `PHASE2_CLOSURE.md`. Rule: `.cursor/rules/phase2-closed.mdc`.

Phase 2 connected existing scrapers/importers to deterministic validation and normalization, preserved raw source data, and fed normalized catalogues into the existing Phase 1 persist path.

SOURCE / PLATFORM → SCRAPER / IMPORTER → RAW CATALOGUE → VALIDATION → NORMALIZATION → PLATFORM ADAPTER → CANONICAL BABA CATALOGUE

Preserve:

- deterministic normalize/validate (price, category, image, tags; missing-data detection)
- duplicate detection that is deterministic, not fuzzy
- durable raw capture: pending file (`scrape_token`) then bind to catalogue UUID; no janitor; no arbitrary truncation
- `ExistingCatalogueAdapter` only (no extra per-platform adapter classes)
- feed Phase 1 `save_catalogue` / `update_catalogue` (no second persistence path)
- scrape / normalize / raw I/O outside DB transactions
- adapter double-failure must not report canonical success
- no fuzzy or cross-platform identity merge

Phase 2 closure tests (historical): backend **296 passed**. `PHASE2_CLOSURE.md` still records “PHASE 3 — NOT STARTED” as the state at Phase 2 close; current status is Phase 3 CLOSED (this file and `PHASE3_CLOSURE.md`).

Phase 3 is downstream of ingest. It did not rewrite normalization, raw capture, adapter boundaries, or catalogue ingestion.

### Phase 3 — Baba Grading Engine (PASS / CLOSED)

Official record: `PHASE3_CLOSURE.md`. Rule: `.cursor/rules/phase3-closed.mdc`.

Status: **PASS — CLOSED**

Purpose: determine the quality of a canonical catalogue.

Architecture:

```
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
Structured Evidence
```

Grading is **downstream** of catalogue ingestion. Catalogue creation does **not** require grading. Grading failure does **not** prevent catalogue creation. Grades bind to the exact catalogue revision and state hash.

#### Deterministic grading

`backend/grading/deterministic.py`. Rule-based, reproducible, no fuzzy matching.

Hard failures (any one forces letter **F** regardless of combined numerical score):

- `extraction_not_ok` — `extraction_status` is not `ok`
- `missing_restaurant_name` — restaurant name missing when extraction is ok
- `missing_source_url` — source URL missing when extraction is ok
- `empty_menu` — restaurant or both catalogue has no menu items when extraction is ok

Ordinary deductions (reduce the deterministic score; do not by themselves force F unless the combined score is below 40):

- `missing_fssai`
- `missing_address`
- `missing_category_name`
- `category_count_mismatch`
- `missing_item_name`
- `missing_price`
- `invalid_price` (selling price or MRP)
- `missing_item_image`
- `missing_description`

#### NLP grading (approved Phase 3 implementation)

`backend/grading/nlp.py`. Local on-host text/content quality heuristics:

- text / description coverage
- placeholder detection
- exact-repeat descriptions (not fuzzy)
- malformed / empty text
- Unicode handling
- long-text handling (analysis cap; grading still completes)

No external NLP provider. No external NLP API. No neural/LLM model is required for Phase 3. This is the approved Phase 3 NLP implementation. Do not replace it without a new approved phase.

#### Vision grading (approved Phase 3 implementation)

`backend/grading/vision.py`. Local image analysis:

- image decoding
- supported formats: PNG / JPEG / GIF / WebP
- dimensions
- image size
- missing / invalid / unreadable / low-quality detection
- remote image fetching
- duplicate URL caching (unique URLs fetched once)
- remote image count limit (`CATALOGFORGE_GRADE_MAX_REMOTE_IMAGES`, default **500**)
- byte limit **8MB** (`MAX_BYTES`)
- fetch timeout **15 seconds** (`DEFAULT_TIMEOUT`)
- SSRF protection (`assert_public_http_url` / public HTTP validation)
- local `/catalogue-assets/` path confinement
- local asset size checking before reading where applicable

No external vision provider. No neural CV model is required for Phase 3. This is the approved Phase 3 vision implementation. Do not replace it without a new approved phase.

Remote-image cap, byte limit, timeout, and duplicate-URL cache are **engineering safety controls**, not Phase 4 features.

#### Approved grading formula (`grading.v1`)

This is an **approved Phase 3 product decision**, not a proposal.

Engine: `grading.v1` (`ENGINE_VERSION` in `backend/grading/contract.py`)

Weights:

- Deterministic = 50%
- NLP = 25%
- Vision = 25%

Thresholds (inclusive lower bounds on the combined 0–100 score):

- A >= 90
- B >= 75
- C >= 60
- D >= 40
- F < 40

Any hard failure forces final grade **F**, regardless of the combined numerical score.

Do not silently modify `grading.v1`. Changing weights or thresholds requires a **new engine version** and **explicit product approval**.

#### Structured evidence

Phase 3 does not return only a prose score. Each finding is an `EvidenceItem`:

- category
- check_id
- severity
- result
- explanation
- path
- details

Evidence is persisted with the grading result (`deterministic_evidence`, `nlp_evidence`, `vision_evidence`, `hard_failures` on `GradingResult` / `catalogue_grades.payload`).

#### API

- `POST /catalogues/{id}/grade` — claim or compute grade for the stored canonical catalogue
- `GET /catalogues/{id}/grade` — completed grade for the current head revision + state hash

Authorization follows catalogue rules: session authentication, organization membership, catalogue scoped to user + organization. Unauthenticated / wrong-org / missing catalogue behave like other catalogue endpoints (same-class 401/403/404). In-flight grade: HTTP 409. Stage or persistence failure: generic HTTP 502 (`Grading could not be completed.`).

Not invoked from `POST /catalog/create`. No Phase 3 grading UI was added on the frontend. Do not invent additional HTTP endpoints.

Service-layer cancel exists in `backend/services/grading_service.py` / persist; there is no public HTTP cancel-grade route.

#### Persistence

Additive tables (Phase 1 migrator id unchanged: `phase1_canonical_v1`):

- `catalogue_grades`
- `catalogue_grade_jobs`

Identity / idempotency:

`catalogue_id` + `graded_head_revision` + `graded_state_hash` + `grading.v1`

- `graded_head_revision` = `MAX(catalogue_revisions.revision)`
- `graded_state_hash` = SHA-256 of the Phase 1 canonical state payload
- revision-bound and state-hash-bound
- unique COMPLETED grades and unique RUNNING jobs (partial unique indexes)
- repeating the same identity returns the existing completed result
- deleting a catalogue also deletes its grade jobs and grades
- additive DDL via `ensure_phase3_ddl`; no Phase 1 migration rewrite

#### Concurrency / atomicity

- `BEGIN IMMEDIATE` on claim and finish
- catalogue payload, head revision, and state hash snapshotted under that lock
- `claim_token` issued on claim / reclaim
- worker-owned COMPLETED / FAILED / CANCELLED transitions use CAS: `status = 'RUNNING' AND claim_token = ?`
- zero rows → `StaleClaim` (HTTP 409); a stale worker cannot overwrite a newer worker
- stale RUNNING jobs may be reclaimed with token rotation
- concurrent same-identity grade: in-flight → 409; completed → existing row
- concurrent catalogue revision changes identity; finish against a stale snapshot is rejected

**Invariant:** a job cannot become COMPLETED unless a matching persisted grade row has been confirmed. Unexpected persistence failure → **FAILED**, never COMPLETED without a grade row.

#### Error handling

Distinguish catalogue **quality** failure from grading **subsystem/processing** failure.

- Invalid / low-quality / missing image → quality finding → stage may complete → grade may persist
- Fetch / timeout / SSRF / oversized / remote-budget / unexpected inspect → processing failure → job **FAILED**
- NLP, vision, or deterministic stage exception → `GradingStageFailure` → job **FAILED**
- Persistence failure → job **FAILED**
- Stale claim → 409, no overwrite
- Cancellation (owning claim) → CANCELLED / 409 to caller
- Unexpected exceptions must not report success
- External API details for stage/persist failure stay generic (502)

#### Security

- session authentication
- organization membership
- catalogue authorization (user + org)
- SSRF protection and public HTTP URL validation
- local asset path confinement
- parameterized SQL
- input / remote-count / image-byte / timeout limits
- generic external error responses
- catalogue text and images are not sent to an external NLP/vision provider

#### Performance

- no per-item SQL N+1 (document snapshotted once; graders iterate in memory)
- duplicate image URL caching
- default 500 unique remote images; 8MB; 15s
- network fetch **outside** database transactions

#### Audit history

Phase 3 had an independent engineering audit covering correctness, completeness, race conditions, atomicity, dead code, unused imports, type safety, security, performance, idempotency, uncaught errors, data integrity, migration safety, backward compatibility, API behavior, and evidence correctness.

Confirmed defects and resolutions:

- **False COMPLETED** — persistence failure could yield an in-memory success. **Fixed:** COMPLETED requires a confirmed persisted grade; unexpected IntegrityError without a duplicate row → FAILED.
- **claim_token CAS** — stale workers could potentially finish after reclaim. **Fixed:** finish/fail/cancel CAS on RUNNING + claim_token.
- **Vision/NLP processing vs quality** — processing errors could be scored as quality. **Fixed:** processing failures fail the job; genuine quality findings remain evidence.
- **Synchronous remote-image risk** — unbounded fetches. **Fixed:** default 500 unique remotes, 8MB, 15s, duplicate URL cache, fetch outside DB TX.
- **Dead code / unused imports** — unused `collect()` and related unused code removed.
- **Exception paths** — stage/persist errors transition the job to FAILED rather than false success.

A product-definition review then **approved** `grading.v1` weights/thresholds and local NLP/vision as the Phase 3 implementations. Formula numbers were not changed.

#### Tests (Phase 3 closure baseline, 2026-08-20)

- Phase 3 focused: `python -m pytest tests/test_phase3_grading.py -q --tb=line` — **27 passed**
- Full backend: `python -m pytest -q --tb=line` — **323 passed**
- Compile: `python -m compileall backend scraper tests -q` — **PASS**

Not installed / not claimed: ruff, mypy, pyright, flake8, pylint.

Frontend: no Phase 3 grading UI; frontend grading tests were not applicable. Tests were not modified merely to make them pass.

#### Files / components

- `backend/grading/` — `contract.py`, `formula.py`, `deterministic.py`, `nlp.py`, `vision.py`, `orchestrator.py`, `persist.py`, `evidence.py`, `document.py`
- `backend/services/grading_service.py`
- `backend/migrate_catalogues.py` (additive Phase 3 DDL; migrator id still `phase1_canonical_v1`)
- `backend/store.py` (delete cascade for grades/jobs)
- `backend/main.py` (`POST`/`GET` `/catalogues/{id}/grade`)
- `tests/test_phase3_grading.py`
- `PHASE3_CLOSURE.md`
- `.cursor/rules/phase3-closed.mdc`

#### Phase 3 does NOT include

- recommendations
- auto-correction
- ranking
- fuzzy identity
- cross-platform identity
- scraper rewrite
- canonical persistence rewrite
- Phase 4 functionality
- autonomous agents
- neural/LLM NLP or neural CV
- external NLP/vision providers
- `grading.v2`

Do not pull future scope into Phase 3.

### Phase 4 — Baba Score + Platform Evaluation (PASS / CLOSED)

Official record: `PHASE4_CLOSURE.md`. Rule: `.cursor/rules/phase4-closed.mdc`.

Status: **PASS — CLOSED**

Purpose: keep Baba's evaluation independent of platform-native scores.

```
Canonical Catalogue
        ↓
   grading.v1 (unchanged)
        ↓
  Baba Score          Platform evaluation adapters (Swiggy / Zomato / Magicpin)
  (projection)                        ↓
                               Platform evidence
```

Invariant: **Platform Score != Baba Score**. Platform ratings may be stored, displayed, or used as evidence. They are never copied into Baba Score. Calibration is deferred.

- Adapters live under `backend/platform_eval/adapters/` and are selected by registry, not scattered `if platform == ...`.
- Evaluation consumes the stored canonical document (including ingested `SourceRating` / related links). No live platform HTTP in Phase 4.
- Identity: `catalogue_id + evaluated_head_revision + evaluated_state_hash + platform + platform_eval.v1`.
- Additive table `catalogue_platform_evaluations`; migrator id remains `phase1_canonical_v1`.
- APIs: `POST`/`GET /catalogues/{id}/platform-evaluation`, `GET /catalogues/{id}/baba-score`. Same session + org + catalogue authz as grading. Unsupported platform: 422. Stale revision: 409.
- `grading.v1` was not modified.

Phase 4 tests (closure): backend **339 passed**; Phase 4 focused **16 passed**; compileall PASS.

#### Phase 4 does NOT include

- score calibration / blending into Baba Score
- live platform APIs
- agents / LLM orchestration
- frontend evaluation UI
- Phase 5 functionality

### Phase 5 — Grade Explanation & Recommendations (PASS / CLOSED)

Official record: `PHASE5_CLOSURE.md`. Rule: `.cursor/rules/phase5-closed.mdc`.

Purpose: make persisted `grading.v1` understandable and actionable (Why? / What should I fix first?).

Read-time projection `grade_explain.v1`. No new tables. No agents. Overall grade copied from the grade row. Section grades are Deterministic / Text / Images from stored stage scores. Severity reuses Phase 3 `hard` / `ordinary` / `info`.

API: `GET /catalogues/{id}/grade-explanation`. UI: catalogue detail Grade panel.

### What must NOT be changed

Do not casually change closed-phase guarantees to solve unrelated future work. Do not change `grading.v1` in place. Do not add per-platform grading adapters. Do not invoke grading from ingest. Do not introduce an external NLP/CV provider as a silent Phase 3 change. Do not copy platform-native scores into Baba Score.

### Current project state

**CURRENT PHASE:** Phase 9 — Baba AI Catalogue Assistant — IMPLEMENTED (not CLOSED)

**NEXT PHASE:** Do not start Phase 10, 11, 12, or 13 without official approval.

**RULE:** Phase 0–8 remain CLOSED. Phase 7 media remains the implemented preview-only baseline. Do not reopen closed phases. Do not change `grading.v1`.

## 2. Current Project Status

**Phase 0 foundation:** PASS — **CLOSED**. Concurrency, atomicity, cancellation, crash recovery, security, and idempotency remain in force.

**Canonical catalogue Phase 1:** PASS — **CLOSED** (2026-08-20). Official handoff: `PHASE1_CLOSURE.md`.

**Catalogue ingestion & normalization Phase 2:** PASS — **CLOSED** (2026-08-20). Official handoff: `PHASE2_CLOSURE.md`. Do not reopen it for cosmetic work.

**Grading engine Phase 3:** PASS — **CLOSED** (2026-08-20). Official handoff: `PHASE3_CLOSURE.md`. Approved `grading.v1`: 50/25/25, A≥90 / B≥75 / C≥60 / D≥40 / F<40; local heuristic NLP and local image analysis (no neural models required).

**Phase 4:** PASS — **CLOSED** (2026-08-20). Official handoff: `PHASE4_CLOSURE.md`. Baba Score is a `grading.v1` projection. Swiggy/Zomato/Magicpin adapters emit platform evidence only. Calibration deferred.

**Phase 5:** PASS — CLOSED. Official handoff: `PHASE5_CLOSURE.md`. Derived `grade_explain.v1` over persisted `grading.v1`. No new tables. No agents.

| Platform | Restaurant | Dineout | Live verified | Status |
|----------|------------|---------|---------------|--------|
| Swiggy | Working (Chrome/CDP + fixtures) | Working with known gallery limitation | Yes (prior sessions) | Stable |
| Zomato | Implemented + fixture-tested (Order Online categories + dish_photos) | Implemented + fixture-tested (photos tab) | **Not live-verified** this session | Development — fixture menus attach dish URLs; live Hecto Baba cards were not re-scraped |
| Magicpin | Implemented + fixture-tested (Delivery nav + food CDN images) | Implemented + fixture-tested (store/photos gallery) | **Not live-verified** this session | Development — fixture menus attach food images; live cards were not re-scraped |

Status language used in this file:

- **Implemented**: code exists
- **Fixture-tested**: tests against `tests/fixtures/*` passed
- **Live-tested**: a real platform page was scraped in-session and results were checked
- **Partially working**: extraction returns some fields but acceptance fails (e.g. blank dish cards)
- **Known limitation / Deferred**: recorded in section 14

## 3. Architecture

Pipeline:

1. **URL** — user pastes a restaurant/store/order/delivery URL (`swiggy_url` field is the generic URL slot).
2. **Platform detection** — Create Catalogue UI requires an explicit platform. `scraper/platform.py` validates host vs selected platform. No silent switch.
3. **Catalogue type** — restaurant / dineout / both.
4. **Access** — `backend/services/catalog_service.py` loads HTML via Chrome/CDP (`collect_swiggy_source`, reused for all platforms) or local fixtures. CLI: `scraper/cli.py`.
5. **Extra tab follow** — Zomato `{venue}/order` + `{venue}/photos`; Magicpin `{store}/delivery` + `{store}/photos`. Not used for `--from-html` single-file mode unless mapped in tests.
6. **Live DOM harvest** — for Zomato/Magicpin, `scraper/platform_dom.py` + `scraper/platform_menu_harvest.js` click category nav, wait, collect cards into `raw.dom_menu`. Wired from `scraper/swiggy/scraper.py` after the existing Swiggy collect path. Do not expand Swiggy-specific collection while changing Zomato/Magicpin.
7. **Platform parser** — `parse_swiggy_catalogue` / `parse_zomato_catalogue` / `parse_magicpin_catalogue`.
8. **Normalized model** — `scraper/swiggy/models.py` (`Catalogue`, `Restaurant`, `DineoutVenue`, `MenuCategory`, `MenuItem`) as **adapter input**.
8b. **Canonical model (Phase 1, closed)** — `backend/canonical/` adapter → canonical document → `backend/store.py` dual-write; legacy API projection for the existing frontend. See `PHASE1_CLOSURE.md`.
8c. **Ingestion & normalization (Phase 2, closed)** — pending raw capture → validate/quality → deterministic normalize → `ExistingCatalogueAdapter` → existing Phase 1 persist → bind raw to catalogue id. See `PHASE2_CLOSURE.md`.
8d. **Grading engine (Phase 3, closed)** — downstream of canonical persistence. `POST /catalogues/{id}/grade` loads the canonical document, runs deterministic → local NLP → local vision, collects structured evidence, aggregates A–F with hard failures (`grading.v1`), persists against `graded_head_revision` + `graded_state_hash`. See `PHASE3_CLOSURE.md`.
8e. **Baba Score + platform evaluation (Phase 4, closed)** — sibling to grading. Baba Score is a labeled projection of a completed `grading.v1` result. Platform adapters evaluate ingested native ratings as evidence (`platform_eval.v1`) and persist per `catalogue_id + revision + state hash + platform`. See `PHASE4_CLOSURE.md`.
8f. **AI improvement engine (Phase 6, closed)** — preview-only proposals. See `PHASE6_CLOSURE.md`.
8g. **Generated media (Phase 7, implemented baseline)** — preview-only image/GIF jobs. Does not write `catalogues.payload`.
8h. **Customer review intelligence (Phase 8, CLOSED)** — first-party customer feedback, deterministic target/aspect/polarity/recurrence, item linkage, inspect-only recommendations. See `PHASE8_CLOSURE.md`.
9. **Image extraction** — dish `image_url` / `source_image_url` vs venue `gallery_images` vs offer images vs menu-page images.
10. **Asset materialization** — `scraper/swiggy/assets.py` `materialize_catalogue_images()` downloads HTTP images to `data/catalogue-assets/{catalogue_id}/` and rewrites to `/catalogue-assets/...`.
11. **Backend storage + API** — FastAPI in `backend/`; static files for catalogue assets.
12. **Frontend** — Next.js `frontend/`; rewrite `/catalogue-assets/*` to the API. Catalogue cards use `CatalogueImage` + `hasProductImage()`.

## 4. Repository Structure

- `scraper/discovery/` — location parse, platform listing adapters, pagination, dedupe, job queue helpers. Does **not** parse menus.
- `backend/services/area_service.py` — create area job, confirm selection, scrape-batch via `create_catalog`.
- `scraper/platform.py` — normalize platform, identify host, **reject** URL/platform mismatch. Consumed by CLI, backend, frontend validation helpers.
- `scraper/html_common.py` — shared HTML/JSON-LD helpers (tags, images, cuisine split, discovery cut). Used by Zomato/Magicpin parsers. Must stay platform-neutral if Swiggy is not to regress.
- `scraper/platform_dom.py` — wait/harvest helpers, dish-image URL rules, `categories_from_dom_menu`, HTML image fill/merge. Consumed by parsers and the Swiggy collector’s Zomato/Magicpin branch.
- `scraper/platform_menu_harvest.js` — in-page async harvest: click Magicpin `nav[aria-label="Menu categories"]` / `data-mp-delivery-sidebar-section`; click Zomato `Name (N)` sidebar; associate card images.
- `scraper/swiggy/scraper.py` — Chrome/CDP collect. **Stable.** Also invokes platform harvest for Zomato/Magicpin URLs. Do not change Swiggy collection logic unless required.
- `scraper/swiggy/parser.py` — Swiggy restaurant menu parser. **Do not modify for Zomato/Magicpin work.**
- `scraper/swiggy/dineout.py` — Swiggy Dineout. **Do not modify for Zomato/Magicpin work.**
- `scraper/swiggy/models.py` — shared dataclasses. Additive fields (`source_image_url`, `MenuCategory.item_count`) are allowed with defaults so Swiggy still works.
- `scraper/swiggy/assets.py` — download/rewrite images (Referer for zmtcdn / googleusercontent).
- `scraper/swiggy/chrome_session.py` — real Chrome attach.
- `scraper/zomato/parser.py` — Zomato identity, Order Online menu, photos merge.
- `scraper/magicpin/parser.py` — Magicpin store identity, Delivery menu, photos merge.
- `backend/grading/` — Phase 3 grading contract, deterministic/NLP/vision graders, aggregator, orchestrator, persistence.
- `backend/services/grading_service.py` — grade/get/cancel a stored catalogue.
- `backend/platform_eval/` — Phase 4 Baba Score projection, platform adapter registry, Swiggy/Zomato/Magicpin evidence adapters, persistence.
- `backend/services/platform_eval_service.py` — evaluate/get platform evidence for a stored catalogue.
- `PHASE3_CLOSURE.md` / `.cursor/rules/phase3-closed.mdc` — official Phase 3 closed record and Cursor rule.
- `PHASE4_CLOSURE.md` / `.cursor/rules/phase4-closed.mdc` — official Phase 4 closed record and Cursor rule.
- `backend/services/catalog_service.py` — create catalogue, follow extra tabs, choose parser.
- `backend/store.py` — persist payload; calls `materialize_catalogue_images`.
- `frontend/` — Hecto Baba UI (create form, catalogues, dineout view).
- `tests/` — pytest; fixtures in `tests/fixtures/`.
- `data/` — runtime catalogue assets (gitignored typically).
- `output/` — CLI JSON dumps.
- `auth/` — Better Auth related backend pieces.

`scraper/platform.py` important rule: if the user selects Swiggy, a Zomato or Magicpin URL must be rejected rather than auto-switching.

## LOCATION RESOLUTION & SCOPE

This is the shared India location layer for Baba AI / Hecto Baba. Restaurant discovery is the current use case; the resolver is **not** a Swiggy-only or restaurant-only module.

**Flow:** user request → query understanding (later) → **LocationResolver** (once per request) → **PlatformLocationResolver** (Swiggy / Zomato / Zomato District / Magicpin) → verify → cheap discovery metadata → physical vs delivery classification → user review → full venue scraper only for selected venues.

### 1. Why location resolution is centralized
Platforms must not independently guess “Puttur” vs “Mangalore” vs “Bengaluru”. A wrong city silently paginates the wrong delivery feed. One canonical `LocationQuery` is resolved first (`scraper/discovery/resolver.py`), then each adapter maps **platform city / slug / URL** without string-replacing city names in URLs.

### 2–3. Geocoding provider
Abstraction: `LocationProvider` (`Geocoder` alias) with `GoogleProvider`, `NominatimProvider`, `MapboxProvider`.

`select_location_provider()`:
- Pytest: no network (`PYTEST_CURRENT_TEST` → `None`; tests pass a `FakeGeocoder`).
- If `GOOGLE_MAPS_API_KEY` or `GOOGLE_GEOCODING_API_KEY` is set and `CATALOGFORGE_GEOCODER` is empty/`auto`/`google`: **Google Geocoding API** (Places/Address Validation are documented for production address checks; city/area search uses Geocoding).
- Else Mapbox if `MAPBOX_ACCESS_TOKEN` is set.
- Else **Nominatim / OpenStreetMap** (India `countrycodes=in`). Chosen as the default because this repo has **no Google Maps credentials in `.env.example`**. Nominatim is India-capable and needs no key.

Do not hardcode the whole system to one vendor.

### 4. Canonical location model
Reuse `LocationQuery` (`scraper/discovery/models.py`): `original`, `normalized`, `locality` (area), `city`, `state`, `country`, `postal_code`, `latitude`, `longitude`, `display_name`, `confidence`, `place_id`, `platform_places`.

Examples (geocoded):
- `Puttur` / `Puttur, Karnataka` → city Puttur, state Karnataka, country India
- `Indiranagar` → area Indiranagar, city Bengaluru, state Karnataka
- `Bangalore` → canonical city **Bengaluru** (alias only on the resolved city field, never URL rewrite)

Ambiguous `Puttur` (Karnataka vs Andhra Pradesh) raises `AmbiguousLocationError` — no random first hit.

### 5. Platform-specific city mapping
`canonical_city` stays Bengaluru. `platform_places[platform]` stores `city`, `slug`, `location_verified`, `url` from **that platform’s** canonical/HTML/URL (e.g. Zomato `bangalore`). Zomato dine-out listing URLs are used **only** when `location_verified` is true. Never `city.lower().replace(" ", "-")` and never `replace("mangalore", "puttur")`.

### 6. Stale location protection
Swiggy: header must match the requested place (`location_is_consistent`). Listing `GET /dapi/restaurants/list/v5` lat/lng must be within **75 km** of resolved coordinates, or discovery stops (`location_verified=false`). Other platforms: if a displayed location is present and does not match, discovery stops. `PlatformLocationResolver.bind` records an inferred slug; mismatch is not silently treated as verified.

### 7–8. Swiggy lat/lng delivery feed vs physical location
`GET /dapi/restaurants/list/v5` + `POST /dapi/restaurants/list/update` pagination is **unchanged**. Live exhaustion (Indiranagar): **197 batches**, **2937** raw URLs, **788** duplicates, **2149** unique, `exhausted=true`. That is a **delivery-to-pin** feed, not “2149 restaurants physically in Indiranagar.”

`discovery_scope=delivery_to_location`. Cheap listing `info.locality` / `areaName` (not `sla` distance) → `located_here` / `delivers_here` / `unknown`. Full restaurant scraper is not run for classification.

### 9. Zomato structured location
Prefer JSON-LD Restaurant (`address.*`, `geo.*`) and BreadcrumbList (`extract_zomato_place`). Do not use generated CSS class names. Dineout is `sub_source=dineout` vs ordinary restaurant discovery.

### 10. Zomato District
Separate adapter `scraper/discovery/district.py`: `platform=zomato`, `sub_source=district`. Listing URL only if `platform_places.district` is verified with a real `district.in` URL. **Not live-verified.** No invented `district.in/{slug}` from canonical city.

### 11. Magicpin
Same `LocationQuery` + `PlatformLocationResolver`. Slug from Magicpin URL/canonical, not a hardcoded Bangalore/Mangalore/Puttur table. Prefer JSON/canonical over styled-component classes.

### 12–13. Distance / KM
`distance_km` is a separate field (`DiscoveredVenue.distance_km`, from Swiggy `sla.lastMileTravel` when present). Values like `2.4 km` **must not** populate city, area, address, locality, or UI “Location”. Distance is optional metadata; show/filter it only when the user asked for a radius (or existing Dineout UI ranking). It is not proof of physical locality.

### 14. URL platform integrity
`platform_url_fields` / frontend `platformUrlSlots` assign URLs **by host**. A Zomato scrape may set `zomato_url` only. A Swiggy scrape must not fill `zomato_url`. Never copy Zomato into the Swiggy URL label (the API field `swiggy_url` remains the generic create-catalogue URL slot).

### 15–16. Cache and performance
`FileLocationCache` (`data/location-cache.json`) stores resolved canonical places. Geocode the **user request once**, not per restaurant. Classify from listing metadata. Extra geocoding only for ambiguous venue place strings (not implemented as a 2149×geocode loop).

### 17–19. Tests, live results, limitations
See changelog below. Pytest does not hit live sites. Live Nominatim geocodes (prior session) for Puttur / Indiranagar / Bengaluru / Mangaluru are recorded in the 2026-08-18 LocationResolver entry. **This pass did not re-run live Swiggy/Zomato/District/Magicpin listing jobs.** Do not claim those platforms are location-complete.

## LOCATION SELECTOR AUTOMATION

The shared `LocationResolver` is reused. There is no second geocoder/city table.

**Flow:** LocationResolver → `type_query` (area, else city — what a human types, e.g. `JP Nagar`) into the **platform header location control beside the logo** → wait for suggestions → `rank_location_suggestion` picks a location (not cuisine/search/phase/road/restaurant) → wait for header/navigation/API → `location_is_consistent` against `picker_query` (`JP Nagar, Bengaluru, Karnataka`; Bengaluru↔Bangalore allowed) → if fail, **stop**. Only then listing discovery and existing venue scrapers. Stale header locations (Indiranagar, Ashok Nagar, …) are replaced by this click-type-select path, not by rewriting URLs.

**Do not** `url.replace("mangalore", "puttur")`. City slugs come from the platform after a verified selection (canonical URL / header / network).

### Providers
- Canonical resolve: Google Geocoding if a key is present, else Mapbox, else Nominatim.
- **Google Places Autocomplete** is additive (`GoogleProvider.autocomplete`, `place_predictions`). It is not a rewrite of `resolve_location`. Without a Google key it is unused.
- Selector **typing** uses `type_query` (locality or city). **Verification** uses `picker_query`. Not a hardcoded Indian city list. `fill()` is avoided; Playwright `press_sequentially` / `type` with delay so autocomplete fires. `locate.js` types `opts.type || opts.query`.

### Canonical vs platform
Canonical city stays `Bengaluru`. Platform may store `platform_places[zomato].slug = bangalore` only after that platform’s own URL/HTML/network says so.

### UI selectors (semantic first, generated CSS fallback)
- **Swiggy** (`https://www.swiggy.com/restaurants`): header location chip (logo → location text → search → Swiggy Corporate). Playwright `_set_swiggy_location` clicks that control, types into `area, street` / location placeholders, picks `[role=option]`. Fallback: `locate.js`.
- **Zomato** (Zomato-only): open `https://www.zomato.com/mangalore/restaurants`, **not** `https://www.zomato.com/`. Then header location beside the logo (not restaurant/cuisine search). `_set_header_location` + `locate.js`. After the site location is verified, restaurant stays on that listing; Dineout follows Zomato’s Dining Out control / verified `/{slug}/dine-out`. Never rewrite `mangalore` in the URL.
- **Magicpin** (entry `https://magicpin.in/india/Bangalore/home/` — Bangalore in the path is only the working entry, not the requested city): header control next to the logo / `.selectedLocation` / `input.location` (“Search Location”), not the places/cuisines search box. Then Food Delivery or Budget/Fine Dining.

`locate.js` `phase=read` is the shared header reader. Styled-component class names remain fallbacks only.

### Verification and stale sessions
Header text (and Swiggy `list/v5` lat/lng vs resolved coords, 75 km) must match the request. A leftover Indiranagar/Mangalore/Bengaluru session **must not** continue for Puttur. Empty unverified Zomato/Magicpin headers now fail closed.

Network capture (placeId / cityId / lat / lng) is stored on `ListingPage.payload.location` when those APIs appear. IDs are not invented.

### Unchanged
Swiggy `GET /dapi/restaurants/list/v5` → `nextOffset`/`widgetOffset` → `POST /dapi/restaurants/list/update` until missing `nextOffset`. Restaurant scraper unchanged. KM still cannot become location. URL fields remain host-bound. Swiggy listings stay `delivery_to_location` (2149 unique Indiranagar exhaustion is a delivery feed). Dineout = zomato/`dineout`. District = zomato/`district` with no invented `district.in` city URL.

## LOCATION AUTOMATION HARDENING

Primary live target for this pass: **JP Nagar, Bengaluru, Karnataka** (area + city). Not Puttur.

**Canonical (Nominatim live):** locality `JP Nagar`, city `Bengaluru` (not Bangalore), state `Karnataka`, country `India`, lat 12.9096941, lng 77.5866067. `parse_location` already splits three comma parts into area/city/state; geocode must not promote JP Nagar to city.

**Suggestion matching:** `rank_location_suggestion` requires the area phrase when locality is set. Rejects restaurant/cuisine names, `… Road`, and numbered **phases** unless the request itself contains `phase`. Prefers `JP Nagar` + `Bengaluru`/`Bangalore` + `Karnataka`. Does not click the first unmatched suggestion. `location_is_consistent` requires the locality phrase, so `Indiranagar, Bengaluru` cannot satisfy a JP Nagar request (and `nagar` alone is not enough).

**Header targeting:** click the control **between the platform logo and** Swiggy Corporate / Zomato restaurant search / Magicpin places search. Cuisine chips and venue search are skipped. Generated CSS remains fallback only.

**Hard gate + retries:** up to 3 select attempts; if still unverified, discovery does not start. Browser platform state is not trusted from cache; only the canonical geocode is cached.

**Google:** Places Autocomplete + Geocoding remain optional on `GoogleProvider`. No key in this environment — Nominatim used. Google does not click platform UIs.

**LIVE (this pass, isolated Playwright + Cursor browser; Chrome CDP 9222 closed / timed out):**
- Swiggy `https://www.swiggy.com/`: Playwright `Page.goto` → `net::ERR_HTTP_RESPONSE_CODE_FAILURE`. Cursor browser tab was a blank/black page. **NOT LIVE VERIFIED.** Discovery not started.
- Zomato / Magicpin Playwright `verify_only`: run aborted before a result. Prior session: Zomato HTTP2 error; Magicpin Arya Nagar fail-closed.
- Dineout / District: not live-verified. District still has no invented city URL and no mapped District location UI.
- AI/browser-agent fallback: **not used** (and not allowed to skip verification).

Do not claim JP Nagar was selected on any platform website this pass.

## DISCOVERY JOB LIFECYCLE (CONFIRMED)

- A discovery job is an `area_jobs` SQLite row: requested location, platforms, type, status, discovery venue list, error.
- Status `failed` is stored when `LocationSelectionError` or `AmbiguousLocationError` is raised during create (venues empty).
- Catalogues created later from selected venues are `catalogues` rows. Deleting the job does not delete those catalogues.
- Failed jobs can be removed from City / Areas with confirmation. The job must not reappear after list reload (row is gone).

## DELETION (CONFIRMED)

- Catalogue delete: hard `DELETE FROM catalogues` plus owned `catalogue-assets/{id}` directory. Not a soft-delete column. Not UI-hide-only.
- Discovery-job delete: hard `DELETE FROM area_jobs` only. Discovery-only venue JSON lives in that payload.
- Do not cascade-delete shared restaurant rows (there is no shared restaurant table beyond catalogue payload JSON).

## 5. Platform Routing

Create Catalogue UI asks for:

- Platform: Swiggy / Zomato / Magicpin
- Catalogue type: Restaurant / Dineout / Both
- URL (same request field `swiggy_url`)

Examples:

- Selected platform = Swiggy, URL = `zomato.com/...` → validation error
- Selected platform = Magicpin, URL = `magicpin.in/...` → accepted

CLI `--platform` uses the same check. Parsers are selected only after validation.

Browser collect still goes through `collect_swiggy_source` (name is historical). Platform parsers run on the resulting `RawSource`.

## 6. Restaurant vs Dineout

**Restaurant:** delivery/order catalogue — categories, dishes, prices, veg/non-veg, dish photos, restaurant identity, offers.

**Dineout:** venue/dining — venue name, offers, popular dishes/cuisines, venue photos, scanned menu pages, amenities, location/map/directions, about.

Platform-specific:

- Swiggy: dedicated dineout extractor + Chrome gallery open.
- Zomato: Overview JSON-LD + `/photos` gallery; menu from `/order`.
- Magicpin: store page identity/offers; priced menu from `/delivery`; venue photos from `/photos`.

## 7. Swiggy — IMPORTANT STABLE AREA

Swiggy extraction is the working/stable area:

- Chrome/CDP (`scraper/swiggy/chrome_session.py`, `scraper/swiggy/scraper.py`)
- Playwright/browser modes exist historically; production path is real Chrome
- `scraper/swiggy/parser.py` restaurant menu
- `scraper/swiggy/dineout.py` Dineout
- primary venue identification, recommendation exclusion
- venue photos, menu, offers, location/map
- image materialization

**Do not modify** `scraper/swiggy/dineout.py`, `parser.py`, or `scraper.py` for Zomato/Magicpin unless a platform-neutral shared utility is required. Existing Swiggy tests must stay green.

Deferred: some Swiggy Dineout photo-gallery cases still miss images that only appear after a heavy in-page gallery UI. Do not “fix” that by changing Zomato/Magicpin parsers.

## 8. Zomato

URL patterns:

- Venue: `https://www.zomato.com/{city}/{slug}`
- Order Online: `{venue}/order`
- Photos: `{venue}/photos`

Menu: discover `Name (N)` category rows dynamically. Do **not** hardcode “Our Traditional Briyani”, “Starters”, etc. Those are reference examples from Ambur Star Briyani Since 1890.

Dish images: `b.zmtcdn.com/data/dish_photos/...` via `img src`, `srcset`, `data-src`, or `background-image`. Associate with the dish card, not the restaurant hero (`data/pictures/...`).

Must **not** become dishes: cuisine tags (Chinese, Biryani, …), Open now, Call, phone numbers, direction-line, restaurant metadata, Similar restaurants.

Live category list for Ambur Star (reference only, from the product task — not hardcoded):

Our Traditional Briyani, Starters, Main Course, Egg Special, Special Parotta, Rice And Noodles, Dessert, Sides / Extra, and any others on the live sidebar.

## 9. Magicpin

URL patterns:

- Store: `https://magicpin.in/{city}/{area}/Restaurant/{name}/store/{id}`
- Delivery (priced menu): `{store}/delivery`
- Photos: `{store}/photos?img=photos&id=1`

The store/photos page can expose many venue Google photos. That is **not** the food menu.

Selectors still used:

- `nav[aria-label="Menu categories"]`
- `data-mp-delivery-sidebar-section`

**Sponsored Deals Near You** sits above the Delivery menu. It must not terminate parsing. Stop at “more restaurants” / similar discovery chrome, not at sponsored deals.

Reference categories (Biryani Trip Delivery — examples only): Recommended, Biryani Family Pack, Daily Hyderabadi Mini Biryanis, Ghee Rice Bowls, Veg Biryanis, Bangalore Veg Donne Biryanis, Non Veg Biryanis, Biryani Add Ons, Starters, Desserts, Beverages.

First `img` in a card is often `magicpin.in/images/merchant/veg-icon.svg`. That is **not** a dish photo.

## 10. Category Extraction Rules

Discover categories from the live sidebar/nav. Never hardcode a restaurant’s list. Preserve `category.name`, `category.item_count` from `(N)` when present, and `category.items[]`.

“All” is a Hecto Baba UI filter, not a source category.

Category → item association must follow the section the platform shows (e.g. Hyderabadi Chicken Dum Biryani under Non Veg Biryanis, not dumped into Recommended).

A real Delivery “Recommended” section with priced food cards is allowed. Platform widgets (“More restaurants”, “Sponsored Deals Near You”) are not.

## 11. Image Architecture

Keep independent:

1. Hero
2. Venue/gallery photos (`dineout.gallery_images`, `source_url` after materialize)
3. Menu/dish images (`item.image_url`, `item.source_image_url`)
4. Menu-page scans (`dineout.menu_pages`)
5. Offer images
6. Location/map image (do not treat maps URLs as downloadable venue photos)

Flow: remote URL → `materialize_catalogue_images()` → `data/catalogue-assets/{id}/` → `/catalogue-assets/{id}/{file}` → FastAPI static → Next.js rewrite → `CatalogueImage`.

A venue photo must never silently become a dish image. Offer banners and maps must not become dish or venue photos.

## 12. Image Debugging Procedure

When a dish card is blank, debug in this order:

1. Live DOM (card-level candidates: src, srcset, data-src, background-image)
2. Candidate URLs
3. Parser output (`image_url` / `source_image_url`)
4. Saved JSON
5. Asset materialization (file exists under `data/catalogue-assets/`)
6. API response
7. Frontend props (`hasProductImage`)
8. Browser network for `/catalogue-assets/...`
9. Rendered `<img>`

Do not randomly patch every layer.

Lazy load: click each category, scroll the section enough to resolve images, wait briefly, collect, move on. Do not endless-scroll the whole page.

Known loss points already seen in product:

- Veg/non-veg **icons** stored as `image_url` → frontend `onError` / `hasProductImage` rejects → gray box
- Materialized `/catalogue-assets/...` rejected when `hasProductImage` only allowed `https?:`
- Catalogue header `Images: N` counting gallery photos while cards use `item.image_url`

## 13. Testing

```bash
python -m pytest
cd frontend
npm test
npm run typecheck
npm run lint
```

**Phase 4 closure baseline (2026-08-20, commands actually run):**

- Phase 4 focused: **16 passed** (`python -m pytest tests/test_phase4_platform_eval.py -q --tb=line`)
- Phase 3 + 4 focused: **43 passed**
- Full backend: **339 passed** (`python -m pytest -q --tb=line`)
- Compile: **PASS** (`python -m compileall backend scraper tests -q`)
- ruff / mypy / pyright / flake8 / pylint: **not installed** — not claimed
- Frontend Phase 4 UI: **not applicable** (no evaluation UI)

**Phase 3 closure baseline (2026-08-20, commands actually run):**

- Phase 3 focused: **27 passed** (`python -m pytest tests/test_phase3_grading.py -q --tb=line`)
- Full backend: **323 passed** (`python -m pytest -q --tb=line`)
- Compile: **PASS** (`python -m compileall backend scraper tests -q`)
- ruff / mypy / pyright / flake8 / pylint: **not installed** — not claimed
- Frontend grading: **not applicable** (no Phase 3 grading UI)

Earlier recorded results (2026-08-17, pre–Phase 1–3; do not treat as current backend count):

- Python: **119 passed** (`python -m pytest`, 2026-08-17)
- Frontend (targeted that change): catalogue-menu, catalogue-view, side-nav vitest **passed**. Full `npm test` last recorded 107 passed / 1 unrelated session-gate timeout.
- Frontend typecheck: **passed** (`npm run typecheck`)
- Frontend lint: **passed** (`npm run lint`, no ESLint warnings)

Pytest must not hit live Zomato/Magicpin.

## 14. Known Limitations

- **Live Zomato/Magicpin dish cards in Hecto Baba** — not re-scraped this session. Fixture-tested dish `image_url` + `/catalogue-assets/` `hasProductImage`. Until a live Chrome scrape + UI check, treat frontend render as **unverified**.
- **Live Zomato item count ~19** previously observed in UI. Harvest now clicks each `Name (N)` sidebar row and keeps empty categories with counts. Still **not live-tested**.
- **Swiggy Dineout photo gallery** sometimes incomplete without opening the full gallery UI. Deferred; do not regress Swiggy to fix other platforms.
- **Official Swiggy partner API** not implemented (`pending` if that access mode is selected).
- **Unrelated frontend flake:** create-catalogue session-gate test can time out at 5s on a slow machine.

## 15. Important Decisions

**Decision:** Phase 3 `grading.v1` formula is the approved product decision (50% deterministic / 25% NLP / 25% vision; A≥90, B≥75, C≥60, D≥40, F<40; hard failures force F).  
**Reason:** Official Phase 3 required A–F and hard failures; numeric weights were an engineering proposal then explicitly approved at closure.  
**Alternatives:** Leave weights unresolved; invent neural NLP/CV requirements; create `grading.v2`.  
**Why rejected:** Founder approved `grading.v1` and local heuristic NLP/vision. Changing the formula requires a new engine version and explicit approval.

**Decision:** Phase 3 NLP and vision are local on-host analysis, not neural models or external providers.  
**Reason:** Official wording required text/content quality evaluation and computer-based image analysis, not a named LLM or CV network.  
**Alternatives:** Require an LLM or neural CV before closing Phase 3.  
**Why rejected:** That would invent a stricter requirement than the approved specification.

**Decision:** Explicit platform selection + URL host validation.  
**Reason:** Prevent silently parsing the wrong site.  
**Alternatives:** Infer platform from URL only.  
**Why rejected:** User can select Swiggy and paste Zomato; that must error.

**Decision:** Fixture-backed parsers for Zomato/Magicpin; no live pytest.  
**Reason:** Live pages are bot-blocked/flaky; tests must be deterministic.  
**Alternatives:** Hit live URLs in CI.  
**Why rejected:** Unstable and against project rules.

**Decision:** Preserve Swiggy extractor files during Zomato/Magicpin work.  
**Reason:** Swiggy is the stable production path.  
**Alternatives:** Unify all platforms in one parser.  
**Why rejected:** High regression risk.

**Decision:** Separate Dineout vs restaurant extraction.  
**Reason:** Different pages and image types.  
**Alternatives:** One blob of all images.  
**Why rejected:** Inflates “menu images” and mis-labels venue photos as dishes.

**Decision:** Dynamic categories from sidebar/nav, never restaurant-specific names.  
**Reason:** Menus change; other restaurants differ.  
**Alternatives:** Hardcode Ambur/Biryani Trip lists.  
**Why rejected:** Breaks tomorrow’s menu.

**Decision:** Materialize images locally.  
**Reason:** CDNs block hotlinking; UI needs stable URLs.  
**Alternatives:** Use remote URLs only.  
**Why rejected:** Blank cards from Referer/hotlink failures.

**Decision:** Exclude recommendation/sponsored widgets.  
**Reason:** Not the restaurant’s menu.  
**Alternatives:** Parse entire page text.  
**Why rejected:** Fake dishes and truncated menus.

## 16. Failed Approaches

**Problem:** Magicpin menu returned zero items.  
**Failed approach:** Parsing the store/photos page as the menu.  
**Why it failed:** Priced cards live under `/delivery`. Photos inflate gallery (`Images: 95`) with no dishes.  
**Solution:** Follow `{store}/delivery`; parse category nav + delivery sections.

**Problem:** Magicpin menu empty even on Delivery HTML.  
**Failed approach:** Cutting the document at “Sponsored Deals Near You”.  
**Why it failed:** That block is *above* the real menu, so a prefix cut dropped everything.  
**Solution:** Start at sidebar / “Recommended (N)” / Order Online; stop at “more restaurants”, not sponsored deals.

**Problem:** Zomato extracted hundreds of fake dishes.  
**Failed approach:** Treating cuisine tags and chrome (`Open now`, `Call`, phone, `Chinese`) as menu headings/items.  
**Why it failed:** Identity page text looks like a list.  
**Solution:** Start menu parse after “Search within menu”; skip chrome and cuisine-only tokens.

**Problem:** Zomato dishes had no `image_url`.  
**Failed approach:** Assuming `img` appears *before* the dish name.  
**Why it failed:** Order Online cards often emit name, then `srcset` / `background-image` `dish_photos`.  
**Solution:** Pending image after the name; `expose_media_urls`; alt/name fill from HTML.

**Problem:** Magicpin `image_url` set but cards still gray.  
**Failed approach:** Taking the first `img.src` in the card.  
**Why it failed:** First image is veg/non-veg icon SVG. Frontend error/fallback.  
**Solution:** Skip icon URLs; require googleusercontent (or similar food CDN) on the same card.

**Problem:** Materialized photos still blank.  
**Failed approach:** `hasProductImage` requiring `^https?:`.  
**Why it failed:** After materialize, URLs are `/catalogue-assets/{id}/...`.  
**Solution:** Accept that prefix; still reject veg-icon/web_assets.

**Problem:** Counting `Images: 69` as success.  
**Failed approach:** Catalogue-level gallery + hero counts.  
**Why it failed:** Cards render `item.image_url` only.  
**Solution:** Debug one item end-to-end; keep gallery separate from dish images.

## 17. Development Procedure

1. Read this file.
2. Inspect the relevant live page (or fixtures if live is blocked).
3. Reproduce the issue.
4. Identify the exact DOM/data source.
5. Smallest change; do not rewrite Swiggy.
6. Add/update fixture tests.
7. Run platform tests, then full pytest.
8. Run frontend `npm test`, `typecheck`, `lint`.
9. Live-verify only if a real scrape is performed; say so honestly.
10. Update AGENT.md (status, limitations, changelog, current task, test counts).

## 18. Change Log

### 2026-08-20 — Phase 5 Grade Explanation & Recommendations CLOSED

**Date:** 2026-08-20  
**Task:** Final Phase 5 audit, defect fixes, and official closure.  
**Files changed:** `backend/grade_explain/explain.py`, `backend/services/grade_explain_service.py`, catalogue detail page, `tests/test_phase5_grade_explain.py`, `PHASE5.md`, `PHASE5_CLOSURE.md`, `.cursor/rules/phase5-closed.mdc`, closed-phase Cursor rules, `AGENT.md`  
**What:** Audit passed after mapping dishonest payloads to 502 and surfacing explanation load errors in the UI. No `grading.v1` / Baba Score / platform-evidence changes.  
**Why:** Official Phase 5 definition of done.  
**Tests:** Phase 3+4+5 focused **75 passed**. Full backend **371 passed**. Frontend **144 passed**. `compileall` PASS.  
**Live verification:** None.  
**Remaining:** Phase 0–5 closed. Later phases require an official roadmap.

### 2026-08-20 — Phase 5 Grade Explanation & Recommendations implemented (NOT CLOSED)

**Date:** 2026-08-20  
**Task:** Official Phase 5 implementation: explain persisted `grading.v1` and emit prioritized recommendations plus Grade UI.  
**Files changed:** `backend/grade_explain/*`, `backend/services/grade_explain_service.py`, `backend/main.py`, `tests/test_phase5_grade_explain.py`, `frontend/src/lib/grade-types.ts`, `frontend/src/lib/catalog-api.ts`, `frontend/src/components/grade-explanation-view.tsx`, catalogue detail page and Next proxies, `PHASE5.md`, `AGENT.md`  
**What:** Derived `grade_explain.v1` from the completed grade row. No new tables. No agents. `grading.v1`, Baba Score, and platform evidence unchanged.  
**Why:** Official authorized Phase 5 scope.  
**Tests:** Phase 3+4+5 focused **73 passed**. Full backend **369 passed**. Frontend **143 passed**. `compileall` PASS. Python type checkers not installed. Frontend `tsc`/`lint` still fail on pre-existing files.  
**Live verification:** None.  
**Remaining:** Phase 5 is **not** CLOSED. Do not write `PHASE5_CLOSURE.md` until official closure.

### 2026-08-20 — Phase 4 Baba Score + Platform Evaluation CLOSED

**Date:** 2026-08-20  
**Task:** Implement official Phase 4 (Baba Score independent of platform-native evidence; Swiggy/Zomato/Magicpin adapters).  
**Files changed:** `backend/platform_eval/*`, `backend/services/platform_eval_service.py`, `backend/migrate_catalogues.py`, `backend/store.py`, `backend/main.py`, `tests/test_phase4_platform_eval.py`, `PHASE4_CLOSURE.md`, `.cursor/rules/phase4-closed.mdc`, closed-phase Cursor rules, `AGENT.md`  
**What:** Additive `catalogue_platform_evaluations`. Baba Score is a `grading.v1` projection. Platform adapters emit evidence only. No calibration, no agents, no live platform HTTP. `grading.v1` unchanged.  
**Why:** Official approved Phase 4 scope.  
**Tests:** Phase 4 focused **16 passed**. Full backend **339 passed**. `compileall` PASS.  
**Live verification:** None.  
**Remaining:** Phase 5 has not started.

### 2026-08-20 — AGENT.md canonical handoff through Phase 3

**Date:** 2026-08-20  
**Task:** Expand `AGENT.md` so a fresh session has the complete Phase 0–3 handoff (no implementation changes).  
**Files changed:** `AGENT.md`  
**What:** Recorded closed-phase status including Phase 4 NOT STARTED; Phase 0–2 preservation; full Phase 3 architecture, formula, NLP/vision approval, persistence, concurrency, audit/fix history, tests, API, files, and exclusions.  
**Why:** `AGENT.md` is the high-level project memory; `PHASE3_CLOSURE.md` remains the official Phase 3 record.  
**Tests:** Not re-run (documentation only). Closure baseline remains 27 / 323 / compileall PASS.  
**Live verification:** None.  
**Remaining:** Phase 4 has not started.

### 2026-08-20 — Baba grading engine Phase 3 CLOSED

**Date:** 2026-08-20  
**Task:** Official final closure of Phase 3 after explicit product approval of `grading.v1` and local NLP/vision.  
**Files changed:** `PHASE3_CLOSURE.md`, `.cursor/rules/phase3-closed.mdc`, `.cursor/rules/phase1-closed.mdc`, `.cursor/rules/phase2-closed.mdc`, `backend/grading/formula.py`, `backend/grading/nlp.py`, `backend/grading/vision.py`, `backend/grading/orchestrator.py`, `AGENT.md`  
**What:** Recorded approved weights 50/25/25, thresholds 90/75/60/40, local heuristic NLP, local image analysis, persistence/concurrency/security/performance guarantees. Formula numbers unchanged.  
**Why:** Founder approved the product decision; Phase 3 must not be reopened for cosmetic work.  
**Tests (closure baseline):** Phase 3 focused **27 passed**. Full backend **323 passed**. `compileall` PASS.  
**Live verification:** None required for this closure record.  
**Remaining:** Phase 4 has not started. Do not implement it until an official Phase 4 roadmap is audited, planned, reviewed, and approved.

### 2026-08-20 — Phase 3 audit fix pass

**Date:** 2026-08-20  
**Task:** Fix confirmed independent-audit findings only (false COMPLETED, claim_token CAS, vision processing vs quality, sync image bounds, dead code, exception paths).  
**Files changed:** `backend/grading/persist.py`, `backend/grading/vision.py`, `backend/grading/evidence.py`, `backend/services/grading_service.py`, `backend/main.py`, `tests/test_phase3_grading.py`, `AGENT.md`  
**What:** COMPLETED only after a confirmed `catalogue_grades` row; unexpected IntegrityError → FAILED; finish/fail/cancel CAS on RUNNING+claim_token; fetch/timeout/oversized/budget/SSRF fail the job instead of scoring B; unique remote fetches capped (default 500, `CATALOGFORGE_GRADE_MAX_REMOTE_IMAGES`) with existing 8MB/timeout limits; removed unused `collect()`.  
**Why:** Audit HIGH/MEDIUM defects. Formula and NLP/CV product questions unchanged.  
**Tests:** Phase 3 focused **27 passed**. Full backend **323 passed**. `compileall` PASS.  
**Live verification:** None.  
**Remaining:** Product decisions on `grading.v1` weights and whether heuristic NLP/vision close Phase 3. Phase 3 is **not** CLOSED.

### 2026-08-20 — Phase 3 Baba Grading Engine implemented (CONDITIONAL)

**Date:** 2026-08-20  
**Task:** Phase 3 grading engine on canonical catalogues (deterministic + local NLP + local vision + A–F + evidence + persistence + API).  
**Files changed:** `backend/grading/*`, `backend/services/grading_service.py`, `backend/migrate_catalogues.py`, `backend/store.py`, `backend/main.py`, `tests/test_phase3_grading.py`, `AGENT.md`  
**What:** Additive `catalogue_grades` / `catalogue_grade_jobs`. Grading is downstream of ingest. Engine version `grading.v1`. NLP and vision are local (no external provider). Remote images use existing SSRF checks.  
**Why:** Official Phase 3 roadmap.  
**Tests:** Backend **314 passed** (Phase 2 baseline 296 + 18 Phase 3). `compileall` PASS. Frontend not changed; not re-run.  
**Live verification:** None.  
**Remaining / CONDITIONAL:** Official roadmap did not specify A–F numeric weights or that NLP/vision must be neural models. `backend/grading/formula.py` documents the v1 assumption. Founder should confirm or issue `grading.v2` weights. Phase 3 is **not** officially CLOSED.

### 2026-08-20 — Catalogue ingestion Phase 2 CLOSED

**Date:** 2026-08-20  
**Task:** Official final closure of Phase 2 (Catalogue Ingestion & Normalization). No further Phase 2 code changes.  
**Files changed:** `PHASE2_CLOSURE.md`, `.cursor/rules/phase2-closed.mdc`, `.cursor/rules/phase1-closed.mdc`, `AGENT.md`  
**What:** Recorded ingest pipeline, raw retention (no truncation, no janitor), deterministic normalize/validate/duplicate reporting, `ExistingCatalogueAdapter` reuse, Phase 1 persist feed, adapter double-failure behavior, crash/cancel/bind ordering, audit results, and out-of-scope list.  
**Why:** Handoff for future phases; Phase 2 must not be reopened for cosmetic refactoring.  
**Tests (closure baseline):** Backend **296 passed**. Relevant frontend **78 passed**. `py_compile` PASS. Phase 2 focused tests PASS. Phase 1 regression PASS.  
**Live verification:** None required for this closure record.  
**Remaining:** Phase 3 is **NOT STARTED**. Do not implement it until an official Phase 3 roadmap is audited, planned, reviewed, and approved.

### 2026-08-20 — Canonical catalogue Phase 1 CLOSED

**Date:** 2026-08-20  
**Task:** Official final closure of canonical catalogue Phase 1. No further Phase 1 code changes.  
**Files changed:** `PHASE1_CLOSURE.md`, `.cursor/rules/phase1-closed.mdc`, `AGENT.md`  
**What:** Recorded architecture, identity, provenance, revisions, identity-conflict 409, concurrency, migrator skip-on-applied, FK pragma, adapter boundary, audit results, and known limitations that must not auto-expand into Phase 2.  
**Why:** Handoff for future phases; Phase 1 must not be reopened for cosmetic refactoring.  
**Tests (closure baseline):** Backend **280 passed**. Focused canonical/store **19**. Migration **5**. Foreign keys **3**. Idempotency/concurrency **11**. Relevant frontend **35**. `py_compile` PASS. Identity-conflict regressions PASS.  
**Live verification:** None required for this closure record.  
**Remaining:** Official Phase 2 roadmap is the source of truth. Do not start Phase 2 from Phase 1 limitations.

### 2026-08-17 — AGENT.md created (pre-fix snapshot)

**Date:** 2026-08-17  
**Task:** Project memory + start of Zomato/Magicpin complete categories and dish images  
**Files changed:** `AGENT.md` (this file)  
**What:** Documented architecture, failed approaches, and the blank-card / incomplete-category bugs from Hecto Baba screenshots.  
**Why:** Required handoff so later sessions do not repeat store-page or sponsored-cut mistakes.  
**Tests:** Not run at file creation.  
**Live verification:** None.  
**Remaining:** Implement category completeness + dish `image_url` through materialize/frontend; then update this log.

### 2026-08-17 — Zomato/Magicpin categories + dish images

**Date:** 2026-08-17  
**Task:** Complete dynamic category extraction and per-item food images for Zomato Order Online and Magicpin Delivery (do not touch Swiggy extractors).  
**Files changed:**
- `AGENT.md`
- `scraper/platform_dom.py`
- `scraper/platform_menu_harvest.js`
- `scraper/zomato/parser.py`
- `scraper/magicpin/parser.py`
- `tests/fixtures/zomato_order.html`
- `tests/fixtures/magicpin_delivery.html`
- `tests/test_platforms.py`
- `tests/test_catalogue_assets.py`
- `frontend/src/lib/catalogue-menu.test.ts`
- (already present from earlier work, still required for render) `frontend/src/lib/catalogue-menu.ts` `hasProductImage` local-asset + veg-icon reject; `scraper/swiggy/assets.py` Referer + `source_image_url`; `scraper/swiggy/models.py` additive fields

**What:**
- Seed **all** sidebar `Name (N)` / `data-mp-delivery-sidebar-section` categories, including empty ones with `item_count`.
- Associate dishes with those categories; do not drop empty sidebar rows.
- Dish images from `src` / `srcset` / `data-src` / `background-image`; skip veg-icon SVGs; accept Magicpin `googleusercontent` including `=w400-rw` on a priced card (still reject `=w200-rw` thumbs and icons).
- Do not put Zomato `dish_photos` into venue gallery.
- Catalogue `image_count` for these platforms is **dish images** when the menu has items (gallery stays on `dineout.gallery_images`).
- Harvest JS clicks each category, short-scrolls, keeps categories with counts even if 0 items collected live.
- Frontend tests assert `/catalogue-assets/` is a real product image.

**Why:** Screenshots showed full-looking sidebars or `Images: 69` while cards were gray: veg icons stored as photos, materialized paths rejected, gallery counted as menu images, and Zomato sidebar categories dropped when they had no items yet.

**Tests:** Python 118 passed. Frontend 107 passed / 1 unrelated timeout. typecheck + lint passed.

**Live verification:** **Not done.** Fixture traces only:

Magicpin Paneer Makhni Biryani → Veg Biryanis → googleusercontent `w512-rw`.  
Zomato Ambur Egg Biryani → Our Traditional Briyani → `dish_photos` JPEG.

**Remaining:** Re-scrape live Magicpin Biryani Trip `/delivery` and Zomato Ambur Star `/order` in Chrome, materialize assets, confirm the actual Hecto Baba card `<img>` (not just JSON).

### 2026-08-17 — Category clicks + Hecto Baba collapse

**Date:** 2026-08-17  
**Task:** Menu category clicks showed a blank panel (Dessert/Beverages); move sidebar collapse onto the Hecto Baba label.  
**Files changed:**
- `scraper/platform_dom.py` (`merge_category_items`)
- `scraper/platform_menu_harvest.js` (collect only cards in the selected section)
- `scraper/zomato/parser.py`, `scraper/magicpin/parser.py`
- `frontend/src/lib/catalogue-menu.ts`
- `frontend/src/components/catalogue-view.tsx`
- `frontend/src/components/nav/side-nav/index.tsx`
- `frontend/src/components/nav/side-nav/components/brand.tsx`
- tests/fixtures and tests

**What:** Harvest was dumping every visible card into each clicked sidebar row, leaving later categories empty. Sequential parser items are now copied into those named sections. The UI keeps the selected category mounted and scrolls after render. Collapse control is the Hecto Baba / HB label; the bottom Collapse button is gone.

**Tests:** Python 119 passed. Targeted frontend vitest (catalogue-menu, catalogue-view, side-nav) passed.

**Live verification:** Not done. Re-open an existing catalogue or re-scrape to confirm Dessert/Beverages cards in the UI.

### 2026-08-17 — Dineout photos/offers, sidebar label, profile

**Date:** 2026-08-17  
**Task:** Zomato/Magicpin Dineout gallery + dining flash-card offers; maps/directions as one control when they share a URL; sidebar collapse only on the Hecto Baba text; profile/settings fields.  
**Files changed:**
- `scraper/html_common.py`, `scraper/platform_dom.py`, `scraper/platform_menu_harvest.js`
- `scraper/zomato/parser.py`, `scraper/magicpin/parser.py`
- `tests/fixtures/zomato_venue.html`, `zomato_photos.html`, `magicpin_store.html`, `magicpin_photos.html`
- `tests/test_platforms.py`
- `frontend/src/components/nav/side-nav/components/brand.tsx`, `profile-menu.tsx`
- `frontend/src/components/dineout-venue-view.tsx`
- `frontend/src/lib/account-profile.ts`, `restaurant-identity.ts`
- `frontend/src/app/(dashboard)/profile/page.tsx`, `settings/page.tsx`
- related tests

**What:**
- Magicpin venue gallery drops nearby `w400` widgets and non-restaurant alts (repair, insurance); keeps store/google venue photos; maps URL `https://www.google.com/maps?q=lat,lng` is both location and directions.
- Zomato Dining Offers parsed as titled offers; `/photos` gallery keeps extra `data/pictures` URLs and still drops similar-restaurant images.
- Dineout offers render as flash cards even without an offer image. If maps and directions are the same URL, only **Directions** is shown (Swiggy still shows Open in Maps + Directions when the two URLs differ).
- Sidebar collapse is the Hecto Baba / HB **label** only, not the header background or empty sidebar space.
- Profile card + Edit Profile (personal vs business, stored in `localStorage` per user id). Settings: change password (Better Auth if available), notification prefs, account settings, logout.
- Unlabeled leftover `dish_photos` / food CDN URLs can be attached to dishes still missing an image (best-effort; re-scrape required for old catalogues).

**Why:** Screenshots showed gray Zomato dish cards, Magicpin Dineout picking nearby businesses, empty offer carousels, duplicate maps buttons, sidebar toggling from blank clicks, and a stub profile.

**Tests:** Python **119 passed**. Targeted frontend vitest **32 passed** (dineout-venue-view, side-nav, account-profile, profile/settings pages, restaurant-identity). Full `npm test` not run this pass.

**Live verification:** **Not done.** Existing saved catalogues are not rewritten; re-create Zomato/Magicpin Dineout (and Order Online) catalogues to pick up offers, gallery filters, and leftover dish images.

### 2026-08-17 — Area / city-wise discovery

**Date:** 2026-08-17  
**Task:** Discovery + orchestration layer for any location × platforms × restaurant/dineout/both, scraping via existing venue extractors.  
**Files changed:** `scraper/discovery/*`, `backend/store.py`, `backend/schemas.py`, `backend/main.py`, `backend/services/area_service.py`, Create Catalogue UI, `/areas`, tests/fixtures `discovery_*`. Venue parsers (`swiggy/parser.py`, `swiggy/dineout.py`, `swiggy/scraper.py`, zomato/magicpin parsers) were **not** rewritten.

**What:**
- Location input is free text; parsed into original/normalized/city/state/locality/slug with no city database.
- Adapters: Swiggy / Zomato / Magicpin listing HTML + JSON. Pagination via rel=next, Load More, `?page=`, `data-has-more`. Default max venues is **None (all available)**. Custom limit is optional. Nothing defaults to 10.
- Dedupes by platform+type+venue_id, then canonical URL, then name+location. Same name, different outlet stays two venues.
- Jobs in sqlite `area_jobs`. States for job and venues. Queue → `create_catalog` (existing). Skip/re-scrape/update if catalogue already exists. Cancel + resume (completed stay completed). Concurrency and retries configurable. Blocked is not retried endlessly.
- UI: Create Catalogue mode Single vs Area / City; review list (select/filter/paginate 50); progress; City / Areas nav.

**Why:** Product next stage is area scraping without duplicating venue parsers.

**Tests:** Python **134 passed**. Frontend vitest **122 passed**. `next lint` passed. `tsc --noEmit` had a pre-existing `catalogue-view.test.tsx` spread issue; fixed with `success.categories || []`.  
**Live verification:** **Not done.** No live listing scrape this session. Do not claim a full area is exhausted on a real platform until Chrome actually hits the listing end.

### 2026-08-18 — Discovery location pickers and category cards

**Date:** 2026-08-18  
**Task:** Point area discovery at the real location-picker pages and category surfaces (Magicpin home + Food Delivery / Budget or Fine Dining; Zomato city dine-out / delivery; Swiggy food-offer-near-me vs offers-near-me).  
**Files changed:** `scraper/discovery/urls.py`, `locate.py`, `locate.js`, `runner.py`, `backend/schemas.py`, `area_service.py`, `area-discovery-form.tsx`, `tests/test_discovery.py`, Magicpin home fixture. Venue extractors were not rewritten.

**What:**
- Location input is typed as **city, state** (e.g. Bangalore, Karnataka) so platform location search is unambiguous. Zomato city slug is the city only (`bangalore`).
- Magicpin starts at `https://magicpin.in/`. Discovery follows the homepage card href for **Food Delivery** (restaurant) or **Budget Dining** / **Fine Dining** (dineout; user chooses in the Area form).
- Zomato dineout entry is `https://www.zomato.com/{city}/dine-out`. Restaurant uses `/{city}` and `/{city}/order`.
- Swiggy restaurant uses `https://www.swiggy.com/food-offer-near-me` (Order Online). Dineout uses `https://www.swiggy.com/offers-near-me`.
- `locate.js` is the in-page script that would click `.selectedLocation` / precise location / Zomato header, type the city+state query, then click the category. Listing fetch still uses `SwiggyAccess.load` HTML; category follow is parsed from homepage links in fixtures. **Live typing in Chrome was not verified.**

**Why:** Discovery must use the same location box and category cards as a person on the site, not invented listing URLs.

**Tests:** Python **135 passed**. Frontend vitest **122 passed**.  
**Live verification:** **Not done.** Do not claim Magicpin/Zomato/Swiggy location boxes were typed in a real Chrome session.

### 2026-08-18 — Location search then click suggestion

**Date:** 2026-08-18  
**Task:** Stop inventing city-slug URLs (Zomato `/pandeshwar/order` 404). Type the user’s place into each platform’s location search, click the matching dropdown suggestion, then open the category.  
**Files changed:** `scraper/discovery/locate.js`, `locate.py`, `urls.py`, `collect.py`, `runner.py`, `backend/services/area_service.py`, area form copy, fixtures `discovery_zomato_home.html`, tests. Venue extractors were not rewritten.

**What:**
- Discovery opens the site home / offers pages (`magicpin.in`, `zomato.com`, Swiggy near-me). It does **not** build `zomato.com/{typed-place}/order`.
- The typed value is what the person would type in the header location box (e.g. `pandeshwar mangaluru`). The first suggestion that matches those words is selected (e.g. “Pandeshwar, Mangaluru, India”), not a random page click.
- After the place is set, category cards/tabs are used: Magicpin Food Delivery / Budget or Fine Dining; Zomato Delivery vs Dining Out; Swiggy Order Online vs Dineout.
- Live Chrome listing fetch (`BrowserAccess`) runs `locate.js` via `collect_listing_with_location`. Fixture/Map access still parses HTML only.

**Why:** The location pin (Zomato showing Chhindwara while the URL was a bad slug) only updates when the suggestion is chosen, same as Magicpin Search Location and Swiggy precise location.

**Tests:** Python **135 passed**. Frontend vitest **122 passed**.  
**Live verification:** **Not done.** Do not claim a real Chrome session typed Pandeshwar and the listing loaded.

### 2026-08-18 — Live Magicpin/Swiggy location UI

**Date:** 2026-08-18  
**Task:** Inspect live Magicpin home and Swiggy food-offer-near-me and point locate/discovery at the real controls.  
**Files changed:** `scraper/discovery/locate.js`, `locate.py`, `tests/fixtures/discovery_magicpin_home.html`, `tests/test_discovery.py`. Venue extractors were not rewritten.

**What:**
- **Magicpin (live page):** location is `div.selectedLocation` plus `input.location` (placeholder Search Location). Category cards are `a.discovery-link` with image alts **Food Delivery 9**, **Budget eats**, **Fine Dining** (not inner text). Hrefs are `/category?categoryName=...`. Discovery follows those cards by alt, then still accepts the older text links in fixtures.
- **Swiggy (live page):** header **Setup your precise location** opens an input **Search for area, street name...**. Typing `mangaluru` produced suggestion rows (`style__Location-sc-...`, e.g. Mangaluru International Airport / Karnataka). Order Online vs Dineout tabs go to `food-offer-near-me` and `offers-near-me`.
- Locate script types character-by-character into those fields, then clicks the matching suggestion, then the category card/tab.

**Why:** Fixture text links (`/food-delivery`) do not match the live homepage cards.

**Tests:** Python **135 passed**. Discovery **16 passed**.  
**Live verification:** Swiggy location suggestions were observed in-session after typing Mangaluru. Magicpin Search Location field and category card alts were observed; Magicpin autocomplete dropdown did not appear in this browser session (overlay/click interception), so suggestion-click on Magicpin is **not** claimed as live-verified.

### 2026-08-18 — Platform-specific discovery (Swiggy homepage) + cart UI + videos

**Date:** 2026-08-18  
**Task:** Phase 1 Swiggy city discovery from `https://www.swiggy.com/` (location box → suggestion → Food Delivery or Dineout); Dineout gallery next-arrow cap raised; videos[] field; Magicpin All; catalogue cart drawer/popup.  
**Files changed:** `scraper/discovery/urls.py`, `locate.py`, `locate.js`, `runner.py`, `tests/fixtures/discovery_swiggy_home.html`, `discovery_swiggy_page1.html`, `tests/test_discovery.py`, `scraper/swiggy/scraper.py` (gallery steps), `scraper/swiggy/dineout.py` (`videos[]`), `scraper/swiggy/models.py`, area form, `catalogue-view.tsx`, `dineout-venue-view.tsx`, `catalog-api.ts` timeout 300s, schemas.

**What:**
- Swiggy discovery starts at the **homepage**, not `food-offer-near-me`. After the location suggestion is chosen, listing follow is **FOOD DELIVERY** → `/restaurants` or **DINEOUT** → `/dineout`. Existing venue scrapers are unchanged as the extractors.
- Zomato Dineout starts at `/{city}/dine-out` only when the parsed city is a **single token** (e.g. Mangalore); multi-word places still start at `zomato.com/` so we do not invent `/pandeshwar/order`. Location typing remains in locate.js.
- Magicpin Dineout dining modes: All / Budget / Fine. All follows both category cards.
- Dineout gallery carousel: up to 400 next-arrow steps, stop after two slides with no new photos. `videos[]` from `<video>`/`<source>` URLs; frontend Videos section only when present.
- Cart: **Cart** button opens a right drawer; **Add to Cart** shows a small centered “Added to cart” popup. View details stays a right drawer. Create-catalogue client timeout increased to 300s (Magicpin single-venue timeout screenshot).
- District: not added as a discovery adapter. Zomato collections / District entertainment links remain excluded from venue parse.

**Why:** User screenshots showed Swiggy homepage location autocomplete (Pandeshwar, Mangaluru) then Food Delivery vs Dineout cards; bottom YOUR CART; Magicpin Budget/Fine; Zomato city Dine Out.

**Tests:** Python **136 passed**. Frontend vitest recorded after `npm test`.  
**Live verification:** **Not done** for this homepage discovery path (open swiggy.com → type location → click suggestion → Food Delivery listing → review job). Do not mark city scraping complete.

### 2026-08-18 — Gallery walk + discovery nav-safe collect

**Date:** 2026-08-18  
**Task:** Zomato/Magicpin interactive gallery + videos; Zomato collections/District exclusion; survive Swiggy location navigation during city discovery.  
**Files changed:**
- `scraper/gallery_walk.py` (new)
- `scraper/swiggy/scraper.py`, `scraper/html_common.py`
- `scraper/zomato/parser.py`, `scraper/magicpin/parser.py`, `scraper/discovery/zomato.py`
- `scraper/discovery/collect.py`, `locate.js`, `swiggy.py`
- `tests/test_gallery_walk.py`, `tests/test_discovery.py`, `tests/fixtures/discovery_zomato_dineout.html`
- `frontend/src/components/catalogue-view.test.tsx`, `area-discovery-form.tsx`, `dineout-venue-view.test.tsx`

**What:**
- Swiggy city collect types location, then clicks the category in a **second** evaluate so a full page navigation does not wipe the listing HTML.
- After Food Delivery / Dineout, the listing page is scrolled and `__NEXT_DATA__` / preloaded state is captured when present.
- Zomato/Magicpin venue collect (not `/order` or `/delivery`) opens View Gallery / `+N Photos` and walks next-arrow up to 400 steps. Harvest stays in dialog/gallery context and drops recommended/nearby text.
- `videos[]` parsed for Zomato/Magicpin from `<video>` / `og:video` / video URLs; merge on photos-tab follow. Not mixed into `gallery_images[]`.
- Zomato listing parse skips collections, cuisines, and `district.in` / `/district` links. District is **not** a discovery adapter.
- Magicpin dining All/Budget/Fine is shown whenever Magicpin is selected (restaurant still follows Food Delivery; dineout follows Budget/Fine/All).

**Why:** Live Swiggy evaluate died on navigation (`Execution context was destroyed`). Gallery completeness for Zomato/Magicpin was still photos-tab HTML only. District entertainment must not become venues.

**Tests:** Python **138 passed**. Frontend vitest **124 passed**. `tsc --noEmit` clean. `next lint` only the existing profile `useEffect` warning.

**Live verification:**
- Swiggy: homepage → location (`pandeshwar mangaluru`) → **FOOD DELIVERY** reached `https://www.swiggy.com/restaurants` with listing HTML (one run ~373k, another ~85k). **0 venue URLs parsed** from that HTML (footer `/city/*/best-restaurants` plus JSON `restaurantId` present; card `/city/...-rest` anchors were not recovered by the current adapter). Other runs landed on a 2–3k homepage shell (flaky Chrome). **Not accepted as working city discovery.**
- Zomato city Dine Out live: **not run**.
- Magicpin city live: **not run**.
- Interactive gallery photo counts / videos on live venues: **not run**.

### 2026-08-18 — Swiggy live restaurant URLs from /restaurants

**Date:** 2026-08-18  
**Task:** Phase 1 live Swiggy restaurant city discovery: real venue URLs, no SEO footer, no invented paths.  
**Files changed:**
- `scraper/discovery/urls.py` — restaurant starts at `https://www.swiggy.com/restaurants`; dineout at `/dineout`
- `scraper/discovery/collect.py` — capture `dapi/mapi restaurants/list` XHR; DOM harvest; scroll until card count is stale; skip category click when already on `/restaurants`
- `scraper/discovery/listing_harvest.js` — `a[href*="-rest"]` / dineout / Zomato two-segment venues / Magicpin `/store/`
- `scraper/discovery/swiggy.py` — parse API `info.cta.link` + DOM; reject `best-restaurants`; **do not construct** `/city/city/...` URLs
- `scraper/discovery/models.py`, `base.py`, `queue.py` — `image_url`, `cuisine`; keep `selected`
- `tests/test_discovery.py`, `tests/fixtures/discovery_swiggy_page1.html`
- `frontend/src/lib/area-jobs.ts`, `area-job-view.tsx` — show URL/locality

**Problem:** Live `/restaurants` HTML had `restaurantId` and footer `/city/*/best-restaurants`. Adapter required `<a href="...-restN">...</a>` pairs and invented city slugs. Result: 0 venues.

**Investigation:** Listing cards are driven by `dapi/restaurants/list` JSON (`info.id`, `info.cta.link` like `/city/mangaluru/name-rest210245`). Footer SEO links must never match `-rest\d+`. Attached Chrome (CDP) may already have a location; query `indiranagar` still listed Mangaluru restaurants from that session.

**Solution:** Start on `/restaurants`, set location, capture listing XHR + harvest `-rest` anchors, parse `cta.link` only when it already contains `-rest{id}`. Deduplicate. Scroll until card count stalls (not a hardcoded 10).

**Tests:** Python **139 passed**. Discovery includes API-card vs SEO fixture.

**Live verification:**
- Entry: `https://www.swiggy.com/restaurants`
- Query typed: `indiranagar` (Chrome session still served **Mangaluru** listings — location override not proven)
- Result: **25** restaurant URLs, **0** `best-restaurants`
- Examples: `https://www.swiggy.com/city/mangaluru/pizza-hut-kadri-rest210245`, `.../barbeque-nation-father-mullers-road-kankanady-rest302695`
- Catalogues created this run: **0** (review/scrape not executed)
- Pagination: first listing + scroll until stale; **not** proven to exhaust the whole city
- Zomato / Magicpin live listing: **not run** this pass
- Existing venue scrapers: **unchanged**

### 2026-08-18 — Swiggy location verification (e2e not completed)

**Date:** 2026-08-18  
**Task:** Force Swiggy `/restaurants` location selection, refuse discovery on mismatch, then one live catalogue.  
**Files changed:** `scraper/discovery/locate.py`, `locate.js`, `collect.py`, `runner.py`, `backend/services/area_service.py`, `tests/test_discovery.py`, `AGENT.md`

**WHAT WAS BROKEN:** The previous 25-URL run reused the attached Chrome tab. Swiggy stayed on Mangaluru. Typing `indiranagar` did not change the listing. A later dump of `/restaurants` showed the header location label as **Other** (not “Setup your precise location”), so the old location click selectors never opened the picker.

**WHAT WAS FIXED (code):**
- Discovery opens a **new tab** instead of the existing located tab.
- Location control click includes header labels such as **Other**, then clear/type/suggestion click (geographic rows preferred).
- After selection, requested vs selected text is checked (`location_is_consistent`). Mismatch returns `Location selection failed` and **does not** parse restaurants. Area jobs store that error as `failed`.
- Listing XHR is attached **after** location verification.
- Pagination fields logged: `initial_cards`, `final_cards`, `listing_xhr_total`, `exhausted`.

**LISTING SOURCE:** Unchanged — Swiggy listing XHR (`dapi/mapi restaurants/list`) plus `-rest` harvest. SEO `best-restaurants` still rejected.

**LIVE TEST (this session):**
- Requested: `Indiranagar, Bengaluru, Karnataka`
- Selected: **not captured**
- Diagnostic (before CDP broke): page body showed header **Other**; click on Other succeeded.
- End-to-end discovery/catalogue: **failed** — `ChromeUnavailableError` waiting for CDP at `http://127.0.0.1:9223` (timeout). Overlapping Chrome launches from earlier dumps likely held the debug port.
- Venues this run: **0**
- Catalogue created: **0**
- Pagination: **not measured** (did not reach listing)

**LIMITATIONS:** Swiggy city scraping is **not** live-complete. Location verification is implemented and fixture-tested; the full LOCATION → XHR → URL → `create_catalog` → saved catalogue chain did not run because Chrome debugging did not come up.

### 2026-08-18 — Swiggy Indiranagar live chain succeeded (one listing page)

**Date:** 2026-08-18  
**Task:** Re-test live Swiggy restaurant Area/City: verified location → listing URLs → one existing `create_catalog`.  
**Files changed:** `scraper/discovery/locate.py`, `collect.py`, `listing_harvest.js`, `tests/test_discovery.py`, `AGENT.md`

**WHAT WAS BROKEN:**
- Header already showed `Other` + `Indiranagar, Bengaluru, Karnataka, India`. Location reader looked for `LocationContent` and treated the first line as the location, so selected was empty and discovery stopped.
- Listing XHR listener was attached **after** location, so the restaurants/list response from the initial `/restaurants` load was missed (`listing_xhr_total: 0`).
- Card counts used `a[href*="-rest"]`, which matched footer **`best-restaurants`**, not real `-rest{id}` cards. Serialized HTML had no `/city/...-rest` anchors.

**WHAT WAS FIXED:**
- Parse the address line under the header chip (`parse_swiggy_header_location`). If it already matches the request, do not reopen the picker.
- Attach listing XHR capture **before** `goto`. If the picker must run, clear earlier payloads and wait for a new list response.
- Count/wait for `-rest` + digits, excluding `best-restaurants`. Do not treat a `/dineout` homepage link as a venue.

**LISTING SOURCE:** Unchanged — Swiggy `dapi/mapi restaurants/list` XHR; `cta.link` only when it already contains `-rest{id}`. SEO `best-restaurants` rejected. Existing Swiggy restaurant scraper unchanged.

**LIVE TEST (this session):**
- Requested: `Indiranagar, Bengaluru, Karnataka`
- Selected: `Indiranagar, Bengaluru, Karnataka, India` (verified)
- Venues: **24**, SEO **0**
- Example: `https://www.swiggy.com/city/bangalore/pizza-hut-indiranagar-rest10584` (Pizza Hut, Indiranagar)
- `create_catalog`: `extraction_status=ok`, 135 items, 22 categories, outlet Indiranagar, Bangalore address
- Saved catalogue: `96207766-9ef9-470c-8ab1-80df1dec2823` — open `/catalogues/96207766-9ef9-470c-8ab1-80df1dec2823`
- Pagination: `listing_xhr_total: 1`, `exhausted: False` (cards are not listing `<a -rest>` anchors; one XHR page is **not** whole-city exhaustion)

**LIMITATIONS:** Entire-city pagination still unproven. Zomato/Magicpin city jobs not run.

### 2026-08-18 — Swiggy listing pagination to API exhaustion

**Date:** 2026-08-18  
**Task:** Finish Swiggy restaurant city discovery pagination / exhaustion without changing working location selection, URL extraction, or the restaurant scraper.  
**Files changed:** `scraper/discovery/listing_update.py` (new), `scraper/discovery/collect.py`, `tests/test_discovery.py`, `AGENT.md`

**PAGINATION MECHANISM (captured live, not guessed):**
- First page: `GET /dapi/restaurants/list/v5?lat=&lng=&is-seo-homepage-enabled=true&page_type=DESKTOP_WEB_LISTING`
- Response `data.pageOffset.nextOffset` + `data.pageOffset.widgetOffset` (including `collectionV5RestaurantListWidget_SimRestoRelevance_food_seo`)
- Swiggy web bundle (`app.*.js`) defines `LISTING_UPDATE: "restaurants/list/update"`; `listing.*.js` calls `updateListing({nextOffset, widgetOffset, filters})` **only when `nextOffset` is truthy**
- Next batches: in-page `POST /dapi/restaurants/list/update` with `lat`, `lng`, `nextOffset`, `widgetOffset`, `filters`, `page_type`, `_csrf` (csrf from the previous listing JSON; not logged)
- `nextOffset` can stay the same while `widgetOffset` advances; stopping on repeated `nextOffset` alone was a false exhaustion (2 batches / 38 unique)
- Exhaustion: **`pageOffset.nextOffset` missing/empty** (same condition as Swiggy’s client). Unchanged `(nextOffset, widgetOffset)` is a stuck-loop stop.

**LIVE TEST (Indiranagar, after location verify):**
- Requested: `Indiranagar, Bengaluru, Karnataka`
- Selected: `Indiranagar, Bengaluru, Karnataka, India`
- Batches: **197** (1 GET + 196 POST update)
- Batch sizes: first **24**, then typically **15** restaurants until the last pages
- Raw URLs: **2937**
- Valid `-rest` URLs (SEO 0): **2937**
- Duplicates removed: **788**
- Final unique: **2149**
- `exhausted=true`, reason `missing nextOffset`
- Additional venue from batch 2 (not the earlier Pizza Hut): Domino's Pizza `https://www.swiggy.com/city/bangalore/dominos-pizza-2nd-stage-indiranagar-rest23802` — `extraction_status=ok`, 263 items, 29 categories, outlet 2nd stage Indiranagar
- Catalogue: `08bd0521-290b-4870-8d9f-e20d2c71bfee` — `/catalogues/08bd0521-290b-4870-8d9f-e20d2c71bfee`
- Prior Pizza Hut catalogue still valid: `96207766-9ef9-470c-8ab1-80df1dec2823`

**Tests:** Python **144 passed**. Frontend tests not run (UI unchanged).

**LIMITATIONS:** Swiggy’s `/restaurants` list is a lat/lng delivery feed, not a locality-locked directory. Later batches include other Bangalore areas (e.g. Koramangala, Kammanahalli) because that is what `list/update` returned. Header chip **Other** plus the Indiranagar address is the verified selected location; the picker is not reopened when that address already matches. Zomato/Magicpin city pagination not run.

### 2026-08-18 — Swiggy discovery_scope: delivery feed vs physical outlet

**Date:** 2026-08-18  
**Task:** Represent Swiggy `/restaurants` as a lat/lng delivery feed; classify listing locality without scraping 2149 catalogues. Pagination and the restaurant scraper were not changed.  
**Files changed:** `scraper/discovery/scope.py` (new), `models.py`, `runner.py`, `queue.py`, `backend/services/area_service.py`, `frontend/src/lib/area-jobs.ts`, `area-job-view.tsx`, tests, `AGENT.md`

**WHAT 2149 MEANS:** That count is **restaurants that deliver to the Indiranagar pin**, not “2149 restaurants physically in Indiranagar.”

**METADATA (live listing `info` objects):** Every listing card had `locality` and `areaName`. None had `address`, `lat`, `lng`, `slat`, or `slng`. `sla` is delivery ETA/distance, not outlet coordinates. Same `locality`/`areaName` fields the venue scraper uses for outlet — cheap enough; full scraper not required for this classification.

**SCOPE MODEL:**
- Job/venue `discovery_scope=delivery_to_location` for Swiggy restaurant listings
- `location_match`: `located_here` (listing locality/address contains the requested area token), `delivers_here` (has a different locality), `unknown` (no locality)
- City requests: listing locality containing the city, or `/city/{slug}/` matching the requested city (bengaluru↔bangalore)
- Area requests: listing locality/address only — URL slug and restaurant name are not used (avoids false Indiranagar labels)
- B (delivers here) is kept, not discarded

**LIVE CLASSIFICATION (Indiranagar, Bengaluru, Karnataka):**
- Delivery-feed venues this run: **1977** unique (`discovery_scope=delivery_to_location`)
- Located here: **441** (example: Pizza Hut | Indiranagar)
- Delivers here: **1536** (example: Burger King | CMH Road — Swiggy’s locality string, not a geofence)
- Unknown: **0**
- Pagination this run ended `update request failed` at 132 batches; the earlier complete exhaustion was **2149** unique. Do not treat 1977 as a replacement for that exhaustion proof.
- No catalogues scraped for classification

**UI:** Review header: delivery-feed disclaimer + Located here / Delivers here / Location unknown counts and filter. Full scrape still happens only for selected venues.

**Tests:** Python **145 passed**. Frontend area-job tests after UI change.

**LIMITATIONS:** Locality is Swiggy’s card string (e.g. “CMH Road” is not mapped to Indiranagar). No polygon/lat filter. City/area discovery is **not** fully complete as a physical directory. Zomato/Magicpin unchanged.

### 2026-08-18 — LocationResolver (canonical place vs platform slug)

**Date:** 2026-08-18  
**Task:** Resolve arbitrary Indian locations before discovery. No hardcoded city list. No `mangalore → puttur` URL rewrite. Swiggy list/v5 + list/update pagination unchanged.  
**Files changed:** `scraper/discovery/resolver.py`, `place_meta.py`, `location.py`, `models.py`, `runner.py`, `urls.py`, `queue.py`, `collect.py` (coordinate distance check only), `backend/services/area_service.py`, UI location line, `tests/test_location_resolver.py`, `tests/fixtures/discovery_zomato_jsonld.html`, `AGENT.md`

**ARCHITECTURE:**
USER QUERY → LocationResolver (Nominatim by default, pluggable Geocoder) → cache → canonical city/area/state/country/lat/lng/confidence → each platform adapter → select/verify → cheap discovery → location_match → user review → full scrape selected only.

**CANONICAL VS PLATFORM SLUG:** Internal city stays `Bengaluru`. Zomato dine-out URL is used only after `platform_places.zomato.slug` is set from that platform (e.g. canonical link `zomato.com/bangalore`). `search_urls` no longer slugifies the display city into a Zomato path.

**SWIGGY:** Resolver supplies expected lat/lng. Chrome still fires the existing `GET /dapi/restaurants/list/v5` and `POST .../update`. If the listing pin is >75 km from resolved coordinates, discovery stops (stale browser city). Pagination/exhaustion code not rewritten.

**ZOMATO:** Cheap JSON-LD + BreadcrumbList extract (`extract_zomato_place`) for locality/region/geo. District remains a separate `sub_source` (not mixed into restaurant/dineout parsers). Live Zomato city-page discovery was not claimed this pass.

**MAGICPIN:** Receives the same LocationQuery; slug inferred from Magicpin URLs when HTML/canonical is present, not from a hardcoded city table.

**LIVE GEOCODE (Nominatim, India):**
- `Puttur, Karnataka` → city Puttur, state Karnataka, country India, lat 12.7632858, lng 75.2018421, high
- `Indiranagar, Bengaluru, Karnataka` → area Indiranagar, city Bengaluru, state Karnataka, lat 12.9732913, lng 77.6404672, medium
- `Bengaluru, Karnataka` → Bengaluru, Karnataka, lat 12.9767936, lng 77.590082, high
- `Mangalore, Karnataka` → **Mangaluru**, Karnataka (OSM canonical name), lat 12.8698101, lng 74.8430082, high

**NOT LIVE THIS PASS:** Full Swiggy Puttur listing pagination, Zomato/Magicpin platform slug verification on live sites, District crawl.

**Tests:** Python **154 passed**. Pagination tests still pass.

### 2026-08-18 — Universal LocationResolver, KM split, URL slots, District stub

**Date:** 2026-08-18  
**Task:** Central LocationProvider (Google if keyed, else Nominatim/Mapbox), platform location bind, never treat KM as place, host-based URL fields, Zomato District as a separate unverified source. Swiggy `list/v5` + `list/update` pagination and the full restaurant scraper were not rewritten.

**LIVE THIS PASS:** No new live listing runs. Prior Indiranagar Swiggy exhaustion (**197 / 2937 / 788 / 2149**) still stands as a delivery feed. Prior Nominatim geocodes for Puttur / Indiranagar / Bengaluru / Mangaluru still stand. Zomato District, Magicpin, and Puttur listing verification are **not** claimed.

**Tests:** Python **160 passed**. Frontend identity/area tests: **15 passed**.

### 2026-08-18 — Platform header location selector automation

**Date:** 2026-08-18  
**Task:** Drive each platform’s real header location control from the shared LocationResolver. Swiggy pagination and restaurant scraper unchanged. LocationResolver not rewritten.

**LIVE THIS PASS:** Playwright `verify_only` against live sites (Chrome CDP port 9222 was not open):
- Canonical Nominatim: Puttur, Karnataka, India, 12.7632858, 75.2018421
- Swiggy: **location_verified=false** — header reader/picker did not land on Puttur (isolated Playwright is not the prior Chrome profile session). Discovery **stopped**; restaurants were not scraped from a stale/wrong place.
- Zomato: **not verified** — `net::ERR_HTTP2_PROTOCOL_ERROR` on `https://www.zomato.com/`
- Magicpin: **location_verified=false** — suggestion matching would have accepted a Karnataka-only restaurant name; city-token filter + fail-closed **stopped** discovery.
Do not claim Swiggy/Zomato/Magicpin header selection is live-complete in Playwright. Prior Chrome-CDP Indiranagar Swiggy header verify still stands from earlier sessions.

**Tests:** Python **161 passed**.

### 2026-08-18 — JP Nagar location hardening

**Date:** 2026-08-18  
**Task:** Safer suggestion matching and header landmarks; live-test **JP Nagar, Bengaluru, Karnataka**. Pagination and restaurant scraper unchanged.

**CANONICAL LIVE:** JP Nagar / Bengaluru / Karnataka / India, 12.9096941, 77.5866067. City-only Bengaluru, Karnataka also resolved.

**LIVE SELECT:** Swiggy selected Ashok Nagar (fail-closed). Zomato HTTP2 error. Magicpin Arya Nagar, New Delhi (fail-closed). **NOT LIVE VERIFIED** for JP Nagar on any platform. Discovery did not start.

**Tests:** Python **163 passed**.

### 2026-08-18 — Human website location typing (type_query)

**Date:** 2026-08-18  
**Task:** Type the area into the real header location control (not invent URLs). Test location JP Nagar, Bengaluru, Karnataka. Swiggy pagination and venue scrapers unchanged.

**CODE:** `type_query` vs `picker_query`; `collect_listing_with_location(..., type_text=)`; logo-adjacent click (Other / Detect-my-location no longer first); sequential typing; `locate.js` `opts.type`. Area job passes `args["type"]`. Magicpin Budget/Fine/All already in the Area UI.

**LIVE:** Chrome CDP **9222 closed**. Isolated Playwright Swiggy home **HTTP response code failure**. JP Nagar was **not** selected on Swiggy, Zomato, or Magicpin. No venue URLs discovered this pass. **NOT LIVE VERIFIED.**

**Tests:** Python **163 passed**. Pagination tests still pass.

### 2026-08-18 — Zomato listing base (not homepage)

**Date:** 2026-08-18  
**Task:** Zomato-only. Discovery opens `https://www.zomato.com/mangalore/restaurants`, not `https://www.zomato.com/`. Location is still selected on the website (header control). Do not string-replace mangalore. Swiggy/Magicpin entry URLs unchanged. Venue scrapers unchanged.

**LIVE:** This URL was not fetched this pass (per instruction). JP Nagar Zomato selection remains **NOT LIVE VERIFIED**.

**Tests:** Python **163 passed**.

### 2026-08-18 — Human location flow; PHASE 1 Swiggy live

**Date:** 2026-08-18  
**Task:** Human click/type/select/verify on real sites. No city URL rewrite. Zomato always starts at `/mangalore/restaurants`. Magicpin starts at `/india/Bangalore/home/`. Swiggy pagination and venue scrapers unchanged.

**ENTRY:** Swiggy `/restaurants`. Zomato `/mangalore/restaurants` (not homepage, not invented dine-out URLs). Magicpin `/india/Bangalore/home/`. Dineout/restaurant mode is chosen after location verify.

**SWIGGY CONTROL (live Chrome):** Header chip `Other` + `Indiranagar, Bengaluru, Karnataka, India` beside the logo (before Swiggy Corporate). Location input placeholder: `Search for area, street name..`. Suggestions are **not** `[role=option]`; live text was `J. P. Nagar Bengaluru, Karnataka, India` on unmarked divs. Ranker now treats `JP Nagar` ≡ `J. P. Nagar`.

**FIXTURE:** Python **163 passed**. Pagination tests still green.

**LIVE PHASE 1 Swiggy Restaurant (JP Nagar):** Chrome opened `https://www.swiggy.com/restaurants`. Stale header **Indiranagar**. Fail-closed **STOP**. Discovery did **not** start. A later retry could not attach Chrome (`9223` timeout). **LIVE: FAIL** (location not replaced).

**LIVE PHASE 2–7:** Not started (one platform at a time). Swiggy Dineout, Zomato, Magicpin, District **NOT LIVE VERIFIED**.

**AI fallback:** not used.

### 2026-08-18 — Location selection hardening + Chrome lifecycle

**Date:** 2026-08-18  
**Task:** Click the first exact/top-level location (J. P. Nagar + Bengaluru), not phases. Stop launching extra Chrome processes. Pagination and venue scrapers unchanged. No city URL rewrite.

**SUGGESTIONS:** `choose_location_suggestion` walks visual order and clicks the first top-level match (`JP Nagar` ≡ `J. P. Nagar`, Bengaluru ≡ Bangalore). Phases, roads, restaurants, and other cities are rejected unless requested. Shared by Swiggy Playwright click, Zomato/Magicpin header flow, and `locate.js`.

**BROWSER:** If CDP is already ready on the preferred port, attach — do not hop to 9223/9224. `browser_job()` keeps one managed Chrome for a whole discovery job; retries reuse it. Owned process is stopped when the job ends. Attached user Chrome (`chrome-cdp`) is never killed. Created listing pages are closed.

**FIXTURE:** Python **167 passed**.

**LIVE:** Not re-run in this pass after the ranking/lifecycle fix. Prior PHASE 1: Indiranagar not replaced. **JP Nagar LIVE: NOT VERIFIED.**

### 2026-08-18 — Failed-job delete; permanent catalogue delete; JP Nagar diagnostic (no listing rewrite)

**Date:** 2026-08-18  
**Task:** Diagnose JP Nagar 0 venues without changing Swiggy pagination/parser. Make failed discovery jobs removable. Confirm catalogue delete semantics.

**DELETION (verified in tests + SQLite schema):**
- `area_jobs` and `catalogues` are separate tables. There is no FK from catalogues to area jobs.
- `DELETE /area-jobs/{id}` permanently deletes the `area_jobs` row (job status, discovery venue JSON, failed-job error). It does **not** delete rows in `catalogues`.
- `DELETE /catalogues/{id}` is a hard SQLite `DELETE FROM catalogues` (no `deleted_at`). After a successful row delete, owned files under `data/catalogue-assets/{catalogue_id}/` are removed. Other catalogues and unrelated jobs are left intact.
- City / Areas shows **Failed** + **Delete** on failed jobs. Confirmation: “Delete this discovery job permanently?” Catalogue UI: “Delete this catalogue permanently? … cannot be undone.”

**JP NAGAR (this pass):** Swiggy pagination and restaurant scraper were **not** modified. Live `/dapi/restaurants/list/v5` capture was **not** obtained this pass (no listing HTTP dump in stored jobs). Local `data/catalogues.sqlite` failed Swiggy job `J. P. Nagar Bengaluru, Karnataka, India` stopped at **LocationResolver** (`No location in India matched this query`) — listing never ran. Magicpin `J P nagar` stopped at **AmbiguousLocationError**. Do **not** treat header-correct + 0 venues as diagnosed to a listing/parser failure until a live listing dump exists.

**Tests:** Python **171 passed**. Frontend **129 passed**.

### 2026-08-21 — Baseline grading correctness (not Phase 6)

**Date:** 2026-08-21  
**Task:** Audit catalogue + grading output vs `grading.v1`. Do not start Phase 6.

**ROOT CAUSE:** NLP stage score multiplied an already 0–100 `_length_score` mean by 100 again (`~3829`). `combine_scores` then weighted that illegal input and clamped the sum to 100, so overall letter A hid Deterministic C and Images F. `image_invalid` (145) was AVIF (`ftypavif`) stored under `.jpg`/`.img`; the vision decoder only understood PNG/JPEG/GIF/WebP. Asset fetch `Accept` already requested AVIF.

**FIX (implementation bugs, `ENGINE_VERSION` remains `grading.v1`):** NLP mean is 0–100; combine clamps each stage before weights; AVIF `ispe` dimensions; COMPLETED rows with stage scores outside 0–100 are not treated as valid `grading.v1` results (GET 404; POST re-grade purges and recomputes). Phase 5 still copies overall from the grade row and 502s out-of-range section scores. No new formula, no generated images/descriptions, no Phase 6.

### 2026-08-21 — Phase 6 V1 AI Improvement Engine implemented (NOT CLOSED)

**Date:** 2026-08-21  
**Task:** Approved Phase 6 V1: consume Phase 5 findings, generate preview-only description/category-name proposals via untrusted local Ollama (`llama3:latest`) plus mandatory backend validation.

**Why:** Founder-approved V1 decision package. Catalogue payload, `grading.v1`, Baba Score, and Phase 5 explanation semantics are unchanged.

**Remaining:** Phase 6 is **not** CLOSED. Apply/approval and actual image/video generation remain later phases.

### 2026-08-21 — Phase 6 remaining V1 gaps implemented (NOT CLOSED)

**Date:** 2026-08-21  
**Task:** Tags (`labels[]`), vision media handoff, kinds registry, trusted `original_price` copy, keep category-name-only menu structure.  
**Why:** Official Phase 6 audit required remaining content kinds plus Phase 7 handoff, without apply or generation.  
**Remaining:** Phase 6 is **not** CLOSED. Awaiting closure review. No `PHASE6_CLOSURE.md` update in this pass. pytest 398 / Vitest 148.

### 2026-08-21 — Phase 6 AI Improvements UI separated from Grade

**Date:** 2026-08-21  
**Task:** Dedicated `/catalogues/{id}/improvements` page; Grade keeps findings + Improve with AI navigation; no backend/contract changes.  
**Why:** Grade measures quality; AI Improvements is the proposed-change preview workflow.  
**Remaining:** Phase 6 backend remains CLOSED. No apply/approval/re-grade.

### 2026-08-21 — TypeScript baseline: progress.test location fixture

**Date:** 2026-08-21  
**Task:** Align `progress.test.ts` AreaJob `location` with `original`/`normalized` (not obsolete `query`).  
**Why:** Clean `tsc --noEmit` before Phase 7. Production `AreaJob` type was already correct.  
**Remaining:** Do not start Phase 7 here.

## 19. Current Task

**CURRENT PHASE:** Phase 9 — Baba AI Catalogue Assistant — IMPLEMENTED (awaiting closure review).

**NEXT PHASE:** Do not start Phase 10, 11, 12, or 13 without official approval.

**CURRENTLY WORKING ON:** Phase 9 implemented. Stop for review.

**COMPLETED:** Phase 0 foundation guarantees. Canonical catalogue Phase 1 (`PHASE1_CLOSURE.md`). Catalogue ingestion & normalization Phase 2 (`PHASE2_CLOSURE.md`). Baba grading engine Phase 3 (`PHASE3_CLOSURE.md`). Baba Score + platform evaluation Phase 4 (`PHASE4_CLOSURE.md`). Grade explanation & recommendations Phase 5 (`PHASE5_CLOSURE.md`). AI Improvement Engine Phase 6 (`PHASE6_CLOSURE.md`). Phase 7 generated media is implemented as a preview-only baseline. Customer review intelligence Phase 8 (`PHASE8_CLOSURE.md`). Baba AI Catalogue Assistant Phase 9 (this session; not CLOSED).

**KNOWN LIMITATIONS (Phase 8 — closed, not automatic later-phase work):** guest/anonymous diner submit is out of V1 (authenticated catalogue-authorized session only); no fuzzy/semantic item match; first-write-wins (no review body updates); recurrence uses the stored set with threshold 2 (no calendar window); lexicon aspect/polarity can miss slang; photos are evidence only.

**KNOWN LIMITATIONS (Phase 6 — not automatic later-phase work):** no apply/approval; no LLM-invented prices or item names; no menu move/order (no safe source+target finding); no image/video generation; video handoff unused because Phase 5 has no video finding.

**KNOWN LIMITATIONS (Phase 5 — not automatic later-phase work):** listed in `PHASE5_CLOSURE.md`. Static Python type checkers were not installed. Frontend `tsc`/`lint` still fail on pre-existing files.

**KNOWN LIMITATIONS (Phase 4 — not automatic later-phase work):** listed in `PHASE4_CLOSURE.md`. Calibration is deferred. No live platform HTTP. No evaluation UI.

**KNOWN LIMITATIONS (Phase 3 — not automatic later-phase work):** listed in `PHASE3_CLOSURE.md`. `grading.v1` is the approved formula; do not change it in place.

**KNOWN LIMITATIONS (canonical Phase 1 — not automatic later-phase work):** listed in `PHASE1_CLOSURE.md`. Discovery items below are separate from that closed phase.

**KNOWN LIMITATIONS (Phase 2 — not automatic later-phase work):** listed in `PHASE2_CLOSURE.md` (including durable pending raw files with no janitor; extra-tab fetches are not separate raw files).

**KNOWN LIMITATIONS (discovery / live, unchanged by Phase 1 closure):**
- JP Nagar live listing (venues from `list/v5`) **NOT VERIFIED** in the earlier discovery pass.
- District location UI not mapped. AI click fallback not wired.
- Leftover Chrome from older hops is not auto-killed if it was not started in this job.
- Google Places Autocomplete not live (no API key).

**COMPLETED:** Failed discovery-job delete API/UI; permanent catalogue row + owned-asset delete; confirmation copy split for jobs vs catalogues.

**NEXT:** Capture live Swiggy location-commit + `list/v5` for JP Nagar vs Indiranagar. Do not change pagination until that dump exists.

**KNOWN LIMITATIONS:**
- JP Nagar live listing (venues from `list/v5`) **NOT VERIFIED** this pass.
- JP Nagar live header change was reported by the user; this pass did not re-capture Swiggy network.
- District location UI not mapped. AI click fallback not wired.
- Leftover Chrome from older hops is not auto-killed if it was not started in this job.
- Google Places Autocomplete not live (no API key).

## 20. AGENT.md UPDATE RULE

After every meaningful change: update status, limitations, failed approaches if needed, changelog, test counts, live verification. Correct stale statements. Do not append contradictions.

## 21. AGENT.md MUST REFLECT REALITY

Never write “working” for fixture-only work. Never invent test results or live verification.

## 22. FIRST AGENT.md ENTRY

This document was created on 2026-08-17 from repository inspection plus the in-progress Zomato/Magicpin task. Implementation details below this line in later changelog entries supersede the pre-fix snapshot where they conflict.
