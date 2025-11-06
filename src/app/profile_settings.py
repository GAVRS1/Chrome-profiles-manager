from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

__all__ = ["ProfileSettings"]


@dataclass
class ProfileSettings:
    """Настройки, хранимые вместе с профилем Chrome."""

    start_url: str = ""
    proxy_enabled: bool = False
    proxy_host: str = ""
    proxy_port: int | None = None

    @property
    def proxy_server(self) -> str | None:
        """Возвращает строку вида "host:port" для передачи Chrome."""

        if not self.proxy_enabled:
            return None
        host = (self.proxy_host or "").strip()
        if not host:
            return None
        if self.proxy_port:
            return f"{host}:{self.proxy_port}"
        return host

    @classmethod
    def load(cls, directory: Path) -> "ProfileSettings":
        path = directory / "profile.json"
        if not path.exists():
            settings = cls()
            settings.save(directory)
            return settings
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return cls()

        settings = cls()
        settings.start_url = str(payload.get("start_url", ""))
        settings.proxy_enabled = bool(payload.get("proxy_enabled", False))
        settings.proxy_host = str(payload.get("proxy_host", ""))
        proxy_port = payload.get("proxy_port")
        try:
            settings.proxy_port = int(proxy_port) if proxy_port is not None else None
        except Exception:
            settings.proxy_port = None
        return settings

    def save(self, directory: Path) -> None:
        path = directory / "profile.json"
        data = asdict(self)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

