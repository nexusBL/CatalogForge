# PHASE 1 — OFFICIAL FINAL CLOSURE RECORD

This is the final Phase 1 handoff for future phases.

PHASE 1 STATUS:
PASS — CLOSED

Do NOT make further Phase 1 changes unless a future phase identifies a concrete defect or dependency that requires reopening it.

==================================================
PHASE 1 FINAL ARCHITECTURE
==================================================

Phase 1 established the canonical catalogue model.

Final conceptual flow:

RAW PLATFORM DATA
        ↓
PLATFORM PARSER / ADAPTER
        ↓
CANONICAL MODEL
        ↓
PERSISTENCE
        ↓
LEGACY API PROJECTION
        ↓
EXISTING FRONTEND

Implementation was additive and backward-compatible.

Existing platform scrapers were not unnecessarily rewritten.

==================================================
IDENTITY
==================================================

Catalogue UUID remains stable.

venue_id represents:

organization + platform + source listing identity

venue_id is NOT a cross-platform restaurant identity.

Therefore Swiggy and Zomato listings remain separate canonical venue/listing identities.

No fuzzy matching is used as primary identity.

Source/platform identifiers are retained as provenance.

Menu items have:

- internal item_id
- optional source_item_id

A trustworthy source_item_id provides continuity.

If source_item_id is unavailable, Phase 1 does not manufacture identity using:

- name
- price
- name + price
- array position
- fuzzy matching

==================================================
PROVENANCE
==================================================

Canonical entities preserve source information including, where available:

- platform
- source URL
- source entity ID
- timestamps
- source/platform metadata
- original/raw information required for traceability

Raw/platform information was not unnecessarily destroyed.

==================================================
REVISION / HISTORY
==================================================

Phase 1 uses current state + revision history.

Identical canonical content:

₹100 → ₹100

results in:

- no duplicate canonical entity
- no unnecessary revision

Material change:

₹100 → ₹110

results in:

- same canonical identity
- current state updated
- revision recorded

No event-sourcing architecture was introduced.

==================================================
IDENTITY CONFLICT SAFETY
==================================================

A critical identity-conflict bug was found during independent audit and fixed before closure.

Example:

Existing A:
URL X
source_id 123

Existing B:
URL Y
source_id 456

Incoming:
URL X
source_id 456

Resolution:

URL → A
source_id → B

Final behavior:

- explicit CatalogueIdentityConflict
- application-level error
- HTTP 409 where exposed through catalogue creation API
- transaction rollback
- A unchanged
- B unchanged
- no third catalogue
- no revision
- no venue/source mutation

The UNIQUE constraint is not the primary conflict detector.

Identity resolution occurs before mutation.

==================================================
CONCURRENCY / ATOMICITY
==================================================

Phase 1 preserves:

BEGIN IMMEDIATE
+
identity re-check
+
IntegrityError handling

Concurrent identical ingestion remains safe.

Scraping/network operations are not performed inside DB transactions.

==================================================
RAW VS CANONICAL
==================================================

Phase 1 is additive.

Existing raw/platform information was not prematurely deleted.

Canonical data coexists with the legacy catalogue representation.

The frontend continues using the compatible legacy API representation.

==================================================
DATABASE / MIGRATION
==================================================

Dedicated migration command:

python -m backend.migrate_catalogues

Migration is:

- explicit
- idempotent
- non-destructive
- safe to rerun

Migration state is tracked.

Behavior:

First required migration:
    backfill + indexes

Already applied:
    skip full backfill

Partial:
    preserve data
    retry required index work

API startup does not repeatedly perform the complete catalogue backfill.

Migration work was not moved into _connect().

==================================================
FOREIGN KEYS
==================================================

Application SQLite connections use the shared connection setup with:

PRAGMA foreign_keys = ON

Foreign-key enforcement is tested.

==================================================
BACKWARD COMPATIBILITY
==================================================

Phase 1 preserved existing:

- catalogue UUIDs
- catalogue API behavior
- legacy catalogue JSON
- frontend assumptions
- existing asset/catalogue relationships

Relevant frontend tests remained passing.

==================================================
ADAPTER BOUNDARY
==================================================

Platform-specific parser models remain inputs to the adapter.

The canonical model and persistence layer do not depend on platform-specific persistence types.

The adapter produces canonical structures for persistence.

Existing shared scraper models remain adapter input by design.

No broad scraper rewrite was required.

==================================================
FINAL TEST RESULTS
==================================================

Backend:

280 passed

Relevant frontend:

35 passed

Focused canonical/store:

19 passed

Migration:

5 passed

Foreign keys:

3 passed

Idempotency/concurrency:

11 passed

Python compile checks:

PASS

Phase 1 identity-conflict regression tests:

PASS

==================================================
PHASE 1 AUDIT RESULT
==================================================

Correctness:
PASS

Race conditions:
PASS

Atomicity:
PASS

Idempotency:
PASS

Security:
PASS

Data integrity:
PASS

Migration safety:
PASS

Backward compatibility:
PASS

Dead-code cleanup:
PASS

Performance/N+1:
AUDITED

Type/code quality:
PASS WITH TOOLING LIMITATION

Scope control:
PASS

No Phase 2 functionality was implemented.

==================================================
KNOWN LIMITATIONS — DO NOT AUTOMATICALLY EXPAND
==================================================

These are known Phase 1 limitations and are NOT automatically Phase 2 requirements:

1. venue_id is source-listing identity, not cross-platform restaurant identity.

2. Menu items without trustworthy source_item_id do not have guaranteed cross-rescrape continuity.

3. catalogues.venue_id is not currently a database foreign key.

4. Ruff/Mypy/Pyright are not fully configured in the repository environment.

5. Existing scraper platform models remain adapter inputs.

Future phases may address these only if their official roadmap explicitly requires it.

==================================================
PHASE 1 CLOSURE RULE
==================================================

PHASE 1 IS CLOSED.

Future phases must preserve these guarantees unless their official requirements explicitly require a controlled change.

Do not reopen Phase 1 for cosmetic refactoring.

Do not use Phase 1 limitations as justification for unrelated Phase 2 work.

The official Phase 2 roadmap is the source of truth for Phase 2 scope.

END OF PHASE 1 CLOSURE RECORD.
