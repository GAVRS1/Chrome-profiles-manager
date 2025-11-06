from __future__ import annotations
import win32gui
import win32process
import win32con
from dataclasses import dataclass
from typing import Optional, List
from .config import CHROME_WINDOW_CLASS, CHROME_WINDOW_CLASSES

@dataclass
class WindowInfo:
    hwnd: int
    pid: int
    rect: tuple[int, int, int, int]  # left, top, right, bottom

class ChromeWindowManager:
    def __init__(self) -> None:
        self._windows: dict[int, WindowInfo] = {}  # pid -> any hwnd

    def refresh(self, candidate_pids: list[int]) -> dict[int, WindowInfo]:
        self._windows.clear()
        classes = CHROME_WINDOW_CLASSES or [CHROME_WINDOW_CLASS]
        def _enum(hwnd, _):
            try:
                cls = win32gui.GetClassName(hwnd)
                if cls not in classes and cls != CHROME_WINDOW_CLASS:
                    return
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid in candidate_pids and win32gui.IsWindowVisible(hwnd):
                    rect = win32gui.GetWindowRect(hwnd)
                    self._windows.setdefault(pid, WindowInfo(hwnd=hwnd, pid=pid, rect=rect))
            except Exception:
                return
        win32gui.EnumWindows(_enum, None)
        return dict(self._windows)

    def get_by_pid(self, pid: int) -> Optional[WindowInfo]:
        return self._windows.get(pid)

    @staticmethod
    def windows_for_pid(pid: int) -> List[int]:
        """Все видимые top-level окна процесса pid."""
        hwnds: list[int] = []
        def _enum(hwnd, _):
            try:
                _, p = win32process.GetWindowThreadProcessId(hwnd)
                if p == pid and win32gui.IsWindowVisible(hwnd):
                    hwnds.append(hwnd)
            except Exception:
                pass
        win32gui.EnumWindows(_enum, None)
        return hwnds

    @staticmethod
    def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
        return win32gui.ClientToScreen(hwnd, (x, y))
