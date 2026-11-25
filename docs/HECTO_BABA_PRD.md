# HECTO BABA — PRODUCT REQUIREMENTS DOCUMENT

---

## 1. Document Control

| Field | Value |
|-------|-------|
| **Product** | Hecto Baba (engineering repo: CatalogForge) |
| **Document type** | Canonical Product Requirements Document (PRD) |
| **Version** | 1.0 |
| **Status** | Active — consolidated baseline |
| **Last updated** | 2026-08-31 |
| **Owner / maintainer** | Not formally assigned in repository |
| **Audience** | Founder, Product Manager, Developer, QA, new engineers |

### Source documents used

This PRD consolidates (does not replace) the following:

| Priority | Source |
|----------|--------|
| 1 | Current verified implementation and E2E evidence |
| 2 | Closed phase contracts: `PHASE1_CLOSURE.md` … `PHASE6_CLOSURE.md`, `PHASE8_CLOSURE.md`, `PHASE9_CLOSURE.md`, `PHASE10_FINAL_HARDENING_AUDIT.md`, `PHASE11_FINAL_AUDIT.md`, `PHASE11_PHASE12_HISTORY_ROLLBACK_AUDIT.md` |
| 3 | `AGENT.md`, `README.md` |
| 4 | Product/technical audits: `PHASE12_AI_CATALOGUE_REFINEMENT_AUDIT.md`, `BABA_AI_FINAL_OWNER_WORKFLOW_AUDIT.md`, `audit_evidence/HECTO_BABA_FULL_READ_ONLY_AUDIT.md`, `audit_evidence/HECTO_BABA_READ_ONLY_FORENSIC_AUDIT.md` |
| 5 | Cursor phase rules (`.cursor/rules/phase*-closed.mdc`) |

### Important note on phase contracts

**Phase closure documents remain authoritative** for detailed technical invariants, formulas, and frozen behaviour within each closed phase (e.g. `grading.v1` weights, allowlisted improvement kinds, Baba AI tool restrictions). This PRD describes **what the product must do** at a consolidated level. When implementing or changing closed-phase behaviour, engineers must still consult the relevant phase closure file.

### Stale documentation reconciliation

The following older documents contain **outdated status** for features now implemented and E2E verified. This PRD uses current verified behaviour:

| Feature | Stale statement (older audits) | Current verified status |
|---------|--------------------------------|-------------------------|
| Manage Catalogue UI | “NOT IMPLEMENTED” in `HECTO_BABA_FULL_READ_ONLY_AUDIT.md`, `HECTO_BABA_READ_ONLY_FORENSIC_AUDIT.md` | **IMPLEMENTED & E2E VERIFIED** |
| Change Password on Profile | Documented only on Settings in `AGENT.md` | **IMPLEMENTED on Profile & E2E VERIFIED** |

---

## 2. Product Overview

**Hecto Baba** is a restaurant catalogue platform for business owners and operators. It helps them:

1. **Ingest** structured menu and venue data from delivery and dineout platforms (Swiggy, Zomato, Magicpin).
2. **View and manage** their catalogue as a canonical, versioned menu.
3. **Measure quality** with a deterministic grading engine and Baba Score.
4. **Improve** catalogue content through AI-generated proposals that the owner reviews and applies.
5. **Edit directly** via Manage Catalogue (forms) or natural-language flows via Baba AI.
6. **Fix media** (hero and item images) through Media Studio with owner-controlled apply.
7. **Understand customer feedback** through first-party review intelligence.
8. **Ask questions** via Baba AI, which retrieves stored facts and deep-links to the right workspace.

The owner remains in control: **AI proposes; the owner confirms or applies.** Live catalogue data is not silently mutated by AI, chat, or scraping.

**What the owner gets:** A single workspace to create catalogues, see quality scores and explanations, fix weak areas (manually or with AI assistance), track edit history, roll back mistakes, and inspect review patterns — without inventing grades, dishes, or review data.

---

## 3. Problem Statement

Evidence from repository documentation and phase contracts supports these problems:

| Problem | How Hecto Baba addresses it |
|---------|----------------------------|
| **Fragmented platform catalogue data** | Scrape/import from Swiggy, Zomato, Magicpin; normalize into one canonical catalogue per venue listing |
| **Poor or inconsistent catalogue quality** | Deterministic grading (`grading.v1`), Baba Score, grade explanations, fix-first findings |
| **Manual product management burden** | Manage Catalogue (direct add/edit/remove/price); typed Baba AI mutations; improvement apply |
| **Difficulty knowing what to fix first** | Grade explanation prioritization; Baba AI deep-links; review intelligence signals |
| **Risk of uncontrolled AI changes** | Proposal → owner Apply/Confirm pipelines; no silent mutation; audit history |
| **Weak or missing product images** | Media Studio jobs; owner apply to live hero/item images |
| **Disconnected customer feedback** | First-party feedback capture; aspect/target taxonomy; recurrence-based intelligence (inspect-only recommendations) |
| **Platform score confusion** | Baba Score is separate from platform-native scores; platform evaluation is evidence only |

---

## 4. Product Goals

### Current Product Goals

| Goal | Description |
|------|-------------|
| **G-C01** | Authenticated owners create and view catalogues from supported platforms |
| **G-C02** | Owners see honest extraction status (ok, blocked, failed, pending) |
| **G-C03** | Owners receive deterministic Baba grading and actionable explanations |
| **G-C04** | Owners preview AI improvements and apply them explicitly |
| **G-C05** | Owners manage products directly in Manage Catalogue with re-grade feedback |
| **G-C06** | Owners change passwords securely from Profile |
| **G-C07** | Owners use Baba AI for grounded answers and workspace navigation |
| **G-C08** | Owners confirm typed catalogue changes proposed via Baba AI |
| **G-C09** | Owners apply media improvements to live catalogue assets with control |
| **G-C10** | Owners inspect first-party review intelligence without auto-modifying catalogues |
| **G-C11** | All applicable catalogue writes are auditable and rollback-capable where implemented |

### Future Product Goals

*(From explicit founder/product backlog — not current commitments.)*

| Goal | Source |
|------|--------|
| **G-F01** | Full category management (add/remove/reorder categories) | Part 17, `HECTO_BABA_FULL_READ_ONLY_AUDIT.md` |
| **G-F02** | Owner-editable product availability | Part 17 |
| **G-F03** | Phase 13 operator dashboard | Part 17 |
| **G-F04** | Server-side profile/settings persistence | Part 17, AGENT.md |
| **G-F05** | True background/subject segmentation for media | Part 17, forensic audit |
| **G-F06** | Official Swiggy partner API when credentials exist | README, Part 17 |
| **G-F07** | Production-ready Email OTP delivery | Part 17, audits |

---

## 5. Non-Goals / Explicitly Out of Scope

| Exclusion | Rationale (source) |
|-----------|-------------------|
| **Silent AI mutation of live catalogue** | Phase 6, 9, 11, 16 — owner Apply/Confirm required |
| **Automatic improvement application** | Phase 6 — preview only until Phase 11 apply |
| **Third-party review scraping** (Google, Zomato, Swiggy, Yelp, etc.) | Phase 8 closure |
| **Guest / anonymous diner review submit in V1** | Phase 8 closure |
| **Baba AI applying improvements, grading, or media writes via tools** | Phase 9 closure |
| **Invented grades, dishes, or review claims in Baba AI** | Phase 9 closure |
| **Copying platform ratings into Baba Score** | Phase 4 closure |
| **Live platform HTTP for evaluation** | Phase 4 closure |
| **True face/subject/object-only segmentation** | Audits — NOT IMPLEMENTED |
| **Direct arbitrary REST item CRUD** | By design — mutations via approved pipelines only |
| **Fuzzy cross-platform restaurant identity merge** | Phase 1 closure |
| **LLM as authoritative grading engine** | Phase 3 — deterministic engine; LLM for proposals only |
| **Password reset email flow** | Not configured in auth (`sendResetPassword` absent) |
| **Phase 13 dashboard** | Explicitly future (Part 17) |

---

## 6. Users and Roles

| Role | Description | Primary workflows |
|------|-------------|-----------------|
| **Restaurant / business owner or operator** | Authenticated Better Auth user; member of a restaurant **organization** | Create catalogues, grade, improve, manage products, media, Baba AI, history |
| **Organization member** | Same auth model; catalogue APIs require org membership + catalogue authorization | Same as owner within authorized org/catalogue |
| **Customer / reviewer (V1)** | Session-authenticated user authorized for the catalogue | Submit first-party written feedback only |
| **Guest diner** | — | **Out of V1 scope** for review submit (Phase 8) |

**Distinction:** Owner workflows mutate catalogue through controlled pipelines. Customer feedback workflows write to review storage and produce inspect-only intelligence — they do **not** modify catalogue payload.

---

## 7. Core User Journeys

### 7.1 Authentication

```
Sign up (username + email + password required)
  OR Sign in (username/password)
  OR Sign in (Email OTP — configuration dependent)
  → Session cookie
  → AuthGate + OrganizationGate
  → Dashboard (Overview)
Profile → Edit profile (device-local fields)
Profile → Change Password (current + new + confirm) → success
Settings → notifications, change password (alternate path), logout
```

**Verified:** Username/password login and Profile Change Password E2E verified (2026-08-31).

### 7.2 Catalogue Creation

```
Login → Create Catalogue (platform URL, FSSAI, type: Restaurant / Dineout / Both)
  → Scrape / parse / normalize / validate
  → Persist canonical catalogue
  → View read-only menu at /catalogues/{id}
```

**Statuses:** `ok`, `blocked`, `failed`, `pending` — empty catalogues are never marked ok.

### 7.3 Catalogue Management (Manage Catalogue)

```
Login → Select catalogue → Manage Catalogue
  → Search products
  → Add product (name, category, price, description)
  → Edit product (name, price, description, tags, category move)
  → Remove product (confirm)
  → Saving & re-grading… feedback during apply
  → Stale revision rejected if catalogue changed elsewhere
  → Edit recorded in history; grade recalculated
```

**Verified:** Manage Catalogue E2E verified (2026-08-28 / 2026-08-31 sessions).

### 7.4 Quality Grading

```
Catalogue → Grade / AI Improvements (or Grading workspace)
  → Baba grading runs on current revision (grading.v1)
  → Baba Score displayed (projection of stored grade)
  → Grade explanation: sections, findings, fix-first
  → Platform evaluation evidence (not blended into Baba Score)
```

### 7.5 AI Improvements

```
Grade findings → Generate improvement proposal (allowlisted kind)
  → Preview: Current → Proposed → Why
  → Owner Apply or Cancel
  → On Apply: live catalogue updated, re-grade, history row
  → Optional: owner NL refinement of proposal before apply (Phase 12)
```

### 7.6 Baba AI (Read-Only Assistant)

```
Owner asks question (dock or /baba-ai)
  → Deterministic router (+ optional Ollama planner JSON)
  → Allowlisted read tools (grade, catalogue summary, reviews, etc.)
  → Grounded answer + server-built deep-link actions
  → No writes, no invented grades/dishes
```

### 7.7 Baba AI Mutations (Typed)

```
Owner natural-language edit request in Baba AI
  → Propose (shows current → proposed)
  → Owner Confirm or Cancel
  → On Confirm: persist via mutation patch + history + re-grade
  → Media ops start jobs only; live image unchanged until Media apply
```

### 7.8 Media

```
Catalogue → Generated Media (Media Studio)
  → Create job (enhance, background, crop, hero edit, etc. — local Pillow default)
  → Preview artifact
  → Owner Apply (or revert)
  → Live catalogue field updated; re-grade
```

### 7.9 Reviews

```
Authorized user → Submit customer feedback (text; optional rating/photo)
  → Stored with opaque author_key
  → Review intelligence engine analyzes aspects/targets/recurrence
  → Owner inspects signals and inspect-only recommendations
  → Does not write catalogue or auto-apply fixes
```

### 7.10 History & Rollback

```
Any approved apply (improvement, mutation, media, manage catalogue)
  → Append-only edit history (actor, before, after, provenance)
  → Owner Rollback with confirm
  → Previous value restored; new history row; re-grade snapshot
```

### 7.11 Change Password

```
Profile → Change Password
  → Enter current password
  → Enter new password + confirm (client validation: min 8 chars, match)
  → Submit → "Changing password…" (disabled controls)
  → Server verifies current password (Better Auth)
  → Success: fields cleared, "Password updated."
  → Other sessions revoked; current session refreshed (revokeOtherSessions)
```

**Verified:** E2E verified (2026-08-31). Wrong current password rejected; new password works; old password fails after change; account restored after test.

---

## 8. Functional Requirements — Master Catalogue

| ID | Requirement | Priority | Current Status | Acceptance Criteria | Source |
|----|-------------|----------|----------------|---------------------|--------|
| AUTH-001 | Owner can sign up with username, email, password (min 8 chars) | Must | IMPLEMENTED | Signup succeeds; username required | Auth hook, signup form |
| AUTH-002 | Owner can sign in with username/password | Must | IMPLEMENTED | Session cookie; dashboard access | README, E2E |
| AUTH-003 | Owner can sign in with Email OTP | Should | PARTIALLY IMPLEMENTED | Works when SMTP or AUTH_OTP_LOG configured | README, audits |
| AUTH-004 | Unauthenticated users cannot access catalogue APIs | Must | IMPLEMENTED | 401 without session | test_auth.py |
| AUTH-005 | Catalogue access requires organization membership | Must | IMPLEMENTED | Org gate on dashboard | README |
| AUTH-006 | Owner can view/edit Profile (device-local storage) | Should | IMPLEMENTED | Profile card + editor persists locally | AGENT.md |
| AUTH-007 | Owner can change password from Profile (current/new/confirm) | Must | IMPLEMENTED | E2E: verify, success, login with new password | E2E 2026-08-31 |
| AUTH-008 | Current password verified server-side on change | Must | IMPLEMENTED | Wrong password rejected without change | E2E, Better Auth |
| AUTH-009 | Password reset via email | Could | NOT IMPLEMENTED | sendResetPassword not configured | Auth config |
| CAT-001 | Owner creates catalogue from platform URL | Must | IMPLEMENTED | POST /catalog/create returns structured catalogue or honest status | README, PHASE2 |
| CAT-002 | Support Restaurant, Dineout, Both types | Must | IMPLEMENTED | Create form options | AGENT.md |
| CAT-003 | Ingest Swiggy / Zomato / Magicpin | Must | IMPLEMENTED | Parsers + fixtures; live varies | AGENT.md |
| CAT-004 | Owner views read-only catalogue menu | Must | IMPLEMENTED | /catalogues/{id} renders categories/items | Audits |
| CAT-005 | Owner deletes catalogue | Should | IMPLEMENTED | Delete from overview | Forensic audit |
| CAT-006 | Owner searches products in Manage Catalogue | Must | IMPLEMENTED | Search filters list | E2E Manage Catalogue |
| CAT-007 | Owner adds product via Manage Catalogue form | Must | IMPLEMENTED | Product appears after save + refresh | E2E |
| CAT-008 | Owner edits product (name, price, description, tags, category) | Must | IMPLEMENTED | Changes persist; re-grade runs | E2E, mutation contract |
| CAT-009 | Owner removes product via Manage Catalogue | Must | IMPLEMENTED | Confirm dialog; product removed | E2E |
| CAT-010 | Owner sees save/re-grade loading feedback on manage edits | Should | IMPLEMENTED | "Saving & re-grading…"; controls disabled | Manage Catalogue UI |
| CAT-011 | Stale revision blocks concurrent manage edits | Must | IMPLEMENTED | STALE when revision/hash mismatch | PHASE10/11 CAS |
| CAT-012 | Owner adds/removes/reorders categories | Could | NOT IMPLEMENTED | No backend operation | Part 17 |
| CAT-013 | Owner edits product availability | Could | NOT IMPLEMENTED | Display/scrape only | Part 17, audits |
| CAT-014 | Area/city batch discovery jobs | Should | PARTIALLY IMPLEMENTED | Fixture-tested; live validation incomplete | AGENT.md |
| GRADE-001 | System grades catalogue with grading.v1 engine | Must | IMPLEMENTED | Letter A–F; persisted grade row | PHASE3 |
| GRADE-002 | Baba Score projects stored grade (not recalculated from platform) | Must | IMPLEMENTED | Read-only projection | PHASE4 |
| GRADE-003 | Grade explanation with findings and fix-first | Must | IMPLEMENTED | GET grade-explanation | PHASE5 |
| GRADE-004 | Platform evaluation as isolated evidence | Should | IMPLEMENTED | Adapters; no live HTTP | PHASE4 |
| AI-001 | Generate improvement proposals (5 allowlisted kinds) | Must | IMPLEMENTED | description, labels, category_name, item_price, media_handoff | PHASE6 |
| AI-002 | Preview improvements before apply | Must | IMPLEMENTED | Current → Proposed → Why | PHASE6 |
| AI-003 | Owner Apply/Cancel improvements | Must | IMPLEMENTED | HTTP apply/cancel; re-grade | PHASE11 |
| AI-004 | Owner NL refinement of improvement proposal | Should | IMPLEMENTED | instruction + refining_proposal_id | PHASE12 audit |
| AI-005 | Baba AI read-only Q&A with deep links | Must | IMPLEMENTED | No write tools execute | PHASE9 |
| AI-006 | Baba AI typed mutations Propose→Confirm→Apply | Must | IMPLEMENTED | 8 payload ops + media honesty | PHASE10 |
| AI-007 | Baba AI refuses direct apply/grade/publish | Must | IMPLEMENTED | refuse_mutation; write tools rejected | PHASE9/10 |
| MEDIA-001 | Media Studio for catalogue images | Must | IMPLEMENTED | Jobs, preview, apply | PHASE7/11/12 |
| MEDIA-002 | Owner applies media to live hero/item fields | Must | IMPLEMENTED | catalogue-assets confinement; re-grade | PHASE11 |
| MEDIA-003 | True subject/background segmentation | Could | NOT IMPLEMENTED | Full-image Pillow processing only | Audits |
| REV-001 | Session-authenticated customer feedback submit | Must | IMPLEMENTED | No guest submit V1 | PHASE8 |
| REV-002 | Review intelligence with taxonomy and recurrence | Must | IMPLEMENTED | inspect-only recommendations | PHASE8 |
| REV-003 | Third-party review scrape | — | OUT OF SCOPE | By design | PHASE8 |
| HIST-001 | Append-only edit history on applies | Must | IMPLEMENTED | actor, before, after, provenance | PHASE11/12 audit |
| HIST-002 | Owner rollback with confirm | Must | IMPLEMENTED | Restores previous value; re-grade | PHASE11/12 audit |

---

## 9. Authentication & Account Requirements

### 9.1 Signup & Login

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| AUTH-001 | Username 3–30 chars, alphanumeric + `_` `.` | IMPLEMENTED | Username plugin |
| AUTH-002 | Password min 8, max 128 | IMPLEMENTED | Better Auth defaults |
| AUTH-003 | Email required at signup | IMPLEMENTED | Better Auth email signup |
| AUTH-004 | Username/password login | IMPLEMENTED | **WORKING** |
| AUTH-005 | Email OTP login | CONFIGURATION DEPENDENT | Requires `SMTP_HOST` or `AUTH_OTP_LOG=true` |

### 9.2 Organization & Authorization

| Requirement | Status |
|-------------|--------|
| Restaurant = Better Auth organization | IMPLEMENTED |
| Catalogue APIs require session + org membership + catalogue ownership | IMPLEMENTED |

### 9.3 Profile

| Requirement | Status | Notes |
|-------------|--------|-------|
| Profile card (name, email, photo, headline) | IMPLEMENTED | Merges session + localStorage |
| Personal/business fields editor | IMPLEMENTED | Stored per user on device |
| Server-side profile persistence | NOT IMPLEMENTED | Part 17 backlog |

### 9.4 Change Password

| Requirement | Status | Acceptance criteria |
|-------------|--------|---------------------|
| Change Password on **Profile** page | IMPLEMENTED | Section visible with 3 fields |
| Current password required | IMPLEMENTED | Client + server validation |
| New password min 8 characters | IMPLEMENTED | Client validation before API |
| Confirm new password must match | IMPLEMENTED | Rejected before API if mismatch |
| Server verifies current password | IMPLEMENTED | Better Auth `/change-password` |
| Passwords never logged or returned | IMPLEMENTED | Product security requirement |
| Loading state + duplicate-submit prevention | IMPLEMENTED | E2E verified |
| Success clears fields + message | IMPLEMENTED | E2E verified |
| Wrong current password shows clear error | IMPLEMENTED | "Current password is incorrect." |
| revokeOtherSessions on success | IMPLEMENTED | Other devices logged out |
| Change Password also on Settings | IMPLEMENTED | Alternate path (no confirm field) |

**Product-security (not implementation detail):** Passwords are hashed with scrypt via Better Auth; verification is server-side only.

### 9.5 Password Reset

| Requirement | Status |
|-------------|--------|
| Forgot password / email reset link | NOT IMPLEMENTED |
| Login "Forgot password?" routes to Email OTP | IMPLEMENTED | UX workaround |

---

## 10. Catalogue Requirements

### 10.1 Creation & Ingestion

| Capability | Status |
|------------|--------|
| Single-venue create from URL | IMPLEMENTED |
| Restaurant / Dineout / Both | IMPLEMENTED |
| Swiggy / Zomato / Magicpin parsers | IMPLEMENTED (fixtures); live varies |
| Normalization & validation | IMPLEMENTED |
| Raw source capture | IMPLEMENTED |
| Honest blocked/failed/pending status | IMPLEMENTED |
| Chrome CDP scraping | IMPLEMENTED — live validation environment-dependent |

### 10.2 Canonical Model

| Capability | Status |
|------------|--------|
| Stable catalogue UUID | IMPLEMENTED |
| Venue identity = org + platform + listing (no cross-platform merge) | IMPLEMENTED |
| Revision + state hash | IMPLEMENTED |
| Identity conflict → 409, no silent merge | IMPLEMENTED |

### 10.3 Product / Category Operations

| Operation | Manage Catalogue | Baba AI Mutation | Improvement Apply | Status |
|-----------|------------------|------------------|-------------------|--------|
| Add product | Yes | Yes | — | IMPLEMENTED |
| Remove product | Yes | Yes | — | IMPLEMENTED |
| Rename product | Yes | Yes | — | IMPLEMENTED |
| Change price | Yes | Yes | Copy trusted original only | IMPLEMENTED |
| Update description | Yes | Yes | Yes | IMPLEMENTED |
| Update tags/labels | Yes | Yes | Yes | IMPLEMENTED |
| Move between categories | Yes | Yes | — | IMPLEMENTED |
| Rename category | — | — | Yes | IMPLEMENTED |
| Change image | Link to Media | Media job start | media_handoff | IMPLEMENTED |
| Search products | Yes | — | — | IMPLEMENTED |
| Add category | — | — | — | NOT IMPLEMENTED |
| Remove category | — | — | — | NOT IMPLEMENTED |
| Reorder categories/items | — | — | — | NOT IMPLEMENTED |
| Edit availability | — | — | — | NOT IMPLEMENTED (display only) |

### 10.4 History & Rollback

| Capability | Status |
|------------|--------|
| Edit history on apply paths | IMPLEMENTED |
| Rollback with owner confirm | IMPLEMENTED |
| Before/after grade snapshots on applicable changes | IMPLEMENTED |

---

## 11. Grading & Baba Score Requirements

### 11.1 Grading Engine (grading.v1 — frozen)

| Aspect | Requirement |
|--------|-------------|
| Purpose | Measure catalogue quality deterministically |
| Weights | 50% deterministic / 25% NLP / 25% vision |
| Letter floors | A≥90, B≥75, C≥60, D≥40, F<40 |
| Hard failures | Force F |
| NLP | Local heuristic (no external provider required) |
| Vision | Local image analysis (no neural CV required) |
| Grade identity | catalogue + revision + hash + engine version |
| Invoke timing | Downstream of persist — not from ingest |

**Product note:** Grading is **deterministic**, not LLM-generated.

### 11.2 Baba Score

| Requirement | Status |
|-------------|--------|
| Baba Score = read-only projection of stored grading.v1 | IMPLEMENTED |
| Baba Score ≠ platform-native score | IMPLEMENTED |
| Ungraded venues stay ungraded (no invented F/0) | IMPLEMENTED |

### 11.3 Grade Explanation

| Requirement | Status |
|-------------|--------|
| Read-time projection of persisted grade | IMPLEMENTED |
| Section grades: Deterministic / Text / Images | IMPLEMENTED |
| Findings from fail/error evidence only | IMPLEMENTED |
| fix_first = priority 1 finding | IMPLEMENTED |
| 404 when no grade for current revision | IMPLEMENTED |

### 11.4 Platform Evaluation

| Requirement | Status |
|-------------|--------|
| Swiggy / Zomato / Magicpin adapters via registry | IMPLEMENTED |
| Platform scores as evidence only | IMPLEMENTED |
| No live platform HTTP | IMPLEMENTED |
| No Baba–platform blending formula | OUT OF SCOPE (deferred) |

---

## 12. AI Improvements Requirements

| Requirement | Status |
|-------------|--------|
| Consume Phase 5 findings + catalogue-state eligibility | IMPLEMENTED |
| Allowlisted kinds only: description, category_name, labels, media_handoff, item_price | IMPLEMENTED |
| Ollama (llama3:latest) as untrusted candidate generator | IMPLEMENTED |
| Backend validation authoritative | IMPLEMENTED |
| Proposals stored separately from canonical catalogue | IMPLEMENTED |
| Preview: Current → Proposed → Why | IMPLEMENTED |
| Owner Apply required | IMPLEMENTED |
| Owner Cancel | IMPLEMENTED |
| STALE on revision mismatch | IMPLEMENTED |
| Re-grade after apply via frozen grading.v1 | IMPLEMENTED |
| NL owner refinement of proposal | IMPLEMENTED |
| Never silently write catalogues.payload | IMPLEMENTED |

**Distinction:** AI **generates suggestions**; deterministic validators and owner Apply **control** what reaches the live catalogue.

---

## 13. Baba AI Requirements

### 13.1 Read-Only Assistant (Phase 9)

| Requirement | Status |
|-------------|--------|
| Explain → retrieve stored facts → recommend workspace → deep-link | IMPLEMENTED |
| Deterministic router before optional Ollama planner | IMPLEMENTED |
| Allowlisted GET tools only | IMPLEMENTED |
| Server-built actions[].href only | IMPLEMENTED |
| Client route hint; authz uses session + org + get_catalogue | IMPLEMENTED |
| No grade, apply, save, publish, media job from Baba tools | IMPLEMENTED |
| Stored grading.v1 / grade explanation / review intel = source of truth | IMPLEMENTED |
| Ungraded venues stay ungraded in answers | IMPLEMENTED |

### 13.2 Typed Mutations (Phase 10)

| Requirement | Status |
|-------------|--------|
| Propose → Confirm → Apply for allowlisted ops | IMPLEMENTED |
| NL parse → pending proposal with before/after | IMPLEMENTED |
| Owner confirm with one-use token | IMPLEMENTED |
| Media ops: job starts; live image unchanged until Media apply | IMPLEMENTED |
| Ambiguous items → clarify, no write | IMPLEMENTED |

### 13.3 Baba AI Does NOT

- Apply improvements via tools
- Grade catalogues
- Invent dishes, prices, or review claims
- Execute SQL or arbitrary JSON patches
- Bypass owner confirmation for payload writes

---

## 14. Media Requirements

| Requirement | Status | Notes |
|-------------|--------|-------|
| Media Studio workspace per catalogue | IMPLEMENTED | /catalogues/{id}/media |
| Job lifecycle: PENDING → GENERATING → READY → APPLIED | IMPLEMENTED | |
| Local Pillow transforms (default) | IMPLEMENTED | Enhance, crop, background ops on full image |
| Optional hosted providers (HF/fal) | PARTIALLY IMPLEMENTED | Env-dependent |
| Hero image edit (`restaurant.image_url`) | IMPLEMENTED | CTA on catalogue view |
| Item image edit | IMPLEMENTED | Scoped paths |
| Owner Apply copies to catalogue-assets | IMPLEMENTED | SSRF-safe confinement |
| Owner Revert | IMPLEMENTED | Where supported |
| Re-grade after media apply | IMPLEMENTED | |
| True segmentation (face/subject/object only) | NOT IMPLEMENTED | Explicit gap |
| AI video/GIF generation | IMPLEMENTED | Job-based; owner apply |

**Precision:** Current media processing operates on **full images** via local heuristics/Pillow — not ML segmentation of subjects from backgrounds.

---

## 15. Review Intelligence Requirements

| Requirement | Status |
|-------------|--------|
| First-party written feedback (`source=customer`) | IMPLEMENTED |
| Operator paste (`source=supplied`) | IMPLEMENTED |
| Session-authenticated submitters only | IMPLEMENTED |
| Opaque author_key; owners don't see email | IMPLEMENTED |
| Target taxonomy (product, catalogue, website, service, other) | IMPLEMENTED |
| Aspect taxonomy (taste, quantity, value, etc.) | IMPLEMENTED |
| Aspect-level polarity | IMPLEMENTED |
| Item linkage: exact → normalized → ambiguous → no_match | IMPLEMENTED |
| Recurrence threshold: 2 distinct reviews | IMPLEMENTED |
| Recommendations inspect-only | IMPLEMENTED |
| Never write catalogues.payload from reviews | IMPLEMENTED |
| Third-party scrape | OUT OF SCOPE |
| Guest/anonymous submit | OUT OF SCOPE (V1) |

---

## 16. Owner Control & Safety Model

Hecto Baba's product philosophy:

1. **The owner decides** what changes go live.
2. **AI proposes** improvements, descriptions, tags, and media candidates — it does not silently apply them.
3. **Confirmation gates** exist for Baba AI payload mutations (Propose → Confirm → Apply).
4. **Manage Catalogue** applies changes immediately after owner form submit — equivalent to confirmed owner intent (UI confirm for remove; save for edits).
5. **No second grading engine** inflates scores; re-grade uses frozen `grading.v1`.
6. **Revision/state-hash CAS** prevents stale writes when the catalogue changed elsewhere.
7. **Append-only history** records who changed what, with before/after values.
8. **Rollback** restores prior canonical values with owner confirm.
9. **Authorization boundaries:** session + organization + catalogue ownership on every mutating API.
10. **Grounding:** Baba AI and improvement generators must not invent catalogue facts not supported by stored evidence.

---

## 17. Non-Functional Requirements

| Category | Requirement | Status |
|----------|-------------|--------|
| **Security** | Session-authenticated APIs; httpOnly cookies | IMPLEMENTED |
| **Security** | Password hashing; no plaintext storage | IMPLEMENTED |
| **Security** | Catalogue-assets path confinement (SSRF-safe) | IMPLEMENTED |
| **Authorization** | Org membership gate on dashboard and APIs | IMPLEMENTED |
| **Data integrity** | BEGIN IMMEDIATE + CAS on concurrent writes | IMPLEMENTED |
| **Data integrity** | Foreign keys ON; identity conflict → 409 | IMPLEMENTED |
| **Auditability** | Edit history with actor, provenance, grade snapshots | IMPLEMENTED |
| **Determinism** | grading.v1 formulas frozen; letter_for_score fixed | IMPLEMENTED |
| **AI safety** | Allowlisted mutation/improvement kinds only | IMPLEMENTED |
| **AI safety** | Ollama output never executed without validation | IMPLEMENTED |
| **Reliability** | Idempotent apply replay (APPLIED rows) | IMPLEMENTED |
| **Performance** | No formal SLAs documented | — |
| **Observability** | No formal product observability spec | — |

---

## 18. Current Product Status

| Area | Status | Notes |
|------|--------|-------|
| **Authentication** | IMPLEMENTED | Username/password working; OTP config-dependent |
| **Change Password (Profile)** | IMPLEMENTED & E2E VERIFIED | Also on Settings (partial UX) |
| **Catalogue create/view** | IMPLEMENTED | Live scrape varies by platform/WAF |
| **Manage Catalogue** | IMPLEMENTED & E2E VERIFIED | Add/edit/remove/search/re-grade |
| **Scraping / ingestion** | IMPLEMENTED | Fixture-verified; live env-dependent |
| **Grading** | IMPLEMENTED | grading.v1 closed |
| **Baba Score** | IMPLEMENTED | Projection only |
| **Grade explanation** | IMPLEMENTED | |
| **AI Improvements** | IMPLEMENTED | Ollama optional |
| **Improvement apply/cancel** | IMPLEMENTED | |
| **Baba AI (read-only)** | IMPLEMENTED | |
| **Baba AI mutations** | IMPLEMENTED | |
| **Media Studio** | IMPLEMENTED | Pillow default |
| **Reviews / intelligence** | IMPLEMENTED | |
| **Edit history / rollback** | IMPLEMENTED | |
| **Category management** | NOT IMPLEMENTED | |
| **Availability editing** | NOT IMPLEMENTED | |
| **Password reset email** | NOT IMPLEMENTED | |
| **Phase 13 dashboard** | NOT IMPLEMENTED | Future |

---

## 19. Known Limitations

| Limitation | Impact |
|------------|--------|
| Email OTP requires SMTP or dev log flag | OTP sign-in non-functional in default dev without config |
| Live Swiggy often blocked by WAF | Extraction returns `blocked`; fixture mode for dev |
| Zomato/Magicpin not uniformly live-verified | Fixture-tested; live cards may differ |
| Category add/remove/reorder unavailable | Owners cannot restructure menu sections directly |
| Availability is scraped/display-only | Cannot mark items unavailable in Manage Catalogue |
| Profile data is device-local | Not synced server-side |
| Password reset not configured | Users must use OTP or admin repair script |
| No true image segmentation | Media ops affect full image, not isolated subjects |
| Duplicate Change Password entry points | Profile (full flow) vs Settings (no confirm) |
| AGENT.md and 2026 audits partially stale | Manage Catalogue / Profile password status |

---

## 20. Future / Backlog

*(Explicitly marked FUTURE — not current product commitments.)*

| ID | Item | Source |
|----|------|--------|
| F-01 | Category add/remove/reorder | Part 17 REQUIRED |
| F-02 | Availability toggle/edit | Part 17 REQUIRED |
| F-03 | Phase 13 operator dashboard | Part 17 FUTURE |
| F-04 | Server-side profile/settings | Part 17 NICE TO HAVE |
| F-05 | True background/subject segmentation | Part 17 NICE TO HAVE |
| F-06 | Honest `partial` extraction status end-to-end | Part 17 NICE TO HAVE |
| F-07 | Production SMTP for OTP | Part 17 NICE TO HAVE |
| F-08 | Official Swiggy partner API | README, Part 17 |
| F-09 | Password reset email flow | Auth gap |
| F-10 | Resolve dual editing UX (Manage vs Baba AI vs Improvements) | Part 17 NEEDS FOUNDER DECISION |

---

## 21. Success Criteria

**Formal product success metrics (KPIs) are currently not defined** in repository documentation.

### Operational / acceptance criteria supported by existing documents

| Criterion | Source |
|-----------|--------|
| Closed phases pass their pytest/vitest matrices | Phase closure / audit records |
| No silent catalogue mutation without owner action | Phase 6, 9, 11, 16 |
| grading.v1 unchanged without new engine version | Phase 3 closure |
| STALE rejected on revision mismatch | Phase 10/11 |
| Manage Catalogue E2E: add/edit/remove/price persist after refresh | E2E verification 2026-08 |
| Change Password E2E: new password works; old fails; wrong current rejected | E2E verification 2026-08-31 |
| Baba AI does not invent grades for ungraded catalogues | Phase 9 closure |
| Review recommendations never auto-apply | Phase 8 closure |

---

## 22. Phase Relationship

| Product Area | Relevant Phase(s) | Current State |
|--------------|-------------------|---------------|
| Foundation (concurrency, security) | Phase 0 | CLOSED |
| Canonical catalogue | Phase 1 | CLOSED |
| Ingestion & normalization | Phase 2 | CLOSED |
| Baba grading engine | Phase 3 | CLOSED |
| Baba Score + platform evaluation | Phase 4 | CLOSED |
| Grade explanation | Phase 5 | CLOSED |
| AI improvement proposals | Phase 6 | CLOSED |
| Generated media (baseline) | Phase 7 | IMPLEMENTED (no PHASE7_CLOSURE.md) |
| Review intelligence | Phase 8 | CLOSED |
| Baba AI assistant | Phase 9 | CLOSED |
| Typed catalogue mutations | Phase 10 | CLOSED |
| Improvement apply + media apply + re-grade | Phase 11 | CLOSED |
| NL refinement + media certification | Phase 12 | AUDITED (refinement slice) |
| History + rollback certification | Phase 11/12 audit | CLOSED |
| Operator dashboard | Phase 13 | NOT STARTED |
| Manage Catalogue UI | Post-audit implementation | IMPLEMENTED (not a numbered phase closure) |

Phase closure files remain the detailed technical contracts. This PRD maps product areas to phases for traceability only.

---

## 23. Open Product Decisions

| Decision | Context | Source |
|----------|---------|--------|
| **Single vs dual editing UX** | Manage Catalogue, Baba AI mutations, and Improvements can all change catalogue content — relationship and primary path unclear | Part 17 NEEDS FOUNDER DECISION |
| **Price editing policy** | Free-form manual price (Manage Catalogue) vs AI copy-trusted-original only — coexistence acceptable? | Part 17 |
| **Category management scope** | Required for self-service catalogue or defer? | Part 17 REQUIRED |
| **Availability editing** | Required for operators or remain scrape-only? | Part 17 REQUIRED |
| **Phase 13 dashboard scope** | What operator metrics/workflows? | Part 17 FUTURE |
| **Profile server persistence** | Device-local acceptable long-term? | Part 17 NICE TO HAVE |
| **Settings vs Profile for Change Password** | Two entry points; Settings lacks confirm field | Implementation fact — product decision pending |

---

## 24. Traceability

| Requirement Area | Primary Source | Supporting Sources |
|------------------|----------------|--------------------|
| Authentication & org | README Stage 3, AGENT.md | test_auth.py, auth/auth.ts |
| Change Password | E2E verification 2026-08-31 | Better Auth change-password API |
| Catalogue model | PHASE1_CLOSURE.md | PHASE2_CLOSURE.md |
| Manage Catalogue | E2E verification, mutation contract | manage-catalogue-view.tsx, test_manage_catalogue.py |
| Grading & Baba Score | PHASE3–5 closures | grading engine code |
| Platform evaluation | PHASE4_CLOSURE.md | platform adapters |
| AI Improvements | PHASE6, PHASE11 closures | improvement service |
| Baba AI read-only | PHASE9_CLOSURE.md | assistant service |
| Baba AI mutations | PHASE10_FINAL_HARDENING_AUDIT.md | mutation service |
| Media | PHASE12 audit, PHASE11 | media jobs |
| Reviews | PHASE8_CLOSURE.md | review_intel engine |
| History / rollback | PHASE11_PHASE12_HISTORY_ROLLBACK_AUDIT.md | history service |
| Owner journeys | This PRD §7 | HECTO_BABA_FULL_READ_ONLY_AUDIT Part 1 (stale on manage) |
| Future backlog | Part 17 | Forensic audit WR-* gaps |
| Stale status conflicts | PRD §1 reconciliation table | Full read-only audit Part 2 |

---

## 25. Change Log

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-08-31 | Initial canonical PRD created by consolidating phase closures, AGENT.md, audits, and current verified implementation (Manage Catalogue, Profile Change Password). |

---

*End of Hecto Baba Product Requirements Document v1.0*
