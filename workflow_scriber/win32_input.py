"""Win32 low-level input hook infrastructure.

The hook callback runs on a background thread with a ~50 ms budget before
Windows silently unhooks it (plan §18.1), so it only enqueues events.
All UIA work happens on the worker thread.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Dict, FrozenSet

# --- Win32 constants ---------------------------------------------------------

WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
HC_ACTION = 0
PM_REMOVE = 0x0001
LLMHF_INJECTED = 0x00000001
LLKHF_INJECTED = 0x00000010

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# --- hook structures ---------------------------------------------------------

class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

# --- Win32 function prototypes ------------------------------------------------

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = (
    wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM,
)
_user32.CallNextHookEx.restype = ctypes.c_ssize_t
_user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
_user32.PeekMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG), wintypes.HWND,
    wintypes.UINT, wintypes.UINT, wintypes.UINT,
)
_user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
_user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
_kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_user32.GetKeyboardState.argtypes = (ctypes.POINTER(ctypes.c_ubyte),)
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.GetKeyState.argtypes = (ctypes.c_int,)
_user32.GetKeyState.restype = ctypes.c_short
_user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
_user32.GetKeyboardLayout.restype = wintypes.HKL
_user32.ToUnicodeEx.argtypes = (
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_ubyte),
    ctypes.POINTER(wintypes.WCHAR), ctypes.c_int, wintypes.UINT, wintypes.HKL,
)

_HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM,
)

# Arg 2 must be the callback function-pointer type, not an integer. _HOOKPROC
# is defined here because it has to exist before the signature is set.
_user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD,
)

_user32.ToUnicodeEx.restype = ctypes.c_int


# --- key name tables ---------------------------------------------------------

_SENDKEYS = {
    "enter": "{ENTER}", "tab": "{TAB}", "esc": "{ESC}", "space": "{SPACE}",
    "backspace": "{BACKSPACE}", "delete": "{DELETE}", "insert": "{INSERT}",
    "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
    "home": "{HOME}", "end": "{END}", "page up": "{PGUP}", "page down": "{PGDN}",
    "caps lock": "{CAPSLOCK}", "print screen": "{PRTSC}", "pause": "{PAUSE}",
    "num lock": "{NUMLOCK}", "scroll lock": "{SCROLLLOCK}", "menu": "{APPS}",
}

_MOD_PREFIX = {"ctrl": "^", "alt": "%", "shift": "+", "windows": ""}

_MODIFIER_NAMES = frozenset({
    "ctrl", "alt", "shift", "windows",
    "left ctrl", "right ctrl", "left alt", "right alt",
    "left shift", "right shift", "left windows", "right windows",
})


def _mod_name(name: str) -> str:
    return name.replace("left ", "").replace("right ", "")


_VK_NAMES: Dict[int, str] = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x1B: "esc", 0x20: "space",
    0x21: "page up", 0x22: "page down", 0x23: "end", 0x24: "home",
    0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
    0x2C: "print screen", 0x2D: "insert", 0x2E: "delete",
    0x13: "pause", 0x14: "caps lock", 0x5D: "menu",
    0x90: "num lock", 0x91: "scroll lock",
    0x10: "shift", 0x11: "ctrl", 0x12: "alt",
    0xA0: "left shift", 0xA1: "right shift",
    0xA2: "left ctrl", 0xA3: "right ctrl",
    0xA4: "left alt", 0xA5: "right alt",
    0x5B: "left windows", 0x5C: "right windows",
}
_VK_NAMES.update({0x70 + i: f"f{i + 1}" for i in range(24)})

_VK_BASE: Dict[int, str] = {0x30 + i: chr(0x30 + i) for i in range(10)}
_VK_BASE.update({0x41 + i: chr(0x61 + i) for i in range(26)})
_VK_BASE.update({
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
    0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
    0x60: "0", 0x61: "1", 0x62: "2", 0x63: "3", 0x64: "4",
    0x65: "5", 0x66: "6", 0x67: "7", 0x68: "8", 0x69: "9",
    0x6A: "*", 0x6B: "+", 0x6D: "-", 0x6E: ".", 0x6F: "/",
})


def _base_name(vk: int) -> str:
    return _VK_BASE.get(vk) or _VK_NAMES.get(vk) or f"vk{vk}"


def _key_state() -> "ctypes.Array":
    state = (ctypes.c_ubyte * 256)()
    _user32.GetKeyboardState(state)
    for vk in (0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
        state[vk] = 0x80 if _user32.GetAsyncKeyState(vk) & 0x8000 else 0
    if _user32.GetKeyState(0x14) & 0x0001:
        state[0x14] = 0x01
    return state


def _typed_char(vk: int, scan: int) -> str:
    state = _key_state()
    buf = ctypes.create_unicode_buffer(8)
    layout = _user32.GetKeyboardLayout(0)
    n = _user32.ToUnicodeEx(vk, scan, state, buf, 8, 0, layout)
    if n < 0:
        _user32.ToUnicodeEx(vk, scan, state, buf, 8, 0, layout)
        return ""
    if n == 0:
        return ""
    return buf.value[:n]


def _current_mods() -> FrozenSet[str]:
    """Modifier state at hook time. Must be read in the callback, not later."""
    mods = set()
    if _user32.GetAsyncKeyState(0x11) & 0x8000:
        mods.add("ctrl")
    if _user32.GetAsyncKeyState(0x12) & 0x8000:
        mods.add("alt")
    if _user32.GetAsyncKeyState(0x10) & 0x8000:
        mods.add("shift")
    if (_user32.GetAsyncKeyState(0x5B) & 0x8000) or (
        _user32.GetAsyncKeyState(0x5C) & 0x8000
    ):
        mods.add("windows")
    return frozenset(mods)


def _sendkeys(name: str, mods: FrozenSet[str]) -> str:
    token = _SENDKEYS.get(name)
    if token is None:
        if len(name) == 1:
            token = name
        else:
            token = "{" + name.upper() + "}"
    prefix = "".join(_MOD_PREFIX[m] for m in ("ctrl", "alt", "shift", "windows")
                     if m in mods)
    return prefix + token


__all__ = [
    "WH_MOUSE_LL", "WH_KEYBOARD_LL", "HC_ACTION", "PM_REMOVE",
    "LLMHF_INJECTED", "LLKHF_INJECTED",
    "WM_LBUTTONDOWN", "WM_LBUTTONUP", "WM_RBUTTONDOWN", "WM_RBUTTONUP",
    "WM_MBUTTONDOWN", "WM_MBUTTONUP",
    "WM_MOUSEWHEEL", "WM_MOUSEHWHEEL",
    "WM_KEYDOWN", "WM_KEYUP", "WM_SYSKEYDOWN", "WM_SYSKEYUP",
    "_POINT", "_MSLLHOOKSTRUCT", "_KBDLLHOOKSTRUCT", "_HOOKPROC",
    "_sendkeys", "_base_name", "_mod_name", "_typed_char", "_key_state",
    "_current_mods",
    "_SENDKEYS", "_MOD_PREFIX", "_MODIFIER_NAMES", "_VK_NAMES", "_VK_BASE",
]
