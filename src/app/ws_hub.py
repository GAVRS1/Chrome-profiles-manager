from __future__ import annotations
import asyncio
import json
import logging
import threading
import time
import websockets
from websockets.server import WebSocketServerProtocol
from typing import Dict, Optional

log = logging.getLogger("hub")

IDLE_TIMEOUT = 120  # секунды без активности до удаления клиента

class Client:
    def __init__(self, ws: WebSocketServerProtocol, name: str, ua: str):
        self.ws = ws
        self.name = name
        self.ua = ua
        self.ts = time.time()  # время последнего пакета

    def touch(self):
        self.ts = time.time()


class WSHub:
    """Локальный WebSocket-хаб для связи между профилями Chrome."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self._host = host
        self._port = port
        self._clients: Dict[str, Client] = {}
        self._master: Optional[str] = None
        self._server: Optional[asyncio.AbstractServer] = None
        self._lock: asyncio.Lock | None = None
        self._disabled: set[str] = set()
        self._disabled_lock = threading.Lock()
        self._clients_guard = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    # ───────── управление ─────────
    async def start(self):
        if self._lock is None:
            self._lock = asyncio.Lock()

        async def handler(ws: WebSocketServerProtocol):
            name = self._parse_name(ws.path)
            ua = ws.request_headers.get("User-Agent", "?")
            client = Client(ws, name, ua)
            async with self._lock:
                with self._clients_guard:
                    self._clients[name] = client
            with self._disabled_lock:
                # Автоматически включаем клиента при новом подключении
                if name in self._disabled:
                    self._disabled.remove(name)
            log.info("[HUB] connect: %s", name)
            await self._broadcast_state()

            try:
                async for raw in ws:
                    await self._on_message(name, raw)
            except Exception as e:
                log.debug("[HUB] ws error %s: %s", name, e)
            finally:
                async with self._lock:
                    with self._clients_guard:
                        if name in self._clients:
                            self._clients.pop(name, None)
                with self._disabled_lock:
                    self._disabled.discard(name)
                log.info("[HUB] disconnect: %s", name)
                await self._broadcast_state()

        # важное: задаём ping-интервалы и НЕ выходим из корутины, пока сервер жив
        self._server = await websockets.serve(
            handler,
            self._host,
            self._port,
            ping_interval=20,
            ping_timeout=20,
            max_queue=64,
        )
        log.info("[HUB] listening on ws://%s:%s", self._host, self._port)
        asyncio.create_task(self._janitor())

        # держим обработчик до остановки сервера
        await self._server.wait_closed()

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            log.info("[HUB] stopped")

    # ───────── внутренние ─────────
    async def _on_message(self, name: str, raw: str):
        client = self._clients.get(name)
        if not client:
            return
        client.touch()

        try:
            msg = json.loads(raw)
        except Exception:
            return

        t = msg.get("type")

        # Heartbeat — просто продлеваем жизнь
        if t == "status":
            return

        # Если это действие мастера — переслать всем остальным
        if self._master and name == self._master:
            await self._broadcast_to_followers(msg)
        else:
            # не-мастер что-то шлёт — игнорируем, но можно отлогировать при необходимости
            pass

    async def _broadcast_to_followers(self, msg: dict):
        data = json.dumps(msg)
        dead = []
        with self._disabled_lock:
            disabled_copy = set(self._disabled)
        with self._clients_guard:
            items = list(self._clients.items())
        for n, c in items:
            if n == self._master or n in disabled_copy:
                continue
            try:
                await c.ws.send(data)
            except Exception:
                dead.append(n)
        if dead:
            async with self._lock:
                for n in dead:
                    self._clients.pop(n, None)
            await self._broadcast_state()

    async def _broadcast_state(self):
        """Рассылаем обновлённое состояние всем подключённым клиентам (и логируем)."""
        with self._disabled_lock:
            disabled_copy = set(self._disabled)
        state = {
            "type": "hub_state",
            "clients": list(self._clients.keys()),
            "master": self._master,
            "ts": int(time.time()),
            "disabled": list(disabled_copy),
        }
        data = json.dumps(state)
        # попытка массовой рассылки состояния; ошибки — молча
        with self._clients_guard:
            clients = list(self._clients.values())
        for c in clients:
            try:
                await c.ws.send(data)
            except Exception:
                pass

        with self._clients_guard:
            clients_names = list(self._clients.keys())
        log.info("[HUB] clients: %s", ", ".join(clients_names) or "(none)")
        log.info("[HUB] master: %s", self._master or "(none)")

    async def _janitor(self):
        """Периодически очищает неактивных клиентов."""
        while True:
            await asyncio.sleep(5)
            now = time.time()
            async with self._lock:
                with self._clients_guard:
                    dead = [n for n, c in self._clients.items() if (now - c.ts) > IDLE_TIMEOUT]
                    for n in dead:
                        log.debug("[HUB] drop idle %s", n)
                        self._clients.pop(n, None)
            if dead:
                with self._disabled_lock:
                    for n in dead:
                        self._disabled.discard(n)
            if dead:
                await self._broadcast_state()

    @staticmethod
    def _parse_name(path: str) -> str:
        # path вида "/?profile=hello"
        if not path:
            return "anon"
        if "profile=" in path:
            try:
                return path.split("profile=")[1].split("&")[0]
            except Exception:
                return "anon"
        return "anon"

    # ───────── API для GUI ─────────
    def set_master(self, name: Optional[str]):
        self._master = name

    def current_master(self) -> Optional[str]:
        return self._master

    def list_clients(self) -> Dict[str, dict]:
        """Состояние для отображения в GUI."""
        out = {}
        with self._disabled_lock:
            disabled = set(self._disabled)
        with self._clients_guard:
            items = list(self._clients.items())
        for n, c in items:
            out[n] = {
                "since": f"{int(time.time()-c.ts)}s",
                "enabled": n not in disabled,
            }
        return out

    # ───────── управление из GUI ─────────
    def set_client_enabled(self, name: str, enabled: bool) -> None:
        with self._disabled_lock:
            if enabled:
                self._disabled.discard(name)
            else:
                self._disabled.add(name)

    def disabled_clients(self) -> set[str]:
        with self._disabled_lock:
            return set(self._disabled)

    # ───────── синхронный запуск ─────────
    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def runner():
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.start())
            finally:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                try:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                loop.close()
                self._loop = None

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        loop = self._loop
        if not loop:
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(self.stop(), loop)
            fut.result(timeout=5)
        except Exception:
            log.warning("[HUB] stop timed out")
        finally:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)
            self._thread = None
            self._server = None
            with self._disabled_lock:
                self._disabled.clear()
            with self._clients_guard:
                self._clients.clear()
            self._lock = None

