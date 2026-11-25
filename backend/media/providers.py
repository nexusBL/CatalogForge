"""Provider-independent media generation boundary.

Default engine is local.v1: deterministic Pillow ops plus local composition.
Hosted image editing is optional and operator-configured (demo Spaces are not production).
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from backend.media.contract import (
    MAX_EDGE_PX,
    MAX_PIXELS,
    MAX_VIDEO_EDGE_PX,
    PROVIDER_ID,
    BlurParams,
    CropParams,
    ExpandParams,
    MediaOperation,
)

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(frozen=True)
class ProviderResult:
    data: bytes
    content_type: str
    media_kind: str


class MediaProvider(Protocol):
    provider_id: str

    def transform(self, request: "ProviderRequest") -> ProviderResult:
        ...


@dataclass
class ProviderRequest:
    operation: MediaOperation
    source: bytes | None
    prompt: str | None
    item_name: str
    description: str | None
    restaurant_name: str | None
    references: list[bytes]
    crop: CropParams | None = None
    blur: BlurParams | None = None
    expand: ExpandParams | None = None


IMAGE_GENERATION_UNAVAILABLE = "AI image generation is temporarily unavailable. Please try again."
GIF_CREATION_UNAVAILABLE = "GIF creation is temporarily unavailable. Please try again."
GENERATED_IMAGE_UNUSABLE = "The generated image could not be used. Please try again."
_HOSTED_ERROR_CODES = frozenset({"quota", "timeout", "unavailable", "malformed"})


class MediaProviderError(RuntimeError):
    def __init__(self, message: str, *, code: str | None = None):
        self.code = code
        super().__init__(message)


def safe_job_error(exc: BaseException, *, operation: str | None = None) -> str:
    """Persist a user-safe job error. Never include tokens, hosts, or stack traces."""
    code = getattr(exc, "code", None)
    if operation == "image_to_video":
        if code in _HOSTED_ERROR_CODES:
            return GIF_CREATION_UNAVAILABLE
        text = str(exc).strip() or GIF_CREATION_UNAVAILABLE
        return text if _message_is_public(text) else GIF_CREATION_UNAVAILABLE
    if code in {"quota", "timeout", "unavailable"}:
        return IMAGE_GENERATION_UNAVAILABLE
    if code == "malformed":
        return GENERATED_IMAGE_UNUSABLE
    text = str(exc).strip()
    if not text:
        return IMAGE_GENERATION_UNAVAILABLE
    if not _message_is_public(text):
        return IMAGE_GENERATION_UNAVAILABLE
    return text


def _message_is_public(text: str) -> bool:
    lowered = text.casefold()
    if "bearer " in lowered or "hf_" in text or "api_token" in lowered or "fal_key" in lowered:
        return False
    if "traceback" in lowered or ".hf.space" in lowered or "gradio" in lowered:
        return False
    return True


def _open_rgb(data: bytes) -> Image.Image:
    if not data:
        raise MediaProviderError("Source image bytes are empty.")
    if data.lstrip()[:1] == b"<" or data[:4].lower() == b"<svg":
        raise MediaProviderError("SVG content is not allowed.")
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except Exception as exc:
        raise MediaProviderError("Image bytes could not be decoded.") from exc
    if image.width * image.height > MAX_PIXELS:
        raise MediaProviderError("Image exceeds the pixel limit.")
    if max(image.width, image.height) > MAX_EDGE_PX:
        image.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.Resampling.LANCZOS)
    return image.convert("RGBA")


def _png_bytes(image: Image.Image) -> bytes:
    rgb = image.convert("RGBA")
    buffer = BytesIO()
    rgb.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _mean_color(images: list[Image.Image]) -> tuple[int, int, int]:
    if not images:
        return (245, 239, 230)
    r = g = b = 0
    count = 0
    for image in images:
        sample = image.convert("RGB").resize((1, 1))
        pixel = sample.getpixel((0, 0))
        r += int(pixel[0])
        g += int(pixel[1])
        b += int(pixel[2])
        count += 1
    return (r // count, g // count, b // count)


def _compose_missing(*, name: str, restaurant: str | None, references: list[bytes]) -> Image.Image:
    refs = []
    for blob in references:
        try:
            refs.append(_open_rgb(blob))
        except MediaProviderError:
            continue
    width, height = 640, 480
    if refs:
        width, height = refs[0].size
        width = min(max(width, 320), MAX_EDGE_PX)
        height = min(max(height, 240), MAX_EDGE_PX)
    color = _mean_color(refs)
    canvas = Image.new("RGBA", (width, height), color + (255,))
    if refs:
        plate = ImageOps.fit(refs[0], (width, height), method=Image.Resampling.LANCZOS)
        plate = ImageEnhance.Color(plate).enhance(0.35)
        plate = ImageEnhance.Brightness(plate).enhance(1.08)
        canvas = Image.blend(canvas, plate, 0.45)
    draw = ImageDraw.Draw(canvas)
    label = (name or "Menu item").strip()[:48]
    venue = (restaurant or "").strip()[:40]
    draw.rectangle([(24, height - 96), (width - 24, height - 24)], fill=(20, 20, 20, 160))
    draw.text((36, height - 84), label, fill=(255, 255, 255, 255))
    if venue:
        draw.text((36, height - 56), venue, fill=(230, 230, 230, 255))
    return canvas


import math
import re

def _apply_prompt_adjustments(image: Image.Image, prompt: str | None) -> Image.Image:
    if not prompt:
        return image
    text = prompt.casefold()

    # Extract brightness
    m = re.search(r"brightness:\s*([+-]?\d+)", text)
    if m:
        val = int(m.group(1))
        image = ImageEnhance.Brightness(image).enhance(max(0.2, 1.0 + val / 100.0))

    # Extract contrast
    m = re.search(r"contrast:\s*([+-]?\d+)", text)
    if m:
        val = int(m.group(1))
        image = ImageEnhance.Contrast(image).enhance(max(0.2, 1.0 + val / 100.0))

    # Extract saturation
    m = re.search(r"saturation:\s*([+-]?\d+)", text)
    if m:
        val = int(m.group(1))
        image = ImageEnhance.Color(image).enhance(max(0.0, 1.0 + val / 100.0))

    # Extract clarity / sharpness
    m = re.search(r"clarity:\s*([+-]?\d+)", text)
    if m:
        val = int(m.group(1))
        image = ImageEnhance.Sharpness(image).enhance(max(0.0, 1.0 + val / 50.0))

    # Extract blur
    m = re.search(r"blur:\s*(\d+)", text)
    if m:
        val = int(m.group(1))
        if val > 0:
            radius = max(0.5, min(val / 5.0, 20.0))
            image = image.filter(ImageFilter.GaussianBlur(radius=radius))

    return image


class LocalMediaProvider:
    """On-host engine. Crop/blur/expand/enhance stay deterministic Pillow ops.

    Generative names (edit, missing image, background generation) are local
    composition fallbacks when no hosted image provider is configured.
    image_to_video is local GIF animation, not AI video.
    """

    provider_id = PROVIDER_ID

    def transform(self, request: ProviderRequest) -> ProviderResult:
        if request.operation == "image_to_video":
            return self._image_to_video(request)
        if request.operation == "generate_image" or request.source is None:
            image = _compose_missing(
                name=request.item_name,
                restaurant=request.restaurant_name,
                references=request.references,
            )
            return ProviderResult(data=_png_bytes(image), content_type="image/png", media_kind="image")
        image = _open_rgb(request.source)
        if request.operation == "enhance":
            image = ImageEnhance.Contrast(image).enhance(1.12)
            image = ImageEnhance.Sharpness(image).enhance(1.2)
            image = ImageEnhance.Brightness(image).enhance(1.06)
            image = _apply_prompt_adjustments(image, request.prompt)
        elif request.operation == "blur":
            radius = (request.blur or BlurParams()).radius
            image = image.filter(ImageFilter.GaussianBlur(radius=max(0.5, min(radius, 30))))
            image = _apply_prompt_adjustments(image, request.prompt)
        elif request.operation == "crop":
            box = request.crop or CropParams()
            left = int(max(0.0, min(box.left, 1.0)) * image.width)
            top = int(max(0.0, min(box.top, 1.0)) * image.height)
            right = int(max(0.0, min(box.right, 1.0)) * image.width)
            bottom = int(max(0.0, min(box.bottom, 1.0)) * image.height)
            if right - left < 8 or bottom - top < 8:
                raise MediaProviderError("Crop region is too small.")
            image = image.crop((left, top, right, bottom))
        elif request.operation == "expand":
            params = request.expand or ExpandParams()
            fill = _mean_color([image])
            image = ImageOps.expand(
                image,
                border=(max(0, params.left), max(0, params.top), max(0, params.right), max(0, params.bottom)),
                fill=fill + (255,),
            )
        elif request.operation == "background_removal":
            image = _fake_cutout(image)
        elif request.operation == "background_generation":
            cut = _fake_cutout(image)
            bg = Image.new("RGBA", cut.size, (248, 244, 236, 255))
            image = Image.alpha_composite(bg, cut)
            image = _apply_prompt_adjustments(image, request.prompt)
        elif request.operation == "cleanup":
            image = image.filter(ImageFilter.MedianFilter(size=3))
            image = ImageEnhance.Sharpness(image).enhance(1.1)
            image = _apply_prompt_adjustments(image, request.prompt)
        elif request.operation == "edit":
            image = ImageEnhance.Brightness(image).enhance(1.04)
            image = ImageEnhance.Contrast(image).enhance(1.05)
            image = _apply_prompt_adjustments(image, request.prompt)
        else:
            raise MediaProviderError(f"Unsupported operation: {request.operation}")
        return ProviderResult(data=_png_bytes(image), content_type="image/png", media_kind="image")

    def _image_to_video(self, request: ProviderRequest) -> ProviderResult:
        if not request.source:
            raise MediaProviderError("GIF creation requires a source image.")
        image = _open_rgb(request.source)
        if max(image.width, image.height) > MAX_VIDEO_EDGE_PX:
            image.thumbnail((MAX_VIDEO_EDGE_PX, MAX_VIDEO_EDGE_PX), Image.Resampling.LANCZOS)
        
        width, height = image.size
        frames = []
        num_frames = 12
        for i in range(num_frames):
            # Smooth sinusoidal gentle zoom motion from center (100% to 104% scale)
            t = math.sin(math.pi * i / num_frames)
            scale = 1.0 + 0.04 * t
            crop_w = max(16, int(width / scale))
            crop_h = max(16, int(height / scale))
            left = (width - crop_w) // 2
            top = (height - crop_h) // 2

            cropped = image.crop((left, top, left + crop_w, top + crop_h))
            resized = cropped.resize((width, height), Image.Resampling.LANCZOS)

            if resized.mode == "RGBA":
                bg = Image.new("RGB", resized.size, (255, 255, 255))
                bg.paste(resized, mask=resized.split()[3])
                rgb_frame = bg
            else:
                rgb_frame = resized.convert("RGB")

            quantized = rgb_frame.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
            frames.append(quantized)

        buffer = BytesIO()
        frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=120,
            loop=0,
        )
        return ProviderResult(data=buffer.getvalue(), content_type="image/gif", media_kind="video")


def _fake_cutout(image: Image.Image) -> Image.Image:
    """Local stand-in for background removal: keep a centered ellipse, transparent outside."""
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    inset_x = int(image.width * 0.08)
    inset_y = int(image.height * 0.08)
    draw.ellipse((inset_x, inset_y, image.width - inset_x, image.height - inset_y), fill=255)
    cut = image.copy()
    cut.putalpha(mask)
    return cut
