"""Platform capabilities data structures."""

from dataclasses import dataclass
from enum import Enum


class Platform(str, Enum):
    """Supported platforms."""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlatformCapabilities:
    """Capabilities detected on the current platform."""
    platform: Platform
    has_uiautomation: bool = False
    has_pywin32: bool = False
    has_accessibility_api: bool = False
    supports_mouse_input: bool = False
    supports_keyboard_input: bool = False
    python_version: str = ""
    os_version: str = ""