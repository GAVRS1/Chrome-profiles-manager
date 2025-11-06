from __future__ import annotations
import logging
import threading
import time
import win32api
import win32con
import win32gui
from typing import Callable
import keyboard
import mouse  # используем общий hook

from .chrome_window_manager import WindowInfo

log = logging.getLogger("sync")

class SyncManager:
    """
    Нативное зеркалирование ввода (WinAPI).
    Используем единый mouse.hook(...) для всех событий мыши.
    """

    def __init__(self, window_lookup: Callable[[], list[WindowInfo]]):
        self._get_targets = window_lookup
        self._master_hwnd_provider: Callable[[], int | None] | None = None
        self._enabled = False
        self._lock = threading.RLock()

        # опции
        self.forward_mouse = True
        self.forward_keyboard = True
        self.forward_mouse_move = True
        self._mouse_move_interval = 0.02  # сек, чтобы не забивать очередь сообщений
        self._last_mouse_move_ts = 0.0

    def set_master_provider(self, fn: Callable[[], int | None]) -> None:
        self._master_hwnd_provider = fn

    def enable(self) -> None:
        with self._lock:
            if self._enabled:
                return
            self._enabled = True
        self._install_hooks()

    def disable(self) -> None:
        with self._lock:
            if not self._enabled:
                return
            self._enabled = False
        # снимем все хуки
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            mouse.unhook_all()
        except Exception:
            pass

    # ---------------- internal ----------------

    def _install_hooks(self) -> None:
        # Мышь: один общий hook
        try:
            mouse.hook(self._on_mouse)
        except Exception as e:
            log.warning("mouse.hook failed: %s", e)

        # Клавиатура
        try:
            keyboard.hook(self._on_key)
        except Exception as e:
            log.warning("keyboard.hook failed: %s", e)

    def _targets_hwnds(self) -> list[int]:
        """Все HWND, кроме мастер-окна."""
        master = self._master_hwnd_provider() if self._master_hwnd_provider else None
        hwnds: list[int] = []
        for w in self._get_targets():
            hwnd = getattr(w, "hwnd", None)
            if not hwnd or hwnd == master:
                continue
            try:
                if win32gui.IsWindow(hwnd) and win32gui.IsWindowEnabled(hwnd):
                    hwnds.append(hwnd)
            except Exception:
                continue
        return hwnds

    # ---------- mouse hook ----------
    def _on_mouse(self, event):
        if not self._enabled or not self.forward_mouse:
            return

        et = getattr(event, "event_type", None)  # 'down'|'up'|'move'|'wheel'
        ex = int(getattr(event, "x", 0))  # экранные координаты
        ey = int(getattr(event, "y", 0))

        # КОЛЕСО: для WM_MOUSEWHEEL – экранные координаты корректны
        if et == "wheel" or hasattr(event, "delta"):
            delta_raw = getattr(event, "delta", 0)
            try:
                delta = int(delta_raw * 120)  # wheel шаги -> 120
            except Exception:
                delta = 0
            for hwnd in self._targets_hwnds():
                try:
                    lparam = win32api.MAKELONG(ex & 0xFFFF, ey & 0xFFFF)
                    win32gui.PostMessage(hwnd, win32con.WM_MOUSEWHEEL, (delta << 16), lparam)
                except Exception as e:
                    log.debug("wheel send failed %s", e)
            return

        # КЛИКИ: для WM_*BUTTON* нужны КЛИЕНТСКИЕ координаты!
        btn = getattr(event, "button", None)
        if btn is not None:
            name = str(btn)
            if "left" in name:
                msg_down, msg_up = win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP
            elif "right" in name:
                msg_down, msg_up = win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP
            elif "middle" in name:
                msg_down, msg_up = win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP
            else:
                msg_down = msg_up = None

            if msg_down is not None and et in ("down", "up"):
                for hwnd in self._targets_hwnds():
                    try:
                        cx, cy = win32gui.ScreenToClient(hwnd, (ex, ey))
                        lparam = win32api.MAKELONG(cx & 0xFFFF, cy & 0xFFFF)
                        win32gui.PostMessage(hwnd, msg_down if et == "down" else msg_up, 0, lparam)
                    except Exception as e:
                        log.debug("mouse send failed %s", e)
                return
        # ДВИЖЕНИЕ МЫШИ: полезно для наведения и drag&drop
        if et == "move" and self.forward_mouse_move:
            now = time.perf_counter()
            if now - self._last_mouse_move_ts < self._mouse_move_interval:
                return
            self._last_mouse_move_ts = now
            for hwnd in self._targets_hwnds():
                try:
                    cx, cy = win32gui.ScreenToClient(hwnd, (ex, ey))
                    lparam = win32api.MAKELONG(cx & 0xFFFF, cy & 0xFFFF)
                    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
                except Exception as e:
                    log.debug("mouse move send failed %s", e)


    # ---------- keyboard hook ----------
    def _on_key(self, event):
        if not self._enabled or not self.forward_keyboard:
            return
        is_down = getattr(event, "event_type", "") == "down"
        name = getattr(event, "name", None)
        vk = self._name_to_vk(name)
        if vk is None:
            return

        msg = win32con.WM_KEYDOWN if is_down else win32con.WM_KEYUP

        # отправка DOWN/UP
        for hwnd in self._targets_hwnds():
            try:
                win32gui.PostMessage(hwnd, msg, vk, 0)
            except Exception as e:
                log.debug("key send failed %s", e)

        # ДОПОЛНИТЕЛЬНО: для печатных символов — WM_CHAR (на нажатии)
        if is_down and name and len(name) == 1:
            ch = ord(name)
            for hwnd in self._targets_hwnds():
                try:
                    win32gui.PostMessage(hwnd, win32con.WM_CHAR, ch, 0)
                except Exception as e:
                    log.debug("char send failed %s", e)

    @staticmethod
    def _name_to_vk(name: str | None) -> int | None:
        if not name:
            return None
        special = {
            "enter": win32con.VK_RETURN,
            "esc": win32con.VK_ESCAPE,
            "escape": win32con.VK_ESCAPE,
            "tab": win32con.VK_TAB,
            "ctrl": win32con.VK_CONTROL,
            "alt": win32con.VK_MENU,
            "shift": win32con.VK_SHIFT,
            "left": win32con.VK_LEFT,
            "right": win32con.VK_RIGHT,
            "up": win32con.VK_UP,
            "down": win32con.VK_DOWN,
            "space": win32con.VK_SPACE,
            "backspace": win32con.VK_BACK,
            "delete": win32con.VK_DELETE,
            "home": win32con.VK_HOME,
            "end": win32con.VK_END,
            "page up": win32con.VK_PRIOR,
            "page down": win32con.VK_NEXT,
        }
        if name in special:
            return special[name]
        if len(name) == 1:
            return ord(name.upper())
        return None
