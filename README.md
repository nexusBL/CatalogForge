# CatalogForge

> **Enterprise AI-Powered Restaurant Catalogue SaaS, Quality Auditing & Optimization Platform**

CatalogForge  is an end-to-end catalogue management and quality intelligence platform for restaurant owners, cloud kitchen operators, and multi-brand franchise directors. It ingests, standardizes, evaluates, and optimizes restaurant menus from food-delivery aggregators (**Swiggy**, **Zomato**, **Magicpin**) and direct inputs.

The system features an automated multi-stage grading engine (`grading.v1`), an anti-hallucination local Large Language Model assistant (**Baba AI** powered by local Ollama `llama3:latest`), an in-house Media Studio, and an optimistic concurrency mutation engine with field-level edit history and 1-click atomic rollback.

---

## Table of Contents

1. [Key Features](#key-features)
2. [System Architecture](#system-architecture)
3. [Repository Directory & File Structure](#repository-directory--file-structure)
4. [Complete REST API Reference (44 Endpoints)](#complete-rest-api-reference-44-endpoints)
5. [Core Algorithms & Mathematical Formulations](#core-algorithms--mathematical-formulations)
6. [Scraper & Data Extraction Engine](#scraper--data-extraction-engine)
7. [Baba AI Assistant & Anti-Hallucination Pipeline](#baba-ai-assistant--anti-hallucination-pipeline)
8. [Database Architecture & Migrations](#database-architecture--migrations)
9. [Environment Variables](#environment-variables)
10. [Local Development & Setup Guide](#local-development--setup-guide)
11. [Testing & Quality Verification](#testing--quality-verification)

---

## Key Features

- **Multi-Platform Web Scraping over Chrome CDP:** Bypasses CloudFront WAF and anti-bot challenges by connecting over Chrome DevTools Protocol (`connect_over_cdp`) to an isolated Google Chrome profile, harvesting complex single-page apps (SPAs), Next.js `__NEXT_DATA__`, JSON-LD schemas, and dynamic DOM menus.
- **Canonical Catalogue Normalization:** Maps heterogeneous menus from Swiggy (Delivery & Dineout), Zomato (Order Online), and Magicpin into a unified `CanonicalDocument` schema with immutable platform provenance.
- **Multi-Stage Quality Grading (`grading.v1`):** Objectively scores menus from **Grade A to F** combining Deterministic validation (50%), heuristic NLP text quality (25%), and binary image header decoding (25%) with hard-failure short-circuits.
- **Zero-Hallucination Baba AI Assistant:** Employs a local 8B LLM (`llama3:latest` via Ollama) with a sub-5ms deterministic regex AST router, Pydantic-constrained JSON planning (`extra="forbid"`), and strict morphological token stem validation that mathematically eliminates fabricated ingredients or false dietary claims.
- **Interactive Natural-Language Refinement:** Restaurant owners can converse with the AI in multi-turn dialogues (*"Make it shorter"*, *"Mention served chilled"*) with full provenance tracking (`OWNER_REFINED`).
- **Compare-And-Swap (CAS) Concurrency & 1-Click Rollback:** Optimistic concurrency control via SHA-256 canonical state hashing and revision locks, backed by an append-only audit trail (`catalogue_edit_history`) that restores prior states and triggers automatic live re-grading.
- **Media Studio & Asset Pipeline:** In-house image processing (cropping, expansion, ellipse masking, prompt assist) paired with SSRF-safe asset materialization blocking private RFC 1918 subnets and cloud metadata endpoints.
- **First-Party Review Intelligence (`review_intel.v1.1`):** Aspect-based sentiment analysis parsing diner feedback into target-aspect-polarity tuples, identifying recurring complaints across a 2-review threshold without flattening mixed sentiments.

---

## System Architecture

```
[ Client / Browser ] (Next.js 14 App Router, React 18, Tailwind, shadcn/ui)
        │
        ├── Session Cookie / Email OTP ──> [ Auth Service ] (Node.js / Better Auth on Port 3005)
        │
        └── REST API Calls (HTTP / Proxied)
                 │
                 ▼
     [ FastAPI Core Backend ] (Port 8000, Python 3.11+)
        │
        ├── Authorization & Multi-Tenancy (authz.py, session.py)
        │
        ├── [ Scraper Subsystem ]
        │      ├── Playwright + Google Chrome DevTools Protocol (CDP Port 9222)
        │      ├── Injected DOM Harvester (platform_menu_harvest.js)
        │      └── Platform Parsers (Swiggy, Zomato, Magicpin)
        │
        ├── [ Quality Grading Engine (grading.v1) ]
        │      ├── Deterministic Rules (50% weight, hard-failure short-circuits)
        │      ├── Local NLP Text Grader (25% weight, length/coverage/placeholders)
        │      └── Local Vision Grader (25% weight, binary ISO-BMFF AVIF/PNG/JPEG decode)
        │
        ├── [ Baba AI & Improvement Subsystem ]
        │      ├── Tier 1: Deterministic Regex AST Router (< 5ms response)
        │      ├── Tier 2: Ollama LLM Planner (Llama 3 8B, Pydantic extra="forbid")
        │      └── Anti-Hallucination Lexical Token Validator (stem & prefix matching)
        │
        ├── [ Safe Mutation & History Subsystem ]
        │      ├── Optimistic Concurrency (CAS revision locks & SHA-256 state hashing)
        │      ├── Append-Only Audit Trail (catalogue_edit_history)
        │      └── 1-Click Atomic Rollback with Auto Re-grading
        │
        └── [ Persistence Layer ]
               ├── SQLite3 Relational Database (17 Tables, WAL Mode, BEGIN IMMEDIATE)
               └── Local Asset Store (/catalogue-assets/{id}/) with SSRF Protection
```

---

## Repository Directory & File Structure

```
CatalogForge/
├── auth/                               # Node.js Better Auth Microservice
│   ├── server.ts                       # Auth server entry point (email OTP, sessions)
│   ├── package.json                    # Auth dependencies (@better-auth/cli, tsx, etc.)
│   └── tsconfig.json                   # TypeScript configuration
├── backend/                            # FastAPI Core Backend Service
│   ├── main.py                         # 44 REST API endpoints, CORS, exception handlers
│   ├── authz.py                        # Organization membership authorization guards
│   ├── session.py                      # Session extraction & verification from Better Auth
│   ├── schemas.py                      # Core Pydantic request/response data contracts
│   ├── store.py                        # SQLite connection management & transactional operations
│   ├── migrate_catalogues.py           # DDL schema migrations across all 17 database tables
│   ├── raw_capture.py                  # Raw scraper payload persistence & audit capture
│   ├── catalogue_normalize.py          # Price coercion, currency cleaning, image unwrapping
│   ├── catalogue_validate.py           # Structural validation of normalized catalogues
│   ├── assistant/                      # Baba AI Assistant Subsystem
│   │   ├── router.py                   # Sub-5ms deterministic regex AST intent router
│   │   ├── planner.py                  # Constrained Pydantic JSON planner for Ollama
│   │   ├── service.py                  # Assistant turn lifecycle & conversation context
│   │   ├── tools.py                    # Allowlisted read-only execution tools
│   │   ├── contract.py                 # Assistant turn schemas, intents, and tool definitions
│   │   └── provider.py                 # HTTP JSON bridge to local Ollama server
│   ├── canonical/                      # Canonical Domain Models & Fingerprinting
│   │   ├── models.py                   # CanonicalDocument, CanonicalMenu, CanonicalMenuItem
│   │   ├── adapter.py                  # Ingestion adapters projecting platform data to canonical
│   │   ├── fingerprint.py              # Canonical state hashing (SHA-256) & equivalence
│   │   ├── identity.py                 # Stable venue & source item identity resolution
│   │   └── project.py                  # Bidirectional canonical-to-response projections
│   ├── grade_explain/                  # Grade Explanation & Prioritized Actions
│   │   ├── explain.py                  # Pure functional projection of grading findings
│   │   ├── recommend.py                # Prioritized fix_first action recommendation engine
│   │   └── contract.py                 # GradeExplanation data schemas
│   ├── grading/                        # Multi-Stage Quality Grading Engine (grading.v1)
│   │   ├── formula.py                  # Weighted scoring formula & hard failure aggregation
│   │   ├── deterministic.py            # Rule-based structural completeness checks
│   │   ├── nlp.py                      # Local text quality heuristics (coverage, placeholders)
│   │   ├── vision.py                   # Binary ISO-BMFF/AVIF/PNG header dimension parsing
│   │   ├── orchestrator.py             # Asynchronous grading job execution & workers
│   │   ├── persist.py                  # Atomic grading result persistence & revision locks
│   │   └── contract.py                 # GradingResult, StageSignals, EvidenceItem schemas
│   ├── history/                        # Field-Level Edit History & Rollback Subsystem
│   │   ├── service.py                  # History retrieval & 1-click rollback orchestrator
│   │   ├── persist.py                  # Append-only insertion into catalogue_edit_history
│   │   ├── compare.py                  # Before/after grade delta snapshot calculation
│   │   └── contract.py                 # EditHistoryRecord, RollbackRequest data contracts
│   ├── improvement/                    # Grounded AI Content Improvement Engine
│   │   ├── service.py                  # Improvement proposal lifecycle & apply engine
│   │   ├── eligibility.py              # Finding-to-target path resolution (e.g. missing descriptions)
│   │   ├── validate.py                 # Lexical token stem validator & anti-hallucination engine
│   │   ├── apply.py                    # Path-scoped live mutation applicator
│   │   ├── generators/                 # LLM Candidate Generators
│   │   │   ├── ollama.py               # Local Ollama Llama 3 8B generator with data grounding
│   │   │   └── grounded.py             # Deterministic fallback sentence generator
│   │   └── contract.py                 # ImprovementProposal, ImprovementLine schemas
│   ├── media/                          # Local Media Studio Subsystem
│   │   ├── service.py                  # Media job orchestrator & live asset application
│   │   ├── engine.py                   # In-house Pillow image processing (crop, expand, mask)
│   │   ├── studio.py                   # Media workspace state management
│   │   ├── prompts.py                  # Generative prompt assistance & template expansion
│   │   └── contract.py                 # MediaJob, MediaStudioResponse data contracts
│   ├── mutation/                       # Typed Chat Catalogue Mutations (Propose -> Confirm -> Apply)
│   │   ├── service.py                  # Natural language mutation parser & CAS validator
│   │   ├── patch.py                    # Granular item/category patch definitions
│   │   ├── resolve.py                  # Exact & normalized dish name entity resolver
│   │   └── contract.py                 # Mutation proposals & confirmation contracts
│   ├── platform_eval/                  # Platform Evaluation & Baba Score
│   │   ├── adapters.py                 # Platform-specific native rule adapters
│   │   ├── baba_score.py               # Independent projection of grading.v1
│   │   └── contract.py                 # Platform evaluation data models
│   ├── review_intel/                   # First-Party Diner Review Intelligence (review_intel.v1.1)
│   │   ├── service.py                  # Review ingestion & aspect-based grouping
│   │   ├── analysis.py                 # Aspect decomposition (taste, quantity, value, service)
│   │   └── contract.py                 # CustomerFeedbackRequest, ReviewIntelligence models
│   └── services/                       # Application Service Orchestrators
│       ├── catalog_service.py          # End-to-end catalogue extraction & access coordination
│       ├── grading_service.py          # Public grading API service
│       ├── area_service.py             # Multi-venue area discovery job runner
│       ├── grade_explain_service.py    # Grade explanation projection service
│       └── platform_eval_service.py    # Platform evidence evaluation service
├── frontend/                           # Next.js 14 Web Application
│   ├── src/
│   │   ├── app/                        # Next.js App Router Pages & API Proxies
│   │   │   ├── (dashboard)/            # Authenticated layout routes (catalogues, studio, etc.)
│   │   │   │   ├── catalogues/         # Catalogue detail, improvements, media routes
│   │   │   │   └── profile/            # User profile management
│   │   │   ├── api/                    # Next.js server route proxies to FastAPI & Better Auth
│   │   │   ├── page.tsx                # Login page
│   │   │   └── signup/                 # Registration page
│   │   ├── components/                 # React UI Components
│   │   │   ├── ai-improvements-view.tsx# ItemQualityBoard & AI proposal preview panel
│   │   │   ├── baba-ai-workspace.tsx   # Baba AI conversational assistant dock & chat interface
│   │   │   ├── catalogue-view.tsx      # Clean menu tree, categories, items, and prices
│   │   │   ├── grade-explanation-view.tsx # Letter grade badges & prioritized fix_first cards
│   │   │   ├── media-studio-view.tsx   # Image canvas editor, background removal & jobs
│   │   │   ├── review-intelligence-view.tsx # Aspect-based sentiment analysis dashboard
│   │   │   └── nav/                    # Collapsible side navigation & brand headers
│   │   ├── lib/                        # Frontend Utilities, API Client & State Stores
│   │   │   ├── catalog-api.ts          # Typed HTTP fetch client with retry logic
│   │   │   ├── catalogue-store.ts      # Optimistic client-side state caching
│   │   │   └── auth-guard.ts           # Route protection & session validation
│   │   └── config/                     # Site metadata & navigation section definitions
│   ├── package.json                    # Frontend dependencies (React 18, Tailwind, Radix UI)
│   └── vitest.config.ts                # Vitest unit & component test configuration
├── scraper/                            # Web Scraping & Extraction Engine
│   ├── cli.py                          # Command-line interface for standalone scraping
│   ├── html_common.py                  # DOM parsing utilities, JSON-LD unpackers, image cleaners
│   ├── platform_dom.py                 # Category sidebar parsers, media exposure, CDN upscaling
│   ├── platform_menu_harvest.js        # Injected client-side JavaScript menu extractor
│   ├── swiggy/                         # Swiggy Platform Extractor
│   │   ├── scraper.py                  # Swiggy page collector (browser & local fixture modes)
│   │   ├── parser.py                   # Swiggy cardGroupMap, REGULAR, and itemCards parser
│   │   ├── chrome_session.py           # Real Google Chrome CDP session manager (Port 9222)
│   │   ├── safe_fetch.py               # SSRF-safe image download manager with IP validation
│   │   └── dineout.py                  # Swiggy Dineout venue and offer parser
│   ├── zomato/                         # Zomato Platform Extractor
│   │   ├── parser.py                   # Order Online DOM parser, MENU_NOISE, and cuisine filters
│   │   ├── restaurant.py               # Zomato venue identity & JSON-LD schema parser
│   │   └── dineout.py                  # Dining rating and offers parser
│   ├── magicpin/                       # Magicpin Platform Extractor
│   │   ├── parser.py                   # Delivery menu parser, sidebar section anchor extractor
│   │   ├── restaurant.py               # Magicpin store identity parser
│   │   └── dineout.py                  # Magicpin vouchers & photos parser
│   └── discovery/                      # Universal Area & Neighborhood Discovery
│       ├── runner.py                   # Area discovery batch queue coordinator
│       ├── resolver.py                 # Geocoding resolver (Nominatim, Google, Mapbox, Haversine)
│       ├── locate.py                   # Automated platform header location picker
│       ├── swiggy.py                   # Swiggy listing paginator & XHR interceptor
│       ├── zomato.py                   # Zomato listing scraper
│       ├── magicpin.py                 # Magicpin listing scraper
│       └── dedupe.py                   # Deterministic venue identity deduplication
├── tests/                              # Backend Automated Pytest Suite (51 Test Files)
│   ├── fixtures/                       # Deterministic HTML & JSON test mocks (no live network)
│   ├── conftest.py                     # Shared test fixtures, mock session injectors, DB setup
│   ├── test_blockers_regression.py     # Critical regression tests for AI grounding & scraping
│   ├── test_phase3_grading.py          # Grading formula invariants, clamping, & hard failures
│   ├── test_phase10_mutation.py        # Natural-language typed mutations & CAS verification
│   ├── test_phase11_history_rollback.py# Append-only history & 1-click atomic rollback tests
│   ├── test_phase12_e2e.py             # End-to-end AI refinement & closed-loop certification
│   ├── test_ssrf.py                    # SSRF protection, DNS validation, & IP blacklist tests
│   └── ...                             # Platform, asset, discovery, and concurrency tests
├── audit_evidence/                     # Formal Engineering Audit Reports & Forensic Dossiers
├── docs/                               # System PRD & Technical Requirements Documentation
├── .env.example                        # Template environment variables configuration
├── .gitignore                          # Production Git ignore rules
└── requirements.txt                    # Python backend production & testing dependencies
```

---

## Complete REST API Reference (44 Endpoints)

### 1. Catalogue Ingestion & Management
- `POST /catalog/create` — Ingests a restaurant menu from Swiggy, Zomato, or Magicpin via Chrome CDP or local fixtures. Validates, normalizes, materializes assets, and persists to SQLite.
- `GET /catalogues` — Lists all stored catalogues for the authenticated organization (supports `compact=true` for sub-200ms sidebar rendering).
- `GET /catalogues/{catalogue_id}` — Retrieves the full canonical catalogue payload, categories, items, and pricing.
- `DELETE /catalogues/{catalogue_id}` — Permanently deletes a catalogue row and removes owned disk assets under `/catalogue-assets/{id}/`.

### 2. Quality Grading & Actionable Recommendations
- `POST /catalogues/{catalogue_id}/grade` — Triggers the `grading.v1` multi-stage grading engine (Deterministic, NLP, Vision) and persists letter grades (A–F) and evidence.
- `GET /catalogues/{catalogue_id}/grade` — Returns the completed grade for the catalogue's current head revision and state hash.
- `GET /catalogues/{catalogue_id}/grade-explanation` — Pure functional projection of findings into categorized severity groups and prioritized `fix_first` recommendations.

### 3. AI Improvements & Natural-Language Refinement
- `POST /catalogues/{catalogue_id}/improvements` — Generates grounded AI proposals (descriptions, tags, categories) via local Ollama (`llama3:latest`) with optional owner natural-language refinement (`instruction: "Make it shorter"`).
- `GET /catalogues/{catalogue_id}/improvements` — Lists all improvement proposals for the catalogue.
- `GET /catalogues/{catalogue_id}/improvements/{proposal_id}` — Retrieves a specific improvement proposal with before/after previews and line status.
- `POST /catalogues/{catalogue_id}/improvements/{proposal_id}/apply` — Applies allowlisted proposal lines to the live catalogue using Compare-And-Swap (CAS) revision locks, logs audit history, and automatically re-grades.
- `POST /catalogues/{catalogue_id}/improvements/{proposal_id}/cancel` — Cancels a pending improvement proposal, preventing subsequent application.

### 4. Audit History & 1-Click Rollback
- `GET /catalogues/{catalogue_id}/history` — Retrieves the append-only field-level audit trail (`catalogue_edit_history`) showing previous values, new values, actors, and grade deltas.
- `POST /catalogues/{catalogue_id}/history/{history_id}/rollback` — Restores the recorded `previous_value` for a specific field path, validates live state, appends a rollback audit row, and triggers live re-grading.

### 5. Baba AI Conversational Assistant
- `POST /assistant/turn` — Global conversational turn; routes via Tier-1 regex AST router or Tier-2 Ollama JSON planner.
- `POST /catalogues/{catalogue_id}/assistant/turn` — Context-aware conversational turn bound to a specific restaurant catalogue.
- `POST /catalogues/{catalogue_id}/assistant/mutations/{proposal_id}/confirm` — Confirms and applies a typed chat mutation (e.g. price change, dish rename).
- `POST /catalogues/{catalogue_id}/assistant/mutations/{proposal_id}/cancel` — Cancels a pending chat mutation proposal.
- `POST /catalogues/{catalogue_id}/catalogue-mutations` — Direct typed mutation endpoint for automated patch application.

### 6. Local Media Studio
- `GET /catalogues/{catalogue_id}/media-studio` — Returns media studio workspace configuration and target assets.
- `POST /catalogues/{catalogue_id}/media-jobs` — Creates an asynchronous image editing or enhancement job (crop, expand, mask, enhance).
- `GET /catalogues/{catalogue_id}/media-jobs` — Lists all media jobs for a catalogue.
- `GET /catalogues/{catalogue_id}/media-jobs/{job_id}` — Retrieves media job status and generated candidate image artifacts.
- `POST /catalogues/{catalogue_id}/media-jobs/{job_id}/apply` — Materializes a generated image artifact to `/catalogue-assets/{id}/`, updates the live catalogue field (`image_url`), and re-grades.
- `POST /catalogues/{catalogue_id}/media-jobs/{job_id}/cancel` — Cancels a pending media job.
- `POST /catalogues/{catalogue_id}/media-revert` — Reverts media workspace edits to the original source photo.
- `POST /catalogues/{catalogue_id}/media-prompt-assist` — Expands generative media prompts using grounded catalogue context.
- `GET /catalogues/{catalogue_id}/media-artifacts/{artefact_id}` — Serves binary generated image artifacts from disk.

### 7. Customer Feedback & Review Intelligence
- `POST /catalogues/{catalogue_id}/customer-feedback` — Ingests authenticated first-party diner written reviews with optional photo evidence.
- `GET /catalogues/{catalogue_id}/reviews` — Lists stored customer reviews for the catalogue.
- `POST /catalogues/{catalogue_id}/reviews/collect` — Batch collects reviews for analysis.
- `POST /catalogues/{catalogue_id}/review-intelligence` — Runs `review_intel.v1.1` aspect-based sentiment decomposition and recurrence grouping.
- `GET /catalogues/{catalogue_id}/review-intelligence` — Retrieves the latest customer review intelligence report.
- `GET /catalogues/{catalogue_id}/customer-feedback-photos/{photo_id}` — Serves diner review photo evidence.

### 8. Platform Evaluation & Baba Score
- `POST /catalogues/{catalogue_id}/platform-evaluation` — Evaluates platform-specific rules (Swiggy, Zomato, Magicpin) into structured evidence.
- `GET /catalogues/{catalogue_id}/platform-evaluation` — Retrieves stored platform evaluation results.
- `GET /catalogues/{catalogue_id}/baba-score` — Retrieves the independent Baba Score projection.

### 9. Area & Neighborhood Discovery
- `POST /area-jobs` — Creates a background discovery job for an area or city query (e.g. "Indiranagar, Bengaluru").
- `GET /area-jobs` — Lists area discovery jobs for the organization.
- `GET /area-jobs/{job_id}` — Retrieves discovery job status, venue lists, and geocoded coordinates.
- `POST /area-jobs/{job_id}/start` — Starts the area discovery scraper.
- `POST /area-jobs/{job_id}/scrape-batch` — Claims and executes batch scraping across discovered venues.
- `DELETE /area-jobs/{job_id}` — Permanently deletes an area discovery job.
- `POST /area-jobs/{job_id}/cancel` — Cancels an in-flight area discovery job.

---

## Core Algorithms & Mathematical Formulations

### 1. Multi-Stage Weighted Scoring Formula (`grading.v1`)
$$\text{Score}_{\text{aggregate}} = \min\left(100.0, \max\left(0.0, 0.50 \cdot C(S_d) + 0.25 \cdot C(S_{\text{nlp}}) + 0.25 \cdot C(S_v)\right)\right)$$
Where $C(x) = \min(100.0, \max(0.0, x))$ enforces strict stage clamping to prevent out-of-range stage scores from overwhelming the sum.
- **Hard Failure Short-Circuit:** If any critical check (such as `empty_menu` or `missing_restaurant_name`) fails with `severity="hard"`, the aggregate letter grade is immediately forced to **F**, regardless of the numeric score.
- **Grade Letters:** $A \ge 90.0$, $B \ge 75.0$, $C \ge 60.0$, $D \ge 40.0$, $F < 40.0$.

### 2. Haversine Great-Circle Distance Outlier Detection
Given restaurant pin $(\phi_1, \lambda_1)$ and target search centroid $(\phi_2, \lambda_2)$:
$$a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right), \quad d = 2 \cdot R \cdot \arcsin(\min(1.0, \sqrt{a}))$$
Where $R = 6371.0\text{ km}$. Listings with $d > 75.0\text{ km}$ are mathematically classified as cross-city search bleed and pruned from area catalogues.

### 3. Binary Image Header Decoding (ISO-BMFF / AVIF)
Traverses raw container byte streams without pixel decompression. For AVIF files, parses 8-byte box headers `(size, type)`. When `type == b'ispe'` is reached, unpacks 32-bit big-endian unsigned integers:
$$\text{width} = \text{struct.unpack}(">I", \text{data}[12:16])[0], \quad \text{height} = \text{struct.unpack}(">I", \text{data}[16:20])[0]$$
Enforces resolution floors: $\text{width} \ge 64$, $\text{height} \ge 64$, and $\text{area} \ge 6400\text{ px}^2$.

### 4. Compare-And-Swap (CAS) Concurrency State Hashing
Computes cryptographic SHA-256 state hashes over key-sorted canonical document projections:
$$H(D) = \text{SHA256}(\text{JSON}_{\text{sorted\_keys}}(\text{CanonicalProjection}(D)))$$
A mutation is applied only if the incoming proposal's `source_state_hash` and `source_head_revision` match the live database row; otherwise, it aborts with HTTP 409 `STALE`.

### 5. Lexical Token Grounding & Anti-Hallucination Verification
Extracts candidate tokens and verifies all ingredient words against trusted context tokens:
$$w \in \text{CandidateIngredients} \implies \exists t \in \text{TrustedTokens} \mid (w = t) \vee (\text{len}(t) \ge 4 \wedge (t.\text{startswith}(w) \vee w.\text{startswith}(t)))$$
Prohibits ungrounded ingredients, prices, quantities, and unverified marketing/dietary claims (e.g. "gluten-free", "halal", "organic").

---

## Scraper & Data Extraction Engine

The scraper (`scraper/`) is built to extract live data from heavily protected food delivery platforms:
- **Chrome CDP Session Management:** Connects to an installed Google Chrome executable over remote debugging port 9222. It uses an isolated user profile directory (`%TEMP%\catalogforge-chrome`), avoiding WAF bot detection triggered by headless Playwright binaries.
- **Injected DOM Harvester (`platform_menu_harvest.js`):** Client-side script injected into the active browser page. It traverses category navigation sidebars, expands collapsed items, parses multi-line price tokens, extracts high-resolution CSS background image URLs, and unescapes Next.js `__NEXT_DATA__` state trees.
- **CDN Dynamic Resolution Upscaling:** Intercepts CDN URLs and strips thumbnail constraints:
  - Google User Content: upgrades `=s120` and `=w120` to high-definition `=s1200`.
  - Swiggy / Cloudinary: rewrites low-res width limits `w_112` / `w_208` to `w_1000,f_auto,q_auto`.
  - Magicpin: rewrites `tr=w-200` to `tr=w-1000`.
- **SSRF-Safe Asset Materialization (`safe_fetch.py`):** Resolves external image hostnames and validates resolved IP addresses against private subnets (RFC 1918), loopback (`127.0.0.1`), link-local, and cloud metadata endpoints (`169.254.169.254`) before downloading assets.

---

## Baba AI Assistant & Anti-Hallucination Pipeline

Baba AI is a grounded assistant designed for commercial food catalogue management:
- **Two-Tier Intent Routing:**
  - *Tier 1 (Deterministic AST Router):* Compiled regular expressions in `backend/assistant/router.py` evaluate high-frequency queries (counts, grade explanations, capabilities, mutation cancellations) in $< 5\text{ms}$ with zero GPU compute.
  - *Tier 2 (Ollama Structured Planner):* Complex queries invoke local Ollama running `llama3:latest`. The planner schema enforces `model_config = ConfigDict(extra="forbid")`, restricting output to allowlisted read-only tools. Write-tool names are rejected at the planner boundary.
- **Data-as-Context Anti-Injection:** System prompts strictly define injected catalogue text as untrusted `DATA` to neutralize prompt injection attacks.
- **Iterative Natural-Language Refinement:** Owners can converse to adjust AI proposals (*"Make it shorter"*, *"Highlight that it's vegetarian"*). The backend tracks line provenance as `mode: "OWNER_REFINED"` alongside the previous proposal ID.
- **Closed-Loop Auto Re-Grading:** Applying an improvement updates the live database, logs before/after values to `catalogue_edit_history`, and recalculates quality grades, reporting exact score improvements (e.g. $+14.2$ points).

---

## Database Architecture & Migrations

The SQLite relational database is managed by deterministic schema migrations in `backend/migrate_catalogues.py` across 17 tables:
1. `catalogues` — Primary catalogue records and JSON payloads.
2. `area_jobs` — Background area discovery jobs and venue queue state.
3. `schema_migrations` — Applied migration version tracking.
4. `venues` — Canonical venue entity records.
5. `venue_sources` — Source aggregator platform mappings.
6. `catalogue_revisions` — Historical payload snapshots and state hashes.
7. `catalogue_grades` — Completed `grading.v1` results, scores, and evidence.
8. `catalogue_grade_jobs` — Asynchronous grading job queue and claim tokens.
9. `catalogue_platform_evaluations` — Platform-specific native evaluation results.
10. `catalogue_improvement_proposals` — Grounded AI proposals and line status.
11. `catalogue_media_jobs` — Image editing and enhancement jobs.
12. `catalogue_media_artifacts` — Generated binary image artifacts.
13. `catalogue_media_workspaces` — Media studio canvas editing sessions.
14. `catalogue_reviews` — First-party diner written feedback and ratings.
15. `catalogue_review_analyses` — Aspect-based review intelligence reports.
16. `catalogue_mutation_proposals` — Typed chat mutation proposals.
17. `catalogue_edit_history` — Append-only audit trail for field-level rollbacks.

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Default | Purpose |
|---|---|---|
| `BETTER_AUTH_SECRET` | *(Required)* | 32+ character secret for Better Auth session signing |
| `BETTER_AUTH_URL` | `http://localhost:3005` | Base URL of the Node.js Better Auth microservice |
| `BETTER_AUTH_TRUSTED_ORIGINS`| `http://localhost:3000` | Allowed CORS origins for authentication |
| `AUTH_PORT` | `3005` | Port for the Better Auth server |
| `AUTH_SQLITE_PATH` | `auth/data/auth.sqlite` | SQLite database path for users and sessions |
| `AUTH_OTP_LOG` | `true` | When true, prints email OTP codes to the console |
| `CATALOGFORGE_CATALOGUE_DB` | `data/catalogues.sqlite`| Path to the primary CatalogForge SQLite database |
| `CATALOGFORGE_SWIGGY_ACCESS`| `browser` | Extraction mode: `browser`, `fixture`, or `official` |
| `CATALOGFORGE_BROWSER_MODE` | `background` | Chrome launch mode: `background`, `chrome`, or `chrome-cdp` |
| `CATALOGFORGE_CHROME_DEBUG_URL`| `http://127.0.0.1:9222`| Target Chrome DevTools Protocol endpoint |
| `CATALOGFORGE_OLLAMA_URL` | `http://127.0.0.1:11434`| Local Ollama inference server base URL |
| `CATALOGFORGE_OLLAMA_MODEL` | `llama3:latest` | Local LLM model identifier (8B parameter model) |
| `CATALOGFORGE_OLLAMA_TIMEOUT`| `60` | HTTP timeout (in seconds) for local LLM inference |
| `GOOGLE_MAPS_API_KEY` | *(Optional)* | Google Geocoding API key for area discovery |
| `MAPBOX_ACCESS_TOKEN` | *(Optional)* | Mapbox Geocoding token for area discovery |

---

## Local Development & Setup Guide

### 1. Prerequisites
- **Python:** 3.11 or higher
- **Node.js:** 18.x or 20.x
- **Google Chrome:** Installed locally
- **Ollama:** Installed and running locally (`ollama run llama3:latest`)

### 2. Backend Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser drivers
playwright install chromium

# Start FastAPI backend (Port 8000)
uvicorn backend.main:app --reload --port 8000
```
> *Note:* Run Uvicorn in a single process. Do not run `uvicorn --workers N`; in-flight area scrape claims coordinate within a single process model.

### 3. Authentication Service Setup
```bash
cd auth
npm install
npx auth@latest migrate
npx tsx server.ts
```
*(Runs Better Auth service on Port 3005. With `AUTH_OTP_LOG=true`, OTP codes will print directly to the terminal).*

### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
*(Runs Next.js web application on `http://localhost:3000`).*

### 5. Starting Google Chrome with Remote Debugging (For Live Scraping)
```bat
:: Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%TEMP%\catalogforge-chrome"
```

---

## Testing & Quality Verification

CatalogForge is validated by **774 automated tests** with a **100% pass rate**:

### Backend Tests (581 Passed in Pytest)
```bash
# Run all backend tests
python -m pytest

# Run with concise summary
python -m pytest -q

# Run critical regression and closed-loop certification suites
python -m pytest tests/test_blockers_regression.py tests/test_phase11_history_rollback.py tests/test_phase12_e2e.py -q
```

### Frontend Tests (193 Passed in Vitest)
```bash
cd frontend

# Run all frontend component & store tests
npm test -- --run

# Run TypeScript typecheck
npm run typecheck

# Run ESLint validation
npm run lint
```
