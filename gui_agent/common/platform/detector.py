"""Platform detection and capability probing."""

import platform as plt
import sys
from .capabilities import Platform, PlatformCapabilities


class PlatformDetector:
    """Detects the current platform and probes its capabilities."""

    @staticmethod
    def detect() -> Platform:
        """Detect the current operating system platform."""
        system = plt.system().lower()
        if system == "windows":
            return Platform.WINDOWS
        elif system == "darwin":
            return Platform.MACOS
        elif system == "linux":
            return Platform.LINUX
        return Platform.UNKNOWN

    @staticmethod
    def probe() -> PlatformCapabilities:
        """Probe platform capabilities."""
        detected_platform = PlatformDetector.detect()
        python_version = sys.version.split()[0]
        os_version = plt.platform()

        if detected_platform == Platform.WINDOWS:
            return PlatformDetector._probe_windows(detected_platform, python_version, os_version)
        elif detected_platform == Platform.MACOS:
            return PlatformDetector._probe_macos(detected_platform, python_version, os_version)
        elif detected_platform == Platform.LINUX:
            return PlatformDetector._probe_linux(detected_platform, python_version, os_version)

        return PlatformCapabilities(
            platform=detected_platform,
            python_version=python_version,
            os_version=os_version,
        )

    @staticmethod
    def _probe_windows(
        platform: Platform,
        python_version: str,
        os_version: str
    ) -> PlatformCapabilities:
        """Probe Windows-specific capabilities."""
        has_uia = False
        has_pywin32 = False

        try:
            import uiautomation  # noqa: F401
            has_uia = True
        except ImportError:
            pass

        try:
            import win32api  # noqa: F401
            has_pywin32 = True
        except ImportError:
            pass

        return PlatformCapabilities(
            platform=platform,
            has_uiautomation=has_uia,
            has_pywin32=has_pywin32,
            has_accessibility_api=has_uia,
            supports_mouse_input=has_pywin32,
            supports_keyboard_input=has_uia,
            python_version=python_version,
            os_version=os_version,
        )

    @staticmethod
    def _probe_macos(
        platform: Platform,
        python_version: str,
        os_version: str
    ) -> PlatformCapabilities:
        """Probe macOS-specific capabilities."""
        has_accessibility = False
        try:
            import ApplicationServices  # noqa: F401
            has_accessibility = True
        except ImportError:
            pass
        return PlatformCapabilities(
            platform=platform,
            has_accessibility_api=has_accessibility,
            supports_mouse_input=True,
            supports_keyboard_input=True,
            python_version=python_version,
            os_version=os_version,
        )

    @staticmethod
    def _probe_linux(
        platform: Platform,
        python_version: str,
        os_version: str
    ) -> PlatformCapabilities:
        """Probe Linux-specific capabilities."""
        # Linux typically uses AT-SPI for accessibility
        return PlatformCapabilities(
            platform=platform,
            has_accessibility_api=False,
            supports_mouse_input=True,
            supports_keyboard_input=True,
            python_version=python_version,
            os_version=os_version,
        )