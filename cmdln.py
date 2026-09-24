import subprocess
import time
import pygetwindow as gw
import pyautogui


class StealthTerminal:
    _instances = []

    def __init__(self, title="MyHiddenTerminal"):
        self.title = title
        self.window = None
        self._hidden = False
        self._original_pos = None

    def spawn(self, command=None):
        """Spawns a new terminal window with correct title parsing."""
        if command:
            cmd = ['start', f'"{self.title}"', 'cmd', '/k', command]
        else:
            cmd = ['start', f'"{self.title}"', 'cmd', '/k', 'echo Terminal Ready']
        subprocess.Popen(" ".join(cmd), shell=True)
        time.sleep(1.0)

        windows = gw.getWindowsWithTitle(self.title)
        if windows:
            self.window = windows[0]
            print(f"Terminal '{self.title}' spawned successfully.")
        else:
            print(f"Could not find window with title: {self.title}")
            print(f"Available windows: {[w.title for w in gw.getAllWindows()]}")

        StealthTerminal._instances.append(self)

    def hide(self):
        """Move the terminal off-screen so it's hidden from view and screenshots."""
        if self.window:
            try:
                self._original_pos = (self.window.left, self.window.top)
                self.window.moveTo(-2000, -2000)
                self._hidden = True
            except Exception:
                pass

    def show(self):
        """Restore the terminal to its original position."""
        if self.window and self._original_pos:
            try:
                self.window.moveTo(*self._original_pos)
                self._hidden = False
            except Exception:
                pass

    @classmethod
    def hide_all(cls):
        """Hide all spawned terminals."""
        for inst in cls._instances:
            inst.hide()

    @classmethod
    def show_all(cls):
        """Restore all spawned terminals."""
        for inst in cls._instances:
            inst.show()

    def move_and_screenshot(self, filename="clean_capture.png"):
        """Moves the specific window, captures the screen, and moves it back."""
        if not self.window:
            print("Terminal not spawned yet.")
            return

        original_pos = (self.window.left, self.window.top)
        self.window.moveTo(-2000, -2000)
        time.sleep(0.2)

        screenshot = pyautogui.screenshot()
        screenshot.save(filename)

        self.window.moveTo(*original_pos)
        print(f"Screenshot taken. Window restored to {original_pos}")

