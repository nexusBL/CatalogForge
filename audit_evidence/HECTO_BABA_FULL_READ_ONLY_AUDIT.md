# Hecto Baba — Full Read-Only Product + Codebase Audit

**Date:** 27 August 2026  
**Repository:** CatalogForge / Hecto Baba  
**Method:** Source inspection only (routes, services, schemas, tests, phase docs). No runtime browser/Ollama/SMTP verification in this pass.  
**Rule:** No application code was modified to produce this document.

---

## Safety checklist (final)

- [x] No application source code changed
- [x] No frontend/backend code changed
- [x] No database, API, config, or dependency changes
- [x] No feature implemented or removed
- [x] Catalogue Management only investigated (not built)
- [x] Add/Edit/Remove product, price, category — investigated only
- [x] Email OTP verified from `auth/auth.ts`
- [x] Image capabilities verified from `backend/media/providers.py`
- [x] Scraping pipeline verified from `catalog_service.py` + `scraper/`
- [x] AI architecture verified from feature folders
- [x] Feature → code, API, DB, test mappings included
- [x] Missing features separated from implemented features

---

# PART 1 — Actual product journey

Verified user flow from `frontend/src/app/**/page.tsx`, `navigation.tsx`, and `backend/main.py`:

```
LOGIN (/) or SIGNUP (/signup)
  → Better Auth session (cookie)
  → AuthGate + OrganizationGate (dashboard layout)
OVERVIEW (/overview)
  → Compact catalogue list
CREATE CATALOGUE (/catalogues/new, platform-specific create links)
  → Single venue: URL + FSSAI + platform + type
  → POST /catalog/create → scrape → parse → normalize → save
  OR Area jobs (/areas, /areas/[id])
  → POST /area-jobs → start → scrape-batch
CATALOGUE VIEW (/catalogues/[id]) — read-only menu browser
  ├── Grade / AI Improvements (/catalogues/[id]/improvements)
  │     → proposals → owner Apply/Cancel → history
  ├── Generated Media (/catalogues/[id]/media)
  │     → media job → preview → Apply/revert
  ├── Reviews (/catalogues/[id]/reviews)
  │     → customer feedback + review intelligence (inspect only)
  └── Assistant (/catalogues/[id]/assistant) + org Baba AI (/baba-ai)
        → read-only tools OR chat mutation Propose → Confirm
GRADING (/grading, /grading/[id])
SETTINGS (/settings), PROFILE (/profile)
RESTAURANT / DINEOUT landing (/restaurant, /dineout)
```

**Not present:** `/catalogues/[id]/manage` or any “Manage Catalogue” sidebar entry.

---

# PART 2 — Catalogue management (future vs existing)

## Summary table

| Capability | Status | Primary path |
|------------|--------|--------------|
| Add product | PARTIALLY IMPLEMENTED | Phase 10 `add_item` via Baba AI chat + confirm |
| Edit product name | PARTIALLY IMPLEMENTED | `rename_item` mutation |
| Remove product | PARTIALLY IMPLEMENTED | `remove_item` mutation |
| Change price (manual) | PARTIALLY IMPLEMENTED | `change_price` mutation OR improvement `item_price` (copy only) |
| Change description | PARTIALLY IMPLEMENTED | Improvement apply OR `update_description` mutation |
| Change tags | PARTIALLY IMPLEMENTED | Improvement `labels` apply OR `update_labels` mutation |
| Change image | PARTIALLY IMPLEMENTED | Media job apply only |
| Move between categories | PARTIALLY IMPLEMENTED | `move_item` mutation |
| Rename category | PARTIALLY IMPLEMENTED | Improvement `category_name` apply |
| Add category | NOT IMPLEMENTED | No op in mutation contract |
| Remove category | NOT IMPLEMENTED | — |
| Reorder categories/items | NOT IMPLEMENTED | No reorder in backend |
| Change availability | NOT IMPLEMENTED | Scraped/display only; no mutation |
| Direct REST item CRUD | NOT IMPLEMENTED | No PUT/PATCH in `main.py` |
| Manage Catalogue UI | NOT IMPLEMENTED | Nav has Create + Catalogues only |
| Price change history / actor | PARTIALLY IMPLEMENTED | `catalogue_edit_history` records `actor=user_id`, `previous_value`, `new_value` on apply paths |

---

## Per-capability evidence

### Add product

- **Status:** PARTIALLY IMPLEMENTED
- **Frontend:** No form. Baba AI / assistant chat only (`baba-assistant-view.tsx`, `baba-mutation-confirm.tsx`)
- **API:** `POST /catalogues/{id}/assistant/turn` → `POST .../assistant/mutations/{id}/confirm`
- **Backend:** `backend/mutation/service.py`, `parse.py`, `patch.py` (`add_item` op)
- **Database:** `catalogues.payload` JSON; `catalogue_mutation_proposals`; `catalogue_edit_history`
- **Tests:** `tests/test_phase10_mutation.py`
- **Explanation:** Owner must phrase add intent in chat; system proposes patch; owner confirms with token. No sidebar “Add product” screen.

### Edit product price

- **Status:** PARTIALLY IMPLEMENTED
- **Frontend:** No price editor. Chat mutation OR improvement proposal Apply on improvements page
- **API (chat):** `POST .../assistant/mutations/{id}/confirm` with `change_price`
- **API (AI):** `POST .../improvements/{id}/apply` for `item_price` kind (copies trusted `original_price`, never invents)
- **Backend:** `backend/mutation/patch.py`, `backend/improvement/apply.py`
- **History:** `backend/history/service.py` → `record_change()` with `actor=user_id`, `previous_value`, `new_value`
- **Tests:** `tests/test_phase10_mutation.py`, `tests/test_phase11_improvement.py`
- **Explanation:** Manual price via chat only. AI price path only copies scraped `original_price`. History records who changed it when apply succeeds.

### Change availability

- **Status:** NOT IMPLEMENTED (display only)
- **Frontend:** `catalogue-view.tsx` + `catalogue-menu.ts` (`isItemAvailable`, `nextAvailableLabel`)
- **Scrape:** `scraper/swiggy/parser.py` `_item_availability()` stores availability in payload
- **Mutation:** None
- **Explanation:** Availability is ingested and displayed; owners cannot edit it.

### Manage Catalogue (product area)

- **Status:** NOT IMPLEMENTED
- **Nav evidence:** `navigation.tsx` lines 224–235 — “Catalogue” section has Create Catalogue + Catalogues only
- **Explanation:** All catalogue content changes require improvement apply, media apply, chat mutation confirm, or rollback — not a dedicated management workspace.

---

# PART 3 — Complete feature inventory

## Authentication

| Feature | Status | Evidence |
|---------|--------|----------|
| Username/password login | IMPLEMENTED & VERIFIED | `login-form.tsx`, `auth/auth.ts` `emailAndPassword` |
| Sign up (username required) | IMPLEMENTED & VERIFIED | `signup/page.tsx`, auth hook on `/sign-up/email` |
| Session cookies | IMPLEMENTED & VERIFIED | Better Auth; `backend/session.py` `require_session()` |
| Organization gate | IMPLEMENTED & VERIFIED | `organization-gate.tsx`, org on all catalogue APIs |
| Protected routes | IMPLEMENTED & VERIFIED | `AuthGate` in dashboard layout; 401 without session |
| Email OTP | **IMPLEMENTED — NOT WORKING** | `sendOtpEmail()` throws without `SMTP_HOST` or `AUTH_OTP_LOG=true` |

## Catalogue

| Feature | Status |
|---------|--------|
| Create single venue | IMPLEMENTED — NEEDS VALIDATION |
| Restaurant / Dineout / Both types | IMPLEMENTED & VERIFIED |
| Read-only catalogue display | IMPLEMENTED & VERIFIED |
| Delete catalogue | IMPLEMENTED & VERIFIED |
| Direct catalogue editing UI | NOT IMPLEMENTED |
| Area/city batch jobs | IMPLEMENTED — NEEDS VALIDATION |

## Scraping

| Feature | Status |
|---------|--------|
| Swiggy / Zomato / Magicpin parsers | IMPLEMENTED & VERIFIED (fixtures) |
| Chrome CDP browser collect | IMPLEMENTED — NEEDS VALIDATION (live) |
| Normalize + validate + canonical | IMPLEMENTED & VERIFIED |
| WAF/blocked handling | IMPLEMENTED & VERIFIED |
| Partial extraction status | PARTIALLY IMPLEMENTED (schema/UI only; parsers don't emit) |
| Image materialization | IMPLEMENTED & VERIFIED |

## AI / Grading

| Feature | Status |
|---------|--------|
| Baba grading (`grading.v1`) | IMPLEMENTED & VERIFIED |
| Grade explanation | IMPLEMENTED & VERIFIED |
| Baba Score | IMPLEMENTED & VERIFIED |
| Platform evaluation | IMPLEMENTED & VERIFIED |
| Improvement proposals (5 kinds) | IMPLEMENTED — NEEDS VALIDATION (Ollama) |
| Apply/cancel improvements | IMPLEMENTED & VERIFIED |
| Baba AI assistant | IMPLEMENTED & VERIFIED |
| Typed chat mutations | IMPLEMENTED & VERIFIED |
| Review intelligence | IMPLEMENTED & VERIFIED |

## Media

| Feature | Status |
|---------|--------|
| Media Studio + jobs | IMPLEMENTED & VERIFIED |
| Pillow local transforms | IMPLEMENTED & VERIFIED |
| Apply/revert to catalogue | IMPLEMENTED & VERIFIED |
| True segmentation (face/subject/object/bg-only) | NOT IMPLEMENTED |

## Reviews

| Feature | Status |
|---------|--------|
| Customer feedback (session auth) | IMPLEMENTED & VERIFIED |
| Review intelligence (inspect only) | IMPLEMENTED & VERIFIED |
| Third-party scrape | NOT IMPLEMENTED (by design, Phase 8 closed) |

## Workspace

| Feature | Status |
|---------|--------|
| Edit history | IMPLEMENTED & VERIFIED |
| Rollback | IMPLEMENTED & VERIFIED |
| Profile | PARTIALLY IMPLEMENTED (localStorage) |
| Settings | PARTIALLY IMPLEMENTED |
| Phase 13 dashboard | NOT IMPLEMENTED |

---

# PART 4 — Feature → code maps (major features)

## Login (username/password)

| Field | Value |
|-------|-------|
| **Purpose** | Authenticate restaurant operator |
| **User action** | Enter credentials on `/` |
| **Frontend page** | `frontend/src/app/page.tsx` |
| **Component** | `login-form.tsx` |
| **API client** | `auth-client.ts` → Better Auth |
| **Backend** | `auth/auth.ts` (Node, port 3001) |
| **Database** | `auth/data/better-auth.sqlite` |
| **Test** | `tests/test_auth.py`, `login-form.test.tsx` |
| **Status** | IMPLEMENTED & VERIFIED |
| **Flow** | UI → Better Auth → session cookie → `require_session()` on FastAPI |

## Create catalogue

| Field | Value |
|-------|-------|
| **Purpose** | Ingest menu from platform URL |
| **User action** | Fill form on `/catalogues/new` |
| **Frontend** | `create-catalogue-form.tsx` |
| **API** | `POST /catalog/create` via `catalog-api.ts` → `app/api/catalog/create/route.ts` |
| **Backend route** | `backend/main.py` `catalog_create()` |
| **Service** | `backend/services/catalog_service.py` `create_catalog()` |
| **Core logic** | scrape → parse → normalize → validate → canonical |
| **Database** | `catalogues`, `venues`, `venue_sources`, `catalogue_revisions` |
| **External** | Chrome CDP via `scraper/swiggy/scraper.py` |
| **Test** | `test_phase2_ingestion.py`, `test_catalog_api.py`, `create-catalogue-form.test.tsx` |
| **Status** | IMPLEMENTED — NEEDS VALIDATION (live scrape) |

## AI improvement apply

| Field | Value |
|-------|-------|
| **Purpose** | Owner-approved catalogue text/price/tag changes |
| **User action** | Generate proposal → Apply on improvements page |
| **Frontend** | `ai-improvements-view.tsx`, `item-quality-board.tsx` |
| **API** | `POST .../improvements`, `POST .../improvements/{id}/apply` |
| **Service** | `backend/improvement/service.py`, `apply.py` |
| **AI model** | Ollama `llama3:latest` (candidate only; validator authoritative) |
| **Database** | `catalogue_improvement_proposals`, `catalogues.payload`, `catalogue_edit_history` |
| **Test** | `test_phase6_improvement.py`, `test_phase11_improvement.py` |
| **Status** | IMPLEMENTED & VERIFIED (contracts); Ollama NEEDS VALIDATION |

## Baba AI assistant

| Field | Value |
|-------|-------|
| **Purpose** | Answer questions; route to pages; propose mutations |
| **User action** | Chat on `/baba-ai` or catalogue assistant |
| **API** | `POST /assistant/turn` or `POST .../assistant/turn` |
| **Router** | `backend/assistant/router.py` (deterministic, before LLM) |
| **Tools** | 7 allowlisted GET tools in `assistant/contract.py` |
| **Write tools** | Explicitly refused (`WRITE_TOOL_NAMES`) |
| **Test** | `test_phase9_assistant.py`, `baba-assistant-view.test.tsx` |
| **Status** | IMPLEMENTED & VERIFIED |

---

# PART 5 — Codebase map for developers

## `frontend/src/app/`
Next.js App Router pages. Dashboard routes wrapped in `AuthGate` + `OrganizationGate`.

## `frontend/src/lib/catalog-api.ts`
Single API client for all FastAPI catalogue operations. All calls go through Next.js `/api/*` proxies with session cookies.

## `frontend/src/app/api/**`
Thin proxies forwarding to FastAPI backend with auth headers.

## `backend/main.py`
FastAPI route registry — start here for API inventory.

## `backend/store.py`
SQLite persistence: `save_catalogue`, `get_catalogue`, `update_catalogue`, `delete_catalogue`. **Only** mutation entry for live payload (called from apply/mutation/media/rollback).

## `backend/services/catalog_service.py`
Catalogue creation orchestration (scrape pipeline).

## `backend/improvement/`
Phase 6/11 proposal generation, validation, apply.

## `backend/mutation/`
Phase 10 chat-driven typed patches.

## `backend/media/`
Phase 7 media jobs, Pillow providers, optional hosted.

## `backend/assistant/`
Phase 9 Baba AI turn, router, planner, tools.

## `backend/grading/`
Phase 3 grading.v1 engine (deterministic NLP + Pillow vision).

## `backend/review_intel/`
Phase 8 reviews + analysis.

## `backend/history/`
Edit history + rollback.

## `scraper/`
Platform scraping: swiggy (shared browser), zomato, magicpin parsers.

## `auth/`
Better Auth Node service (separate process).

## `tests/`
49 pytest files covering phases 1–12, scraping, auth config.

---

# PART 6 — Frontend map

| Page | Route | Purpose | Key API |
|------|-------|---------|---------|
| Login | `/` | Auth | Better Auth |
| Signup | `/signup` | Register | Better Auth |
| Overview | `/overview` | Dashboard | `GET /catalogues` |
| Create catalogue | `/catalogues/new` | Ingest | `POST /catalog/create` |
| Catalogue list | `/catalogues` | Browse | `GET /catalogues` |
| Catalogue detail | `/catalogues/[id]` | Read menu | `GET /catalogues/{id}` |
| Improvements | `/catalogues/[id]/improvements` | AI proposals | improvements APIs |
| Media | `/catalogues/[id]/media` | Media studio | media-jobs APIs |
| Reviews | `/catalogues/[id]/reviews` | Feedback + intel | reviews APIs |
| Assistant | `/catalogues/[id]/assistant` | Baba chat | assistant/turn |
| Baba AI | `/baba-ai` | Org assistant | assistant/turn |
| Grading | `/grading`, `/grading/[id]` | Grades | grade APIs |
| Areas | `/areas`, `/areas/[id]` | City jobs | area-jobs APIs |
| Settings | `/settings` | Preferences | local only |
| Profile | `/profile` | User profile | localStorage |

**No management screens** for direct item/category CRUD.

---

# PART 7 — Backend route map

See PART 9 API map. All catalogue routes use `require_session()` + organization authorization via catalogue ownership checks in services.

Mutation vs read:
- **Read:** GET catalogue, grade, explanations, lists, review intel, media studio
- **Mutate:** POST create, delete, grade (grade rows), improvements apply, media apply, mutation confirm, rollback, area jobs, customer feedback, review collect

---

# PART 8 — Database map

| Entity | Table | Purpose | Code |
|--------|-------|---------|------|
| Catalogue | `catalogues` | JSON payload + metadata | `store.py` |
| Venue | `venues`, `venue_sources` | Identity (org+platform+listing) | `canonical/` |
| Revision | `catalogue_revisions` | Pre-write snapshots | `store.py` |
| Grade | `catalogue_grades`, `catalogue_grade_jobs` | grading.v1 results | `grading/persist.py` |
| Platform eval | `catalogue_platform_evaluations` | Evidence | `platform_eval/` |
| Improvement | `catalogue_improvement_proposals` | AI proposals | `improvement/persist.py` |
| Media | `catalogue_media_jobs`, `_artifacts`, `_workspaces` | Media jobs | `media/persist.py` |
| Reviews | `catalogue_reviews`, `catalogue_review_analyses` | Feedback + intel | `review_intel/` |
| Mutation | `catalogue_mutation_proposals` | Chat proposals | `mutation/persist.py` |
| History | `catalogue_edit_history` | Audit trail | `history/persist.py` |
| Area job | `area_jobs` | Batch discovery | `area/` |
| User/Org | Better Auth SQLite | Auth | `auth/auth.ts` |

**Items/categories** are nested inside `catalogues.payload` — not separate tables.

---

# PART 9 — API map (product-critical)

| Method | Endpoint | Purpose | Mutates | Auth |
|--------|----------|---------|---------|------|
| POST | `/catalog/create` | Create from URL | Yes | Session+org |
| GET | `/catalogues` | List | Read | Session+org |
| GET | `/catalogues/{id}` | Detail | Read | Session+org |
| DELETE | `/catalogues/{id}` | Delete | Yes | Session+org |
| POST/GET | `/catalogues/{id}/grade` | Grade | Yes (grade) | Session+org |
| GET | `/catalogues/{id}/grade-explanation` | Explain | Read | Session+org |
| GET | `/catalogues/{id}/baba-score` | Baba Score | Read | Session+org |
| GET/POST | `/catalogues/{id}/platform-evaluation` | Platform evidence | POST yes | Session+org |
| POST | `/catalogues/{id}/improvements` | Generate proposal | Yes (row) | Session+org |
| GET | `/catalogues/{id}/improvements` | List proposals | Read | Session+org |
| POST | `.../improvements/{id}/apply` | Apply to catalogue | Yes (payload) | Session+org |
| POST | `.../improvements/{id}/cancel` | Cancel proposal | Yes (status) | Session+org |
| GET | `/catalogues/{id}/history` | Edit history | Read | Session+org |
| POST | `.../history/{id}/rollback` | Rollback | Yes (payload) | Session+org |
| GET | `/catalogues/{id}/media-studio` | Studio state | Read | Session+org |
| POST | `/catalogues/{id}/media-jobs` | Create job | Yes (row) | Session+org |
| POST | `.../media-jobs/{id}/apply` | Apply image | Yes (payload) | Session+org |
| POST | `/catalogues/{id}/media-revert` | Revert media | Yes | Session+org |
| POST | `/catalogues/{id}/customer-feedback` | Submit review | Yes | Session+org |
| POST/GET | `.../review-intelligence` | Analyze | POST yes | Session+org |
| POST | `/assistant/turn` | Org Baba chat | Read* | Session+org |
| POST | `/catalogues/{id}/assistant/turn` | Catalogue chat | Read* | Session+org |
| POST | `.../assistant/mutations/{id}/confirm` | Confirm mutation | Yes (payload) | Session+org |
| POST | `/area-jobs` | Create area job | Yes | Session+org |
| POST | `/area-jobs/{id}/start` | Start job | Yes | Session+org |
| POST | `/area-jobs/{id}/scrape-batch` | Batch scrape | Yes | Session+org |

\*May create proposal rows without mutating payload until confirm.

**Frontend caller:** `frontend/src/lib/catalog-api.ts` + Next proxies under `frontend/src/app/api/`.

---

# PART 10 — Scraping architecture

```
URL (CatalogCreateRequest)
  ↓
catalog_service.create_catalog()
  ↓
BrowserAccess.load() → collect_swiggy_source() [Chrome CDP, not Playwright bundled]
  OR FixtureAccess (tests)
  OR OfficialApiAccess (stub — pending)
  ↓
Platform parser:
  parse_swiggy_catalogue / parse_zomato_catalogue / parse_magicpin_catalogue
  ↓
normalize_catalogue() → validate_catalogue()
  ↓
ExistingCatalogueAdapter → to_canonical_from_response
  ↓
save_catalogue() + materialize_catalogue_images()
  ↓
catalogues table
```

| Stage | File | Output status |
|-------|------|---------------|
| Browser | `scraper/swiggy/scraper.py` | RawSource or blocked |
| CDP session | `scraper/swiggy/chrome_session.py` | Chrome attach/launch |
| Swiggy parse | `scraper/swiggy/parser.py` | ok / blocked / failed |
| Zomato parse | `scraper/zomato/parser.py` | ok / blocked / failed |
| Magicpin parse | `scraper/magicpin/parser.py` | ok / blocked / failed |
| Normalize | `backend/catalogue_normalize.py` | Normalized JSON |
| Validate | `backend/catalogue_validate.py` | Valid or reject |
| Persist | `backend/store.py` | SQLite row |

**Config:** `CATALOGFORGE_BROWSER_MODE`, `CATALOGFORGE_CHROME_DEBUG_URL`, `CATALOGFORGE_SWIGGY_ACCESS`  
**Partial:** Schema accepts `partial`; parsers emit ok/blocked/failed/pending only — **dead path**.  
**Retry:** No automatic retry storm; operator must retry create.  
**WAF:** Parser sets `blocked` status; UI shows blocked badge.

---

# PART 11 — AI architecture

| Feature | Class | Model | Approval | DB write |
|---------|-------|-------|----------|----------|
| Description/tags/category proposals | HYBRID | Ollama llama3 + validator | Owner apply | Yes |
| Item price improvement | DETERMINISTIC | Copies original_price | Owner apply | Yes |
| Grading NLP | DETERMINISTIC | Local heuristics | N/A | Grade row |
| Grading vision | DETERMINISTIC | Pillow heuristics | N/A | Grade row |
| Baba router | DETERMINISTIC | Regex/intents | N/A | No |
| Baba planner | HYBRID | Optional Ollama JSON | N/A | No |
| NL mutations | HYBRID | parse + patch | Confirm card | Yes on confirm |
| Review intel | DETERMINISTIC | review_intel.v1.1 | Inspect only | Analysis row only |
| Media local | DETERMINISTIC | Pillow | Owner apply | Yes on apply |
| Media hosted (optional) | HYBRID | FLUX/SVD if env | Owner apply | Yes on apply |

Prompts: `improvement/generators/ollama.py`, `assistant/planner.py`, `media/instruction.py`.

---

# PART 12 — Image / media architecture

| Operation | Target | Technology | Status |
|-----------|--------|------------|--------|
| enhance | FULL IMAGE | Pillow contrast/sharpness/brightness | Implemented |
| blur | FULL IMAGE | GaussianBlur | Implemented |
| crop | FULL IMAGE | Pillow crop box | Implemented |
| expand | FULL IMAGE | Pillow expand | Implemented |
| cleanup | FULL IMAGE | Median + sharpen | Implemented |
| edit | FULL IMAGE | Brightness/contrast + prompt hints | Implemented |
| background_removal | FULL IMAGE (ellipse mask) | `_fake_cutout` | Partial — not ML |
| background_generation | FULL IMAGE | Ellipse + flat bg | Partial |
| generate_image | FULL IMAGE | Compose or hosted | Partial |
| image_to_video | FULL IMAGE | 12-frame GIF zoom | Implemented |
| Face only | — | — | NOT IMPLEMENTED |
| Person/subject only | — | — | NOT IMPLEMENTED |
| Object only | — | — | NOT IMPLEMENTED |
| Background only (true seg) | — | — | NOT IMPLEMENTED |

Storage: `data/catalogue-assets/{catalogue_id}/`. Original preserved in artifacts; revert via `POST .../media-revert`.

---

# PART 13 — Authentication (including Email OTP)

| Layer | Location |
|-------|----------|
| Login UI | `login-form.tsx` (password + OTP tabs) |
| Auth server | `auth/auth.ts` Better Auth |
| OTP plugin | `emailOTP({ sendVerificationOTP })` line 148 |
| Delivery | `sendOtpEmail()` — SMTP or `AUTH_OTP_LOG=true` |
| Session on APIs | `backend/session.py` → Better Auth `/api/auth/get-session` |
| Org | Better Auth `organization()` plugin + `OrganizationGate` |

**Email OTP status: IMPLEMENTED — NOT WORKING**

Without `SMTP_HOST` or `AUTH_OTP_LOG=true`, line 111 throws: *"Email delivery is not configured..."*

Tests (`test_auth.py`) verify plugin **configuration exists**, not live OTP delivery.

---

# PART 14 — Testing map

| Area | Test file | Verifies | Limitation |
|------|-----------|----------|------------|
| Auth config | `test_auth.py` | OTP plugin wired | No SMTP test |
| Ingestion | `test_phase2_ingestion.py` | Fixture pipeline | No live WAF |
| Grading | `test_phase3_grading.py` | Engine | — |
| Grade explain | `test_phase5_grade_explain.py` | Projection | — |
| Improvements | `test_phase6_improvement.py` | Proposals | Ollama optional |
| Media | `test_phase7_media.py` | Jobs/apply | Hosted optional |
| Reviews | `test_phase8_*.py` | Feedback/intel | — |
| Assistant | `test_phase9_assistant.py` | Router/tools | — |
| Mutations | `test_phase10_mutation.py` | Chat patches | — |
| Apply/history | `test_phase11_*.py` | Apply + rollback | — |
| Phase 12 | `test_phase12_*.py` | Closed loop | — |
| Scraping | `test_swiggy_*.py`, `test_zomato_*` | Parsers | Fixtures |
| Frontend | 37 vitest files | Components/API client | No E2E browser |

**Distinction:** ~49 pytest + ~37 vitest = **code contracts verified**. Live scrape, OTP, Ollama = manual validation needed.

---

# PART 15 — Bugs and limitations

## BUG
- **BUG-001:** Email OTP fails without SMTP / AUTH_OTP_LOG
- **BUG-002:** Live scrape fails on WAF/blocked or Chrome CDP port busy
- **BUG-004:** `partial` extraction status never emitted by parsers

## LIMITATION
- **LIM-001:** Background removal is ellipse mask, not segmentation
- **LIM-002:** Nav uses first organization only
- **LIM-003:** Official Swiggy API access is stub (`OfficialApiAccess`)
- **LIM-004:** AI price improvement copies scraped price only — cannot set arbitrary new price via improvements

## VALIDATION GAP
- Live Chrome CDP scraping in production
- Ollama availability for improvements
- SMTP OTP end-to-end

## INCOMPLETE IMPLEMENTATION
- Partial extraction status (schema/UI without parser support)
- Profile/settings server persistence

## MISSING FEATURE
- Manage Catalogue UI
- Category add/remove/reorder
- Availability editing
- Phase 13 dashboard

---

# PART 16 — Phase history

| Phase | Name | Status | Closure doc |
|-------|------|--------|-------------|
| 0–1 | Canonical catalogue | CLOSED | PHASE1_CLOSURE.md |
| 2 | Ingestion | CLOSED | PHASE2_CLOSURE.md |
| 3 | Grading | CLOSED | PHASE3_CLOSURE.md |
| 4 | Platform eval | CLOSED | PHASE4_CLOSURE.md |
| 5 | Grade explanation | CLOSED | PHASE5_CLOSURE.md |
| 6 | AI improvements (preview) | CLOSED | PHASE6_CLOSURE.md |
| 7 | Media generation | Implemented, no closure doc | — |
| 8 | Review intelligence | CLOSED | PHASE8_CLOSURE.md |
| 9 | Baba AI assistant | CLOSED | PHASE9_CLOSURE.md |
| 10 | Typed mutations | CLOSED (in rules) | — |
| 11 | Apply + history | CLOSED | PHASE11_FINAL_AUDIT.md |
| 12 | Closed-loop re-grade | CLOSED (tests exist) | test_phase12_* |
| 13 | Operator dashboard | NOT STARTED | — |

Do not reopen closed phases without official defect declaration.

---

# PART 17 — Future product requirements

## REQUIRED (if product goal is owner self-service catalogue)
- Manage Catalogue sidebar section with Products/Categories UI
- Direct add/edit/remove item forms (not chat-only)
- Category add/remove/reorder
- Availability toggle/edit
- **Founder decision:** Whether chat/mutation/improvement paths remain parallel or get superseded

## NICE TO HAVE
- Server-side profile/settings
- True background segmentation for media
- Emit `partial` extraction honestly
- Production SMTP OTP

## FUTURE IDEA
- Phase 13 operator dashboard
- Official Swiggy partner API when credentials exist

## NEEDS FOUNDER DECISION
- Single vs dual editing UX (Manage Catalogue vs Baba AI vs Improvements)
- Price editing: free-form manual vs trusted-copy-only

---

# PART 18 — Documentation index (founder + developer)

Each major feature in this audit includes:
- Product description (Part 3 inventory)
- User flow (Part 1)
- Technical logic (Parts 4, 10, 11, 12)
- Tech stack (below)
- Code location (Parts 5–7)
- API (Part 9)
- Database (Part 8)
- Tests (Part 14)
- Status (throughout)
- Remaining work (Part 17)

**Founder Excel (separate artifact):** `HECTO_BABA_FEATURE_DELIVERY_DOSSIER.xlsx` — regenerate via `python audit_evidence/build_founder_dossier.py`

---

# Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 15, React 19, TypeScript, Tailwind |
| API proxy | Next.js App Router `/api/*` |
| Backend | FastAPI, Python 3 |
| Database | SQLite (catalogue + auth separate) |
| Auth | Better Auth (Node), username + emailOTP + org |
| Scraping | Playwright library + real Chrome CDP |
| Text AI | Ollama llama3:latest (local, optional) |
| Vision/heuristics | Pillow (grading + media default) |
| Hosted media | Optional HF/fal env (not required) |
| Tests | pytest (49 files), vitest (~37 files) |

---

# Architecture summary

Hecto Baba is a **monorepo restaurant catalogue platform**. Operators authenticate via Better Auth, create catalogues by scraping Swiggy/Zomato/Magicpin, view read-only menus, run deterministic grading, generate AI improvement proposals (Ollama + validation), apply approved changes, fix media via Media Studio, chat with Baba AI (read-only tools + mutation proposals), collect customer feedback, and inspect review intelligence.

**Critical invariant:** Live catalogue payload mutations never happen via direct REST item CRUD. They flow through **improvement apply**, **mutation confirm**, **media apply**, or **rollback** — all with history and re-grade.

**For onboarding:** Start at `backend/main.py`, `frontend/src/lib/catalog-api.ts`, `backend/store.py`, then the feature folder for your area.

---

*End of audit. No implementation performed.*
