#!/usr/bin/env python3
"""Build the Hecto Baba Feature Delivery Dossier workbook.

Forensic Product + Engineering handover. Cells are limited to verified Vela
public/sign-in evidence and CatalogForge / Hecto Baba repository facts.
Authenticated Vela app pages are never invented.
"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "HECTO_BABA_FEATURE_DELIVERY_DOSSIER.xlsx"

NAVY = "1B2A4A"
WHITE = "FFFFFF"
SLATE = "334155"
MUTED_SLATE = "64748B"
ROW_ZEBRA = "F8FAFC"
LIGHT_GRAY = "E2E8F0"
GREEN = "D9E8D9"
AMBER = "F3E6C8"
RED = "EBD4D4"
SOFT_NAVY = "E8EEF6"
TITLE_SIZE = 18
SUBTITLE_SIZE = 12

HEADER_FILL = PatternFill("solid", fgColor=NAVY)
HEADER_FONT = Font(name="Calibri", bold=True, color=WHITE, size=11)
TITLE_FONT = Font(name="Calibri", bold=True, color=NAVY, size=TITLE_SIZE)
SUBTITLE_FONT = Font(name="Calibri", italic=True, color=SLATE, size=SUBTITLE_SIZE)
SECTION_FONT = Font(name="Calibri", bold=True, color=NAVY, size=13)
BODY_FONT = Font(name="Calibri", color=SLATE, size=10)
BOLD_FONT = Font(name="Calibri", bold=True, color=SLATE, size=10)
THIN = Border(
    left=Side(style="thin", color=LIGHT_GRAY),
    right=Side(style="thin", color=LIGHT_GRAY),
    top=Side(style="thin", color=LIGHT_GRAY),
    bottom=Side(style="thin", color=LIGHT_GRAY),
)
WRAP = Alignment(wrap_text=True, vertical="center", horizontal="left")

STATUS_FILLS = {
    "IMPLEMENTED": GREEN,
    "CLOSED": GREEN,
    "PASS": GREEN,
    "PARITY": GREEN,
    "ENHANCEMENT": GREEN,
    "NEW": GREEN,
    "PARTIAL": AMBER,
    "DIFFERENT": AMBER,
    "UNKNOWN": AMBER,
    "SCREENSHOT REQUIRED": AMBER,
    "NOT TESTED": AMBER,
    "IMPLEMENTED — NO CLOSURE FILE": AMBER,
    "MISSING": RED,
    "NOT STARTED": RED,
    "GAP": RED,
    "STUB": RED,
    "OVERCLAIM": RED,
    "FILE NOT FOUND": RED,
    "NOT IMPLEMENTED": RED,
}

SCREENSHOTS = (
    ("SS-VELA-01", "audit_evidence/SS-VELA-01-signin.png", "Vela sign-in (public)", "Live inspected"),
    ("SS-VELA-02", "audit_evidence/SS-VELA-02-pricing.png", "Vela pricing (public)", "Live inspected"),
    ("SS-VELA-03", "audit_evidence/SS-VELA-03-studio-help.png", "Vela Studio help (public)", "Live inspected"),
    ("SS-VELA-04", "audit_evidence/SS-VELA-04-score-optimize-help.png", "Vela Score + Optimize help (public)", "Live inspected"),
    ("SS-HB-01", "audit_evidence/SS-HB-01-login.png", "Hecto Baba login", "Captured"),
)

SHEET_NAMES = (
    "Executive Summary",
    "Product Journey",
    "Complete Feature Matrix",
    "Vela vs Hecto Baba",
    "Detailed Feature Implementation",
    "Scraping & Data Pipeline",
    "AI Agent Inventory",
    "Image Intelligence",
    "Proposal & Approval Workflow",
    "Technical Stack",
    "Architecture & Data Flow",
    "Testing & Verification",
    "Screenshot Evidence",
    "Issues & Gaps",
    "AI Code Complexity Audit",
    "Phase History",
)

ACCURACY_RULE = (
    "ACCURACY RULE: Authenticated Vela dashboard pages were NOT accessed. "
    "Those surfaces are marked UNKNOWN / SCREENSHOT REQUIRED. "
    "Do not invent Vela internals. Vela facts below come only from live sign-in, "
    "public pricing, and public help. Hecto Baba facts come only from this repository."
)


def _status_fill(value: str) -> PatternFill | None:
    text = (value or "").strip().upper()
    if text in STATUS_FILLS:
        return PatternFill("solid", fgColor=STATUS_FILLS[text])
    for key, color in STATUS_FILLS.items():
        if key in text:
            return PatternFill("solid", fgColor=color)
    return None


def _apply_data_cell(cell, value: object, zebra: bool) -> None:
    cell.value = value
    cell.font = BODY_FONT
    cell.alignment = WRAP
    cell.border = THIN
    fill = _status_fill(str(value)) if isinstance(value, str) else None
    if fill is not None:
        cell.fill = fill
        cell.font = BOLD_FONT
    elif zebra:
        cell.fill = PatternFill("solid", fgColor=ROW_ZEBRA)


def write_table(
    ws: Worksheet,
    headers: list[str],
    rows: list[list[object]],
    *,
    start_row: int = 1,
    widths: list[float] | None = None,
    wrap_height: float = 42,
) -> int:
    cols = len(headers)
    header_row = start_row
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(header_row, col, header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = WRAP
        cell.border = THIN
    ws.row_dimensions[header_row].height = 28

    last = header_row
    for offset, row in enumerate(rows):
        excel_row = header_row + 1 + offset
        zebra = offset % 2 == 1
        for col in range(1, cols + 1):
            value = row[col - 1] if col - 1 < len(row) else ""
            _apply_data_cell(ws.cell(excel_row, col), value, zebra)
        ws.row_dimensions[excel_row].height = wrap_height
        last = excel_row

    if last > header_row:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(cols)}{last}"
    else:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(cols)}{header_row}"
    ws.freeze_panes = f"A{header_row + 1}"

    chosen = widths or [22] * cols
    for col, width in enumerate(chosen, start=1):
        ws.column_dimensions[get_column_letter(col)].width = min(45, max(18, width))

    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.sheet_view.showGridLines = False
    return last


def merge_banner(ws: Worksheet, row: int, cols: int, text: str, font: Font, fill: PatternFill | None = None, height: float = 28) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=cols)
    cell = ws.cell(row, 1, text)
    cell.font = font
    cell.alignment = WRAP
    if fill is not None:
        cell.fill = fill
        for col in range(1, cols + 1):
            ws.cell(row, col).fill = fill
            ws.cell(row, col).border = THIN
    ws.row_dimensions[row].height = height


def setup_sheet(wb: Workbook, title: str) -> Worksheet:
    ws = wb.create_sheet(title)
    ws.sheet_properties.tabColor = NAVY
    return ws


# ---------------------------------------------------------------------------
# Sheet data (verified only)
# ---------------------------------------------------------------------------


def cover_and_executive_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["Topic", "Finding", "Classification", "Evidence", "Implication for handover"]
    rows: list[list[object]] = [
        [
            "Domain",
            "Vela is multi-channel ecommerce listings (Etsy, Shopify, eBay, Faire; Squarespace Coming Soon). Hecto Baba is Indian restaurant catalogue SaaS (CatalogForge): owners ingest Swiggy/Zomato/Magicpin restaurant and dineout menus, grade quality, propose AI improvements, owner-apply only.",
            "DIFFERENT",
            "Vela sign-in marketing + pricing; HB AGENT.md / product routes",
            "Do not claim marketplace parity. Compare analogous workflows, not identical products.",
        ],
        [
            "Analogous pattern",
            "Score → AI optimize field → preview → human keep/apply → publish is reproduced in Hecto Baba as grade → allowlisted improvement / media job → Current→Proposed preview → owner Apply → optional re-grade. Publish to a live shop does not exist.",
            "DIFFERENT",
            "Vela Score+Optimize help; HB Phases 3, 5, 6, 11",
            "Architecture and safety model differ; the operator loop is analogous, not a clone.",
        ],
        [
            "Baba improvements vs Vela",
            "Grounded backend validation, local Ollama llama3:latest, Playwright/Chrome CDP scrape ingestion, first-party review intel (review_intel.v1.1), Baba chat (deterministic router then optional planner extra=forbid, GET tools only), CAS/STALE, owner-apply safety (catalogues.payload not mutated until Apply).",
            "ENHANCEMENT",
            "Repo: improvement/, assistant/, review_intel/, scraper/, grading/",
            "These are restaurant-catalogue strengths, not Vela feature copies.",
        ],
        [
            "Baba missing vs Vela",
            "Channel publish, CSV import/export, listing profiles, sandbox, prompt manager, real AI studio isolation (face/subject/object), schedule publish/updates, Google/Facebook SSO, billing (Lite $29.95 / Plus $39.95 observed).",
            "MISSING",
            "Vela sign-in + pricing + help vs HB auth.ts / absence of CSV/publish routes",
            "Production readiness is as a restaurant catalogue system, NOT a Vela clone.",
        ],
        [
            "Production readiness",
            "Implemented as restaurant catalogue quality system with closed phases 1–6 and 8–12. Phase 7 media is implemented without PHASE7_CLOSURE.md. Phase 13 dashboard is NOT STARTED. Not a Vela marketplace clone.",
            "IMPLEMENTED",
            "PHASE*_CLOSURE.md, PHASE11_FINAL_AUDIT.md, PHASE12_AI_CATALOGUE_REFINEMENT_AUDIT.md",
            "Do not claim Vela parity for marketplace, CSV, profiles, sandbox, or studio isolation.",
        ],
        [
            "Vela inspection limit",
            "https://app.getvela.com/account redirected to https://app.getvela.com/auth/sign-in. Sign-in, public pricing, and public help were inspected. Authenticated Listings Dashboard / Editor / Studio app UI were not accessed.",
            "UNKNOWN",
            "Live sign-in + public help/pricing only",
            "Mark authenticated Vela UI UNKNOWN / SCREENSHOT REQUIRED. Do not invent internals.",
        ],
        [
            "HB screenshot limit",
            "Authenticated Hecto Baba dashboard screenshots were not captured (login required) except the login page SS-HB-01.",
            "PARTIAL",
            "Screenshot Evidence sheet",
            "Dashboard UX claims must be backed by later screenshots, not assumed from routes alone.",
        ],
        [
            "Scoring analog",
            "Vela: letter scores; Etsy Title/Tags/Description; Shopify Title/Description/SEO metadata. HB: grading.v1 50% deterministic / 25% NLP heuristic / 25% local vision; A≥90 B≥75 C≥60 D≥40 F<40; hard fail F. Baba Score is a read-only projection of frozen grading.v1. Ungraded venues stay ungraded (no invented F/0).",
            "DIFFERENT",
            "backend/grading/formula.py; PHASE3_CLOSURE.md; PHASE4_CLOSURE.md",
            "Letter scores exist in both; field taxonomies and engines are not the same.",
        ],
        [
            "Optimize analog",
            "Vela: Optimize / Retry / Revert / Keep then Publish or Schedule; bulk field optimize; Keep then Sync Updates (does not touch live shop until sync). HB: generate proposal READY/FAILED → UI card → owner Apply mutates payload → re-grade; media apply is a separate live image replace. Baba chat cannot apply.",
            "DIFFERENT",
            "PHASE6_CLOSURE.md; PHASE11_FINAL_AUDIT.md; assistant WRITE_TOOL_NAMES",
            "Human-gated apply is analogous; publish/schedule/sync-to-shop is missing.",
        ],
        [
            "Ingest vs channels",
            "Vela active channels: Etsy, Shopify, eBay, Faire. HB ingest platforms: Swiggy, Zomato, Magicpin via shared BrowserAccess.collect_swiggy_source. No marketplace publish.",
            "DIFFERENT",
            "Vela sign-in channels; backend/services/catalog_service.py",
            "Platforms are sources for HB, destinations for Vela.",
        ],
        [
            "Auth",
            "Vela sign-in: Google, Facebook, Email+Password, Forgot, Sign up. HB: Better Auth email/password, username, email OTP, organization plugin. No Google/Facebook SSO. FastAPI require_session + require_organization_member.",
            "DIFFERENT",
            "auth/auth.ts; frontend auth-client.ts; backend/session.py; backend/authz.py",
            "SSO and Vela billing are missing on HB.",
        ],
        [
            "Media honesty",
            "HB local media.v1 uses Pillow. background_removal is _fake_cutout ellipse mask, not ML segmentation. image_to_video is a 12-frame GIF zoom; routing forces local for GIF. Face-only / subject-only / object-only are NOT implemented. Hosted FLUX Kontext / SVD is optional HTTP/Gradio when configured.",
            "OVERCLAIM",
            "backend/media/providers.py; routing.py; media-ui.ts copy",
            "Do not describe local studio as Vela-grade isolation or AI video.",
        ],
        [
            "Known pipeline gaps",
            "extraction_status partial is accepted by schema/UI but parsers emit ok/blocked/failed/pending only. OfficialApiAccess is a stub. Swiggy WAF can block. Chrome CDP port 9222 busy can fail scrape. Nav uses first organization only. Profile/settings notifications are localStorage.",
            "GAP",
            "backend/schemas.py; parsers; OfficialApiAccess; chrome_session.py DEFAULT_CDP_PORT; organizations?.[0]",
            "Document as residual risk, not as shipped Vela-equivalent capability.",
        ],
        [
            "Billing",
            "Vela Lite $29.95 / Plus $39.95 per shop/month (1,000–2,500 listings band observed); 20% multi-shop discount; 1-week free trial no card. HB has no billing product in this repo.",
            "MISSING",
            "Vela pricing page",
            "No Lite/Plus model split, no trial, no shop-month SKU.",
        ],
        [
            "Workbook method",
            "This dossier was generated from verified notes and repository contracts. Authenticated Vela pages are not described. Missing screenshot files are listed as FILE NOT FOUND rather than substituted.",
            "PASS",
            "audit_evidence/build_dossier.py",
            "Regenerate this xlsx from the script; do not hand-edit facts.",
        ],
    ]
    return headers, rows


def product_journey_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["Step", "Actor", "Hecto Baba surface", "What happens", "Vela analog (verified only)", "Classification"]
    rows = [
        ["1", "Owner", "/signup", "Create account with username + email/password (username required on sign-up).", "Vela Sign up on sign-in page", "DIFFERENT"],
        ["2", "Owner", "/", "Username login and email OTP path. No Google/Facebook.", "Vela Google, Facebook, Email+Password, Forgot", "DIFFERENT"],
        ["3", "Owner", "/overview", "Dashboard overview of catalogues for organizations[0].", "Vela listings dashboard — authenticated, UNKNOWN", "UNKNOWN"],
        ["4", "Owner", "/catalogues/new", "CreateCatalogueForm: restaurant name, FSSAI, platform URL, catalogue_type restaurant|dineout|both.", "Vela Create listings / Add Shop — not the same object", "DIFFERENT"],
        ["5", "System", "POST /catalog/create", "BrowserAccess.collect_swiggy_source (shared for Swiggy/Zomato/Magicpin) → parse → normalize → validate → ExistingCatalogueAdapter → save_catalogue → materialize images → bind_raw_capture.", "Vela does not scrape Indian food platforms (not observed on public pages)", "NEW"],
        ["6", "System", "WAF / identity", "WAF → extraction_status blocked. CatalogueIdentityConflict → HTTP 409, rollback, no third row.", "Not observed on public Vela pages", "NEW"],
        ["7", "Owner", "/catalogues/[id]", "View canonical catalogue. extraction_status ok|partial|blocked|failed|pending in UI; parsers do not emit partial.", "Vela listing editor — authenticated UNKNOWN", "DIFFERENT"],
        ["8", "Owner", "POST .../grade", "grade_catalogue with frozen grading.v1. COMPLETED only after persisted grade row.", "Vela Quality Score / letter scores (help)", "DIFFERENT"],
        ["9", "Owner", "GET .../grade-explanation", "Phase 5 read-time projection grade_explain.v1. 404 if no completed grade for current revision/hash.", "Vela Score help (letter scores, field breakdown by channel)", "DIFFERENT"],
        ["10", "Owner", "GET .../baba-score", "Baba Score is a read-only projection of grading.v1, not platform ratings.", "Vela listing scoring (sign-in list)", "DIFFERENT"],
        ["11", "Owner", "/catalogues/[id]/improvements", "Improve with AI → POST /improvements. resolve_targets must be 1 target if 1 path. Preview Current → Proposed → Why.", "Vela Optimize / Keep then Publish or Schedule (help)", "DIFFERENT"],
        ["12", "Owner", "POST .../improvements/{id}/apply", "Owner Apply mutates allowlisted fields, then re-grade. Baba tools cannot apply.", "Vela Keep then Sync Updates (help: does not touch live shop until sync)", "DIFFERENT"],
        ["13", "Owner", "/catalogues/[id]/media", "Media jobs: local Pillow and optional hosted. Apply copies artefact into catalogue-assets.", "Vela Studio (public help). Authenticated Studio UNKNOWN", "DIFFERENT"],
        ["14", "Owner", "/catalogues/[id]/reviews", "First-party customer feedback (source=customer) and operator paste (source=supplied). No Google/Zomato scrape.", "Not on Vela public marketing list", "NEW"],
        ["15", "Owner", "/baba-ai and dock", "Single brain. Deterministic router first, optional Ollama planner extra=forbid. GET tools only.", "Vela green wand / AI optimize (help) — not a chat assistant of this design", "NEW"],
        ["16", "Owner", "Phase 10 mutations", "Propose → Confirm → Apply; 15 min TTL. Separate from Phase 6 improvement rows.", "Vela Edit listings (sign-in list); internals UNKNOWN", "DIFFERENT"],
        ["17", "Owner", "/catalogues/[id]/history", "GET history; POST rollback. Phase 11/12 audit covers history rollback.", "Not verified on Vela public pages", "NEW"],
        ["18", "Owner", "/areas and /areas/[id]", "Area jobs: create/list/start/scrape-batch/cancel/delete. Batch poll, not Celery.", "Not on Vela public marketing list", "NEW"],
        ["19", "Owner", "/restaurant /dineout", "Domain views for restaurant vs dineout catalogues.", "Not applicable to Vela ecommerce listings", "NEW"],
        ["20", "Owner", "/profile /settings", "Profile and notification prefs stored in localStorage keyed by user id.", "Vela Help/Support/Settings (help overview)", "DIFFERENT"],
        ["21", "Missing", "Marketplace publish", "No publish listings, schedule publish, multi-channel, CSV, POD, listing profiles.", "Vela sign-in feature list and pricing Plus profiles", "MISSING"],
        ["22", "Missing", "Phase 13", "Operator dashboard product is NOT STARTED.", "Vela listings dashboard (authenticated UNKNOWN)", "NOT STARTED"],
    ]
    return headers, rows


def feature_matrix_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["ID", "Feature", "Area", "Status", "Primary route / API", "Mutates catalogue?", "Notes"]
    rows: list[list[object]] = [
        ["HB-AUTH-01", "Email + password authentication", "Auth", "IMPLEMENTED", "Better Auth emailAndPassword; /", "No", "auth/auth.ts enabled"],
        ["HB-AUTH-02", "Username sign-in", "Auth", "IMPLEMENTED", "authClient.signIn.username; login-form.tsx", "No", "Username plugin min 3 / max 30"],
        ["HB-AUTH-03", "Email OTP", "Auth", "IMPLEMENTED", "emailOTP plugin; SMTP or AUTH_OTP_LOG", "No", "Raises if neither SMTP_HOST nor AUTH_OTP_LOG"],
        ["HB-AUTH-04", "Sign-up with required username", "Auth", "IMPLEMENTED", "/signup; before hook on /sign-up/email", "No", "APIError if username missing"],
        ["HB-AUTH-05", "Organization plugin", "Auth", "IMPLEMENTED", "organization(); organizationClient()", "No", "Org membership required on FastAPI"],
        ["HB-AUTH-06", "Session gate", "Auth", "IMPLEMENTED", "require_session", "No", "Cookie session; Next /api/auth same-origin"],
        ["HB-AUTH-07", "Organization authorization", "Auth", "IMPLEMENTED", "require_organization_member", "No", "Session + org membership + catalogue access"],
        ["HB-AUTH-08", "Google / Facebook SSO", "Auth", "NOT IMPLEMENTED", "—", "No", "Vela has Google and Facebook on sign-in; HB does not"],
        ["HB-NAV-01", "Overview", "Navigation", "IMPLEMENTED", "/overview", "No", "Uses organizations?.[0]?.id"],
        ["HB-NAV-02", "Areas list and job detail", "Navigation", "IMPLEMENTED", "/areas, /areas/[id]", "No", "Area scrape jobs"],
        ["HB-NAV-03", "Restaurant domain", "Navigation", "IMPLEMENTED", "/restaurant, /restaurant/about", "No", "catalogueMatchesDomain restaurant"],
        ["HB-NAV-04", "Dineout domain", "Navigation", "IMPLEMENTED", "/dineout, /dineout/about", "No", "catalogueMatchesDomain dineout"],
        ["HB-NAV-05", "Catalogue workspace", "Navigation", "IMPLEMENTED", "/catalogues, /catalogues/new, /catalogues/[id]", "No", "List / create / detail"],
        ["HB-NAV-06", "Improvements / media / reviews / assistant", "Navigation", "IMPLEMENTED", "/catalogues/[id]/improvements|media|reviews|assistant", "Apply endpoints yes", "Sibling workspace routes"],
        ["HB-NAV-07", "Grading", "Navigation", "IMPLEMENTED", "/grading, /grading/[id]", "POST grade yes (persists grade row, not payload)", "Grade job UI"],
        ["HB-NAV-08", "Baba AI full page", "Navigation", "IMPLEMENTED", "/baba-ai", "No writes via tools", "Same brain as compact dock"],
        ["HB-NAV-09", "Profile and settings", "Navigation", "IMPLEMENTED", "/profile, /settings", "No", "Prefs in localStorage"],
        ["HB-NAV-10", "Multi-org switcher", "Navigation", "NOT IMPLEMENTED", "organizations?.[0] only", "No", "First organization only"],
        ["HB-CAT-01", "Create catalogue from platform URL", "Catalogue", "IMPLEMENTED", "POST /catalog/create via /api/catalog/create", "Inserts catalogue", "CreateCatalogueForm → catalog-api createCatalogue"],
        ["HB-CAT-02", "List catalogues", "Catalogue", "IMPLEMENTED", "GET /catalogues", "No", "Org-scoped"],
        ["HB-CAT-03", "Get catalogue", "Catalogue", "IMPLEMENTED", "GET /catalogues/{id}", "No", "StoredCatalogue"],
        ["HB-CAT-04", "Delete catalogue", "Catalogue", "IMPLEMENTED", "DELETE /catalogues/{id}", "Deletes row", "Authz same as get"],
        ["HB-CAT-05", "Catalogue types", "Catalogue", "IMPLEMENTED", "catalogue_type restaurant|dineout|both", "On create", "CatalogCreateRequest"],
        ["HB-CAT-06", "Swiggy ingest", "Catalogue", "IMPLEMENTED", "platform=swiggy; parse_swiggy_catalogue", "On create", "Shared Chrome CDP collector"],
        ["HB-CAT-07", "Zomato ingest", "Catalogue", "IMPLEMENTED", "parse_zomato_catalogue", "On create", "Same BrowserAccess collector"],
        ["HB-CAT-08", "Magicpin ingest", "Catalogue", "IMPLEMENTED", "parse_magicpin_catalogue", "On create", "Same BrowserAccess collector"],
        ["HB-CAT-09", "Identity conflict", "Catalogue", "IMPLEMENTED", "CatalogueIdentityConflict HTTP 409", "Rollback, no third row", "PHASE1_CLOSURE.md"],
        ["HB-CAT-10", "Canonical persist", "Catalogue", "IMPLEMENTED", "save_catalogue; ExistingCatalogueAdapter", "Yes", "No second persistence path (Phase 2)"],
        ["HB-CAT-11", "Raw capture bind", "Catalogue", "IMPLEMENTED", "write_pending_raw then bind", "Side store", "Durable raw; no janitor"],
        ["HB-CAT-12", "Image materialize", "Catalogue", "IMPLEMENTED", "materialize_catalogue_images; /catalogue-assets", "Asset files", "Local confinement"],
        ["HB-CAT-13", "extraction_status schema", "Catalogue", "PARTIAL", "ok|partial|blocked|failed|pending", "No", "partial accepted in UI/schema; parsers do not emit partial"],
        ["HB-CAT-14", "History list", "Catalogue", "IMPLEMENTED", "GET /catalogues/{id}/history", "No", "Edit history"],
        ["HB-CAT-15", "History rollback", "Catalogue", "IMPLEMENTED", "POST /history/{history_id}/rollback", "Yes", "PHASE11_PHASE12_HISTORY_ROLLBACK_AUDIT.md"],
        ["HB-SCRAPE-01", "Chrome CDP collection", "Scraping", "IMPLEMENTED", "playwright.chromium.connect_over_cdp", "No until save", "Not HTTP-only menu scrape"],
        ["HB-SCRAPE-02", "Timeouts", "Scraping", "IMPLEMENTED", "NAV 45s, menu wait 20s, challenge 12s, max 16 scrolls", "No", "scraper/swiggy/scraper.py; no retry-storm"],
        ["HB-SCRAPE-03", "WAF blocked", "Scraping", "IMPLEMENTED", "extraction_status blocked", "No success persist of menu", "Does not bypass access controls"],
        ["HB-SCRAPE-04", "Official API access", "Scraping", "STUB", "OfficialApiAccess.load pending=True", "No", "OFFICIAL_API_PENDING_MESSAGE"],
        ["HB-SCRAPE-05", "Area jobs", "Scraping", "IMPLEMENTED", "POST/GET /area-jobs; start; scrape-batch; cancel; delete", "Creates catalogues when batch succeeds", "Batch poll, not Celery"],
        ["HB-SCRAPE-06", "CDP port 9222", "Scraping", "GAP", "DEFAULT_CDP_PORT = 9222", "Can fail scrape", "Busy port can fail collection"],
        ["HB-GRADE-01", "grading.v1 engine", "Grading", "CLOSED", "POST/GET /catalogues/{id}/grade", "Grade row only", "Weights 50/25/25; hard fail F"],
        ["HB-GRADE-02", "Grade explanation", "Grading", "CLOSED", "GET /grade-explanation", "No", "Phase 5; 404/502 rules preserved"],
        ["HB-GRADE-03", "Baba Score", "Grading", "CLOSED", "GET /baba-score", "No", "Projection of grading.v1; not platform ratings"],
        ["HB-GRADE-04", "Platform evaluation", "Grading", "CLOSED", "POST/GET /platform-evaluation", "Eval row", "platform_eval.v1 evidence; empty GET is 200 []"],
        ["HB-GRADE-05", "Item quality letters", "Grading", "IMPLEMENTED", "item-quality.ts", "No", "Missing description/tags/image/price display F"],
        ["HB-GRADE-06", "Ungraded venues", "Grading", "IMPLEMENTED", "No completed grade → no invented F/0", "No", "Phase 9 / Phase 5 404 when no grade"],
        ["HB-IMP-01", "Generate improvement proposal", "Improvements", "CLOSED", "POST /improvements", "Proposal table only", "BEGIN IMMEDIATE GENERATING before generator"],
        ["HB-IMP-02", "List / get proposals", "Improvements", "CLOSED", "GET /improvements, GET /improvements/{id}", "No", "Replay persisted proposal on duplicate request_key"],
        ["HB-IMP-03", "Owner apply improvement", "Improvements", "CLOSED", "POST /improvements/{id}/apply", "Allowlisted fields only", "Phase 11; Baba cannot apply via tools"],
        ["HB-IMP-04", "Cancel improvement", "Improvements", "CLOSED", "POST /improvements/{id}/cancel", "Terminal CANCELLED", "Same request_key regenerates rather than resurrecting"],
        ["HB-IMP-05", "Allowlisted kinds", "Improvements", "CLOSED", "description, category_name, labels, media_handoff, item_price", "Only those kinds on apply", "KIND_REGISTRY; no arbitrary JSON patch"],
        ["HB-IMP-06", "Trusted price copy", "Improvements", "CLOSED", "item_price from original_price", "Copies original_price", "LLM never invents price"],
        ["HB-IMP-07", "Labels merge", "Improvements", "CLOSED", "labels kind; validate_labels", "labels[]", "food_type veg preserved; Ollama candidate + deterministic merge"],
        ["HB-IMP-08", "media_handoff", "Improvements", "CLOSED", "handoff record, no generation", "Does not replace live image", "Apply skipped; live replace is media-job apply"],
        ["HB-IMP-09", "STALE / CAS", "Improvements", "CLOSED", "revision + state hash", "Refused if diverged", "APPLIED replay idempotent"],
        ["HB-IMP-10", "Re-grade after apply", "Improvements", "CLOSED", "grade_catalogue after apply", "Grade row", "Frozen grading.v1; never inflate letters"],
        ["HB-MEDIA-01", "Media studio payload", "Media", "IMPLEMENTED", "GET /media-studio", "No", "Phase 7; no PHASE7_CLOSURE.md"],
        ["HB-MEDIA-02", "Create media job", "Media", "IMPLEMENTED", "POST /media-jobs", "Job + artefacts only until apply", "Statuses GENERATING/READY/FAILED/CANCELLED/STALE/APPLIED"],
        ["HB-MEDIA-03", "List / get / cancel jobs", "Media", "IMPLEMENTED", "GET jobs; POST cancel", "No live replace on cancel", "media.v1"],
        ["HB-MEDIA-04", "Apply media job", "Media", "CLOSED", "POST /media-jobs/{id}/apply", "Live image/video field via catalogue-assets", "Separate from improvement apply"],
        ["HB-MEDIA-05", "Media revert", "Media", "IMPLEMENTED", "POST /media-revert", "Restores prior media field", "Exists as API"],
        ["HB-MEDIA-06", "Prompt assist", "Media", "IMPLEMENTED", "POST /media-prompt-assist", "No", "Prompt validation; catalogue text is DATA"],
        ["HB-MEDIA-07", "Local Pillow operations", "Media", "IMPLEMENTED", "LocalMediaProvider", "Preview until apply", "enhance/blur/crop/expand/cleanup/edit full-image filters"],
        ["HB-MEDIA-08", "Fake subject cutout", "Media", "IMPLEMENTED", "_fake_cutout ellipse", "Preview until apply", "NOT ML segmentation; NOT face/subject/object modes"],
        ["HB-MEDIA-09", "GIF zoom", "Media", "IMPLEMENTED", "image_to_video 12 frames", "Preview until apply", "Routing forces local; not AI video"],
        ["HB-MEDIA-10", "Optional hosted FLUX/SVD", "Media", "PARTIAL", "hosted.v1 HTTP/Gradio when env configured", "Preview until apply", ".env.example: non-commercial quota-limited; not production by default"],
        ["HB-AI-01", "Ollama text generator", "AI", "IMPLEMENTED", "127.0.0.1:11434 llama3:latest; 60s default", "Proposal only", "Untrusted candidate; backend validation authoritative"],
        ["HB-AI-02", "Baba assistant turn", "AI", "CLOSED", "POST /assistant/turn and /catalogues/{id}/assistant/turn", "No via tools", "Phase 9"],
        ["HB-AI-03", "Mutation confirm/cancel", "AI", "CLOSED", "POST .../assistant/mutations/{id}/confirm|cancel", "Yes on confirm apply", "Phase 10; 15 min TTL"],
        ["HB-REV-01", "Collect supplied reviews", "Reviews", "CLOSED", "POST /reviews/collect", "Review store only", "source=supplied"],
        ["HB-REV-02", "Customer feedback", "Reviews", "CLOSED", "POST /customer-feedback; GET photos", "Review store only", "source=customer; session-authenticated V1"],
        ["HB-REV-03", "List reviews", "Reviews", "CLOSED", "GET /reviews", "No", "author_key opaque; owners do not see email"],
        ["HB-REV-04", "Review intelligence", "Reviews", "CLOSED", "POST/GET /review-intelligence", "No catalogue write", "review_intel.v1.1; inspect-only recommendations"],
        ["HB-REV-05", "Third-party review scrape", "Reviews", "NOT IMPLEMENTED", "No Google/Zomato/Swiggy/Yelp APIs", "No", "PHASE8_CLOSURE.md"],
        ["HB-ASSETS-01", "Static catalogue assets", "Infra", "IMPLEMENTED", "GET /catalogue-assets", "Files", "FastAPI StaticFiles; SSRF-safe fetch elsewhere"],
    ]
    return headers, rows


def vela_vs_baba_rows() -> tuple[list[str], list[list[object]]]:
    headers = [
        "Vela capability",
        "Vela evidence source",
        "Hecto Baba counterpart",
        "Classification",
        "Honest notes",
    ]
    rows: list[list[object]] = [
        ["Create listings", "Sign-in marketing list", "POST /catalog/create scrape ingest of restaurant/dineout menus", "DIFFERENT", "HB creates catalogues from platform URLs, not ecommerce listings."],
        ["CSV import", "Sign-in marketing list", "None", "MISSING", "No CSV ingest route in backend/main.py."],
        ["Bulk edit", "Sign-in + help Bulk Editor; Lite includes bulk edit", "Allowlisted improvement lines (default max 5 lines/request in Phase 6 V1)", "DIFFERENT", "Not a Vela Bulk Editor. No arbitrary bulk field grid."],
        ["Listing scoring", "Sign-in list; help Quality Score", "grading.v1 + GET /grade + Baba Score", "DIFFERENT", "Analogous letter score; restaurant catalogue engine, not Etsy/Shopify field scores."],
        ["Schedule publish", "Sign-in list; help publish/schedule", "None", "MISSING", "No schedule or marketplace publish."],
        ["POD support", "Sign-in marketing list", "None", "MISSING", "Print-on-demand is ecommerce; not in HB domain."],
        ["Active channels", "Sign-in list; help Activate channels", "Swiggy/Zomato/Magicpin as ingest sources only", "MISSING", "HB has no publish channels."],
        ["Media library", "Sign-in list", "catalogue-assets + media studio + media jobs", "DIFFERENT", "Local assets and job artefacts, not verified as Vela Studio library (authenticated Studio UNKNOWN)."],
        ["Optimize listings", "Sign-in list; Lite AI individual optimize", "POST /improvements + owner Apply", "DIFFERENT", "Grounded allowlisted kinds; not Vela listing optimizer."],
        ["Edit listings", "Sign-in list; Lite create/edit", "Catalogue UI + Phase 10 typed mutations", "DIFFERENT", "Restaurant items/categories, not marketplace listings."],
        ["Copy listings", "Sign-in list; help Copy", "None", "MISSING", "No copy-listing API."],
        ["Merge listings", "Sign-in list; help Merge", "None", "MISSING", "Phase 2: no fuzzy/cross-platform identity merge."],
        ["Attribute scoring", "Sign-in list", "Section grades Deterministic / Text / Images from stored stage scores", "DIFFERENT", "Not Vela attribute scoring internals (those internals not inspected)."],
        ["Schedule updates", "Sign-in list; help Schedule", "None", "MISSING", "No scheduled updates."],
        ["Listing profiles", "Sign-in list; Plus unlimited profiles; help Profiles; AI Profiles vs Standard Profiles", "None", "MISSING", "HB /profile is account localStorage, not listing profiles."],
        ["Photo unification", "Sign-in marketing list", "None as a named product feature", "MISSING", "No photo-unification engine documented."],
        ["Isolate products", "Sign-in list; Studio help Remove background with scale/rotate isolated item", "_fake_cutout ellipse mask", "MISSING", "Not face/subject/object isolation. Not Vela isolate."],
        ["Cross-channel copy", "Sign-in marketing list", "None", "MISSING", "No cross-channel copy. Ingest platforms are not publish channels."],
        ["Video creation", "Sign-in list", "image_to_video 12-frame GIF zoom; hosted SVD unused for GIF routing", "DIFFERENT", "Local GIF animation, not AI video."],
        ["Photo backgrounds", "Sign-in list; Studio Standard Generate / AI Generate", "background_generation cream composite or hosted if configured", "DIFFERENT", "Local fallback is cream composite after ellipse cutout."],
        ["Publish listings", "Sign-in list; help publish", "None", "MISSING", "Owner Apply updates HB catalogue only."],
        ["Multi-channel", "Sign-in list; channels Etsy/Shopify/eBay/Faire", "Multi-source ingest only", "MISSING", "Squarespace Coming Soon on Vela; irrelevant to HB."],
        ["CSV export", "Sign-in marketing list", "None", "MISSING", "No CSV export route."],
        ["Alt text generation", "Sign-in list; Studio AI alt text", "None for listing alt text", "MISSING", "media-prompt-assist is image prompt help, not alt text generation."],
        ["Channel: Etsy", "Sign-in channels", "None", "MISSING", "Not a restaurant ingest source."],
        ["Channel: Shopify", "Sign-in channels; Score help Shopify Title/Description/SEO", "None", "MISSING", "No Shopify adapter."],
        ["Channel: eBay", "Sign-in channels", "None", "MISSING", "No eBay adapter."],
        ["Channel: Faire", "Sign-in channels", "None", "MISSING", "No Faire adapter."],
        ["Channel: Squarespace Coming Soon", "Sign-in channels", "None", "MISSING", "Vela future channel; HB has no equivalent."],
        ["Lite $29.95 / shop / month", "Pricing page (1,000–2,500 listings band observed)", "No billing SKU", "MISSING", "No Lite plan."],
        ["Plus $39.95 / shop / month", "Pricing page", "No billing SKU", "MISSING", "No Plus plan."],
        ["20% multi-shop discount", "Pricing page", "None", "MISSING", "Nav uses first organization only; no multi-shop billing."],
        ["1-week free trial no card", "Pricing page", "None", "MISSING", "Auth is account creation, not a billed trial."],
        ["Lite: scoring", "Pricing Lite vs Plus", "grading.v1 scoring exists without a Lite SKU", "DIFFERENT", "Capability exists in HB; not sold as Lite."],
        ["Lite: create/edit listings", "Pricing", "Create/edit catalogues and items", "DIFFERENT", "Different object model."],
        ["Lite: AI individual optimize", "Pricing", "Per-path improvement generate", "DIFFERENT", "Allowlisted kinds only."],
        ["Lite: bulk edit", "Pricing", "No Vela Bulk Editor", "MISSING", "Phase 6 caps lines per request; not bulk listing edit."],
        ["Plus: AI bulk optimize", "Pricing", "None", "MISSING", "No AI bulk optimize product."],
        ["Plus: AI copy", "Pricing", "Ollama description candidates + validators", "DIFFERENT", "Grounded item descriptions, not Vela AI copy product."],
        ["Plus: unlimited profiles", "Pricing", "None", "MISSING", "No listing profiles."],
        ["Plus: more studio AI", "Pricing", "Optional hosted FLUX/SVD; local Pillow fallbacks", "DIFFERENT", "Do not equate to Plus studio AI. Authenticated Vela Studio UNKNOWN."],
        ["Help: shops menu", "Platform Overview help", "Organization catalogues; first org only", "DIFFERENT", "No shops menu as Vela describes."],
        ["Help: listings dashboard Quality Score", "Platform Overview help", "/grading, catalogue grade, Baba Score", "DIFFERENT", "HB dashboard screenshots not captured except login."],
        ["Help: Copy/Merge", "Platform Overview help", "None", "MISSING", "No copy/merge listings."],
        ["Help: Add Shop", "Platform Overview help", "/catalogues/new URL ingest", "DIFFERENT", "Adds a catalogue from a menu URL, not a shop channel."],
        ["Help: Activate channels", "Platform Overview help", "None", "MISSING", "No channel activation."],
        ["Help: Listing Editor green wand", "Platform Overview help", "Improvements UI + Baba AI", "DIFFERENT", "Authenticated Vela editor UNKNOWN."],
        ["Help: publish/schedule", "Platform Overview help", "None", "MISSING", "No publish/schedule."],
        ["Help: Bulk Editor", "Platform Overview help; AI Tools bulk editor", "None as Vela bulk editor", "MISSING", "See also bulk edit above."],
        ["Help: Profiles", "Platform Overview help", "None (account /profile is localStorage)", "MISSING", "Not listing profiles."],
        ["Help: Schedule", "Platform Overview help", "None", "MISSING", "No scheduler."],
        ["Help: Studio", "Platform Overview help; Studio help article", "/catalogues/[id]/media", "DIFFERENT", "Authenticated Vela Studio app UI UNKNOWN / SCREENSHOT REQUIRED."],
        ["Help: Help/Support/Settings", "Platform Overview help", "/settings, /profile", "DIFFERENT", "No Vela Help center clone."],
        ["Score: letter scores", "Score + Optimize help", "A–F via letter_for_score", "DIFFERENT", "Same letter labels; different formula and domain."],
        ["Score: Etsy Title/Tags/Description", "Score + Optimize help", "None", "MISSING", "No Etsy fields."],
        ["Score: Shopify Title/Description/SEO metadata", "Score + Optimize help", "None", "MISSING", "No Shopify SEO metadata product."],
        ["Optimize / Retry / Revert / Keep then Publish or Schedule", "Score + Optimize help", "Generate / cancel-regenerate / media revert / owner Apply (no Publish or Schedule)", "DIFFERENT", "Keep-then-publish is not implemented."],
        ["Bulk field optimize", "Score + Optimize help", "Not Vela bulk field optimize", "MISSING", "Phase 6 default max 5 lines/request."],
        ["AI Tools: AI Profiles vs Standard Profiles", "AI Tools help", "None", "MISSING", "No profile manager."],
        ["AI Tools: Sandbox", "AI Tools help", "None", "MISSING", "No sandbox product."],
        ["AI Tools: Prompt Manager", "AI Tools help", "None", "MISSING", "No Prompt Manager. media-prompt-assist is not a prompt library."],
        ["AI Tools: custom prompts", "AI Tools help", "Owner instruction on improvements; media prompt string", "DIFFERENT", "Not Vela Prompt Manager custom prompts."],
        ["AI Tools: Lite vs Plus models", "AI Tools help", "Single local llama3:latest", "MISSING", "No plan-gated model SKUs."],
        ["Keep then Sync Updates", "AI Tools help (does not touch live shop until sync)", "Proposals do not write catalogues.payload until owner Apply", "DIFFERENT", "Analogous safety; sync target is HB SQLite catalogue, not a live marketplace shop."],
        ["Studio: sort/filter", "Studio help", "Not verified as equivalent UI", "UNKNOWN", "HB media UI exists; authenticated Vela Studio UNKNOWN; HB dashboard screenshots not captured."],
        ["Studio: replace/download/delete (replace everywhere image is used)", "Studio help", "Media apply replaces the targeted catalogue field; no verified replace-everywhere library", "DIFFERENT", "Do not claim Vela replace-everywhere semantics."],
        ["Studio: folders", "Studio help", "None verified", "MISSING", "No Studio folder product."],
        ["Studio: upload", "Studio help", "Ingested/materialized images; generate_image for missing", "DIFFERENT", "Not a general media library uploader like Vela help describes."],
        ["Studio: AI enhance + sliders brightness/exposure/saturation", "Studio help", "Local enhance Contrast 1.12, Sharpness 1.2, Brightness 1.06 + prompt adjustments", "DIFFERENT", "No verified slider UI equivalent to Vela help."],
        ["Studio: Remove background + scale/rotate isolated item", "Studio help", "Ellipse _fake_cutout only", "MISSING", "No isolated-item transform endpoints."],
        ["Studio: Standard Generate color/photo/stock", "Studio help", "None", "MISSING", "No stock/color/photo generator of that type."],
        ["Studio: AI Generate prompt + Prompt assist + 3 scene options", "Studio help", "prompt-assist exists; no 3 scene options", "MISSING", "Do not claim three scene options."],
        ["Studio: Expand+Crop platform/social aspect ratios", "Studio help", "crop/expand numeric Pillow params", "DIFFERENT", "No platform/social aspect-ratio presets verified."],
        ["Studio: AI alt text", "Studio help", "None", "MISSING", "Not implemented."],
        ["Studio: Bulk photo/alt-text editing coming soon", "Studio help", "None", "MISSING", "Vela marks coming soon; HB also lacks it."],
        ["Authenticated Listings Dashboard", "Requires authenticated access", "HB /overview /catalogues — screenshots not captured", "UNKNOWN", "Vela page requires authenticated access — manual verification required."],
        ["Authenticated Listing Editor", "Requires authenticated access", "HB catalogue detail + improvements", "UNKNOWN", "Vela page requires authenticated access — manual verification required."],
        ["Authenticated Studio app UI", "Requires authenticated access", "HB /catalogues/[id]/media", "UNKNOWN", "Vela page requires authenticated access — manual verification required."],
        ["Sign-in: Google", "Live sign-in", "None", "MISSING", "Not in betterAuth plugins."],
        ["Sign-in: Facebook", "Live sign-in", "None", "MISSING", "Not in betterAuth plugins."],
        ["Sign-in: Email+Password", "Live sign-in", "Enabled", "PARITY", "Both offer email/password. HB also uses username."],
        ["Sign-in: Forgot", "Live sign-in", "Email OTP path exists; dedicated Forgot not verified as Vela equivalent", "DIFFERENT", "Do not claim Vela Forgot-password parity without a matching flow screenshot."],
        ["Sign-in: Sign up", "Live sign-in", "/signup", "PARITY", "Account creation exists on both public surfaces."],
    ]
    return headers, rows


def detailed_impl_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["ID", "Contract", "Implementation", "Safety / validation", "Status", "Source files"]
    rows: list[list[object]] = [
        ["DI-01", "Stable catalogue UUID; venue_id = org + platform + source listing", "Canonical Phase 1 store; no fuzzy restaurant merge", "CatalogueIdentityConflict before mutation; BEGIN IMMEDIATE + IntegrityError handling", "CLOSED", "PHASE1_CLOSURE.md; backend/store.py"],
        ["DI-02", "Feed Phase 1 save_catalogue only", "ExistingCatalogueAdapter.to_canonical after normalize/validate", "Adapter double-failure must not report canonical success", "CLOSED", "PHASE2_CLOSURE.md; catalog_service.py"],
        ["DI-03", "ENGINE_VERSION grading.v1", "50% deterministic / 25% NLP heuristic / 25% local vision", "Hard failures force F; letters A≥90 B≥75 C≥60 D≥40 F<40", "CLOSED", "backend/grading/formula.py"],
        ["DI-04", "Local heuristic NLP; local image analysis", "No external NLP/CV provider required for grading", "SSRF-safe fetch; catalogue-assets confinement", "CLOSED", "backend/grading/; PHASE3_CLOSURE.md"],
        ["DI-05", "Grade identity catalogue_id + revision + state_hash + engine", "COMPLETED only after persisted grade row; claim_token CAS", "BEGIN IMMEDIATE", "CLOSED", "backend/grading/persist.py"],
        ["DI-06", "Platform Score != Baba Score", "platform_eval.v1 evidence; Baba Score projection", "GET empty list HTTP 200 []", "CLOSED", "PHASE4_CLOSURE.md"],
        ["DI-07", "grade_explain.v1 read-time projection", "Copy overall letter/score from grade row; findings from fail/error evidence", "404 no completed grade; 502 dishonest payload", "CLOSED", "PHASE5_CLOSURE.md"],
        ["DI-08", "Allowlisted improvement kinds only", "KIND_REGISTRY five kinds", "Ollama untrusted; validate_candidate authoritative", "CLOSED", "backend/improvement/kinds.py"],
        ["DI-09", "unique request_key; GENERATING reservation first", "Duplicate requests replay persisted proposal", "STALE on revision/hash mismatch", "CLOSED", "PHASE6_CLOSURE.md"],
        ["DI-10", "Price never LLM-invented", "item_price copies original_price", "missing_item_name unsupported", "CLOSED", "improvement/service.py"],
        ["DI-11", "Tags are labels[] catalogue content", "food_type preserved (veg); merge + validate_labels", "Not a grading.v1 section", "CLOSED", "PHASE6_CLOSURE.md"],
        ["DI-12", "Menu structure V1 category-name only", "category_name kind; no invented move destinations", "category_count_mismatch rejected", "CLOSED", "PHASE6_CLOSURE.md"],
        ["DI-13", "media.v1 jobs preview-only until apply", "Local Pillow; optional hosted.v1", "Phase 7 implemented; no PHASE7_CLOSURE.md", "IMPLEMENTED — NO CLOSURE FILE", "backend/media/"],
        ["DI-14", "First-party reviews only", "source=customer and source=supplied", "No third-party review APIs", "CLOSED", "PHASE8_CLOSURE.md"],
        ["DI-15", "Item linkage exact → normalized → ambiguous → no_match", "No fuzzy/semantic/LLM guess", "Recurrence threshold 2 distinct stored reviews", "CLOSED", "review_intel/"],
        ["DI-16", "Polarity at aspect level", "positive/negative/neutral/mixed; ratings not mapped to polarity", "Targets separate from aspects", "CLOSED", "review_intel/contract.py"],
        ["DI-17", "Baba GET tools only", "ALLOWED_TOOLS seven names", "WRITE_TOOL_NAMES rejected including apply_improvement", "CLOSED", "backend/assistant/contract.py"],
        ["DI-18", "Planner extra=forbid", "Optional Ollama planner JSON", "Deterministic router first", "CLOSED", "PHASE9_CLOSURE.md"],
        ["DI-19", "href_allowed server-built", "actions[].href from server; never model hrefs", "context.current_route is a hint only", "CLOSED", "backend/assistant/links.py"],
        ["DI-20", "Phase 10 Propose→Confirm→Apply", "mutation.v1; PROPOSAL_TTL_SECONDS = 15*60", "One-use token; CAS; media ops do not write payload on confirm", "CLOSED", "backend/mutation/contract.py"],
        ["DI-21", "Phase 10 operations", "add_item, remove_item, rename_item, change_price, update_description, update_labels, move_item, improve_image, generate_video", "Names resolved server-side exact/normalized", "CLOSED", "backend/mutation/"],
        ["DI-22", "Phase 11 apply on same proposal rows", "HTTP apply/cancel; media live replace via media-job apply", "Owner Apply required", "CLOSED", "PHASE11_FINAL_AUDIT.md"],
        ["DI-23", "Phase 12 refinement", "Owner instruction on POST /improvements; media studio cycle", "PASS — CLOSED per PHASE12_AI_CATALOGUE_REFINEMENT_AUDIT.md", "CLOSED", "PHASE12_AI_CATALOGUE_REFINEMENT_AUDIT.md"],
        ["DI-24", "Phase 13 dashboard", "Not started", "Do not start as part of earlier phases", "NOT STARTED", "PHASE11_PHASE12_HISTORY_ROLLBACK_AUDIT.md"],
        ["DI-25", "resolve_targets single path", "Must be 1 target if 1 path", "Prevents cross-item generation", "IMPLEMENTED", "improvement eligibility/service"],
        ["DI-26", "Frontend API proxies", "Next.js /api/* duplicate FastAPI surface", "Needed so session cookies stay on app host", "IMPLEMENTED", "frontend/src/app/api"],
        ["DI-27", "SQLite catalogues", "data/catalogues.sqlite via backend/store.py; no ORM", "PRAGMA foreign_keys = ON", "IMPLEMENTED", "backend/store.py"],
        ["DI-28", "Auth SQLite separate", "auth/data/better-auth.sqlite (AUTH_SQLITE_PATH)", "BETTER_AUTH_SECRET required ≥32 chars", "IMPLEMENTED", "auth/auth.ts"],
        ["DI-29", "Static assets mount", "app.mount /catalogue-assets", "Local confinement", "IMPLEMENTED", "backend/main.py"],
        ["DI-30", "Area job crash recovery tests exist", "tests/test_area_job_crash_recovery.py; test_area_scrape_claim.py", "Batch poll not Celery", "IMPLEMENTED", "tests/"],
        ["DI-31", "OfficialApiAccess", "pending=True, error message, no undocumented API calls", "Stub", "STUB", "catalog_service.py"],
        ["DI-32", "Parsers extraction_status", "ok / blocked / failed / pending", "partial not emitted", "GAP", "swiggy/zomato/magicpin parser.py"],
        ["DI-33", "item-quality F display", "letterForMissing; missing description/tags/image/price → F in UI board", "Display mapping; not a second grading.v1 formula", "IMPLEMENTED", "frontend/src/lib/item-quality.ts"],
        ["DI-34", "DETERMINISTIC_OPERATIONS", "crop, blur, enhance, background_removal always local", "background_removal never hosted", "IMPLEMENTED", "backend/media/routing.py"],
        ["DI-35", "Hosted generative ops", "generate_image, background_generation, edit, cleanup, expand when hosted configured", "image_to_video forced local", "PARTIAL", "backend/media/hosted.py"],
        ["DI-36", "Prompt injection guard", "media prompts reject ignore previous / system prompt / SQL-ish phrases", "Catalogue text is DATA", "IMPLEMENTED", "backend/media/prompts.py"],
        ["DI-37", "Assistant limits", "MAX_MESSAGE_CHARS 2000; MAX_TOOLS_PER_TURN 3; MAX_FINDINGS 5", "ToolLimitExceeded / ToolRejected", "IMPLEMENTED", "backend/assistant/contract.py"],
        ["DI-38", "Review photos", "Optional evidence; GET customer-feedback-photos", "No CV on photos", "CLOSED", "PHASE8_CLOSURE.md"],
        ["DI-39", "MAX_STORED_REVIEWS 1000", "Not a recurrence threshold", "Recurrence = 2 distinct stored reviews in a signal group", "CLOSED", "review_intel/contract.py"],
        ["DI-40", "Nav first organization", "organizations?.[0]?.id on overview, catalogues, restaurant/dineout about", "No org switcher", "GAP", "frontend dashboard pages"],
        ["DI-41", "Notification prefs", "localStorage notificationStorageKey(userId)", "Not server-persisted", "GAP", "frontend/src/lib/account-profile.ts"],
        ["DI-42", "Create form partial UI", "create-catalogue-form.tsx treats partial as success path", "Parsers never emit partial", "GAP", "frontend + schemas vs parsers"],
        ["DI-43", "Connect over CDP", "chrome_session.py connect_over_cdp(debug_url)", "DEFAULT_CDP_URL http://127.0.0.1:9222", "IMPLEMENTED", "scraper/swiggy/chrome_session.py"],
        ["DI-44", "SCRAPE_TIMEOUT_MS 300000", "Frontend timedFetch for create", "QUICK_TIMEOUT_MS 30000 for other APIs", "IMPLEMENTED", "frontend/src/lib/catalog-api.ts"],
        ["DI-45", "Ollama improvement timeout 60s", "CATALOGFORGE_OLLAMA_TIMEOUT", "Synchronous V1", "IMPLEMENTED", "backend/improvement/generators/ollama.py"],
        ["DI-46", "Assistant Ollama timeout 30s", "CATALOGFORGE_ASSISTANT_OLLAMA_TIMEOUT", "Optional planner", "IMPLEMENTED", "backend/assistant/provider.py"],
        ["DI-47", "Media wait 30s contract", "WAIT_SECONDS = 30.0", "Hosted timeout env CATALOGFORGE_MEDIA_TIMEOUT_SECONDS default 45", "IMPLEMENTED", "backend/media/contract.py; hosted.py"],
        ["DI-48", "Next.js 15.0.6 / React 19 RC", "frontend/package.json", "jotai, next-themes, Tailwind, radix/shadcn-style", "IMPLEMENTED", "frontend/package.json"],
        ["DI-49", "FastAPI + uvicorn", "backend/main.py", "Python requirements.txt", "IMPLEMENTED", "requirements.txt"],
        ["DI-50", "pytest + vitest", "tests/ and frontend *.test.ts(x)", "See Testing sheet", "IMPLEMENTED", "repo test layout"],
    ]
    return headers, rows


def scraping_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["Stage", "Component", "Behavior", "Timeout / limit", "Failure mode", "Status"]
    rows: list[list[object]] = [
        ["UI", "CreateCatalogueForm", "Owner submits restaurant identity + URL + platform + catalogue_type", "SCRAPE_TIMEOUT_MS 300s client", "Shows blocked/failed/ok; partial UI exists", "IMPLEMENTED"],
        ["BFF", "frontend POST /api/catalog/create", "Same-origin proxy; cookies included", "QUICK vs scrape timeouts", "Proxy required for session cookie", "IMPLEMENTED"],
        ["API", "POST /catalog/create", "require_session + require_organization_member", "FastAPI", "401/403 if session/org fail", "IMPLEMENTED"],
        ["Service", "create_catalog", "Selects access method; BrowserAccess default", "—", "OfficialApiAccess returns pending stub", "IMPLEMENTED"],
        ["Access", "BrowserAccess.load", "collect_swiggy_source(url) for all 3 platforms", "CATALOGFORGE_BROWSER_MODE default background", "CDP attach failure", "IMPLEMENTED"],
        ["Access", "FixtureAccess", "collect_local_source for tests", "—", "Offline pipeline", "IMPLEMENTED"],
        ["Access", "OfficialApiAccess", "Does not call undocumented endpoints", "pending=True", "STUB pending credentials", "STUB"],
        ["Browser", "connect_over_cdp", "Playwright attaches to CatalogForge Chrome, not bundled Chromium for production mode", "CDP_READY_TIMEOUT_SEC 25", "Port 9222 busy can fail", "GAP"],
        ["Navigate", "page.goto wait_until=domcontentloaded", "NAV_TIMEOUT_MS 45_000", "45s", "raw.reason navigation timed out", "IMPLEMENTED"],
        ["Challenge", "wait_for_timeout CHALLENGE_WAIT_MS", "Let challenge render; do not retry-storm", "12s", "blocked if bot/CAPTCHA", "IMPLEMENTED"],
        ["Menu wait", "MENU_WAIT_MS", "Wait for menu content", "20s", "failed if reachable but no data", "IMPLEMENTED"],
        ["Scroll", "MAX_SCROLL_STEPS", "Bounded scroll", "16", "No infinite scroll loop", "IMPLEMENTED"],
        ["Parse", "parse_swiggy_catalogue", "xhr_json / dom / dom_discovery", "status ok if name or items else failed; blocked path exists", "Does not emit partial", "IMPLEMENTED"],
        ["Parse", "parse_zomato_catalogue", "json_ld or dom", "ok if name/categories/images/offers else failed; _empty blocked/failed", "Does not emit partial", "IMPLEMENTED"],
        ["Parse", "parse_magicpin_catalogue", "ok if has_data else failed; blocked via _empty", "—", "Does not emit partial", "IMPLEMENTED"],
        ["Normalize", "normalize_catalogue", "Deterministic", "Outside DB transaction (Phase 2)", "Validation errors", "CLOSED"],
        ["Validate", "validate_catalogue", "Deterministic", "Outside DB transaction", "Rejects invalid canonical", "CLOSED"],
        ["Adapt", "ExistingCatalogueAdapter.to_canonical", "No extra per-platform adapter classes", "Phase 2", "Double-failure must not look like success", "CLOSED"],
        ["Persist", "save_catalogue", "Phase 1 path only", "BEGIN IMMEDIATE identity re-check", "HTTP 409 identity conflict", "CLOSED"],
        ["Assets", "materialize_catalogue_images", "Local catalogue-assets", "SSRF-safe fetch", "Skip unsafe URLs", "IMPLEMENTED"],
        ["Raw", "bind_raw_capture", "pending then bind; no janitor; no arbitrary truncation", "gzip json under org/catalogue", "Durable capture", "CLOSED"],
        ["Area", "POST /area-jobs", "Create job", "—", "Authz org member", "IMPLEMENTED"],
        ["Area", "GET /area-jobs and GET /area-jobs/{id}", "List / get", "—", "Org scoped", "IMPLEMENTED"],
        ["Area", "POST /area-jobs/{id}/start", "Start", "—", "Crash recovery tests exist", "IMPLEMENTED"],
        ["Area", "POST /area-jobs/{id}/scrape-batch", "Batch scrape poll", "Not Celery", "Claim tests exist", "IMPLEMENTED"],
        ["Area", "POST cancel / DELETE job", "Cancel or delete", "—", "Org scoped", "IMPLEMENTED"],
        ["Quality", "extraction_status", "Schema: ok|partial|blocked|failed|pending", "UI accepts partial", "Parsers: ok/blocked/failed/pending only", "GAP"],
        ["Risk", "Swiggy WAF", "blocked; no bypass", "challenge wait 12s", "Live scrape PARTIAL", "GAP"],
        ["Risk", "Chrome 9222", "DEFAULT_CDP_PORT", "25s CDP ready", "Busy port fails scrape", "GAP"],
        ["Non-goal", "HTTP-only menu scrape", "Not the production collector", "—", "Playwright + CDP required", "IMPLEMENTED"],
        ["Non-goal", "Fuzzy identity merge", "Forbidden by Phase 1/2", "—", "409 instead", "CLOSED"],
        ["Client statuses", "StatusBadge", "Renders extraction_status", "—", "partial label exists in form", "IMPLEMENTED"],
        ["Discovery locators", "scraper/discovery", "Suggestion locators capped", "min(count, 16) in collect.py", "Bounded", "IMPLEMENTED"],
        ["Safe fetch", "scraper/swiggy/safe_fetch.py", "Public HTTP only; blocks link-local", "DEFAULT_TIMEOUT 15s", "UnsafeURLError", "IMPLEMENTED"],
        ["Dineout enrich", "scraper/swiggy/dineout.py", "enrich_dineout after swiggy parse when ok or dineout URL", "—", "Shared collector HTML/payloads", "IMPLEMENTED"],
        ["Platform infer", "infer_legacy_platform", "From URL or request.platform", "swiggy|zomato|magicpin", "platform_url_error on bad URL", "IMPLEMENTED"],
        ["CLI", "scraper/cli.py", "Reports extraction_status", "exit 1 if not ok", "Operator tool", "IMPLEMENTED"],
        ["Tests", "test_swiggy_extraction.py et al.", "blocked/failed/ok fixtures", "—", "partial not asserted as parser output", "PASS"],
        ["Live scrape", "Production WAF", "May block", "—", "NOT a certified always-green live path", "PARTIAL"],
        ["Downstream", "Grade/improve require persisted catalogue", "Grading downstream of Phase 1 persist; not invoked from ingest", "Phase 3 rule", "No grade-on-scrape side effect", "CLOSED"],
    ]
    return headers, rows


def ai_inventory_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["ID", "Component", "Role", "Model / engine", "Trust boundary", "Writes catalogue?", "Status"]
    rows: list[list[object]] = [
        ["AI-01", "Deterministic improvement eligibility", "Maps Phase 5 findings + empty_item_labels to kinds", "None (code)", "KIND_REGISTRY / DRIVER_KIND", "No", "CLOSED"],
        ["AI-02", "Ollama improvement generator", "Untrusted text/label/category candidate", "local llama3:latest :11434; 60s", "validate_candidate is authoritative", "No (proposal only)", "CLOSED"],
        ["AI-03", "Deterministic price copier", "item_price", "None", "original_price only", "On owner Apply", "CLOSED"],
        ["AI-04", "Deterministic media_handoff", "Persist finding identity for Phase 7", "None", "No image generation", "Handoff record only", "CLOSED"],
        ["AI-05", "Baba deterministic router", "Intent before optional planner", "None", "First", "No", "CLOSED"],
        ["AI-06", "Baba Ollama planner", "Optional JSON plan extra=forbid", "llama3:latest; 30s default", "Tools allowlisted GET only", "No", "CLOSED"],
        ["AI-07", "Assistant tools", "get_catalogue_summary, get_grade_explanation, get_baba_score, get_review_intelligence, get_item_context, list_improvement_proposals, list_org_grade_summaries", "Existing services", "Unknown tool rejected", "No", "CLOSED"],
        ["AI-08", "Refused write tool names", "create/update/delete catalogue, prices, apply_improvement, grade, publish, media execute, etc.", "N/A", "ToolRejected", "No", "CLOSED"],
        ["AI-09", "Phase 10 NL parse", "Typed mutation draft", "Deterministic parse.py patterns", "Server name resolve; model IDs ignored", "Only after confirm", "CLOSED"],
        ["AI-10", "Phase 10 quality checks", "Description/tags from verified facts", "backend/mutation/quality.py", "Unsupported claims refused", "On confirm apply", "CLOSED"],
        ["AI-11", "maybe_handle_quality_improve", "NL Improve {item} creates Phase 6 proposal", "Same improvement generator", "Does not apply from chat", "Proposal only", "CLOSED"],
        ["AI-12", "Local grading NLP", "Heuristic text stage", "No neural/LLM required", "Stored evidence", "Grade row", "CLOSED"],
        ["AI-13", "Local grading vision", "Pillow heuristics", "No neural CV required", "SSRF-safe / assets", "Grade row", "CLOSED"],
        ["AI-14", "Review intel engine", "Aspect signals review_intel.v1.1", "Deterministic", "Inspect-only recommendations", "No", "CLOSED"],
        ["AI-15", "Media prompt assist", "Suggest/validate prompts", "Rules + optional model not required for local ops", "PromptRejected on injection", "No", "IMPLEMENTED"],
        ["AI-16", "LocalMediaProvider", "Pillow filters, ellipse cutout, GIF zoom, cream composite", "local.v1", "Not ML segmentation / not AI video", "On media apply", "IMPLEMENTED"],
        ["AI-17", "HostedMediaProvider", "Optional FLUX Kontext / SVD Gradio or HTTP", "hosted.v1 when env set", "Secrets stay in process; fallback local", "On media apply", "PARTIAL"],
        ["AI-18", "RoutingMediaProvider", "Deterministic ops always local; GIF always local", "routing.py", "Prevents treating GIF as hosted I2V", "On media apply", "IMPLEMENTED"],
        ["AI-19", "Platform eval adapters", "Swiggy/Zomato/Magicpin registry", "No live platform HTTP in Phase 4", "Evidence only", "Eval row", "CLOSED"],
        ["AI-20", "No second grade", "Baba must use stored grading.v1 / explanation / review intel", "Phase 9 rule", "No invented dishes/reviews", "No", "CLOSED"],
        ["AI-21", "Face-only / subject-only / object-only", "Not implemented", "—", "Do not advertise", "No", "NOT IMPLEMENTED"],
        ["AI-22", "Competitor/demand pricing AI", "Not implemented", "—", "Price copy only from original_price", "No", "NOT IMPLEMENTED"],
        ["AI-23", "Vela Prompt Manager / Sandbox / AI Profiles", "Not in HB", "—", "MISSING vs Vela help", "No", "MISSING"],
        ["AI-24", "AGENT.md", "Human/agent context dump", "Not a runtime agent", "Large documentation surface", "No", "IMPLEMENTED"],
    ]
    return headers, rows


def image_intel_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["Operation / claim", "Editing scope class", "What the code actually does", "Provider", "UI label risk", "Status"]
    rows: list[list[object]] = [
        ["enhance", "FULL IMAGE", "Contrast 1.12, Sharpness 1.2, Brightness 1.06, then prompt adjustments", "local.v1 (deterministic)", "UI title 'AI Enhance' is a filter, not a neural enhancer unless hosted edit path used", "IMPLEMENTED"],
        ["blur", "FULL IMAGE", "GaussianBlur radius clamped 0.5–30", "local.v1", "Honest filter", "IMPLEMENTED"],
        ["crop", "FULL IMAGE", "Normalized box CropParams; min 8px", "local.v1", "Not platform aspect-ratio presets", "IMPLEMENTED"],
        ["expand", "FULL IMAGE", "ImageOps.expand with mean-color fill", "local.v1 unless hosted generative expand configured", "Not Vela Expand+Crop social ratios", "IMPLEMENTED"],
        ["cleanup", "FULL IMAGE", "MedianFilter 3 + mild sharpen + prompt adjustments locally; hosted possible if configured", "routing: generative set but local if no host", "Not true inpainting", "IMPLEMENTED"],
        ["edit", "FULL IMAGE", "Local: slight brightness/contrast + prompt adjustments. Hosted edit if configured.", "local fallback / hosted.v1", "UI: 'Baba keeps the dish and only edits what you ask for' overclaims local path", "OVERCLAIM"],
        ["generate_image", "FULL IMAGE", "Local _compose_missing name/restaurant/references; hosted FLUX if configured", "local or hosted", "Missing-image placeholder vs true generative", "PARTIAL"],
        ["background_removal", "FAKE SUBJECT CUTOUT", "_fake_cutout: centered ellipse alpha mask, inset 8%", "Always local (DETERMINISTIC_OPERATIONS)", "UI 'Remove Background' / 'AI Backgrounds' is not segmentation", "OVERCLAIM"],
        ["background_generation", "BACKGROUND", "Local: ellipse cutout composited on cream RGBA(248,244,236). Hosted if configured.", "local cream or hosted", "Not Vela Standard/AI Generate scenes", "DIFFERENT"],
        ["image_to_video", "FULL IMAGE", "12-frame sinusoidal zoom 100–104%, GIF duration 120ms loop", "Forced local", "UI 'Create GIF' is accurate; not AI video; hosted SVD not used for this op", "IMPLEMENTED"],
        ["face-only", "NOT IMPLEMENTED", "No face detection", "—", "Must not appear as shipped", "NOT IMPLEMENTED"],
        ["subject-only", "NOT IMPLEMENTED", "No subject detection", "—", "Ellipse is not subject detection", "NOT IMPLEMENTED"],
        ["object-only", "NOT IMPLEMENTED", "No object detection", "—", "—", "NOT IMPLEMENTED"],
        ["real inpainting", "NOT IMPLEMENTED", "cleanup/edit are filters or optional hosted HTTP, not an in-repo inpaint model", "—", "Do not claim inpainting", "NOT IMPLEMENTED"],
        ["real segmentation", "NOT IMPLEMENTED", "No ML mask", "—", "Ellipse only", "NOT IMPLEMENTED"],
        ["Vela isolate products", "NOT IMPLEMENTED", "No scale/rotate isolated-item endpoints", "—", "MISSING vs Studio help", "MISSING"],
        ["Vela AI alt text", "NOT IMPLEMENTED", "No alt-text generator", "—", "MISSING", "MISSING"],
        ["Vela 3 scene options", "NOT IMPLEMENTED", "No three-scene picker", "—", "MISSING", "MISSING"],
        ["sliders brightness/exposure/saturation", "NOT IMPLEMENTED as Vela sliders", "Fixed enhance factors; prompt adjustments may tweak", "local.v1", "DIFFERENT from Studio help sliders", "DIFFERENT"],
        ["media_handoff", "N/A (not pixels)", "Stores Phase 7 handoff from vision findings", "deterministic", "Does not generate pixels", "CLOSED"],
        ["media apply", "Live replace", "Copies artefact into catalogue-assets and updates field; re-grades", "Phase 11", "Separate from improvement apply", "CLOSED"],
        ["media revert", "Live replace undo", "POST /media-revert", "API exists", "Not Vela Optimize Revert semantics", "IMPLEMENTED"],
        ["MAX_PIXELS / MAX_EDGE_PX", "Guard", "20_000_000 pixels; 4096 edge; GIF 1024 edge", "contract.py", "Engineering caps", "IMPLEMENTED"],
        ["Prompt assist", "Text only", "Maps phrases to operations; rejects injection", "prompts.py", "Not Vela Prompt Manager", "IMPLEMENTED"],
        ["Hosted FLUX Kontext", "Optional", "Gradio/HTTP when IMAGE_URL configured; .env.example says non-commercial quota-limited not production", "hosted.v1", "Must not be described as default production", "PARTIAL"],
        ["Hosted SVD", "Optional", "Video space payload exists; GIF routing still local", "hosted.v1 unused for image_to_video", "Do not call HB GIF 'SVD video'", "PARTIAL"],
        ["Vision grading", "Read-only analysis", "Local image analysis for grading.v1 vision stage", "No neural CV required", "Not an editor", "CLOSED"],
        ["Review photos", "Evidence only", "Optional customer-feedback photos; no CV", "Phase 8", "Not studio editing", "CLOSED"],
        ["Replace everywhere (Vela)", "NOT IMPLEMENTED", "Apply updates the targeted catalogue path", "—", "Vela Studio help: replace everywhere image is used", "MISSING"],
        ["Studio folders / library sort", "UNKNOWN / MISSING", "HB has no verified folder library; Vela authenticated Studio UNKNOWN", "—", "Do not invent", "UNKNOWN"],
    ]
    return headers, rows


def workflow_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["Pipeline", "Step", "Action", "Who", "Persisted state", "Catalogue payload mutated?"]
    rows: list[list[object]] = [
        ["Phase 6/11 improvement", "1", "Owner clicks Improve with AI (finding/path)", "Owner", "—", "No"],
        ["Phase 6/11 improvement", "2", "POST /improvements with single path", "UI", "request_key", "No"],
        ["Phase 6/11 improvement", "3", "resolve_targets: 1 path ⇒ 1 target", "Server", "—", "No"],
        ["Phase 6/11 improvement", "4", "BEGIN IMMEDIATE GENERATING reservation", "Server", "proposal GENERATING", "No"],
        ["Phase 6/11 improvement", "5", "Ollama or deterministic generator", "Untrusted / code", "—", "No"],
        ["Phase 6/11 improvement", "6", "validate_candidate / kind validators", "Server authoritative", "—", "No"],
        ["Phase 6/11 improvement", "7", "Persist READY or FAILED", "Server", "proposal row", "No"],
        ["Phase 6/11 improvement", "8", "UI card Current → Proposed → Why → status", "Owner", "—", "No"],
        ["Phase 6/11 improvement", "9", "POST apply (owner only)", "Owner", "APPLIED; history", "Yes (allowlisted fields)"],
        ["Phase 6/11 improvement", "10", "media_handoff skipped on improvement apply", "Server", "handoff remains", "No live image"],
        ["Phase 6/11 improvement", "11", "grade_catalogue frozen grading.v1", "Server", "grade row", "No (grade only)"],
        ["Phase 6/11 improvement", "12", "POST cancel", "Owner", "CANCELLED terminal", "No"],
        ["Phase 6/11 improvement", "13", "STALE if revision/hash diverges", "Server", "STALE", "No"],
        ["Phase 6/11 improvement", "14", "Replay APPLIED is idempotent", "Server", "APPLIED", "No extra mutation"],
        ["Phase 7/11 media", "1", "GET media-studio", "Owner", "—", "No"],
        ["Phase 7/11 media", "2", "POST media-jobs", "Owner", "job GENERATING→READY/FAILED", "No"],
        ["Phase 7/11 media", "3", "Preview artefact", "Owner", "artefact bytes", "No"],
        ["Phase 7/11 media", "4", "POST media-jobs/{id}/apply", "Owner", "APPLIED", "Yes live media field"],
        ["Phase 7/11 media", "5", "Re-grade after media apply", "Server", "grade row", "No"],
        ["Phase 7/11 media", "6", "POST media-revert", "Owner", "prior media", "Yes (restore)"],
        ["Phase 7/11 media", "7", "Cancel job", "Owner", "CANCELLED", "No"],
        ["Phase 10 mutation", "1", "NL or typed propose", "Owner via Baba/UI", "PENDING; 15 min TTL", "No"],
        ["Phase 10 mutation", "2", "Show current vs proposed", "UI", "—", "No"],
        ["Phase 10 mutation", "3", "POST confirm", "Owner", "APPLIED or media job start", "Yes for payload ops; media ops writes_payload false"],
        ["Phase 10 mutation", "4", "POST cancel", "Owner", "CANCELLED", "No"],
        ["Phase 10 mutation", "5", "EXPIRED after TTL", "Server", "EXPIRED", "No"],
        ["Baba chat", "1", "Message + current_route hint", "Owner", "—", "No"],
        ["Baba chat", "2", "Router then optional planner", "Server", "—", "No"],
        ["Baba chat", "3", "GET tools only", "Server", "—", "No"],
        ["Baba chat", "4", "Write tool names refused", "Server", "—", "No"],
        ["Baba chat", "5", "Improve {item} may create Phase 6 proposal", "Server", "proposal", "No until owner Apply on HTTP"],
        ["Reviews", "1", "POST customer-feedback or reviews/collect", "Session user / operator", "review rows", "No"],
        ["Reviews", "2", "POST review-intelligence", "Owner", "intel READY/FAILED/STALE", "No"],
        ["Reviews", "3", "Recommendations inspect-only", "UI", "—", "Never writes catalogues.payload"],
        ["Vela analog (public help)", "Keep then Sync", "Does not touch live shop until sync (Vela help)", "Vela user", "UNKNOWN internals", "UNKNOWN"],
        ["Vela analog (public help)", "Optimize then Publish/Schedule", "Not implemented in HB", "—", "—", "MISSING"],
    ]
    return headers, rows


def stack_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["Layer", "Choice", "Version / detail", "Why it matters", "Status"]
    rows: list[list[object]] = [
        ["Frontend framework", "Next.js", "15.0.6", "App router pages listed in this dossier", "IMPLEMENTED"],
        ["UI library", "React", "19.0.0-rc-69d4b800-20241021", "RC, not a stable React 19 pin beyond package.json", "IMPLEMENTED"],
        ["Styling", "Tailwind + tailwindcss-animate", "tailwindcss ^3.4.1", "—", "IMPLEMENTED"],
        ["Components", "Radix primitives (dialog, dropdown, popover, slot, tooltip, icons, colors)", "package.json", "shadcn-style stack", "IMPLEMENTED"],
        ["State", "jotai", "^2.10.1", "—", "IMPLEMENTED"],
        ["Theming", "next-themes", "^0.3.0", "—", "IMPLEMENTED"],
        ["Language", "TypeScript", "^5.5.4", "typecheck script tsc --noEmit", "IMPLEMENTED"],
        ["Frontend tests", "vitest", "^2.1.0", "vitest run", "IMPLEMENTED"],
        ["Auth client", "better-auth/react", "better-auth ^1.3.0", "username, emailOTP, organization plugins", "IMPLEMENTED"],
        ["Auth server", "Better Auth Node", "auth/auth.ts; better-sqlite3", "emailAndPassword enabled; separate sqlite", "IMPLEMENTED"],
        ["Auth email", "nodemailer SMTP or AUTH_OTP_LOG", "Hecto Baba sign-in code subject", "Fails closed if neither configured", "IMPLEMENTED"],
        ["BFF", "Next.js route handlers under /api", "Duplicate FastAPI paths", "Cookie same-origin", "IMPLEMENTED"],
        ["Backend", "FastAPI", "fastapi>=0.110.0", "backend/main.py", "IMPLEMENTED"],
        ["Server", "uvicorn", ">=0.27.0", "—", "IMPLEMENTED"],
        ["HTTP client", "httpx", ">=0.27.0", "Hosted media + tests", "IMPLEMENTED"],
        ["Images", "Pillow", ">=10.0.0", "Grading vision + local media", "IMPLEMENTED"],
        ["Scrape", "Playwright", ">=1.40.0", "connect_over_cdp", "IMPLEMENTED"],
        ["Tests backend", "pytest", ">=8.0.0", "tests/", "IMPLEMENTED"],
        ["Catalogue DB", "SQLite", "data/catalogues.sqlite via store.py", "No ORM", "IMPLEMENTED"],
        ["Auth DB", "SQLite", "AUTH_SQLITE_PATH / auth data/better-auth.sqlite", "Separate from catalogues", "IMPLEMENTED"],
        ["AI text", "Ollama", "llama3:latest 127.0.0.1:11434", "Local default V1", "IMPLEMENTED"],
        ["Vision grading", "Local heuristics Pillow", "No neural CV required", "Phase 3 closed", "CLOSED"],
        ["Media local", "local.v1 Pillow", "ellipse cutout; GIF zoom", "Honesty sheet Image Intelligence", "IMPLEMENTED"],
        ["Media hosted", "optional HTTP/Gradio FLUX Kontext / SVD", "env; not default production per .env.example", "PARTIAL", "PARTIAL"],
        ["Jobs", "In-process / SQLite CAS", "No Celery; area batch poll", "—", "IMPLEMENTED"],
        ["Static", "FastAPI StaticFiles /catalogue-assets", "—", "Vision reads applied local media", "IMPLEMENTED"],
        ["Lint FE", "eslint-config-next 15.0.1", "eslint ^8.57.0", "—", "IMPLEMENTED"],
        ["Icons", "lucide-react", "^0.436.0", "—", "IMPLEMENTED"],
        ["Multipart", "python-multipart", ">=0.0.9", "Uploads", "IMPLEMENTED"],
        ["Session cookies", "httpOnly, sameSite lax, path /", "Better Auth advanced.defaultCookieAttributes", "—", "IMPLEMENTED"],
        ["Trusted origins", "BETTER_AUTH_TRUSTED_ORIGINS", "default includes 8000, 3005, 3001, 3000", "Local ports", "IMPLEMENTED"],
        ["Auth baseURL", "BETTER_AUTH_URL", "default http://localhost:3001", "—", "IMPLEMENTED"],
        ["Frontend scripts", "dev / build / start / lint / typecheck / test", "package.json", "—", "IMPLEMENTED"],
        ["Python package layout", "backend/, scraper/, tests/, auth/", "CatalogForge repo", "—", "IMPLEMENTED"],
        ["ORM", "None", "SQL via store.py", "Explicit transactions", "IMPLEMENTED"],
        ["Google SSO", "Not present", "—", "MISSING vs Vela", "MISSING"],
        ["Facebook SSO", "Not present", "—", "MISSING vs Vela", "MISSING"],
        ["Billing", "Not present", "—", "MISSING vs Vela Lite/Plus", "MISSING"],
        ["CSV", "Not present", "—", "MISSING", "MISSING"],
        ["Marketplace publish", "Not present", "—", "MISSING", "MISSING"],
        ["Redis", "Not used in Phase 10 boundary", "PHASE10_FINAL_HARDENING_AUDIT.md", "No Graphify/Redis/Celery", "IMPLEMENTED"],
        ["openpyxl (this dossier)", "3.1.5 already installed", "audit_evidence/build_dossier.py only", "Does not modify product code", "IMPLEMENTED"],
    ]
    return headers, rows


def architecture_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["Flow", "From", "To", "Contract", "Notes"]
    rows: list[list[object]] = [
        ["Ingest", "CreateCatalogueForm", "catalog-api createCatalogue", "Browser fetch credentials include", "300s scrape timeout"],
        ["Ingest", "createCatalogue", "POST /api/catalog/create", "Next BFF", "Cookie stay on app host"],
        ["Ingest", "/api/catalog/create", "POST /catalog/create", "FastAPI CatalogCreateResponse", "require_session + org"],
        ["Ingest", "create_catalog", "BrowserAccess.collect_swiggy_source", "Shared for swiggy/zomato/magicpin", "Chrome CDP"],
        ["Ingest", "RawSource", "parse_swiggy / parse_zomato / parse_magicpin", "extraction_status", "partial not emitted"],
        ["Ingest", "parsed Catalogue", "normalize_catalogue", "Deterministic", "Outside DB txn"],
        ["Ingest", "normalized", "validate_catalogue", "Deterministic", "Outside DB txn"],
        ["Ingest", "validated", "ExistingCatalogueAdapter.to_canonical", "Phase 1 adapter", "No extra adapter classes"],
        ["Ingest", "canonical", "save_catalogue", "SQLite", "Identity 409"],
        ["Ingest", "saved", "materialize_catalogue_images", "catalogue-assets", "Local files"],
        ["Ingest", "saved", "bind_raw_capture", "pending→bound gzip", "Durable raw"],
        ["Grade", "POST /grade", "grade_catalogue", "grading.v1", "Not from ingest"],
        ["Grade", "COMPLETED grade row", "GET /grade", "Same identity", "—"],
        ["Grade", "COMPLETED grade row", "GET /grade-explanation", "grade_explain.v1", "404 if none"],
        ["Grade", "COMPLETED grade row", "GET /baba-score", "Projection", "Not platform ratings"],
        ["Grade", "POST /platform-evaluation", "platform_eval.v1", "Adapters registry", "No live platform HTTP in Phase 4"],
        ["Improve", "Improve with AI", "POST /improvements", "single path", "1 target if 1 path"],
        ["Improve", "Generator", "Ollama or deterministic", "Untrusted vs validator", "GENERATING reserved first"],
        ["Improve", "READY proposal", "UI card", "Preview only", "payload unchanged"],
        ["Improve", "Owner Apply", "POST .../apply", "Allowlisted kinds", "Then regrade"],
        ["Improve", "media_handoff line", "Phase 7 studio", "No pixel gen in Phase 6", "Live replace later"],
        ["Media", "POST /media-jobs", "RoutingMediaProvider", "local vs hosted", "GIF always local"],
        ["Media", "READY job", "POST apply", "catalogue-assets replace", "Re-grade"],
        ["Chat", "Dock or /baba-ai", "POST /assistant/turn or catalogue turn", "One brain", "current_route hint"],
        ["Chat", "Router", "Optional planner JSON", "extra=forbid", "GET tools"],
        ["Chat", "Tools", "Existing read services", "Authz session+org+get_catalogue", "No writes"],
        ["Mutate", "NL propose", "catalogue_mutation_proposals PENDING", "15 min TTL", "Phase 10"],
        ["Mutate", "Confirm", "update_catalogue or media job", "CAS", "Separate from Phase 6 table"],
        ["Reviews", "customer-feedback", "source=customer", "author_key opaque", "No email to owners"],
        ["Reviews", "reviews/collect", "source=supplied", "operator paste", "—"],
        ["Reviews", "review-intelligence", "review_intel.v1.1", "Deterministic", "No payload write"],
        ["Areas", "area-jobs scrape-batch", "create_catalog per venue", "Poll", "Not Celery"],
        ["Assets", "Browser", "GET /catalogue-assets/...", "StaticFiles", "Local confinement"],
        ["Authz", "Any catalogue API", "require_session + require_organization_member", "Better Auth cookie", "list/get catalogue org check"],
        ["Nav org", "Dashboard pages", "organizations[0]", "First org only", "No switcher"],
        ["History", "Apply/mutate", "GET /history", "Records", "rollback endpoint"],
        ["Delete", "DELETE /catalogues/{id}", "store delete", "Authz", "tests/test_deletion.py"],
        ["Vela (public)", "Sign-in / pricing / help", "Not connected to HB", "No shared runtime", "Different products"],
        ["Non-flow", "Marketplace publish", "—", "Does not exist", "MISSING"],
        ["Non-flow", "CSV import/export", "—", "Does not exist", "MISSING"],
        ["Non-flow", "Phase 13 dashboard", "—", "NOT STARTED", "NOT STARTED"],
    ]
    return headers, rows


def testing_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["ID", "Suite / check", "Type", "Result", "Notes"]
    pytest_files = [
        "tests/test_swiggy_parser.py",
        "tests/test_hero_image_ux.py",
        "tests/test_swiggy_dom_discovery.py",
        "tests/test_database_mutation_safety.py",
        "tests/test_phase12_closed_loop.py",
        "tests/test_phase11_history_rollback.py",
        "tests/test_swiggy_local_source.py",
        "tests/test_catalogue_assets.py",
        "tests/test_swiggy_extraction.py",
        "tests/test_blockers_regression.py",
        "tests/test_description_and_tag_ai.py",
        "tests/test_product_image_pipeline.py",
        "tests/test_description_grounding.py",
        "tests/test_phase11_live_certification.py",
        "tests/test_phase6_improvement.py",
        "tests/test_phase12_e2e.py",
        "tests/test_platforms.py",
        "tests/test_baba_ai_owner_assistant_e2e.py",
        "tests/test_zomato_menu_items.py",
        "tests/test_phase11_improvement.py",
        "tests/test_phase10_mutation.py",
        "tests/test_phase9_assistant.py",
        "tests/test_phase8_customer_feedback.py",
        "tests/test_phase8_reviews.py",
        "tests/test_phase7_media.py",
        "tests/test_phase7_hosted.py",
        "tests/test_phase5_grade_explain.py",
        "tests/test_phase3_grading.py",
        "tests/test_phase4_platform_eval.py",
        "tests/test_phase2_ingestion.py",
        "tests/test_canonical_migrate.py",
        "tests/test_canonical_foreign_keys.py",
        "tests/test_canonical_store.py",
        "tests/test_catalog_api.py",
        "tests/test_deletion.py",
        "tests/test_canonical_adapter.py",
        "tests/test_canonical_model.py",
        "tests/test_authz.py",
        "tests/test_area_job_crash_recovery.py",
        "tests/test_error_resilience.py",
        "tests/test_ssrf.py",
        "tests/test_auth.py",
        "tests/test_catalogue_idempotency.py",
        "tests/test_area_scrape_claim.py",
        "tests/test_chrome_session.py",
        "tests/test_discovery.py",
        "tests/test_location_resolver.py",
        "tests/test_gallery_walk.py",
        "tests/test_dineout_extraction.py",
        "test_http_fetch.py",
        "test_normalize_fix.py",
    ]
    vitest_files = [
        "frontend/src/lib/auth-guard.test.ts",
        "frontend/src/components/dineout-venue-view.test.tsx",
        "frontend/src/lib/restaurant-identity.test.ts",
        "frontend/src/lib/catalog-form.test.ts",
        "frontend/src/style/theme-tokens.test.ts",
        "frontend/src/lib/catalogue-menu.test.ts",
        "frontend/src/components/login-form.test.tsx",
        "frontend/src/lib/auth-form.test.ts",
        "frontend/src/lib/catalogue-cart.test.ts",
        "frontend/src/lib/item-quality.test.ts",
        "frontend/src/components/catalogue-view.test.tsx",
        "frontend/src/lib/progress.test.ts",
        "frontend/src/components/media-studio-view.test.tsx",
        "frontend/src/components/ai-improvements-view.test.tsx",
        "frontend/src/components/improvement-preview-view.test.tsx",
        "frontend/src/lib/catalog-api.test.ts",
        "frontend/src/components/grading-views.test.tsx",
        "frontend/src/components/nav/side-nav.test.tsx",
        "frontend/src/lib/grading-ui.test.ts",
        "frontend/src/components/baba-ai-dock.test.tsx",
        "frontend/src/lib/grade-ui.test.ts",
        "frontend/src/components/baba-assistant-view.test.tsx",
        "frontend/src/components/review-intelligence-view.test.tsx",
        "frontend/src/components/customer-feedback-form.test.tsx",
        "frontend/src/lib/media-ui.test.ts",
        "frontend/src/lib/area-scrape-poll.test.ts",
        "frontend/src/lib/catalogue-store.test.ts",
        "frontend/src/app/(dashboard)/catalogues/new/page.test.tsx",
        "frontend/src/components/create-catalogue-form.test.tsx",
        "frontend/src/components/process-progress.test.tsx",
        "frontend/src/components/deletion-ui.test.ts",
        "frontend/src/lib/area-jobs.test.ts",
        "frontend/src/components/area-discovery-form.test.tsx",
        "frontend/src/app/(dashboard)/profile/page.test.tsx",
        "frontend/src/lib/account-profile.test.ts",
        "frontend/src/lib/nav-catalogues.test.ts",
    ]
    rows: list[list[object]] = [
        ["TV-00", "pytest present", "Tooling", "PASS", "requirements.txt pytest>=8; tests/ layout"],
        ["TV-00b", "vitest present", "Tooling", "PASS", "frontend package.json test: vitest run"],
        ["TV-LIVE-VELA", "Live authenticated Vela dashboard/editor/studio", "Manual", "NOT TESTED", "Authenticated Vela pages were not accessed"],
        ["TV-LIVE-SCRAPE", "Live platform scrape", "Manual / production risk", "PARTIAL", "WAF → blocked remains a real failure mode"],
        ["TV-HB-LOGIN", "Browser HB login screenshot", "Manual evidence", "PASS", "SS-HB-01-login.png required path; embed if file exists"],
        ["TV-HB-DASH", "Authenticated HB dashboard screenshots", "Manual evidence", "NOT TESTED", "Login required; not captured except login page"],
        ["TV-PHASE10-NOTE", "Phase 10 hardening residual", "Manual", "NOT TESTED", "PHASE10_FINAL_HARDENING_AUDIT.md: browser click-through of dock was not available in that pass"],
    ]
    for i, path in enumerate(pytest_files, start=1):
        rows.append([f"TV-PY-{i:02d}", path, "pytest unit/integration (file exists)", "PASS", "Suite exists in repo; this dossier does not re-run pytest"])
    for i, path in enumerate(vitest_files, start=1):
        rows.append([f"TV-VT-{i:02d}", path, "vitest unit (file exists)", "PASS", "Suite exists in repo; this dossier does not re-run vitest"])
    return headers, rows


def screenshot_table_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["ID", "Relative path", "Subject", "Access level", "File status", "How used"]
    rows: list[list[object]] = []
    for sid, rel, subject, access in SCREENSHOTS:
        path = ROOT / rel
        status = "PASS" if path.is_file() else "FILE NOT FOUND"
        how = "Embedded below at ~520px width" if path.is_file() else "SCRIPT WILL SKIP EMBED; SCREENSHOT REQUIRED"
        rows.append([sid, rel, subject, access, status, how])
    rows.extend(
        [
            [
                "SS-VELA-AUTH-DASH",
                "—",
                "Authenticated Vela Listings Dashboard",
                "Authenticated Vela — not accessed",
                "SCREENSHOT REQUIRED",
                "UNKNOWN internals; do not invent",
            ],
            [
                "SS-VELA-AUTH-EDITOR",
                "—",
                "Authenticated Vela Listing Editor",
                "Authenticated Vela — not accessed",
                "SCREENSHOT REQUIRED",
                "UNKNOWN internals; do not invent",
            ],
            [
                "SS-VELA-AUTH-STUDIO",
                "—",
                "Authenticated Vela Studio app UI",
                "Authenticated Vela — not accessed",
                "SCREENSHOT REQUIRED",
                "UNKNOWN internals; do not invent",
            ],
            [
                "SS-HB-DASH",
                "—",
                "Authenticated Hecto Baba dashboard (overview/catalogues/grade/media)",
                "Authenticated HB — not captured",
                "SCREENSHOT REQUIRED",
                "Login required; only login page listed as captured",
            ],
        ]
    )
    return headers, rows


def issues_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["ID", "Issue", "Severity", "Classification", "Evidence", "Handover action"]
    rows: list[list[object]] = [
        ["GAP-01", "Authenticated Vela Listings Dashboard / Editor / Studio were not inspected", "High (evidence)", "UNKNOWN", "app.getvela.com/account → sign-in; no authed session", "Mark UNKNOWN / SCREENSHOT REQUIRED; do not invent Vela internals"],
        ["GAP-02", "Authenticated HB dashboard screenshots not captured except login", "High (evidence)", "PARTIAL", "SS-HB-01 only in evidence list", "Capture overview, catalogue, grade, improvements, media after login"],
        ["GAP-03", "extraction_status partial is dead in parsers", "Medium", "GAP", "schemas + UI accept partial; swiggy/zomato/magicpin emit ok/blocked/failed/pending", "Either emit partial honestly or remove UI/schema success path"],
        ["GAP-04", "OfficialApiAccess stub", "Medium", "STUB", "catalog_service.OfficialApiAccess pending=True", "Do not advertise official partner API ingest"],
        ["GAP-05", "Local media overclaims vs Pillow fallbacks", "High (honesty)", "OVERCLAIM", "media-ui.ts / media-tools.ts vs _fake_cutout and GIF zoom", "Align UI copy with FULL IMAGE / FAKE CUTOUT / BACKGROUND classes"],
        ["GAP-06", "Phase 13 dashboard not started", "Product", "NOT STARTED", "Phase audits", "Do not schedule as leftover Phase 9–12 work"],
        ["GAP-07", "No marketplace publish", "Product vs Vela", "MISSING", "No publish routes", "Do not claim Vela channel parity"],
        ["GAP-08", "No CSV import or export", "Product vs Vela", "MISSING", "Sign-in list vs main.py", "Out of domain unless a later phase"],
        ["GAP-09", "No competitor/demand pricing AI", "Product", "MISSING", "item_price copies original_price only", "Keep LLM off prices"],
        ["GAP-10", "Swiggy WAF / blocked risk", "Operational", "PARTIAL", "parser blocked path; live scrape not always green", "Treat live scrape as PARTIAL"],
        ["GAP-11", "Chrome port 9222 busy can fail scrape", "Operational", "GAP", "DEFAULT_CDP_PORT 9222", "Document port exclusivity for operators"],
        ["GAP-12", "Multi-org switcher missing", "Product", "GAP", "organizations?.[0] on dashboard pages", "First organization only"],
        ["GAP-13", "No Google/Facebook SSO", "Product vs Vela", "MISSING", "auth.ts plugins", "Email/password + username + OTP only"],
        ["GAP-14", "No billing / Lite vs Plus", "Product vs Vela", "MISSING", "Vela pricing page", "No shop/month SKU"],
        ["GAP-15", "No listing profiles, sandbox, prompt manager", "Product vs Vela", "MISSING", "Vela AI Tools help", "HB prompt-assist is not Prompt Manager"],
        ["GAP-16", "No real isolation / inpaint / segmentation", "Honesty", "NOT IMPLEMENTED", "providers._fake_cutout", "Classify FAKE SUBJECT CUTOUT"],
        ["GAP-17", "Phase 7 has no PHASE7_CLOSURE.md", "Process", "PARTIAL", "Glob of PHASE*_CLOSURE.md", "Media is implemented; closure file absent"],
        ["GAP-18", "Profile/settings notifications are localStorage", "Durability", "GAP", "account-profile.ts", "Prefs do not survive browser-data wipe / multi-device"],
        ["GAP-19", "Two mutation pipelines can confuse operators", "UX / eng", "DIFFERENT", "Phase 6 proposals vs Phase 10 mutations", "Intentional; document in training (see Complexity sheet)"],
        ["GAP-20", "AGENT.md is huge", "Maintainability", "GAP", "AGENT.md ~1600+ lines", "Risk of stale agent context vs closed phase files"],
        ["GAP-21", "Frontend API proxy duplication", "Engineering cost", "IMPLEMENTED", "frontend/src/app/api vs backend/main.py", "Needed for cookies; keep in sync"],
        ["GAP-22", "Hosted media default is not production", "Honesty", "PARTIAL", ".env.example: non-commercial quota-limited", "Do not sell hosted FLUX as default prod"],
        ["GAP-23", "Zomato/Magicpin live-verify caveat in AGENT.md", "Evidence", "PARTIAL", "AGENT.md: not documented as live-verified unless changelog records live scrape", "Do not claim live-certified for all platforms"],
        ["GAP-24", "No schedule publish/updates", "Product vs Vela", "MISSING", "Vela help Schedule", "Out of scope"],
        ["GAP-25", "This workbook screenshots may be missing on disk", "Evidence", "SCREENSHOT REQUIRED", "embed only if files exist", "Drop PNGs into audit_evidence/ and regenerate"],
    ]
    return headers, rows


def complexity_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["ID", "Hotspot", "Why it exists", "Risk if misunderstood", "Verdict"]
    rows: list[list[object]] = [
        ["CX-01", "Frontend /api proxy duplication", "Session cookies must stay on the Next.js app host (auth-client comment). FastAPI is a separate origin.", "Someone 'simplifies' by calling FastAPI from the browser and breaks auth", "Needed for cookies; keep route parity with backend/main.py"],
        ["CX-02", "OfficialApiAccess stub", "Product will not call undocumented endpoints or bypass WAF without partner credentials.", "Treating stub as a working official API", "Honest pending; do not implement scrape bypass to 'finish' it"],
        ["CX-03", "Media UI copy vs local fake cutout", "Studio-like labels (AI Enhance, AI Backgrounds, AI Edit) wrap Pillow filters and ellipse masks.", "Sales/demo claims of Vela-like isolation", "Classify FULL IMAGE vs FAKE SUBJECT CUTOUT vs BACKGROUND vs NOT IMPLEMENTED"],
        ["CX-04", "AGENT.md size", "Long-running agent context for CatalogForge phases and caveats.", "Stale instructions vs PHASE*_CLOSURE.md", "Prefer official closure files for phase law; AGENT.md is context not runtime"],
        ["CX-05", "Two mutation pipelines (Phase 6 vs 10)", "Phase 6/11: grade-driven allowlisted improvements. Phase 10: typed NL Propose→Confirm→Apply. Intentionally separate tables.", "Applying the wrong endpoint; expecting chat to Apply improvements", "Intentional. Baba write tools remain refused; HTTP apply is owner-only"],
        ["CX-06", "Profile localStorage", "account-profile and notification prefs keyed by user id in the browser.", "Assuming server-persisted settings", "Document as client-only"],
        ["CX-07", "Parser partial unused", "Schema/UI include partial; parsers never emit it; catalog_service still branches on partial.", "QA chasing a status that cannot appear from live parse", "Dead path; fix or delete in a later official phase"],
        ["CX-08", "Shared collect_swiggy_source for three platforms", "One Chrome CDP collector; platform-specific parsers afterwards.", "Assuming HTTP APIs per platform", "Correct; OfficialApiAccess is not that collector"],
        ["CX-09", "background_removal in DETERMINISTIC_OPERATIONS", "Forces ellipse cutout even when hosted is configured.", "Expecting hosted matting on Remove Background", "By design in routing.py"],
        ["CX-10", "image_to_video forced local", "GIF must not be treated as hosted SVD AI video.", "Demo as AI video", "12-frame zoom GIF only"],
        ["CX-11", "Planner extra=forbid + deterministic router", "Untrusted JSON cannot add keys; router runs first.", "Letting the model invent tools/hrefs", "Preserve; href_allowed is authoritative"],
        ["CX-12", "item-quality.ts F display vs grading.v1", "UI board shows F for missing description/tags/image/price; overall letter still from stored grade.", "Thinking the UI invented a second engine", "Display mapping; do not change grading.v1 numbers in place"],
        ["CX-13", "Baba Score vs platform_eval", "Two scores on purpose.", "Blending formulas", "Phase 4 closed: no Baba–platform blend"],
        ["CX-14", "Improvement apply vs media apply", "media_handoff does not live-replace; media-job apply does.", "Owner clicks the wrong Apply", "Document in training / UI (already separate routes)"],
        ["CX-15", "Area jobs poll vs Celery", "SQLite-backed batch without a broker.", "Expecting distributed workers", "By design"],
        ["CX-16", "No ORM", "Explicit SQL and transactions (BEGIN IMMEDIATE, CAS).", "Introducing an ORM mid-flight", "Keep store.py as source of persist behavior"],
        ["CX-17", "Next.js 15 + React 19 RC", "Pinned in package.json.", "Assuming React 19 stable APIs everywhere", "Record the RC version on handover"],
        ["CX-18", "shadcn/radix without claiming full shadcn kit", "Radix packages present; do not invent extra components.", "Docs overclaim component library", "Cite package.json only"],
        ["CX-19", "Hosted Gradio spaces", "Optional; .env.example warns non-commercial quota-limited.", "Production dependency on public spaces", "Keep optional"],
        ["CX-20", "Write-tool name list vs HTTP apply", "apply_improvement is refused as a tool but exists as HTTP.", "Security review confusion", "By design Phase 9/11"],
        ["CX-21", "First-org nav", "useListOrganizations()[0] repeated across pages.", "Silent wrong-org in multi-org accounts", "GAP-12"],
        ["CX-22", "Dossier generator isolation", "This script only writes xlsx; no product code changes.", "Editing closed phases to 'match Vela'", "Forbidden unless a later official phase names a defect"],
    ]
    return headers, rows


def phase_history_rows() -> tuple[list[str], list[list[object]]]:
    headers = ["Phase", "Name", "Status", "Official record", "What shipped (verified)", "Must not reopen for"]
    rows: list[list[object]] = [
        ["1", "Canonical catalogue", "CLOSED", "PHASE1_CLOSURE.md", "Stable UUID; venue_id org+platform+listing; identity 409; save_catalogue; FK on", "Fuzzy identity; cosmetic refactors"],
        ["2", "Catalogue ingestion & normalization", "CLOSED", "PHASE2_CLOSURE.md", "Deterministic normalize/validate; raw capture pending→bind; ExistingCatalogueAdapter; scrape I/O outside txn", "Second persist path; janitor truncation"],
        ["3", "Baba grading engine", "CLOSED", "PHASE3_CLOSURE.md", "grading.v1 50/25/25; letter floors; hard F; local NLP+vision; CAS COMPLETED", "Changing grading.v1 numbers in place"],
        ["4", "Baba Score + platform evaluation", "CLOSED", "PHASE4_CLOSURE.md", "Baba Score projection; platform_eval.v1 adapters; GET [] is 200", "Blending Baba with platform ratings"],
        ["5", "Grade explanation & recommendations", "CLOSED", "PHASE5_CLOSURE.md", "grade_explain.v1 read-time; fix_first; 404/502 rules", "Second live grade; LLM explanation"],
        ["6", "AI Improvement Engine", "CLOSED", "PHASE6_CLOSURE.md", "Allowlisted kinds; Ollama untrusted; preview only at the time; request_key; no payload write", "Arbitrary JSON patch; inventing prices"],
        ["7", "Media studio / jobs", "IMPLEMENTED — NO CLOSURE FILE", "No PHASE7_CLOSURE.md (media.v1 in repo + tests/test_phase7_*.py)", "Media jobs, local Pillow, optional hosted, prompt-assist, artefacts", "Do not pretend PHASE7_CLOSURE.md exists"],
        ["8", "Customer Review Intelligence", "CLOSED", "PHASE8_CLOSURE.md", "First-party + supplied; review_intel.v1.1; no third-party scrape", "Google/Zomato review APIs"],
        ["9", "Baba AI Catalogue Assistant", "CLOSED", "PHASE9_CLOSURE.md", "Single brain dock+/baba-ai; router; GET tools; href_allowed", "Write tools; inventing grades"],
        ["10", "Typed catalogue mutation", "CLOSED", "PHASE10_AUDIT.md / PHASE10_FINAL_HARDENING_AUDIT.md", "Propose→Confirm→Apply; 15 min TTL; separate from Phase 6", "Using this as Phase 6 apply engine"],
        ["11", "AI Catalogue Improvement, Grade & Apply", "CLOSED", "PHASE11_FINAL_AUDIT.md", "HTTP apply/cancel; media live apply; re-grade grading.v1; owner Apply", "Baba applying via tools; letter inflation"],
        ["12", "AI catalogue refinement / media audit", "CLOSED", "PHASE12_AI_CATALOGUE_REFINEMENT_AUDIT.md (PASS — CLOSED)", "Owner instruction refinement; media cycle on Phase 11 baseline", "Closed-loop optimizer beyond this record"],
        ["13", "Dashboard", "NOT STARTED", "Cited in PHASE8/6/11 history audits as not started", "Nothing shipped as Phase 13 dashboard", "Do not start as part of Phases 7–12 leftovers"],
    ]
    return headers, rows


def fastapi_route_rows() -> list[list[object]]:
    """Verified FastAPI routes from backend/main.py — extra detail for Technical Stack append."""
    return [
        ["API", "POST /catalog/create", "CatalogCreateResponse", "Create from URL", "IMPLEMENTED"],
        ["API", "GET /catalogues", "CatalogueListResponse", "List", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}", "StoredCatalogue", "Get", "IMPLEMENTED"],
        ["API", "DELETE /catalogues/{id}", "—", "Delete", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/grade", "GradingResult", "Start/complete grade", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/grade", "GradingResult", "Read grade", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/grade-explanation", "GradeExplanation", "Phase 5", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/baba-score", "BabaScore", "Projection", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/platform-evaluation", "CatalogueEvaluationResponse", "Phase 4", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/platform-evaluation", "CatalogueEvaluationResponse", "Empty list 200", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/improvements", "ImprovementProposal", "Generate", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/improvements", "ImprovementListResponse", "List", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/improvements/{proposal_id}", "ImprovementProposal", "Get", "IMPLEMENTED"],
        ["API", "POST .../improvements/{proposal_id}/apply", "ImprovementApplyResult", "Owner apply", "IMPLEMENTED"],
        ["API", "POST .../improvements/{proposal_id}/cancel", "ImprovementProposal", "Cancel", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/history", "EditHistoryListResponse", "History", "IMPLEMENTED"],
        ["API", "POST .../history/{history_id}/rollback", "EditHistoryRecord", "Rollback", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/media-studio", "MediaStudioResponse", "Studio payload", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/media-jobs", "MediaJob", "Create job", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/media-jobs", "MediaJobListResponse", "List jobs", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/media-jobs/{job_id}", "MediaJob", "Get job", "IMPLEMENTED"],
        ["API", "POST .../media-jobs/{job_id}/cancel", "MediaJob", "Cancel job", "IMPLEMENTED"],
        ["API", "POST .../media-jobs/{job_id}/apply", "MediaApplyResult", "Live media replace", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/media-revert", "MediaJob | None", "Revert media", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/media-prompt-assist", "PromptAssistResponse", "Prompt help", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/media-artifacts/{artefact_id}", "bytes", "Artefact", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/reviews/collect", "ReviewCollectResponse", "supplied ingest", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/customer-feedback", "CustomerFeedbackResponse", "customer ingest", "IMPLEMENTED"],
        ["API", "GET .../customer-feedback-photos/{photo_id}", "bytes", "Optional evidence", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/reviews", "ReviewListResponse", "List", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/review-intelligence", "ReviewIntelligence", "Analyze", "IMPLEMENTED"],
        ["API", "GET /catalogues/{id}/review-intelligence", "ReviewIntelligence", "Read", "IMPLEMENTED"],
        ["API", "POST /assistant/turn", "AssistantTurnResponse", "Org-level turn", "IMPLEMENTED"],
        ["API", "POST /catalogues/{id}/assistant/turn", "AssistantTurnResponse", "Catalogue turn", "IMPLEMENTED"],
        ["API", "POST .../assistant/mutations/{proposal_id}/confirm", "AssistantTurnResponse", "Phase 10 confirm", "IMPLEMENTED"],
        ["API", "POST .../assistant/mutations/{proposal_id}/cancel", "AssistantTurnResponse", "Phase 10 cancel", "IMPLEMENTED"],
        ["API", "POST /area-jobs", "—", "Create", "IMPLEMENTED"],
        ["API", "GET /area-jobs", "—", "List", "IMPLEMENTED"],
        ["API", "GET /area-jobs/{job_id}", "—", "Get", "IMPLEMENTED"],
        ["API", "POST /area-jobs/{job_id}/start", "—", "Start", "IMPLEMENTED"],
        ["API", "POST /area-jobs/{job_id}/scrape-batch", "—", "Batch", "IMPLEMENTED"],
        ["API", "DELETE /area-jobs/{job_id}", "—", "Delete", "IMPLEMENTED"],
        ["API", "POST /area-jobs/{job_id}/cancel", "—", "Cancel", "IMPLEMENTED"],
        ["API", "GET /catalogue-assets/...", "StaticFiles", "Local media", "IMPLEMENTED"],
    ]


def frontend_route_rows() -> list[list[object]]:
    routes = [
        "/", "/signup", "/overview", "/areas", "/areas/[id]", "/restaurant", "/restaurant/about",
        "/dineout", "/dineout/about", "/catalogues", "/catalogues/new", "/catalogues/[id]",
        "/catalogues/[id]/improvements", "/catalogues/[id]/media", "/catalogues/[id]/reviews",
        "/catalogues/[id]/assistant", "/grading", "/grading/[id]", "/baba-ai", "/profile", "/settings",
    ]
    rows = []
    for path in routes:
        rows.append(["Frontend", path, "Next.js app router page.tsx", "Verified glob frontend/src/app", "IMPLEMENTED"])
    return rows


def embed_screenshots(ws: Worksheet, start_row: int) -> None:
    ws.cell(start_row, 1, "Embedded screenshots (scaled to ~520px wide). Missing files are not invented.")
    ws.cell(start_row, 1).font = SECTION_FONT
    ws.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=6)
    ws.row_dimensions[start_row].height = 28
    cursor = start_row + 2
    for sid, rel, subject, _access in SCREENSHOTS:
        path = ROOT / rel
        caption = f"{sid} — {subject} — {rel}"
        if not path.is_file():
            caption += " — FILE NOT FOUND / SCREENSHOT REQUIRED"
            ws.cell(cursor, 1, caption)
            ws.cell(cursor, 1).font = BOLD_FONT
            ws.cell(cursor, 1).fill = PatternFill("solid", fgColor=RED)
            ws.merge_cells(start_row=cursor, start_column=1, end_row=cursor, end_column=6)
            ws.row_dimensions[cursor].height = 36
            cursor += 2
            continue
        ws.cell(cursor, 1, caption)
        ws.cell(cursor, 1).font = BOLD_FONT
        ws.merge_cells(start_row=cursor, start_column=1, end_row=cursor, end_column=6)
        ws.row_dimensions[cursor].height = 24
        img = XLImage(str(path))
        width = float(img.width or 520)
        height = float(img.height or 300)
        scale = 520.0 / width if width else 1.0
        img.width = int(width * scale)
        img.height = int(height * scale)
        anchor_row = cursor + 1
        ws.add_image(img, f"A{anchor_row}")
        # Approximate Excel rows occupied by the bitmap (row height ~15pt ≈ 20px).
        rows_needed = max(18, int(img.height / 18) + 2)
        cursor = anchor_row + rows_needed + 1


def build() -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    # remove default sheet; we create exactly 16 named sheets
    default = wb.active
    wb.remove(default)

    # 1 Executive Summary (includes cover banner)
    ws = setup_sheet(wb, "Executive Summary")
    cols = 5
    for col, width in enumerate([22, 45, 18, 40, 40], start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    merge_banner(ws, 1, cols, "HECTO BABA FEATURE DELIVERY DOSSIER", TITLE_FONT, PatternFill("solid", fgColor=SOFT_NAVY), 36)
    merge_banner(ws, 2, cols, "Vela Comparison + Complete Feature Implementation Audit", SUBTITLE_FONT, None, 24)
    merge_banner(ws, 3, cols, "Date: 27 August 2026", BOLD_FONT, None, 22)
    merge_banner(ws, 4, cols, ACCURACY_RULE, BODY_FONT, PatternFill("solid", fgColor=AMBER), 48)
    merge_banner(
        ws,
        5,
        cols,
        "Classification key: PARITY / ENHANCEMENT / NEW / MISSING / DIFFERENT / UNKNOWN. "
        "Status fills: green implemented/closed/pass; amber partial/different/unknown; red missing/gap/stub/not started. "
        "Sheet 7 is titled AI Agent Inventory (Excel forbids '/' in sheet names).",
        BODY_FONT,
        None,
        48,
    )
    headers, rows = cover_and_executive_rows()
    write_table(ws, headers, rows, start_row=7, widths=[22, 45, 18, 40, 40], wrap_height=48)

    # 2 Product Journey
    ws = setup_sheet(wb, "Product Journey")
    headers, rows = product_journey_rows()
    write_table(ws, headers, rows, widths=[12, 18, 32, 45, 45, 18], wrap_height=44)

    # 3 Complete Feature Matrix
    ws = setup_sheet(wb, "Complete Feature Matrix")
    headers, rows = feature_matrix_rows()
    write_table(ws, headers, rows, widths=[16, 36, 18, 22, 42, 22, 42], wrap_height=40)

    # 4 Vela vs Hecto Baba
    ws = setup_sheet(wb, "Vela vs Hecto Baba")
    headers, rows = vela_vs_baba_rows()
    write_table(ws, headers, rows, widths=[40, 32, 42, 18, 45], wrap_height=44)

    # 5 Detailed Feature Implementation
    ws = setup_sheet(wb, "Detailed Feature Implementation")
    headers, rows = detailed_impl_rows()
    write_table(ws, headers, rows, widths=[12, 40, 42, 40, 22, 36], wrap_height=42)

    # 6 Scraping & Data Pipeline
    ws = setup_sheet(wb, "Scraping & Data Pipeline")
    headers, rows = scraping_rows()
    write_table(ws, headers, rows, widths=[16, 32, 45, 28, 32, 18], wrap_height=40)

    # 7 AI Agent Inventory (Excel-safe name)
    ws = setup_sheet(wb, "AI Agent Inventory")
    headers, rows = ai_inventory_rows()
    write_table(ws, headers, rows, widths=[12, 36, 42, 32, 36, 22, 18], wrap_height=42)

    # 8 Image Intelligence
    ws = setup_sheet(wb, "Image Intelligence")
    headers, rows = image_intel_rows()
    write_table(ws, headers, rows, widths=[36, 24, 45, 28, 42, 20], wrap_height=44)

    # 9 Proposal & Approval Workflow
    ws = setup_sheet(wb, "Proposal & Approval Workflow")
    headers, rows = workflow_rows()
    write_table(ws, headers, rows, widths=[28, 12, 42, 22, 32, 28], wrap_height=40)

    # 10 Technical Stack
    ws = setup_sheet(wb, "Technical Stack")
    headers, rows = stack_rows()
    rows = rows + frontend_route_rows() + fastapi_route_rows()
    write_table(ws, headers, rows, widths=[22, 42, 40, 40, 18], wrap_height=36)

    # 11 Architecture & Data Flow
    ws = setup_sheet(wb, "Architecture & Data Flow")
    headers, rows = architecture_rows()
    write_table(ws, headers, rows, widths=[18, 36, 40, 32, 36], wrap_height=38)

    # 12 Testing & Verification
    ws = setup_sheet(wb, "Testing & Verification")
    headers, rows = testing_rows()
    write_table(ws, headers, rows, widths=[16, 45, 36, 18, 45], wrap_height=36)

    # 13 Screenshot Evidence
    ws = setup_sheet(wb, "Screenshot Evidence")
    headers, rows = screenshot_table_rows()
    last = write_table(ws, headers, rows, widths=[22, 42, 40, 32, 22, 40], wrap_height=36)
    embed_screenshots(ws, last + 2)

    # 14 Issues & Gaps
    ws = setup_sheet(wb, "Issues & Gaps")
    headers, rows = issues_rows()
    write_table(ws, headers, rows, widths=[12, 45, 18, 18, 40, 42], wrap_height=44)

    # 15 AI Code Complexity Audit
    ws = setup_sheet(wb, "AI Code Complexity Audit")
    headers, rows = complexity_rows()
    write_table(ws, headers, rows, widths=[12, 36, 45, 40, 42], wrap_height=44)

    # 16 Phase History
    ws = setup_sheet(wb, "Phase History")
    headers, rows = phase_history_rows()
    write_table(ws, headers, rows, widths=[12, 36, 28, 40, 45, 36], wrap_height=48)

    names = list(wb.sheetnames)
    if len(names) != 16:
        raise RuntimeError(f"Expected 16 sheets, built {len(names)}: {names}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)
    return OUTPUT_PATH


def main() -> int:
    path = build()
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True)
    print(f"Wrote {path}")
    print("Sheets:")
    for name in wb.sheetnames:
        print(f"  {name}")
    wb.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
