from backend.platform_eval.adapters.magicpin import MagicpinPlatformAdapter
from backend.platform_eval.adapters.registry import (
    UnsupportedPlatform,
    get_adapter,
    register_adapter,
    require_adapter,
    supported_platforms,
)
from backend.platform_eval.adapters.swiggy import SwiggyPlatformAdapter
from backend.platform_eval.adapters.zomato import ZomatoPlatformAdapter

register_adapter(SwiggyPlatformAdapter())
register_adapter(ZomatoPlatformAdapter())
register_adapter(MagicpinPlatformAdapter())

__all__ = [
    "UnsupportedPlatform",
    "get_adapter",
    "register_adapter",
    "require_adapter",
    "supported_platforms",
]
