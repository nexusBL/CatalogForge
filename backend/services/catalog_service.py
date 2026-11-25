from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from scraper.magicpin.parser import parse_magicpin_catalogue
from scraper.platform import DISPLAY, infer_legacy_platform
from scraper.swiggy.models import RawSource
from scraper.swiggy.parser import parse_swiggy_catalogue
from scraper.swiggy.scraper import collect_local_source, collect_swiggy_source
from scraper.zomato.parser import parse_zomato_catalogue

from backend.canonical.adapter import ExistingCatalogueAdapter, to_canonical_from_response
from backend.canonical.project import apply_canonical_to_response
from backend.catalogue_normalize import normalize_catalogue
from backend.catalogue_validate import validate_catalogue
from backend.raw_capture import write_pending_raw
from backend.schemas import CatalogCreateRequest, CatalogCreateResponse, ExtractionStatus

logger = logging.getLogger(__name__)

OFFICIAL_API_PENDING_MESSAGE = (
    "No authorized Swiggy partner/MCP credentials are configured. "
    "CatalogForge will not call undocumented endpoints or bypass access controls. "
    "Partner portal login and/or Swiggy Builders Club OAuth is required for official menu access."
)


@dataclass
class AccessResult:
    method: str
    raw: RawSource | None = None
    pending: bool = False
    error: str | None = None
    raw_capture_id: str | None = None


class SwiggyAccess:
    """Obtain accessible Swiggy source data. Does not parse catalogues."""

    def load(self, swiggy_url: str) -> AccessResult:
        raise NotImplementedError


class BrowserAccess(SwiggyAccess):
    """Real Chrome + CDP collector. Does not use Playwright's bundled Chromium."""

    def load(self, swiggy_url: str) -> AccessResult:
        mode = os.getenv("CATALOGFORGE_BROWSER_MODE", "background")
        raw = collect_swiggy_source(swiggy_url, browser_mode=mode)
        return AccessResult(method="catalogforge_chrome_cdp", raw=raw)


class FixtureAccess(SwiggyAccess):
    """Local HTML/JSON fixture. Used for tests and offline pipeline checks."""

    def __init__(self, json_path: str | Path | None = None, html_path: str | Path | None = None):
        self.json_path = json_path
        self.html_path = html_path

    def load(self, swiggy_url: str) -> AccessResult:
        raw = collect_local_source(swiggy_url, json_path=self.json_path, html_path=self.html_path)
        return AccessResult(method="local_fixture", raw=raw)


class OfficialApiAccess(SwiggyAccess):
    """Placeholder for authorized Swiggy APIs. Not implemented without credentials."""

    def load(self, swiggy_url: str) -> AccessResult:
        return AccessResult(method="official_api", pending=True, error=OFFICIAL_API_PENDING_MESSAGE)


def _failed(
    request: CatalogCreateRequest,
    *,
    error: str,
    access_method: str | None,
    status: ExtractionStatus = "failed",
    raw_capture_id: str | None = None,
    quality: dict | None = None,
) -> CatalogCreateResponse:
    platform = infer_legacy_platform(request.swiggy_url, getattr(request, "platform", None))
    return CatalogCreateResponse(
            extraction_status=status,
            restaurant_name=request.restaurant_name,
            fssai_number=request.fssai_number or "",
            source_url=request.swiggy_url,
            platform=platform,  # type: ignore[arg-type]
            catalogue_type=request.catalogue_type,
            restaurant=None,
            dineout=None,
            categories=[],
            item_count=0,
            image_count=0,
            error=error,
            access_method=access_method,
            raw_capture_id=raw_capture_id,
            quality=quality,
        )


def _prepare_parsed(catalogue):
    normalize_catalogue(catalogue)
    return validate_catalogue(catalogue)


def _finalize_ok(
    request: CatalogCreateRequest,
    catalogue,
    access_method: str | None,
    result: CatalogCreateResponse,
    *,
    raw_capture_id: str | None = None,
    quality: dict | None = None,
) -> CatalogCreateResponse:
    result = result.model_copy(update={"raw_capture_id": raw_capture_id, "quality": quality})
    try:
        document = ExistingCatalogueAdapter().to_canonical(catalogue, request=request, access_method=access_method)
    except Exception:
        logger.exception("Catalogue adapter failed; projecting canonical document from normalized response")
        try:
            document = to_canonical_from_response(result)
        except Exception:
            logger.exception("Canonical catalogue mapping failed")
            raise
    return apply_canonical_to_response(result, document)


def _load_parsed(
    access: SwiggyAccess,
    url: str,
    request: CatalogCreateRequest,
    platform: str = "swiggy",
    *,
    capture: bool = False,
):
    label = DISPLAY.get(platform, "Swiggy")
    try:
        obtained = access.load(url)
    except Exception as exc:
        return None, _failed(
            request,
            error=f"{label} data access failed: {type(exc).__name__}: {exc}",
            access_method=type(access).__name__,
        )
    if obtained.pending or obtained.raw is None:
        return None, _failed(
            request,
            error=obtained.error or OFFICIAL_API_PENDING_MESSAGE,
            access_method=obtained.method,
            status="pending",
        )
    if capture:
        obtained.raw_capture_id = write_pending_raw(
            organization_id=request.organization_id,
            raw=obtained.raw,
            platform=platform,
        )
    try:
        if platform == "zomato":
            parsed = parse_zomato_catalogue(obtained.raw)
        elif platform == "magicpin":
            parsed = parse_magicpin_catalogue(obtained.raw)
        else:
            parsed = parse_swiggy_catalogue(obtained.raw)
    except Exception as exc:
        logger.exception("Catalogue parse failed for %s", platform)
        return None, _failed(
            request,
            error=f"{label} catalogue extraction failed: {type(exc).__name__}: {exc}",
            access_method=obtained.method,
            raw_capture_id=obtained.raw_capture_id,
        )
    return obtained, parsed


def _dineout_payload(catalogue) -> dict | None:
    payload = catalogue.to_dict().get("dineout")
    return payload if isinstance(payload, dict) and any(payload.values()) else None


def create_catalog(request: CatalogCreateRequest, access: SwiggyAccess) -> CatalogCreateResponse:
    platform = infer_legacy_platform(request.swiggy_url, getattr(request, "platform", None))
    if platform != "swiggy":
        return _create_platform_catalog(request, access, platform)
    return _create_swiggy_catalog(request, access)


def _follow_extra(access: SwiggyAccess, url: str | None, request: CatalogCreateRequest, platform: str):
    if not url:
        return None
    obtained, parsed = _load_parsed(access, url, request, platform)
    if obtained is None:
        return None
    if getattr(parsed, "extraction_status", None) != "ok":
        return None
    return parsed


def _create_platform_catalog(request: CatalogCreateRequest, access: SwiggyAccess, platform: str) -> CatalogCreateResponse:
    label = DISPLAY.get(platform, platform.title())
    obtained, parsed = _load_parsed(access, request.swiggy_url, request, platform, capture=True)
    if obtained is None:
        return parsed
    catalogue = parsed
    capture_id = obtained.raw_capture_id
    if catalogue.extraction_status == "blocked":
        return _failed(
            request,
            error=catalogue.error or f"{label} could not be accessed right now.",
            access_method=obtained.method,
            status="blocked",
            raw_capture_id=capture_id,
        )
    if catalogue.extraction_status not in {"ok", "partial"}:
        return _failed(
            request,
            error=catalogue.error or f"{label} catalogue extraction failed.",
            access_method=obtained.method,
            status="failed",
            raw_capture_id=capture_id,
        )
    if platform == "zomato":
        from scraper.zomato.parser import merge_zomato_images, merge_zomato_menu, order_menu_url, photos_gallery_url

        if request.catalogue_type in {"restaurant", "both"}:
            extra_menu = _follow_extra(access, order_menu_url(request.swiggy_url), request, platform)
            if extra_menu is not None:
                catalogue = merge_zomato_menu(catalogue, extra_menu)
        extra_photos = _follow_extra(access, photos_gallery_url(request.swiggy_url), request, platform)
        if extra_photos is not None:
            catalogue = merge_zomato_images(catalogue, extra_photos)
    if platform == "magicpin":
        from scraper.magicpin.parser import (
            delivery_menu_url,
            merge_magicpin_images,
            merge_magicpin_menu,
            photos_gallery_url,
        )

        if request.catalogue_type in {"restaurant", "both"}:
            if (catalogue.item_count or 0) < 10 or len(catalogue.categories or []) <= 1:
                extra_menu = _follow_extra(access, delivery_menu_url(request.swiggy_url), request, platform)
                if extra_menu is not None:
                    catalogue = merge_magicpin_menu(catalogue, extra_menu)
        if not catalogue.dineout or not (catalogue.dineout.gallery_images or catalogue.dineout.photos):
            extra_photos = _follow_extra(access, photos_gallery_url(request.swiggy_url), request, platform)
            if extra_photos is not None:
                catalogue = merge_magicpin_images(catalogue, extra_photos)
    if request.catalogue_type == "both" and request.dineout_url:
        extra_obtained, extra_parsed = _load_parsed(access, request.dineout_url, request, platform)
        if extra_obtained is not None and getattr(extra_parsed, "extraction_status", None) == "ok":
            extra_dineout = _dineout_payload(extra_parsed)
            if extra_dineout:
                catalogue.dineout = extra_parsed.dineout
    quality = _prepare_parsed(catalogue)
    payload = catalogue.to_dict()
    restaurant = payload.get("restaurant") or {}
    dineout = _dineout_payload(catalogue)

    # Fallback for hero image if primary restaurant image_url is missing
    if isinstance(restaurant, dict) and not restaurant.get("image_url"):
        hero_candidate = (
            (dineout.get("hero_image") if isinstance(dineout, dict) else None)
            or ((dineout.get("photos") or [None])[0] if isinstance(dineout, dict) and dineout.get("photos") else None)
            or next((item.get("image_url") for cat in (payload.get("categories") or []) for item in (cat.get("items") or []) if isinstance(item, dict) and item.get("image_url")), None)
        )
        if hero_candidate:
            restaurant["image_url"] = hero_candidate
    has_restaurant = bool(isinstance(restaurant, dict) and restaurant.get("name"))
    has_dineout = bool(
        dineout
        and (
            dineout.get("venue")
            or dineout.get("offers")
            or dineout.get("photos")
            or dineout.get("gallery_images")
            or dineout.get("hero_image")
        )
    )
    if request.catalogue_type == "dineout":
        if not has_dineout and not has_restaurant:
            return _failed(
                request,
                error=f"Page was reachable but no {label} Dineout venue data was extracted.",
                access_method=obtained.method,
                raw_capture_id=capture_id,
                quality=quality,
            )
        final_status = catalogue.extraction_status if catalogue.extraction_status in {"ok", "partial"} else "ok"
        return _finalize_ok(
            request,
            catalogue,
            obtained.method,
            CatalogCreateResponse(
            extraction_status=final_status,
            source_type=catalogue.source_type,
            restaurant_name=(dineout or {}).get("venue") or request.restaurant_name,
            fssai_number=request.fssai_number or "",
            source_url=request.swiggy_url,
            platform=platform,  # type: ignore[arg-type]
            catalogue_type="dineout",
            restaurant=restaurant if has_restaurant else None,
            dineout=dineout,
            categories=[],
            item_count=0,
            image_count=catalogue.image_count,
            error=None,
            access_method=obtained.method,
            ),
            raw_capture_id=capture_id,
            quality=quality,
        )
    if not has_restaurant:
        return _failed(
            request,
            error=f"Page was reachable but no {label} restaurant data was extracted.",
            access_method=obtained.method,
            raw_capture_id=capture_id,
            quality=quality,
        )
    final_status = catalogue.extraction_status if catalogue.extraction_status in {"ok", "partial"} else "ok"
    return _finalize_ok(
        request,
        catalogue,
        obtained.method,
        CatalogCreateResponse(
        extraction_status=final_status,
        source_type=catalogue.source_type,
        restaurant_name=request.restaurant_name,
        fssai_number=request.fssai_number,
        source_url=request.swiggy_url,
        platform=platform,  # type: ignore[arg-type]
        catalogue_type=request.catalogue_type,
        restaurant=restaurant,
        dineout=dineout if request.catalogue_type in {"dineout", "both"} else None,
        categories=payload.get("categories") or [],
        item_count=catalogue.item_count,
        image_count=catalogue.image_count,
        error=None,
        access_method=obtained.method,
        ),
        raw_capture_id=capture_id,
        quality=quality,
    )


def _create_swiggy_catalog(request: CatalogCreateRequest, access: SwiggyAccess) -> CatalogCreateResponse:
    obtained, parsed = _load_parsed(access, request.swiggy_url, request, capture=True)
    if obtained is None:
        return parsed

    catalogue = parsed
    capture_id = obtained.raw_capture_id
    status = catalogue.extraction_status
    if status in {"ok", "partial"}:
        if request.catalogue_type == "both" and request.dineout_url:
            dineout_obtained, dineout_parsed = _load_parsed(access, request.dineout_url, request)
            if dineout_obtained is not None and getattr(dineout_parsed, "extraction_status", None) == "ok":
                extra = _dineout_payload(dineout_parsed)
                if extra:
                    catalogue.dineout = dineout_parsed.dineout
        quality = _prepare_parsed(catalogue)
        payload = catalogue.to_dict()
        restaurant = payload.get("restaurant") or {}
        has_menu = bool(catalogue.item_count and payload.get("categories"))
        has_restaurant = bool(isinstance(restaurant, dict) and restaurant.get("name"))
        dineout = _dineout_payload(catalogue)
        has_dineout = bool(
            dineout
            and (
                dineout.get("venue")
                or dineout.get("offers")
                or dineout.get("photos")
                or dineout.get("gallery_images")
                or dineout.get("hero_image")
            )
        )

        if request.catalogue_type == "dineout":
            if not has_dineout and not has_restaurant:
                return _failed(
                    request,
                    error="Page was reachable but no Dineout venue data was extracted.",
                    access_method=obtained.method,
                    raw_capture_id=capture_id,
                    quality=quality,
                )
            image_count = catalogue.image_count
            if dineout:
                image_count = max(
                    image_count,
                    (1 if dineout.get("hero_image") else 0)
                    + len(dineout.get("gallery_images") or dineout.get("photos") or []),
                )
            final_status = catalogue.extraction_status if catalogue.extraction_status in {"ok", "partial"} else "ok"
            return _finalize_ok(
                request,
                catalogue,
                obtained.method,
                CatalogCreateResponse(
                extraction_status=final_status,
                source_type=catalogue.source_type,
                restaurant_name=dineout.get("venue") if dineout and dineout.get("venue") else request.restaurant_name,
                fssai_number=request.fssai_number or "",
                source_url=request.swiggy_url,
                platform="swiggy",
                catalogue_type="dineout",
                restaurant=payload.get("restaurant") if has_restaurant else None,
                dineout=dineout,
                categories=[],
                item_count=0,
                image_count=image_count,
                error=None,
                access_method=obtained.method,
                ),
                raw_capture_id=capture_id,
                quality=quality,
            )

        if not has_restaurant or not has_menu:
            return _failed(
                request,
                error="Page was reachable but no complete restaurant menu was extracted.",
                access_method=obtained.method,
                raw_capture_id=capture_id,
                quality=quality,
            )

        final_status = catalogue.extraction_status if catalogue.extraction_status in {"ok", "partial"} else "ok"
        return _finalize_ok(
            request,
            catalogue,
            obtained.method,
            CatalogCreateResponse(
            extraction_status=final_status,
            source_type=catalogue.source_type,
            restaurant_name=request.restaurant_name,
            fssai_number=request.fssai_number,
            source_url=request.swiggy_url,
            platform="swiggy",
            catalogue_type=request.catalogue_type,
            restaurant=payload["restaurant"],
            dineout=dineout if request.catalogue_type in {"dineout", "both"} else None,
            categories=payload["categories"],
            item_count=catalogue.item_count,
            image_count=catalogue.image_count,
            error=None,
            access_method=obtained.method,
            ),
            raw_capture_id=capture_id,
            quality=quality,
        )

    if status not in {"blocked", "failed"}:
        status = "failed"
    return _failed(
        request,
        error=catalogue.error or obtained.error or "Catalogue extraction failed.",
        access_method=obtained.method,
        status=status,
        raw_capture_id=capture_id,
    )
