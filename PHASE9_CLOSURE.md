# Phase 9 — Baba AI Catalogue Assistant
Status: PASS — CLOSED

Official name: Baba AI Catalogue Assistant.

This is the official Phase 9 handoff. Do not make further Phase 9 changes unless a later official phase names a concrete defect or required dependency.

Do not start Phase 10 (apply / mutate / publish) without a later official roadmap.

==================================================
PROJECT PHASE STATUS
==================================================

PHASE 0–8 remain closed / implemented baselines. Phase 9 did not reopen them.

PHASE 9 — PASS / CLOSED

PHASE 10 — NOT STARTED

==================================================
## 1. Purpose
==================================================

Give restaurant owners a read-only Baba AI that can:

explain → retrieve stored facts → recommend next workspace → deep-link

Deterministic services remain the source of truth. Baba does not grade, apply improvements, generate media, or write catalogues.

==================================================
## 2. Runtime path
==================================================

```
User message
  → Baba AI UI (dock or /baba-ai)
  → context { current_route } + session cookie + organization_id
  → POST /catalogues/{id}/assistant/turn   OR   POST /assistant/turn
  → require_session + require_organization_member
  → get_catalogue / list_catalogues (user_id + organization_id)
  → parse_page_context + apply_page_context
  → route_intent (deterministic)
  → optional plan_message (Ollama JSON, extra forbid)
  → execute_tool (allowlisted GET only)
  → explain_turn (templates from tool payloads)
  → actions_for_intent + href_allowed
  → UI renders response.actions[].href only
```

==================================================
## 3. Wiring
==================================================

| Step | Source | Target | File | Function / route | Purpose | Data | Authorization | Status |
|---|---|---|---|---|---|---|---|---|
| Mount dock | Owner pages | Compact chat | `frontend/src/components/baba-ai-dock.tsx` | `BabaAiDock` | Collapsed launcher → compact chat → expand; link to `/baba-ai` | `catalogueId`, `currentRoute` | Session org from `authClient` | implemented |
| Mount global | Sidebar /baba-ai | Workspace | `frontend/src/components/baba-ai-page.tsx` `baba-ai-workspace.tsx` | `BabaAiPage` | Org-wide or selected-venue chat | `selectedId` optional | Same | implemented |
| Compatibility | Old assistant tab | Redirect | `frontend/src/app/(dashboard)/catalogues/[id]/assistant/page.tsx` | redirect `babaAiHref(id)` | Keep `/catalogues/{id}/assistant` | catalogue id | Route gate | implemented |
| Context build | UI | Request body | `frontend/src/lib/catalog-api.ts` | `assistantTurnApi` | Sends `{ message, context: { current_route } }` | route string | N/A (hint) | implemented |
| Next proxy | Browser | API | `frontend/src/app/api/catalogues/[id]/assistant/turn/route.ts` `frontend/src/app/api/assistant/turn/route.ts` | `POST` | Forwards cookie | body passthrough | Cookie | implemented |
| Catalogue turn | HTTP | Service | `backend/main.py` | `POST /catalogues/{catalogue_id}/assistant/turn` | Venue-scoped turn | `AssistantTurnRequest` | `require_session` + `require_organization_member` + `get_catalogue` | implemented |
| Org turn | HTTP | Same service | `backend/main.py` | `POST /assistant/turn` | Org-scoped turn (`catalogue_id=None`) | same | session + org member; tools use `list_catalogues(user, org)` | implemented |
| Orchestration | HTTP | Brain | `backend/assistant/service.py` | `run_turn` | Bind context, route, plan, tools, explain, actions | `TurnCache` | Catalogue 404 if `get_catalogue` misses | implemented |
| Page context | Route hint | Intent | `backend/assistant/context.py` | `parse_page_context`, `apply_page_context` | Deictic “this grade/restaurant” | `PageContext` | Path id cannot override authz; request catalogue wins | implemented |
| Intent | Message | Frozen intent | `backend/assistant/router.py` | `route_intent` | No LLM when phrase matches | `AssistantIntent` | Mutation phrases → `refuse_mutation` | implemented |
| Planner | Unmatched message | JSON | `backend/assistant/planner.py` | `plan_message` | `intent`, `item_name`, `tool` only | `PlannerOutput` extra=forbid | Rejects href / ids / write tools | implemented |
| Tools | Intent | Facts | `backend/assistant/tools.py` | `execute_tool` | Allowlisted GET map | payloads | Same user/org/catalogue as cache | implemented |
| Catalogue retrieval | Tool | Store | `backend/store.py` + tools | `get_catalogue`, `_catalogue_summary` | Name, platform, type, item_count | `StoredCatalogue` | `user_id` + `organization_id` | implemented |
| Grade retrieval | Tool | Phase 5 | `backend/services/grade_explain_service.py` | `get_grade_explanation` | Letter, score, why, findings, item_names from paths | `GradeExplanation` or missing | Same | implemented |
| Review retrieval | Tool | Phase 8 | `backend/review_intel/service.py` | `get_review_intelligence` | Observations, recurrence, stale/missing | `ReviewIntelligence` | Same | implemented |
| Explain | Facts | Copy | `backend/assistant/explain.py` | `explain_turn` | Human language; ungraded honest | templates | N/A | implemented |
| Actions | Intent | hrefs | `backend/assistant/links.py` | `actions_for_intent`, `href_allowed` | Server hrefs only | `AssistantAction` | Prefix `/catalogues/{id}/…` or `/grading/{id}` | implemented |
| UI actions | Response | Next Link | dock + workspace | `actions.map` → `Link href={action.href}` | No client-built URLs | server href | User still subject to page authz | implemented |

==================================================
## 4. Allowlisted tools (GET / read)
==================================================

`get_catalogue_summary`, `get_grade_explanation`, `get_baba_score`, `get_review_intelligence`, `get_item_context`, `list_improvement_proposals`, `list_org_grade_summaries`

Write names (`apply_improvement`, `grade`, `create_media_job`, …) are listed only to reject them.

==================================================
## 5. Deep links
==================================================

Built in `actions_for_intent`:

- View Grade → `/grading/{catalogue_id}`
- Open Grading → `/grading`
- Open Catalogue → `/catalogues/{id}`
- Open AI Improvements → `/catalogues/{id}/improvements` (optional `check_id`)
- Open Generated Media → `/catalogues/{id}/media` (optional `path`)
- View Reviews → `/catalogues/{id}/reviews`

`href_allowed` rejects schemes, hosts, `..`, and query keys other than `path` / `proposal_id` / `check_id` / grading `tab`.

==================================================
## 6. Context fields
==================================================

Passed when available:

- organization: `organization_id` query + session
- catalogue / venue: path `catalogue_id` or selected `/baba-ai?catalogue=`
- current_route: `AssistantClientContext.current_route`
- item: resolved from message against catalogue item refs (not a client-supplied id)
- grade / review / media section: inferred from `current_route` (`/grading/{id}`, `/reviews`, `/media`, `/improvements`)

==================================================
## 7. Graphify
==================================================

Graphify is **not** installed in this repository and is **not** on the Baba runtime path. Phase 9 understanding is this closure document plus `backend/assistant/`. Do not add Graphify to assistant tool execution.

==================================================
## 8. Tests
==================================================

Backend: `tests/test_phase9_assistant.py`

Frontend: Vitest including `catalog-api`, Baba dock, Baba workspace.

TypeScript: `npx tsc --noEmit`
