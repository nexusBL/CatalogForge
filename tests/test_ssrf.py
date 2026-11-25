from __future__ import annotations

import socket
from email.message import EmailMessage
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from scraper.swiggy.safe_fetch import (
    MAX_BYTES,
    UnsafeURLError,
    assert_public_http_url,
    fetch_public_http_bytes,
)


def resolve_to(*ips: str):
    def resolver(host, port, *args, **kwargs):
        answers = []
        for ip in ips:
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            answers.append((family, socket.SOCK_STREAM, 6, "", (ip, port or 0)))
        return answers

    return resolver


def test_localhost_hostname_rejected():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://localhost/secret", resolver=resolve_to("8.8.8.8"))


def test_loopback_ip_rejected():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://127.0.0.1/secret", resolver=resolve_to("127.0.0.1"))


def test_rfc1918_private_ip_rejected():
    for ip in ("10.1.2.3", "172.16.9.9", "192.168.1.20"):
        with pytest.raises(UnsafeURLError):
            assert_public_http_url(f"http://{ip}/img", resolver=resolve_to(ip))


def test_link_local_and_metadata_ip_rejected():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://169.254.169.254/latest/meta-data", resolver=resolve_to("169.254.169.254"))


def test_metadata_hostname_rejected():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url(
            "http://metadata.google.internal/computeMetadata/v1/",
            resolver=resolve_to("8.8.8.8"),
        )


def test_private_ipv6_rejected():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://[fc00::1]/img", resolver=resolve_to("fc00::1"))
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://[fe80::1]/img", resolver=resolve_to("fe80::1"))


def test_ipv4_mapped_private_ipv6_rejected():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://host.example/img", resolver=resolve_to("::ffff:192.168.0.5"))


def test_multicast_and_unspecified_rejected():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://host.example/img", resolver=resolve_to("224.0.0.1"))
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://host.example/img", resolver=resolve_to("0.0.0.0"))
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("http://host.example/img", resolver=resolve_to("ff02::1"))


def test_public_https_hostname_allowed():
    assert_public_http_url("https://cdn.example/hero.jpg", resolver=resolve_to("93.184.216.34"))


def test_credentials_in_url_rejected():
    with pytest.raises(UnsafeURLError):
        assert_public_http_url("https://user:pass@cdn.example/hero.jpg", resolver=resolve_to("93.184.216.34"))


def _redirect(url: str, location: str, code: int = 302) -> HTTPError:
    headers = EmailMessage()
    headers["Location"] = location
    return HTTPError(url, code, "Found", headers, BytesIO())


class FakeBody:
    def __init__(self, data: bytes, content_type: str = "image/jpeg"):
        self._data = data
        self.headers = {"Content-Type": content_type}

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            out = self._data
            self._data = b""
            return out
        out = self._data[:n]
        self._data = self._data[n:]
        return out

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_redirect_to_private_ip_rejected():
    hops: list[str] = []

    def open_url(request: Request, timeout: float):
        hops.append(request.full_url)
        if request.full_url == "https://cdn.example/go":
            raise _redirect(request.full_url, "http://127.0.0.1/secret")
        raise AssertionError(f"unexpected fetch {request.full_url}")

    def resolver(host, port, *args, **kwargs):
        if host in {"cdn.example"}:
            return resolve_to("93.184.216.34")(host, port)
        return resolve_to("127.0.0.1")(host, port)

    assert fetch_public_http_bytes("https://cdn.example/go", resolver=resolver, open_url=open_url) is None
    assert hops == ["https://cdn.example/go"]


def test_redirect_chain_is_revalidated():
    hops: list[str] = []

    def open_url(request: Request, timeout: float):
        hops.append(request.full_url)
        if request.full_url == "https://cdn.example/a":
            raise _redirect(request.full_url, "https://cdn.example/b")
        if request.full_url == "https://cdn.example/b":
            raise _redirect(request.full_url, "http://10.0.0.8/internal")
        raise AssertionError(f"unexpected fetch {request.full_url}")

    def resolver(host, port, *args, **kwargs):
        if host == "cdn.example":
            return resolve_to("93.184.216.34")(host, port)
        return resolve_to("10.0.0.8")(host, port)

    assert fetch_public_http_bytes("https://cdn.example/a", resolver=resolver, open_url=open_url) is None
    assert hops == ["https://cdn.example/a", "https://cdn.example/b"]


def test_timeout_returns_none():
    def open_url(request: Request, timeout: float):
        raise TimeoutError()

    assert (
        fetch_public_http_bytes(
            "https://cdn.example/slow.jpg",
            resolver=resolve_to("93.184.216.34"),
            open_url=open_url,
        )
        is None
    )


def test_oversized_response_returns_none():
    class Big(FakeBody):
        def read(self, n: int = -1) -> bytes:
            size = MAX_BYTES + 1 if n < 0 else min(n, 64 * 1024)
            return b"x" * size

    def open_url(request: Request, timeout: float):
        return Big(b"")

    assert (
        fetch_public_http_bytes(
            "https://cdn.example/huge.jpg",
            resolver=resolve_to("93.184.216.34"),
            open_url=open_url,
        )
        is None
    )


def test_public_https_fetch_returns_bytes():
    def open_url(request: Request, timeout: float):
        return FakeBody(b"image-bytes")

    data = fetch_public_http_bytes(
        "https://cdn.example/hero.jpg",
        resolver=resolve_to("93.184.216.34"),
        open_url=open_url,
    )
    assert data == b"image-bytes"
