from __future__ import annotations
import asyncio
import json
import logging
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
        self._lock = asyncio.Lock()

    # ───────── управление ─────────
    async def start(self):
        async def handler(ws: WebSocketServerProtocol):
            name = self._parse_name(ws.path)
            ua = ws.request_headers.get("User-Agent", "?")
            client = Client(ws, name, ua)
            async with self._lock:
                self._clients[name] = client
            log.info("[HUB] connect: %s", name)
            await self._broadcast_state()

            try:
                async for raw in ws:
                    await self._on_message(name, raw)
            except Exception as e:
                log.debug("[HUB] ws error %s: %s", name, e)
            finally:
                async with self._lock:
                    if name in self._clients:
                        self._clients.pop(name, None)
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
        for n, c in self._clients.items():
            if n == self._master:
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
        state = {
            "type": "hub_state",
            "clients": list(self._clients.keys()),
            "master": self._master,
            "ts": int(time.time()),
        }
        data = json.dumps(state)
        # попытка массовой рассылки состояния; ошибки — молча
        for c in list(self._clients.values()):
            try:
                await c.ws.send(data)
            except Exception:
                pass

        log.info("[HUB] clients: %s", ", ".join(self._clients.keys()) or "(none)")
        log.info("[HUB] master: %s", self._master or "(none)")

    async def _janitor(self):
        """Периодически очищает неактивных клиентов."""
        while True:
            await asyncio.sleep(5)
            now = time.time()
            async with self._lock:
                dead = [n for n, c in self._clients.items() if (now - c.ts) > IDLE_TIMEOUT]
                for n in dead:
                    log.debug("[HUB] drop idle %s", n)
                    self._clients.pop(n, None)
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
        for n, c in self._clients.items():
            out[n] = {"since": f"{int(time.time()-c.ts)}s"}
        return out

    # ───────── синхронный запуск ─────────
    def start_sync(self):
        # запускаем и держим цикл до остановки сервера
        asyncio.run(self.start())
