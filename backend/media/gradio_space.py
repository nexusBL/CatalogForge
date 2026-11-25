"""Gradio Hugging Face Space client. Sends image bytes, never CatalogueForge artifact URLs."""

from __future__ import annotations

import json
import os
import time
from urllib.parse import urlparse

import httpx

from backend.media.providers import MediaProviderError
from scraper.swiggy.safe_fetch import MAX_BYTES, UnsafeURLError, assert_public_http_url, fetch_public_http_bytes


def is_gradio_space_url(url: str) -> bool:
    if os.getenv("CATALOGFORGE_MEDIA_PROTOCOL", "").strip().lower() == "gradio":
        return True
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(".hf.space")


def gradio_file_payload(png_b64: str, *, name: str = "source.png") -> dict:
    return {
        "path": None,
        "url": f"data:image/png;base64,{png_b64}",
        "orig_name": name,
        "mime_type": "image/png",
        "meta": {"_type": "gradio.FileData"},
    }


def kontext_infer_data(png_b64: str, prompt: str) -> list:
    """Payload for FLUX.1 Kontext Dev Space `/infer` (validated live)."""
    return [gradio_file_payload(png_b64), prompt, 0, True, 2.5, 8]


def svd_video_data(png_b64: str) -> list:
    """Payload for SVD Img2Vid Space `/video`."""
    return [gradio_file_payload(png_b64), 42, True, 80, 6]


def _space_root(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _first_file_url(payload: object) -> str | None:
    stack: list[object] = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            url = item.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
            nested = item.get("image") or item.get("video")
            if nested is not None:
                stack.append(nested)
            stack.extend(item.values())
        elif isinstance(item, str) and item.startswith(("http://", "https://", "data:")):
            return item
    return None


def _bytes_from_url(url: str) -> bytes:
    if url.startswith("data:"):
        import base64

        _, _, encoded = url.partition(",")
        return base64.b64decode(encoded)
    assert_public_http_url(url)
    data = fetch_public_http_bytes(url, timeout=30, max_bytes=MAX_BYTES)
    if not data:
        raise MediaProviderError("The media provider result URL was empty.", code="malformed")
    return data


def invoke_gradio_space(
    *,
    endpoint: str,
    api_name: str,
    data: list,
    token: str | None,
    timeout: float,
) -> bytes:
    root = _space_root(endpoint)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=min(30.0, timeout), follow_redirects=True) as client:
            started = client.post(
                f"{root}/gradio_api/call/{api_name.lstrip('/')}",
                json={"data": data},
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise MediaProviderError("The media provider timed out.", code="timeout") from exc
    except httpx.HTTPError as exc:
        raise MediaProviderError("The media provider is unavailable.", code="unavailable") from exc
    if started.status_code in {402, 429}:
        raise MediaProviderError("The media provider rate-limited or exhausted quota.", code="quota")
    if started.status_code >= 400:
        raise MediaProviderError("The media provider is unavailable.", code="unavailable")
    try:
        event_id = started.json().get("event_id")
    except Exception as exc:
        raise MediaProviderError("The media provider returned a malformed response.", code="malformed") from exc
    if not event_id:
        raise MediaProviderError("The media provider returned a malformed response.", code="malformed")
    deadline = time.monotonic() + timeout
    payload: object = None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream(
                "GET",
                f"{root}/gradio_api/call/{api_name.lstrip('/')}/{event_id}",
                headers={k: v for k, v in headers.items() if k != "Content-Type"},
            ) as stream:
                event_name = None
                for line in stream.iter_lines():
                    if time.monotonic() > deadline:
                        raise MediaProviderError("The media provider timed out.", code="timeout")
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_name = line.split(":", 1)[1].strip()
                        continue
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        if event_name == "error":
                            raise MediaProviderError("The media provider is unavailable.", code="unavailable")
                        if event_name == "complete":
                            payload = json.loads(raw)
                            break
    except MediaProviderError:
        raise
    except httpx.TimeoutException as exc:
        raise MediaProviderError("The media provider timed out.", code="timeout") from exc
    except httpx.HTTPError as exc:
        raise MediaProviderError("The media provider is unavailable.", code="unavailable") from exc
    except json.JSONDecodeError as exc:
        raise MediaProviderError("The media provider returned a malformed response.", code="malformed") from exc
    if payload is None:
        raise MediaProviderError("The media provider is unavailable.", code="unavailable")
    url = _first_file_url(payload)
    if not url:
        raise MediaProviderError("The media provider returned a malformed response.", code="malformed")
    try:
        return _bytes_from_url(url)
    except UnsafeURLError as exc:
        raise MediaProviderError("The media provider result URL was blocked.", code="malformed") from exc
