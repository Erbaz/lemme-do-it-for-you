"""Platform detection package."""
from .detector import PlatformDetector
from .capabilities import Platform, PlatformCapabilities

__all__ = ["PlatformDetector", "Platform", "PlatformCapabilities"]
