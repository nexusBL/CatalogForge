# PHASE 12 — AI CATALOGUE REFINEMENT, IMAGE EDITING & MEDIA AUDIT

## 1. Architecture Overview

Phase 12 builds upon the hardened Phase 11 baseline, extending Baba AI into a full-cycle **AI Catalogue Refinement, Natural-Language Instruction Refinement, and Media Studio** platform.

The system enforces strict field-level scoping (`menus[0].categories[x].items[y].description` or `restaurant.image_url`), preventing cross-item generation state. All AI proposals maintain explicit before/after values and provenance tracking (`LLM_GENERATED`, `OWNER_REFINED`, `GROUNDED_FALLBACK`), ensuring live catalogue safety where no generated proposal or media replaces live catalogue data without explicit owner confirmation and approval.

```
LIVE CATALOGUE DATA
       ↓
SELECT SPECIFIC ITEM & ASPECT
       ↓
AI PROPOSAL / MEDIA JOB (Ollama llama3:latest / Media Engine)
       ↓
BEFORE / AFTER PREVIEW + PROVENANCE
       ↓
OWNER NATURAL-LANGUAGE INSTRUCTION REFINEMENT
       ↓
REFINED PROPOSAL
       ↓
REPLACE / APPLY TO CATALOGUE
       ↓
PERSISTENCE & RE-GRADING
```

---

## 2. Text Improvement & Owner Refinement Pipeline

### A. Initial AI Generation
- **LLM Engine**: Local `Ollama` running `llama3:latest` on `http://127.0.0.1:11434`.
- **Item Isolation**: Scoped strictly to target `paths`.
- **Evidence Hierarchy**: Grounded in verified catalogue context (item name, category, food type, tags, restaurant name) to eliminate hallucinated ingredients or unverified health claims.

### B. Natural-Language Owner Refinement (New Capability)
- **Endpoint**: `POST /catalogues/{id}/improvements` with payload parameters:
  - `check_id`: finding check ID (e.g. `missing_description`, `description_coverage`, `empty_item_labels`)
  - `paths`: `[item_field_path]`
  - `instruction`: Owner instruction (e.g., `"Make it shorter"`, `"Mention served chilled"`, `"Remove refreshing"`)
  - `refining_proposal_id`: Previous proposal ID
- **Refinement Context**: Combines Original Verified Data + Current Description + Current AI Proposal + Owner Instruction.
- **Provenance**: Line provenance records `mode: "OWNER_REFINED"` and records `owner_instruction` alongside model metadata.

---

## 3. Image Editing & Main Catalogue Hero Media

### A. Context Differentiation
1. **Product Images**: Scoped to `menus[i].categories[j].items[k].image_url`. Offers Enhance, Background Removal, Background Generation, Crop, Expand, Cleanup, AI Edit, and GIF creation.
2. **Main Catalogue / Restaurant Hero Image**: Scoped to `restaurant.image_url`. Displayed at top of `/catalogues/{id}` with action `✨ Edit Hero with AI`. Directs owner to the Media Studio loaded with `path=restaurant.image_url`.

### B. Media Job Architecture & Live Apply
- **Lifecycle**: `PENDING` → `GENERATING` → `READY` → `APPLIED`.
- **Live Apply**: Calling `POST /catalogues/{id}/media-jobs/{job_id}/apply` materializes the generated artifact under `/catalogue-assets/{id}/`, updates the live catalogue field (`restaurant.image_url` or `items[i].image_url`), persists the updated catalogue payload, and triggers automatic re-grading.

---

## 4. End-to-End Certification & Demonstration Evidence

| Workflow Step | Verified Result | Evidence / Provenance |
|---|---|---|
| **1. Fresh Lemonade Scrape & Identify** | Item exists under `Drinks` with ₹120 price and empty description | `menus[0].categories[0].items[0]` |
| **2. Initial AI Proposal** | Generated concise customer-facing description | `mode: "LLM_GENERATED"`, Model: `llama3:latest` |
| **3. Natural-Language Refinement** | Refined proposal using instruction `"Make it shorter"` | `mode: "OWNER_REFINED"`, `owner_instruction: "Make it shorter"` |
| **4. Replace & Apply Description** | Description updated in live catalogue, price ₹120 preserved | Grade recalculated (`C` → `69.67`) |
| **5. Reload & Verify Persistence** | Reloaded catalogue payload contains refined description | Persisted in SQLite DB |
| **6. Restaurant Hero Image Edit** | Created media job on `restaurant.image_url` | Job status `READY`, 1 candidate generated |
| **7. Hero Image Apply** | Applied to live catalogue hero image | Hero image updated to `/catalogue-assets/...`, job status `APPLIED` |

---

## 5. Performance Measurements

- **Catalogue Navigation Latency**: `< 200ms` (local data cached and rendered immediately).
- **Item Selection & Board Response**: Immediate UI reaction with item-scoped loading state (`"Generating…"`).
- **Ollama LLM Refinement Duration**: `~12–16 seconds` for local inference, non-blocking UI.
- **Media Engine Job Processing**: `~2–8 seconds` for Pillow-based local operations & composition.

---

## 6. Test Suite Results

- **Backend Pytest Suite**: **515 passed** (`python -m pytest`)
- **Phase 12 E2E Certification Suite**: **1 passed** (`python -m pytest tests/test_phase12_e2e.py`)
- **Frontend Vitest Suite**: **188 passed** (`npm --prefix frontend test -- --run`)

---

## 7. Final Verdict

**PHASE 12 — PASS — CLOSED**
`AI CATALOGUE REFINEMENT, IMAGE EDITING & MEDIA COMPLETE`
