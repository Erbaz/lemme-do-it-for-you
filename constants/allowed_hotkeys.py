"""
Allowed hotkey combinations for GUI automation.
Safe shortcuts for productivity and browser operations across Windows/macOS/Linux.
"""

ALLOWED_HOTKEYS = [
    # ============ CLIPBOARD OPERATIONS ============
    ["ctrl", "c"],      # Copy
    ["ctrl", "x"],      # Cut
    ["ctrl", "v"],      # Paste
    
    # ============ TEXT EDITING ============
    ["ctrl", "a"],      # Select All
    ["ctrl", "z"],      # Undo
    ["ctrl", "y"],      # Redo
    ["ctrl", "shift", "z"],  # Redo (alternative)
    
    # ============ FILE OPERATIONS ============
    ["ctrl", "s"],      # Save
    ["ctrl", "shift", "s"],  # Save As
    ["ctrl", "n"],      # New (file/window)
    ["ctrl", "o"],      # Open
    
    # ============ WINDOW MANAGEMENT ============
    ["alt", "f4"],      # Close window (Windows/Linux)
    ["alt", "tab"],     # Switch window (Windows/Linux)
    ["alt", "shift", "tab"],  # Switch window backwards (Windows/Linux)
    ["cmd", "w"],       # Close window/tab (macOS)
    ["cmd", "tab"],     # Switch app (macOS)
    ["cmd", "shift", "tab"],  # Switch app backwards (macOS)
    ["cmd", "m"],       # Minimize window (macOS)
    ["cmd", "h"],       # Hide window (macOS)
    ["super"],          # Open Start Menu (Windows)
    ["super", "d"],     # Show Desktop (Windows)
    ["super", "m"],     # Minimize all (Windows)
    ["super", "shift", "m"],  # Restore minimized (Windows)
    ["super", "e"],     # Open File Explorer (Windows)
    ["super", "i"],     # Open Settings (Windows)
    ["super", "x"],     # Open Power menu (Windows)
    
    # ============ VOLUME & SOUND CONTROL ============
    ["volumemute"],     # Mute volume
    ["volumedown"],     # Decrease volume
    ["volumeup"],       # Increase volume
    
    # Fn hotkeys (Windows/Linux)
    ["f1"],             # Mute (some laptops)
    ["f2"],             # Volume down (some laptops)
    ["f3"],             # Volume up (some laptops)
    
    # macOS media/volume keys
    ["f10"],            # Mute (macOS)
    ["f11"],            # Decrease volume (macOS)
    ["f12"],            # Increase volume (macOS)
    
    # ============ BROWSER SHORTCUTS ============
    # Navigation
    ["ctrl", "tab"],    # Next tab (Windows/Linux)
    ["ctrl", "shift", "tab"],  # Previous tab (Windows/Linux)
    ["cmd", "option", "right"],  # Next tab (macOS)
    ["cmd", "option", "left"],   # Previous tab (macOS)
    ["alt", "left"],    # Back (Windows/Linux)
    ["alt", "right"],   # Forward (Windows/Linux)
    ["cmd", "left"],    # Back (macOS)
    ["cmd", "right"],   # Forward (macOS)
    ["ctrl", "w"],      # Close tab (Windows/Linux)
    ["ctrl", "shift", "w"],  # Close window (Windows/Linux)
    ["ctrl", "shift", "t"],  # Reopen closed tab (Windows/Linux)
    ["ctrl", "shift", "n"],  # New incognito window (Windows/Linux)
    ["ctrl", "n"],      # New window (Windows/Linux)
    
    # Search & Find
    ["ctrl", "f"],      # Find in page
    ["ctrl", "g"],      # Find next
    ["ctrl", "shift", "g"],  # Find previous
    ["ctrl", "h"],      # History (Windows/Linux)
    ["cmd", "y"],       # History (macOS)
    
    # Page actions
    ["ctrl", "r"],      # Refresh page
    ["ctrl", "shift", "r"],  # Hard refresh (Windows/Linux)
    ["cmd", "shift", "r"],   # Hard refresh (macOS)
    ["ctrl", "shift", "delete"],  # Clear browsing data
    ["f5"],             # Refresh (Windows/Linux)
    ["cmd", "r"],       # Refresh (macOS)
    ["f11"],            # Fullscreen (Windows/Linux)
    ["cmd", "ctrl", "f"],  # Fullscreen (macOS)
    ["ctrl", "l"],      # Focus address bar
    ["cmd", "l"],       # Focus address bar (macOS)
    ["ctrl", "shift", "l"],  # Open address bar suggestion dropdown
    ["ctrl", "k"],      # Open search (Chrome)
    ["ctrl", "y"],      # Open downloads
    ["ctrl", "shift", "b"],  # Toggle bookmarks bar
    
    # Developer tools
    ["f12"],            # Open DevTools (Windows/Linux)
    ["cmd", "option", "i"],  # Open DevTools (macOS)
    ["ctrl", "shift", "i"],  # Open DevTools (Windows/Linux alternative)
    ["ctrl", "shift", "j"],  # Open DevTools Console (Windows/Linux)
    ["cmd", "option", "j"],  # Open DevTools Console (macOS)
    
    # Zoom
    ["ctrl", "plus"],   # Zoom in
    ["ctrl", "minus"],  # Zoom out
    ["ctrl", "0"],      # Reset zoom
    
    # Tab management
    ["ctrl", "1"],      # Jump to first tab
    ["ctrl", "2"],      # Jump to second tab
    ["ctrl", "3"],      # Jump to third tab
    ["ctrl", "4"],      # Jump to fourth tab
    ["ctrl", "5"],      # Jump to fifth tab
    ["ctrl", "6"],      # Jump to sixth tab
    ["ctrl", "7"],      # Jump to seventh tab
    ["ctrl", "8"],      # Jump to eighth tab
    ["ctrl", "9"],      # Jump to last tab
    ["alt", "1"],       # Jump to first tab (alternative)
    ["alt", "2"],       # Jump to second tab (alternative)
    ["alt", "3"],       # Jump to third tab (alternative)
    ["alt", "4"],       # Jump to fourth tab (alternative)
    ["alt", "5"],       # Jump to fifth tab (alternative)
    ["alt", "6"],       # Jump to sixth tab (alternative)
    ["alt", "7"],       # Jump to seventh tab (alternative)
    ["alt", "8"],       # Jump to eighth tab (alternative)
    ["alt", "9"],       # Jump to last tab (alternative)
    
    # Page interaction
    ["space"],          # Scroll down / Play video
    ["shift", "space"], # Scroll up
    ["pagedown"],       # Scroll down
    ["pageup"],         # Scroll up
    ["home"],           # Jump to top
    ["end"],            # Jump to bottom
    
    # ============ SYSTEM SHORTCUTS ============
    ["print"],          # Print page / Take screenshot
    ["ctrl", "p"],      # Print
    ["alt", "f4"],      # Close app (Windows)
    
    # ============ GENERAL NAVIGATION ============
    ["tab"],            # Tab forward
    ["shift", "tab"],   # Tab backward
    ["enter"],          # Confirm/Submit
    ["escape"],         # Cancel/Close
    ["delete"],         # Delete
    ["backspace"],      # Backspace
]