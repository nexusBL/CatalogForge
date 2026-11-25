from __future__ import annotations

import ipaddress
import socket
from http.client import HTTPException as HTTPClientException
from http.client import IncompleteRead
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request

MAX_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = 15.0
REDIRECT_CODES = {301, 302, 303, 307, 308}

BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata.google.com",
    "metadata.goog",
    "metadata",
}

Resolver = Callable[..., list[tuple[Any, ...]]]
OpenUrl = Callable[[Request, float], Any]


class UnsafeURLError(ValueError):
    pass


def assert_public_http_url(url: str, *, resolver: Resolver | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("only http and https are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURLError("credentials are not allowed")
    hostname = (parsed.hostname or "").strip().rstrip(".").lower()
    if not hostname:
        raise UnsafeURLError("hostname is required")
    if hostname in BLOCKED_HOSTS or hostname.endswith(".metadata.google.internal"):
        raise UnsafeURLError("destination is not allowed")
    lookup = resolver or socket.getaddrinfo
    try:
        answers = lookup(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except (OSError, socket.gaierror) as exc:
        raise UnsafeURLError("hostname could not be resolved") from exc
    if not answers:
        raise UnsafeURLError("hostname could not be resolved")
    for answer in answers:
        sockaddr = answer[4]
        if not sockaddr:
            raise UnsafeURLError("hostname could not be resolved")
        _assert_public_ip(sockaddr[0])
    return url


def fetch_public_http_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    resolver: Resolver | None = None,
    open_url: OpenUrl | None = None,
) -> bytes | None:
    """Fetch URL bytes after SSRF checks. Returns None on any validation or I/O failure."""
    opener = open_url or _open_no_redirect
    current = url
    try:
        for _hop in range(max_redirects + 1):
            assert_public_http_url(current, resolver=resolver)
            request = Request(current, headers=headers or {})
            try:
                with opener(request, timeout) as response:
                    content_type = ""
                    raw_headers = getattr(response, "headers", None)
                    if raw_headers is not None:
                        content_type = (raw_headers.get("Content-Type") or "").lower()
                    data = _read_limited(response, max_bytes)
            except HTTPError as exc:
                try:
                    if exc.code in REDIRECT_CODES:
                        location = ((exc.headers.get("Location") if exc.headers else None) or "").strip()
                        if not location:
                            return None
                        current = urljoin(current, location)
                        continue
                    return None
                finally:
                    try:
                        exc.close()
                    except Exception:
                        pass
            if data is None:
                return None
            if not data or "text/html" in content_type:
                return None
            return data
        return None
    except (UnsafeURLError, URLError, TimeoutError, OSError, ValueError, IncompleteRead, HTTPClientException):
        return None


def _assert_public_ip(raw: str) -> None:
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise UnsafeURLError("invalid address") from exc
    if ip.version == 6 and ip.ipv4_mapped is not None:
        _assert_public_ip(str(ip.ipv4_mapped))
        return
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in ipaddress.ip_network("169.254.0.0/16"))
    ):
        raise UnsafeURLError("destination is not allowed")


def _read_limited(response: Any, max_bytes: int) -> bytes | None:
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = response.read(64 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > max_bytes:
            return None
        chunks.append(piece)
    return b"".join(chunks)


def _open_no_redirect(request: Request, timeout: float):
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.HTTPHandler(), urllib.request.HTTPSHandler())
    return opener.open(request, timeout=timeout)
