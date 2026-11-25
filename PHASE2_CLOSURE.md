# PHASE 2 — OFFICIAL FINAL CLOSURE RECORD

This is the final Phase 2 handoff for future phases.

PHASE 2 STATUS:
PASS — CLOSED

Official name: Catalogue Ingestion & Normalization

Do NOT make further Phase 2 changes unless a future official phase identifies a concrete defect or required dependency.

==================================================
PROJECT PHASE STATUS
==================================================

PHASE 0 — PASS / CLOSED

PHASE 1 — PASS / CLOSED

PHASE 2 — PASS / CLOSED

PHASE 3 — NOT STARTED

Phase 0, Phase 1, and Phase 2 are closed baselines. Do not reopen or modify them unless the official requirements of a future phase explicitly require a change.

==================================================
PHASE 2 OBJECTIVE
==================================================

Phase 2 connected existing scrapers/importers to deterministic validation and normalization, preserved raw source data, and fed normalized catalogues into the existing Phase 1 canonical persistence path.

Conceptual flow:

SOURCE / PLATFORM
        ↓
SCRAPER / IMPORTER
        ↓
RAW CATALOGUE
        ↓
VALIDATION
        ↓
NORMALIZATION
        ↓
PLATFORM ADAPTER
        ↓
CANONICAL BABA CATALOGUE

Covered:

- connecting existing scrapers/importers
- using the existing platform adapter boundary
- source-field mapping
- price, category, image, and tag normalization
- missing-data detection
- validation
- duplicate detection (deterministic, not fuzzy)
- raw source preservation
- feeding normalized data into Phase 1 canonical ingestion

Implementation was additive. Phase 1 canonical persistence was not replaced.

==================================================
ARCHITECTURE
==================================================

Production ingest remains:

`create_catalog` → normalize/validate → `ExistingCatalogueAdapter` → `save_catalogue` / `update_catalogue` (`_stamp_canonical`)

Raw capture:

NETWORK / SCRAPE (outside DB)
        ↓
pending raw file (`scrape_token`)
        ↓
parse / validate / normalize
        ↓
Phase 1 database transaction
        ↓
bind pending file to catalogue UUID

Important modules (inspect the repository for exact current details):

- `backend/catalogue_normalize.py`
- `backend/catalogue_validate.py`
- `backend/raw_capture.py`
- `backend/services/catalog_service.py`
- `backend/main.py`
- `backend/services/area_service.py`
- `backend/schemas.py`
- `backend/canonical/fingerprint.py`
- `backend/canonical/adapter.py` (`ExistingCatalogueAdapter`)
- `tests/test_phase2_ingestion.py`

CLI is not a production canonical importer and was not redesigned for Phase 2 parity.

==================================================
RAW DATA POLICY
==================================================

Raw captures are durable Phase 2 provenance.

- Raw captures are retained.
- Bound raw captures are retained.
- Pending captures may remain after crash, cancellation, or identity conflict.
- No automatic janitor or orphan cleanup.
- Manual/operator cleanup is outside Phase 2.
- Raw data is not deleted merely because canonical persistence fails.
- Raw I/O is outside the database transaction.
- Paths are organization/tenant isolated.
- The raw directory is not statically served.

The 8MB raw truncation that briefly existed was removed before closure.

Full raw HTML / `next_data` payloads are preserved.

Do NOT reintroduce arbitrary raw-data truncation.

There is no raw database table, replay subsystem, or object-storage redesign.

==================================================
NORMALIZATION
==================================================

Deterministic only.

Prices: parse numeric values, strip symbols, handle inverted MRP where supported, do not ÷100 without evidence, do not fabricate prices.

Categories: whitespace, deterministic missing-name handling. No Baba taxonomy. No AI classification.

Images: normalize references, preserve valid source URLs, reject junk/invalid references per existing safety rules. No image AI. Image HTTP download remains the existing asset path, outside DB transactions.

Tags: trim, drop empty, dedupe, preserve meaningful source tags, map supported bestseller flags deterministically.

==================================================
VALIDATION
==================================================

Hard extraction/completeness failures remain the existing ingest gates.

Quality warnings (additive `quality` on the API response, excluded from canonical fingerprint) include missing price/image/source item id/item name, invalid price/image, and category count mismatch.

A named item is not silently dropped solely because price is missing.

Raw source remains available for diagnosis.

==================================================
DEDUPLICATION
==================================================

No fuzzy restaurant or menu-item matching.

No embeddings, semantic similarity, AI deduplication, or cross-platform identity merge.

Repeated identical ingestion, duplicate source rows, identity conflicts, and duplicate menu items remain separate concepts.

Duplicates are reported where appropriate. They are not silently merged unless Phase 1 deterministic identity already requires that.

==================================================
PLATFORM ADAPTER
==================================================

Phase 2 reused `ExistingCatalogueAdapter`.

Do not add SwiggyAdapter / ZomatoAdapter / MagicpinAdapter unless a future official phase requires them and inspection proves they are necessary.

Platform parser models terminate at the shared `Catalogue` adapter input.

Canonical models remain platform-independent.

Provenance is preserved.

==================================================
CANONICAL INGESTION
==================================================

Phase 2 feeds Phase 1. It does not create a second persistence system.

Phase 1 remains authoritative for:

- stable catalogue UUIDs
- venue_id = org + platform + source-listing identity (not cross-platform restaurant identity)
- identity conflict detection and rollback
- revisions and idempotency
- BEGIN IMMEDIATE + re-check
- SQLite foreign keys
- explicit/idempotent migration (no repeated full backfill on API startup)

==================================================
ADAPTER FAILURE
==================================================

Normal path: Catalogue → `ExistingCatalogueAdapter` → canonical document → existing persistence.

If primary adapter mapping fails, fallback canonical projection from the normalized response is attempted (`to_canonical_from_response`).

If both mappings fail:

- the failure is raised
- the operation does not report canonical success
- canonical persistence is not performed
- pending raw data remains

==================================================
TRANSACTION / CONCURRENCY
==================================================

Scraping, parsing, normalization, validation, raw I/O, and network/image fetch stay outside the database transaction.

Do not scrape, fetch, or hold long normalization work inside the canonical DB lock.

Phase 1 concurrency protections are unchanged.

==================================================
CANCELLATION / CRASH RECOVERY
==================================================

Cancellation: pending raw may remain; persistence is skipped when the ingestion no longer owns the claim; no partial canonical mutation.

Crash: persistence commits before raw binding. A crash between them leaves the canonical row and the pending capture. Raw is not deleted. Retry uses a new capture token. Re-binding an already-moved token is a no-op.

==================================================
SECURITY
==================================================

Preserved:

- organization isolation on raw paths
- sanitized path segments
- no static raw directory
- existing session/org authorization
- existing safe URL fetch / SSRF controls
- no new arbitrary URL fetching for raw capture

Do not expose raw filesystem paths through an unauthenticated endpoint.

==================================================
BACKWARD COMPATIBILITY
==================================================

Legacy catalogue API and existing frontend catalogue behavior remain compatible.

Quality and raw capture identifiers are additive response fields.

==================================================
FINAL TEST RESULTS
==================================================

Backend:

296 passed

Relevant frontend:

78 passed

Python compile checks:

PASS

Phase 2 focused tests:

PASS

Phase 1 regression:

PASS

==================================================
PHASE 2 AUDIT RESULT
==================================================

Correctness: PASS

Race conditions: PASS

Atomicity: PASS

Cancellation: PASS

Crash recovery: PASS

Idempotency: PASS

Security: PASS

Authorization: PASS

SSRF: PASS

Performance: PASS

N+1 queries: PASS

Type safety: PASS

Uncaught errors: PASS

Data integrity: PASS

Transaction safety: PASS

Backward compatibility: PASS

Dead code / unused imports: PASS

Migration safety: PASS

Raw-data preservation: PASS

Scope control: PASS

FINAL RESULT:

PHASE 2 — PASS / CLOSED

==================================================
OUT OF SCOPE
==================================================

Phase 2 did NOT implement:

- Baba Grading Engine, Baba Score, Platform Evaluation, Grade Explanation, Recommendations
- AI Improvement Engine, agents, LLM workflows, AI/NLP, vision, image/video AI, review intelligence
- Baba AI Assistant, chatbot, chat-based catalogue modification, controlled tool execution
- owner approval, re-grading, closed-loop optimization
- dashboard redesign, city-discovery expansion
- fuzzy or cross-platform restaurant/item identity
- replay subsystem, raw database table, janitor, object-storage redesign
- CLI parity redesign

==================================================
PHASE 2 CLOSURE RULE
==================================================

PHASE 2 IS CLOSED.

Future chats MUST treat Phase 2 as an established baseline.

Do not reopen Phase 2 for cosmetic improvements, unrelated debt, speculative refactoring, architecture experiments, or later-phase functionality.

If a future phase requires a change:

1. Identify the exact requirement from that phase's official roadmap.
2. Explain why Phase 2 behavior must change.
3. Preserve Phase 2 guarantees wherever possible.
4. Do not silently reopen Phase 2.

PHASE 3 IS NOT STARTED.

Do not implement Phase 3 until its official roadmap is provided, audited, planned, reviewed, and explicitly approved.

Related records:

- `PHASE1_CLOSURE.md`
- `.cursor/rules/phase1-closed.mdc`
- `.cursor/rules/phase2-closed.mdc`
- `AGENT.md`

END OF PHASE 2 CLOSURE RECORD.
