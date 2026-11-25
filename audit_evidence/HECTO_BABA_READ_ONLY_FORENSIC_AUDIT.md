# Hecto Baba — Read-Only Forensic Product + Codebase Audit

**Audit date:** 27 August 2026  
**Scope:** Full repository read-only inspection  
**Rule:** No application source code was modified for this audit.

---

## Safety checklist

- [x] No application source code changed
- [x] No UI changed
- [x] No database changed
- [x] No API changed
- [x] No dependencies installed
- [x] No feature implemented
- [x] Catalogue Management only audited (not built)
- [x] Email OTP status verified from `auth/auth.ts`
- [x] AI vs deterministic classification from actual code paths
- [x] Image capabilities documented from `backend/media/providers.py`

---

## A. Product feature inventory

| ID | Module | Product feature | Status |
|----|--------|-----------------|--------|
| HB-AUTH-01 | Auth | Username/password login | IMPLEMENTED & VERIFIED |
| HB-AUTH-02 | Auth | Sign up (username required) | IMPLEMENTED & VERIFIED |
| HB-AUTH-03 | Auth | Email OTP sign-in | **IMPLEMENTED — NOT WORKING** (no SMTP / AUTH_OTP_LOG) |
| HB-AUTH-04 | Auth | Session-protected APIs | IMPLEMENTED & VERIFIED |
| HB-AUTH-05 | Auth | Organization membership gate | IMPLEMENTED & VERIFIED |
| HB-NAV-01 | Nav | Overview dashboard | IMPLEMENTED & VERIFIED |
| HB-NAV-02 | Nav | Side navigation (platforms, catalogues, grading, Baba AI) | IMPLEMENTED & VERIFIED |
| HB-CAT-01 | Catalogue | Single-venue create (Swiggy/Zomato/Magicpin) | IMPLEMENTED — NEEDS VALIDATION |
| HB-CAT-02 | Catalogue | Catalogue types: restaurant / dineout / both | IMPLEMENTED & VERIFIED |
| HB-CAT-03 | Catalogue | Catalogue detail view (read-only menu browser) | IMPLEMENTED & VERIFIED |
| HB-CAT-04 | Catalogue | Delete catalogue | IMPLEMENTED & VERIFIED |
| HB-CAT-05 | Catalogue | Dineout venue display | IMPLEMENTED & VERIFIED |
| HB-AREA-01 | Area | City/area discovery jobs | IMPLEMENTED — NEEDS VALIDATION |
| HB-AREA-02 | Area | Batch area scraping | IMPLEMENTED & VERIFIED |
| HB-GRADE-01 | Grading | Baba grading engine (`grading.v1`) | IMPLEMENTED & VERIFIED |
| HB-GRADE-02 | Grading | Grade explanation | IMPLEMENTED & VERIFIED |
| HB-GRADE-03 | Grading | Baba Score projection | IMPLEMENTED & VERIFIED |
| HB-GRADE-04 | Grading | Platform evaluation evidence | IMPLEMENTED & VERIFIED |
| HB-IMP-01 | AI | Improvement proposals (description, tags, category, price, media handoff) | IMPLEMENTED — NEEDS VALIDATION |
| HB-IMP-02 | AI | Owner apply/cancel improvements | IMPLEMENTED & VERIFIED |
| HB-IMP-03 | AI | Edit history & rollback | IMPLEMENTED & VERIFIED |
| HB-MEDIA-01 | Media | Media Studio + jobs | IMPLEMENTED & VERIFIED |
| HB-MEDIA-02 | Media | Image transforms (Pillow local default) | PARTIALLY IMPLEMENTED |
| HB-AI-01 | Assistant | Baba AI chat (read-only tools) | IMPLEMENTED & VERIFIED |
| HB-AI-02 | Assistant | NL mutations (Propose → Confirm → Apply) | IMPLEMENTED & VERIFIED |
| HB-REV-01 | Reviews | Customer feedback submit | IMPLEMENTED & VERIFIED |
| HB-REV-02 | Reviews | Review intelligence | IMPLEMENTED & VERIFIED |
| HB-ACC-01 | Account | Profile (localStorage) | PARTIALLY IMPLEMENTED |
| HB-ACC-02 | Account | Settings | PARTIALLY IMPLEMENTED |
| HB-MGMT-UI | **Future** | **Manage Catalogue sidebar / direct CRUD UI** | **NOT IMPLEMENTED** |

---

## B. Complete user journey

```
LOGIN (/, signup)
  → Better Auth session cookie
OVERVIEW (/overview)
  → list catalogues compact
CREATE CATALOGUE (/catalogues/new)
  → Single Venue | Area (areas/)
  → POST /catalog/create → scrape → normalize → save
CATALOGUE VIEW (/catalogues/[id])
  → read menu, images, dineout
GRADING (/grading, /grading/[id])
  → POST/GET grade, GET grade-explanation
AI IMPROVEMENTS (/catalogues/[id]/improvements)
  → POST improvements → proposal → Apply
MEDIA STUDIO (/catalogues/[id]/media)
  → media job → preview → Apply
BABA AI (/baba-ai, dock, /catalogues/[id]/assistant)
  → tools read-only OR mutation propose → confirm
REVIEWS (/catalogues/[id]/reviews)
  → feedback + review intelligence
HISTORY (on improvements page)
  → rollback prior edits
```

There is **no** journey step for a dedicated “Manage Catalogue” form editor.

---

## C. Catalogue management audit (future vs existing)

| Capability | Status | Evidence |
|------------|--------|----------|
| Add product/food item | **PARTIALLY EXISTS** | Phase 10 `add_item` via Baba AI chat → confirm → `backend/mutation/patch.py`. No form UI. |
| Edit product (name) | **PARTIALLY EXISTS** | `rename_item` mutation path only |
| Remove product | **PARTIALLY EXISTS** | `remove_item` mutation path only |
| Change price | **PARTIALLY EXISTS** | `change_price` mutation; improvement `item_price` (copy original_price) |
| Change description | **PARTIALLY EXISTS** | Improvement apply OR `update_description` mutation |
| Change tags | **PARTIALLY EXISTS** | Improvement apply OR `update_labels` mutation |
| Change image | **PARTIALLY EXISTS** | Media job apply only (not inline upload form) |
| Change category (move item) | **PARTIALLY EXISTS** | `move_item` mutation only |
| Rename category | **PARTIALLY EXISTS** | Improvement `category_name` kind + apply |
| Add category | **DOES NOT EXIST** | No op in mutation contract or patch |
| Remove category | **DOES NOT EXIST** | No dedicated op |
| Reorder items/categories | **DOES NOT EXIST** | No reorder in backend grep |
| Change availability | **DOES NOT EXIST** | Display-only helper in catalogue-view; no mutation |
| Direct REST CRUD on items | **DOES NOT EXIST** | No PUT/PATCH catalogue routes in `main.py` |
| Manage Catalogue nav section | **DOES NOT EXIST** | Nav has Catalogue list + per-catalogue sub-routes only |

**Product vs implementation:** Catalogue **content can change** only through approved pipelines (improvements, media apply, chat mutations, rollback)—not through a owner-facing catalogue management screen.

---

## D. Feature → code map (major areas)

### Catalogue creation

| Layer | Location |
|-------|----------|
| UI | `frontend/src/components/create-catalogue-form.tsx` |
| Page | `frontend/src/app/(dashboard)/catalogues/new/page.tsx` |
| API client | `frontend/src/lib/catalog-api.ts` → `createCatalogue()` |
| Next proxy | `frontend/src/app/api/catalog/create/route.ts` |
| Backend route | `backend/main.py` → `catalog_create()` |
| Service | `backend/services/catalog_service.py` → `create_catalog()` |
| Scrape | `scraper/swiggy/scraper.py` → `collect_swiggy_source()` |
| Parse | `scraper/{swiggy,zomato,magicpin}/parser.py` |
| Normalize | `backend/catalogue_normalize.py` |
| Validate | `backend/catalogue_validate.py` |
| Canonical | `backend/canonical/adapter.py` |
| DB | `backend/store.py` → `save_catalogue()` → `catalogues` table |
| Tests | `tests/test_phase2_ingestion.py`, `tests/test_catalog_api.py` |

**Flow:** UI → POST proxy → FastAPI → browser collect → parse → normalize → validate → canonical → SQLite → response.

### AI improvements

| Layer | Location |
|-------|----------|
| UI | `item-quality-board.tsx`, `ai-improvements-view.tsx` |
| Page | `catalogues/[id]/improvements/page.tsx` |
| API | `POST /catalogues/{id}/improvements` |
| Service | `backend/improvement/service.py` → `create_improvement()` |
| Generator | `backend/improvement/generators/ollama.py` |
| Validation | `backend/improvement/validate.py` |
| Apply | `backend/improvement/apply.py` |
| DB | `catalogue_improvement_proposals` |
| Model | Ollama `llama3:latest` @ `127.0.0.1:11434` |
| Tests | `tests/test_phase6_improvement.py`, `tests/test_blockers_regression.py` |

### Baba AI mutations (catalogue edits via chat)

| Layer | Location |
|-------|----------|
| UI | `baba-mutation-confirm.tsx`, assistant pages |
| API | `POST .../assistant/mutations/{id}/confirm` |
| Service | `backend/mutation/service.py` |
| Parse | `backend/mutation/parse.py` |
| Patch | `backend/mutation/patch.py` → `update_catalogue()` |
| DB | `catalogue_mutation_proposals`, `catalogues.payload` |
| Tests | `tests/test_phase10_mutation.py` |

---

## E–F. Frontend / backend code maps

### Frontend (product-critical)

| Path | Responsibility |
|------|----------------|
| `src/app/page.tsx` | Login |
| `src/app/signup/page.tsx` | Registration |
| `src/app/(dashboard)/layout.tsx` | AuthGate + OrganizationGate |
| `src/app/(dashboard)/overview/page.tsx` | Dashboard |
| `src/app/(dashboard)/catalogues/new/page.tsx` | Create catalogue |
| `src/app/(dashboard)/catalogues/[id]/page.tsx` | Catalogue detail |
| `src/app/(dashboard)/catalogues/[id]/improvements/page.tsx` | AI improvements |
| `src/app/(dashboard)/catalogues/[id]/media/page.tsx` | Media studio |
| `src/app/(dashboard)/catalogues/[id]/assistant/page.tsx` | Catalogue assistant |
| `src/app/(dashboard)/baba-ai/page.tsx` | Org-level Baba AI |
| `src/app/(dashboard)/grading/**` | Grading views |
| `src/app/(dashboard)/areas/**` | Area jobs |
| `src/lib/catalog-api.ts` | All catalogue API clients |
| `src/lib/auth-client.ts` | Better Auth client |
| `src/components/nav/side-nav/**` | Navigation tree |

### Backend (product-critical)

| Path | Responsibility |
|------|----------------|
| `backend/main.py` | All FastAPI routes |
| `backend/store.py` | SQLite persistence (save/get/update/delete catalogue) |
| `backend/services/catalog_service.py` | Create/scrape orchestration |
| `backend/services/grading_service.py` | Grade orchestration |
| `backend/improvement/` | Proposal generation + apply |
| `backend/mutation/` | Chat-driven catalogue patches |
| `backend/media/` | Media jobs + apply |
| `backend/assistant/` | Baba AI turn + router + planner |
| `backend/grading/` | grading.v1 engine |
| `backend/review_intel/` | Reviews + analysis |
| `backend/history/` | Edit history + rollback |
| `scraper/` | Platform scraping |
| `auth/auth.ts` | Better Auth + OTP |

---

## G. API map (summary)

All routes require session + `organization_id` unless noted.

| Method | Endpoint | Purpose | Mutates |
|--------|----------|---------|---------|
| POST | `/catalog/create` | Create catalogue from URL | Yes (new row) |
| GET | `/catalogues` | List catalogues | Read |
| GET | `/catalogues/{id}` | Get catalogue | Read |
| DELETE | `/catalogues/{id}` | Delete catalogue | Yes |
| POST/GET | `/catalogues/{id}/grade` | Run/get grade | Yes (grade rows) |
| GET | `/catalogues/{id}/grade-explanation` | Explain grade | Read |
| POST | `/catalogues/{id}/improvements` | Generate proposal | Yes (proposal row) |
| POST | `.../improvements/{id}/apply` | Apply proposal | Yes (payload) |
| POST | `.../media-jobs` | Create media job | Yes (job row) |
| POST | `.../media-jobs/{id}/apply` | Apply image | Yes (payload) |
| POST | `.../assistant/turn` | Baba chat | Read (+ proposal rows) |
| POST | `.../assistant/mutations/{id}/confirm` | Confirm mutation | Yes (payload) |
| POST | `.../history/{id}/rollback` | Rollback edit | Yes (payload) |
| POST | `/area-jobs` | Area discovery | Yes (job row) |

**No** `PUT`/`PATCH` `/catalogues/{id}/items/...` endpoints exist.

---

## H. Database map

| Entity | Table | Payload / notes |
|--------|-------|-----------------|
| Catalogue | `catalogues` | JSON `payload` (menus, categories, items) |
| Venue identity | `venues`, `venue_sources` | Phase 1 identity |
| Revision | `catalogue_revisions` | Snapshots before update |
| Grade | `catalogue_grades`, `catalogue_grade_jobs` | grading.v1 |
| Platform eval | `catalogue_platform_evaluations` | Evidence |
| Improvement proposal | `catalogue_improvement_proposals` | Phase 6/11 |
| Media job | `catalogue_media_jobs`, `catalogue_media_artifacts`, `catalogue_media_workspaces` | Phase 7 |
| Reviews | `catalogue_reviews`, `catalogue_review_analyses` | Phase 8 |
| Mutation proposal | `catalogue_mutation_proposals` | Phase 10 |
| Edit history | `catalogue_edit_history` | Phase 11 |
| Area job | `area_jobs` | Discovery/scrape batches |
| Auth users | `auth/data/better-auth.sqlite` | Separate DB |

Items/categories live **inside** `catalogues.payload` JSON—not separate normalized item tables.

---

## I. AI architecture

| Feature | Class | Model | Human approval |
|---------|-------|-------|----------------|
| Description/tags/category AI | Hybrid | Ollama llama3 | Owner apply |
| Item price improvement | Deterministic | Copies `original_price` | Owner apply |
| Grading NLP | Deterministic | Local heuristics | N/A |
| Grading vision | Deterministic | Pillow heuristics | N/A |
| Baba router | Deterministic | Regex/intents | N/A |
| Baba planner | Hybrid | Ollama JSON optional | N/A |
| NL mutations | Hybrid | parse + patch | Confirm card |
| Review intel | Deterministic | review_intel.v1.1 | Inspect only |
| Media prompt assist | Deterministic | Templates | N/A |
| Media generative (optional) | Hybrid | Hosted FLUX/SVD if env set | Owner apply |

Prompts: `backend/improvement/generators/ollama.py`, `backend/assistant/planner.py`, `backend/media/instruction.py`.

---

## J. Image / media map

| Operation | Scope | Technology | Status |
|-----------|-------|------------|--------|
| enhance, blur, crop, expand, cleanup, edit | FULL IMAGE | Pillow | Implemented |
| background_removal | FAKE ellipse cutout | Pillow `_fake_cutout` | Partial |
| background_generation | Ellipse + flat bg | Pillow / optional hosted | Partial |
| generate_image | FULL compose | Pillow / optional hosted | Partial |
| image_to_video | FULL GIF zoom | Pillow 12-frame | Implemented |
| Face / subject / object only | — | — | **NOT IMPLEMENTED** |

Storage: `data/catalogue-assets/{catalogue_id}/`; apply via `apply_media_job()`.

---

## K. Scraping / ingestion map

| Stage | File | Function |
|-------|------|----------|
| Browser collect | `scraper/swiggy/scraper.py` | `collect_swiggy_source` (shared all platforms) |
| CDP | `scraper/swiggy/chrome_session.py` | `acquire_chrome_cdp`, modes |
| Swiggy parse | `scraper/swiggy/parser.py` | `parse_swiggy_catalogue` |
| Zomato parse | `scraper/zomato/parser.py` | `parse_zomato_catalogue` + merge helpers |
| Magicpin parse | `scraper/magicpin/parser.py` | `parse_magicpin_catalogue` |
| Normalize | `backend/catalogue_normalize.py` | `normalize_catalogue` |
| Persist | `backend/store.py` | `save_catalogue` |
| Images | `scraper/swiggy/assets.py` | `materialize_catalogue_images` |

Timeouts: NAV 45s, menu wait 20s, challenge 12s. **No retry-storm.** WAF → `blocked`. `partial` status in schema but **parsers do not emit it**.

Config: `CATALOGFORGE_BROWSER_MODE`, `CATALOGFORGE_CHROME_DEBUG_URL`, `CATALOGFORGE_SWIGGY_ACCESS`.

---

## L. Authentication (Email OTP)

**Implementation exists:**
- Plugin: `auth/auth.ts` lines 148–151 `emailOTP`
- UI: `frontend/src/components/login-form.tsx` OTP mode
- Client: `auth-client.ts` `emailOTPClient`

**Why NOT WORKING:**
- `sendOtpEmail()` throws if `SMTP_HOST` unset AND `AUTH_OTP_LOG !== "true"` (line 111)
- Tests only verify **configuration presence** (`tests/test_auth.py`), not live email delivery

**Status:** IMPLEMENTED — NOT WORKING (until SMTP or dev log configured and verified)

---

## M. Test / verification map

| Area | Test files | Verifies | Live gap |
|------|------------|----------|----------|
| Auth config | `test_auth.py` | Plugin wired | OTP delivery not tested |
| Ingestion | `test_phase2_ingestion.py` | Fixture pipeline | Live WAF not in CI |
| Grading | `test_phase3_grading.py` | Engine contracts | — |
| Improvements | `test_phase6_improvement.py`, `test_blockers_regression.py` | Proposals/apply | Real Ollama optional |
| Mutations | `test_phase10_mutation.py` | Chat patches | — |
| Media | `test_phase7_media.py` | Jobs/apply | Hosted optional |
| Assistant | `test_phase9_assistant.py` | Tools/router | — |
| Frontend | `frontend/src/**/*.test.ts(x)` | Components | 189 vitest tests |

**Distinction:** ~567 pytest + 189 vitest = **code verified**. Live scrape, OTP email, and Ollama = **NEEDS MANUAL VERIFICATION**.

---

## N. Work remaining

| ID | Type | Item |
|----|------|------|
| WR-001 | BUG | Fix Email OTP delivery (SMTP / config) |
| WR-002 | VALIDATION | Live scraping under WAF + Chrome CDP ops |
| WR-003 | INCOMPLETE | Emit `partial` extraction when menu partially harvested |
| WR-004 | INCOMPLETE | Media UI vs Pillow capability alignment |
| WR-005 | **MISSING PRODUCT** | **Manage Catalogue UI (direct CRUD)** |
| WR-006 | **MISSING PRODUCT** | Add/remove category, reorder menu |
| WR-007 | **MISSING PRODUCT** | Item availability editing |
| WR-008 | FUTURE | Phase 13 operator dashboard |
| WR-009 | VALIDATION | Production deployment runbook |
| WR-010 | INCOMPLETE | Server-side profile/settings |

---

## O. Known bugs

| ID | Issue |
|----|-------|
| BUG-001 | Email OTP does not deliver without SMTP/AUTH_OTP_LOG |
| BUG-002 | Live scrape fails blocked/WAF or Chrome port busy |
| BUG-003 | Media UI overclaims vs local ellipse background removal |
| BUG-004 | `partial` extraction status never set by parsers |

---

## P. Tech stack & architecture summary

**Stack:** Next.js 15 + React 19 + TypeScript + Tailwind (frontend); FastAPI + Python (backend); SQLite (catalogue + auth); Better Auth Node; Playwright/Chrome CDP (scrape); Ollama llama3 (text AI); Pillow (media/vision heuristics).

**Architecture:** Monorepo with Next.js API proxies to FastAPI. Catalogue state is JSON in SQLite. All **mutations** to menu content go through guarded pipelines (improvement apply, mutation confirm, media apply, rollback)—never direct REST item CRUD. Grading is frozen `grading.v1`. Phases 1–6, 8–12 closed; Phase 7 implemented; Phase 13 not started.

**For new developers:** Start at `backend/main.py` (routes), `frontend/src/lib/catalog-api.ts` (client), `backend/store.py` (persistence), then feature folder (`improvement/`, `mutation/`, `media/`, `assistant/`).

---

*End of read-only audit.*
