"""Rebuild HECTO_BABA_FEATURE_DELIVERY_DOSSIER.xlsx — Founder/PM edition.

Documentation only. Run: python audit_evidence/build_founder_dossier.py
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "HECTO_BABA_FEATURE_DELIVERY_DOSSIER.xlsx"
AUDIT_DATE = "27 August 2026"

# --- Styling ---
NAVY = "1B2A4A"
SLATE = "F4F6F8"
WHITE = "FFFFFF"
THIN = Side(style="thin", color="D0D5DD")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

STATUS_FILLS = {
    "IMPLEMENTED & VERIFIED": "D1FADF",
    "IMPLEMENTED — NEEDS VALIDATION": "FFF3BF",
    "PARTIALLY IMPLEMENTED": "FFE8A3",
    "IMPLEMENTED — NOT WORKING": "FECACA",
    "IN PROGRESS": "DBEAFE",
    "NOT IMPLEMENTED": "E5E7EB",
    "PLANNED": "E9D5FF",
    "BLOCKED": "FECACA",
    "NEEDS MANUAL VERIFICATION": "FFF3BF",
}

HEADER_FONT = Font(name="Calibri", bold=True, color=WHITE, size=11)
TITLE_FONT = Font(name="Calibri", bold=True, size=16, color=NAVY)
SUB_FONT = Font(name="Calibri", size=11, color="475467")
BODY_FONT = Font(name="Calibri", size=10)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def style_header_row(ws, row: int, ncol: int) -> None:
    fill = PatternFill("solid", fgColor=NAVY)
    for c in range(1, ncol + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = HEADER_FONT
        cell.fill = fill
        cell.alignment = CENTER
        cell.border = BORDER


def style_data_rows(ws, start: int, end: int, ncol: int, status_col: int | None = None) -> None:
    alt = PatternFill("solid", fgColor=SLATE)
    for r in range(start, end + 1):
        for c in range(1, ncol + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = BODY_FONT
            cell.alignment = WRAP
            cell.border = BORDER
            if r % 2 == 0:
                cell.fill = alt
        if status_col:
            val = str(ws.cell(row=r, column=status_col).value or "")
            for key, color in STATUS_FILLS.items():
                if key in val:
                    ws.cell(row=r, column=status_col).fill = PatternFill("solid", fgColor=color)
                    break


def set_col_widths(ws, widths: dict[int, float]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def add_table(ws, name: str, ref: str) -> None:
    tab = Table(displayName=name.replace(" ", "_").replace("/", "_")[:255], ref=ref)
    tab.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    ws.add_table(tab)


def write_rows(ws, headers: list[str], rows: list[list], status_col: int | None = None) -> int:
    ws.append(headers)
    style_header_row(ws, 1, len(headers))
    for row in rows:
        ws.append(row)
    end = len(rows) + 1
    style_data_rows(ws, 2, end, len(headers), status_col)
    ws.freeze_panes = "A2"
    last_col = get_column_letter(len(headers))
    add_table(ws, ws.title, f"A1:{last_col}{end}")
    return end


# --- Feature data (verified from repository audit) ---
FEATURES = [
    # Feature ID, Module, Feature, What We Built, How It Works, Technology, Logic, Status, Work Remaining
    ["HB-AUTH-01", "Authentication", "Username & password login", "Sign-in with username and password via Better Auth.", "User submits credentials on login page → Better Auth validates → session cookie stored → dashboard unlocked.", "Next.js login form; Better Auth Node; session cookie proxy.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-AUTH-02", "Authentication", "Sign up with username", "New account registration requires username, email, and password.", "Signup page → Better Auth sign-up hook enforces username → user record in auth SQLite.", "Better Auth username plugin; auth/data/better-auth.sqlite.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-AUTH-03", "Authentication", "Email OTP sign-in", "UI and backend plugin for email one-time password login.", "User enters email → sendVerificationOtp → user enters code → signIn.emailOtp. Delivery requires SMTP or AUTH_OTP_LOG=true.", "Better Auth emailOTP plugin; nodemailer in auth/auth.ts.", "Deterministic", "IMPLEMENTED — NOT WORKING", "Configure SMTP or fix delivery; verify end-to-end OTP in production."],
    ["HB-AUTH-04", "Authentication", "Session-protected APIs", "All catalogue APIs require a valid Better Auth session.", "FastAPI require_session reads cookie via GET /api/auth/get-session; 401 if missing.", "backend/session.py; frontend API proxies.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-AUTH-05", "Authentication", "Organization membership gate", "Every catalogue action is scoped to a restaurant organization.", "Frontend OrganizationGate; backend require_organization_member on all catalogue routes.", "Better Auth organization plugin; backend/authz.py.", "Deterministic", "IMPLEMENTED & VERIFIED", "Multi-org switcher not built; first org only."],
    ["HB-NAV-01", "Navigation", "Overview dashboard", "Landing page after login showing catalogue metrics and recent catalogues.", "GET /catalogues (compact) → overview stats cards and catalogue cards.", "frontend/.../overview/page.tsx; list_catalogues.", "Deterministic", "IMPLEMENTED & VERIFIED", "Not the Phase 13 operator dashboard (planned separately)."],
    ["HB-NAV-02", "Navigation", "Side navigation", "Persistent nav for platforms, catalogues, grading, Baba AI, areas.", "Side nav builds hrefs from platform and catalogue type helpers.", "frontend/src/components/nav/side-nav/", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-NAV-03", "Navigation", "Restaurant domain list", "Lists restaurant-type catalogues by platform.", "Filters catalogue list for restaurant menus.", "frontend/.../restaurant/page.tsx", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-NAV-04", "Navigation", "Dineout domain list", "Lists dineout-type catalogues and venue views.", "Filters for dineout payloads and venue metadata.", "frontend/.../dineout/page.tsx; dineout-venue-view.tsx", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-CAT-01", "Catalogue", "Single-venue catalogue creation", "Create one restaurant or dineout catalogue from a platform URL.", "Create Catalogue form → POST /catalog/create → scrape → normalize → save → show summary.", "create-catalogue-form.tsx; catalog_service.create_catalog; store.save_catalogue.", "Deterministic", "IMPLEMENTED — NEEDS VALIDATION", "Live scrape depends on Chrome/CDP and platform WAF; validate in production browser."],
    ["HB-CAT-02", "Catalogue", "Platform selection", "Supports Swiggy, Zomato, and Magicpin source URLs.", "Platform inferred from URL; platform-specific parser after shared browser collect.", "scraper/platform.py; catalog_service._create_platform_catalog.", "Deterministic", "IMPLEMENTED & VERIFIED", "Official Swiggy API mode is stub (pending)."],
    ["HB-CAT-03", "Catalogue", "Catalogue type selection", "Restaurant menu, Dineout venue, or Both.", "Query params on /catalogues/new; backend validates restaurant vs dineout completeness.", "nav-catalogues.ts; catalog_service branching.", "Deterministic", "IMPLEMENTED & VERIFIED", "Both type may need separate dineout_url."],
    ["HB-CAT-04", "Catalogue", "Create progress & errors", "Shows scraping progress and actionable failure messages.", "Indeterminate progress while loading; extracts backend error detail via extractErrorMessage.", "process-progress.tsx; catalog-api.ts.", "Deterministic", "IMPLEMENTED & VERIFIED", "Partial scrape status in schema but parsers do not emit partial yet."],
    ["HB-CAT-05", "Catalogue", "Catalogue deletion", "Owner can delete a catalogue and related rows.", "DELETE /catalogues/{id} cascades grades, media, reviews, assets.", "store.delete_catalogue; tests/test_deletion.py.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-VIEW-01", "Catalogue", "Catalogue detail view", "Browse categories, items, prices, descriptions, and product images.", "GET /catalogues/{id} → catalogue-view renders menus and items.", "catalogue-view.tsx; catalogue-menu.ts.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-VIEW-02", "Catalogue", "Dineout venue display", "Photos, offers, gallery, and venue info for dineout catalogues.", "Dineout sections in catalogue and domain pages.", "dineout-venue-view.tsx", "Deterministic", "IMPLEMENTED & VERIFIED", "Gallery completeness varies by platform scrape."],
    ["HB-VIEW-03", "Catalogue", "Hero image → Media Studio", "Restaurant hero image is the entry point for hero editing.", "Hero click routes to media studio with venue image path.", "catalogue-view.tsx; media service venue workspace.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-GRADE-01", "Grading", "Baba grading engine", "Letter grade A–F from deterministic, NLP heuristic, and local vision stages.", "POST /grade → grading.v1 orchestrator → persisted grade row for revision.", "backend/grading/; tests/test_phase3_grading.py.", "Hybrid (no external AI)", "IMPLEMENTED & VERIFIED", "Formula frozen in grading.v1."],
    ["HB-GRADE-02", "Grading", "Grade explanation", "Human-readable findings and fix-first recommendations.", "GET /grade-explanation projects stored grade to grade_explain.v1.", "grade_explain_service; grade-explanation-view.tsx.", "Deterministic", "IMPLEMENTED & VERIFIED", "404 if catalogue not yet graded."],
    ["HB-GRADE-03", "Grading", "Baba Score", "Read-only score from stored grade (not platform ratings).", "GET /baba-score loads projection from grade row.", "platform_eval/baba_score.py.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-GRADE-04", "Grading", "Platform evaluation", "Swiggy/Zomato/Magicpin evidence adapters from ingested catalogue.", "POST/GET platform-evaluation; no live platform HTTP.", "platform_eval_service; registry adapters.", "Deterministic", "IMPLEMENTED & VERIFIED", "Score calibration deferred."],
    ["HB-IMP-01", "AI Improvements", "Generate improvement proposals", "AI suggests description, tags, category name, price copy, or media handoff.", "POST /improvements → Ollama or deterministic → validate → proposal row READY/FAILED.", "improvement/service.py; validate.py; Ollama llama3.", "Hybrid", "IMPLEMENTED — NEEDS VALIDATION", "Requires local Ollama for text proposals; verify per-field in browser."],
    ["HB-IMP-02", "AI Improvements", "Apply / cancel proposals", "Owner explicitly applies or cancels; live catalogue unchanged until apply.", "POST apply/cancel → apply_improvement → optional re-grade → history.", "improvement/apply.py; Phase 11 closure.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-IMP-03", "AI Improvements", "Single-item single-field targeting", "One Improve with AI click targets exactly one item and one field.", "requested_paths length 1 → resolve_targets must return 1 target.", "eligibility.py enforcement.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-IMP-04", "AI Improvements", "Edit history & rollback", "Append-only history; owner rollback with confirm.", "GET history; POST rollback with confirm:true.", "history/service.py; edit-history-panel.tsx.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-MEDIA-01", "Media", "Media Studio workspace", "Per-item and hero image workspace with job preview.", "GET media-studio; create media jobs; preview artifacts.", "media-studio-view.tsx; media/service.py.", "Deterministic", "IMPLEMENTED & VERIFIED", "Preview until owner applies."],
    ["HB-MEDIA-02", "Media", "Image operations (local default)", "Enhance, crop, expand, blur, background, edit, cleanup, generate, GIF.", "Pillow local.v1 transforms; optional hosted HTTP if env configured.", "backend/media/providers.py; routing.py.", "Hybrid (hosted optional)", "PARTIALLY IMPLEMENTED", "Local path is filter/composition not true AI segmentation."],
    ["HB-MEDIA-03", "Media", "Apply media to catalogue", "Owner applies approved media job to live catalogue image URL.", "POST media-jobs/{id}/apply → catalogue-assets → payload update → re-grade.", "apply_media_job in media/service.py.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-AI-01", "Assistant", "Baba AI chat", "Org-level and catalogue-scoped assistant with read-only tools.", "POST assistant/turn → deterministic router → optional Ollama planner → tool calls.", "assistant/service.py; router.py; planner.py.", "Hybrid", "IMPLEMENTED & VERIFIED", "Ollama optional; max 3 tools per turn."],
    ["HB-AI-02", "Assistant", "Typed catalogue mutations", "Natural language propose → confirm → apply for allowlisted edits.", "Mutation proposal row → owner confirm/cancel → patch catalogue.", "mutation/service.py; baba-mutation-confirm.tsx.", "Hybrid", "IMPLEMENTED & VERIFIED", "15-minute proposal TTL."],
    ["HB-AI-03", "Assistant", "Read-only tool boundary", "Chat cannot apply improvements, grade, or publish directly.", "WRITE_TOOL_NAMES refused; server builds action hrefs only.", "assistant contract Phase 9.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
    ["HB-REV-01", "Reviews", "Customer feedback submit", "Session-authenticated diners submit written feedback (+ optional photo).", "POST customer-feedback → stored with opaque author_key.", "review_intel/service.py.", "Deterministic", "IMPLEMENTED & VERIFIED", "No guest/anonymous submit in V1."],
    ["HB-REV-02", "Reviews", "Review intelligence", "Aspect/target analysis and recommendations (inspect-only).", "POST/GET review-intelligence; engine review_intel.v1.1.", "review_intel/analyze.py.", "Deterministic", "IMPLEMENTED & VERIFIED", "Never writes catalogue payload."],
    ["HB-REV-03", "Reviews", "Operator review collect", "Owner pastes supplied reviews for analysis.", "POST reviews/collect source=supplied.", "Phase 8 contract.", "Deterministic", "IMPLEMENTED & VERIFIED", "No third-party review scrape."],
    ["HB-AREA-01", "Area jobs", "City / area discovery", "Discover multiple venues in a city/area for batch catalogue creation.", "POST area-jobs → discovery adapters → job payload.", "area_service; scraper/discovery/.", "Deterministic", "IMPLEMENTED — NEEDS VALIDATION", "Validate discovery on live platforms."],
    ["HB-AREA-02", "Area jobs", "Batch area scraping", "Poll-based batch scrape of selected venues.", "start → scrape-batch loop; CAS claims.", "area-jobs API; test_area_scrape_claim.", "Deterministic", "IMPLEMENTED & VERIFIED", "Single Uvicorn worker assumption."],
    ["HB-ACC-01", "Account", "Profile page", "Local profile fields and avatar stored client-side.", "Profile page uses localStorage via account-profile.ts.", "frontend profile page.", "Deterministic", "PARTIALLY IMPLEMENTED", "Not persisted server-side."],
    ["HB-ACC-02", "Account", "Settings", "Password change and notification prefs UI.", "Settings page; notification prefs localStorage.", "settings/page.tsx.", "Deterministic", "PARTIALLY IMPLEMENTED", "Notification prefs not on server."],
    ["HB-ACC-03", "Account", "Theme toggle", "Light/dark mode.", "next-themes provider.", "theme-toggle.tsx.", "Deterministic", "IMPLEMENTED & VERIFIED", "None"],
]

FEATURE_DETAILS = [
    ["HB-CAT-01", "Single-venue catalogue creation", "Ingest a restaurant or dineout menu from Swiggy/Zomato/Magicpin into a structured catalogue.", "Overview → Create Catalogue → choose platform/type → enter URL + FSSAI → Create → processing → catalogue summary", "Frontend POST proxy → FastAPI catalog_create → create_catalog → BrowserAccess collect → parse → normalize → validate → canonical save → materialize images", "create-catalogue-form.tsx", "backend/main.py catalog_create; catalog_service.py", "POST /catalog/create", "catalogues, venues, venue_sources, catalogue_revisions", "None (scrape)", "validate_catalogue; identity conflict 409", "IMPLEMENTED — NEEDS VALIDATION", "Live WAF/Chrome failures; partial status unused", "frontend/src/app/(dashboard)/catalogues/new/page.tsx; backend/services/catalog_service.py"],
    ["HB-AUTH-03", "Email OTP sign-in", "Passwordless login via email code.", "Login → Sign in with Email OTP → Send OTP → enter code → Sign In", "Better Auth emailOTP plugin; sendOtpEmail throws if no SMTP and AUTH_OTP_LOG not true", "login-form.tsx", "auth/auth.ts sendOtpEmail", "POST /api/auth/email-otp/* (proxied)", "Better Auth SQLite OTP tables", "None", "None", "IMPLEMENTED — NOT WORKING", "Production email delivery not verified", "auth/auth.ts; frontend/src/components/login-form.tsx"],
    ["HB-IMP-01", "AI improvement proposals", "Suggest grounded copy/tags without mutating live catalogue.", "Improvements page → Improve with AI on one field → proposal card → Replace with this", "create_improvement → resolve_targets → Ollama generate → validate → persist proposal", "ai-improvements-view.tsx; item-quality-board.tsx", "improvement/service.py", "POST /catalogues/{id}/improvements", "catalogue_improvement_proposals", "Ollama llama3:latest @ 127.0.0.1:11434", "validate.py; CandidateRejected", "IMPLEMENTED — NEEDS VALIDATION", "Ollama must be running locally", "backend/improvement/"],
    ["HB-MEDIA-02", "Image operations", "Preview image edits before applying to catalogue.", "Catalogue → Media → select item → choose tool → Generate → Apply live", "create_media_job → LocalMediaProvider Pillow ops → artifact → owner apply", "media-studio-view.tsx", "media/service.py; providers.py", "POST /catalogues/{id}/media-jobs", "catalogue_media_jobs, catalogue_media_artifacts", "local.v1 Pillow; optional hosted FLUX/SVD", "prompt validation; preview≠payload until apply", "PARTIALLY IMPLEMENTED", "Background removal is ellipse mask not ML", "backend/media/providers.py"],
    ["HB-AI-01", "Baba AI assistant", "Answer questions and navigate using stored catalogue/grade data.", "Baba AI page or dock → user message → response + optional action links", "run_turn → router (deterministic) → optional Ollama planner JSON → allowlisted GET tools", "baba-ai-page.tsx; baba-ai-dock.tsx", "assistant/service.py", "POST /assistant/turn; POST /catalogues/{id}/assistant/turn", "None (read-only)", "Ollama optional for planner", "extra=forbid planner schema; tool allowlist", "IMPLEMENTED & VERIFIED", "Cannot apply via chat tools", "backend/assistant/"],
    ["HB-GRADE-01", "Baba grading", "Quality letter grade for catalogue revision.", "Catalogue saved → Grade run → letter + findings", "grade_catalogue → deterministic + NLP + vision → grading.v1 persist", "grading views", "grading_service.py", "POST/GET /catalogues/{id}/grade", "catalogue_grades, catalogue_grade_jobs", "None", "CAS claim_token", "IMPLEMENTED & VERIFIED", "Hard failures force F", "backend/grading/"],
]

SCRAPING_PIPELINE = [
    ["1", "User input", "Owner provides platform URL, restaurant name, FSSAI, org, catalogue type.", "Deterministic", "CreateCatalogueForm fields", "CatalogCreateRequest JSON", "Form validation", "IMPLEMENTED & VERIFIED", "frontend/.../create-catalogue-form.tsx; backend/schemas.py"],
    ["2", "API request", "Frontend proxies to FastAPI with session cookie.", "Deterministic", "Next.js API route", "HTTP POST /catalog/create", "require_session + require_organization_member", "IMPLEMENTED & VERIFIED", "frontend/src/app/api/catalog/create/route.ts"],
    ["3", "Platform routing", "Select Swiggy/Zomato/Magicpin handler.", "Deterministic", "infer_legacy_platform", "CatalogCreateRequest", "CatalogCreateResponse shell", "IMPLEMENTED & VERIFIED", "backend/services/catalog_service.py create_catalog"],
    ["4", "Browser collection", "Load page via Chrome CDP / Playwright; capture XHR JSON + DOM.", "Deterministic", "Playwright connect_over_cdp; collect_swiggy_source (shared)", "URL", "RawSource (HTML, JSON payloads, dom_menu)", "IMPLEMENTED — NEEDS VALIDATION", "scraper/swiggy/scraper.py; chrome_session.py"],
    ["5", "Platform parse", "Extract restaurant, categories, items, prices, descriptions, images.", "Deterministic", "parse_swiggy/zomato/magicpin_catalogue", "RawSource", "Parsed catalogue model", "IMPLEMENTED & VERIFIED", "scraper/*/parser.py"],
    ["6", "Follow-up URLs", "Zomato/Magicpin may fetch order/delivery/photos pages.", "Deterministic", "catalog_service _follow_extra", "Primary parse", "Merged catalogue", "IMPLEMENTED & VERIFIED", "catalog_service._create_platform_catalog"],
    ["7", "Normalize", "Clean prices, labels, image URLs; drop junk assets.", "Deterministic", "normalize_catalogue", "Raw categories/items", "Normalized structures", "IMPLEMENTED & VERIFIED", "backend/catalogue_normalize.py"],
    ["8", "Validate quality", "Record quality issues (does not fail extraction alone).", "Deterministic", "validate_catalogue", "Normalized catalogue", "quality.issues[]", "IMPLEMENTED & VERIFIED", "backend/catalogue_validate.py"],
    ["9", "Canonical convert", "Map to canonical document + identity.", "Deterministic", "ExistingCatalogueAdapter.to_canonical", "CatalogCreateResponse", "CanonicalDocument", "IMPLEMENTED & VERIFIED", "backend/canonical/adapter.py"],
    ["10", "Persist", "Save SQLite row; revision snapshot; bind raw capture.", "Deterministic", "save_catalogue; bind_raw_capture", "Canonical + response", "catalogue_id", "IMPLEMENTED & VERIFIED", "backend/store.py; raw_capture.py"],
    ["11", "Image materialize", "Download remote images to catalogue-assets.", "Deterministic", "materialize_catalogue_images", "image URLs", "Local asset paths", "IMPLEMENTED & VERIFIED", "scraper/swiggy/assets.py"],
    ["12", "Status & UI", "Return extraction_status ok/blocked/failed; show summary or error.", "Deterministic", "CatalogCreateResponse", "Backend status + error", "UI summary card", "IMPLEMENTED — NEEDS VALIDATION", "WAF → blocked; partial status not emitted by parsers"],
]

AI_FEATURES = [
    ["Description improvement", "Generate grounded item description", "Improve with AI on Description", "Ollama llama3:latest", "Local 127.0.0.1:11434", "None (HTTP generate)", "TrustedItemContext from catalogue", "proposed_value text", "validate_candidate rejects hallucination", "Owner apply via improvements API", "IMPLEMENTED — NEEDS VALIDATION"],
    ["Tags / labels improvement", "Generate grounded tags; preserve food_type e.g. veg", "Improve with AI on Tags", "Ollama llama3:latest", "Local", "None", "Item name, food_type, existing labels", "proposed_labels[]", "validate_labels; merge canonical food_type first", "Owner apply", "IMPLEMENTED — NEEDS VALIDATION"],
    ["Category name improvement", "Suggest category name fixes", "Bulk or targeted improvement", "Ollama llama3:latest", "Local", "None", "Category context", "proposed_value", "Allowlisted kind only", "Owner apply", "IMPLEMENTED & VERIFIED"],
    ["Item price handoff", "Copy trusted original_price only", "Improve with AI on Price", "None", "N/A", "None", "original_price field", "Numeric copy", "LLM never invents price", "Owner apply", "IMPLEMENTED & VERIFIED"],
    ["Media handoff", "Route missing image to Media Studio", "Improve with AI on Image", "None", "N/A", "None", "Vision finding", "Handoff record", "No image generation in improvement apply", "Owner uses Media Studio", "IMPLEMENTED & VERIFIED"],
    ["Baba AI planner", "Optional JSON plan for tool calls", "Chat message", "Ollama llama3:latest", "Local 30s timeout", "Allowlisted GET tools only", "Route + catalogue context", "Structured plan + narrative", "Deterministic router first; extra=forbid", "No direct mutation", "IMPLEMENTED & VERIFIED"],
    ["NL catalogue mutations", "Propose typed edits from chat", "Confirm mutation card", "Ollama + parsers", "Local", "mutation parse/resolve", "Catalogue snapshot", "MutationProposal", "patch validation", "Owner confirm", "IMPLEMENTED & VERIFIED"],
    ["Grading NLP stage", "Heuristic text quality signals", "Automatic on grade", "None", "N/A", "None", "Item text", "Stage score evidence", "Local heuristics only", "Automatic", "IMPLEMENTED & VERIFIED"],
    ["Review intelligence", "Aspect polarity and recurrence", "Run analysis", "None", "N/A", "None", "Stored reviews", "review_intel.v1.1", "Rule-based", "Inspect-only", "IMPLEMENTED & VERIFIED"],
    ["Media prompt assist", "Suggest edit prompt text", "Empty prompt in studio", "None", "N/A", "None", "Item metadata", "Prompt string", "Template/heuristic not LLM", "N/A", "IMPLEMENTED & VERIFIED"],
]

IMAGE_OPS = [
    ["Enhance", "Item or hero image bytes", "FULL IMAGE", "FULL IMAGE", "Contrast/sharpness/brightness boost + prompt regex tweaks", "Pillow local.v1", "None", "Whole image pixels", "Entire frame", "IMPLEMENTED & VERIFIED", "Not neural enhance unless hosted configured"],
    ["Blur", "Image bytes", "FULL IMAGE", "FULL IMAGE", "Gaussian blur radius", "Pillow", "None", "Whole image", "Entire frame", "IMPLEMENTED & VERIFIED", "None"],
    ["Crop", "Image bytes", "FULL IMAGE", "FULL IMAGE", "Percentage box crop default 10–90%", "Pillow", "None", "Cropped region kept", "Outside crop discarded", "IMPLEMENTED & VERIFIED", "UI aspect presets not sent to API by default"],
    ["Expand", "Image bytes", "FULL IMAGE", "FULL IMAGE", "Pad with mean border color", "Pillow", "None", "Larger canvas", "Original center content", "IMPLEMENTED & VERIFIED", "Not true outpainting locally"],
    ["Background removal", "Image bytes", "FAKE SUBJECT (ellipse)", "FULL IMAGE mask", "Centered ellipse alpha; not ML segmentation", "Pillow _fake_cutout", "None", "Alpha channel", "No real subject isolation", "PARTIALLY IMPLEMENTED", "UI implies AI isolation; local is fake cutout"],
    ["Background generation", "Image bytes", "BACKGROUND", "SUBJECT ellipse + flat bg", "Composite on cream RGBA", "Pillow / optional hosted", "Optional FLUX if hosted URL set", "Background pixels", "Ellipse subject preserved", "PARTIALLY IMPLEMENTED", "Hosted optional; local is flat color"],
    ["Edit / Cleanup", "Image bytes", "FULL IMAGE", "FULL IMAGE", "Filters + mild adjustments", "Pillow", "None", "Whole image", "Entire frame", "PARTIALLY IMPLEMENTED", "UI claims dish-only edit; local edits full frame"],
    ["Generate missing image", "Item context + refs", "FULL IMAGE", "FULL IMAGE", "Compose plate from text/refs", "Pillow compose / optional hosted", "Optional FLUX", "New PNG", "N/A", "PARTIALLY IMPLEMENTED", "Placeholder composition locally"],
    ["GIF / image-to-video", "Image bytes", "FULL IMAGE", "FULL IMAGE", "12-frame zoom animation", "Pillow GIF", "None", "Animated GIF", "Not AI video", "IMPLEMENTED & VERIFIED", "Routing forces local GIF not SVD"],
    ["Face-only edit", "N/A", "NOT IMPLEMENTED", "NOT IMPLEMENTED", "No face detection in codebase", "—", "—", "—", "—", "NOT IMPLEMENTED", "Planned: none"],
    ["Subject-only edit", "N/A", "NOT IMPLEMENTED", "NOT IMPLEMENTED", "No subject segmentation", "—", "—", "—", "—", "NOT IMPLEMENTED", "Ellipse is not subject detection"],
    ["Object-only edit", "N/A", "NOT IMPLEMENTED", "NOT IMPLEMENTED", "No object mask pipeline", "—", "—", "—", "—", "NOT IMPLEMENTED", "—"],
]

TECH_STACK = [
    ["Frontend", "Next.js 15.0.6", "App Router pages and API proxies", "Web UI and same-origin session cookies"],
    ["Frontend", "React 19 RC", "Components", "Interactive catalogue and AI UI"],
    ["Frontend", "TypeScript", "All frontend source", "Type safety"],
    ["Frontend", "Tailwind CSS + Radix/shadcn", "UI components", "Consistent design system"],
    ["Frontend", "Vitest", "frontend/src/**/*.test.ts(x)", "Unit/component tests"],
    ["Backend", "FastAPI + Uvicorn", "backend/main.py", "REST API for catalogues, grading, AI, media"],
    ["Backend", "Python 3", "backend/, scraper/, tests/", "Business logic and scraping"],
    ["Backend", "Pytest", "tests/", "Backend integration and contract tests"],
    ["Database", "SQLite", "data/catalogues.sqlite", "Catalogues, grades, proposals, media, reviews"],
    ["Database", "Raw SQL via store.py", "backend/store.py", "No ORM; explicit migrations"],
    ["Auth", "Better Auth (Node)", "auth/auth.ts", "Login, OTP plugin, organizations"],
    ["Auth", "better-sqlite3", "auth/data/better-auth.sqlite", "Users and sessions"],
    ["Scraping", "Playwright + Chrome CDP", "scraper/swiggy/scraper.py", "Live menu page collection"],
    ["Scraping", "Platform parsers", "scraper/swiggy|zomato|magicpin/", "Structured menu extraction"],
    ["AI text", "Ollama llama3:latest", "backend/improvement/generators/ollama.py", "Improvement and assistant planner"],
    ["AI validation", "Python validators", "backend/improvement/validate.py", "Grounding and security gate"],
    ["Grading vision", "Pillow heuristics", "backend/grading/vision.py", "Local image quality signals"],
    ["Media", "Pillow local.v1", "backend/media/providers.py", "Default image transforms"],
    ["Media optional", "Hosted HTTP / Gradio FLUX", "backend/media/hosted.py", "Optional generative edit if configured"],
    ["Storage", "Filesystem catalogue-assets", "data/catalogue-assets/", "Persisted product and applied images"],
    ["Deployment", "Local dev processes", "README: uvicorn + npm dev + auth server", "No bundled production deploy manifest in repo"],
]

WORK_REMAINING = [
    ["WR-001", "Email OTP", "IMPLEMENTED — NOT WORKING", "Configure SMTP (or AUTH_OTP_LOG for dev); test send OTP and sign-in end-to-end", "High", "Open", "auth/auth.ts throws without SMTP or AUTH_OTP_LOG"],
    ["WR-002", "Live scraping reliability", "IMPLEMENTED — NEEDS VALIDATION", "Validate Swiggy/Zomato/Magicpin under WAF; document blocked vs failed; Chrome CDP ops runbook", "High", "Open", "WAF and chrome port conflicts observed"],
    ["WR-003", "Partial scrape status", "PARTIALLY IMPLEMENTED", "Emit extraction_status=partial when some items fail but menu usable", "Medium", "Open", "Schema/UI accept partial; parsers never set it"],
    ["WR-004", "Media studio fidelity", "PARTIALLY IMPLEMENTED", "Align UI copy with local Pillow limits OR enable hosted segmentation", "Medium", "Open", "Background removal is ellipse not ML"],
    ["WR-005", "Phase 13 dashboard", "NOT IMPLEMENTED", "Product decision on operator dashboard scope", "Low", "Planned", "Referenced in phase rules only"],
    ["WR-006", "Official Swiggy API", "NOT IMPLEMENTED", "Partner credentials for OfficialApiAccess", "Low", "Blocked", "Returns pending today"],
    ["WR-007", "Profile server persistence", "PARTIALLY IMPLEMENTED", "Persist profile/settings server-side if required", "Low", "Open", "localStorage only today"],
    ["WR-008", "Multi-organization UI", "PARTIALLY IMPLEMENTED", "Org switcher if customers have multiple restaurants", "Low", "Open", "Nav uses first org only"],
    ["WR-009", "Production deployment", "NEEDS MANUAL VERIFICATION", "Document/hosting for auth + API + Ollama + Chrome scrape", "High", "Open", "Local dev documented in README"],
    ["WR-010", "Authenticated UI regression pass", "NEEDS MANUAL VERIFICATION", "Founder browser checklist: create → grade → improve → apply → media", "High", "Open", "Unit tests pass; live OTP and scrape need manual pass"],
]

ISSUES = [
    ["BUG-001", "Email OTP", "OTP email not delivered to users", "User receives code and can sign in", "Flow fails without SMTP or dev log flag", "Blocks passwordless login", "High", "Open", "See WR-001"],
    ["BUG-002", "Scraping", "Generic or blocked scrape failures in browser", "Actionable error or partial catalogue", "WAF blocked or Chrome busy errors", "Blocks catalogue creation", "High", "Open", "Improve operator messaging; validate CDP"],
    ["BUG-003", "Media UI", "AI Backgrounds implies segmentation", "True subject isolation", "Ellipse mask only locally", "Misleading preview expectations", "Medium", "Open", "Copy vs capability mismatch"],
    ["BUG-004", "Extraction partial", "partial status never emitted", "PARTIAL when some items fail", "Only ok/blocked/failed from parsers", "Usable data may be marked failed", "Medium", "Open", "See WR-003"],
]

PHASE_HISTORY = [
    ["0", "Foundation", "Project scaffold, auth proxy, initial UI", "CLOSED", "Baseline", "Do not reopen without defect"],
    ["1", "Canonical catalogue", "Stable UUID, venue identity, revisions", "CLOSED", "PHASE1_CLOSURE.md", "Identity conflict → 409"],
    ["2", "Ingestion & normalization", "Scrape adapters, raw capture, normalize", "CLOSED", "PHASE2_CLOSURE.md", "No second persistence path"],
    ["3", "Baba grading engine", "grading.v1, CAS grades", "CLOSED", "PHASE3_CLOSURE.md", "Formula frozen"],
    ["4", "Platform evaluation", "Baba Score vs platform evidence", "CLOSED", "PHASE4_CLOSURE.md", "No live platform HTTP"],
    ["5", "Grade explanation", "grade_explain.v1 projections", "CLOSED", "PHASE5_CLOSURE.md", "Read-time only"],
    ["6", "AI improvement preview", "Ollama proposals, validation", "CLOSED", "PHASE6_CLOSURE.md", "Preview only in Phase 6"],
    ["7", "Media studio", "Media jobs, local Pillow, optional hosted", "Implemented", "No PHASE7_CLOSURE.md", "Preview until apply"],
    ["8", "Review intelligence", "Customer feedback + analysis", "CLOSED", "PHASE8_CLOSURE.md", "No third-party scrape"],
    ["9", "Baba AI assistant", "Read-only tools, router", "CLOSED", "PHASE9_CLOSURE.md", "No apply via chat"],
    ["10", "Typed mutations", "Propose → confirm → apply", "CLOSED", "PHASE10_FINAL_HARDENING_AUDIT.md", "Separate from Phase 6 apply"],
    ["11", "Improvement apply + history", "Owner apply, media apply, rollback", "CLOSED", "PHASE11_FINAL_AUDIT.md", "Terminal proposal states"],
    ["12", "NL refine + closed loop", "Refinement, compare, re-grade snapshots", "CLOSED", "PHASE12_AI_CATALOGUE_REFINEMENT_AUDIT.md", "—"],
    ["13", "Operator dashboard", "Not started", "NOT IMPLEMENTED", "Roadmap only", "Future product decision"],
]

USER_JOURNEY = [
    ["1", "Login", "Enter username/password or OTP", "Better Auth session created", "Redirect to /overview", "IMPLEMENTED & VERIFIED"],
    ["2", "Overview", "View metrics and catalogues", "Load compact catalogue list", "Dashboard cards", "IMPLEMENTED & VERIFIED"],
    ["3", "Create Catalogue", "Choose Single Venue", "Navigate to /catalogues/new", "Create form", "IMPLEMENTED & VERIFIED"],
    ["4", "Venue input", "URL, name, FSSAI, platform, type", "POST /catalog/create", "Processing UI", "IMPLEMENTED — NEEDS VALIDATION"],
    ["5", "Scraping", "Wait for extraction", "Browser collect + parse + save", "Catalogue summary or error", "IMPLEMENTED — NEEDS VALIDATION"],
    ["6", "Catalogue view", "Browse menu", "GET catalogue", "Categories and items", "IMPLEMENTED & VERIFIED"],
    ["7", "Grading", "Run or view Baba grade", "POST/GET grade + explanation", "Letter grades and findings", "IMPLEMENTED & VERIFIED"],
    ["8", "AI Improvements", "Improve with AI per field", "Proposal generated (not live change)", "Proposal card", "IMPLEMENTED — NEEDS VALIDATION"],
    ["9", "Approval", "Replace with this / Apply", "apply_improvement mutates payload", "Live catalogue updated", "IMPLEMENTED & VERIFIED"],
    ["10", "Media Studio", "Edit images", "Media job preview → apply", "Updated image URLs", "PARTIALLY IMPLEMENTED"],
    ["11", "Baba AI", "Ask questions or propose edits", "Tools read data; mutations need confirm", "Chat response + actions", "IMPLEMENTED & VERIFIED"],
    ["12", "Reviews", "Collect/analyze feedback", "Review intel analysis", "Recommendations inspect-only", "IMPLEMENTED & VERIFIED"],
    ["13", "Area jobs", "Discover/scrape many venues", "Area job batch loop", "Multiple catalogues", "IMPLEMENTED — NEEDS VALIDATION"],
]


def build() -> None:
    wb = Workbook()
    wb.remove(wb.active)

    # --- Sheet 1: Executive Summary ---
    ws = wb.create_sheet("EXECUTIVE SUMMARY")
    ws["A1"] = "Hecto Baba"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Feature Delivery & Implementation Summary"
    ws["A2"].font = SUB_FONT
    ws["A3"] = f"Audit Date: {AUDIT_DATE}"
    ws["A3"].font = SUB_FONT

    verified = sum(1 for f in FEATURES if f[7] == "IMPLEMENTED & VERIFIED")
    needs_val = sum(1 for f in FEATURES if "NEEDS VALIDATION" in f[7] or f[7] == "NEEDS MANUAL VERIFICATION")
    partial = sum(1 for f in FEATURES if "PARTIALLY" in f[7])
    not_working = sum(1 for f in FEATURES if "NOT WORKING" in f[7])
    ai_count = sum(1 for f in FEATURES if "Hybrid" in f[6] or f[1] in ("AI Improvements", "Assistant"))
    media_count = sum(1 for f in FEATURES if f[1] == "Media")

    metrics = [
        ("Total features documented", len(FEATURES)),
        ("Implemented & Verified", verified),
        ("Needs validation", needs_val),
        ("Partially implemented", partial),
        ("Known defects (not working)", not_working),
        ("Work items open", len(WORK_REMAINING)),
        ("AI-related feature areas", ai_count),
        ("Image/media feature areas", media_count),
    ]
    row = 5
    ws.cell(row, 1, "Metric").font = Font(bold=True)
    ws.cell(row, 2, "Count").font = Font(bold=True)
    for name, val in metrics:
        row += 1
        ws.cell(row, 1, name)
        ws.cell(row, 2, val)
    row += 2
    summary = (
        "Hecto Baba is a restaurant catalogue product for Indian delivery/dineout platforms "
        "(Swiggy, Zomato, Magicpin). Owners ingest menus, receive Baba quality grades, generate "
        "AI improvement proposals (local Ollama), approve changes explicitly, and edit images in "
        "Media Studio. Core username login and catalogue workflows are implemented with automated tests. "
        "Email OTP is implemented in code but NOT WORKING without email delivery configuration. "
        "Live scraping and AI improvements need production browser validation. "
        "Image editing defaults to Pillow filters/composition—not true AI segmentation—unless optional hosted media URLs are configured."
    )
    ws.cell(row, 1, "Product state summary")
    ws.cell(row, 1).font = Font(bold=True)
    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row + 3, end_column=6)
    c = ws.cell(row, 1, summary)
    c.alignment = WRAP
    c.font = BODY_FONT
    set_col_widths(ws, {1: 32, 2: 12, 3: 18, 4: 18, 5: 18, 6: 18})

    # --- Sheet 2: FEATURES WE BUILT ---
    ws2 = wb.create_sheet("FEATURES WE BUILT")
    headers2 = ["Feature ID", "Module", "Feature", "What We Built", "How It Works", "Technology", "Logic", "Status", "Work Remaining"]
    write_rows(ws2, headers2, FEATURES, status_col=8)
    set_col_widths(ws2, {1: 12, 2: 14, 3: 22, 4: 28, 5: 36, 6: 24, 7: 14, 8: 22, 9: 24})

    # --- Sheet 3: FEATURE DETAILS ---
    ws3 = wb.create_sheet("FEATURE DETAILS")
    headers3 = [
        "Feature ID", "Feature", "Purpose", "User Flow", "Technical Logic", "Frontend", "Backend",
        "API", "Database", "AI/Model", "Validation", "Status", "Known Limitation", "Repository Reference",
    ]
    write_rows(ws3, headers3, FEATURE_DETAILS, status_col=12)
    set_col_widths(ws3, {1: 12, 2: 22, 3: 24, 4: 28, 5: 32, 6: 22, 7: 22, 8: 22, 9: 20, 10: 18, 11: 22, 12: 22, 13: 24, 14: 36})

    # --- Sheet 4: USER JOURNEY ---
    ws4 = wb.create_sheet("USER JOURNEY")
    headers4 = ["Step", "Stage", "User action", "System action", "Result", "Status"]
    write_rows(ws4, headers4, USER_JOURNEY, status_col=6)
    set_col_widths(ws4, {1: 6, 2: 18, 3: 28, 4: 32, 5: 24, 6: 22})

    # --- Sheet 5: SCRAPING & CATALOGUE PIPELINE ---
    ws5 = wb.create_sheet("SCRAPING & CATALOGUE PIPELINE")
    headers5 = ["Stage", "Step", "Purpose", "Logic", "Technology", "Input", "Output", "Status", "Files"]
    write_rows(ws5, headers5, SCRAPING_PIPELINE, status_col=8)
    set_col_widths(ws5, {1: 8, 2: 16, 3: 32, 4: 14, 5: 28, 6: 20, 7: 22, 8: 22, 9: 40})

    # --- Sheet 6: AI / ASSISTANT ---
    ws6 = wb.create_sheet("AI ASSISTANT")
    headers6 = [
        "Feature", "Purpose", "User Input", "AI/Model", "Runtime", "Tools", "Context",
        "Output", "Deterministic Layer", "Human Approval", "Status",
    ]
    write_rows(ws6, headers6, AI_FEATURES, status_col=11)
    set_col_widths(ws6, {1: 22, 2: 28, 3: 22, 4: 18, 5: 16, 6: 18, 7: 22, 8: 18, 9: 24, 10: 18, 11: 22})

    # --- Sheet 7: IMAGE CORRECTION ---
    ws7 = wb.create_sheet("IMAGE CORRECTION")
    headers7 = [
        "Feature", "Input", "Target scope", "Scope class", "Operation", "Technology", "Model",
        "Logic", "What Changes", "What Remains Unchanged", "Status", "Work Remaining",
    ]
    write_rows(ws7, headers7, IMAGE_OPS, status_col=11)
    set_col_widths(ws7, {1: 18, 2: 16, 3: 18, 4: 16, 5: 28, 6: 14, 7: 14, 8: 24, 9: 18, 10: 22, 11: 22, 12: 24})

    # --- Sheet 8: TECH STACK ---
    ws8 = wb.create_sheet("TECH STACK")
    headers8 = ["Area", "Technology", "Where Used", "Purpose"]
    write_rows(ws8, headers8, TECH_STACK)
    set_col_widths(ws8, {1: 14, 2: 22, 3: 36, 4: 40})

    # --- Sheet 9: WORK REMAINING ---
    ws9 = wb.create_sheet("WORK REMAINING")
    headers9 = ["Work ID", "Feature", "Current State", "Required Work", "Priority", "Status", "Notes"]
    write_rows(ws9, headers9, WORK_REMAINING, status_col=6)
    set_col_widths(ws9, {1: 10, 2: 20, 3: 22, 4: 40, 5: 10, 6: 10, 7: 32})

    # --- Sheet 10: ISSUES / BUGS ---
    ws10 = wb.create_sheet("ISSUES BUGS")
    headers10 = ["Issue ID", "Feature", "Issue", "Expected", "Actual", "Impact", "Priority", "Status", "Notes"]
    write_rows(ws10, headers10, ISSUES, status_col=8)
    set_col_widths(ws10, {1: 10, 2: 16, 3: 28, 4: 24, 5: 24, 6: 18, 7: 10, 8: 10, 9: 24})

    # --- Sheet 11: PHASE HISTORY ---
    ws11 = wb.create_sheet("PHASE HISTORY")
    headers11 = ["Phase", "Scope", "What Was Built", "Status", "Closure", "Current Notes"]
    write_rows(ws11, headers11, PHASE_HISTORY, status_col=4)
    set_col_widths(ws11, {1: 8, 2: 22, 3: 32, 4: 14, 5: 28, 6: 32})

    # --- HOW TO UPDATE ---
    ws12 = wb.create_sheet("HOW TO UPDATE")
    instructions = [
        "HOW TO UPDATE THIS WORKBOOK",
        "",
        "1. Add a feature: Insert a new row in FEATURES WE BUILT with the next HB-xxx ID. Copy the row format. Optionally add a row in FEATURE DETAILS for deep documentation.",
        "2. Update status: Change the Status column only using the allowed values (IMPLEMENTED & VERIFIED, IMPLEMENTED — NEEDS VALIDATION, PARTIALLY IMPLEMENTED, IMPLEMENTED — NOT WORKING, NOT IMPLEMENTED, PLANNED, BLOCKED, NEEDS MANUAL VERIFICATION).",
        "3. Add work remaining: Add a row in WORK REMAINING with the next WR-xxx ID. Link to Feature ID in Notes if helpful.",
        "4. Add an issue/bug: Add a row in ISSUES BUGS with the next BUG-xxx ID. Do not duplicate the full work description—reference WR-xxx if the fix is tracked there.",
        "5. Preserve IDs: Never reuse Feature ID, Work ID, or Issue ID numbers once assigned.",
        "6. Keep tables intact: Insert rows inside the Excel table body so filters and formulas continue to work.",
        "7. Executive Summary: Update counts manually after major changes to FEATURES WE BUILT.",
        "8. Do not merge cells in data sheets. Wrap text is enabled; adjust row height if needed.",
        "9. Screenshots: Add manually outside this workbook or in a separate folder; not part of this template.",
        "10. Rebuild from script: python audit_evidence/build_founder_dossier.py regenerates from code audit data (overwrites file). Export custom edits first if needed.",
    ]
    for i, line in enumerate(instructions, 1):
        ws12.cell(i, 1, line).font = TITLE_FONT if i == 1 else BODY_FONT
        ws12.cell(i, 1).alignment = WRAP
    ws12.column_dimensions["A"].width = 100

    wb.save(OUT)
    print(f"Wrote {OUT}")
    print("Sheets:", ", ".join(wb.sheetnames))


if __name__ == "__main__":
    build()
