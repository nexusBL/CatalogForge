from __future__ import annotations

from urllib.parse import urlparse

PLATFORMS = ("swiggy", "zomato", "magicpin")

HOSTS = {
    "swiggy": ("swiggy.com",),
    "zomato": ("zomato.com",),
    "magicpin": ("magicpin.in",),
}

DISPLAY = {
    "swiggy": "Swiggy",
    "zomato": "Zomato",
    "magicpin": "Magicpin",
}


def normalize_platform(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in PLATFORMS:
        return text
    return "swiggy"


def hostname(url: str) -> str:
    try:
        host = urlparse(url.strip()).hostname or ""
    except Exception:
        return ""
    return host.replace("www.", "").lower()


def platform_from_url(url: str | None) -> str | None:
    host = hostname(url or "")
    if not host:
        return None
    for name, suffixes in HOSTS.items():
        if any(host == suffix or host.endswith("." + suffix) for suffix in suffixes):
            return name
    return None


def url_matches_platform(platform: str, url: str) -> bool:
    expected = HOSTS.get(normalize_platform(platform), ())
    host = hostname(url)
    return any(host == suffix or host.endswith("." + suffix) for suffix in expected)


def platform_url_error(platform: str, url: str) -> str | None:
    name = normalize_platform(platform)
    if url_matches_platform(name, url):
        return None
    label = DISPLAY[name]
    return f"You selected {label}, but the URL does not appear to be a {label} URL."


def infer_legacy_platform(source_url: str | None, explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return normalize_platform(explicit)
    from_url = platform_from_url(source_url)
    return from_url or "swiggy"
