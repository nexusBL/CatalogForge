"""Hosted inference client. Bytes in, bytes out. Secrets stay in process env."""

from __future__ import annotations

import base64
import json
import os
from urllib.parse import urlparse

import httpx
from PIL import Image

from backend.media.gradio_space import (
    invoke_gradio_space,
    is_gradio_space_url,
    kontext_infer_data,
    svd_video_data,
)
from backend.media.instruction import generation_instruction
from backend.media.providers import MediaProviderError, ProviderRequest, ProviderResult, _open_rgb, _png_bytes
from scraper.swiggy.safe_fetch import MAX_BYTES, UnsafeURLError, assert_public_http_url, fetch_public_http_bytes

HOSTED_PROVIDER_ID = "hosted.v1"
HOSTED_EDGE_PX = 768
GENERATIVE_OPERATIONS = frozenset(
    {
        "generate_image",
        "background_generation",
        "edit",
        "cleanup",
        "expand",
        "image_to_video",
    }
)

_QUOTA_STATUS = {402, 429}
_UNAVAILABLE_STATUS = {401, 403, 404, 408, 409, 500, 502, 503, 504}


def hosted_timeout_seconds() -> float:
    raw = os.getenv("CATALOGFORGE_MEDIA_TIMEOUT_SECONDS", "45")
    try:
        return max(5.0, min(float(raw), 180.0))
    except ValueError:
        return 45.0


def _require_https_endpoint(url: str) -> str:
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MediaProviderError("Hosted media endpoint is not a valid HTTP URL.")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "testserver"}:
        raise MediaProviderError("Hosted media endpoint must use HTTPS.")
    return text


def _b64_image(data: bytes) -> str:
    image = _open_rgb(data)
    if max(image.width, image.height) > HOSTED_EDGE_PX:
        image.thumbnail((HOSTED_EDGE_PX, HOSTED_EDGE_PX), Image.Resampling.LANCZOS)
    return base64.b64encode(_png_bytes(image)).decode("ascii")


def _classify_status(status_code: int) -> MediaProviderError:
    if status_code in _QUOTA_STATUS:
        return MediaProviderError("The media provider rate-limited or exhausted quota.", code="quota")
    if status_code == 408:
        return MediaProviderError("The media provider timed out.", code="timeout")
    if status_code in _UNAVAILABLE_STATUS:
        return MediaProviderError("The media provider is unavailable.", code="unavailable")
    return MediaProviderError("The media provider failed.", code="unavailable")


def _decode_payload(content: bytes, content_type: str) -> ProviderResult:
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype.startswith("video/"):
        if len(content) > MAX_BYTES:
            raise MediaProviderError("Hosted video exceeds the size limit.", code="malformed")
        return ProviderResult(data=content, content_type=ctype, media_kind="video")
    if ctype.startswith("image/"):
        _open_rgb(content)
        return ProviderResult(data=content, content_type=ctype, media_kind="image")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MediaProviderError("The media provider returned a malformed response.", code="malformed") from exc
    if not isinstance(payload, dict):
        raise MediaProviderError("The media provider returned a malformed response.", code="malformed")
    b64 = payload.get("b64") or payload.get("b64_json")
    if isinstance(payload.get("data"), list) and payload["data"]:
        first = payload["data"][0]
        if isinstance(first, dict):
            b64 = b64 or first.get("b64_json")
            url = first.get("url")
        else:
            url = None
    else:
        url = payload.get("url")
    if isinstance(b64, str) and b64.strip():
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception as exc:
            raise MediaProviderError("The media provider returned a malformed response.", code="malformed") from exc
        kind = "video" if raw[:3] == b"GIF" or raw[4:8] == b"ftyp" else "image"
        if kind == "image":
            _open_rgb(raw)
        return ProviderResult(
            data=raw,
            content_type="image/gif" if raw[:3] == b"GIF" else ("video/mp4" if kind == "video" else "image/png"),
            media_kind=kind,
        )
    if isinstance(url, str) and url.strip():
        try:
            assert_public_http_url(url.strip())
            raw = fetch_public_http_bytes(url.strip(), timeout=15, max_bytes=MAX_BYTES)
        except (UnsafeURLError, ValueError, OSError) as exc:
            raise MediaProviderError("The media provider result URL was blocked.", code="malformed") from exc
        if not raw:
            raise MediaProviderError("The media provider returned a malformed response.", code="malformed")
        if raw[:4] == b"\x00\x00\x00" or raw[4:8] == b"ftyp":
            return ProviderResult(data=raw, content_type="video/mp4", media_kind="video")
        _open_rgb(raw)
        return ProviderResult(data=raw, content_type="image/png", media_kind="image")
    raise MediaProviderError("The media provider returned a malformed response.", code="malformed")


class HostedMediaProvider:
    """HTTP inference adapter. Operator-configured URL; never user-controlled."""

    provider_id = HOSTED_PROVIDER_ID

    def __init__(
        self,
        *,
        image_url: str | None,
        video_url: str | None,
        token: str | None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.image_url = _require_https_endpoint(image_url) if image_url else None
        self.video_url = _require_https_endpoint(video_url) if video_url else None
        self._token = token or None
        self.timeout = timeout if timeout is not None else hosted_timeout_seconds()
        self._transport = transport

    @property
    def supports_image(self) -> bool:
        return bool(self.image_url)

    @property
    def supports_video(self) -> bool:
        return bool(self.video_url)

    def transform(self, request: ProviderRequest) -> ProviderResult:
        endpoint = self.video_url if request.operation == "image_to_video" else self.image_url
        if not endpoint:
            raise MediaProviderError("Hosted media provider is not configured for this operation.", code="unavailable")
        if request.operation == "image_to_video" and not request.source:
            raise MediaProviderError("Image-to-video requires a source image.")
        source = request.source
        if request.operation == "generate_image" and not source and request.references:
            source = request.references[0]
        if request.operation != "generate_image" and request.operation != "image_to_video" and not source:
            raise MediaProviderError("This operation requires a source image.")
        if request.operation == "generate_image" and not source:
            raise MediaProviderError(
                "Hosted image generation needs a restaurant reference photo.",
                code="unavailable",
            )
        prompt = generation_instruction(
            operation=request.operation,
            user_prompt=request.prompt,
            item_name=request.item_name,
            description=request.description,
            restaurant_name=request.restaurant_name,
        )
        if is_gradio_space_url(endpoint):
            return self._transform_gradio(request, endpoint=endpoint, source=source, prompt=prompt)
        body = {
            "operation": request.operation,
            "prompt": prompt,
            "item_name": request.item_name,
            "description": request.description,
            "restaurant_name": request.restaurant_name,
        }
        if source:
            body["image"] = {"content_type": "image/png", "b64": _b64_image(source)}
        if request.references:
            body["references"] = [
                {"content_type": "image/png", "b64": _b64_image(blob)} for blob in request.references[:3]
            ]
        headers = {"Content-Type": "application/json", "Accept": "application/json, image/*, video/*"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(endpoint, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise MediaProviderError("The media provider timed out.", code="timeout") from exc
        except httpx.HTTPError as exc:
            raise MediaProviderError("The media provider is unavailable.", code="unavailable") from exc
        if response.status_code >= 400:
            raise _classify_status(response.status_code)
        result = _decode_payload(response.content, response.headers.get("content-type") or "")
        if request.operation == "image_to_video":
            return ProviderResult(data=result.data, content_type=result.content_type, media_kind="video")
        return result

    def _transform_gradio(
        self,
        request: ProviderRequest,
        *,
        endpoint: str,
        source: bytes,
        prompt: str,
    ) -> ProviderResult:
        png_b64 = _b64_image(source)
        if request.operation == "image_to_video":
            api_name = os.getenv("CATALOGFORGE_MEDIA_VIDEO_API", "video").strip() or "video"
            data = svd_video_data(png_b64)
        else:
            api_name = os.getenv("CATALOGFORGE_MEDIA_IMAGE_API", "infer").strip() or "infer"
            data = kontext_infer_data(png_b64, prompt)
        raw = invoke_gradio_space(
            endpoint=endpoint,
            api_name=api_name,
            data=data,
            token=self._token,
            timeout=self.timeout,
        )
        if request.operation == "image_to_video":
            content_type = "video/mp4" if raw[4:8] == b"ftyp" else ("image/gif" if raw[:3] == b"GIF" else "application/octet-stream")
            return ProviderResult(data=raw, content_type=content_type, media_kind="video")
        _open_rgb(raw)
        sniffed = "image/webp" if raw[:4] == b"RIFF" else ("image/jpeg" if raw[:2] == b"\xff\xd8" else "image/png")
        return ProviderResult(data=raw, content_type=sniffed, media_kind="image")


def hosted_provider_from_env(*, transport: httpx.BaseTransport | None = None) -> HostedMediaProvider | None:
    image_url = os.getenv("CATALOGFORGE_MEDIA_IMAGE_URL", "").strip() or None
    video_url = os.getenv("CATALOGFORGE_MEDIA_VIDEO_URL", "").strip() or None
    token = os.getenv("CATALOGFORGE_MEDIA_API_TOKEN", "").strip() or None
    if not image_url and not video_url:
        return None
    return HostedMediaProvider(image_url=image_url, video_url=video_url, token=token, transport=transport)
