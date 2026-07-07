from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import shutil
import psutil
import time
from typing import Optional, List, Dict, Set
from .config import PROFILES_ROOT, CANDIDATE_CHROME_PATHS, CHROME_ARGS_BASE, EXTENSION_PATH
from .profile_settings import ProfileSettings

__all__ = ["ProfileInfo", "ProfileManager"]

def _find_chrome_path() -> Optional[str]:
    for p in CANDIDATE_CHROME_PATHS:
        if Path(p).exists():
            return p
    return None

@dataclass
class ProfileInfo:
    name: str
    path: Path
    pid: Optional[int] = None
    settings: ProfileSettings = field(default_factory=ProfileSettings)

class ProfileManager:
    """
    Быстрое сопоставление процессов с профилями по --user-data-dir.
    Завершение профиля: WM_CLOSE всем окнам → terminate() всем PID → kill() оставшимся.
    """
    def __init__(self) -> None:
        self._chrome_path: Optional[str] = _find_chrome_path()
        self._profiles: List[ProfileInfo] = []
        self.refresh_filesystem()
        self.attach_running_pids()

    @property
    def chrome_path(self) -> Optional[str]:
        return self._chrome_path

    # ---------- FS ----------
    def refresh_filesystem(self) -> List[ProfileInfo]:
        self._profiles.clear()
        for p in sorted(PROFILES_ROOT.glob("*")):
            if p.is_dir():
                settings = ProfileSettings.load(p)
                self._profiles.append(ProfileInfo(name=p.name, path=p, settings=settings))
        return list(self._profiles)

    def list(self) -> List[ProfileInfo]:
        return list(self._profiles)

    def get(self, name: str) -> ProfileInfo:
        for i in self._profiles:
            if i.name == name:
                return i
        raise KeyError(name)

    def create(self, name: str) -> ProfileInfo:
        path = PROFILES_ROOT / name
        path.mkdir(parents=True, exist_ok=False)
        settings = ProfileSettings()
        settings.save(path)
        info = ProfileInfo(name=name, path=path, settings=settings)
        self._profiles.append(info)
        return info

    def delete(self, name: str) -> None:
        info = self.get(name)
        if info.pid:
            raise RuntimeError("Нельзя удалить запущенный профиль")
        shutil.rmtree(info.path, ignore_errors=True)
        self.refresh_filesystem()

    # ---------- процессы ----------
    @staticmethod
    def _user_data_dir(cmdline: List[str] | None) -> Optional[str]:
        """Достаёт значение --user-data-dir из аргументов процесса."""
        for arg in cmdline or []:
            if arg.startswith("--user-data-dir="):
                return arg.split("=", 1)[1].strip('"')
        return None

    def _pids_for_profile(self, prof: ProfileInfo) -> Set[int]:
        """Все PID профиля: корневые процессы Chrome с его --user-data-dir и их дети."""
        pids: Set[int] = set()
        prof_path = str(prof.path)

        roots: Set[int] = set()
        for p in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                if "chrome" not in (p.info["name"] or "").lower():
                    continue
                # точное сравнение: подстрока ловила чужой профиль (a ⊂ a1)
                if self._user_data_dir(p.info.get("cmdline")) == prof_path:
                    roots.add(p.info["pid"])
            except Exception:
                continue

        for pid in roots:
            try:
                proc = psutil.Process(pid)
                pids.add(pid)
                for ch in proc.children(recursive=True):
                    pids.add(ch.pid)
            except Exception:
                continue

        return pids

    def attach_running_pids(self) -> Dict[str, int | None]:
        for i in self._profiles:
            i.pid = None
        found: Dict[str, int | None] = {p.name: None for p in self._profiles}
        if not self._profiles:
            return found
        # один проход по процессам, поиск по хеш-таблице путей, ранний выход
        by_path: Dict[str, ProfileInfo] = {str(p.path): p for p in self._profiles}
        remaining = len(by_path)
        for p in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            if remaining == 0:
                break
            try:
                if "chrome" not in (p.info["name"] or "").lower():
                    continue
                udd = self._user_data_dir(p.info.get("cmdline"))
                if not udd:
                    continue
                prof = by_path.get(udd)
                if prof is not None and found[prof.name] is None:
                    found[prof.name] = p.info["pid"]
                    prof.pid = p.info["pid"]
                    remaining -= 1
            except Exception:
                continue
        return found

    def launch(self, name: str, extra_args: Optional[List[str]] = None) -> int:
        info = self.get(name)
        if not self._chrome_path:
            raise RuntimeError("chrome.exe не найден. Укажите путь в config.py")
        args: List[str] = [
            self._chrome_path,
            f"--user-data-dir={str(info.path)}",
            *CHROME_ARGS_BASE,
        ]
        if EXTENSION_PATH and EXTENSION_PATH.exists():
            args.append(f"--load-extension={str(EXTENSION_PATH)}")
        proxy = info.settings.proxy_server
        if proxy:
            args.append(f"--proxy-server={proxy}")
        if extra_args:
            args.extend(extra_args)
        start_url = info.settings.start_url.strip()
        if start_url:
            args.append(start_url)
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        info.pid = proc.pid
        return info.pid

    def update_settings(self, name: str, settings: ProfileSettings) -> ProfileSettings:
        info = self.get(name)
        info.settings = settings
        settings.save(info.path)
        return settings

    def stop_fast(self, name: str, soft_ms: int = 600, term_ms: int = 900) -> None:
        info = self.get(name)
        if not info:
            return

        # 0) соберём все PID профиля, включая дочерние
        pids = self._pids_for_profile(info)
        if info.pid:
            pids.add(info.pid)
        if not pids:
            info.pid = None
            return

        # 1) WM_CLOSE всем окнам (только у тех, у кого есть HWND)
        try:
            from .chrome_window_manager import ChromeWindowManager
            for pid in list(pids):
                try:
                    for hwnd in ChromeWindowManager.windows_for_pid(pid):
                        import win32gui, win32con
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except Exception:
                    continue
        except Exception:
            pass

        # 2) мягкая пауза
        time.sleep(soft_ms/1000)

        # 3) terminate всем, кто жив (обновим список — могли появиться дети)
        more: Set[int] = set()
        for pid in list(pids):
            try:
                if psutil.pid_exists(pid):
                    proc = psutil.Process(pid)
                    proc.terminate()
                    for ch in proc.children(recursive=True):
                        more.add(ch.pid)
            except Exception:
                pass
        pids |= more

        # 4) пауза
        time.sleep(term_ms/1000)

        # 5) kill остатки
        for pid in list(pids):
            try:
                if psutil.pid_exists(pid):
                    psutil.Process(pid).kill()
            except Exception:
                pass

        info.pid = None