"""Route deterministic ops to Pillow and generative ops to hosted inference when configured."""

from __future__ import annotations

from backend.media.hosted import GENERATIVE_OPERATIONS, HostedMediaProvider, hosted_provider_from_env
from backend.media.providers import LocalMediaProvider, MediaProvider, ProviderRequest, ProviderResult

DETERMINISTIC_OPERATIONS = frozenset({"crop", "blur", "enhance", "background_removal"})


class RoutingMediaProvider:
    """Keeps Phase 7 jobs provider-independent. Hosted credentials never leave this process."""

    def __init__(self, *, local: LocalMediaProvider | None = None, hosted: HostedMediaProvider | None = None) -> None:
        self.local = local or LocalMediaProvider()
        self.hosted = hosted

    @property
    def provider_id(self) -> str:
        if self.hosted is None:
            return self.local.provider_id
        return self.hosted.provider_id

    def _engine(self, operation: str) -> MediaProvider:
        if operation not in GENERATIVE_OPERATIONS or operation in DETERMINISTIC_OPERATIONS:
            return self.local
        if operation == "image_to_video":
            # GIF Creation is local animation. Hosted I2V stays unused until a later
            # commercial provider is selected; do not treat GIF as AI video.
            return self.local
        if self.hosted is not None and self.hosted.supports_image:
            return self.hosted
        return self.local

    def provider_id_for(self, operation: str) -> str:
        return str(getattr(self._engine(operation), "provider_id", self.provider_id))

    def transform(self, request: ProviderRequest) -> ProviderResult:
        return self._engine(request.operation).transform(request)


def default_media_provider() -> RoutingMediaProvider:
    return RoutingMediaProvider(local=LocalMediaProvider(), hosted=hosted_provider_from_env())
